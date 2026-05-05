"""Async web client for Iddero panels."""

from __future__ import annotations

import asyncio
import unicodedata
from collections.abc import Sequence
from typing import Any
from urllib.parse import urljoin

from aiohttp import ClientError, ClientResponse, ClientSession, ClientTimeout
from yarl import URL

from .models import (
    IdderoDeviceDescription,
    IdderoPoint,
    IdderoSnapshot,
    IdderoZoneDescription,
)
from .parser import (
    IdderoParseError,
    parse_discovered_devices,
    parse_login_form,
    parse_snapshot,
    parse_zone_statuses,
    parse_zones,
)

COMMAND_SETTLE_DELAY = 0.75


class IdderoError(Exception):
    """Base Iddero client error."""


class IdderoCannotConnectError(IdderoError):
    """Raised when the panel cannot be reached."""


class IdderoInvalidAuthError(IdderoError):
    """Raised when authentication fails."""


class IdderoCommandError(IdderoError):
    """Raised when a write command cannot be sent."""


class IdderoPageParseError(IdderoError):
    """Raised when an Iddero page cannot be parsed."""


class IdderoWebClient:
    """Client for an Iddero web interface.

    The class intentionally avoids Home Assistant imports so it can be tested
    independently with saved HTML fixtures.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        use_ssl: bool,
        verify_ssl: bool,
        base_path: str,
        username: str | None,
        password: str | None,
        session: ClientSession,
        request_timeout: int = 10,
    ) -> None:
        self._base_url = _build_base_url(host, port, use_ssl, base_path)
        self._username = username
        self._password = password
        self._session = session
        self._timeout = ClientTimeout(total=request_timeout)
        self._ssl: bool | None = None if verify_ssl else False
        self._authenticated = False
        self._token: str | None = None

    async def async_probe(self) -> None:
        """Verify that the panel is reachable and credentials work."""
        await self.async_login()
        await self._request_text("GET", "", retry_auth=False)

    async def async_login(self) -> None:
        """Log in to the Iddero panel."""
        if self._authenticated:
            return

        if not self._username and not self._password:
            self._authenticated = True
            return

        login_html, login_response = await self._request_text(
            "POST",
            "/login",
            data={"user": self._username or "", "pass": self._password or ""},
            retry_auth=False,
        )
        self._token = login_response.url.query.get("id") or None
        if self._token and "login" not in login_response.url.path.lower():
            self._authenticated = True
            return

        login_form = parse_login_form(login_html, str(login_response.url))
        if login_form is None:
            raise IdderoInvalidAuthError("Iddero login did not return a session token")

        fields: dict[str, str] = dict(login_form.fields)
        if login_form.username_field:
            fields[login_form.username_field] = self._username or ""
        fields[login_form.password_field] = self._password or ""

        login_html, login_response = await self._request_text(
            login_form.method,
            login_form.action,
            data=fields,
            retry_auth=False,
        )
        self._token = login_response.url.query.get("id") or None
        if (
            parse_login_form(login_html, str(login_response.url)) is not None
            or self._token is None
        ):
            raise IdderoInvalidAuthError("Login form was shown after login")

        self._authenticated = True

    async def async_get_raw_page(self, path: str = "") -> str:
        """Fetch a raw HTML page after authentication."""
        await self.async_login()
        html, _response = await self._request_text("GET", path)
        return html

    async def async_fetch_snapshot(self) -> IdderoSnapshot:
        """Fetch and parse the current panel state."""
        html = await self.async_get_raw_page("")
        try:
            return parse_snapshot(html)
        except IdderoParseError as err:
            raise IdderoPageParseError(f"Unable to parse Iddero page: {err}") from err

    async def async_fetch_mapped_snapshot(
        self,
        devices: Sequence[IdderoDeviceDescription],
    ) -> IdderoSnapshot:
        """Fetch status for configured Iddero devices."""
        points: dict[str, IdderoPoint] = {}
        grouped_devices: dict[tuple[int, int], list[IdderoDeviceDescription]] = {}
        for device in devices:
            grouped_devices.setdefault(
                (device.zone_code, device.section_code),
                [],
            ).append(device)

        for (zone_code, section_code), zone_devices in grouped_devices.items():
            html = await self.async_get_zone_page(
                zone_code=zone_code,
                section_code=section_code,
            )
            statuses = parse_zone_statuses(html)
            for device in zone_devices:
                points[device.key] = _point_from_device(
                    device,
                    statuses.get(device.device_code),
                )

        return IdderoSnapshot(
            device_name="Iddero",
            model=None,
            firmware=None,
            points=points,
        )

    async def async_discover_devices(
        self,
        *,
        section_codes: Sequence[int] = (0, 1),
        max_consecutive_empty: int = 3,
    ) -> list[IdderoDeviceDescription]:
        """Best-effort discovery by crawling Iddero zone pages."""
        discovered: dict[str, IdderoDeviceDescription] = {}
        zones = await self.async_discover_zones()

        if zones:
            for zone in zones:
                if _is_scene_zone(zone.name):
                    continue
                for section_code in section_codes:
                    html = await self.async_get_zone_page(
                        zone_code=zone.zone_code,
                        section_code=section_code,
                    )
                    for device in parse_discovered_devices(
                        html,
                        zone_code=zone.zone_code,
                        section_code=section_code,
                        zone_name=zone.name,
                    ):
                        discovered[device.key] = device
        else:
            consecutive_empty = 0
            zone_code = 1
            while consecutive_empty < max_consecutive_empty:
                found_in_zone = False
                for section_code in section_codes:
                    html = await self.async_get_zone_page(
                        zone_code=zone_code,
                        section_code=section_code,
                    )
                    for device in parse_discovered_devices(
                        html,
                        zone_code=zone_code,
                        section_code=section_code,
                    ):
                        discovered[device.key] = device
                        found_in_zone = True
                if found_in_zone:
                    consecutive_empty = 0
                else:
                    consecutive_empty += 1
                zone_code += 1

        return list(discovered.values())

    async def async_discover_zones(self) -> list[IdderoZoneDescription]:
        """Discover zones from the Iddero zones overview page."""
        await self.async_login()
        html, _response = await self._request_text("GET", self._zones_path())
        return parse_zones(html)

    async def async_get_zone_page(self, *, zone_code: int, section_code: int) -> str:
        """Fetch a zone page from the Iddero panel."""
        await self.async_login()
        html, _response = await self._request_text(
            "GET",
            self._zone_path(zone_code=zone_code, section_code=section_code),
        )
        return html

    async def async_set_light(self, point: IdderoPoint, is_on: bool) -> None:
        """Set a light by using Iddero's toggle command when needed."""
        current_state = point.state if isinstance(point.state, bool) else None
        if current_state is is_on:
            return

        device = _device_from_point(point)
        await self._request_text(
            "GET",
            self._zone_path(device=device, action=True, light_click=True),
        )
        await asyncio.sleep(COMMAND_SETTLE_DELAY)
        self._authenticated = True

    async def async_set_cover_position(
        self,
        point: IdderoPoint,
        position: int,
    ) -> None:
        """Set a blind position from 0 to 100."""
        device = _device_from_point(point)
        await self._request_text(
            "POST",
            self._zone_path(device=device, action=True),
            data={"value": str(position), "command:set": "true"},
        )
        await asyncio.sleep(COMMAND_SETTLE_DELAY)
        self._authenticated = True

    async def async_open_cover(self, point: IdderoPoint) -> None:
        """Move a blind up."""
        await self._async_move_cover(point, "command:moveUp=true")

    async def async_close_cover(self, point: IdderoPoint) -> None:
        """Move a blind down."""
        await self._async_move_cover(point, "command:moveDown=true")

    async def async_stop_cover(self, point: IdderoPoint) -> None:
        """Stop a blind by sending a step command."""
        await self._async_move_cover(point, "command:stepUp=true")

    async def async_set_switch(self, point: IdderoPoint, is_on: bool) -> None:
        """Set a parsed switch point.

        Real Iddero pages may use form posts, query strings, or JavaScript
        endpoints. The parser should attach the discovered control details to
        the point attributes listed below.
        """
        control_path = point.attributes.get("control_path")
        if not isinstance(control_path, str) or not control_path:
            raise IdderoCommandError(
                f"No control action was parsed for point {point.key!r}"
            )

        method = str(point.attributes.get("control_method", "POST")).upper()
        id_param = str(point.attributes.get("control_id_param", "id"))
        value_param = str(point.attributes.get("control_value_param", "value"))
        on_value = str(point.attributes.get("control_on_value", "1"))
        off_value = str(point.attributes.get("control_off_value", "0"))
        data = {
            id_param: point.key,
            value_param: on_value if is_on else off_value,
        }
        await self._request_text(method, control_path, data=data)
        await asyncio.sleep(COMMAND_SETTLE_DELAY)
        self._authenticated = True

    async def _async_move_cover(self, point: IdderoPoint, command: str) -> None:
        device = _device_from_point(point)
        await self._request_text(
            "POST",
            f"{self._zone_path(device=device, action=True)}&{command}",
            data={},
        )
        await asyncio.sleep(COMMAND_SETTLE_DELAY)
        self._authenticated = True

    async def _request_text(
        self,
        method: str,
        path_or_url: str,
        retry_auth: bool = True,
        **kwargs: Any,
    ) -> tuple[str, ClientResponse]:
        url = self._url_for(path_or_url)
        try:
            response = await self._session.request(
                method,
                url,
                timeout=self._timeout,
                ssl=self._ssl,
                **kwargs,
            )
            async with response:
                if response.status in (401, 403):
                    raise IdderoInvalidAuthError(
                        f"Panel rejected request with HTTP {response.status}"
                    )
                if response.status >= 400:
                    raise IdderoCannotConnectError(
                        f"Panel returned HTTP {response.status}"
                    )
                if retry_auth and self._needs_login(response):
                    self._authenticated = False
                    await self.async_login()
                    return await self._request_text(
                        method,
                        path_or_url,
                        retry_auth=False,
                        **kwargs,
                    )
                return await response.text(), response
        except IdderoError:
            raise
        except (TimeoutError, ClientError) as err:
            raise IdderoCannotConnectError(str(err)) from err

    def _url_for(self, path_or_url: str) -> str:
        if not path_or_url:
            return str(self._base_url)
        if "://" in path_or_url:
            return path_or_url
        return urljoin(str(self._base_url), path_or_url)

    def _needs_login(self, response: ClientResponse) -> bool:
        if not self._username and not self._password:
            return False
        path = response.url.path.lower()
        return "login" in path or self._token is None

    def _zone_path(
        self,
        *,
        zone_code: int | None = None,
        section_code: int | None = None,
        device: IdderoDeviceDescription | None = None,
        action: bool = False,
        light_click: bool = False,
    ) -> str:
        if device is not None:
            zone_code = device.zone_code
            section_code = device.section_code
        if zone_code is None or section_code is None:
            raise IdderoCommandError("Zone code and section code are required")

        query_parts = ["zone?"]
        if self._token:
            query_parts.append(f"id={self._token}")
        query_parts.append(f"&map=1&zone={zone_code}&section={section_code}")
        if action:
            if device is None:
                raise IdderoCommandError("Device is required for control actions")
            query_parts.append(f"&control={device.device_code}")
            if light_click:
                query_parts.append("&command:click=true")
        return "".join(query_parts)

    def _zones_path(self) -> str:
        query_parts = ["zones?"]
        if self._token:
            query_parts.append(f"id={self._token}&")
        query_parts.append("map=1")
        return "".join(query_parts)


