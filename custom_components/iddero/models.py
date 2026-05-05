"""Models for normalized Iddero page data."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class IdderoPointKind(StrEnum):
    """Supported normalized point types."""

    COVER = "cover"
    LIGHT = "light"
    SENSOR = "sensor"
    SWITCH = "switch"


@dataclass(frozen=True, slots=True)
class IdderoDeviceDescription:
    """A controllable device location in the Iddero web UI."""

    key: str
    name: str
    kind: IdderoPointKind
    zone_code: int
    section_code: int
    device_code: int
    zone_name: str | None = None
    alias: str | None = None

    @classmethod
    def from_storage(cls, raw: Mapping[str, Any]) -> IdderoDeviceDescription:
        """Create a device description from persisted JSON data."""
        return cls(
            key=str(raw["key"]),
            name=str(raw["name"]),
            kind=IdderoPointKind(str(raw["kind"])),
            zone_code=int(raw["zone_code"]),
            section_code=int(raw["section_code"]),
            device_code=int(raw["device_code"]),
            zone_name=str(raw["zone_name"]) if raw.get("zone_name") else None,
            alias=str(raw["alias"]) if raw.get("alias") else None,
        )

    def as_storage(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "key": self.key,
            "name": self.name,
            "kind": self.kind.value,
            "zone_code": self.zone_code,
            "section_code": self.section_code,
            "device_code": self.device_code,
            "zone_name": self.zone_name,
            "alias": self.alias,
        }


@dataclass(frozen=True, slots=True)
class IdderoZoneDescription:
    """A zone listed by the Iddero panel."""

    zone_code: int
    name: str | None = None


@dataclass(frozen=True, slots=True)
class IdderoPoint:
    """A single value or controllable point exposed by the Iddero page."""

    key: str
    name: str
    kind: IdderoPointKind
    state: bool | int | float | str | None
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IdderoSnapshot:
    """A normalized snapshot of the whole panel."""

    device_name: str
    model: str | None
    firmware: str | None
    points: Mapping[str, IdderoPoint]
