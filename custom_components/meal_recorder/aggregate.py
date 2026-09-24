"""Grouping and totals for the day and month views."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable

from .const import MEALS, NUTRIENTS

_FIELDS = ["mass", *NUTRIENTS]


def _empty_totals() -> dict[str, float]:
    return {field: 0.0 for field in _FIELDS}


def _add(totals: dict[str, float], record: dict[str, Any]) -> None:
    for field in _FIELDS:
        totals[field] += float(record[field])


def day_summary(records: Iterable[dict[str, Any]], day: date) -> dict[str, Any]:
    """Group one day's records by meal, with totals per meal and for the day."""
    meals: dict[str, dict[str, Any]] = {
        meal: {"items": [], "totals": _empty_totals()} for meal in MEALS
    }
    totals = _empty_totals()

    for record in sorted(records, key=lambda item: item["created_at"]):
        created: datetime = record["created_at"]
        if created.date() != day:
            continue
        meal = record["meal"] if record["meal"] in meals else "snack"
        meals[meal]["items"].append(
            {
                "time": created.strftime("%H:%M"),
                "name": record["name"],
                "portion": record["portion"],
                **{field: round(float(record[field]), 1) for field in _FIELDS},
            }
        )
        _add(meals[meal]["totals"], record)
        _add(totals, record)

    for meal in meals.values():
        meal["totals"] = {field: round(value, 1) for field, value in meal["totals"].items()}

    return {
        "date": day.isoformat(),
        "meals": meals,
        "totals": {field: round(value, 1) for field, value in totals.items()},
        "item_count": sum(len(meal["items"]) for meal in meals.values()),
    }


def day_totals(records: Iterable[dict[str, Any]], day: date) -> dict[str, float]:
    """Return one day's totals only."""
    totals = _empty_totals()
    for record in records:
        if record["created_at"].date() == day:
            _add(totals, record)
    return {field: round(value, 1) for field, value in totals.items()}


def month_summary(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Totals, averages over days with items, and per-day totals for a month."""
    per_day: dict[str, dict[str, float]] = {}
    totals = _empty_totals()

    for record in records:
        key = record["created_at"].date().isoformat()
        day = per_day.setdefault(key, _empty_totals())
        _add(day, record)
        _add(totals, record)

    days_logged = len(per_day)
    averages = {
        field: round(totals[field] / days_logged, 1) if days_logged else 0.0
        for field in _FIELDS
    }

    return {
        "days": {
            key: {field: round(value, 1) for field, value in day.items()}
            for key, day in sorted(per_day.items())
        },
        "totals": {field: round(value, 1) for field, value in totals.items()},
        "averages": averages,
        "days_logged": days_logged,
    }
