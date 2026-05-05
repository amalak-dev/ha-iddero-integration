"""Capture an Iddero HTML page for parser development."""

from __future__ import annotations

import argparse
import asyncio
from getpass import getpass
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from custom_components.iddero.client import IdderoWebClient


async def _async_main() -> None:
    args = _parse_args()
    parsed = urlparse(args.url)
    if not parsed.hostname:
        raise SystemExit("URL must include a hostname")

    username = args.username
    password = args.password
    if username and password is None:
        password = getpass("Password: ")

    async with aiohttp.ClientSession(
        cookie_jar=aiohttp.CookieJar(unsafe=True),
    ) as session:
        client = IdderoWebClient(
            host=f"{parsed.scheme}://{parsed.hostname}",
            port=parsed.port or (443 if parsed.scheme == "https" else 80),
            use_ssl=parsed.scheme == "https",
            verify_ssl=not args.no_verify_ssl,
            base_path=parsed.path or "/",
            username=username,
            password=password,
            session=session,
        )
        html = await client.async_get_raw_page("")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html)
    print(f"Wrote {output}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="Base URL for the Iddero web UI")
    parser.add_argument("--output", required=True, help="HTML file to write")
    parser.add_argument("--username", help="Login username")
    parser.add_argument("--password", help="Login password")
    parser.add_argument(
        "--no-verify-ssl",
        action="store_true",
        help="Disable TLS certificate verification",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(_async_main())

