"""Grouping and totals for the day and month views."""

from __future__ import annotations

from datetime import date, datetime, timedelta
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


def daily_series(
    records: Iterable[dict[str, Any]],
    end: date,
    start: date | None = None,
    base: dict[str, float] | None = None,
) -> list[tuple[date, dict[str, float], dict[str, float]]]:
    """Every day from start to end: its totals and the running totals.

    Without a start the series begins on the first day with items. Items before
    start are left out, and the running totals begin from base. Days with
    nothing recorded are included as zero, so a day whose items were all
    deleted still has a row and the running totals after it stay true.
    """
    per_day: dict[date, dict[str, float]] = {}
    for record in records:
        when = record["created_at"].date()
        if start is not None and when < start:
            continue
        _add(per_day.setdefault(when, _empty_totals()), record)
    if start is None:
        if not per_day:
            return []
        start = min(per_day)

    running = {**_empty_totals(), **(base or {})}
    series: list[tuple[date, dict[str, float], dict[str, float]]] = []
    day = start
    last = max(end, *per_day) if per_day else end
    while day <= last:
        totals = per_day.get(day, _empty_totals())
        for field in _FIELDS:
            running[field] += totals[field]
        series.append(
            (
                day,
                {field: round(value, 1) for field, value in totals.items()},
                {field: round(value, 1) for field, value in running.items()},
            )
        )
        day += timedelta(days=1)
    return series
