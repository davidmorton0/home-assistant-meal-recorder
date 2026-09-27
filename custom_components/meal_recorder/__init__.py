"""The Meal Recorder integration."""

from __future__ import annotations

import logging

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_change

from .api import MealItemsView
from .const import DOMAIN
from .coordinator import MealRecorderCoordinator
from .dashboard import async_setup_dashboard
from .services import async_register_services, async_remove_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.DATE, Platform.SELECT, Platform.SENSOR]

CARD_URL = "/meal_recorder/meal-recorder-card.js"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Meal Recorder from a config entry."""
    coordinator = MealRecorderCoordinator(hass, entry)
    await hass.async_add_executor_job(
        lambda: coordinator.store.base_dir.mkdir(parents=True, exist_ok=True)
    )
    await coordinator.async_load_view()
    await coordinator.async_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    if not hass.data.get(f"{DOMAIN}_view_registered"):
        hass.http.register_view(MealItemsView(hass))
        # The dashboard card, loaded on every page so any dashboard can use it.
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(Path(__file__).parent / "meal-recorder-card.js"), False)]
        )
        if "frontend" in hass.config.components:
            add_extra_js_url(hass, CARD_URL)
        hass.data[f"{DOMAIN}_view_registered"] = True

    async_register_services(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # The daily totals always describe today, so they roll over at midnight.
    entry.async_on_unload(
        async_track_time_change(hass, coordinator.async_refresh, hour=0, minute=0, second=10)
    )
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))

    await async_setup_dashboard(hass, entry, coordinator)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        async_remove_services(hass)
    return unloaded


async def _async_entry_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Re-read after the options changed."""
    coordinator: MealRecorderCoordinator | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is not None:
        await coordinator.async_refresh()