def _build_base_url(host: str, port: int, use_ssl: bool, base_path: str) -> URL:
    if "://" in host:
        url = URL(host)
    else:
        url = URL.build(
            scheme="https" if use_ssl else "http",
            host=host,
            port=port or None,
        )

    normalized_path = base_path if base_path.startswith("/") else f"/{base_path}"
    if not normalized_path.endswith("/"):
        normalized_path = f"{normalized_path}/"

    return url.with_path(normalized_path).with_query(None).with_fragment(None)


def _point_from_device(
    device: IdderoDeviceDescription,
    state: bool | int | str | None,
) -> IdderoPoint:
    return IdderoPoint(
        key=device.key,
        name=device.name,
        kind=device.kind,
        state=state,
        attributes={
            "alias": device.alias,
            "zone_name": device.zone_name,
            "zone_code": device.zone_code,
            "section_code": device.section_code,
            "device_code": device.device_code,
        },
    )


def _device_from_point(point: IdderoPoint) -> IdderoDeviceDescription:
    return IdderoDeviceDescription(
        key=point.key,
        name=point.name,
        kind=point.kind,
        zone_code=int(point.attributes["zone_code"]),
        section_code=int(point.attributes["section_code"]),
        device_code=int(point.attributes["device_code"]),
        zone_name=str(point.attributes["zone_name"])
        if point.attributes.get("zone_name")
        else None,
        alias=str(point.attributes["alias"]) if point.attributes.get("alias") else None,
    )


def _is_scene_zone(name: str | None) -> bool:
    if not name:
        return False
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return ascii_name in {"cenario", "cenarios", "scenes", "scene"}
