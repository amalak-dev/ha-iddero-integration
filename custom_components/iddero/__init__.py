"""The Iddero integration."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Iddero from a config entry."""
    from homeassistant.helpers.aiohttp_client import async_create_clientsession

    from .client import IdderoWebClient
    from .const import (
        CONF_AUTO_DISCOVER,
        CONF_BASE_PATH,
        CONF_DEVICES,
        CONF_DEVICES_FILE,
        CONF_POLL_INTERVAL,
        CONF_USE_SSL,
        CONF_VERIFY_SSL,
        DATA_CLIENT,
        DATA_COORDINATOR,
        DATA_SESSION,
        DEFAULT_AUTO_DISCOVER,
        DEFAULT_BASE_PATH,
        DEFAULT_POLL_INTERVAL,
        DEFAULT_PORT,
        DOMAIN,
        PLATFORMS,
    )
    from .coordinator import IdderoDataUpdateCoordinator
    from .device_map import (
        device_descriptions_from_storage,
        load_device_descriptions_from_file,
    )

    data: dict[str, Any] = entry.data
    options: dict[str, Any] = entry.options
    verify_ssl = data.get(CONF_VERIFY_SSL, True)
    session = async_create_clientsession(hass, verify_ssl=verify_ssl)

    client = IdderoWebClient(
        host=data["host"],
        port=data.get("port", DEFAULT_PORT),
        use_ssl=data.get(CONF_USE_SSL, False),
        verify_ssl=verify_ssl,
        base_path=data.get(CONF_BASE_PATH, DEFAULT_BASE_PATH),
        username=data.get("username"),
        password=data.get("password"),
        session=session,
    )

    devices = []
    devices_file = options.get(CONF_DEVICES_FILE) or data.get(CONF_DEVICES_FILE)
    if devices_file:
        path = Path(devices_file)
        if not path.is_absolute():
            path = Path(hass.config.path(devices_file))
        devices = await hass.async_add_executor_job(
            load_device_descriptions_from_file,
            path,
        )
    else:
        devices = device_descriptions_from_storage(options.get(CONF_DEVICES))

    if not devices and options.get(
        CONF_AUTO_DISCOVER,
        data.get(CONF_AUTO_DISCOVER, DEFAULT_AUTO_DISCOVER),
    ):
        devices = await client.async_discover_devices()
        if devices:
            hass.config_entries.async_update_entry(
                entry,
                options={
                    **entry.options,
                    CONF_DEVICES: [device.as_storage() for device in devices],
                },
            )

    coordinator = IdderoDataUpdateCoordinator(
        hass=hass,
        config_entry=entry,
        client=client,
        devices=devices,
        poll_interval=options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
    )

    await coordinator.async_config_entry_first_refresh()

    from homeassistant.helpers import device_registry as dr

    from .const import MANUFACTURER

    device_reg = dr.async_get(hass)
    device_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer=MANUFACTURER,
        name="Iddero",
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        DATA_CLIENT: client,
        DATA_COORDINATOR: coordinator,
        DATA_SESSION: session,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an Iddero config entry."""
    from .const import DATA_SESSION, DOMAIN, PLATFORMS

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        runtime = hass.data[DOMAIN].pop(entry.entry_id)
        await runtime[DATA_SESSION].close()
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)

    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entry after options change."""
    await hass.config_entries.async_reload(entry.entry_id)
