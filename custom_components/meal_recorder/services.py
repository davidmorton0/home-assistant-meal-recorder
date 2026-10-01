"""The add, update and delete services the dashboard card calls."""

from __future__ import annotations

import uuid
from typing import Any

import voluptuous as vol
from homeassistant.helpers import config_validation as cv
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .const import DOMAIN, NUTRIENTS
from .coordinator import DuplicateId, ItemNotFound, MealRecorderCoordinator, UnknownPerson
from .items import validate_batch

SERVICE_ADD = "add_item"
SERVICE_UPDATE = "update_item"
SERVICE_DELETE = "delete_item"
SERVICE_UPDATE_WEEK = "update_week_statistics"

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


def async_remove_services(hass: HomeAssistant) -> None:
    for service in (SERVICE_ADD, SERVICE_UPDATE, SERVICE_DELETE, SERVICE_UPDATE_WEEK):
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
    """Replace an item's details. It keeps its id, person and received time."""
    coordinator = _coordinator(call)
    try:
        folder, record = await coordinator.async_find_item(call.data["id"])
        item = _validated({**call.data, "person": coordinator.person_name(folder)})
        item["received_at"] = record["received_at"]
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
