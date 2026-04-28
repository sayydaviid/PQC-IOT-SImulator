from __future__ import annotations

from pathlib import Path
from typing import Any

from ..components import Network, Logger
from ..engines import MininetWiFiEngine


class Simulation:
    def __init__(self, config_path: str | Path):
        self.config_path = Path(config_path)
        self.config = self._load_config()

        self.network: Network | None = None
        self.engine: MininetWiFiEngine | None = None

    def _load_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Config nao encontrado: {self.config_path}"
            )

        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError(
                "Dependencia PyYAML nao encontrada. Instale com: pip install PyYAML"
            ) from exc

        with open(self.config_path, "r", encoding="utf-8") as file:
            loaded = yaml.safe_load(file) or {}

        return self._merge_dicts(self._default_config(), loaded)

    def _default_config(self) -> dict[str, Any]:
        return {
            "simulation": {
                "activate_logger": True,
                "run_engine": False,
                "send_test_message": True,
                "collect_link_metrics": False,
                "test_source": "iot_1",
                "test_destination": "server_1",
                "test_payload": {
                    "sensor": "temperature",
                    "value": 28.5,
                    "unit": "celsius",
                    "message": "sample payload"
                }
            },
            "network": {
                "verbose": True,
                "topology": {
                    "name": "grade",
                    "params": {
                        "rows": 3,
                        "cols": 3
                    }
                },
                "protocol": "mqtt",
                "crypto": {
                    "mode": "classical",
                    "params": {}
                },
                "metrics": [
                    "latency",
                    "packet_loss",
                    "pdr",
                    "energy",
                    "crypto_time",
                    "message_overhead",
                    "link_metrics"
                ]
            },
            "engine": {
                "enabled": False,
                "type": "mininet_wifi",
                "params": {
                    "default_bw": 10,
                    "default_delay": "5ms",
                    "default_loss": 0,
                    "link_mode": "infrastructure",
                    "open_cli_on_start": False
                }
            }
        }

    def _merge_dicts(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        result = dict(base)

        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._merge_dicts(result[key], value)
            else:
                result[key] = value

        return result

    def build(self):
        sim_cfg = self.config.get("simulation", {})
        network_cfg = self.config.get("network", {})
        engine_cfg = self.config.get("engine", {})

        if sim_cfg.get("activate_logger", False):
            Logger.activate()
        else:
            Logger.deactivate()

        self.network = Network(verbose=bool(network_cfg.get("verbose", True)))

        topology_cfg = network_cfg.get("topology", {})
        topology_name = topology_cfg.get("name", "grade")
        topology_params = topology_cfg.get("params", {}) or {}

        self.network.set_ready_topology(topology_name, **topology_params)

        protocol = network_cfg.get("protocol")
        if protocol:
            self.network.set_protocol(protocol)

        crypto_cfg = network_cfg.get("crypto", {}) or {}
        crypto_mode = crypto_cfg.get("mode")
        if crypto_mode:
            crypto_params = crypto_cfg.get("params", {}) or {}
            self.network.set_crypto_mode(crypto_mode, **crypto_params)

        metrics = network_cfg.get("metrics")
        if metrics:
            self.network.set_metrics(metrics)

        if engine_cfg.get("enabled", False):
            self.engine = self._create_engine(engine_cfg)
            self.network.set_runtime_engine(self.engine)

        return self

    def _create_engine(self, engine_cfg: dict[str, Any]):
        engine_type = engine_cfg.get("type", "mininet_wifi")
        engine_params = engine_cfg.get("params", {}) or {}

        if engine_type != "mininet_wifi":
            raise ValueError(f"Engine nao suportada: {engine_type}")

        if self.network is None:
            raise RuntimeError("Network precisa ser criada antes da engine.")

        return MininetWiFiEngine(
            network=self.network,
            logger=self.network.logger,
            **engine_params
        )

    def run(self):
        if self.network is None:
            self.build()

        if self.network is None:
            raise RuntimeError("Network nao inicializada.")

        sim_cfg = self.config.get("simulation", {})
        run_engine = bool(sim_cfg.get("run_engine", False))

        engine_started = False

        try:
            if self.engine and run_engine:
                self.engine.build()
                self.engine.start()
                engine_started = True
            else:
                self.network.build()

            if not sim_cfg.get("send_test_message", False):
                return None

            source = sim_cfg.get("test_source", "iot_1")
            destination = sim_cfg.get("test_destination", "server_1")
            payload = sim_cfg.get("test_payload", {})

            link_metrics = None

            if self.engine and run_engine and sim_cfg.get("collect_link_metrics", False):
                link_metrics = self._safe_collect_link_metrics(
                    source=source,
                    destination=destination
                )

            return self.network.send(
                source=source,
                destination=destination,
                payload=payload,
                link_metrics=link_metrics
            )

        finally:
            if self.engine and engine_started:
                self.engine.stop()

    def _safe_collect_link_metrics(self, source: str, destination: str):
        if self.engine is None:
            return None

        try:
            return self.engine.collect_link_metrics(
                source=source,
                destination=destination
            )
        except Exception:
            return None
