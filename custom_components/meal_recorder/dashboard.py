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

from .const import CONF_DASHBOARD_VIEWS, NUTRIENTS
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
            CONF_DASHBOARD_VIEWS: sorted(coordinator.persons) if created else [],
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
    """Build the dashboard config: one view per person."""
    return {
        "views": [
            build_view(folder, person)
            for folder, person in sorted(coordinator.persons.items())
        ]
    }


def build_view(folder: str, person: str) -> dict[str, Any]:
    """One person's view: the day, their meals, the chart and the month."""
    return {"title": person, "path": folder or "person", "cards": _cards(folder, person)}


async def async_add_person_view(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: MealRecorderCoordinator, folder: str
) -> None:
    """Append a view for a person added after the dashboard was created.

    Views already made are never remade, so one deleted on purpose stays gone,
    and nothing already on the dashboard is rewritten.
    """
    made: list[str] = list(entry.data.get(CONF_DASHBOARD_VIEWS, []))
    if folder in made or not entry.data.get(DASHBOARD_CREATED):
        return

    view = build_view(folder, coordinator.person_name(folder))
    try:
        store = _dashboard_store(hass)
        if store is None:
            return
        config = await store.async_load(False) or {"views": []}
        config.setdefault("views", []).append(view)
        await store.async_save(config)
    except Exception:  # noqa: BLE001 - the Lovelace storage API is not stable
        _LOGGER.exception("Could not add the %s view to the Meals dashboard", folder)
        return

    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_DASHBOARD_VIEWS: [*made, folder]}
    )


def _cards(folder: str, person: str) -> list[dict[str, Any]]:
    day = f"sensor.meals_{folder}_day"
    month = f"sensor.meals_{folder}_month"
    totals = [f"sensor.meals_{folder}_today_{field}" for field in NUTRIENTS]

    return [
        {
            "type": "entities",
            "title": f"{person} — day",
            "entities": ["date.meals_day_shown", {"entity": day, "name": "Day total"}],
        },
        {"type": "markdown", "content": _day_markdown(day)},
        {
            "type": "statistics-graph",
            "title": "Daily totals",
            "entities": totals,
            "days_to_show": 30,
            "period": "day",
            "stat_types": ["sum"],
            "chart_type": "bar",
        },
        {"type": "markdown", "content": _month_markdown(month)},
    ]


def _day_markdown(day_entity: str) -> str:
    return (
        "{% set meals = state_attr('" + day_entity + "', 'meals') or {} %}\n"
        "{% set totals = state_attr('" + day_entity + "', 'totals') or {} %}\n"
        "{% for meal in ['breakfast', 'lunch', 'dinner', 'snack'] %}"
        "{% set entry = meals.get(meal, {}) %}"
        "{% set meal_totals = entry.get('totals', {}) %}\n"
        "### {{ meal | capitalize }} — {{ meal_totals.get('kcal', 0) }} kcal\n"
        "{% if entry.get('items') %}"
        "| Time | Item | Portion | Mass | kcal | P | C | F |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "{% for item in entry['items'] %}"
        "| {{ item.time }} | {{ item.name }} | {{ item.portion }} | {{ item.mass }} g | "
        "{{ item.kcal }} | {{ item.protein }} | {{ item.carbs }} | {{ item.fat }} |\n"
        "{% endfor %}"
        "{% else %}_Nothing recorded._\n{% endif %}\n"
        "{% endfor %}\n"
        "---\n"
        "**Day total: {{ totals.get('kcal', 0) }} kcal** · "
        "protein {{ totals.get('protein', 0) }} g · "
        "carbs {{ totals.get('carbs', 0) }} g · "
        "fat {{ totals.get('fat', 0) }} g\n"
    )


def _month_markdown(month_entity: str) -> str:
    return (
        "{% set totals = state_attr('" + month_entity + "', 'totals') or {} %}\n"
        "{% set averages = state_attr('" + month_entity + "', 'averages') or {} %}\n"
        "### Month\n"
        "Days logged: {{ state_attr('" + month_entity + "', 'days_logged') or 0 }}\n\n"
        "Total {{ totals.get('kcal', 0) }} kcal · "
        "Average per logged day {{ averages.get('kcal', 0) }} kcal · "
        "protein {{ averages.get('protein', 0) }} g · "
        "carbs {{ averages.get('carbs', 0) }} g · "
        "fat {{ averages.get('fat', 0) }} g\n"
    )
