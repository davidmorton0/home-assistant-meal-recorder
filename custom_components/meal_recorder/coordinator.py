"""Reads the CSV files and keeps the published data up to date."""

from __future__ import annotations

import asyncio
import logging
import calendar
from datetime import date, datetime, timedelta
from typing import Any, NamedTuple

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import aggregate, stats
from .const import (
    CONF_PERSONS,
    DEFAULT_INTAKE_PRESET,
    DEFAULT_INTAKES,
    DOMAIN,
    NUTRIENTS,
    SIGNAL_DATA_UPDATED,
    SIGNAL_PERSON_ADDED,
    SIGNAL_VIEW_UPDATED,
    STORAGE_DIR,
)
from .items import normalise_person
from .storage import CsvStore

_LOGGER = logging.getLogger(__name__)


class UnknownPerson(Exception):
    """A request named a person who has not been created in the integration."""

    def __init__(self, person: str) -> None:
        super().__init__(f"{person!r} has not been added")
        self.person = person


class DuplicateId(Exception):
    """A batch holds ids that are already stored."""

    def __init__(self, ids: list[str]) -> None:
        super().__init__(f"already stored: {', '.join(ids)}")
        self.ids = ids


class ItemNotFound(Exception):
    """No stored item has the id asked for."""

    def __init__(self, item_id: str) -> None:
        super().__init__(f"no item has id {item_id!r}")
        self.item_id = item_id


class PersonCollision(Exception):
    """Two person names normalise onto the same folder."""

    def __init__(self, person: str, existing: str, folder: str) -> None:
        super().__init__(f"{person!r} collides with {existing!r} in folder {folder!r}")
        self.person = person
        self.existing = existing
        self.folder = folder


class View(NamedTuple):
    """What the dashboard shows: a person's day."""

    folder: str
    day: date


