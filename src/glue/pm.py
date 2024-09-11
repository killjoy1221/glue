from __future__ import annotations

import os
import pty
import signal
import subprocess
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.control import Control

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
        self.process: subprocess.Popen[bytes] | None = None

    def shutdown(self) -> None:
        if self.process is not None:
            self.process.send_signal(signal.SIGINT)
            try:
                self.process.wait(5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
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

        master_fd, slave_fd = pty.openpty()
        self.process = subprocess.Popen(  # noqa: S603
            command,
            cwd=Path(self.config.cwd).resolve(),
            stdin=subprocess.DEVNULL,
            stdout=slave_fd,
            stderr=slave_fd,
        )

        def target() -> None:
            assert self.process is not None
            while self.process.poll() is None:
                if data := os.read(master_fd, 1024):
                    write(data.decode())
            write("%")

        t = threading.Thread(target=target, daemon=True)
        t.start()

    def __del__(self) -> None:
        self.shutdown()
