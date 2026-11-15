import asyncio
from collections.abc import AsyncIterator

import aiohttp
import pytest
import pytest_asyncio
from custom_components.iddero import client as client_module
from custom_components.iddero.client import IdderoWebClient
from custom_components.iddero.models import (
    IdderoDeviceDescription,
    IdderoPoint,
    IdderoPointKind,
)
from tests.fake_panel import FakePanel

CEILING = IdderoDeviceDescription(
    key="zone_1_0_light_0",
    name="Teto",
    kind=IdderoPointKind.LIGHT,
    zone_code=1,
    section_code=0,
    device_code=0,
    zone_name="Zone",
)
CORNICE = IdderoDeviceDescription(
    key="zone_1_0_light_1",
    name="Sanca",
    kind=IdderoPointKind.LIGHT,
    zone_code=1,
    section_code=0,
    device_code=1,
    zone_name="Zone",
)


@pytest.fixture(autouse=True)
def no_settle_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "COMMAND_SETTLE_DELAY", 0)


@pytest_asyncio.fixture
async def panel(socket_enabled: None) -> AsyncIterator[FakePanel]:
    fake = FakePanel()
    await fake.start()
    yield fake
    await fake.close()


@pytest_asyncio.fixture
async def client(panel: FakePanel) -> AsyncIterator[IdderoWebClient]:
    assert panel.server is not None
    async with aiohttp.ClientSession() as session:
        web_client = IdderoWebClient(
            host="127.0.0.1",
            port=panel.server.port,
            use_ssl=False,
            verify_ssl=True,
            base_path="/",
            username=panel.username,
            password=panel.password,
            session=session,
        )
        # Integration setup polls before any command, so start logged in.
        await web_client.async_login()
        yield web_client


def _light_point(device: IdderoDeviceDescription, state: bool | None) -> IdderoPoint:
    return IdderoPoint(
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


async def test_turn_on_twice_with_stale_state_toggles_once(
    panel: FakePanel, client: IdderoWebClient
) -> None:
    stale_point = _light_point(CEILING, False)

    await client.async_set_light(stale_point, True)
    await client.async_set_light(stale_point, True)

    assert panel.lights[0] is True
    assert panel.click_count == 1


async def test_concurrent_turn_on_toggles_once(
    panel: FakePanel, client: IdderoWebClient
) -> None:
    stale_point = _light_point(CEILING, False)

    await asyncio.gather(
        client.async_set_light(stale_point, True),
        client.async_set_light(stale_point, True),
    )

    assert panel.lights[0] is True
    assert panel.click_count == 1


async def test_turn_on_with_unknown_state_does_not_switch_off_lit_light(
    panel: FakePanel, client: IdderoWebClient
) -> None:
    panel.lights[0] = True

    await client.async_set_light(_light_point(CEILING, None), True)

    assert panel.lights[0] is True
    assert panel.click_count == 0


async def test_snapshot_recovers_after_panel_session_expires(
    panel: FakePanel, client: IdderoWebClient
) -> None:
    panel.lights[1] = True
    first = await client.async_fetch_mapped_snapshot([CEILING, CORNICE])
    assert first.points[CORNICE.key].state is True

    panel.expire_sessions()
    second = await client.async_fetch_mapped_snapshot([CEILING, CORNICE])

    assert second.points[CEILING.key].state is False
    assert second.points[CORNICE.key].state is True
    assert panel.login_count == 2


async def test_command_recovers_after_panel_session_expires(
    panel: FakePanel, client: IdderoWebClient
) -> None:
    await client.async_fetch_mapped_snapshot([CEILING])

    panel.expire_sessions()
    await client.async_set_light(_light_point(CEILING, False), True)

    assert panel.lights[0] is True
    assert panel.login_count == 2