class MealRecorderCoordinator:
    """Owns the store, the selected date and the data published as entities."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.store = CsvStore(hass.config.path(STORAGE_DIR))
        self.selected_date: date = dt_util.now().date()
        self.data: dict[str, dict[str, Any]] = {}
        # The dashboard's person, month and day, kept across restarts. Until
        # one is picked, the first person in the list is shown.
        self.view = View("", dt_util.now().date())
        self.view_records: list[dict[str, Any]] = []
        self.view_months: list[tuple[int, int]] = []
        self._view_store: Store = Store(hass, 1, f"{DOMAIN}.view")
        # Each person's daily intake targets, by folder, kept across restarts.
        self.intakes: dict[str, dict[str, Any]] = {}
        self._intakes_store: Store = Store(hass, 1, f"{DOMAIN}.intakes")
        self._announced: set[str] = set()
        self._refreshing = False
        # Batches arriving at once are written one after another.
        self._write_lock = asyncio.Lock()

    # Person registry -----------------------------------------------------

    @property
    def persons(self) -> dict[str, str]:
        """Folder to person name, as recorded when items were stored."""
        return dict(self.entry.data.get(CONF_PERSONS, {}))

    @property
    def folders(self) -> list[str]:
        """The folders of the people who have been added."""
        return sorted(self.persons)

    def person_name(self, folder: str) -> str:
        return self.persons.get(folder, folder)

    def folder_for(self, person: str) -> str:
        """Return the folder of a person who has been added."""
        folder = normalise_person(person)
        existing = self.persons.get(folder)
        if existing is None:
            raise UnknownPerson(person)
        if existing != person:
            raise UnknownPerson(person)
        return folder

    async def async_add_person(self, person: str) -> str:
        """Add a person: their folder, entities and any files already there."""
        folder = normalise_person(person)
        existing = self.persons.get(folder)
        if existing == person:
            return folder
        if existing is not None:
            raise PersonCollision(person, existing, folder)

        persons = {**self.persons, folder: person}
        self.hass.config_entries.async_update_entry(
            self.entry, data={**self.entry.data, CONF_PERSONS: persons}
        )
        await self.async_refresh()
        self._announce(self.folders)
        return folder

    def _announce(self, folders: list[str]) -> None:
        """Ask the platforms for entities for folders not seen before."""
        for folder in folders:
            if folder in self._announced:
                continue
            self._announced.add(folder)
            async_dispatcher_send(
                self.hass, f"{SIGNAL_PERSON_ADDED}_{self.entry.entry_id}", folder
            )

    def mark_announced(self, folder: str) -> None:
        """Record that a platform has already made this folder's entities."""
        self._announced.add(folder)

    # Writing -------------------------------------------------------------

    async def async_add_items(self, items: list[dict[str, Any]]) -> list[str]:
        """Append items to their files.

        Raises UnknownPerson or DuplicateId before writing anything.
        """
        for item in items:
            item["folder"] = self.folder_for(item["person"])

        async with self._write_lock:
            stored = await self.hass.async_add_executor_job(self.store.ids)
            duplicates = [item["id"] for item in items if item["id"] in stored]
            if duplicates:
                raise DuplicateId(duplicates)
            await self.hass.async_add_executor_job(self.store.append_items, items)
        await self.async_refresh()
        since: dict[str, date] = {}
        for item in items:
            day = item["created_at"].date()
            since[item["folder"]] = min(day, since.get(item["folder"], day))
        await self.async_update_statistics(since)
        return [item["id"] for item in items]

    async def async_list_items(
        self, folders: list[str], start: date, end: date
    ) -> list[dict[str, Any]]:
        """The stored items of some people between two days, oldest first.

        Each record holds the folder it was read from.
        """
        return await self.hass.async_add_executor_job(self._read_items, folders, start, end)

    def _read_items(
        self, folders: list[str], start: date, end: date
    ) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        last = end.year * 12 + end.month - 1
        for folder in folders:
            index = start.year * 12 + start.month - 1
            while index <= last:
                for record in self.store.read_month(folder, index // 12, index % 12 + 1):
                    if start <= record["created_at"].date() <= end:
                        found.append({**record, "folder": folder})
                index += 1
        found.sort(key=lambda record: record["created_at"])
        return found

    async def async_find_item(self, item_id: str) -> tuple[str, dict[str, Any]]:
        """The folder and the stored record of an item. Raises ItemNotFound."""
        for folder in self.folders:
            record = await self.hass.async_add_executor_job(
                self.store.get_item, folder, item_id
            )
            if record is not None:
                return folder, record
        raise ItemNotFound(item_id)

    async def async_update_item(self, folder: str, item: dict[str, Any]) -> None:
        """Replace a person's stored item with the same id. Raises ItemNotFound."""
        async with self._write_lock:
            old = await self.hass.async_add_executor_job(
                self.store.get_item, folder, item["id"]
            )
            found = await self.hass.async_add_executor_job(
                self.store.update_item, folder, item
            )
        if not found:
            raise ItemNotFound(item["id"])
        await self.async_refresh()
        day = item["created_at"].date()
        if old is not None:
            day = min(day, old["created_at"].date())
        await self.async_update_statistics({folder: day})

    async def async_delete_item(self, folder: str, item_id: str) -> None:
        """Remove a person's stored item. Raises ItemNotFound."""
        async with self._write_lock:
            old = await self.hass.async_add_executor_job(
                self.store.get_item, folder, item_id
            )
            found = await self.hass.async_add_executor_job(
                self.store.delete_item, folder, item_id
            )
        if not found or old is None:
            raise ItemNotFound(item_id)
        await self.async_refresh()
        await self.async_update_statistics({folder: old["created_at"].date()})

    # The dashboard's view ------------------------------------------------

    async def async_load_view(self) -> None:
        """Restore the person, month and day picked before a restart."""
        saved = await self._view_store.async_load()
        if saved:
            try:
                self.view = View(saved["folder"], date.fromisoformat(saved["day"]))
            except (KeyError, TypeError, ValueError):
                _LOGGER.warning("Ignoring the saved dashboard selection %s", saved)

    async def async_set_view(self, folder: str | None = None, day: date | None = None) -> None:
        """Pick the person or the day shown, then load that day's items."""
        if folder is not None:
            if folder not in self.persons:
                raise UnknownPerson(folder)
            self.view = View(folder, self.view.day)
        if day is not None:
            self.view = View(self.view.folder, day)
        self._view_store.async_delay_save(
            lambda: {"folder": self.view.folder, "day": self.view.day.isoformat()}, 1
        )
        await self._async_read_view()

    async def async_set_view_month(self, year: int, month: int) -> None:
        """Pick a month, keeping the day of the month where it can."""
        last = calendar.monthrange(year, month)[1]
        await self.async_set_view(day=date(year, month, min(self.view.day.day, last)))

    async def async_shift_view(self, days: int = 0, months: int = 0) -> None:
        """Move the day shown by days, or by whole months."""
        if months:
            index = self.view.day.year * 12 + self.view.day.month - 1 + months
            await self.async_set_view_month(index // 12, index % 12 + 1)
        else:
            await self.async_set_view(day=self.view.day + timedelta(days=days))

    async def _async_read_view(self) -> None:
        folders = self.folders
        if self.view.folder not in folders and folders:
            self.view = View(folders[0], self.view.day)
        self.view_records, self.view_months = await self.hass.async_add_executor_job(
            self._read_view, self.view
        )
        async_dispatcher_send(self.hass, f"{SIGNAL_VIEW_UPDATED}_{self.entry.entry_id}")

    def _read_view(self, view: View) -> tuple[list[dict[str, Any]], list[tuple[int, int]]]:
        day = view.day
        records = [
            record
            for record in self.store.read_month(view.folder, day.year, day.month)
            if record["created_at"].date() == day
        ]
        # Every month from the first stored one to now, so past months with
        # nothing in them yet can be picked and filled in.
        stored = self.store.months(view.folder)
        today = dt_util.now().date()
        first = min([*stored, (today.year, today.month), (day.year, day.month)])
        last = max([*stored, (today.year, today.month), (day.year, day.month)])
        months = []
        index = first[0] * 12 + first[1] - 1
        while index <= last[0] * 12 + last[1] - 1:
            months.append((index // 12, index % 12 + 1))
            index += 1
        return records, months[::-1]

    # Intake targets ------------------------------------------------------

    async def async_load_intakes(self) -> None:
        """Restore every person's intake targets."""
        saved = await self._intakes_store.async_load()
        if isinstance(saved, dict):
            self.intakes = saved

    def intakes_for(self, folder: str) -> dict[str, Any]:
        """A person's targets and the preset they came from, or the defaults."""
        default = {"preset": DEFAULT_INTAKE_PRESET, **DEFAULT_INTAKES}
        saved = self.intakes.get(folder) or {}
        return {key: saved.get(key, value) for key, value in default.items()}

    async def async_set_intakes(
        self, folder: str, values: dict[str, float], preset: str
    ) -> None:
        """Store a person's targets and show them on the page."""
        if folder not in self.persons:
            raise UnknownPerson(folder)
        self.intakes[folder] = {
            "preset": preset,
            **{field: values[field] for field in NUTRIENTS},
        }
        self._intakes_store.async_delay_save(lambda: self.intakes, 1)
        async_dispatcher_send(self.hass, f"{SIGNAL_VIEW_UPDATED}_{self.entry.entry_id}")

    # Reading -------------------------------------------------------------

    async def async_set_date(self, value: date) -> None:
        self.selected_date = value
        await self.async_refresh()


    async def async_refresh(self, _now: datetime | None = None) -> None:
        """Re-read the files and republish.

        Recording a person updates the config entry, which asks for a refresh of
        its own; the guard keeps that from re-entering this method.
        """
        if self._refreshing:
            return
        self._refreshing = True
        try:
            await self._async_refresh()
        finally:
            self._refreshing = False

    async def _async_refresh(self) -> None:
        folders = self.folders
        self.data = await self.hass.async_add_executor_job(
            self._read_all, folders, self.selected_date
        )
        self._announce(folders)
        async_dispatcher_send(self.hass, f"{SIGNAL_DATA_UPDATED}_{self.entry.entry_id}")
        await self._async_read_view()
        await self.async_update_statistics()

    async def async_update_statistics(self, since: dict[str, date] | None = None) -> None:
        """Rewrite daily totals, which is what the graphs draw, from a day to today.

        since maps a folder to the first day to rewrite. Without it, every
        person's today is rewritten. Nothing is written until Home Assistant has
        started: the recorder only works through its queue from then on.
        """
        if self.hass.state is not CoreState.running:
            return
        today = dt_util.now().date()
        if since is None:
            since = {folder: today for folder in self.folders}
        for folder, day in since.items():
            start = min(day, today)
            base = await stats.async_sums_before(self.hass, folder, start)
            series = await self.hass.async_add_executor_job(
                stats.read_series, self.store, folder, start, today, base
            )
            stats.write(self.hass, folder, self.person_name(folder), series)

    async def async_update_week(self, folder: str, start: date) -> None:
        """Rewrite a person's daily totals from a week to today, for the page.

        A week with no file for any of its days is left as it is.
        """
        if folder not in self.persons:
            raise UnknownPerson(folder)
        has_files = await self.hass.async_add_executor_job(
            stats.has_files, self.store, folder, start, start + timedelta(days=6)
        )
        if not has_files:
            return
        await self.async_update_statistics({folder: start})
        await stats.async_wait_written(self.hass)

    def _read_all(self, folders: list[str], selected: date) -> dict[str, dict[str, Any]]:
        today = dt_util.now().date()
        result: dict[str, dict[str, Any]] = {}
        for folder in folders:
            selected_records = self.store.read_month(folder, selected.year, selected.month)
            today_records = (
                selected_records
                if (today.year, today.month) == (selected.year, selected.month)
                else self.store.read_month(folder, today.year, today.month)
            )
            result[folder] = {
                "day": aggregate.day_summary(selected_records, selected),
                "today": aggregate.day_totals(today_records, today),
                "month": {
                    "year": selected.year,
                    "month": selected.month,
                    **aggregate.month_summary(selected_records),
                },
            }
        return result
