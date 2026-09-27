"""Validation rules. Pure logic, no Home Assistant needed."""

import uuid
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
    "carbohydrate": 54.0,
    "fat": 6.2,
}


def good(**changes):
    """A valid item with a fresh id."""
    return {**GOOD, "id": str(uuid.uuid4()), **changes}


def validate(payload):
    return validate_batch(payload, TZ, NOW)


def test_accepts_a_batch():
    stored, errors = validate({"items": [good()]})
    assert errors == []
    assert len(stored) == 1
    assert stored[0]["person"] == "David"
    assert stored[0]["received_at"] == NOW
    assert stored[0]["id"]


def test_accepts_a_bare_list():
    stored, errors = validate([good()])
    assert errors == [] and len(stored) == 1


def test_meal_is_case_insensitive_and_stored_lower_case():
    stored, _ = validate([good(meal="BreakFast")])
    assert stored[0]["meal"] == "breakfast"


def test_unknown_meal_is_rejected():
    _, errors = validate([good(meal="brunch")])
    assert errors[0]["field"] == "meal"


@pytest.mark.parametrize("person", [None, "", "  "])
def test_missing_person_is_rejected(person):
    item = {k: v for k, v in good().items() if k != "person"}
    if person is not None:
        item["person"] = person
    _, errors = validate([item])
    assert errors[0]["field"] == "person"


def test_naive_time_is_read_in_the_given_zone():
    stored, _ = validate([good(created_at="2026-09-24T08:15:00")])
    assert stored[0]["created_at"].utcoffset() == timedelta(hours=1)


def test_zulu_time_is_accepted():
    stored, _ = validate([good(created_at="2026-09-24T07:15:00Z")])
    assert stored[0]["created_at"].utcoffset() == timedelta(0)


@pytest.mark.parametrize("field", ["mass", "kcal", "protein", "carbohydrate", "fat"])
def test_negative_numbers_are_rejected(field):
    _, errors = validate([good(**{field: -1})])
    assert errors[0]["field"] == field


@pytest.mark.parametrize("value", ["310", True, None])
def test_non_numbers_are_rejected(value):
    _, errors = validate([good(kcal=value)])
    assert errors[0]["field"] == "kcal"


def test_empty_name_is_rejected():
    _, errors = validate([good(name="  ")])
    assert errors[0]["field"] == "name"


def test_long_name_is_rejected():
    _, errors = validate([good(name="x" * 201)])
    assert errors[0]["field"] == "name"


def test_empty_portion_is_allowed():
    stored, errors = validate([good(portion="")])
    assert errors == [] and stored[0]["portion"] == ""


def test_a_batch_is_all_or_nothing():
    stored, errors = validate([good(), good(meal="brunch")])
    assert stored == []
    assert [error["index"] for error in errors] == [1]


def test_payload_must_be_a_list():
    stored, errors = validate({"item": good()})
    assert stored == [] and errors[0]["field"] == "items"


def test_too_many_items_raises():
    with pytest.raises(TooManyItems):
        validate([good()] * (items_module.MAX_ITEMS + 1))


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
    _, errors = validate([good(person="!!!")])
    assert errors[0]["field"] == "person"


@pytest.mark.parametrize("value", [None, "", "not-a-uuid", 123])
def test_a_missing_or_invalid_id_is_rejected(value):
    _, errors = validate([good(id=value)])
    assert errors[0]["field"] == "id"


def test_the_id_is_kept_in_canonical_form():
    item_id = str(uuid.uuid4())
    stored, _ = validate([good(id=item_id.upper())])
    assert stored[0]["id"] == item_id


def test_an_id_repeated_in_a_batch_is_rejected():
    first = good()
    _, errors = validate([first, good(id=first["id"])])
    assert [(error["index"], error["field"]) for error in errors] == [(1, "id")]
