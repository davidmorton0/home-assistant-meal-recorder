"""Validation of an incoming batch of items.

Pure logic: no Home Assistant imports, so it can be tested on its own.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, tzinfo
from typing import Any

from .const import (
    MAX_ITEMS,
    MAX_NAME_LEN,
    MAX_PERSON_LEN,
    MAX_PORTION_LEN,
    MEALS,
    NUTRIENTS,
)

_UNSAFE = re.compile(r"[^a-z0-9_]")


class TooManyItems(Exception):
    """Raised when a batch holds more items than the cap allows."""


def normalise_person(person: str) -> str:
    """Return the folder name for a person: lower case, spaces to underscores."""
    folder = _UNSAFE.sub("", person.strip().lower().replace(" ", "_"))
    return folder.strip("_")


def _parse_created_at(value: Any, tz: tzinfo) -> datetime:
    if not isinstance(value, str):
        raise ValueError("must be an ISO 8601 string")
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as err:
        raise ValueError("not a valid ISO 8601 timestamp") from err
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed


def _parse_number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("must be a number")
    number = float(value)
    if number < 0:
        raise ValueError("must not be negative")
    return number


def _parse_text(value: Any, maximum: int, allow_empty: bool) -> str:
    if not isinstance(value, str):
        raise ValueError("must be text")
    text = value.strip()
    if not text and not allow_empty:
        raise ValueError("must not be empty")
    if len(text) > maximum:
        raise ValueError(f"must be at most {maximum} characters")
    return text


def validate_batch(
    payload: Any,
    default_person: str,
    tz: tzinfo,
    received_at: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate a payload.

    Returns (items, errors). A batch is all or nothing: if errors is not empty
    the caller stores nothing.
    """
    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict) and isinstance(payload.get("items"), list):
        raw_items = payload["items"]
    else:
        return [], [{"index": None, "field": "items", "message": "expected a list of items"}]

    if len(raw_items) > MAX_ITEMS:
        raise TooManyItems(len(raw_items))

    items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            errors.append({"index": index, "field": None, "message": "item must be an object"})
            continue

        item: dict[str, Any] = {"id": str(uuid.uuid4()), "received_at": received_at}

        try:
            item["created_at"] = _parse_created_at(raw.get("created_at"), tz)
        except ValueError as err:
            errors.append({"index": index, "field": "created_at", "message": str(err)})

        person = raw.get("person")
        if person is None or (isinstance(person, str) and not person.strip()):
            person = default_person
        try:
            person_name = _parse_text(person, MAX_PERSON_LEN, allow_empty=False)
            if not normalise_person(person_name):
                raise ValueError("must hold letters or digits")
            item["person"] = person_name
        except ValueError as err:
            errors.append({"index": index, "field": "person", "message": str(err)})

        try:
            item["name"] = _parse_text(raw.get("name"), MAX_NAME_LEN, allow_empty=False)
        except ValueError as err:
            errors.append({"index": index, "field": "name", "message": str(err)})

        meal = raw.get("meal")
        if isinstance(meal, str) and meal.strip().lower() in MEALS:
            item["meal"] = meal.strip().lower()
        else:
            errors.append(
                {"index": index, "field": "meal", "message": f"must be one of {', '.join(MEALS)}"}
            )

        try:
            item["portion"] = _parse_text(raw.get("portion"), MAX_PORTION_LEN, allow_empty=True)
        except ValueError as err:
            errors.append({"index": index, "field": "portion", "message": str(err)})

        for field in ["mass", *NUTRIENTS]:
            try:
                item[field] = _parse_number(raw.get(field))
            except ValueError as err:
                errors.append({"index": index, "field": field, "message": str(err)})

        items.append(item)

    if errors:
        return [], errors
    return items, []
