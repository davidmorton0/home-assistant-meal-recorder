"""The default dashboard: standard cards over the published entities.

Written once, when the integration is set up. It is never rewritten, so the
user's changes to it survive an update of the integration.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .coordinator import MealRecorderCoordinator

_LOGGER = logging.getLogger(__name__)

DASHBOARD_URL_PATH = "meal-recorder"
DASHBOARD_CREATED = "dashboard_created"


async def async_setup_dashboard(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: MealRecorderCoordinator
) -> None:
    """Create the dashboard once, or write it to a file if that is not possible."""
    if entry.data.get(DASHBOARD_CREATED):
        return

    config = build_dashboard(coordinator)
    created = False
    try:
        created = await _async_create_dashboard(hass, config)
    except Exception:  # noqa: BLE001 - the Lovelace storage API is not stable
        _LOGGER.exception("Could not create the Meals dashboard")

    if not created:
        path = coordinator.store.base_dir / "dashboard.json"
        await hass.async_add_executor_job(
            path.write_text, json.dumps(config, indent=2), "utf-8"
        )
        _LOGGER.warning(
            "The Meals dashboard was not created, because a dashboard already "
            "exists at /%s or Lovelace could not be written to. Its configuration "
            "is in %s: create a dashboard in Settings > Dashboards and paste it in "
            "through the raw configuration editor",
            DASHBOARD_URL_PATH,
            path,
        )

    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            DASHBOARD_CREATED: True,
        },
    )


def _lovelace(hass: HomeAssistant) -> tuple[Any, Any]:
    """The dashboards collection and the dashboards, across Home Assistant versions."""
    lovelace = hass.data["lovelace"]
    collection = getattr(lovelace, "dashboards_collection", None)
    dashboards = getattr(lovelace, "dashboards", None)
    if collection is None or dashboards is None:  # older Home Assistant layout
        collection = lovelace["dashboards_collection"]
        dashboards = lovelace["dashboards"]
    return collection, dashboards


def _dashboard_store(hass: HomeAssistant) -> Any:
    """The store of our own dashboard, or None if it is not there."""
    collection, dashboards = _lovelace(hass)
    item = next(
        (i for i in collection.async_items() if i.get("url_path") == DASHBOARD_URL_PATH),
        None,
    )
    if item is None:
        return None
    return dashboards.get(DASHBOARD_URL_PATH) or dashboards.get(item["id"])


async def _async_create_dashboard(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Add the dashboard, unless one is already there.

    An existing dashboard at this path is left untouched, whoever made it.
    """
    collection, dashboards = _lovelace(hass)

    if any(item.get("url_path") == DASHBOARD_URL_PATH for item in collection.async_items()):
        _LOGGER.warning(
            "A dashboard already exists at /%s, so it was left as it is",
            DASHBOARD_URL_PATH,
        )
        return False

    created = await collection.async_create_item(
        {
            "url_path": DASHBOARD_URL_PATH,
            "title": "Meals",
            "icon": "mdi:food-apple",
            "show_in_sidebar": True,
            "require_admin": False,
        }
    )

    # Keyed by url path in current Home Assistant, by id in older versions.
    store = dashboards.get(DASHBOARD_URL_PATH) or dashboards[created["id"]]
    await store.async_save(config)
    return True


def build_dashboard(coordinator: MealRecorderCoordinator) -> dict[str, Any]:
    """Build the dashboard config: the pickers, the day and month buttons, the items."""
    return {
        "views": [
            {
                "title": "Meals",
                "path": "meals",
                "cards": [
                    {
                        "type": "entities",
                        "entities": ["select.meals_person", "select.meals_month", "select.meals_day"],
                    },
                    {
                        "type": "horizontal-stack",
                        "cards": [
                            _press("button.meals_previous_month", "Month", "mdi:chevron-double-left"),
                            _press("button.meals_previous_day", "Day", "mdi:chevron-left"),
                            _press("button.meals_next_day", "Day", "mdi:chevron-right"),
                            _press("button.meals_next_month", "Month", "mdi:chevron-double-right"),
                        ],
                    },
                    {"type": "custom:meal-recorder-card", "entity": "sensor.meals_day"},
                ],
            }
        ]
    }


def _press(entity: str, name: str, icon: str) -> dict[str, Any]:
    """A button card that presses a button entity."""
    return {
        "type": "button",
        "entity": entity,
        "name": name,
        "icon": icon,
        "show_state": False,
        "tap_action": {
            "action": "perform-action",
            "perform_action": "button.press",
            "target": {"entity_id": entity},
        },
    }
