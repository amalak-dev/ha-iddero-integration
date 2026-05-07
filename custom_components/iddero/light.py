"""Light platform for Iddero."""

from __future__ import annotations

from homeassistant.components.light import ColorMode, LightEntity
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
    """Set up Iddero lights."""
    coordinator: IdderoDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        DATA_COORDINATOR
    ]
    async_add_entities(
        IdderoLightEntity(coordinator, point.key)
        for point in coordinator.data.points.values()
        if point.kind == IdderoPointKind.LIGHT
    )


class IdderoLightEntity(IdderoEntity, LightEntity):
    """An Iddero light."""

    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_color_mode = ColorMode.ONOFF

    @property
    def is_on(self) -> bool | None:
        """Return light state."""
        if isinstance(self._optimistic_state, bool):
            return self._optimistic_state
        state = self.point.state
        return state if isinstance(state, bool) else None

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the light on."""
        await self.coordinator.client.async_set_light(self.point, True)
        self._set_optimistic(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the light off."""
        await self.coordinator.client.async_set_light(self.point, False)
        self._set_optimistic(False)

