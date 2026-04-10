"""Config flow for Omada Hotspot Voucher – v2.5."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .api import OmadaApiError, OmadaAuthError, OmadaSiteNotFoundError, OmadaVoucherApi
from .const import (
    CONF_HOST, CONF_HOTSPOT_PASSWORD, CONF_HOTSPOT_USERNAME,
    CONF_OMADAC_ID, CONF_PASSWORD, CONF_SCAN_INTERVAL,
    CONF_SITE_ID, CONF_SITE_NAME, CONF_USERNAME, CONF_VERIFY_SSL,
    DEFAULT_SCAN_INTERVAL, DEFAULT_VERIFY_SSL, DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema({
    vol.Required(CONF_HOST): str,
    vol.Required(CONF_USERNAME): str,
    vol.Required(CONF_PASSWORD): str,
    vol.Required(CONF_SITE_NAME): str,
    vol.Optional(CONF_HOTSPOT_USERNAME, default=""): str,
    vol.Optional(CONF_HOTSPOT_PASSWORD, default=""): str,
    vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): bool,
    vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
        int, vol.Range(min=60, max=3600)
    ),
})


async def _validate_and_discover(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    hotspot_user = data.get(CONF_HOTSPOT_USERNAME, "").strip() or None
    hotspot_pass = data.get(CONF_HOTSPOT_PASSWORD, "").strip() or None

    api = OmadaVoucherApi(
        host=data[CONF_HOST],
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        site_name=data[CONF_SITE_NAME],
        verify_ssl=data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
        hotspot_username=hotspot_user,
        hotspot_password=hotspot_pass,
    )
    try:
        discovered = await api.async_setup()
        return {
            **data,
            CONF_OMADAC_ID: discovered["omadac_id"],
            CONF_SITE_ID: discovered["site_id"],
        }
    except OmadaAuthError as err:
        _LOGGER.error("Auth failed: %s", err)
        raise
    except OmadaSiteNotFoundError as err:
        _LOGGER.error("Site not found: %s", err)
        raise
    except OmadaApiError as err:
        _LOGGER.error("API error: %s", err)
        raise
    except Exception as err:
        _LOGGER.exception("Unexpected error: %s", err)
        raise
    finally:
        await api.close()


class OmadaVoucherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                full_config = await _validate_and_discover(self.hass, user_input)
            except OmadaAuthError:
                errors["base"] = "invalid_auth"
            except OmadaSiteNotFoundError:
                errors[CONF_SITE_NAME] = "site_not_found"
            except OmadaApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                omadac_id = full_config[CONF_OMADAC_ID]
                site_id = full_config[CONF_SITE_ID]
                await self.async_set_unique_id(f"{omadac_id}_{site_id}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Omada – {user_input[CONF_SITE_NAME]}",
                    data=full_config,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )
