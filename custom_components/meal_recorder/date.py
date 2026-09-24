"""The date control that picks the day the Day entity describes."""

from __future__ import annotations

from datetime import date

from homeassistant.components.date import DateEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import MealRecorderCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the shared date control."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MealRecorderDate(coordinator)])


class MealRecorderDate(DateEntity):
    """One control, shared by everyone, for the day being viewed."""

    _attr_has_entity_name = False
    _attr_name = "Meals day shown"
    _attr_icon = "mdi:calendar"
    _attr_should_poll = False

    def __init__(self, coordinator: MealRecorderCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_selected_date"

    @property
    def native_value(self) -> date:
        return self.coordinator.selected_date

    async def async_set_value(self, value: date) -> None:
        await self.coordinator.async_set_date(value)
        self.async_write_ha_state()
