import os
from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import BaseRoute, Host, Mount

from glue.config import Config, load_config
from glue.utils import DirResolver, Dirs


def load_config_from_env() -> tuple[Config, DirResolver]:
    config_file = os.environ.get("GLUE_CONFIG_FILE")

    if not config_file:
        msg = "Config file was not set. Was the server started though `glue.web.main`?"
        raise AssertionError(msg)

    config_path = Path(config_file)

    config = load_config(config_path)
    dirs = Dirs.from_path(config_path)
    resolver = DirResolver({svc.name: dirs / svc.name for svc in config.services})

    return config, resolver


def create_app() -> Starlette:
    config, resolver = load_config_from_env()

    routes: list[BaseRoute] = []

    for name, server in config.servers.items():
        routes.append(Host(name, server.create_route(resolver), name=name))

    if config.default_server:
        routes.append(
            Mount(
                "",
                config.default_server.create_route(resolver),
                name="default-server",
            )
        )
    else:
        resp = Response("The resource is not available", status_code=502)
        routes.append(Mount("", resp))

    return Starlette(
        routes=routes,
    )
