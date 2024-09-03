from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

import anyio
from starlette.requests import Request
from starlette.responses import StreamingResponse
from starlette.routing import Router
from starlette.websockets import WebSocket, WebSocketDisconnect
from websockets import ConnectionClosed, InvalidState, Subprotocol
from websockets.asyncio.client import ClientConnection, connect

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable

    import httpx
    from httpx import URL
    from starlette.types import ASGIApp, Receive, Scope, Send


class ProxyPassApp:
    def __init__(self, create_client: Callable[[], httpx.AsyncClient]) -> None:
        self.router = Router(lifespan=self.lifespan)
        self.create_client = create_client

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self.handle_lifespan(scope, receive, send)
        elif scope["type"] == "http":
            await self.handle_http(scope, receive, send)
        elif scope["type"] == "websocket":
            await self.handle_websocket(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(self, _: ASGIApp) -> AsyncGenerator[Any, Any]:
        async with self.create_client() as client:
            yield {"client": client}

    async def handle_lifespan(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.router.lifespan(scope, receive, send)

    async def handle_http(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive, send)
        headers = request.headers.mutablecopy()
        if request.client:
            headers["Forwarded"] = (
                f"for={request.client.host}"
                f";host={request.url.netloc}"
                f";proto={request.url.scheme}"
            )

            headers["X-Forwarded-For"] = request.client.host
            headers["X-Forwarded-Host"] = request.url.netloc
            headers["X-Forwarded-Proto"] = request.url.scheme

        client: httpx.AsyncClient = request.state.client

        resp = await client.request(
            request.method,
            str(request.url.path),
            params=request.query_params,
            headers=headers.items(),
            content=request.stream(),
        )

        resp_headers = resp.headers.copy()

        # content-encoding should be removed to prevent invalid client response decoding
        if "content-encoding" in resp_headers:
            del resp_headers["content-encoding"]

        response = StreamingResponse(
            content=resp.iter_bytes(),
            status_code=resp.status_code,
            headers=resp_headers,
        )

        await response(scope, receive, send)

    async def handle_websocket(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        websocket = WebSocket(scope, receive, send)
        protocols = [
            Subprotocol(x.strip())
            for x in websocket.headers.get("Sec-WebSocket-Protocol", "").split(",")
        ]

        url: URL = websocket.state.client.base_url
        websocket_url = str(
            websocket.url.replace(hostname=url.host, port=url.port)
        ).removesuffix("/")

        async with connect(websocket_url, subprotocols=protocols) as socketclient:
            handler = WebSocketHandler(websocket, socketclient)
            await handler()


class WebSocketHandler:
    def __init__(self, websocket: WebSocket, socketclient: ClientConnection) -> None:
        self.websocket = websocket
        self.socketclient = socketclient

    async def recv_client(self) -> None:
        try:
            while True:
                data = await self.socketclient.recv()
                if isinstance(data, str):
                    await self.websocket.send_text(data)
                else:
                    await self.websocket.send_bytes(data)
        except ConnectionClosed as e:
            with contextlib.suppress(RuntimeError):
                await self.websocket.close(e.code, e.reason)

    async def recv_server(self) -> None:
        try:
            while True:
                msg = await self.websocket.receive()
                if msg["type"] == "websocket.disconnect":
                    await self.socketclient.close(msg["code"], msg.get("reason", ""))
                    break

                if "bytes" in msg:
                    await self.socketclient.send(msg["bytes"])
                elif "text" in msg:
                    await self.socketclient.send(msg["text"])
        except WebSocketDisconnect as e:
            with contextlib.suppress(InvalidState):
                await self.socketclient.close(e.code, e.reason)

    async def __call__(self) -> None:
        async with anyio.create_task_group() as tg:
            tg.start_soon(self.recv_client)
            tg.start_soon(self.recv_server)

            await self.websocket.accept(subprotocol=self.socketclient.subprotocol)
