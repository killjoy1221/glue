#!/usr/bin/env python3
import contextlib
import importlib.metadata
import importlib.util
import json
import logging
import os
import urllib.parse
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Annotated, Any

import rich
import typer
import uvicorn
import uvicorn.protocols.utils
from click import version_option
from rich.console import Console
from rich.panel import Panel
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import Response
from starlette.routing import BaseRoute, Host, Mount
from typer.core import TyperCommand
from uvicorn._types import WWWScope

from glue.config import Config, load_config
from glue.middleware import MountedLifespanMiddleware
from glue.typecast import TypeCastError

app = typer.Typer(add_completion=False)
out = rich.get_console()
err = Console(stderr=True)


def get_path_with_query_string(scope: WWWScope) -> str:
    scheme = scope.get("scheme", "http")

    for name, value in scope["headers"]:
        if name.lower() == b"host":
            host = value.decode("ascii")
            break
    else:
        host = None

    server = scope.get("server", None)
    path = scope["path"]
    query_string = scope.get("query_string", b"")

    url = f"{scheme}://"
    if host is not None:
        url += host
    elif server:
        host, port = server
        url += host
        if scheme == "http" and port != 80 or scheme == "https" and port != 443:
            url += f":{port}"
    url += path
    if query_string:
        url += f"?{query_string.decode('ascii')}"
    return url


# Include the full hostname in the log
uvicorn.protocols.utils.get_path_with_query_string = get_path_with_query_string


def create_app() -> Starlette:
    config_file = os.environ["GLUE_CONFIG_FILE"]
    port = os.environ["GLUE_PORT"]
    assert config_file
    config = load_config(Path(config_file))

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncGenerator[None, Any]:
        logger = logging.getLogger("uvicorn.error")
        for route in app.routes:
            if isinstance(route, Host):
                logger.info("Will serve VHost at http://%s:%s/", route.host, port)
        yield

    routes: list[BaseRoute] = []

    for name, server in config.servers.items():
        routes.append(Host(name, server.create_route(), name=name))

    if config.default_server:
        routes.append(
            Mount("", config.default_server.create_route(), name="default-server")
        )
    else:
        resp = Response("The resource is not available", status_code=502)
        routes.append(Mount("", resp))

    return Starlette(
        middleware=[Middleware(MountedLifespanMiddleware)],
        routes=routes,
        lifespan=lifespan,
    )


def uri_to_path(uri: str) -> str:
    p = urllib.parse.urlparse(uri)
    assert p.scheme == "file"
    return str(Path(p.netloc, p.path).absolute())


def get_editable_dirs() -> list[str]:
    direct_url = importlib.metadata.distribution("glue").read_text("direct_url.json")
    if direct_url:
        data = json.loads(direct_url)
        if data.get("dir_info", {}).get("editable", False):
            return [uri_to_path(data["url"])]
    return []


def get_service_paths(config: Config) -> list[str]:
    return [str(Path(c.cwd).absolute()) for c in config.services if c != "."]


class OptionableCommand(TyperCommand):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        version_option()(self)


@app.command(cls=OptionableCommand)
def main(
    config_path: Path,
    *,
    host: Annotated[str, typer.Option(help="The server host to bind")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="The server port to bind")] = 8000,
    reload: Annotated[bool, typer.Option(help="Enable config reloading")] = False,
) -> None:
    """Start and manage development infrastructure."""
    try:
        config = load_config(config_path)
    except TypeCastError as e:
        err.print(
            Panel(
                err.render_str(str(e)),
                title="Error",
                title_align="left",
                border_style="red",
            )
        )
        raise typer.Exit(1) from None

    os.environ["GLUE_HOST"] = host
    os.environ["GLUE_PORT"] = str(port)
    os.environ["GLUE_CONFIG_FILE"] = str(config_path.absolute())

    uvicorn.run(
        "glue.main:create_app",
        host=host,
        port=port,
        reload=reload,
        lifespan="on",
        timeout_graceful_shutdown=5,
        factory=True,
        reload_dirs=get_editable_dirs() if reload else None,
        reload_includes=[str(config_path)] if reload else None,
        reload_excludes=get_service_paths(config) if reload else None,
    )


if __name__ == "__main__":
    app()
