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


class MonthSelect(ViewEntity, SelectEntity):
    """The month shown, as YYYY-MM: every month from the first stored one to now."""

    @property
    def options(self) -> list[str]:
        return [f"{year:04d}-{month:02d}" for year, month in self.coordinator.view_months]

    @property
    def current_option(self) -> str:
        return self.coordinator.view.day.strftime("%Y-%m")

    async def async_select_option(self, option: str) -> None:
        year, _, month = option.partition("-")
        await self.coordinator.async_set_view_month(int(year), int(month))


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
