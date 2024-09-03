from __future__ import annotations

import asyncio
from functools import partial
from typing import TYPE_CHECKING, Any

import anyio
import anyio.to_thread
from starlette.routing import Host, Match, Mount
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from glue.apps.proxy_pass import ProxyPassApp

if TYPE_CHECKING:
    from starlette.applications import Starlette

APP_STATE_KEY = "{name}-state"


class MountedLifespanMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def lifespan(self, scope: Scope, receive: Receive, send: Send) -> None:
        app: Starlette = scope["app"]
        downstream = [
            DownstreamLifespan(r.app, name=r.name)
            for r in app.routes
            if isinstance(r, (Mount, Host))
            if isinstance(r.app, ProxyPassApp)
        ]

        upstream = UpstreamLifespan(self.app, downstream)

        await upstream(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self.lifespan(scope, receive, send)
            return

        app: Starlette = scope["app"]
        route = next(
            (route for route in app.routes if route.matches(scope)[0] == Match.FULL),
            None,
        )

        if isinstance(route, (Mount, Host)) and route.name:
            state_key = APP_STATE_KEY.format(name=route.name)
            scope = {
                **scope,
                "state": scope["state"].get(state_key, {}),
            }

        await self.app(scope, receive, send)


class DownstreamLifespan:
    def __init__(self, app: ASGIApp, *, name: str | None) -> None:
        self.app = app
        self.name = name

        self.forward_queue = asyncio.Queue[Message]()

        self.startup = anyio.Event()
        self.shutdown = anyio.Event()
        self.startup_error: str | None = None
        self.shutdown_error: str | None = None

    async def __call__(self, scope: Scope) -> None:
        state: dict[str, Any] = {}
        lifespan_scope = {**scope, "state": state}

        async with anyio.create_task_group() as tg:
            tg.start_soon(self.on_startup_complete, scope, state)
            await self.app(lifespan_scope, self.receive, self.send)

    async def on_startup_complete(self, scope: Scope, state: dict[str, Any]) -> None:
        await self.startup.wait()
        if self.startup_error is None and state:
            assert self.name, "state is not supported on unnamed nested lifespans"
            state_key = APP_STATE_KEY.format(name=self.name)
            scope["state"][state_key] = state

    async def receive(self) -> Message:
        return await self.forward_queue.get()

    async def send(self, message: Message) -> None:
        if message["type"] in {
            "lifespan.startup.complete",
            "lifespan.startup.failed",
        }:
            assert not self.startup.is_set()
            self.startup.set()
            if msg := message.get("message"):
                self.startup_error = msg
        elif message["type"] in {
            "lifespan.shutdown.complete",
            "lifespan.shutdown.failed",
        }:
            assert not self.shutdown.is_set()
            self.shutdown.set()
            if msg := message.get("message"):
                self.shutdown_error = msg

    async def forward(self, message: Message) -> None:
        await self.forward_queue.put(message)


class UpstreamLifespan:
    """Receive function which forwards messages to downstream lifespans."""

    def __init__(self, app: ASGIApp, downstream: list[DownstreamLifespan]) -> None:
        self.app = app
        self.downstream = downstream

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async with anyio.create_task_group() as tg:
            for down in self.downstream:
                tg.start_soon(down, scope)

            receive = partial(self.receive, receive)
            send = partial(self.send, send)

            await self.app(scope, receive, send)

    async def receive(self, receive: Receive) -> Message:
        msg = await receive()
        async with anyio.create_task_group() as tg:
            for down in self.downstream:
                tg.start_soon(down.forward, msg)

        return msg

    async def send(self, send: Send, message: Message) -> None:
        error_messages = None
        if message["type"] in {
            "lifespan.startup.complete",
            "lifespan.startup.failed",
        }:
            for x in self.downstream:
                await x.startup.wait()

            error_messages = [
                x.startup_error for x in self.downstream if x.startup_error
            ]

        elif message["type"] in {
            "lifespan.shutdown.complete",
            "lifespan.shutdown.failed",
        }:
            for x in self.downstream:
                await x.shutdown.wait()

            error_messages = [
                x.shutdown_error for x in self.downstream if x.shutdown_error
            ]

        if error_messages:
            message["type"] = message["type"].replace(".complete", ".failed")
            if msg := message.get("message"):
                error_messages.insert(0, msg)
            message["message"] = "\n".join(error_messages)

        await send(message)
