import abc
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

import dotenv
import httpx
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp
from typing_extensions import override

from .apps import ProxyPassApp
from .compat import tomllib
from .typecast import typecast


class BaseServerConfig(abc.ABC):
    @abc.abstractmethod
    def create_route(self) -> ASGIApp:
        raise NotImplementedError


class BaseProxyPassServer(BaseServerConfig):
    @override
    def create_route(self) -> ASGIApp:
        return ProxyPassApp(self.create_client)

    @abc.abstractmethod
    def create_client(self) -> httpx.AsyncClient:
        raise NotImplementedError


@dataclass(kw_only=True)
class UnixDomainSocketServer(BaseProxyPassServer):
    uds: str

    @override
    def create_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url="http://localhost/",
            transport=httpx.AsyncHTTPTransport(uds=self.uds.format(xdg_run="run")),
        )


@dataclass(kw_only=True)
class LocalAddressServer(BaseProxyPassServer):
    target: str

    @override
    def create_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.target)


@dataclass(kw_only=True)
class StaticServer(BaseServerConfig):
    root_path: str

    @override
    def create_route(self) -> ASGIApp:
        return StaticFiles(directory=self.root_path, html=True)


ServerConfig = Union[UnixDomainSocketServer, LocalAddressServer, StaticServer]


@dataclass(kw_only=True)
class BaseServiceConfig:
    cwd: str = "."
    env: dict[str, Optional[str]] = field(default_factory=dict)
    env_file: Optional[str] = None

    def read_env_file(self) -> dict[str, Optional[str]]:
        env = {}

        if self.env_file:
            env_file = Path(self.cwd) / self.env_file
            env.update(dotenv.dotenv_values(env_file, interpolate=False))

        env.update(self.env)

        return OrderedDict(dotenv.main.resolve_variables(env.items(), override=True))


@dataclass(kw_only=True)
class PythonServiceConfig(BaseServiceConfig):
    python: str
    module: str
    args: list[str] = field(default_factory=list)


@dataclass(kw_only=True)
class ScriptServiceConfig(BaseServiceConfig):
    exec: str
    args: list[str] = field(default_factory=list)


ServiceConfig = Union[PythonServiceConfig, ScriptServiceConfig]


@dataclass(kw_only=True)
class Config:
    default_server: Optional[ServerConfig] = None
    servers: dict[str, ServerConfig] = field(default_factory=dict)
    services: list[ServiceConfig] = field(default_factory=list)


def load_config(path: Path) -> Config:
    data = tomllib.loads(path.read_text())
    return typecast(Config, data)
