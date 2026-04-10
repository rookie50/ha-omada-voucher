"""Sensor entities for next available voucher codes per group.

Uses api.async_get_group_vouchers() which calls:
  GET /{omadacId}/api/v2/hotspot/sites/{siteId}/voucherGroups/{groupId}/vouchers
with the HOTSPOT session (not the controller session).
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import OmadaVoucherCoordinator

_LOGGER = logging.getLogger(__name__)


class VoucherCodeSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing the Nth next free voucher code for a specific group."""

    _attr_icon = "mdi:ticket-confirmation-outline"

    def __init__(
        self,
        coordinator: OmadaVoucherCoordinator,
        group_id: str,
        group_name: str,
        slot: int,
    ) -> None:
        super().__init__(coordinator)
        self._group_id = group_id
        self._group_name = group_name
        self._slot = slot
        self._code: str = ""
        self._attr_unique_id = f"omada_voucher_code_{group_id}_slot{slot}"
        self._attr_name = f"Voucher {group_name} Code {slot}"

    @property
    def native_value(self) -> str:
        return self._code or "–"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "group_id": self._group_id,
            "group_name": self._group_name,
            "slot": self._slot,
            "has_code": bool(self._code),
        }

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    async def async_update_code(self) -> None:
        """Fetch voucher codes using the hotspot API session."""
        try:
            vouchers = await self.coordinator.api.async_get_group_vouchers(
                self._group_id, page_size=10
            )
            _LOGGER.debug(
                "Group '%s': got %d vouchers, fields: %s",
                self._group_name, len(vouchers),
                list(vouchers[0].keys()) if vouchers else []
            )
            # Extract unused codes
            codes = []
            for v in vouchers:
                is_used = v.get("used", False)
                if isinstance(is_used, str):
                    is_used = is_used.lower() in ("true", "1", "yes")
                code = v.get("code", "")
                if not is_used and code:
                    codes.append(code)
                if len(codes) >= 2:
                    break

            idx = self._slot - 1
            new_code = codes[idx] if idx < len(codes) else ""

            if new_code != self._code:
                _LOGGER.debug(
                    "Group '%s' slot %d: %s → %s",
                    self._group_name, self._slot,
                    self._code or "–", new_code or "–",
                )
                self._code = new_code
                self.async_write_ha_state()

        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning(
                "Failed to fetch codes for group '%s' slot %d: %s",
                self._group_name, self._slot, err
            )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self.async_update_code()

    def _handle_coordinator_update(self) -> None:
        self.hass.async_create_task(self.async_update_code())
