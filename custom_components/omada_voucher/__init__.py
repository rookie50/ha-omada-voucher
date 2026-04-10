"""Omada Hotspot Voucher Integration – v2.5."""
from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .api import OmadaVoucherApi
from .const import (
    ATTR_CODE_FORMAT, ATTR_CODE_LENGTH, ATTR_COUNT,
    ATTR_EXPIRE_END, ATTR_EXPIRE_START, ATTR_GROUP_ID,
    ATTR_GROUP_NAME, ATTR_TYPE, ATTR_TYPE_VALUE,
    CONF_HOST, CONF_HOTSPOT_PASSWORD, CONF_HOTSPOT_USERNAME,
    CONF_OMADAC_ID, CONF_PASSWORD, CONF_SCAN_INTERVAL,
    CONF_SITE_ID, CONF_SITE_NAME, CONF_USERNAME, CONF_VERIFY_SSL,
    DATA_COORDINATOR, DEFAULT_SCAN_INTERVAL, DEFAULT_VERIFY_SSL,
    DOMAIN, SERVICE_CREATE_VOUCHERS, SERVICE_DELETE_GROUP,
    SERVICE_RELOAD_CODES, SERVICE_REPLENISH_GROUP,
)
from .coordinator import OmadaVoucherCoordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor"]

CREATE_VOUCHERS_SCHEMA = vol.Schema({
    vol.Required(ATTR_GROUP_NAME): cv.string,
    vol.Optional(ATTR_COUNT, default=10): vol.All(int, vol.Range(min=1, max=5000)),
    vol.Optional(ATTR_CODE_LENGTH, default=6): vol.All(int, vol.Range(min=6, max=10)),
    vol.Optional(ATTR_CODE_FORMAT, default=["NUM"]): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(ATTR_TYPE, default=0): vol.In([0, 1, 2]),
    vol.Optional(ATTR_TYPE_VALUE, default=1): vol.All(int, vol.Range(min=1, max=999)),
    vol.Optional(ATTR_EXPIRE_START): cv.string,
    vol.Optional(ATTR_EXPIRE_END): cv.string,
})
DELETE_GROUP_SCHEMA = vol.Schema({vol.Required(ATTR_GROUP_ID): cv.string})
REPLENISH_GROUP_SCHEMA = vol.Schema({
    vol.Required(ATTR_GROUP_ID): cv.string,
    vol.Required(ATTR_COUNT): vol.All(int, vol.Range(min=1, max=5000)),
})
RELOAD_CODES_SCHEMA = vol.Schema({})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    hotspot_user = entry.data.get(CONF_HOTSPOT_USERNAME, "").strip() or None
    hotspot_pass = entry.data.get(CONF_HOTSPOT_PASSWORD, "").strip() or None

    api = OmadaVoucherApi(
        host=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        site_name=entry.data[CONF_SITE_NAME],
        verify_ssl=entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
        omadac_id=entry.data.get(CONF_OMADAC_ID),
        site_id=entry.data.get(CONF_SITE_ID),
        hotspot_username=hotspot_user,
        hotspot_password=hotspot_pass,
    )

    try:
        await api.login()
    except Exception as err:
        _LOGGER.error("Controller login failed: %s", err)
        return False

    # Hotspot login – optional, don't fail if it doesn't work
    try:
        await api._hotspot_login()
    except Exception as err:
        _LOGGER.error("Hotspot login FAILED - codes will show as dash. Error: %s", err)

    coordinator = OmadaVoucherCoordinator(
        hass, api,
        scan_interval=entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {DATA_COORDINATOR: coordinator, "api": api}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def handle_create_vouchers(call: ServiceCall) -> None:
        await api.async_create_voucher_group(
            name=call.data[ATTR_GROUP_NAME],
            count=call.data.get(ATTR_COUNT, 10),
            code_length=call.data.get(ATTR_CODE_LENGTH, 6),
            code_format=call.data.get(ATTR_CODE_FORMAT, ["NUM"]),
            type_=call.data.get(ATTR_TYPE, 0),
            type_value=call.data.get(ATTR_TYPE_VALUE, 1),
            expire_start=call.data.get(ATTR_EXPIRE_START),
            expire_end=call.data.get(ATTR_EXPIRE_END),
        )
        await coordinator.async_request_refresh()

    async def handle_delete_group(call: ServiceCall) -> None:
        await api.async_delete_voucher_group(call.data[ATTR_GROUP_ID])
        await coordinator.async_request_refresh()

    async def handle_replenish_group(call: ServiceCall) -> None:
        await api.async_replenish_voucher_group(call.data[ATTR_GROUP_ID], call.data[ATTR_COUNT])
        await coordinator.async_request_refresh()

    async def handle_reload_codes(call: ServiceCall) -> None:
        await coordinator.async_request_refresh()
        _LOGGER.info("Voucher codes refreshed")

    if not hass.services.has_service(DOMAIN, SERVICE_CREATE_VOUCHERS):
        hass.services.async_register(DOMAIN, SERVICE_CREATE_VOUCHERS, handle_create_vouchers, schema=CREATE_VOUCHERS_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_DELETE_GROUP, handle_delete_group, schema=DELETE_GROUP_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_REPLENISH_GROUP, handle_replenish_group, schema=REPLENISH_GROUP_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_RELOAD_CODES, handle_reload_codes, schema=RELOAD_CODES_SCHEMA)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["api"].close()
        if not hass.data[DOMAIN]:
            for svc in [SERVICE_CREATE_VOUCHERS, SERVICE_DELETE_GROUP, SERVICE_REPLENISH_GROUP, SERVICE_RELOAD_CODES]:
                hass.services.async_remove(DOMAIN, svc)
    return unload_ok
