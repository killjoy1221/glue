import abc
import sys
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

import dotenv
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp
from typing_extensions import override

from .compat import tomllib
from .typecast import typecast
from .utils import DirResolver
from .web import ProxyApp
from .web.clients import ClientsFactory, UnixClientFactory, URLClientFactory


class BaseServerConfig(abc.ABC):
    @abc.abstractmethod
    def create_route(self, dirs: DirResolver) -> ASGIApp:
        raise NotImplementedError


class BaseProxyPassServer(BaseServerConfig):
    @override
    def create_route(self, dirs: DirResolver) -> ASGIApp:
        return ProxyApp(self.create_client_factory(dirs))

    @abc.abstractmethod
    def create_client_factory(self, dirs: DirResolver) -> ClientsFactory:
        raise NotImplementedError


@dataclass(kw_only=True)
class UnixDomainSocketServer(BaseProxyPassServer):
    uds: str

    @override
    def create_client_factory(self, dirs: DirResolver) -> ClientsFactory:
        return UnixClientFactory(self.uds, dirs)


@dataclass(kw_only=True)
class LocalAddressServer(BaseProxyPassServer):
    target: str

    @override
    def create_client_factory(self, dirs: DirResolver) -> ClientsFactory:
        return URLClientFactory(self.target, dirs)


@dataclass(kw_only=True)
class StaticServer(BaseServerConfig):
    root_path: str

    @override
    def create_route(self, dirs: DirResolver) -> ASGIApp:
        return StaticFiles(directory=self.root_path, html=True)


ServerConfig = Union[UnixDomainSocketServer, LocalAddressServer, StaticServer]


@dataclass(kw_only=True)
class BaseServiceConfig:
    name: str
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

    def resolve_command(self) -> list[str]:
        return [self.python, "-m", self.module, *self.args]


@dataclass(kw_only=True)
class ScriptServiceConfig(BaseServiceConfig):
    exec: str
    args: list[str] = field(default_factory=list)

    def resolve_command(self) -> list[str]:
        return [self.exec, *self.args]


ServiceConfig = Union[PythonServiceConfig, ScriptServiceConfig]


@dataclass(kw_only=True)
class Config:
    default_server: Optional[ServerConfig] = None
    servers: dict[str, ServerConfig] = field(default_factory=dict)
    services: list[ServiceConfig] = field(default_factory=list)

    def insert_root_service(
        self, config_path: Path, *, host: str, port: int, reload: bool
    ) -> None:
        for svc in self.services:
            if svc.name == ":root:":
                return

        root_service = PythonServiceConfig(
            name=":root:",
            python=sys.executable,
            module="glue.web.main",
            args=[
                str(config_path),
                "--host",
                host,
                "--port",
                str(port),
                *(["--reload"] if reload else []),
            ],
        )
        self.services.insert(0, root_service)


def load_config(path: Path) -> Config:
    data = tomllib.loads(path.read_text())
    return typecast(Config, data)
