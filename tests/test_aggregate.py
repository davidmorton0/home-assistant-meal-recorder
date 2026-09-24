"""Grouping and totals."""

from datetime import date, datetime, timedelta, timezone

from custom_components.meal_recorder import aggregate

TZ = timezone(timedelta(hours=1))


def record(when, meal="breakfast", kcal=100.0, name="Item"):
    return {
        "id": "x",
        "created_at": datetime.fromisoformat(when).replace(tzinfo=TZ),
        "received_at": datetime(2026, 9, 24, tzinfo=TZ),
        "name": name,
        "meal": meal,
        "portion": "1 bowl",
        "mass": 100.0,
        "kcal": kcal,
        "protein": 10.0,
        "carbs": 20.0,
        "fat": 5.0,
    }


def test_day_groups_by_meal_with_totals():
    records = [
        record("2026-09-24T08:15", "breakfast", 310.0, "Porridge"),
        record("2026-09-24T12:30", "lunch", 420.0, "Salad"),
    ]
    summary = aggregate.day_summary(records, date(2026, 9, 24))
    assert list(summary["meals"]) == ["breakfast", "lunch", "dinner", "snack"]
    assert summary["meals"]["breakfast"]["totals"]["kcal"] == 310.0
    assert summary["meals"]["dinner"]["items"] == []
    assert summary["totals"]["kcal"] == 730.0
    assert summary["item_count"] == 2


def test_day_ignores_other_days():
    records = [record("2026-09-23T08:15"), record("2026-09-24T08:15")]
    assert aggregate.day_summary(records, date(2026, 9, 24))["item_count"] == 1


def test_day_items_are_in_time_order():
    records = [record("2026-09-24T12:30", name="Later"), record("2026-09-24T08:15", name="Earlier")]
    items = aggregate.day_summary(records, date(2026, 9, 24))["meals"]["breakfast"]["items"]
    assert [item["name"] for item in items] == ["Earlier", "Later"]


def test_day_totals_only():
    records = [record("2026-09-24T08:15", kcal=310.0), record("2026-09-24T12:30", kcal=420.0)]
    assert aggregate.day_totals(records, date(2026, 9, 24))["kcal"] == 730.0


def test_month_averages_over_days_with_items():
    records = [
        record("2026-09-01T08:15", kcal=2000.0),
        record("2026-09-02T08:15", kcal=1000.0),
    ]
    summary = aggregate.month_summary(records)
    assert summary["days_logged"] == 2
    assert summary["totals"]["kcal"] == 3000.0
    assert summary["averages"]["kcal"] == 1500.0
    assert list(summary["days"]) == ["2026-09-01", "2026-09-02"]


def test_empty_month():
    summary = aggregate.month_summary([])
    assert summary["days_logged"] == 0
    assert summary["averages"]["kcal"] == 0.0
