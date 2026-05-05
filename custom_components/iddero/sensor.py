"""Sensor platform for Iddero."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import IdderoDataUpdateCoordinator
from .entity import IdderoEntity
from .models import IdderoPointKind


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Iddero sensors."""
    coordinator: IdderoDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        DATA_COORDINATOR
    ]
    async_add_entities(
        IdderoSensorEntity(coordinator, point.key)
        for point in coordinator.data.points.values()
        if point.kind == IdderoPointKind.SENSOR
    )


class IdderoSensorEntity(IdderoEntity, SensorEntity):
    """An Iddero sensor."""

    @property
    def native_value(self):
        """Return native value."""
        return self.point.state

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return native unit."""
        return self.point.unit

    @property
    def device_class(self) -> str | None:
        """Return device class."""
        return self.point.device_class

    @property
    def state_class(self) -> str | None:
        """Return state class."""
        return self.point.state_class

