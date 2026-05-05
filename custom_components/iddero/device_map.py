"""Helpers for persisted Iddero device mappings."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import IdderoDeviceDescription, IdderoPointKind


def device_descriptions_from_storage(
    raw_devices: list[dict[str, Any]] | None,
) -> list[IdderoDeviceDescription]:
    """Load persisted device descriptions from config entry data/options."""
    if not raw_devices:
        return []
    return [IdderoDeviceDescription.from_storage(raw) for raw in raw_devices]


def load_device_descriptions_from_file(
    path: str | Path,
) -> list[IdderoDeviceDescription]:
    """Load device descriptions from a JSON file."""
    raw = json.loads(Path(path).read_text())
    if not isinstance(raw, list):
        raise ValueError("Device map file must contain a JSON array")
    return device_descriptions_from_storage(raw)


def make_discovered_device_description(
    *,
    zone_code: int,
    section_code: int,
    device_code: int,
    kind: IdderoPointKind,
    name: str | None = None,
    zone_name: str | None = None,
) -> IdderoDeviceDescription:
    """Create a stable description for a device discovered from a zone page."""
    fallback_type = "blind" if kind == IdderoPointKind.COVER else kind.value
    fallback_name = f"Zone {zone_code} {fallback_type} {device_code}"
    resolved_name = _clean_name(name) or fallback_name
    key_parts = [
        zone_name or "zone",
        str(zone_code),
        str(section_code),
        fallback_type,
        str(device_code),
    ]
    key = _slugify("_".join(key_parts))
    return IdderoDeviceDescription(
        key=key,
        name=resolved_name,
        kind=kind,
        zone_code=zone_code,
        section_code=section_code,
        device_code=device_code,
        zone_name=zone_name,
    )


def _clean_name(name: str | None) -> str | None:
    if name is None:
        return None
    cleaned = " ".join(name.split())
    return cleaned or None


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return slug or "iddero_device"
