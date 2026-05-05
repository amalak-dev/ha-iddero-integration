# Iddero for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Validate with hassfest](https://github.com/amalak-dev/ha-iddero-integration/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/amalak-dev/ha-iddero-integration/actions/workflows/hassfest.yaml)
[![HACS Validation](https://github.com/amalak-dev/ha-iddero-integration/actions/workflows/validate.yaml/badge.svg)](https://github.com/amalak-dev/ha-iddero-integration/actions/workflows/validate.yaml)

A Home Assistant custom integration for controlling [Iddero](https://www.iddero.com/) KNX touchpanels via their local web interface.

## When to use this

If you have a KNX/IP interface or router, prefer Home Assistant's built-in KNX integration. This integration is for the fallback case where the Iddero panel is the only reachable control surface and there is no documented API.

The integration reverse-engineers the HTTP requests the Iddero web UI sends and replays them using `aiohttp` — no browser automation required.

## Features

- Control lights (on/off toggle)
- Control blinds/covers (open, close, set position)
- Auto-discovery of devices by crawling zone pages
- Automatic area creation from Iddero zone names
- Per-zone device grouping in Home Assistant
- Configurable polling interval

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Click the three dots in the top right corner → **Custom repositories**
3. Add `https://github.com/amalak-dev/ha-iddero-integration` with category **Integration**
4. Click **Install**
5. Restart Home Assistant

### Manual

Copy the `custom_components/iddero` directory to your Home Assistant `custom_components` folder:

```
<ha-config>/custom_components/iddero/
```

Restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Iddero**
3. Enter your panel's IP address, port, and credentials
4. The integration will auto-discover devices from the panel's zone pages

### Options

| Option | Default | Description |
|--------|---------|-------------|
| Auto-discover | `true` | Scan zone pages when no device map exists |
| Create areas from zones | `true` | Auto-create HA areas matching zone names |
| Device map JSON file | — | Optional path to a pre-built device map |
| Poll interval | 30s | How often to poll the panel for state changes |

## Device Mapping

The integration auto-discovers devices by crawling the panel's zone pages. If you need a custom device map, provide a JSON file:

```json
[
  {
    "key": "living_room_ceiling",
    "name": "Living room ceiling",
    "kind": "light",
    "zone_code": 4,
    "section_code": 0,
    "device_code": 0,
    "zone_name": "Living room"
  }
]
```

Supported `kind` values: `light`, `cover`, `sensor`, `switch`.

## Development

```bash
pip install poetry
poetry install --no-root
poetry run pytest
poetry run ruff check .
```

## License

[MIT](LICENSE)
