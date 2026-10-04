"""The REST endpoint: a collection of items and the items in it.

    GET    /api/meal_recorder/items            list items
    POST   /api/meal_recorder/items            store one item or a batch
    GET    /api/meal_recorder/items/{id}       read one item
    PUT    /api/meal_recorder/items/{id}       replace one item
    DELETE /api/meal_recorder/items/{id}       remove one item

Every method takes the same HTTP Basic credentials.
"""

from __future__ import annotations

import base64
import binascii
import calendar
import json
import logging
from datetime import date
from functools import wraps
from http import HTTPStatus
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.ban import process_success_login, process_wrong_login
from homeassistant.util import dt as dt_util

from .auth import verify_password, verify_username
from .const import (
    CONF_PASSWORD_HASH,
    CONF_USERNAME,
    DOMAIN,
    MAX_BODY_BYTES,
    NUTRIENTS,
)
from .coordinator import (
    DuplicateId,
    ItemNotFound,
    MealRecorderCoordinator,
    UnknownPerson,
)
from .items import TooManyItems, normalise_person, validate_batch

_LOGGER = logging.getLogger(__name__)

_REALM = 'Basic realm="Meal Recorder", charset="UTF-8"'

BASE_URL = "/api/meal_recorder/items"


def authenticated(handler):
    """Refuse the request unless the integration is loaded and the credentials match."""

    @wraps(handler)
    async def wrapper(self, request: web.Request, **kwargs) -> web.Response:
        coordinator = self.coordinator
        if coordinator is None:
            return self._error(HTTPStatus.SERVICE_UNAVAILABLE, "not_configured")
        if not await self._authenticate(request, coordinator):
            await process_wrong_login(request)
            return self._error(
                HTTPStatus.UNAUTHORIZED,
                "unauthorized",
                headers={"WWW-Authenticate": _REALM},
            )
        process_success_login(request)
        return await handler(self, request, coordinator, **kwargs)

    return wrapper


class MealRecorderView(HomeAssistantView):
    """Shared auth, body reading and error replies."""

    requires_auth = False

    def __init__(self, hass) -> None:
        self.hass = hass

    @property
    def coordinator(self) -> MealRecorderCoordinator | None:
        """The coordinator of the configured entry, if the entry is loaded."""
        entries = self.hass.data.get(DOMAIN, {})
        return next(iter(entries.values()), None)

    async def _authenticate(self, request: web.Request, coordinator) -> bool:
        header = request.headers.get("Authorization", "")
        scheme, _, encoded = header.partition(" ")
        if scheme.lower() != "basic" or not encoded:
            return False
        try:
            decoded = base64.b64decode(encoded, validate=True).decode()
        except (binascii.Error, UnicodeDecodeError):
            return False
        username, separator, password = decoded.partition(":")
        if not separator:
            return False

        entry_data = coordinator.entry.data
        name_ok = verify_username(username, entry_data[CONF_USERNAME])
        password_ok = await self.hass.async_add_executor_job(
            verify_password, password, entry_data[CONF_PASSWORD_HASH]
        )
        return name_ok and password_ok

    async def _read_json(self, request: web.Request) -> Any:
        """The request body, parsed. Raises _Refused for a body that cannot be used."""
        if request.content_length and request.content_length > MAX_BODY_BYTES:
            raise _Refused(self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "too_large"))

        body = await request.content.read(MAX_BODY_BYTES + 1)
        if len(body) > MAX_BODY_BYTES:
            raise _Refused(self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "too_large"))

        try:
            return json.loads(body)
        except ValueError as err:
            raise _Refused(self._error(HTTPStatus.BAD_REQUEST, "invalid_json")) from err

    def _validate(self, payload: Any) -> list[dict[str, Any]]:
        """Validated items. Raises _Refused if any of them is wrong."""
        try:
            items, errors = validate_batch(
                payload,
                dt_util.DEFAULT_TIME_ZONE,
                dt_util.now(),
            )
        except TooManyItems as err:
            raise _Refused(
                self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "too_many_items")
            ) from err
        if errors:
            raise _Refused(
                self.json({"error": "validation", "details": errors}, HTTPStatus.BAD_REQUEST)
            )
        return items

    def _error(self, status: HTTPStatus, error: str, headers: dict | None = None) -> web.Response:
        return self.json({"error": error}, status, headers=headers)


class _Refused(Exception):
    """Holds the reply to send back instead of carrying on."""

    def __init__(self, response: web.Response) -> None:
        super().__init__("refused")
        self.response = response


