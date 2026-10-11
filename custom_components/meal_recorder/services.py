"""The add, update and delete services the dashboard card calls, and the page's targets."""

from __future__ import annotations

import uuid
from typing import Any

import voluptuous as vol
from homeassistant.helpers import config_validation as cv
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .const import DOMAIN, MAX_INTAKE, MAX_PRESET_LEN, NUTRIENTS
from .coordinator import DuplicateId, ItemNotFound, MealRecorderCoordinator, UnknownPerson
from .items import validate_batch

SERVICE_ADD = "add_item"
SERVICE_UPDATE = "update_item"
SERVICE_DELETE = "delete_item"
SERVICE_UPDATE_WEEK = "update_week_statistics"
SERVICE_SET_INTAKES = "set_intakes"

_FIELDS = {
    vol.Required("created_at"): str,
    vol.Required("name"): str,
    vol.Required("meal"): str,
    vol.Optional("portion", default=""): str,
    **{vol.Required(field): vol.Coerce(float) for field in ["mass", *NUTRIENTS]},
}
ADD_SCHEMA = vol.Schema({vol.Required("person"): str, **_FIELDS})
UPDATE_SCHEMA = vol.Schema({vol.Required("id"): str, **_FIELDS})
DELETE_SCHEMA = vol.Schema({vol.Required("id"): str})
UPDATE_WEEK_SCHEMA = vol.Schema({vol.Required("folder"): str, vol.Required("start"): cv.date})
SET_INTAKES_SCHEMA = vol.Schema(
    {
        vol.Required("person"): str,
        vol.Optional("preset", default="custom"): vol.All(
            str, vol.Length(min=1, max=MAX_PRESET_LEN)
        ),
        **{
            vol.Required(field): vol.All(
                vol.Coerce(float), vol.Range(min=0, max=MAX_INTAKE, min_included=False)
            )
            for field in NUTRIENTS
        },
    }
)


def async_register_services(hass: HomeAssistant) -> None:
    """Register the services, once for the integration."""
    if hass.services.has_service(DOMAIN, SERVICE_ADD):
        return
    hass.services.async_register(DOMAIN, SERVICE_ADD, _add, schema=ADD_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_UPDATE, _update, schema=UPDATE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DELETE, _delete, schema=DELETE_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_UPDATE_WEEK, _update_week, schema=UPDATE_WEEK_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_INTAKES, _set_intakes, schema=SET_INTAKES_SCHEMA
    )


def async_remove_services(hass: HomeAssistant) -> None:
    for service in (
        SERVICE_ADD, SERVICE_UPDATE, SERVICE_DELETE, SERVICE_UPDATE_WEEK, SERVICE_SET_INTAKES
    ):
        hass.services.async_remove(DOMAIN, service)


def _coordinator(call: ServiceCall) -> MealRecorderCoordinator:
    coordinator = next(iter(call.hass.data.get(DOMAIN, {}).values()), None)
    if coordinator is None:
        raise ServiceValidationError("Meal Recorder is not loaded")
    return coordinator


def _validated(raw: dict[str, Any]) -> dict[str, Any]:
    """Check an item with the same rules as the endpoint."""
    items, errors = validate_batch(
        [raw],
        dt_util.get_default_time_zone(),
        dt_util.now(),
    )
    if errors:
        raise ServiceValidationError(
            "; ".join(f"{error['field']} {error['message']}" for error in errors)
        )
    return items[0]


async def _add(call: ServiceCall) -> None:
    """Add an item."""
    coordinator = _coordinator(call)
    item = _validated({**call.data, "id": str(uuid.uuid4())})
    try:
        await coordinator.async_add_items([item])
    except (UnknownPerson, DuplicateId) as err:
        raise ServiceValidationError(str(err)) from err


async def _update(call: ServiceCall) -> None:
    """Replace an item's details. It keeps its id and its person."""
    coordinator = _coordinator(call)
    try:
        folder, _ = await coordinator.async_find_item(call.data["id"])
        item = _validated({**call.data, "person": coordinator.person_name(folder)})
        await coordinator.async_update_item(folder, item)
    except ItemNotFound as err:
        raise ServiceValidationError(str(err)) from err


async def _delete(call: ServiceCall) -> None:
    """Delete an item."""
    coordinator = _coordinator(call)
    try:
        folder, _ = await coordinator.async_find_item(call.data["id"])
        await coordinator.async_delete_item(folder, call.data["id"])
    except ItemNotFound as err:
        raise ServiceValidationError(str(err)) from err


async def _update_week(call: ServiceCall) -> None:
    """Rewrite a person's daily totals from a week on, before the page draws it."""
    coordinator = _coordinator(call)
    try:
        await coordinator.async_update_week(call.data["folder"], call.data["start"])
    except UnknownPerson as err:
        raise ServiceValidationError(str(err)) from err


async def _set_intakes(call: ServiceCall) -> None:
    """Store a person's daily intake targets."""
    coordinator = _coordinator(call)
    try:
        folder = coordinator.folder_for(call.data["person"])
        await coordinator.async_set_intakes(folder, call.data, call.data["preset"])
    except UnknownPerson as err:
        raise ServiceValidationError(str(err)) from err
