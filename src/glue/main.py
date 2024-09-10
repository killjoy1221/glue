import sys
from pathlib import Path

import click
import rich
from click.exceptions import Exit
from rich.console import Console

from glue.pm import ServiceManager
from glue.utils import Dirs

from .config import PythonServiceConfig, load_config
from .typecast import TypeCastError
from .ui import GlueApp

out = rich.get_console()
err = Console(stderr=True)


@click.command()
@click.argument("config_path", type=Path)
@click.option("--host", type=str, default="127.0.0.1")
@click.option("--port", type=int, default=8000)
@click.option("--reload", type=bool, is_flag=True)
@click.version_option()
def main(config_path: Path, *, host: str, port: int, reload: bool) -> None:
    try:
        config = load_config(config_path)
    except TypeCastError as e:
        err.print(e)
        raise Exit(1) from None

    config.services.insert(
        0,
        PythonServiceConfig(
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
        ),
    )

    dirs = Dirs.from_path(config_path)

    app = GlueApp(ServiceManager(dirs, config), port)

    app.run()


if __name__ == "__main__":
    main()
