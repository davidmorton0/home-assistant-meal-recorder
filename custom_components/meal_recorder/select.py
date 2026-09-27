"""The dashboard's pickers: person, month and day."""

from __future__ import annotations

import calendar
from datetime import date

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import ViewEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the pickers."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            PersonSelect(coordinator, "person", "Meals person", "mdi:account"),
            YearSelect(coordinator, "year", "Meals year", "mdi:calendar-blank"),
            MonthSelect(coordinator, "month", "Meals month", "mdi:calendar-month"),
            DaySelect(coordinator, "day", "Meals day", "mdi:calendar-today"),
        ]
    )


class PersonSelect(ViewEntity, SelectEntity):
    """Whose items are shown."""

    @property
    def options(self) -> list[str]:
        return [self.coordinator.person_name(folder) for folder in self.coordinator.folders]

    @property
    def current_option(self) -> str:
        return self.coordinator.person_name(self.coordinator.view.folder)

    async def async_select_option(self, option: str) -> None:
        folder = next(
            (f for f in self.coordinator.folders if self.coordinator.person_name(f) == option),
            None,
        )
        if folder is None:
            raise ServiceValidationError(f"{option} has not been added")
        await self.coordinator.async_set_view(folder=folder)


class YearSelect(ViewEntity, SelectEntity):
    """The year shown: every year from the first stored month to now."""

    @property
    def options(self) -> list[str]:
        years = {year for year, _ in self.coordinator.view_months}
        return [str(year) for year in sorted(years, reverse=True)]

    @property
    def current_option(self) -> str:
        return str(self.coordinator.view.day.year)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_view_month(
            int(option), self.coordinator.view.day.month
        )


class MonthSelect(ViewEntity, SelectEntity):
    """The month shown, by name, out of the months that year holds."""

    @property
    def options(self) -> list[str]:
        year = self.coordinator.view.day.year
        return [
            calendar.month_name[month]
            for stored_year, month in sorted(self.coordinator.view_months)
            if stored_year == year
        ]

    @property
    def current_option(self) -> str:
        return calendar.month_name[self.coordinator.view.day.month]

    async def async_select_option(self, option: str) -> None:
        names = list(calendar.month_name)
        if option not in names:
            raise ServiceValidationError(f"{option} is not a month")
        await self.coordinator.async_set_view_month(
            self.coordinator.view.day.year, names.index(option)
        )


class DaySelect(ViewEntity, SelectEntity):
    """The day of the month shown."""

    @property
    def options(self) -> list[str]:
        day = self.coordinator.view.day
        return [str(d) for d in range(1, calendar.monthrange(day.year, day.month)[1] + 1)]

    @property
    def current_option(self) -> str:
        return str(self.coordinator.view.day.day)

    async def async_select_option(self, option: str) -> None:
        day = self.coordinator.view.day
        await self.coordinator.async_set_view(day=date(day.year, day.month, int(option)))
