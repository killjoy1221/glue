from __future__ import annotations

import os
import pty
import signal
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


class _UnixProcess:
    def __init__(self, process: subprocess.Popen[bytes], master_fd: int) -> None:
        self.process = process
        self.master_fd = master_fd

    def is_running(self) -> bool:
        return self.process.poll() is None

    def read(self, length: int) -> bytes:
        return os.read(self.master_fd, length)

    def write(self, data: bytes) -> int:
        return os.write(self.master_fd, data)

    def stop(self) -> None:
        self.process.send_signal(signal.SIGINT)
        try:
            self.process.wait(5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


def spawn(
    argv: list[str],
    *,
    cwd: os.PathLike,
    env: Mapping[str, str] | None = None,
) -> _UnixProcess:
    master_fd, slave_fd = pty.openpty()
    process = subprocess.Popen(  # noqa: S603
        argv,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=slave_fd,
        stderr=slave_fd,
    )
    return _UnixProcess(process, master_fd)
