from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.control import Control

from .pty import Process, spawn

if TYPE_CHECKING:
    from collections.abc import Callable

    from rich.console import RenderableType

    from glue.config import Config, ServiceConfig
    from glue.utils import Dirs


class ServiceManager:
    def __init__(self, dirs: Dirs, config: Config) -> None:
        self.config = config
        self.services = {
            svc.name: ServiceInstance(dirs / svc.name, svc) for svc in config.services
        }

    def shutdown(self) -> None:
        for svc in self.services.values():
            svc.shutdown()


class ServiceInstance:
    def __init__(self, dirs: Dirs, config: ServiceConfig) -> None:
        self.dirs = dirs
        self.config = config
        self.process: Process | None = None

    def shutdown(self) -> None:
        if self.process is not None:
            self.process.stop()
            self.process = None

    def restart(self, write: Callable[[RenderableType], Any]) -> None:
        self.shutdown()
        self.start(write)

    def start(self, write: Callable[[RenderableType], Any]) -> None:
        if self.process is not None:
            return

        write(Control.clear())

        self.dirs.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.dirs.state_dir.mkdir(parents=True, exist_ok=True)
        command = self.dirs.resolve_vars_list(self.config.resolve_command())

        write(f"$ cd {self.config.cwd} && {' '.join(command)}\n")

        self.process = process = spawn(
            command,
            cwd=Path(self.config.cwd).resolve(),
        )

        def target() -> None:
            data = b""
            while process.is_running():
                if data := process.read(1024):
                    write(data.decode())
            if not data.endswith(b"\n"):
                write("%")

        t = threading.Thread(target=target, daemon=True)
        t.start()

    def __del__(self) -> None:
        self.shutdown()
