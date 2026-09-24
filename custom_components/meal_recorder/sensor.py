"""The entities published for each person."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, NUTRIENTS, SIGNAL_DATA_UPDATED, SIGNAL_PERSON_ADDED
from .coordinator import MealRecorderCoordinator

UNITS = {"kcal": "kcal", "protein": "g", "carbs": "g", "fat": "g", "mass": "g"}
LABELS = {"kcal": "kcal", "protein": "protein", "carbs": "carbs", "fat": "fat"}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the entities for every person, and for people added later."""
    coordinator: MealRecorderCoordinator = hass.data[DOMAIN][entry.entry_id]
    known: set[str] = set()

    @callback
    def _add(folder: str) -> None:
        if folder in known:
            return
        known.add(folder)
        entities: list[SensorEntity] = [
            MealDaySensor(coordinator, folder),
            MealMonthSensor(coordinator, folder),
        ]
        entities.extend(MealTodaySensor(coordinator, folder, field) for field in NUTRIENTS)
        async_add_entities(entities)

    for folder in coordinator.folders:
        _add(folder)
        coordinator.mark_announced(folder)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, f"{SIGNAL_PERSON_ADDED}_{entry.entry_id}", _add
        )
    )


class MealSensorBase(SensorEntity):
    """Shared wiring: device per person, refreshed by the coordinator."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: MealRecorderCoordinator, folder: str) -> None:
        self.coordinator = coordinator
        self.folder = folder

    @property
    def person(self) -> str:
        return self.coordinator.person_name(self.folder)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.coordinator.entry.entry_id}_{self.folder}")},
            name=f"Meals: {self.person}",
            manufacturer="Meal Recorder",
            entry_type=None,
        )

    @property
    def _data(self) -> dict[str, Any]:
        return self.coordinator.data.get(self.folder, {})

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_DATA_UPDATED}_{self.coordinator.entry.entry_id}",
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class MealDaySensor(MealSensorBase):
    """The selected day: kcal as the state, the items in the attributes."""

    _attr_name = "Day"
    _attr_icon = "mdi:silverware-fork-knife"
    _attr_native_unit_of_measurement = "kcal"
    # Follows the date control, so it is never recorded as history.
    _unrecorded_attributes = frozenset({MATCH_ALL})

    def __init__(self, coordinator: MealRecorderCoordinator, folder: str) -> None:
        super().__init__(coordinator, folder)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{folder}_day"

    @property
    def native_value(self) -> float | None:
        day = self._data.get("day")
        return None if day is None else day["totals"]["kcal"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        day = self._data.get("day", {})
        return {
            "person": self.person,
            "date": day.get("date"),
            "item_count": day.get("item_count", 0),
            "meals": day.get("meals", {}),
            "totals": day.get("totals", {}),
        }


class MealMonthSensor(MealSensorBase):
    """The selected month: kcal as the state, totals and averages in attributes."""

    _attr_name = "Month"
    _attr_icon = "mdi:calendar-month"
    _attr_native_unit_of_measurement = "kcal"
    _unrecorded_attributes = frozenset({MATCH_ALL})

    def __init__(self, coordinator: MealRecorderCoordinator, folder: str) -> None:
        super().__init__(coordinator, folder)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{folder}_month"

    @property
    def native_value(self) -> float | None:
        month = self._data.get("month")
        return None if month is None else month["totals"]["kcal"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        month = self._data.get("month", {})
        return {
            "person": self.person,
            "year": month.get("year"),
            "month": month.get("month"),
            "days_logged": month.get("days_logged", 0),
            "totals": month.get("totals", {}),
            "averages": month.get("averages", {}),
            "days": month.get("days", {}),
        }


class MealTodaySensor(MealSensorBase):
    """One of today's totals. Always today, so the recorded history stays true."""

    _attr_state_class = SensorStateClass.TOTAL

    def __init__(
        self, coordinator: MealRecorderCoordinator, folder: str, field: str
    ) -> None:
        super().__init__(coordinator, folder)
        self.field = field
        self._attr_name = f"Today {LABELS[field]}"
        self._attr_native_unit_of_measurement = UNITS[field]
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{folder}_today_{field}"

    @property
    def native_value(self) -> float | None:
        today = self._data.get("today")
        return None if today is None else today[self.field]

    @property
    def last_reset(self) -> datetime:
        """Today's totals start again at local midnight."""
        return dt_util.start_of_local_day()
