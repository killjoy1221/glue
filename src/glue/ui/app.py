from __future__ import annotations

import atexit
from typing import TYPE_CHECKING, Any, ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Header, Label

from .commands import BaseCommandProvider, Matricies, cmd
from .screens import ProcessLogScreen

if TYPE_CHECKING:
    from textual.command import Provider

    from glue.pm import ServiceManager


class RootAppCommands(BaseCommandProvider):
    def view_log_matrix(self: Provider) -> Matricies:
        app = self.app
        assert isinstance(app, GlueApp)
        for svc in app.app_names:
            yield {"svc": svc}

    @cmd("View logs for {svc}", view_log_matrix)
    def view_logs(self, svc: str) -> None:
        try:
            self.app.switch_screen(svc)
        except IndexError:
            self.app.push_screen(svc)


class GlueApp(App):
    COMMANDS: ClassVar = App.COMMANDS | {RootAppCommands}
    BINDINGS: ClassVar = [
        *App.BINDINGS,
        Binding("escape", "home", "Home"),
        Binding("ctrl+z", "suspend_process"),
    ]

    CSS = """
    #home {
        align: center middle;
    }
    .app-url {
        link-background: dodgerblue;
    }
    """

    def __init__(self, mgr: ServiceManager, port: int) -> None:
        super().__init__()
        self.mgr = mgr
        atexit.register(mgr.shutdown)
        for index, (name, svc) in enumerate(mgr.services.items()):
            self.install_screen(ProcessLogScreen(svc), name)
            if index < 10:
                self.bind(str(index), f"view_logs('{name}')", description=name)
        self.app_names = list(mgr.services.keys())
        self.port = port

    def on_mount(self) -> None:
        self.push_screen(self.app_names[0])
        for x in self.app_names:
            self.switch_screen(x)
        self.pop_screen()

    def on_exit_app(self) -> None:
        self.mgr.shutdown()

    def action_view_logs(self, screen: str) -> None:
        if len(self.screen_stack) > 1:
            self.switch_screen(screen)
        else:
            self.push_screen(screen)

    def action_home(self) -> None:
        self.pop_screen()

    def check_action(self, action: str, parameters: tuple[Any, ...]) -> bool | None:
        if action == "home" and len(self.screen_stack) <= 1:
            return None
        if (
            action == "view_logs"
            and len(self.screen_stack) >= 1
            and self.screen.name == parameters[0]
        ):
            return None

        return super().check_action(action, parameters)

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Label("URLs:"),
            *(
                Label(f"http://{host}:{self.port}/", classes="app-url")
                for host in self.mgr.config.servers
            ),
            id="home",
        )
        yield Footer()
