from datetime import datetime
from typing import Any


class Logger:
    # Por seguranca, o logger comeca desativado; chame `Logger.activate()`
    # para ligá-lo explicitamente.
    active: bool = False
    verbose: bool = True
    global_events: list[dict[str, Any]] = []

    def __init__(self, name: str = "Logger", verbose: bool | None = None):
        self.name = name
        self.events: list[dict[str, Any]] = []

        if verbose is not None:
            self.verbose = verbose

    @classmethod
    def activate(cls):
        previously = cls.active
        cls.active = True
        if not previously:
            print("[INFO] Logger ativado")

    @classmethod
    def deactivate(cls):
        previously = cls.active
        cls.active = False
        if previously:
            print("[INFO] Logger desativado")

    @classmethod
    def set_global_verbose(cls, verbose: bool):
        cls.verbose = verbose

    def set_verbose(self, verbose: bool):
        self.verbose = verbose

    def log(
        self,
        message: str,
        data: dict[str, Any] | None = None,
        level: str = "INFO",
        component: str | None = None
    ):
        if not Logger.active:
            return

        event = {
            "timestamp": datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
            "level": level,
            "component": component or self.name,
            "message": message,
            "data": data or {}
        }

        self.events.append(event)
        Logger.global_events.append(event)

        if self.verbose and Logger.verbose:
            print(
                f"[{event['level']}] "
                f"{event['timestamp']} | "
                f"{event['component']} | "
                f"{event['message']} | "
                f"{event['data']}"
            )

    def info(
        self,
        message: str,
        data: dict[str, Any] | None = None,
        component: str | None = None
    ):
        self.log(
            message=message,
            data=data,
            level="INFO",
            component=component
        )

    def warning(
        self,
        message: str,
        data: dict[str, Any] | None = None,
        component: str | None = None
    ):
        self.log(
            message=message,
            data=data,
            level="WARNING",
            component=component
        )

    def error(
        self,
        message: str,
        data: dict[str, Any] | None = None,
        component: str | None = None
    ):
        self.log(
            message=message,
            data=data,
            level="ERROR",
            component=component
        )

    def get_events(self):
        return self.events

    @classmethod
    def get_global_events(cls):
        return cls.global_events

    def clear(self):
        self.events.clear()

    @classmethod
    def clear_global(cls):
        cls.global_events.clear()