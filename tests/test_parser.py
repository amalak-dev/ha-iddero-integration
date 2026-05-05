from pathlib import Path

from custom_components.iddero.models import IdderoPointKind
from custom_components.iddero.parser import (
    parse_discovered_devices,
    parse_login_form,
    parse_snapshot,
    parse_zone_statuses,
    parse_zones,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_snapshot_from_iddero_data_attributes() -> None:
    snapshot = parse_snapshot((FIXTURES / "status.html").read_text())

    assert snapshot.device_name == "Ground Floor Panel"
    assert snapshot.model == "HC3-KNX"
    assert snapshot.firmware == "5.0"
    assert snapshot.points["living_temperature"].state == 21.4
    assert snapshot.points["living_temperature"].unit == "C"
    assert snapshot.points["living_temperature"].kind == IdderoPointKind.SENSOR
    assert snapshot.points["living_light"].state is True
    assert snapshot.points["living_light"].attributes["control_path"] == "/widgets/set"


def test_parse_login_form() -> None:
    html = """
    <form method="post" action="/login">
      <input type="hidden" name="csrf" value="token">
      <input type="text" name="user">
      <input type="password" name="pass">
    </form>
    """

    form = parse_login_form(html, "http://iddero.local/")

    assert form is not None
    assert form.action == "http://iddero.local/login"
    assert form.method == "POST"
    assert form.fields["csrf"] == "token"
    assert form.username_field == "user"
    assert form.password_field == "pass"


def test_parse_zone_statuses_uses_go_iddero_shape() -> None:
    html = """
    <table>
      <tr>
        <td id="status0"><a><img src="/img/light_on.png"></a></td>
        <td id="status1"><a><img src="/img/light_off.png"></a></td>
        <td id="status2"><a><span>45%</span></a></td>
      </tr>
    </table>
    """

    assert parse_zone_statuses(html) == {
        0: True,
        1: False,
        2: 45,
    }


def test_parse_discovered_devices_from_zone_statuses() -> None:
    html = """
    <table>
      <tr>
        <td id="status0"><a title="Kitchen ceiling"><img src="on.png"></a></td>
      </tr>
      <tr>
        <td id="status1"><a title="Kitchen blind"><span>0%</span></a></td>
      </tr>
    </table>
    """

    devices = parse_discovered_devices(html, zone_code=5, section_code=0)

    assert devices[0].kind == IdderoPointKind.LIGHT
    assert devices[0].device_code == 0
    assert devices[0].name == "Kitchen ceiling"
    assert devices[1].kind == IdderoPointKind.COVER
    assert devices[1].device_code == 1


def test_parse_zones_from_overview() -> None:
    html = """
    <map name="mapAreas">
      <area href="/zone?id=token&map=1&zone=1" title="Suite" alt="">
      <area href="/zone?id=token&map=1&zone=4" title="Sala" alt="">
    </map>
    <ul>
      <li><a href="/zone?id=token&map=1&zone=5">Cozinha</a></li>
    </ul>
    """

    zones = parse_zones(html)

    assert [(zone.zone_code, zone.name) for zone in zones] == [
        (1, "Suite"),
        (4, "Sala"),
        (5, "Cozinha"),
    ]
