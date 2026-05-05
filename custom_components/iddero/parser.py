"""HTML parsers for Iddero pages.

Real Iddero web pages are expected to need device-specific parsing. The default
parser supports explicit `data-iddero-*` attributes, which gives us a stable
contract for tests and a clear shape for the real adapter to return.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

from .device_map import make_discovered_device_description
from .models import (
    IdderoDeviceDescription,
    IdderoPoint,
    IdderoPointKind,
    IdderoSnapshot,
    IdderoZoneDescription,
)

_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link"}


class IdderoParseError(Exception):
    """Raised when a page cannot be parsed."""


@dataclass(frozen=True, slots=True)
class LoginForm:
    """Login form details extracted from a page."""

    action: str
    method: str
    fields: dict[str, str]
    password_field: str
    username_field: str | None


def parse_login_form(html: str, page_url: str) -> LoginForm | None:
    """Extract the first login-like form from a page."""
    parser = _FormParser()
    parser.feed(html)

    for form in parser.forms:
        password_inputs = [
            field for field in form.inputs if field["type"] == "password"
        ]
        if not password_inputs:
            continue

        fields = {
            field["name"]: field["value"]
            for field in form.inputs
            if field["name"] and field["type"] not in {"button", "submit"}
        }
        username_field = _find_username_field(form.inputs)
        return LoginForm(
            action=urljoin(page_url, form.action or page_url),
            method=form.method,
            fields=fields,
            password_field=password_inputs[0]["name"],
            username_field=username_field,
        )

    return None


def parse_snapshot(html: str) -> IdderoSnapshot:
    """Parse a panel state page into a normalized snapshot."""
    parser = _IdderoDataParser()
    parser.feed(html)

    return IdderoSnapshot(
        device_name=parser.device_name or "Iddero",
        model=parser.model,
        firmware=parser.firmware,
        points={point.key: point for point in parser.points},
    )


def parse_zone_statuses(html: str) -> dict[int, bool | int | str]:
    """Parse Iddero status cells from a zone page.

    Ported from the Go version:
    - lights use `td#statusN a img`, where the image src contains `off`
    - blinds use `td#statusN a span`, where text normally contains a percentage
    """
    parser = _ZoneStatusParser()
    parser.feed(html)
    return {
        device_code: status_node.state
        for device_code, status_node in parser.statuses.items()
        if status_node.state is not None
    }


def parse_zones(html: str) -> list[IdderoZoneDescription]:
    """Parse available zone codes from the Iddero zones overview page."""
    parser = _ZonesParser()
    parser.feed(html)
    return list(parser.zones.values())


def parse_discovered_devices(
    html: str,
    *,
    zone_code: int,
    section_code: int,
    zone_name: str | None = None,
) -> list[IdderoDeviceDescription]:
    """Best-effort device discovery from an Iddero zone page."""
    parser = _ZoneStatusParser()
    parser.feed(html)
    devices: list[IdderoDeviceDescription] = []
    for device_code, status_node in sorted(parser.statuses.items()):
        if status_node.state is None:
            continue
        kind = status_node.kind
        if kind is None:
            kind = (
                IdderoPointKind.COVER
                if section_code == 1
                else IdderoPointKind.LIGHT
            )
        devices.append(
            make_discovered_device_description(
                zone_code=zone_code,
                section_code=section_code,
                device_code=device_code,
                kind=kind,
                name=status_node.label,
                zone_name=zone_name,
            )
        )
    return devices


def _find_username_field(inputs: list[dict[str, str]]) -> str | None:
    preferred_names = ("username", "user", "login", "email")
    named_inputs = [
        field
        for field in inputs
        if field["name"] and field["type"] in {"text", "email", "search"}
    ]
    for preferred_name in preferred_names:
        for field in named_inputs:
            if preferred_name in field["name"].lower():
                return field["name"]
    return named_inputs[0]["name"] if named_inputs else None


class _Form:
    def __init__(self, attrs: dict[str, str]) -> None:
        self.action = attrs.get("action", "")
        self.method = attrs.get("method", "POST").upper()
        self.inputs: list[dict[str, str]] = []


class _FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[_Form] = []
        self._current_form: _Form | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = {key.lower(): value or "" for key, value in attrs}
        if tag == "form":
            self._current_form = _Form(attributes)
            return

        if tag != "input" or self._current_form is None:
            return

        self._current_form.inputs.append(
            {
                "name": attributes.get("name", ""),
                "type": attributes.get("type", "text").lower(),
                "value": attributes.get("value", ""),
            }
        )

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._current_form is not None:
            self.forms.append(self._current_form)
            self._current_form = None


class _IdderoDataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.device_name: str | None = None
        self.model: str | None = None
        self.firmware: str | None = None
        self.points: list[IdderoPoint] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = {key.lower(): value or "" for key, value in attrs}
        self._maybe_parse_device(attributes)
        self._maybe_parse_point(tag, attributes)

    def _maybe_parse_device(self, attributes: dict[str, str]) -> None:
        self.device_name = attributes.get("data-iddero-device-name", self.device_name)
        self.model = attributes.get("data-iddero-model", self.model)
        self.firmware = attributes.get("data-iddero-firmware", self.firmware)

    def _maybe_parse_point(self, tag: str, attributes: dict[str, str]) -> None:
        key = attributes.get("data-iddero-id")
        if not key:
            return

        kind = _parse_kind(attributes.get("data-iddero-kind", "sensor"))
        raw_state = attributes.get("data-iddero-state")
        if raw_state == "" and tag == "input":
            raw_state = attributes.get("value")
        if raw_state == "" and attributes.get("checked"):
            raw_state = "on"

        point_attributes: dict[str, Any] = {
            attr_key.removeprefix("data-iddero-attr-"): attr_value
            for attr_key, attr_value in attributes.items()
            if attr_key.startswith("data-iddero-attr-")
        }
        for attr_key, attr_value in attributes.items():
            if attr_key.startswith("data-iddero-control-"):
                point_attributes[
                    attr_key.removeprefix("data-iddero-").replace("-", "_")
                ] = attr_value

        self.points.append(
            IdderoPoint(
                key=key,
                name=attributes.get("data-iddero-name") or key,
                kind=kind,
                state=_coerce_state(raw_state, kind),
                unit=attributes.get("data-iddero-unit") or None,
                device_class=attributes.get("data-iddero-device-class") or None,
                state_class=attributes.get("data-iddero-state-class") or None,
                attributes=point_attributes,
            )
        )


def _parse_kind(raw_kind: str) -> IdderoPointKind:
    try:
        return IdderoPointKind(raw_kind)
    except ValueError as err:
        raise IdderoParseError(f"Unsupported point kind: {raw_kind}") from err


def _coerce_state(
    raw_state: str | None,
    kind: IdderoPointKind,
) -> bool | int | float | str | None:
    if raw_state is None:
        return None

    stripped = raw_state.strip()
    lowered = stripped.lower()
    if kind == IdderoPointKind.SWITCH:
        if lowered in {"1", "on", "true", "yes"}:
            return True
        if lowered in {"0", "off", "false", "no"}:
            return False

    try:
        return int(stripped)
    except ValueError:
        pass

    try:
        return float(stripped)
    except ValueError:
        return stripped


@dataclass(slots=True)
class _StatusNode:
    device_code: int
    text_parts: list[str]
    image_sources: list[str]
    labels: list[str]

    @property
    def label(self) -> str | None:
        for label in self.labels:
            cleaned = " ".join(label.split())
            if cleaned:
                return cleaned
        return None

    @property
    def kind(self) -> IdderoPointKind | None:
        if self.image_sources:
            return IdderoPointKind.LIGHT
        text = self._text.lower()
        if "%" in text or text.isdigit():
            return IdderoPointKind.COVER
        return None

    @property
    def state(self) -> bool | int | str | None:
        if self.image_sources:
            return not any("off" in source.lower() for source in self.image_sources)

        text = self._text
        if not text:
            return None
        if "%" in text:
            text = text.replace("%", "").strip()
        try:
            return int(text)
        except ValueError:
            return text

    @property
    def _text(self) -> str:
        return " ".join(part.strip() for part in self.text_parts if part.strip())


class _ZoneStatusParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.statuses: dict[int, _StatusNode] = {}
        self._control_names: dict[int, list[str]] = {}
        self._current_control: int | None = None
        self._control_depth = 0
        self._name_control: int | None = None
        self._name_depth = 0
        self._current_status: _StatusNode | None = None
        self._status_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = {key.lower(): value or "" for key, value in attrs}
        if self._current_control is None:
            control_id = attributes.get("id", "")
            if tag == "div" and control_id.startswith("control"):
                control_code = _parse_control_device_code(control_id)
                if control_code is not None:
                    self._current_control = control_code
                    self._control_depth = 1
        elif self._current_status is None and tag not in _VOID_TAGS:
            self._control_depth += 1

        if (
            self._current_control is not None
            and self._name_control is None
            and tag == "td"
            and "name" in attributes.get("class", "").split()
        ):
            self._name_control = self._current_control
            self._name_depth = 1
        elif self._name_control is not None and tag not in _VOID_TAGS:
            self._name_depth += 1

        if self._current_status is None:
            status_id = attributes.get("id", "")
            if tag == "td" and status_id.startswith("status"):
                device_code = _parse_status_device_code(status_id)
                if device_code is None:
                    return
                self._current_status = _StatusNode(
                    device_code=device_code,
                    text_parts=[],
                    image_sources=[],
                    labels=self._control_names.get(device_code, []).copy(),
                )
                self._status_depth = 1
                self._collect_labels(attributes)
            return

        self._collect_labels(attributes)
        if tag == "img":
            source = attributes.get("src", "")
            if source:
                self._current_status.image_sources.append(source)
        if tag not in _VOID_TAGS:
            self._status_depth += 1

    def handle_data(self, data: str) -> None:
        if self._name_control is not None:
            self._control_names.setdefault(self._name_control, []).append(data)
        if self._current_status is not None:
            self._current_status.text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._name_control is not None:
            self._name_depth -= 1
            if self._name_depth <= 0:
                self._name_control = None
                self._name_depth = 0

        if self._current_status is None:
            if self._current_control is not None:
                self._control_depth -= 1
                if self._control_depth <= 0:
                    self._current_control = None
                    self._control_depth = 0
            return

        self._status_depth -= 1
        if self._status_depth <= 0:
            self.statuses[self._current_status.device_code] = self._current_status
            self._current_status = None
            self._status_depth = 0
            if self._current_control is not None:
                self._control_depth -= 1
                if self._control_depth <= 0:
                    self._current_control = None
                    self._control_depth = 0

    def _collect_labels(self, attributes: dict[str, str]) -> None:
        if self._current_status is None:
            return
        for key in ("data-name", "aria-label", "title", "alt", "name"):
            value = attributes.get(key)
            if value:
                self._current_status.labels.append(value)


def _parse_status_device_code(status_id: str) -> int | None:
    raw_device_code = status_id.removeprefix("status")
    if not raw_device_code.isdigit():
        return None
    return int(raw_device_code)


def _parse_control_device_code(control_id: str) -> int | None:
    raw_device_code = control_id.removeprefix("control")
    if not raw_device_code.isdigit():
        return None
    return int(raw_device_code)


class _ZonesParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.zones: dict[int, IdderoZoneDescription] = {}
        self._active_zone_code: int | None = None
        self._active_text_parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = {key.lower(): value or "" for key, value in attrs}
        if tag not in {"a", "area"}:
            return

        zone_code = _zone_code_from_href(attributes.get("href", ""))
        if zone_code is None:
            return

        name = attributes.get("title") or attributes.get("alt") or None
        if tag == "area":
            self._store_zone(zone_code, name)
            return

        self._active_zone_code = zone_code
        self._active_text_parts = []
        if name:
            self._store_zone(zone_code, name)

    def handle_data(self, data: str) -> None:
        if self._active_zone_code is not None:
            self._active_text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._active_zone_code is None:
            return
        text = " ".join(part.strip() for part in self._active_text_parts).strip()
        self._store_zone(self._active_zone_code, text or None)
        self._active_zone_code = None
        self._active_text_parts = []

    def _store_zone(self, zone_code: int, name: str | None) -> None:
        existing = self.zones.get(zone_code)
        if existing is not None and existing.name:
            return
        self.zones[zone_code] = IdderoZoneDescription(
            zone_code=zone_code,
            name=name,
        )


def _zone_code_from_href(href: str) -> int | None:
    if not href:
        return None
    parsed = urlparse(href)
    if not parsed.path.endswith("/zone") and parsed.path != "zone":
        return None
    values = parse_qs(parsed.query).get("zone")
    if not values or not values[0].isdigit():
        return None
    return int(values[0])
