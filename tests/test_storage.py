"""CSV storage: folders per person, one file per month."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.meal_recorder.storage import CsvStore, month_file_name

TZ = timezone(timedelta(hours=1))


def item(when, name="Porridge", meal="breakfast", folder="david", portion="1 bowl", kcal=310.0):
    return {
        "id": str(uuid.uuid4()),
        "created_at": datetime.fromisoformat(when).replace(tzinfo=TZ),
        "received_at": datetime(2026, 9, 24, 12, 0, tzinfo=TZ),
        "name": name,
        "meal": meal,
        "portion": portion,
        "mass": 250.0,
        "kcal": kcal,
        "protein": 10.5,
        "carbohydrate": 54.0,
        "fat": 6.2,
        "folder": folder,
    }


@pytest.fixture(name="store")
def store_fixture(tmp_path):
    return CsvStore(tmp_path)


def test_file_name_is_month_then_year():
    assert month_file_name(2026, 9) == "09_2026.csv"


def test_writes_a_folder_per_person(store, tmp_path):
    store.append_items([item("2026-09-24T08:15"), item("2026-09-24T09:00", folder="sam")])
    assert store.folders() == ["david", "sam"]
    assert (tmp_path / "david" / "09_2026.csv").exists()


def test_header_is_written_once(store, tmp_path):
    store.append_items([item("2026-09-24T08:15")])
    store.append_items([item("2026-09-24T09:15")])
    text = (tmp_path / "david" / "09_2026.csv").read_text()
    assert text.count("id,created_at") == 1
    assert len(store.read_month("david", 2026, 9)) == 2


def test_month_comes_from_local_time(store, tmp_path):
    store.append_items([item("2026-10-01T00:30")])
    assert (tmp_path / "david" / "10_2026.csv").exists()
    assert not (tmp_path / "david" / "09_2026.csv").exists()


def test_a_batch_spanning_months_writes_both(store, tmp_path):
    store.append_items([item("2026-09-30T23:30"), item("2026-10-01T00:30")])
    assert (tmp_path / "david" / "09_2026.csv").exists()
    assert (tmp_path / "david" / "10_2026.csv").exists()


def test_quoting_survives_a_round_trip(store):
    store.append_items([item("2026-09-24T08:15", name='Chips, "big"\nportion')])
    assert store.read_month("david", 2026, 9)[0]["name"] == 'Chips, "big"\nportion'


def test_records_are_sorted_by_created_at(store):
    store.append_items([item("2026-09-24T12:30", name="Lunch"), item("2026-09-24T08:15")])
    assert [r["name"] for r in store.read_month("david", 2026, 9)] == ["Porridge", "Lunch"]


def test_missing_file_is_an_empty_month(store):
    assert store.read_month("nobody", 2026, 9) == []


def test_malformed_row_is_skipped(store, tmp_path):
    store.append_items([item("2026-09-24T08:15")])
    path = tmp_path / "david" / "09_2026.csv"
    with path.open("a", encoding="utf-8") as handle:
        handle.write("not,a,valid,row\n")
    assert len(store.read_month("david", 2026, 9)) == 1


def test_edits_to_the_file_are_picked_up(store, tmp_path):
    store.append_items([item("2026-09-24T08:15")])
    assert len(store.read_month("david", 2026, 9)) == 1
    path = tmp_path / "david" / "09_2026.csv"
    lines = path.read_text().splitlines()
    path.write_text("\n".join(lines[:1]) + "\n")
    assert store.read_month("david", 2026, 9) == []


def test_ids_cover_every_person_and_month(store):
    items = [item("2026-09-24T08:15"), item("2026-10-01T08:15", folder="sam")]
    store.append_items(items)
    assert store.ids() == {i["id"] for i in items}


def test_delete_removes_only_that_item(store):
    keep, drop = item("2026-09-24T08:15", name="Keep"), item("2026-09-24T09:15", name="Drop")
    store.append_items([keep, drop])
    assert store.delete_item("david", drop["id"])
    assert [r["name"] for r in store.read_month("david", 2026, 9)] == ["Keep"]
    assert drop["id"] not in store.ids()


def test_delete_of_an_unknown_id_is_false(store):
    store.append_items([item("2026-09-24T08:15")])
    assert not store.delete_item("david", str(uuid.uuid4()))
    assert not store.delete_item("nobody", str(uuid.uuid4()))


def test_update_rewrites_the_item_in_place(store):
    stored = item("2026-09-24T08:15")
    store.append_items([stored])
    assert store.update_item("david", {**stored, "name": "Toast", "kcal": 320.0})
    [record] = store.read_month("david", 2026, 9)
    assert (record["id"], record["name"], record["kcal"]) == (stored["id"], "Toast", 320.0)


def test_update_moves_an_item_to_its_new_month(store, tmp_path):
    stored = item("2026-09-30T08:15")
    store.append_items([stored])
    moved = {**stored, "created_at": datetime(2026, 10, 1, 8, 15, tzinfo=TZ)}
    assert store.update_item("david", moved)
    assert store.read_month("david", 2026, 9) == []
    assert [r["id"] for r in store.read_month("david", 2026, 10)] == [stored["id"]]


def test_update_of_an_unknown_id_is_false(store):
    assert not store.update_item("david", item("2026-09-24T08:15"))


def test_months_are_read_from_the_file_names(store, tmp_path):
    store.append_items([item("2026-09-24T08:15"), item("2026-06-02T08:15")])
    (tmp_path / "david" / "notes.csv").write_text("")
    assert store.months("david") == [(2026, 6), (2026, 9)]
    assert store.months("nobody") == []


def test_get_item_finds_it_by_id(store):
    stored = item("2026-09-24T08:15")
    store.append_items([stored])
    assert store.get_item("david", stored["id"])["name"] == "Porridge"
    assert store.get_item("david", str(uuid.uuid4())) is None
