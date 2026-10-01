"""The dashboard's buttons: back and forward by a day or a month, and back to today."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import MealRecorderCoordinator
from .entity import ViewEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the buttons."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            ShiftButton(coordinator, "previous_month", "Meals previous month", "mdi:chevron-double-left", months=-1),
            ShiftButton(coordinator, "previous_week", "Meals previous week", "mdi:calendar-arrow-left", days=-7),
            ShiftButton(coordinator, "previous_day", "Meals previous day", "mdi:chevron-left", days=-1),
            ShiftButton(coordinator, "next_day", "Meals next day", "mdi:chevron-right", days=1),
            ShiftButton(coordinator, "next_week", "Meals next week", "mdi:calendar-arrow-right", days=7),
            ShiftButton(coordinator, "next_month", "Meals next month", "mdi:chevron-double-right", months=1),
            TodayButton(coordinator, "today", "Meals today", "mdi:calendar-today"),
        ]
    )


class ShiftButton(ViewEntity, ButtonEntity):
    """Moves the day shown."""

    def __init__(
        self,
        coordinator: MealRecorderCoordinator,
        key: str,
        name: str,
        icon: str,
        days: int = 0,
        months: int = 0,
    ) -> None:
        super().__init__(coordinator, key, name, icon)
        self._days = days
        self._months = months

    async def async_press(self) -> None:
        await self.coordinator.async_shift_view(days=self._days, months=self._months)


class TodayButton(ViewEntity, ButtonEntity):
    """Moves the day shown to today."""

    async def async_press(self) -> None:
        await self.coordinator.async_set_view(day=dt_util.now().date())
