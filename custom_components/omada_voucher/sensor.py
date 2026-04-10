"""Sensor platform for Omada Voucher groups + free code sensors."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import OmadaVoucherCoordinator
from .voucher_code_sensor import VoucherCodeSensor

_LOGGER = logging.getLogger(__name__)

# Confirmed field names from Omada API (discovered via raw_fields logging)
FIELD_ID = "id"
FIELD_NAME = "name"
FIELD_UNUSED = "unusedCount"   # ← remaining/free vouchers
FIELD_USED = "usedCount"       # ← used vouchers
FIELD_TOTAL = "totalCount"     # ← total vouchers


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OmadaVoucherCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    group_sensors = [
        OmadaVoucherGroupSensor(coordinator, group_id)
        for group_id in coordinator.data
    ]
    code_sensors = []
    for group_id, group_data in coordinator.data.items():
        group_name = group_data.get(FIELD_NAME, group_id)
        for slot in (1, 2):
            code_sensors.append(VoucherCodeSensor(coordinator, group_id, group_name, slot))

    async_add_entities(group_sensors + code_sensors, update_before_add=True)

    def _handle_coordinator_update() -> None:
        existing_ids = {e._group_id for e in group_sensors}
        new_entities = []
        for gid in coordinator.data:
            if gid not in existing_ids:
                new_entities.append(OmadaVoucherGroupSensor(coordinator, gid))
                gname = coordinator.data[gid].get(FIELD_NAME, gid)
                for slot in (1, 2):
                    new_entities.append(VoucherCodeSensor(coordinator, gid, gname, slot))
                existing_ids.add(gid)
        if new_entities:
            group_sensors.extend(e for e in new_entities if isinstance(e, OmadaVoucherGroupSensor))
            async_add_entities(new_entities)

    coordinator.async_add_listener(_handle_coordinator_update)


class OmadaVoucherGroupSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing remaining (unused) vouchers in a group."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "Voucher"
    _attr_icon = "mdi:ticket-confirmation"

    def __init__(self, coordinator: OmadaVoucherCoordinator, group_id: str) -> None:
        super().__init__(coordinator)
        self._group_id = group_id
        self._attr_unique_id = f"omada_voucher_{group_id}"

    @property
    def _group(self) -> dict[str, Any]:
        return self.coordinator.data.get(self._group_id, {})

    @property
    def name(self) -> str:
        return f"Voucher {self._group.get(FIELD_NAME, self._group_id)}"

    @property
    def native_value(self) -> int:
        # unusedCount is the correct field for remaining free vouchers
        return int(self._group.get(FIELD_UNUSED, 0) or 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        g = self._group
        return {
            "group_id": self._group_id,
            "group_name": g.get(FIELD_NAME),
            "total_vouchers": int(g.get(FIELD_TOTAL, 0) or 0),
            "used_vouchers": int(g.get(FIELD_USED, 0) or 0),
            "remaining_vouchers": int(g.get(FIELD_UNUSED, 0) or 0),
            "expire_start": g.get("effectiveTime"),
            "expire_end": g.get("expirationTime"),
            "duration": g.get("duration"),
            "duration_type": g.get("durationType"),
            "type": g.get("type"),
            "max_users": g.get("maxUsers"),
            "created_time": g.get("createdTime"),
        }

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._group_id in self.coordinator.data
