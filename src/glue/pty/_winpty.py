from __future__ import annotations

import os
from typing import TYPE_CHECKING

if os.name == "nt":
    from winpty import PtyProcess  # type: ignore
else:
    msg = f"{os.name} is not supported"
    raise ImportError(msg) from None

if TYPE_CHECKING:
    if os.name != "nt":
        from collections.abc import Mapping
        from typing import Self

        class PtyProcess:
            delayafterclose: int

            @classmethod
            def spawn(
                cls,
                argv: list[str],
                *,
                cwd: os.PathLike | None = ...,
                env: Mapping[str, str] | None = ...,
                dimensions: tuple[int, int] = ...,
                backend: int | None = ...,
            ) -> Self: ...
            def isalive(self) -> bool: ...
            def read(self, size: int = ...) -> bytes: ...
            def write(self, data: bytes) -> int: ...
            def terminate(self, *, force: bool = ...) -> bool: ...


class _WinProcess:
    def __init__(self, process: PtyProcess) -> None:
        self.process = process

    def is_running(self) -> bool:
        return self.process.isalive()

    def read(self, length: int) -> bytes:
        return self.process.read(length)

    def write(self, data: bytes) -> int:
        return self.process.write(data)

    def stop(self) -> None:
        if not self.process.terminate():
            self.process.terminate(force=True)


def spawn(
    argv: list[str],
    *,
    cwd: os.PathLike,
    env: Mapping[str, str] | None = None,
) -> _WinProcess:
    process = PtyProcess.spawn(argv, cwd=cwd, env=env)
    process.delayafterclose = 5
    return _WinProcess(process)
