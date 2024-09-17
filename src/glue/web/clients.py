from typing import Protocol
from urllib.parse import urlparse

import httpx
from starlette.websockets import WebSocket
from websockets import Subprotocol
from websockets.asyncio.client import connect, unix_connect

from glue.utils import VarResolver


class ClientsFactory(Protocol):
    def create_http_client(self) -> httpx.AsyncClient: ...
    def create_ws_client(self, websocket: WebSocket) -> connect: ...


def _get_protocols(websocket: WebSocket) -> list[Subprotocol]:
    return [
        Subprotocol(x.strip())
        for x in websocket.headers.get("Sec-WebSocket-Protocol", "").split(",")
    ]


class URLClientFactory(ClientsFactory):
    def __init__(self, target: str, resolver: VarResolver) -> None:
        self.target = target
        self.resolver = resolver

    def create_http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.resolver.resolve_vars(self.target),
        )

    def create_ws_client(self, websocket: WebSocket) -> connect:
        urlp = urlparse(self.target)
        scheme = {"http": "ws", "https": "wss"}.get(urlp.scheme, "ws")
        url = str(websocket.url.replace(scheme=scheme, netloc=urlp.netloc))
        return connect(
            url,
            subprotocols=_get_protocols(websocket),
        )


class UnixClientFactory(ClientsFactory):
    def __init__(self, uds: str, resolver: VarResolver) -> None:
        self.uds = uds
        self.resolver = resolver

    def get_socket_path(self) -> str:
        return self.resolver.resolve_vars(self.uds)

    def create_http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url="http://localhost",
            transport=httpx.AsyncHTTPTransport(
                uds=self.get_socket_path(),
            ),
        )

    def create_ws_client(self, websocket: WebSocket) -> connect:
        url = str(websocket.url.replace(scheme="ws", netloc="localhost"))
        return unix_connect(
            self.get_socket_path(),
            url,
            subprotocols=_get_protocols(websocket),
        )
