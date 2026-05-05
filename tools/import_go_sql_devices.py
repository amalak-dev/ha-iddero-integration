"""Convert the old Go service PostgreSQL inserts into an Iddero device map."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

ZONE_RE = re.compile(r"INSERT INTO public\.zones VALUES \((?P<values>.*?)\);")
DEVICE_RE = re.compile(
    r'INSERT INTO public\.devices .*?VALUES \((?P<values>.*?)\);',
    re.DOTALL,
)


def convert_sql_devices(sql_text: str) -> list[dict[str, Any]]:
    """Convert old SQL insert backup text to Iddero device map dictionaries."""
    zones = _parse_zones(sql_text)
    devices: list[dict[str, Any]] = []
    for match in DEVICE_RE.finditer(sql_text):
        values = _split_sql_values(match.group("values"))
        if len(values) < 9:
            continue
        device_id = int(values[0])
        device_type = values[3]
        name = values[4]
        device_code = int(values[5])
        section_code = int(values[6])
        zone_id = int(values[7])
        alias = values[8]
        zone = zones.get(zone_id, {})
        kind = "cover" if device_type == "blind" else device_type
        zone_name = zone.get("name")
        devices.append(
            {
                "key": alias
                or _slugify(
                    f"{zone_name or 'zone'}_{zone_id}_{device_type}_{device_code}"
                ),
                "name": name,
                "kind": kind,
                "zone_code": int(zone.get("zone_code", zone_id)),
                "section_code": section_code,
                "device_code": device_code,
                "zone_name": zone_name,
                "alias": alias or None,
                "legacy_device_id": device_id,
            }
        )

    return devices


def _parse_zones(sql_text: str) -> dict[int, dict[str, Any]]:
    zones: dict[int, dict[str, Any]] = {}
    for match in ZONE_RE.finditer(sql_text):
        values = _split_sql_values(match.group("values"))
        if len(values) < 4:
            continue
        zone_id = int(values[0])
        zones[zone_id] = {
            "zone_code": int(values[1]),
            "name": values[2],
            "alias": values[3] or None,
        }
    return zones


def _split_sql_values(raw_values: str) -> list[str]:
    row = next(
        csv.reader(
            [raw_values],
            delimiter=",",
            quotechar="'",
            skipinitialspace=True,
        )
    )
    return [value.strip() for value in row]


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return slug or "iddero_device"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("sql_file", help="Path to insertsbackup.sql")
    parser.add_argument("--output", required=True, help="Device map JSON to write")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    devices = convert_sql_devices(Path(args.sql_file).read_text())
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(devices, indent=2, sort_keys=True))
    print(f"Wrote {len(devices)} devices to {output}")


if __name__ == "__main__":
    main()
