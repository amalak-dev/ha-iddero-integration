"""In-process fake Iddero panel serving markup shaped like real captures."""

from __future__ import annotations

import itertools

from aiohttp import web
from aiohttp.test_utils import TestServer

LOGIN_PAGE = """<!DOCTYPE html><html><body>
<div class="page" id="loginPage"><header><h1>Login</h1></header>
<form action="/login" method="post"><ul class="list inset">
<li><input class="form-control" type="text" id="user" name="user"></li>
<li><input class="form-control" type="password" id="pass" name="pass"></li>
</ul><div class="buttons"><input class="button" type="submit" value="Entrar"></div>
</form></div></body></html>"""


class FakePanel:
    """A single-zone panel with lights in section 0."""

    def __init__(self, *, username: str = "user", password: str = "pass") -> None:
        self.username = username
        self.password = password
        self.lights: dict[int, bool] = {0: False, 1: False}
        self.light_names = {0: "Teto", 1: "Sanca"}
        self.valid_tokens: set[str] = set()
        self.login_count = 0
        self.click_count = 0
        self._token_ids = itertools.count(1)
        self.server: TestServer | None = None

    def expire_sessions(self) -> None:
        self.valid_tokens.clear()

    async def start(self) -> TestServer:
        app = web.Application()
        app.router.add_post("/login", self._login)
        app.router.add_get("/zone", self._zone)
        app.router.add_get("/", self._root)
        self.server = TestServer(app)
        await self.server.start_server()
        return self.server

    async def close(self) -> None:
        if self.server is not None:
            await self.server.close()

    async def _root(self, request: web.Request) -> web.Response:
        return web.Response(text=LOGIN_PAGE, content_type="text/html")

    async def _login(self, request: web.Request) -> web.StreamResponse:
        form = await request.post()
        if form.get("user") != self.username or form.get("pass") != self.password:
            return web.Response(text=LOGIN_PAGE, content_type="text/html")
        self.login_count += 1
        token = f"tok{next(self._token_ids)}"
        self.valid_tokens.add(token)
        raise web.HTTPFound(f"/zone?id={token}&map=1&zone=1&section=0")

    async def _zone(self, request: web.Request) -> web.Response:
        if request.query.get("id") not in self.valid_tokens:
            # Expired or unknown session: the login page at the same URL.
            return web.Response(text=LOGIN_PAGE, content_type="text/html")

        control = request.query.get("control")
        if control is not None and request.query.get("command:click") == "true":
            code = int(control)
            self.lights[code] = not self.lights[code]
            self.click_count += 1

        return web.Response(text=self._zone_html(), content_type="text/html")

    def _zone_html(self) -> str:
        rows = []
        for code, is_on in self.lights.items():
            icon = "iconLampOn" if is_on else "iconLampOff"
            rows.append(
                f'<div id="control{code}" class="list-item control">'
                '<table class="controlClosed"><tr><td class="expand"></td>'
                f'<td class="name"><a href="#">{self.light_names[code]}</a></td>'
                f'<td id="status{code}" class="status"><a href="#">'
                f'<img class="st-icon platimg" src="images/{icon}" alt=""></a>'
                "</td></tr></table></div>"
            )
        return (
            '<!DOCTYPE html><html><body><div class="page" id="zone">'
            f'<div id="controls" class="list">{"".join(rows)}</div>'
            "</div></body></html>"
        )
