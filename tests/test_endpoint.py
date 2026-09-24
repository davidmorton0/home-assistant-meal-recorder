"""The ingest endpoint and the config flow.

These need Home Assistant and pytest-homeassistant-custom-component, so they
are skipped where those are not installed and run in CI.
"""

import base64
import json
from http import HTTPStatus

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.meal_recorder.auth import hash_password  # noqa: E402
from custom_components.meal_recorder.const import (  # noqa: E402
    CONF_DEFAULT_PERSON,
    CONF_PASSWORD_HASH,
    CONF_PERSONS,
    CONF_USERNAME,
    DOMAIN,
)

ITEM = {
    "created_at": "2026-09-24T08:15:00+01:00",
    "name": "Porridge with milk",
    "meal": "breakfast",
    "portion": "1 bowl",
    "mass": 250,
    "kcal": 310,
    "protein": 10.5,
    "carbs": 54.0,
    "fat": 6.2,
}

URL = "/api/meal_recorder/items"


def basic(username="meals", password="secret"):
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture(name="enable_custom_integrations", autouse=True)
def enable_custom_integrations_fixture(enable_custom_integrations):
    return enable_custom_integrations


@pytest.fixture(name="entry")
async def entry_fixture(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Meal Recorder",
        data={
            CONF_USERNAME: "meals",
            CONF_PASSWORD_HASH: hash_password("secret"),
            CONF_DEFAULT_PERSON: "David",
            CONF_PERSONS: {"david": "David"},
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_stores_a_batch(hass, hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    response = await client.post(URL, json={"items": [ITEM]}, headers=basic())
    assert response.status == HTTPStatus.CREATED
    body = await response.json()
    assert body["stored"] == 1 and len(body["ids"]) == 1

    path = hass.config.path("meal_recorder", "david", "09_2026.csv")
    with open(path, encoding="utf-8") as handle:
        assert "Porridge with milk" in handle.read()


async def test_a_bare_list_is_accepted(hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    response = await client.post(URL, json=[ITEM], headers=basic())
    assert response.status == HTTPStatus.CREATED


async def test_missing_credentials_are_refused(hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    response = await client.post(URL, json={"items": [ITEM]})
    assert response.status == HTTPStatus.UNAUTHORIZED
    assert "Basic realm" in response.headers["WWW-Authenticate"]


@pytest.mark.parametrize(
    "headers",
    [basic(password="wrong"), basic(username="other"), {"Authorization": "Bearer x"}],
)
async def test_wrong_credentials_are_refused(hass_client_no_auth, entry, headers):
    client = await hass_client_no_auth()
    response = await client.post(URL, json={"items": [ITEM]}, headers=headers)
    assert response.status == HTTPStatus.UNAUTHORIZED


async def test_an_invalid_item_stores_nothing(hass, hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    response = await client.post(
        URL, json={"items": [ITEM, {**ITEM, "meal": "brunch"}]}, headers=basic()
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
    payload = json.dumps({"items": [{**ITEM, "name": "x" * 199}] * 20000})
    response = await client.post(
        URL, data=payload, headers={**basic(), "Content-Type": "application/json"}
    )
    assert response.status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE


async def test_an_unknown_person_is_refused(hass, hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    response = await client.post(URL, json=[{**ITEM, "person": "Sam"}], headers=basic())
    assert response.status == HTTPStatus.CONFLICT
    assert (await response.json())["error"] == "unknown_person"
    import os

    assert not os.path.exists(hass.config.path("meal_recorder", "sam"))


async def test_a_person_added_in_the_options_is_accepted(hass, hass_client_no_auth, entry):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_add_person("Sam")
    await hass.async_block_till_done()

    client = await hass_client_no_auth()
    response = await client.post(URL, json=[{**ITEM, "person": "Sam"}], headers=basic())
    assert response.status == HTTPStatus.CREATED
    assert hass.states.get("sensor.meals_sam_day") is not None


async def test_a_colliding_person_is_refused(hass, entry):
    from custom_components.meal_recorder.coordinator import PersonCollision

    coordinator = hass.data[DOMAIN][entry.entry_id]
    with pytest.raises(PersonCollision):
        await coordinator.async_add_person("D a v i d")


async def test_entities_follow_the_stored_items(hass, hass_client_no_auth, entry):
    client = await hass_client_no_auth()
    await client.post(URL, json={"items": [ITEM]}, headers=basic())
    await hass.async_block_till_done()

    day = hass.states.get("sensor.meals_david_day")
    assert day is not None
    assert day.attributes["meals"]["breakfast"]["items"][0]["name"] == "Porridge with milk"
    assert day.attributes["totals"]["kcal"] == 310.0
    assert hass.states.get("date.meals_day_shown") is not None
