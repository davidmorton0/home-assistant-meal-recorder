"""The Meal Recorder integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_time_change

from .api import MealItemsView
from .const import DOMAIN, SIGNAL_PERSON_ADDED
from .coordinator import MealRecorderCoordinator
from .dashboard import async_add_person_view, async_setup_dashboard

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.DATE, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Meal Recorder from a config entry."""
    coordinator = MealRecorderCoordinator(hass, entry)
    await hass.async_add_executor_job(
        lambda: coordinator.store.base_dir.mkdir(parents=True, exist_ok=True)
    )
    await coordinator.async_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    if not hass.data.get(f"{DOMAIN}_view_registered"):
        hass.http.register_view(MealItemsView(hass))
        hass.data[f"{DOMAIN}_view_registered"] = True

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # The daily totals always describe today, so they roll over at midnight.
    entry.async_on_unload(
        async_track_time_change(hass, coordinator.async_refresh, hour=0, minute=0, second=10)
    )
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))

    await async_setup_dashboard(hass, entry, coordinator)

    async def _person_added(folder: str) -> None:
        """Give a person added later their own view."""
        await async_add_person_view(hass, entry, coordinator, folder)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, f"{SIGNAL_PERSON_ADDED}_{entry.entry_id}", _person_added
        )
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def _async_entry_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Re-read after the options changed."""
    coordinator: MealRecorderCoordinator | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is not None:
        await coordinator.async_refresh()
