import contextlib
import logging
import os
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import Response
from starlette.routing import BaseRoute, Host, Mount

from glue.config import load_config
from glue.utils import DirResolver, Dirs

from .middleware import MountedLifespanMiddleware


def create_app() -> Starlette:
    config_file = os.environ.get("GLUE_CONFIG_FILE")
    port = os.environ.get("GLUE_PORT")

    if not config_file:
        msg = "Config file was not set. Was the server started though `glue.web.main`?"
        raise AssertionError(msg)

    dirs = Dirs.from_path(Path(config_file))
    config = load_config(Path(config_file))
    dir_resovler = DirResolver({svc.name: dirs / svc.name for svc in config.services})

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncGenerator[None, Any]:
        logger = logging.getLogger("uvicorn.error")
        for route in app.routes:
            if isinstance(route, Host):
                logger.info("Will serve VHost at http://%s:%s/", route.host, port)
        yield

    routes: list[BaseRoute] = []

    for name, server in config.servers.items():
        routes.append(Host(name, server.create_route(dir_resovler), name=name))

    if config.default_server:
        routes.append(
            Mount(
                "",
                config.default_server.create_route(dir_resovler),
                name="default-server",
            )
        )
    else:
        resp = Response("The resource is not available", status_code=502)
        routes.append(Mount("", resp))

    return Starlette(
        middleware=[Middleware(MountedLifespanMiddleware)],
        routes=routes,
        lifespan=lifespan,
    )
