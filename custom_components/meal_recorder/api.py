"""The ingest endpoint."""

from __future__ import annotations

import base64
import binascii
import json
import logging
from http import HTTPStatus

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.ban import process_success_login, process_wrong_login
from homeassistant.util import dt as dt_util

from .auth import verify_password, verify_username
from .const import (
    CONF_DEFAULT_PERSON,
    CONF_PASSWORD_HASH,
    CONF_USERNAME,
    DOMAIN,
    MAX_BODY_BYTES,
)
from .coordinator import MealRecorderCoordinator, UnknownPerson
from .items import TooManyItems, validate_batch

_LOGGER = logging.getLogger(__name__)

_REALM = 'Basic realm="Meal Recorder", charset="UTF-8"'


class MealItemsView(HomeAssistantView):
    """Accepts a batch of items over Basic auth."""

    url = "/api/meal_recorder/items"
    name = "api:meal_recorder:items"
    requires_auth = False

    def __init__(self, hass) -> None:
        self.hass = hass

    @property
    def coordinator(self) -> MealRecorderCoordinator | None:
        """The coordinator of the configured entry, if the entry is loaded."""
        entries = self.hass.data.get(DOMAIN, {})
        return next(iter(entries.values()), None)

    async def post(self, request: web.Request) -> web.Response:
        """Validate and store a batch."""
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

        if request.content_length and request.content_length > MAX_BODY_BYTES:
            return self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "too_large")

        body = await request.content.read(MAX_BODY_BYTES + 1)
        if len(body) > MAX_BODY_BYTES:
            return self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "too_large")

        try:
            payload = json.loads(body)
        except ValueError:
            return self._error(HTTPStatus.BAD_REQUEST, "invalid_json")

        entry_data = coordinator.entry.data
        try:
            items, errors = validate_batch(
                payload,
                entry_data[CONF_DEFAULT_PERSON],
                dt_util.DEFAULT_TIME_ZONE,
                dt_util.now(),
            )
        except TooManyItems:
            return self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "too_many_items")

        if errors:
            return self.json({"error": "validation", "details": errors}, HTTPStatus.BAD_REQUEST)

        try:
            ids = await coordinator.async_add_items(items)
        except UnknownPerson as err:
            return self.json(
                {"error": "unknown_person", "person": err.person},
                HTTPStatus.CONFLICT,
            )
        except OSError:
            _LOGGER.exception("Storing items failed")
            return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "storage")

        return self.json({"stored": len(ids), "ids": ids}, HTTPStatus.CREATED)

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

    def _error(self, status: HTTPStatus, error: str, headers: dict | None = None) -> web.Response:
        return self.json({"error": error}, status, headers=headers)
