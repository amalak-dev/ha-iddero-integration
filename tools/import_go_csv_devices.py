"""Convert exported Go service CSV tables into an Iddero device map."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


def convert_csv_devices(
    zones_csv: str | Path,
    devices_csv: str | Path,
) -> list[dict[str, Any]]:
    """Convert exported zones/devices CSV files to Iddero device map dictionaries."""
    zones = _read_zones(Path(zones_csv))
    devices: list[dict[str, Any]] = []
    with Path(devices_csv).open(newline="") as file:
        for row in csv.DictReader(file):
            zone = zones[int(row["zone_id"])]
            kind = "cover" if row["type"] == "blind" else row["type"]
            zone_name = zone["name"]
            alias = row["alias"] or None
            devices.append(
                {
                    "key": alias
                    or _slugify(
                        f"{zone_name}_{row['section_code']}_{row['type']}_{row['device_code']}"
                    ),
                    "name": row["name"],
                    "kind": kind,
                    "zone_code": int(zone["zone_code"]),
                    "section_code": int(row["section_code"]),
                    "device_code": int(row["device_code"]),
                    "zone_name": zone_name,
                    "alias": alias,
                    "legacy_device_id": int(row["device_id"]),
                }
            )
    return devices


def _read_zones(path: Path) -> dict[int, dict[str, str]]:
    with path.open(newline="") as file:
        return {int(row["zone_id"]): row for row in csv.DictReader(file)}


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return slug or "iddero_device"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zones", default="zones.csv", help="Path to zones.csv")
    parser.add_argument("--devices", default="devices.csv", help="Path to devices.csv")
    parser.add_argument("--output", required=True, help="Device map JSON to write")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    devices = convert_csv_devices(args.zones, args.devices)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(devices, indent=2, sort_keys=True))
    print(f"Wrote {len(devices)} devices to {output}")


if __name__ == "__main__":
    main()
