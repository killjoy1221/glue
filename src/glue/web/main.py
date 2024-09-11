from __future__ import annotations

import importlib.metadata
import json
import os
import urllib.parse
from pathlib import Path
from typing import TypedDict

import click
import uvicorn
from typing_extensions import NotRequired

from glue.config import Config, load_config


def uri_to_path(uri: str) -> str:
    p = urllib.parse.urlparse(uri)
    assert p.scheme == "file"
    return str(Path(p.netloc, p.path).absolute())


class DirInfo(TypedDict, total=False):
    editable: bool


class DirectUrlJson(TypedDict):
    url: str
    dir_info: NotRequired[DirInfo]


def get_editable_dirs() -> list[str]:
    direct_url = importlib.metadata.distribution("glue").read_text("direct_url.json")
    if direct_url:
        data: DirectUrlJson = json.loads(direct_url)
        if data.get("dir_info", {}).get("editable", False):
            return [uri_to_path(data["url"])]
    return []


def get_service_paths(config: Config) -> list[str]:
    return [str(Path(c.cwd).absolute()) for c in config.services if c.cwd != "."]


@click.command()
@click.argument("config_path", type=Path)
@click.option("--host", type=str, default="127.0.0.1")
@click.option("--port", type=int, default=8000)
@click.option("--reload", type=bool, is_flag=True)
def main(config_path: Path, *, host: str, port: int, reload: bool) -> None:
    """Start and manage development infrastructure."""
    os.environ["GLUE_CONFIG_FILE"] = str(config_path.absolute())

    config = load_config(config_path)

    uvicorn.run(
        "glue.web.factory:create_app",
        host=host,
        port=port,
        reload=reload,
        lifespan="on",
        timeout_graceful_shutdown=5,
        factory=True,
        reload_dirs=get_editable_dirs() if reload else None,
        reload_includes=[str(config_path)] if reload else None,
        reload_excludes=get_service_paths(config) if reload else None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
