"""Cover platform for Iddero blinds."""

from __future__ import annotations

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverEntity,
    CoverEntityFeature,
)
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
    """Set up Iddero covers."""
    coordinator: IdderoDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        DATA_COORDINATOR
    ]
    async_add_entities(
        IdderoCoverEntity(coordinator, point.key)
        for point in coordinator.data.points.values()
        if point.kind == IdderoPointKind.COVER
    )


class IdderoCoverEntity(IdderoEntity, CoverEntity):
    """An Iddero blind.

    Iddero reports 0 as open and 100 as closed. Home Assistant uses 100 as open
    and 0 as closed, so positions are inverted at the entity boundary.
    """

    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    @property
    def current_cover_position(self) -> int | None:
        """Return Home Assistant cover position."""
        raw_position = _raw_position(self.point.state)
        if raw_position is None:
            return None
        return 100 - raw_position

    @property
    def is_closed(self) -> bool | None:
        """Return whether the blind is closed."""
        raw_position = _raw_position(self.point.state)
        if raw_position is None:
            return None
        return raw_position >= 100

    async def async_open_cover(self, **kwargs) -> None:
        """Open the blind."""
        await self.coordinator.client.async_open_cover(self.point)
        await self.coordinator.async_request_refresh()

    async def async_close_cover(self, **kwargs) -> None:
        """Close the blind."""
        await self.coordinator.client.async_close_cover(self.point)
        await self.coordinator.async_request_refresh()

    async def async_stop_cover(self, **kwargs) -> None:
        """Stop the blind."""
        await self.coordinator.client.async_stop_cover(self.point)
        await self.coordinator.async_request_refresh()

    async def async_set_cover_position(self, **kwargs) -> None:
        """Set blind position."""
        ha_position = int(kwargs[ATTR_POSITION])
        iddero_position = 100 - ha_position
        await self.coordinator.client.async_set_cover_position(
            self.point,
            iddero_position,
        )
        await self.coordinator.async_request_refresh()


def _raw_position(state: bool | int | float | str | None) -> int | None:
    if isinstance(state, bool) or state is None:
        return None
    if isinstance(state, int | float):
        return max(0, min(100, int(state)))
    try:
        return max(0, min(100, int(state)))
    except ValueError:
        return None
