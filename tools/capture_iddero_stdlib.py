"""Capture Iddero pages using only the Python standard library."""

from __future__ import annotations

import argparse
from getpass import getpass
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener


def main() -> None:
    args = _parse_args()
    password = args.password
    if args.username and password is None:
        password = getpass("Password: ")

    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    base_url = _base_url(args.url)
    token = None

    if args.username:
        response_url, _body = _request(
            opener,
            urljoin(base_url, "/login"),
            method="POST",
            form={"user": args.username, "pass": password or ""},
        )
        token = _token_from_url(response_url)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = args.path or ["/"]
    for path in paths:
        resolved_path = path
        if token and path.startswith(("zone?", "zones?")) and "id=" not in path:
            page, _, query = path.partition("?")
            resolved_path = f"{page}?id={token}&{query}"
        response_url, body = _request(opener, urljoin(base_url, resolved_path))
        output = output_dir / _output_name(path)
        output.write_bytes(body)
        print(f"Wrote {output} from {response_url}")


def _request(
    opener,
    url: str,
    *,
    method: str = "GET",
    form: dict[str, str] | None = None,
) -> tuple[str, bytes]:
    data = urlencode(form).encode() if form is not None else None
    request = Request(url, data=data, method=method)
    if form is not None:
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
    with opener.open(request, timeout=10) as response:
        return response.geturl(), response.read()


def _base_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise SystemExit("URL must include scheme and host, for example http://host/")
    return f"{parsed.scheme}://{parsed.netloc}/"


def _token_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    for part in parsed.query.split("&"):
        key, _, value = part.partition("=")
        if key == "id":
            return value or None
    return None


def _output_name(path: str) -> str:
    if not path or path == "/":
        return "root.html"
    return (
        path.replace("/", "_")
        .replace("?", "_")
        .replace("&", "_")
        .replace("=", "-")
        + ".html"
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="Base URL for the Iddero web UI")
    parser.add_argument(
        "--path",
        action="append",
        default=None,
        help="Relative path to capture. May be repeated.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory to write")
    parser.add_argument("--username", help="Login username")
    parser.add_argument("--password", help="Login password")
    return parser.parse_args()


if __name__ == "__main__":
    main()
