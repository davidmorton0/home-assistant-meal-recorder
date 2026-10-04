"""The ingest endpoint and the config flow.

These need Home Assistant and pytest-homeassistant-custom-component, so they
are skipped where those are not installed and run in CI.
"""

import base64
import json
import uuid
from http import HTTPStatus

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

pytestmark = pytest.mark.usefixtures("recorder_mock", "enable_custom_integrations")

from homeassistant.core import HomeAssistant  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.meal_recorder.auth import hash_password  # noqa: E402
from custom_components.meal_recorder.const import (  # noqa: E402
    CONF_PASSWORD_HASH,
    CONF_PERSONS,
    CONF_USERNAME,
    DOMAIN,
)

ITEM = {
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

URL = "/api/meal_recorder/items"


def item(**changes):
    """A valid item with a fresh id."""
    return {**ITEM, "id": str(uuid.uuid4()), **changes}


def basic(username="meals", password="secret"):
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture(name="entry")
async def entry_fixture(hass: HomeAssistant, tmp_path):
    hass.config.config_dir = str(tmp_path)
    # Items are stored as local times, so the zone the test items are sent in.
    await hass.config.async_set_time_zone("Europe/London")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Meal Recorder",
        data={
            CONF_USERNAME: "meals",
            CONF_PASSWORD_HASH: hash_password("secret"),
            CONF_PERSONS: {"david": "David"},
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_stores_a_batch(hass, hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    response = await client.post(URL, json={"items": [item()]}, headers=basic())
    assert response.status == HTTPStatus.CREATED
    body = await response.json()
    assert body["stored"] == 1 and len(body["ids"]) == 1

    path = hass.config.path("meal_recorder", "david", "09_2026.csv")
    with open(path, encoding="utf-8") as handle:
        assert "Porridge with milk" in handle.read()


async def test_a_bare_list_is_accepted(hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    response = await client.post(URL, json=[item()], headers=basic())
    assert response.status == HTTPStatus.CREATED


async def test_missing_credentials_are_refused(hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    response = await client.post(URL, json={"items": [item()]})
    assert response.status == HTTPStatus.UNAUTHORIZED
    assert "Basic realm" in response.headers["WWW-Authenticate"]


@pytest.mark.parametrize(
    "headers",
    [basic(password="wrong"), basic(username="other"), {"Authorization": "Bearer x"}],
)
async def test_wrong_credentials_are_refused(hass_client_no_auth, entry, headers):
    client = await hass_client_no_auth()
    response = await client.post(URL, json={"items": [item()]}, headers=headers)
    assert response.status == HTTPStatus.UNAUTHORIZED


async def test_an_invalid_item_stores_nothing(hass, hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    response = await client.post(
        URL, json={"items": [item(), item(meal="brunch")]}, headers=basic()
    )
    assert response.status == HTTPStatus.BAD_REQUEST
    body = await response.json()
    assert body["error"] == "validation"
    assert body["details"][0]["index"] == 1
    import os

    assert not os.path.exists(hass.config.path("meal_recorder", "david", "09_2026.csv"))


async def test_broken_json_is_refused(hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    response = await client.post(URL, data="{", headers=basic())
    assert response.status == HTTPStatus.BAD_REQUEST


async def test_an_oversized_body_is_refused(hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    payload = json.dumps({"items": [item(name="x" * 199)] * 20000})
    response = await client.post(
        URL, data=payload, headers={**basic(), "Content-Type": "application/json"}
    )
    assert response.status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE


async def test_an_unknown_person_is_refused(hass, hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    response = await client.post(URL, json=[item(person="Sam")], headers=basic())
    assert response.status == HTTPStatus.CONFLICT
    assert (await response.json())["error"] == "unknown_person"
    import os

    assert not os.path.exists(hass.config.path("meal_recorder", "sam"))


async def test_a_person_added_in_the_options_is_accepted(hass, hass_client_no_auth, entry):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_add_person("Sam")
    await hass.async_block_till_done()

    client = await hass_client_no_auth()
    response = await client.post(URL, json=[item(person="Sam")], headers=basic())
    assert response.status == HTTPStatus.CREATED
    assert hass.states.get("sensor.meals_sam_day") is not None


async def test_a_colliding_person_is_refused(hass, entry):
    from custom_components.meal_recorder.coordinator import PersonCollision

    coordinator = hass.data[DOMAIN][entry.entry_id]
    with pytest.raises(PersonCollision):
        await coordinator.async_add_person("DAVID")


@pytest.mark.freeze_time("2026-09-24 12:00:00+01:00")
async def test_entities_follow_the_stored_items(hass, hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    await client.post(URL, json={"items": [item()]}, headers=basic())
    await hass.async_block_till_done()

    day = hass.states.get("sensor.meals_david_day")
    assert day is not None
    assert day.attributes["meals"]["breakfast"]["items"][0]["name"] == "Porridge with milk"
    assert day.attributes["totals"]["kcal"] == 310.0
    assert hass.states.get("date.meals_day_shown") is not None


async def test_an_id_already_stored_is_refused(hass, hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    first = item()
    await client.post(URL, json=[first], headers=basic())
    response = await client.post(URL, json=[item(), item(id=first["id"])], headers=basic())
    assert response.status == HTTPStatus.CONFLICT
    body = await response.json()
    assert body == {"error": "duplicate_id", "ids": [first["id"]]}

    coordinator = hass.data[DOMAIN][entry.entry_id]
    records = coordinator.store.read_month("david", 2026, 9)
    assert len(records) == 1



async def test_a_single_item_is_accepted(hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    response = await client.post(URL, json=item(), headers=basic())
    assert response.status == HTTPStatus.CREATED
    body = await response.json()
    assert body["stored"] == 1
    assert response.headers["Location"] == f"{URL}/{body['ids'][0]}"


@pytest.mark.freeze_time("2026-09-24 12:00:00+01:00")
async def test_the_collection_lists_a_day_a_month_and_a_person(hass, hass_client_no_auth, entry):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_add_person("Sam")
    client = await hass_client_no_auth()
    today = item()
    await client.post(
        URL,
        json=[
            today,
            item(created_at="2026-09-20T13:00:00+01:00", name="Soup"),
            item(created_at="2026-08-31T13:00:00+01:00", name="Last month"),
            item(person="Sam", name="Toast"),
        ],
        headers=basic(),
    )

    # A person and no day: today.
    body = await (await client.get(f"{URL}?person=David", headers=basic())).json()
    assert body["count"] == 1
    assert (body["from"], body["to"]) == ("2026-09-24", "2026-09-24")
    [stored] = body["items"]
    assert stored["person"] == "David" and stored["kcal"] == 310
    assert stored["id"] == today["id"]
    assert stored["created_at"].startswith("2026-09-24T08:15:00")

    body = await (await client.get(f"{URL}?person=Sam", headers=basic())).json()
    assert [i["name"] for i in body["items"]] == ["Toast"]

    body = await (await client.get(f"{URL}?person=David&date=2026-09-20", headers=basic())).json()
    assert [i["name"] for i in body["items"]] == ["Soup"]

    body = await (await client.get(f"{URL}?month=2026-09&person=david", headers=basic())).json()
    assert [i["name"] for i in body["items"]] == ["Soup", "Porridge with milk"]


async def test_the_collection_refuses_bad_filters(hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    for query, error in [
        ("", "person_required"),
        ("?date=2026-09-24", "person_required"),
        ("?person=David&date=2026-13-01", "invalid_date"),
        ("?person=David&month=2026-99", "invalid_month"),
        ("?person=David&date=2026-09-24&month=2026-09", "date_and_month"),
    ]:
        response = await client.get(f"{URL}{query}", headers=basic())
        assert response.status == HTTPStatus.BAD_REQUEST
        assert (await response.json())["error"] == error

    response = await client.get(f"{URL}?person=Sam", headers=basic())
    assert response.status == HTTPStatus.NOT_FOUND
    assert (await response.json())["error"] == "unknown_person"


async def test_an_item_is_read_replaced_and_deleted(hass, hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    stored = item()
    await client.post(URL, json=[stored], headers=basic())
    item_url = f"{URL}/{stored['id']}"

    body = await (await client.get(item_url, headers=basic())).json()
    assert (body["id"], body["person"], body["name"]) == (stored["id"], "David", "Porridge with milk")
    received_at = body["received_at"]

    response = await client.put(
        item_url, json={**ITEM, "name": "Porridge with soya milk", "kcal": 280}, headers=basic()
    )
    assert response.status == HTTPStatus.OK
    body = await response.json()
    assert (body["name"], body["kcal"], body["id"]) == ("Porridge with soya milk", 280.0, stored["id"])
    # received_at is the time the row was written, so it moves on.
    from datetime import datetime

    assert datetime.fromisoformat(body["received_at"]) >= datetime.fromisoformat(received_at)

    coordinator = hass.data[DOMAIN][entry.entry_id]
    [record] = coordinator.store.read_month("david", 2026, 9)
    assert record["name"] == "Porridge with soya milk"

    response = await client.delete(item_url, headers=basic())
    assert response.status == HTTPStatus.NO_CONTENT
    assert coordinator.store.read_month("david", 2026, 9) == []


async def test_a_replaced_item_can_move_month(hass, hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    stored = item()
    await client.post(URL, json=[stored], headers=basic())
    # Neither the id nor the person is needed in the body, as the skill's script sends it.
    fields = {k: v for k, v in ITEM.items() if k != "person"}
    response = await client.put(
        f"{URL}/{stored['id']}",
        json={**fields, "created_at": "2026-08-31T19:00:00+01:00"},
        headers=basic(),
    )
    assert response.status == HTTPStatus.OK

    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator.store.read_month("david", 2026, 9) == []
    [moved] = coordinator.store.read_month("david", 2026, 8)
    assert moved["id"] == stored["id"]


async def test_an_unknown_item_is_not_found(hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    missing = f"{URL}/0b6f3c1e-8a2d-4f1e-9c3b-5d7a2e4f6a10"
    for response in [
        await client.get(missing, headers=basic()),
        await client.put(missing, json=ITEM, headers=basic()),
        await client.delete(missing, headers=basic()),
    ]:
        assert response.status == HTTPStatus.NOT_FOUND
        assert (await response.json())["error"] == "not_found"


async def test_a_replacement_is_checked(hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    stored = item()
    await client.post(URL, json=[stored], headers=basic())
    item_url = f"{URL}/{stored['id']}"

    response = await client.put(item_url, json={**ITEM, "meal": "brunch"}, headers=basic())
    assert response.status == HTTPStatus.BAD_REQUEST
    assert (await response.json())["error"] == "validation"

    response = await client.put(item_url, json={**ITEM, "person": "Sam"}, headers=basic())
    assert response.status == HTTPStatus.BAD_REQUEST
    assert (await response.json())["error"] == "person_mismatch"

    response = await client.put(
        item_url, json={**ITEM, "id": "0b6f3c1e-8a2d-4f1e-9c3b-5d7a2e4f6a10"}, headers=basic()
    )
    assert response.status == HTTPStatus.BAD_REQUEST
    assert (await response.json())["error"] == "id_mismatch"

    response = await client.put(item_url, json=[ITEM], headers=basic())
    assert response.status == HTTPStatus.BAD_REQUEST
    assert (await response.json())["error"] == "expected_an_item"


async def test_every_method_needs_credentials(hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    item_url = f"{URL}/0b6f3c1e-8a2d-4f1e-9c3b-5d7a2e4f6a10"
    for response in [
        await client.get(URL),
        await client.get(item_url),
        await client.put(item_url, json=ITEM),
        await client.delete(item_url),
    ]:
        assert response.status == HTTPStatus.UNAUTHORIZED


async def call(hass, domain, service, **data):
    await hass.services.async_call(domain, service, data, blocking=True)


@pytest.mark.freeze_time("2026-09-24 12:00:00+01:00")
async def test_the_pickers_start_on_today_for_the_first_person(hass, entry):
    assert hass.states.get("select.meals_person").state == "David"
    assert hass.states.get("select.meals_year").state == "2026"
    assert hass.states.get("select.meals_month").state == "September"
    day = hass.states.get("select.meals_day")
    assert day.state == "24"
    assert day.attributes["options"][-1] == "30"


@pytest.mark.freeze_time("2026-09-24 12:00:00+01:00")
async def test_the_day_sensor_holds_the_days_items(hass, hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    stored = item()
    await client.post(URL, json=[stored, item(created_at="2026-09-23T08:15:00+01:00")], headers=basic())
    await hass.async_block_till_done()

    state = hass.states.get("sensor.meals_day")
    assert state.state == "310.0"
    [shown] = state.attributes["items"]
    assert shown["id"] == stored["id"]
    assert (shown["date"], shown["time"], shown["meal"]) == ("2026-09-24", "08:15", "breakfast")
    assert state.attributes["meal_totals"]["breakfast"]["kcal"] == 310.0


@pytest.mark.freeze_time("2026-09-24 12:00:00+01:00")
async def test_the_buttons_move_by_a_day_a_week_and_a_month(hass, entry):
    async def press(name):
        await call(hass, "button", "press", entity_id=f"button.meals_{name}")
        return hass.states.get("select.meals_month").state, hass.states.get("select.meals_day").state

    assert await press("next_month") == ("October", "24")
    assert await press("previous_day") == ("October", "23")
    await call(hass, "select", "select_option", entity_id="select.meals_day", option="31")
    assert await press("previous_month") == ("September", "30")
    assert await press("next_day") == ("October", "1")
    assert await press("next_week") == ("October", "8")
    assert await press("previous_week") == ("October", "1")
    assert await press("previous_week") == ("September", "24")
    await call(hass, "select", "select_option", entity_id="select.meals_day", option="2")
    assert await press("today") == ("September", "24")


@pytest.mark.freeze_time("2026-09-24 12:00:00+01:00")
async def test_the_pickers_list_every_month_since_the_first_file(hass, hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    await client.post(URL, json=[item(created_at="2025-11-02T08:15:00+00:00")], headers=basic())
    await hass.async_block_till_done()

    assert hass.states.get("select.meals_year").attributes["options"] == ["2026", "2025"]
    months = hass.states.get("select.meals_month").attributes["options"]
    assert months == ["January", "February", "March", "April", "May", "June",
                      "July", "August", "September"]

    # The year keeps the month, and the month shown is always listed.
    await call(hass, "select", "select_option", entity_id="select.meals_year", option="2025")
    assert hass.states.get("select.meals_month").state == "September"
    assert hass.states.get("select.meals_month").attributes["options"] == [
        "September", "October", "November", "December"
    ]


@pytest.mark.freeze_time("2026-09-24 12:00:00+01:00")
async def test_the_person_picker_changes_whose_items_are_shown(hass, hass_client_no_auth, entry):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_add_person("Sam")
    client = await hass_client_no_auth()
    await client.post(URL, json=[item(person="Sam", name="Toast")], headers=basic())
    await hass.async_block_till_done()
    assert hass.states.get("sensor.meals_day").attributes["items"] == []

    await call(hass, "select", "select_option", entity_id="select.meals_person", option="Sam")
    state = hass.states.get("sensor.meals_day")
    assert state.attributes["person"] == "Sam"
    assert [i["name"] for i in state.attributes["items"]] == ["Toast"]


@pytest.mark.freeze_time("2026-09-24 12:00:00+01:00")
async def test_the_services_add_update_and_delete(hass, entry):
    fields = {k: v for k, v in ITEM.items() if k != "created_at"}
    await call(hass, DOMAIN, "add_item", **fields, created_at="2026-09-20T13:00")
    coordinator = hass.data[DOMAIN][entry.entry_id]
    [record] = coordinator.store.read_month("david", 2026, 9)
    assert record["created_at"].date().isoformat() == "2026-09-20"

    del fields["person"]
    await call(hass, DOMAIN, "update_item", id=record["id"], **{**fields, "kcal": 400}, created_at="2026-08-31T13:00")
    assert coordinator.store.read_month("david", 2026, 9) == []
    [moved] = coordinator.store.read_month("david", 2026, 8)
    assert (moved["id"], moved["kcal"]) == (record["id"], 400.0)

    await call(hass, DOMAIN, "delete_item", id=record["id"])
    assert coordinator.store.read_month("david", 2026, 8) == []


async def test_the_services_refuse_bad_input(hass, entry):
    from homeassistant.exceptions import ServiceValidationError

    fields = {k: v for k, v in ITEM.items() if k != "created_at"}
    with pytest.raises(ServiceValidationError, match="meal"):
        await call(hass, DOMAIN, "add_item", **{**fields, "meal": "brunch"}, created_at="2026-09-20T13:00")
    with pytest.raises(ServiceValidationError, match="person"):
        await call(hass, DOMAIN, "add_item", **{**fields, "person": " "}, created_at="2026-09-20T13:00")
    with pytest.raises(ServiceValidationError, match="no item"):
        await call(hass, DOMAIN, "delete_item", id="0b6f3c1e-8a2d-4f1e-9c3b-5d7a2e4f6a10")


async def test_the_card_script_is_served(hass, hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    response = await client.get("/meal_recorder/meal-recorder-card.js")
    assert response.status == HTTPStatus.OK
    assert "meal-recorder-card" in await response.text()



async def test_every_entity_on_the_page_exists(hass, entry):
    import re
    from pathlib import Path

    folder = Path(__file__).parents[1] / "custom_components" / "meal_recorder"
    text = (folder / "meal-recorder-panel.js").read_text() + (folder / "meal-recorder-card.js").read_text()
    entity_ids = set(re.findall(r"\b(?:select|button|sensor)\.meals_\w+", text))
    assert len(entity_ids) == 12
    for entity_id in entity_ids:
        assert hass.states.get(entity_id) is not None, entity_id


async def test_the_page_script_is_served(hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    response = await client.get("/meal_recorder/meal-recorder-panel.js")
    assert response.status == HTTPStatus.OK
