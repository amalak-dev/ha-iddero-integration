"""Config flow for Iddero."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .client import IdderoCannotConnectError, IdderoInvalidAuthError, IdderoWebClient
from .const import (
    CONF_AUTO_DISCOVER,
    CONF_BASE_PATH,
    CONF_CREATE_AREAS,
    CONF_DEVICES_FILE,
    CONF_POLL_INTERVAL,
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DEFAULT_AUTO_DISCOVER,
    DEFAULT_BASE_PATH,
    DEFAULT_CREATE_AREAS,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class IdderoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle an Iddero config flow."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the initial user step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            unique_id = f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            errors = await self._async_validation_errors(user_input)
            if not errors:
                options = {
                    CONF_AUTO_DISCOVER: user_input.pop(CONF_AUTO_DISCOVER),
                    CONF_CREATE_AREAS: user_input.pop(CONF_CREATE_AREAS),
                    CONF_DEVICES_FILE: user_input.pop(CONF_DEVICES_FILE),
                    CONF_POLL_INTERVAL: user_input.pop(CONF_POLL_INTERVAL),
                }
                return self.async_create_entry(
                    title=f"Iddero {user_input[CONF_HOST]}",
                    data=user_input,
                    options=options,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(user_input),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start re-authentication after the panel rejected the credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Ask for new credentials and check them against the panel."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = await self._async_validation_errors({**entry.data, **user_input})
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                _REAUTH_SCHEMA,
                {CONF_USERNAME: (user_input or entry.data).get(CONF_USERNAME)},
            ),
            description_placeholders={"host": entry.data[CONF_HOST]},
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return IdderoOptionsFlow(config_entry)

    async def _async_validation_errors(
        self, user_input: Mapping[str, Any]
    ) -> dict[str, str]:
        try:
            await self._async_validate_input(user_input)
        except IdderoInvalidAuthError:
            return {"base": "invalid_auth"}
        except IdderoCannotConnectError:
            return {"base": "cannot_connect"}
        except Exception:
            _LOGGER.exception("Unexpected error while validating the Iddero panel")
            return {"base": "unknown"}
        return {}

    async def _async_validate_input(self, user_input: Mapping[str, Any]) -> None:
        session = async_create_clientsession(
            self.hass,
            verify_ssl=user_input.get(CONF_VERIFY_SSL, True),
        )
        client = IdderoWebClient(
            host=user_input[CONF_HOST],
            port=user_input[CONF_PORT],
            use_ssl=user_input[CONF_USE_SSL],
            verify_ssl=user_input[CONF_VERIFY_SSL],
            base_path=user_input[CONF_BASE_PATH],
            username=user_input.get(CONF_USERNAME),
            password=user_input.get(CONF_PASSWORD),
            session=session,
        )
        await client.async_probe()


class IdderoOptionsFlow(config_entries.OptionsFlow):
    """Handle Iddero options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Manage integration options."""
        if user_input is not None:
            user_input = {
                **self._config_entry.options,
                **user_input,
            }
            return self.async_create_entry(title="", data=user_input)

        options = self._config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_AUTO_DISCOVER,
                        default=options.get(
                            CONF_AUTO_DISCOVER,
                            DEFAULT_AUTO_DISCOVER,
                        ),
                    ): bool,
                    vol.Required(
                        CONF_CREATE_AREAS,
                        default=options.get(
                            CONF_CREATE_AREAS,
                            DEFAULT_CREATE_AREAS,
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_DEVICES_FILE,
                        default=options.get(CONF_DEVICES_FILE, ""),
                    ): str,
                    vol.Required(
                        CONF_POLL_INTERVAL,
                        default=options.get(
                            CONF_POLL_INTERVAL,
                            DEFAULT_POLL_INTERVAL,
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
                }
            ),
        )


_PASSWORD_SELECTOR = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
)

_REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR,
    }
)


def _user_schema(user_input: dict[str, Any] | None = None) -> vol.Schema:
    defaults = user_input or {}
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(
                CONF_PORT,
                default=defaults.get(CONF_PORT, DEFAULT_PORT),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            vol.Required(
                CONF_USE_SSL,
                default=defaults.get(CONF_USE_SSL, False),
            ): bool,
            vol.Required(
                CONF_VERIFY_SSL,
                default=defaults.get(CONF_VERIFY_SSL, True),
            ): bool,
            vol.Required(
                CONF_BASE_PATH,
                default=defaults.get(CONF_BASE_PATH, DEFAULT_BASE_PATH),
            ): str,
            vol.Required(
                CONF_AUTO_DISCOVER,
                default=defaults.get(CONF_AUTO_DISCOVER, DEFAULT_AUTO_DISCOVER),
            ): bool,
            vol.Required(
                CONF_CREATE_AREAS,
                default=defaults.get(CONF_CREATE_AREAS, DEFAULT_CREATE_AREAS),
            ): bool,
            vol.Optional(
                CONF_DEVICES_FILE,
                default=defaults.get(CONF_DEVICES_FILE, ""),
            ): str,
            vol.Optional(
                CONF_USERNAME,
                default=defaults.get(CONF_USERNAME, ""),
            ): str,
            vol.Optional(
                CONF_PASSWORD,
                default=defaults.get(CONF_PASSWORD, ""),
            ): _PASSWORD_SELECTOR,
            vol.Required(
                CONF_POLL_INTERVAL,
                default=defaults.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
        }
    )
