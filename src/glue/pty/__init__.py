from __future__ import annotations

import os
from typing import TYPE_CHECKING, Protocol

if os.name == "nt":
    from ._winpty import spawn as _spawn
else:
    from ._unixpty import spawn as _spawn


__all__ = ["spawn", "Process"]


class Process(Protocol):
    def is_running(self) -> bool: ...
    def read(self, length: int) -> bytes: ...
    def write(self, data: bytes) -> None: ...
    def stop(self) -> None: ...


if TYPE_CHECKING:
    from collections.abc import Mapping

    def spawn(
        argv: list[str],
        *,
        cwd: os.PathLike,
        env: Mapping[str, str] | None = None,
    ) -> Process: ...
else:
    spawn = _spawn
