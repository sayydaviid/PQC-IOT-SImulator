"""Fornece registro estruturado e proteção de dados sensíveis nos logs."""

from datetime import datetime
from typing import Any
import threading


class Logger:
    # Por seguranca, o logger comeca desativado; chame `Logger.activate()`
    # para ligá-lo explicitamente.
    """Registra eventos da plataforma e controla a saída detalhada."""
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
        """Inicializa a instância e prepara seu estado interno.

        Parâmetros:
            name: Nome usado para identificar o objeto ou protocolo.
            verbose: Indica se a saída detalhada será exibida.
        """
        self.name = name
        self.events: list[dict[str, Any]] = []

        if verbose is not None:
            self.verbose = verbose

    @classmethod
    def activate(cls):
        """Ativa globalmente a emissão de logs."""
        previously = cls.active
        cls.active = True
        if not previously:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"{timestamp} | Logger ativado")

    @classmethod
    def deactivate(cls):
        """Desativa globalmente a emissão de logs."""
        previously = cls.active
        cls.active = False
        if previously:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"{timestamp} | Logger desativado")

    @classmethod
    def _redact_data(cls, data: Any):
        """Oculta chaves, segredos e credenciais dos dados de log."""
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
        """Ativa ou desativa a saída detalhada.

        Parâmetros:
            verbose: Indica se a saída detalhada será exibida.
        """
        self.verbose = verbose

    def log(
        self,
        message: str,
        data: dict[str, Any] | None = None,
        level: str = "INFO",
        component: str | None = None
    ):
        """Registra uma mensagem e seus dados associados.

        Parâmetros:
            message: Mensagem processada pela operação.
            data: Dados processados pela operação.
            level: Nível atual da topologia em árvore.
            component: Componente responsável pelo evento.
        """
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
        """Remove os registros acumulados pelo componente."""
        with Logger._lock:
            self.events.clear()