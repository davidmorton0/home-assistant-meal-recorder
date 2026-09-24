"""Setup and options flow."""

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant import config_entries  # noqa: E402
from homeassistant.data_entry_flow import FlowResultType  # noqa: E402

from custom_components.meal_recorder.auth import verify_password  # noqa: E402
from custom_components.meal_recorder.const import (  # noqa: E402
    CONF_DEFAULT_PERSON,
    CONF_PASSWORD_HASH,
    CONF_PERSONS,
    CONF_USERNAME,
    DOMAIN,
)


@pytest.fixture(name="enable_custom_integrations", autouse=True)
def enable_custom_integrations_fixture(enable_custom_integrations):
    return enable_custom_integrations


async def test_setup_stores_a_hash_not_the_password(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: "meals", "password": "secret", CONF_DEFAULT_PERSON: "David"},
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert "secret" not in str(data)
    assert verify_password("secret", data[CONF_PASSWORD_HASH])
    assert data[CONF_PERSONS] == {"david": "David"}


async def test_a_person_without_letters_is_refused(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: "meals", "password": "secret", CONF_DEFAULT_PERSON: "!!!"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"][CONF_DEFAULT_PERSON] == "invalid_person"


async def test_only_one_entry(hass):
    first = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    await hass.config_entries.flow.async_configure(
        first["flow_id"],
        {CONF_USERNAME: "meals", "password": "secret", CONF_DEFAULT_PERSON: "David"},
    )
    await hass.async_block_till_done()

    second = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert second["type"] == FlowResultType.ABORT
    assert second["reason"] == "single_instance_allowed"
