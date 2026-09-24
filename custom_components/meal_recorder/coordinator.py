"""Reads the CSV files and keeps the published data up to date."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from . import aggregate
from .const import (
    CONF_PERSONS,
    SIGNAL_DATA_UPDATED,
    SIGNAL_PERSON_ADDED,
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


class PersonCollision(Exception):
    """Two person names normalise onto the same folder."""

    def __init__(self, person: str, existing: str, folder: str) -> None:
        super().__init__(f"{person!r} collides with {existing!r} in folder {folder!r}")
        self.person = person
        self.existing = existing
        self.folder = folder


class MealRecorderCoordinator:
    """Owns the store, the selected date and the data published as entities."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.store = CsvStore(hass.config.path(STORAGE_DIR))
        self.selected_date: date = dt_util.now().date()
        self.data: dict[str, dict[str, Any]] = {}
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
        """Append items to their files. Raises UnknownPerson before writing."""
        for item in items:
            item["folder"] = self.folder_for(item["person"])

        async with self._write_lock:
            await self.hass.async_add_executor_job(self.store.append_items, items)
        await self.async_refresh()
        return [item["id"] for item in items]

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
