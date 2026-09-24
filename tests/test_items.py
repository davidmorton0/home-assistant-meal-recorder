"""Validation rules. Pure logic, no Home Assistant needed."""

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.meal_recorder import items as items_module
from custom_components.meal_recorder.items import (
    TooManyItems,
    normalise_person,
    validate_batch,
)

TZ = timezone(timedelta(hours=1))
NOW = datetime(2026, 9, 24, 12, 0, tzinfo=TZ)

GOOD = {
    "created_at": "2026-09-24T08:15:00+01:00",
    "person": "David",
    "name": "Porridge with milk",
    "meal": "breakfast",
    "portion": "1 bowl",
    "mass": 250,
    "kcal": 310,
    "protein": 10.5,
    "carbs": 54.0,
    "fat": 6.2,
}


def validate(payload):
    return validate_batch(payload, "Default", TZ, NOW)


def test_accepts_a_batch():
    stored, errors = validate({"items": [GOOD]})
    assert errors == []
    assert len(stored) == 1
    assert stored[0]["person"] == "David"
    assert stored[0]["received_at"] == NOW
    assert stored[0]["id"]


def test_accepts_a_bare_list():
    stored, errors = validate([GOOD])
    assert errors == [] and len(stored) == 1


def test_meal_is_case_insensitive_and_stored_lower_case():
    stored, _ = validate([{**GOOD, "meal": "BreakFast"}])
    assert stored[0]["meal"] == "breakfast"


def test_unknown_meal_is_rejected():
    _, errors = validate([{**GOOD, "meal": "brunch"}])
    assert errors[0]["field"] == "meal"


def test_missing_person_uses_the_default():
    stored, _ = validate([{k: v for k, v in GOOD.items() if k != "person"}])
    assert stored[0]["person"] == "Default"


def test_naive_time_is_read_in_the_given_zone():
    stored, _ = validate([{**GOOD, "created_at": "2026-09-24T08:15:00"}])
    assert stored[0]["created_at"].utcoffset() == timedelta(hours=1)


def test_zulu_time_is_accepted():
    stored, _ = validate([{**GOOD, "created_at": "2026-09-24T07:15:00Z"}])
    assert stored[0]["created_at"].utcoffset() == timedelta(0)


@pytest.mark.parametrize("field", ["mass", "kcal", "protein", "carbs", "fat"])
def test_negative_numbers_are_rejected(field):
    _, errors = validate([{**GOOD, field: -1}])
    assert errors[0]["field"] == field


@pytest.mark.parametrize("value", ["310", True, None])
def test_non_numbers_are_rejected(value):
    _, errors = validate([{**GOOD, "kcal": value}])
    assert errors[0]["field"] == "kcal"


def test_empty_name_is_rejected():
    _, errors = validate([{**GOOD, "name": "  "}])
    assert errors[0]["field"] == "name"


def test_long_name_is_rejected():
    _, errors = validate([{**GOOD, "name": "x" * 201}])
    assert errors[0]["field"] == "name"


def test_empty_portion_is_allowed():
    stored, errors = validate([{**GOOD, "portion": ""}])
    assert errors == [] and stored[0]["portion"] == ""


def test_a_batch_is_all_or_nothing():
    stored, errors = validate([GOOD, {**GOOD, "meal": "brunch"}])
    assert stored == []
    assert [error["index"] for error in errors] == [1]


def test_payload_must_be_a_list():
    stored, errors = validate({"item": GOOD})
    assert stored == [] and errors[0]["field"] == "items"


def test_too_many_items_raises():
    with pytest.raises(TooManyItems):
        validate([GOOD] * (items_module.MAX_ITEMS + 1))


@pytest.mark.parametrize(
    ("name", "folder"),
    [
        ("David", "david"),
        ("David Morton", "david_morton"),
        ("  Sam  ", "sam"),
        ("Anne-Marie", "annemarie"),
        ("D@vid!", "dvid"),
    ],
)
def test_person_normalisation(name, folder):
    assert normalise_person(name) == folder


def test_person_without_letters_or_digits_is_rejected():
    _, errors = validate([{**GOOD, "person": "!!!"}])
    assert errors[0]["field"] == "person"
