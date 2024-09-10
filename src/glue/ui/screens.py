from typing import ClassVar

from rich.console import RenderableType
from rich.control import Control
from rich.segment import ControlType
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, RichLog

from glue.pm import ServiceInstance

from .commands import BaseCommandProvider, cmd


class ProcessCommands(BaseCommandProvider):
    @cmd("Restart Service", discovery=True)
    async def restart_service(self) -> None:
        assert isinstance(self.screen, ProcessLogScreen)
        await self.screen.run_action("restart_service")


class ProcessLogScreen(Screen):
    COMMANDS: ClassVar = {ProcessCommands}
    BINDINGS: ClassVar = [
        Binding("ctrl+r", "restart_service", "Restart", show=False),
    ]

    ALLOW_MAXIMIZE = False

    def __init__(self, instance: ServiceInstance) -> None:
        super().__init__(name=instance.config.name)
        self.instance = instance
        self.widget_log = RichLog()

        self.instance.start(self.write_log)
        self.title = self.instance.config.name

    def write_log(self, text: RenderableType) -> None:
        if isinstance(text, Control):
            for code in text.segment.control or ():
                if ControlType.CLEAR in code:
                    self.widget_log.clear()
                    break
            return

        if isinstance(text, str):
            text = Text.from_ansi(text)

        self.widget_log.write(text)

    def action_restart_service(self) -> None:
        self.instance.restart(self.write_log)

    def compose(self) -> ComposeResult:
        yield Header()
        yield self.widget_log
        yield Footer()
