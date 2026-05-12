from datetime import datetime
from typing import Any
import threading


class Logger:
    # Por seguranca, o logger comeca desativado; chame `Logger.activate()`
    # para ligá-lo explicitamente.
    active: bool = False
    verbose: bool = True
    global_events: list[dict[str, Any]] = []
    max_global_events: int = 10000
    max_instance_events: int = 2000
    redact_keys: set[str] = {
        "payload",
        "ciphertext",
        "nonce",
        "private_key",
        "shared_secret"
    }
    _lock = threading.Lock()

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
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"{timestamp} | Logger ativado")

    @classmethod
    def deactivate(cls):
        previously = cls.active
        cls.active = False
        if previously:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"{timestamp} | Logger desativado")

    @classmethod
    def _redact_data(cls, data: Any):
        if isinstance(data, dict):
            redacted = {}
            for key, value in data.items():
                if key in cls.redact_keys:
                    redacted[key] = "<redacted>"
                else:
                    redacted[key] = cls._redact_data(value)
            return redacted

        if isinstance(data, list):
            return [cls._redact_data(item) for item in data]

        return data

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

        safe_data = Logger._redact_data(data or {})

        event = {
            "timestamp": datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
            "level": level,
            "component": component or self.name,
            "message": message,
            "data": safe_data
        }

        with Logger._lock:
            self.events.append(event)
            Logger.global_events.append(event)

            if len(self.events) > self.max_instance_events:
                self.events = self.events[-self.max_instance_events:]

            if len(Logger.global_events) > Logger.max_global_events:
                Logger.global_events = Logger.global_events[-Logger.max_global_events:]

        if self.verbose and Logger.verbose:
            time_only = event["timestamp"].split(" ", 1)[-1]
            print(f"{time_only} | {event['message']}")

    def clear(self):
        with Logger._lock:
            self.events.clear()