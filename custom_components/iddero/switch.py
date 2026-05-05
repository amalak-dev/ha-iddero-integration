"""Switch platform for Iddero."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
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
    """Set up Iddero switches."""
    coordinator: IdderoDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        DATA_COORDINATOR
    ]
    async_add_entities(
        IdderoSwitchEntity(coordinator, point.key)
        for point in coordinator.data.points.values()
        if point.kind == IdderoPointKind.SWITCH
    )


class IdderoSwitchEntity(IdderoEntity, SwitchEntity):
    """An Iddero switch."""

    @property
    def is_on(self) -> bool | None:
        """Return switch state."""
        state = self.point.state
        return state if isinstance(state, bool) else None

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        await self.coordinator.client.async_set_switch(self.point, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off."""
        await self.coordinator.client.async_set_switch(self.point, False)
        await self.coordinator.async_request_refresh()

