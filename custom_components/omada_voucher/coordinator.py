"""DataUpdateCoordinator for Omada Voucher groups."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import OmadaApiError, OmadaVoucherApi

_LOGGER = logging.getLogger(__name__)


class OmadaVoucherCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that fetches all voucher groups periodically."""

    def __init__(self, hass: HomeAssistant, api: OmadaVoucherApi, scan_interval: int) -> None:
        super().__init__(
            hass, _LOGGER,
            name="Omada Voucher Groups",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            groups = await self.api.async_get_voucher_groups()
        except OmadaApiError as err:
            raise UpdateFailed(f"Omada API error: {err}") from err

        result = {}
        for g in groups:
            # Confirmed field name: "id" (from raw_fields logging)
            group_id = g.get("id", "")
            if group_id:
                result[group_id] = g
                _LOGGER.debug(
                    "Group '%s' (id=%s): unused=%s used=%s total=%s",
                    g.get("name"), group_id[:8],
                    g.get("unusedCount"), g.get("usedCount"), g.get("totalCount"),
                )
            else:
                _LOGGER.warning("Voucher group missing 'id' field: %s", list(g.keys()))

        return result
