from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import platformdirs
from typing_extensions import Self

dirs = platformdirs.PlatformDirs("glue")


class Dirs:
    def __init__(self, subdir: Path | str) -> None:
        self._subdir = subdir

    def __truediv__(self, subdir: Path | str) -> Dirs:
        return Dirs(Path(self._subdir) / subdir)

    @property
    def runtime_dir(self) -> Path:
        return dirs.user_runtime_path / self._subdir

    @property
    def state_dir(self) -> Path:
        return dirs.user_state_path / self._subdir

    def build_namespace(self) -> dict[str, Path]:
        return {"xdg_run": self.runtime_dir, "xdg_state": self.state_dir}

    def resolve_vars(self, arg: str) -> str:
        return arg.format(**self.build_namespace())

    def resolve_vars_list(self, args: list[str]) -> list[str]:
        return [self.resolve_vars(arg) for arg in args]

    @classmethod
    def from_path(cls, path: Path) -> Self:
        return cls(
            base64.b64encode(
                hashlib.sha1(
                    str(path.resolve()).encode(), usedforsecurity=False
                ).digest()
            ).decode()[:11]
        )


class DirResolver:
    def __init__(self, dirs: dict[str, Dirs]) -> None:
        self._dirs = dirs

    def resolve_vars(self, arg: str) -> str:
        f_args: dict[str, Any] = {}
        for name, dirs in self._dirs.items():
            f_args[name] = SimpleNamespace(**dirs.build_namespace())
        return arg.format(**f_args)

    def resolve_vars_list(self, args: list[str]) -> list[str]:
        return [self.resolve_vars(arg) for arg in args]
