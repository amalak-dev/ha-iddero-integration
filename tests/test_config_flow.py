from collections.abc import Sequence
from unittest.mock import patch

import pytest
from custom_components.iddero.client import IdderoInvalidAuthError
from custom_components.iddero.const import CONF_AUTO_DISCOVER, CONF_DEVICES, DOMAIN
from custom_components.iddero.models import (
    IdderoDeviceDescription,
    IdderoPoint,
    IdderoPointKind,
    IdderoSnapshot,
)
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

CEILING = IdderoDeviceDescription(
    key="zone_1_0_light_0",
    name="Teto",
    kind=IdderoPointKind.LIGHT,
    zone_code=1,
    section_code=0,
    device_code=0,
    zone_name="Zone",
)
ENTRY_DATA = {
    "host": "192.0.2.10",
    "port": 80,
    "use_ssl": False,
    "verify_ssl": True,
    "base_path": "/",
    "username": "user",
    "password": "old-pass",
}


class FakePanelClient:
    """Stand-in for IdderoWebClient that accepts one set of credentials."""

    valid = ("user", "new-pass")

    def __init__(self, *, username: str | None, password: str | None, **_: object):
        self.credentials = (username, password)

    def _check_auth(self) -> None:
        if self.credentials != self.valid:
            raise IdderoInvalidAuthError("rejected")

    async def async_probe(self) -> None:
        self._check_auth()

    async def async_discover_devices(self) -> list[IdderoDeviceDescription]:
        self._check_auth()
        return [CEILING]

    async def async_fetch_mapped_snapshot(
        self, devices: Sequence[IdderoDeviceDescription]
    ) -> IdderoSnapshot:
        self._check_auth()
        return IdderoSnapshot(
            device_name="Iddero",
            model=None,
            firmware=None,
            points={
                device.key: IdderoPoint(
                    key=device.key,
                    name=device.name,
                    kind=device.kind,
                    state=False,
                    attributes={
                        "alias": None,
                        "zone_name": device.zone_name,
                        "zone_code": device.zone_code,
                        "section_code": device.section_code,
                        "device_code": device.device_code,
                    },
                )
                for device in devices
            },
        )


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    return None


@pytest.fixture(autouse=True)
def fake_panel_client():
    with (
        patch("custom_components.iddero.client.IdderoWebClient", FakePanelClient),
        patch("custom_components.iddero.config_flow.IdderoWebClient", FakePanelClient),
    ):
        yield


def _entry(options: dict) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.0.2.10:80",
        data=dict(ENTRY_DATA),
        options=options,
    )


async def test_rejected_credentials_during_discovery_start_reauth(
    hass: HomeAssistant,
) -> None:
    entry = _entry({CONF_AUTO_DISCOVER: True})
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]


async def test_reauth_with_new_password_updates_entry_and_reloads(
    hass: HomeAssistant,
) -> None:
    entry = _entry({CONF_AUTO_DISCOVER: False, CONF_DEVICES: [CEILING.as_storage()]})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR

    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": "user", "password": "new-pass"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data == {**ENTRY_DATA, "password": "new-pass"}
    assert entry.state is ConfigEntryState.LOADED


async def test_reauth_with_wrong_password_shows_error(hass: HomeAssistant) -> None:
    entry = _entry({CONF_AUTO_DISCOVER: False, CONF_DEVICES: [CEILING.as_storage()]})
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": "user", "password": "still-wrong"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data["password"] == "old-pass"
