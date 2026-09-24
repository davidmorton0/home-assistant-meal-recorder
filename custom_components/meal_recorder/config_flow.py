"""Setup and options for Meal Recorder."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .auth import hash_password
from .coordinator import PersonCollision
from .const import (
    CONF_DEFAULT_PERSON,
    CONF_PASSWORD_HASH,
    CONF_PERSONS,
    CONF_USERNAME,
    DOMAIN,
)
from .items import normalise_person

SETUP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required("password"): str,
        vol.Required(CONF_DEFAULT_PERSON): str,
    }
)


class MealRecorderConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask for the ingest credential and the default person."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors: dict[str, str] = {}
        if user_input is not None:
            person = user_input[CONF_DEFAULT_PERSON].strip()
            if not normalise_person(person):
                errors[CONF_DEFAULT_PERSON] = "invalid_person"
            elif not user_input["password"]:
                errors["password"] = "empty_password"
            else:
                password_hash = await self.hass.async_add_executor_job(
                    hash_password, user_input["password"]
                )
                return self.async_create_entry(
                    title="Meal Recorder",
                    data={
                        CONF_USERNAME: user_input[CONF_USERNAME].strip(),
                        CONF_PASSWORD_HASH: password_hash,
                        CONF_DEFAULT_PERSON: person,
                        CONF_PERSONS: {normalise_person(person): person},
                    },
                )

        return self.async_show_form(step_id="user", data_schema=SETUP_SCHEMA, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return MealRecorderOptionsFlow(entry)


OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional("add_person", default=""): str,
        vol.Optional("password", default=""): str,
    }
)


class MealRecorderOptionsFlow(OptionsFlow):
    """Add a person, or change the password."""

    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            person = (user_input.get("add_person") or "").strip()
            password = user_input.get("password") or ""

            if person and not normalise_person(person):
                errors["add_person"] = "invalid_person"

            if not errors and person:
                coordinator = self.hass.data[DOMAIN][self.entry.entry_id]
                try:
                    await coordinator.async_add_person(person)
                except PersonCollision:
                    errors["add_person"] = "person_collision"

            if not errors:
                if password:
                    self.hass.config_entries.async_update_entry(
                        self.entry,
                        data={
                            **self.entry.data,
                            CONF_PASSWORD_HASH: await self.hass.async_add_executor_job(
                                hash_password, password
                            ),
                        },
                    )
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init",
            data_schema=OPTIONS_SCHEMA,
            errors=errors,
            description_placeholders={
                "people": ", ".join(sorted(self.entry.data.get(CONF_PERSONS, {}).values()))
            },
        )
