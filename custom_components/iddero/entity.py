"""Shared Iddero entity helpers."""

from __future__ import annotations

from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CREATE_AREAS, DEFAULT_CREATE_AREAS, DOMAIN, MANUFACTURER
from .coordinator import IdderoDataUpdateCoordinator
from .models import IdderoPoint


class IdderoEntity(CoordinatorEntity[IdderoDataUpdateCoordinator]):
    """Base class for Iddero entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: IdderoDataUpdateCoordinator,
        point_key: str,
    ) -> None:
        super().__init__(coordinator, context=point_key)
        self._point_key = point_key
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{point_key}"
        self._optimistic_state: Any = None

    @callback
    def _handle_coordinator_update(self) -> None:
        # Real data has arrived; trust it over the optimistic guess.
        self._optimistic_state = None
        super()._handle_coordinator_update()

    def _set_optimistic(self, state: Any) -> None:
        self._optimistic_state = state
        self.async_write_ha_state()

    @property
    def point(self) -> IdderoPoint:
        """Return the latest point data."""
        return self.coordinator.data.points[self._point_key]

    @property
    def name(self) -> str:
        """Return entity name."""
        return self.point.name

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        entry_id = self.coordinator.config_entry.entry_id
        device_desc = self.coordinator.devices_by_key.get(self._point_key)

        if device_desc and device_desc.zone_name:
            options = self.coordinator.config_entry.options
            create_areas = options.get(CONF_CREATE_AREAS, DEFAULT_CREATE_AREAS)
            info = DeviceInfo(
                identifiers={
                    (DOMAIN, f"{entry_id}_zone_{device_desc.zone_code}")
                },
                manufacturer=MANUFACTURER,
                name=device_desc.zone_name,
                via_device=(DOMAIN, entry_id),
            )
            if create_areas:
                info["suggested_area"] = device_desc.zone_name
            return info

        snapshot = self.coordinator.data
        return DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            manufacturer=MANUFACTURER,
            name=snapshot.device_name,
            model=snapshot.model,
            sw_version=snapshot.firmware,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return safe point attributes."""
        return {
            key: value
            for key, value in self.point.attributes.items()
            if not key.startswith("control_")
        }
