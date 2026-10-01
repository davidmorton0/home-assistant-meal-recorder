"""The Meal Recorder integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import panel_custom
from homeassistant.components.frontend import add_extra_js_url, async_remove_panel
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.start import async_at_started

from .api import MealItemsView
from .const import DOMAIN
from .coordinator import MealRecorderCoordinator
from .services import async_register_services, async_remove_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.DATE, Platform.SELECT, Platform.SENSOR]

CARD_URL = "/meal_recorder/meal-recorder-card.js"
PANEL_URL = "/meal_recorder/meal-recorder-panel.js"
PANEL_PATH = "meal-recorder"


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
        folder = Path(__file__).parent
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(CARD_URL, str(folder / "meal-recorder-card.js"), False),
                StaticPathConfig(PANEL_URL, str(folder / "meal-recorder-panel.js"), False),
            ]
        )
        # The item card, loaded on every page so any dashboard can use it too.
        if "frontend" in hass.config.components:
            add_extra_js_url(hass, CARD_URL)
        hass.data[f"{DOMAIN}_view_registered"] = True

    async_register_services(hass)

    # The Meals page in the sidebar.
    if "frontend" in hass.config.components:
        try:
            await panel_custom.async_register_panel(
                hass,
                frontend_url_path=PANEL_PATH,
                webcomponent_name="meal-recorder-panel",
                sidebar_title="Meal record",
                sidebar_icon="mdi:food-apple",
                module_url=PANEL_URL,
            )
        except ValueError:
            _LOGGER.warning(
                "The Meals page was not added, because something else is already at "
                "/%s. Delete that dashboard in Settings > Dashboards and restart",
                PANEL_PATH,
            )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Statistics are skipped while Home Assistant starts, so write today's once started.
    async def _write_statistics(_hass: HomeAssistant) -> None:
        await coordinator.async_update_statistics()

    entry.async_on_unload(async_at_started(hass, _write_statistics))

    # The daily totals always describe today, so they roll over at midnight.
    entry.async_on_unload(
        async_track_time_change(hass, coordinator.async_refresh, hour=0, minute=0, second=10)
    )
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        async_remove_services(hass)
        async_remove_panel(hass, PANEL_PATH, warn_if_unknown=False)
    return unloaded


async def _async_entry_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Re-read after the options changed."""
    coordinator: MealRecorderCoordinator | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is not None:
        await coordinator.async_refresh()
