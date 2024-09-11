from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from functools import partial
from typing import Any, TypeVar

from textual.command import DiscoveryHit, Hit, Hits, Provider
from typing_extensions import TypeAlias

__all__ = [
    "cmd",
    "BaseCommandProvider",
    "Matricies",
]

AnyFunc: TypeAlias = "Callable[..., None] | Callable[..., Awaitable[None]]"

TFunc = TypeVar("TFunc", bound=AnyFunc)

Matricies: TypeAlias = Iterable[dict[str, Any]]


def default_matrix(_: Any) -> Matricies:
    yield {}


@dataclass
class Cmd:
    display: str
    matrix: Callable[[Provider], Matricies] = default_matrix
    help: str | None = None
    discovery: bool = False

    callback: Callable[..., None] | Callable[..., Awaitable[None]] = field(init=False)

    def __call__(self, f: TFunc) -> TFunc:
        self.callback = f
        f.__command__ = self  # type: ignore[union-attr]
        return f


cmd = Cmd


class BaseCommandProvider(Provider):
    async def startup(self) -> None:
        self.commands: list[Cmd] = [
            value.__command__
            for value in type(self).__dict__.values()
            if hasattr(value, "__command__")
        ]

    async def discover(self) -> Hits:
        for cmd in self.commands:
            if cmd.discovery:
                for kwargs in cmd.matrix(self):
                    yield DiscoveryHit(
                        display=cmd.display.format(**kwargs),
                        command=partial(cmd.callback, self, **kwargs),
                        help=cmd.help.format(**kwargs) if cmd.help else cmd.help,
                    )

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)

        def match(cmd: Cmd, **kwargs: Any) -> Iterable[Hit]:
            display = cmd.display.format(**kwargs)
            if (score := matcher.match(display)) > 0:
                yield Hit(
                    score=score,
                    match_display=matcher.highlight(display),
                    command=partial(cmd.callback, self, **kwargs),
                    help=cmd.help.format(**kwargs) if cmd.help else cmd.help,
                )

        for cmd in self.commands:
            for kwargs in cmd.matrix(self):
                for c in match(cmd, **kwargs):
                    yield c
