"""Data update coordinator for Iddero."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import IdderoError, IdderoInvalidAuthError, IdderoWebClient
from .models import IdderoDeviceDescription, IdderoSnapshot

_LOGGER = logging.getLogger(__name__)


class IdderoDataUpdateCoordinator(DataUpdateCoordinator[IdderoSnapshot]):
    """Coordinate Iddero polling."""

    def __init__(
        self,
        *,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: IdderoWebClient,
        devices: list[IdderoDeviceDescription],
        poll_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Iddero",
            config_entry=config_entry,
            update_interval=timedelta(seconds=poll_interval),
            always_update=False,
        )
        self.client = client
        self.devices = devices
        self.devices_by_key: dict[str, IdderoDeviceDescription] = {
            d.key: d for d in devices
        }

    async def _async_update_data(self) -> IdderoSnapshot:
        """Fetch data from the Iddero panel."""
        try:
            if self.devices:
                return await self.client.async_fetch_mapped_snapshot(self.devices)
            return await self.client.async_fetch_snapshot()
        except IdderoInvalidAuthError as err:
            raise ConfigEntryAuthFailed from err
        except IdderoError as err:
            raise UpdateFailed(str(err)) from err
