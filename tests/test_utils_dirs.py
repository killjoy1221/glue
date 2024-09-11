from pathlib import Path

import pytest

from glue.utils import DirResolver, Dirs


class XDGDirs:
    user_state_path = Path("/test/.local/state/glue")
    user_runtime_path = Path("/run/test/glue")


@pytest.fixture
def dirs() -> Dirs:
    return Dirs("testapp", _dirs=XDGDirs())


def test_dirs(dirs: Dirs) -> None:
    assert str(dirs.runtime_dir) == "/run/test/glue/testapp"
    assert str(dirs.state_dir) == "/test/.local/state/glue/testapp"


def test_dirs_factory() -> None:
    pth = Path("/test/app/servers.toml")
    dirs = Dirs.from_path(pth)
    assert dirs.subdir == "qTIawyxhoT6"


def test_subdirs(dirs: Dirs) -> None:
    d2 = dirs / "app2"
    assert str(d2.runtime_dir) == "/run/test/glue/testapp/app2"
    assert str(d2.state_dir) == "/test/.local/state/glue/testapp/app2"


def test_dirs_resolve(dirs: Dirs) -> None:
    d2 = dirs / "app2"

    assert d2.resolve_vars_list(["{xdg_run}/app.sock", "{xdg_state}/stdout.log"]) == [
        "/run/test/glue/testapp/app2/app.sock",
        "/test/.local/state/glue/testapp/app2/stdout.log",
    ]


def test_namespaced_resolver(dirs: Dirs) -> None:
    d1 = dirs / "app2"
    d2 = dirs / "app3"

    args = [
        "{app2.xdg_run}/app2.sock",
        "{app3.xdg_state}/stdout.log",
    ]

    res = DirResolver({"app2": d1, "app3": d2})

    assert res.resolve_vars_list(args) == [
        "/run/test/glue/testapp/app2/app2.sock",
        "/test/.local/state/glue/testapp/app3/stdout.log",
    ]