class MealItemsView(MealRecorderView):
    """The collection: list the stored items, or store new ones."""

    url = BASE_URL
    name = "api:meal_recorder:items"

    @authenticated
    async def get(self, request: web.Request, coordinator) -> web.Response:
        """List one person's items for a day or a month."""
        try:
            folders = _folders(request, coordinator)
            start, end = _days(request)
        except _Refused as refused:
            return refused.response

        records = await coordinator.async_list_items(folders, start, end)
        items = [_item_json(coordinator, record["folder"], record) for record in records]
        return self.json(
            {
                "items": items,
                "count": len(items),
                "from": start.isoformat(),
                "to": end.isoformat(),
            }
        )

    @authenticated
    async def post(self, request: web.Request, coordinator) -> web.Response:
        """Store one item or a batch. All or nothing: one bad item stores none."""
        try:
            items = self._validate(await self._read_json(request))
        except _Refused as refused:
            return refused.response

        try:
            ids = await coordinator.async_add_items(items)
        except UnknownPerson as err:
            return self.json(
                {"error": "unknown_person", "person": err.person},
                HTTPStatus.CONFLICT,
            )
        except DuplicateId as err:
            return self.json(
                {"error": "duplicate_id", "ids": err.ids},
                HTTPStatus.CONFLICT,
            )
        except OSError:
            _LOGGER.exception("Storing items failed")
            return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "storage")

        headers = {"Location": f"{BASE_URL}/{ids[0]}"} if len(ids) == 1 else None
        return self.json(
            {"stored": len(ids), "ids": ids}, HTTPStatus.CREATED, headers=headers
        )


class MealItemView(MealRecorderView):
    """One stored item, addressed by its id."""

    url = f"{BASE_URL}/{{item_id}}"
    name = "api:meal_recorder:item"

    @authenticated
    async def get(self, request: web.Request, coordinator, item_id: str) -> web.Response:
        """Read one item."""
        try:
            folder, record = await coordinator.async_find_item(item_id)
        except ItemNotFound:
            return self._not_found(item_id)
        return self.json(_item_json(coordinator, folder, record))

    @authenticated
    async def put(self, request: web.Request, coordinator, item_id: str) -> web.Response:
        """Replace an item's details. It keeps its id and its person."""
        try:
            payload = await self._read_json(request)
        except _Refused as refused:
            return refused.response
        if not isinstance(payload, dict):
            return self._error(HTTPStatus.BAD_REQUEST, "expected_an_item")

        try:
            folder, _ = await coordinator.async_find_item(item_id)
        except ItemNotFound:
            return self._not_found(item_id)

        person = coordinator.person_name(folder)
        if payload.get("id") not in (None, item_id):
            return self._error(HTTPStatus.BAD_REQUEST, "id_mismatch")
        if payload.get("person") not in (None, person):
            return self._error(HTTPStatus.BAD_REQUEST, "person_mismatch")

        try:
            [item] = self._validate([{**payload, "id": item_id, "person": person}])
        except _Refused as refused:
            return refused.response

        try:
            await coordinator.async_update_item(folder, item)
        except ItemNotFound:
            return self._not_found(item_id)
        except OSError:
            _LOGGER.exception("Updating an item failed")
            return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "storage")

        return self.json(_item_json(coordinator, folder, item))

    @authenticated
    async def delete(self, request: web.Request, coordinator, item_id: str) -> web.Response:
        """Remove an item."""
        try:
            folder, _ = await coordinator.async_find_item(item_id)
            await coordinator.async_delete_item(folder, item_id)
        except ItemNotFound:
            return self._not_found(item_id)
        except OSError:
            _LOGGER.exception("Deleting an item failed")
            return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "storage")
        return web.Response(status=HTTPStatus.NO_CONTENT)

    def _not_found(self, item_id: str) -> web.Response:
        return self.json({"error": "not_found", "id": item_id}, HTTPStatus.NOT_FOUND)


def _folders(request: web.Request, coordinator) -> list[str]:
    """The folder a list request asks for. Raises _Refused without a known person."""
    person = request.query.get("person")
    if person is None:
        raise _Refused(
            web.json_response({"error": "person_required"}, status=HTTPStatus.BAD_REQUEST)
        )
    folder = normalise_person(person)
    if folder not in coordinator.persons:
        raise _Refused(
            web.json_response(
                {"error": "unknown_person", "person": person}, status=HTTPStatus.NOT_FOUND
            )
        )
    return [folder]


def _days(request: web.Request) -> tuple[date, date]:
    """The days a list request asks for: a date, a month, or today."""
    query = request.query
    if "date" in query and "month" in query:
        raise _Refused(
            web.json_response(
                {"error": "date_and_month"}, status=HTTPStatus.BAD_REQUEST
            )
        )
    if "date" in query:
        try:
            day = date.fromisoformat(query["date"])
        except ValueError as err:
            raise _Refused(
                web.json_response({"error": "invalid_date"}, status=HTTPStatus.BAD_REQUEST)
            ) from err
        return day, day
    if "month" in query:
        try:
            year, _, month = query["month"].partition("-")
            first = date(int(year), int(month), 1)
        except ValueError as err:
            raise _Refused(
                web.json_response({"error": "invalid_month"}, status=HTTPStatus.BAD_REQUEST)
            ) from err
        return first, first.replace(day=calendar.monthrange(first.year, first.month)[1])
    today = dt_util.now().date()
    return today, today


def _item_json(coordinator, folder: str, record: dict[str, Any]) -> dict[str, Any]:
    """A stored record as it is sent back."""
    item = {
        "id": record["id"],
        "person": coordinator.person_name(folder),
        "created_at": record["created_at"].isoformat(),
        "received_at": record["received_at"].isoformat(),
        "name": record["name"],
        "meal": record["meal"],
        "portion": record["portion"],
    }
    for field in ["mass", *NUTRIENTS]:
        item[field] = record[field]
    return item
