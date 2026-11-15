import asyncio
from collections.abc import Callable, Sequence
from datetime import timedelta
from unittest.mock import patch

import pytest
from custom_components.iddero.const import CONF_AUTO_DISCOVER, CONF_DEVICES, DOMAIN
from custom_components.iddero.models import (
    IdderoDeviceDescription,
    IdderoPoint,
    IdderoPointKind,
    IdderoSnapshot,
)
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

CEILING = IdderoDeviceDescription(
    key="zone_1_0_light_0",
    name="Teto",
    kind=IdderoPointKind.LIGHT,
    zone_code=1,
    section_code=0,
    device_code=0,
    zone_name="Zone",
)


class FakeClient:
    """Stand-in for IdderoWebClient whose polls can be held open."""

    def __init__(self, **_kwargs: object) -> None:
        self.light_on = False
        self.fetch_calls = 0
        self.gates: list[asyncio.Event] = []

    async def async_fetch_mapped_snapshot(
        self, devices: Sequence[IdderoDeviceDescription]
    ) -> IdderoSnapshot:
        self.fetch_calls += 1
        state = self.light_on  # what the panel showed when the poll started
        if self.gates:
            await self.gates.pop(0).wait()
        return IdderoSnapshot(
            device_name="Iddero",
            model=None,
            firmware=None,
            points={
                device.key: IdderoPoint(
                    key=device.key,
                    name=device.name,
                    kind=device.kind,
                    state=state,
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

    async def async_set_light(self, point: IdderoPoint, is_on: bool) -> None:
        self.light_on = is_on


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    return None


@pytest.fixture
async def setup(hass: HomeAssistant) -> tuple[FakeClient, str, object]:
    fake = FakeClient()
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": "192.0.2.10",
            "port": 80,
            "use_ssl": False,
            "verify_ssl": True,
            "base_path": "/",
            "username": "user",
            "password": "pass",
        },
        options={CONF_AUTO_DISCOVER: False, CONF_DEVICES: [CEILING.as_storage()]},
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.iddero.client.IdderoWebClient",
        return_value=fake,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    entity_id = er.async_get(hass).async_get_entity_id(
        "light", DOMAIN, f"{entry.entry_id}_{CEILING.key}"
    )
    assert entity_id is not None
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    return fake, entity_id, coordinator


async def _wait_for(condition: Callable[[], bool]) -> None:
    for _ in range(200):
        if condition():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition not reached")


async def test_turn_on_refreshes_from_panel(
    hass: HomeAssistant, setup: tuple[FakeClient, str, object]
) -> None:
    fake, entity_id, _coordinator = setup
    fetches_before = fake.fetch_calls

    await hass.services.async_call(
        "light", "turn_on", {"entity_id": entity_id}, blocking=True
    )
    await hass.async_block_till_done()

    assert fake.fetch_calls == fetches_before + 1
    assert hass.states.get(entity_id).state == STATE_ON


async def test_poll_started_before_command_does_not_revert_state(
    hass: HomeAssistant, setup: tuple[FakeClient, str, object]
) -> None:
    fake, entity_id, coordinator = setup
    stale_gate = asyncio.Event()
    fake.gates = [stale_gate]
    fetches_before = fake.fetch_calls

    # A scheduled poll starts while the light is still off...
    stale_poll = hass.async_create_task(coordinator.async_refresh())
    await _wait_for(lambda: fake.fetch_calls == fetches_before + 1)

    # ...then the user turns the light on before that poll answers. With a
    # poll in flight, Home Assistant defers the requested refresh by its
    # cooldown instead of running it right away.
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": entity_id}, blocking=True
    )
    assert hass.states.get(entity_id).state == STATE_ON

    # The stale poll lands with "off"; the UI must not flip back.
    stale_gate.set()
    await stale_poll
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_ON

    # The deferred refresh then confirms the new state.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
    await hass.async_block_till_done()
    assert fake.fetch_calls == fetches_before + 2
    assert hass.states.get(entity_id).state == STATE_ON


async def test_fresh_poll_replaces_optimistic_state(
    hass: HomeAssistant, setup: tuple[FakeClient, str, object]
) -> None:
    fake, entity_id, coordinator = setup
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": entity_id}, blocking=True
    )
    await hass.async_block_till_done()

    # Someone switches it off at the wall panel; the next poll must show it.
    fake.light_on = False
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_OFF
