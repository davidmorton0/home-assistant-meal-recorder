"""Shared wiring for the dashboard's view entities."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import SIGNAL_VIEW_UPDATED
from .coordinator import MealRecorderCoordinator


class ViewEntity(Entity):
    """An entity that follows the person, month and day the dashboard shows."""

    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(
        self, coordinator: MealRecorderCoordinator, key: str, name: str, icon: str
    ) -> None:
        self.coordinator = coordinator
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"{coordinator.entry.entry_id}_view_{key}"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_VIEW_UPDATED}_{self.coordinator.entry.entry_id}",
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
