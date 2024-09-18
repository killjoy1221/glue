from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import anyio
import httpx
from starlette import status
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.websockets import WebSocket, WebSocketDisconnect
from websockets import ConnectionClosed, InvalidState

if TYPE_CHECKING:
    from starlette.types import Receive, Scope, Send
    from websockets.asyncio.connection import Connection

    from .clients import ClientsFactory


class ProxyApp:
    def __init__(self, clients_factory: ClientsFactory) -> None:
        self.clients = clients_factory

        self.handlers = {
            "http": self.handle_http,
            "websocket": self.handle_websocket,
        }

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        handler = self.handlers.get(scope["type"])
        if handler is not None:
            await handler(scope, receive, send)

    async def handle_http(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive, send)
        async with self.clients.create_http_client() as client:
            handler = HttpHandler(client)
            await handler(request)

    async def handle_websocket(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        websocket = WebSocket(scope, receive, send)
        async with self.clients.create_ws_client(websocket) as client:
            handler = WebSocketHandler(client)
            await handler(websocket)


class HttpHandler:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    def prepare_headers(self, request: Request) -> list[tuple[str, str]]:
        headers = request.headers.mutablecopy()
        if "host" in headers:
            del headers["host"]
        if request.client:
            forwarded = {
                "for": request.client.host,
                "host": request.url.netloc,
                "proto": request.url.scheme,
            }
            headers["Forwarded"] = ";".join(f"{k}={v}" for k, v in forwarded.items())

            headers.update({f"x-forwarded-{k}": v for k, v in forwarded.items()})

        return headers.items()

    async def do_request(self, request: Request) -> httpx.Response:
        return await self.client.request(
            request.method,
            str(request.url.path),
            params=request.query_params,
            headers=self.prepare_headers(request),
            content=request.stream(),
            timeout=30,
        )

    async def __call__(self, request: Request) -> Response:
        try:
            resp = await self.do_request(request)
        except httpx.TimeoutException:
            raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT) from None
        except httpx.TransportError:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY) from None
        except httpx.RequestError:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE) from None

        resp_headers = resp.headers.copy()

        # content-encoding should be removed to prevent invalid client response decoding
        if "content-encoding" in resp_headers:
            del resp_headers["content-encoding"]

        return StreamingResponse(
            content=resp.iter_bytes(),
            status_code=resp.status_code,
            headers=resp_headers,
        )


class WebSocketHandler:
    def __init__(self, client: Connection) -> None:
        self.client = client

    async def recv_client(self, websocket: WebSocket) -> None:
        try:
            while True:
                data = await self.client.recv()
                if isinstance(data, str):
                    await websocket.send_text(data)
                else:
                    await websocket.send_bytes(data)
        except ConnectionClosed as e:
            with contextlib.suppress(RuntimeError):
                await websocket.close(e.code, e.reason)

    async def recv_server(self, websocket: WebSocket) -> None:
        try:
            while True:
                msg = await websocket.receive()
                if msg["type"] == "websocket.disconnect":
                    await self.client.close(msg["code"], msg.get("reason", ""))
                    break

                if "bytes" in msg:
                    await self.client.send(msg["bytes"])
                elif "text" in msg:
                    await self.client.send(msg["text"])
        except WebSocketDisconnect as e:
            with contextlib.suppress(InvalidState):
                await self.client.close(e.code, e.reason)

    async def __call__(self, websocket: WebSocket) -> None:
        async with anyio.create_task_group() as tg:
            tg.start_soon(self.recv_client, websocket)
            tg.start_soon(self.recv_server, websocket)

            await websocket.accept(subprotocol=self.client.subprotocol)
