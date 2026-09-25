"""Orquestra a simulação física executada sobre o Mininet-WiFi."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from ..components.crypto import CryptoManager
from ..components.device import PhysicalIoTDevice, load_device_profiles
from ..components.energy import BatteryDepletedError, load_calibration_csv
from ..components.logger import Logger
from ..components.metrics import PhysicalMetricsCollector
from ..components.mininet_coupling import apply_mininet_transport_observation
from ..components.network import Network
from ..components.workload import EnvironmentalWorkloadGenerator
from ..engines import MininetWiFiEngine


class Simulation:
    """Orquestra uma simulação física de IoT executada pelo Mininet-WiFi."""

    def __init__(self, config_path: str | Path | Network | None = None):
        """Inicializa a instância e prepara seu estado interno.

        Parâmetros:
            config_path: Caminho da configuração ou rede configurada.
        """
        default_path = (
            Path(__file__).resolve().parents[1] / "configs" / "default.yaml"
        )
        self._network_template: Network | None = None

        if isinstance(config_path, Network):
            self._network_template = config_path
            self.config_path = default_path
        elif config_path is None:
            self.config_path = default_path
        else:
            self.config_path = Path(config_path)

        self.config = self._load_config()
        if self._network_template is not None:
            self._network_template.apply_to_config(self.config)

        self.network: Network | None = None
        self.engine: MininetWiFiEngine | None = None
        self.devices: dict[str, PhysicalIoTDevice] = {}
        self.metrics_collector = PhysicalMetricsCollector()
        self.wallclock_execution_time_seconds = 0.0
        self.engine_limitation: str | None = None

    def _load_config(self) -> dict[str, Any]:
        """Carrega o YAML e o combina com a configuração padrão."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"config not found: {self.config_path}")
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError("PyYAML is required to load simulation configuration") from exc
        with self.config_path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        return self._merge_dicts(self._default_config(), loaded)

    def _default_config(self) -> dict[str, Any]:
        """Cria a configuração mínima padrão da simulação."""
        return {
            "simulation": {
                "duration_seconds": 3600,
                "random_seed": 42,
                "start_datetime": "2026-08-05T14:00:00-03:00",
                "activate_logger": True,
                "run_engine": True,
                "collect_link_metrics": True,
                "capture_packets": True,
                "require_packet_capture": True,
                "pcap_directory": None,
                "communication_correction_factor": 1.0,
                "test_destination": "server_1",
            },
            "devices": {},
            "device_profiles": {},
            "crypto_timing": {"mode": "target_profile", "operations": {}},
            "network": {
                "verbose": True,
                "topology": {"name": "grade", "params": {"rows": 3, "cols": 3}},
                "protocol": "mqtt",
                "crypto": {"mode": "classical", "params": {}},
                "default_conditions": {
                    "bandwidth_mbps": 10,
                    "latency_ms": 5,
                    "rtt_avg_ms": 10,
                    "packet_loss_percent": 0,
                },
            },
            "engine": {"enabled": True, "type": "mininet_wifi", "params": {}},
        }

    def _merge_dicts(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """Combina recursivamente dois dicionários sem alterar os originais."""
        result = deepcopy(base)
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_dicts(result[key], value)
            else:
                result[key] = deepcopy(value)
        return result

    def _invalidate_build(self) -> None:
        """Descarta objetos construídos após uma mudança de configuração."""
        self.devices = {}
        self.engine = None
        self.metrics_collector = PhysicalMetricsCollector()

    def _profile_config(self, profile: str) -> dict[str, Any]:
        """Localiza e valida um perfil físico pelo nome."""
        profiles = self.config.get("device_profiles", {}) or {}
        if profile not in profiles:
            raise ValueError(
                f"unknown device profile: {profile}. "
                f"Available profiles: {sorted(profiles)}"
            )
        return profiles[profile]

    def available_device_profiles(self) -> list[str]:
        """Lista os perfis físicos disponíveis.

        Retorna:
            Lista com os elementos produzidos.
        """
        return sorted((self.config.get("device_profiles", {}) or {}).keys())

    def device_profile(self, profile: str = "esp32_bme280_wifi") -> dict[str, Any]:
        """Retorna uma cópia do perfil solicitado.

        Parâmetros:
            profile: Nome do perfil físico.

        Retorna:
            Dicionário com os dados produzidos.
        """
        return deepcopy(self._profile_config(profile))

    def set_devices(
        self,
        *device_ids: str,
        profile: str = "esp32_bme280_wifi",
        destination: str = "server_1",
    ) -> "Simulation":
        """Seleciona os dispositivos IoT da simulação.

        Parâmetros:
            profile: Nome do perfil físico.
            destination: Identificador do destino.
            *device_ids: Identificadores dos dispositivos IoT.

        Retorna:
            A própria instância, permitindo encadear operações.
        """
        if not device_ids:
            raise ValueError("declare at least one IoT device")
        self._profile_config(profile)

        if self._network_template is not None:
            available_nodes = set(self._network_template.topology_data.nodes)
            missing = [device_id for device_id in device_ids if device_id not in available_nodes]
            if missing:
                raise ValueError(
                    f"devices are not present in the selected topology: {missing}"
                )

        self.config["devices"] = {
            str(device_id): {
                "profile": profile,
                "destination": destination,
            }
            for device_id in device_ids
        }
        self._invalidate_build()
        return self

    def set_duration(self, seconds: float) -> "Simulation":
        """Define a duração total representada pela simulação.

        Parâmetros:
            seconds: Valor de tempo, em segundos.

        Retorna:
            A própria instância, permitindo encadear operações.
        """
        if seconds <= 0:
            raise ValueError("duration must be greater than zero")
        self.config.setdefault("simulation", {})["duration_seconds"] = float(seconds)
        self._invalidate_build()
        return self

    def set_sample_interval(
        self,
        seconds: float,
        profile: str = "esp32_bme280_wifi",
    ) -> "Simulation":
        """Define o intervalo entre amostras.

        Parâmetros:
            seconds: Valor de tempo, em segundos.
            profile: Nome do perfil físico.

        Retorna:
            A própria instância, permitindo encadear operações.
        """
        if seconds <= 0:
            raise ValueError("sample interval must be greater than zero")
        self._profile_config(profile).setdefault("workload", {})[
            "sample_interval_seconds"
        ] = float(seconds)
        self._invalidate_build()
        return self

    def set_battery(
        self,
        *,
        capacity_mah: float | None = None,
        initial_soc_percent: float | None = None,
        profile: str = "esp32_bme280_wifi",
    ) -> "Simulation":
        """Atualiza a capacidade e a carga inicial da bateria.

        Parâmetros:
            capacity_mah: Capacidade da bateria em miliampère-hora.
            initial_soc_percent: Estado de carga inicial em porcentagem.
            profile: Nome do perfil físico.

        Retorna:
            A própria instância, permitindo encadear operações.
        """
        battery = self._profile_config(profile).setdefault("battery", {})
        if capacity_mah is not None:
            if capacity_mah <= 0:
                raise ValueError("battery capacity must be greater than zero")
            battery["capacity_mah"] = float(capacity_mah)
        if initial_soc_percent is not None:
            if not 0 <= initial_soc_percent <= 100:
                raise ValueError("initial battery state must be between 0 and 100")
            battery["initial_soc_percent"] = float(initial_soc_percent)
        self._invalidate_build()
        return self

    def set_session(
        self,
        *,
        lifetime_seconds: float | None = None,
        max_messages: int | None = None,
        profile: str = "esp32_bme280_wifi",
    ) -> "Simulation":
        """Atualiza a duração e o limite da sessão.

        Parâmetros:
            lifetime_seconds: Tempo de vida da sessão em segundos.
            max_messages: Quantidade máxima de mensagens da sessão.
            profile: Nome do perfil físico.

        Retorna:
            A própria instância, permitindo encadear operações.
        """
        session = self._profile_config(profile).setdefault("crypto_session", {})
        if lifetime_seconds is not None:
            if lifetime_seconds <= 0:
                raise ValueError("session lifetime must be greater than zero")
            session["lifetime_seconds"] = float(lifetime_seconds)
        if max_messages is not None:
            if max_messages <= 0:
                raise ValueError("session message limit must be greater than zero")
            session["max_messages"] = int(max_messages)
        self._invalidate_build()
        return self

    def set_link(
        self,
        *,
        bandwidth_mbps: float | None = None,
        latency_ms: float | None = None,
        packet_loss_percent: float | None = None,
    ) -> "Simulation":
        """Define banda, latência e perda do enlace.

        Parâmetros:
            bandwidth_mbps: Largura de banda em megabits por segundo.
            latency_ms: Latência em milissegundos.
            packet_loss_percent: Perda de pacotes em porcentagem.

        Retorna:
            A própria instância, permitindo encadear operações.
        """
        conditions = self.config.setdefault("network", {}).setdefault(
            "default_conditions", {}
        )
        engine = self.config.setdefault("engine", {}).setdefault("params", {})

        if bandwidth_mbps is not None:
            if bandwidth_mbps <= 0:
                raise ValueError("bandwidth must be greater than zero")
            conditions["bandwidth_mbps"] = float(bandwidth_mbps)
            engine["default_bw"] = float(bandwidth_mbps)
        if latency_ms is not None:
            if latency_ms < 0:
                raise ValueError("latency cannot be negative")
            conditions["latency_ms"] = float(latency_ms)
            conditions["rtt_avg_ms"] = 2 * float(latency_ms)
            engine["default_delay"] = f"{latency_ms}ms"
        if packet_loss_percent is not None:
            if not 0 <= packet_loss_percent <= 100:
                raise ValueError("packet loss must be between 0 and 100")
            conditions["packet_loss_percent"] = float(packet_loss_percent)
            engine["default_loss"] = float(packet_loss_percent)

        self._invalidate_build()
        return self

    def set_calibration(
        self,
        csv_path: str | Path,
        *,
        strict: bool = True,
    ) -> "Simulation":
        """Seleciona o arquivo de calibração criptográfica.

        Parâmetros:
            csv_path: Caminho do CSV de calibração.
            strict: Indica se a validação deve ser estrita.

        Retorna:
            A própria instância, permitindo encadear operações.
        """
        path = Path(csv_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"calibration file not found: {path}")
        timing = self.config.setdefault("crypto_timing", {})
        timing["mode"] = "target_profile"
        timing["calibration_csv"] = str(path)
        timing["strict_target_calibration"] = bool(strict)
        self._invalidate_build()
        return self

    def set_output(self, directory: str | Path) -> "Simulation":
        """Define onde métricas e PCAP serão salvos.

        Parâmetros:
            directory: Diretório de saída.

        Retorna:
            A própria instância, permitindo encadear operações.
        """
        output = Path(directory).expanduser().resolve()
        simulation = self.config.setdefault("simulation", {})
        simulation["capture_packets"] = True
        simulation["require_packet_capture"] = True
        simulation["pcap_directory"] = str(output / "pcap")
        self.config["output"] = {
            "json": str(output / "resultado.json"),
            "csv": str(output / "ciclos.csv"),
        }
        self._invalidate_build()
        return self

    def _target_operations(self) -> dict[str, Any]:
        """Carrega as calibrações das operações criptográficas do dispositivo-alvo."""
        timing = self.config.get("crypto_timing", {}) or {}
        operations: dict[str, Any] = dict(timing.get("operations", {}) or {})
        calibration_csv = timing.get("calibration_csv")
        if calibration_csv:
            calibration_path = Path(calibration_csv)
            if not calibration_path.is_absolute():
                calibration_path = self.config_path.parent / calibration_path
            operations.update(load_calibration_csv(calibration_path))
        return operations

    def build(self) -> "Simulation":
        """Prepara o componente para execução.

        Retorna:
            A própria instância, permitindo encadear operações.
        """
        sim_cfg = self.config.get("simulation", {}) or {}
        network_cfg = self.config.get("network", {}) or {}
        engine_cfg = self.config.get("engine", {}) or {}
        if sim_cfg.get("activate_logger", False):
            Logger.activate()
        else:
            Logger.deactivate()

        if self._network_template is not None:
            self._network_template.apply_to_config(self.config)
            self.network = self._network_template
            self.network.set_verbose(bool(network_cfg.get("verbose", True)))
        else:
            self.network = Network(verbose=bool(network_cfg.get("verbose", True)))

        topology = network_cfg.get("topology", {}) or {}
        self.network.set_ready_topology(
            topology.get("name", "grade"),
            **(topology.get("params", {}) or {}),
        )
        protocol = network_cfg.get("protocol", "mqtt")
        self.network.set_protocol(protocol)
        crypto_cfg = network_cfg.get("crypto", {}) or {}
        crypto_mode = crypto_cfg.get("mode", "classical")
        crypto_params = crypto_cfg.get("params", {}) or {}
        self.network.set_crypto_mode(crypto_mode, **crypto_params)
        if network_cfg.get("metrics"):
            self.network.set_metrics(network_cfg["metrics"])

        profiles = load_device_profiles(self.config)
        devices_cfg = self.config.get("devices", {}) or {}
        if not devices_cfg:
            raise ValueError("configuration must declare at least one physical IoT device")
        timing_cfg = self.config.get("crypto_timing", {}) or {}
        target_operations = self._target_operations()
        start_datetime = datetime.fromisoformat(str(sim_cfg["start_datetime"]))
        seed = int(sim_cfg.get("random_seed", 42))
        self.devices = {}
        for index, (device_id, device_data) in enumerate(devices_cfg.items()):
            profile_name = str(device_data["profile"])
            if profile_name not in profiles:
                raise ValueError(f"unknown device profile for {device_id}: {profile_name}")
            profile = profiles[profile_name]
            csv_input = profile.workload.csv_input
            if csv_input:
                csv_path = Path(csv_input)
                if not csv_path.is_absolute():
                    profile.workload.csv_input = str(self.config_path.parent / csv_path)
            manager = CryptoManager(
                mode=crypto_mode,
                kem=str(crypto_params.get("kem", "ML-KEM-512")),
                pqc_signature=str(crypto_params.get("pqc_signature", "ML-DSA-44")),
                classical_signature=str(crypto_params.get("classical_signature", "ed25519")),
                use_classical_signature=bool(crypto_params.get("use_classical_signature", True)),
                use_pqc_signature=bool(crypto_params.get("use_pqc_signature", True)),
                timing_mode=str(timing_cfg.get("mode", "target_profile")),
                target_operations=target_operations,
                target_metadata={
                    key: timing_cfg.get(key)
                    for key in ("device", "firmware", "compiler", "implementation")
                },
                session_lifetime_seconds=profile.crypto_session.lifetime_seconds,
                session_max_messages=profile.crypto_session.max_messages,
                logger=self.network.logger,
            )
            generator = EnvironmentalWorkloadGenerator(
                profile.workload,
                random_seed=seed + index,
                start_datetime=start_datetime,
            )
            self.devices[device_id] = PhysicalIoTDevice(
                device_id,
                profile,
                manager,
                generator,
                destination=str(device_data.get("destination", sim_cfg.get("test_destination", "server_1"))),
                random_seed=seed + index,
                calibrations=target_operations,
            )

        if not engine_cfg.get("enabled", True):
            raise RuntimeError(
                "Mininet-WiFi e obrigatorio: engine.enabled nao pode ser false"
            )
        self.engine = self._create_engine(engine_cfg)
        self.network.set_runtime_engine(self.engine)
        return self

    def _create_engine(self, engine_cfg: dict[str, Any]) -> MininetWiFiEngine:
        """Cria o motor Mininet-WiFi a partir da configuração."""
        if engine_cfg.get("type", "mininet_wifi") != "mininet_wifi":
            raise ValueError(f"unsupported engine: {engine_cfg.get('type')}")
        if self.network is None:
            raise RuntimeError("network must be built before the engine")
        return MininetWiFiEngine(
            network=self.network,
            logger=self.network.logger,
            **(engine_cfg.get("params", {}) or {}),
        )

    def _conditions_for(self, device: PhysicalIoTDevice) -> dict[str, Any]:
        """Obtém as condições de enlace aplicáveis ao dispositivo."""
        conditions = dict(self.config.get("network", {}).get("default_conditions", {}) or {})
        sim_cfg = self.config.get("simulation", {}) or {}
        if not self.engine or not self.engine.is_running() or not sim_cfg.get("collect_link_metrics", False):
            return conditions
        try:
            measured = self.engine.collect_link_metrics(device.device_id, device.destination)
            conditions.update({key: value for key, value in measured.items() if value is not None})
        except Exception as exc:
            self.engine_limitation = f"Mininet-WiFi link metrics unavailable: {exc}"
            raise RuntimeError(self.engine_limitation) from exc
        return conditions

    def _pcap_path(self, device: PhysicalIoTDevice, sequence: int) -> Path | None:
        """Monta o caminho do PCAP de um ciclo."""
        sim_cfg = self.config.get("simulation", {}) or {}
        directory = sim_cfg.get("pcap_directory")
        if not directory:
            return None
        path = Path(str(directory))
        if not path.is_absolute():
            path = self.config_path.parent / path
        return path / f"{device.device_id}-{sequence:06d}.pcap"

    def _execute_cycle_in_mininet(
        self,
        device: PhysicalIoTDevice,
        cycle: Any,
    ) -> dict[str, Any]:
        """Transmite no Mininet as mensagens produzidas por um ciclo."""
        if self.engine is None or not self.engine.is_running():
            raise RuntimeError(
                "Mininet-WiFi precisa estar em execucao para processar um ciclo"
            )
        if not cycle.wire_messages:
            raise RuntimeError(
                f"ciclo {device.device_id}/{cycle.sequence} nao produziu mensagens de rede"
            )
        sim_cfg = self.config.get("simulation", {}) or {}
        capture_packets = bool(sim_cfg.get("capture_packets", False))
        observation = self.engine.execute_wire_messages(
            device.device_id,
            device.destination,
            cycle.wire_messages,
            transfer_id=f"simulation-{device.device_id}-{cycle.sequence:06d}",
            capture_packets=capture_packets,
            pcap_output_path=(
                self._pcap_path(device, cycle.sequence)
                if capture_packets else None
            ),
        )
        capture = dict(observation.get("packet_capture") or {})
        if (
            capture_packets
            and sim_cfg.get("require_packet_capture", False)
            and not capture.get("capture_available")
        ):
            raise RuntimeError(
                "PCAP obrigatorio indisponivel para "
                f"{device.device_id}/{cycle.sequence}: "
                f"{capture.get('error') or 'captura vazia'}"
            )
        return observation

    @staticmethod
    def _cycle_with_mininet_observation(
        cycle: Any,
        observation: dict[str, Any],
        *,
        observed_attempted: int,
        observed_delivered: int,
        communication_correction_factor: float,
    ) -> dict[str, Any]:
        """Mescla o ciclo modelado com a observação de transporte do Mininet."""
        row = cycle.to_dict()
        apply_mininet_transport_observation(
            row,
            observation,
            communication_correction_factor=communication_correction_factor,
        )
        row.update(
            {
                "messages_attempted": observed_attempted,
                "messages_delivered": observed_delivered,
                "messages_lost": observed_attempted - observed_delivered,
            }
        )
        return row

    def run(self) -> dict[str, Any]:
        """Executa o componente e retorna seus resultados.

        Retorna:
            Dicionário com os dados produzidos.
        """
        if not self.devices:
            self.build()
        sim_cfg = self.config.get("simulation", {}) or {}
        duration = float(sim_cfg.get("duration_seconds", 3600.0))
        if duration < 0:
            raise ValueError("simulation.duration_seconds cannot be negative")
        run_engine = bool(sim_cfg.get("run_engine", True))
        if not run_engine:
            raise RuntimeError(
                "Mininet-WiFi e obrigatorio: simulation.run_engine nao pode ser false"
            )
        if self.engine is None:
            raise RuntimeError("Mininet-WiFi e obrigatorio para executar a simulacao")
        wall_started = perf_counter()
        engine_started = False
        observed_counts = {
            device_id: {"attempted": 0, "delivered": 0}
            for device_id in self.devices
        }
        try:
            self.engine.build()
            self.engine.start()
            engine_started = True

            for device in self.devices.values():
                conditions = self._conditions_for(device)
                interval = device.profile.workload.sample_interval_seconds
                scheduled = 0.0
                available = 0.0
                while scheduled < duration:
                    start = max(scheduled, available)
                    if start >= duration:
                        break
                    budget = min(interval, duration - scheduled)
                    try:
                        cycle = device.run_cycle(
                            start,
                            network_conditions=conditions,
                            cycle_budget_seconds=budget,
                        )
                    except BatteryDepletedError:
                        break
                    observation = self._execute_cycle_in_mininet(device, cycle)
                    counts = observed_counts[device.device_id]
                    counts["attempted"] += 1
                    if observation.get("delivered"):
                        counts["delivered"] += 1
                    self.metrics_collector.record_cycle(
                        self._cycle_with_mininet_observation(
                            cycle,
                            observation,
                            observed_attempted=counts["attempted"],
                            observed_delivered=counts["delivered"],
                            communication_correction_factor=float(
                                sim_cfg.get(
                                    "communication_correction_factor",
                                    1.0,
                                )
                            ),
                        )
                    )
                    available = start + cycle.cycle_duration_seconds
                    scheduled += interval
                    if device.battery.is_depleted:
                        break
        finally:
            if engine_started:
                self.engine.stop()
            self.wallclock_execution_time_seconds = perf_counter() - wall_started

        output_cfg = self.config.get("output", {}) or {}
        if output_cfg.get("json"):
            self.export_metrics_json(str(output_cfg["json"]))
        if output_cfg.get("csv"):
            self.export_metrics_csv(str(output_cfg["csv"]))
        return self.results()

    def results(self) -> dict[str, Any]:
        """Retorna os resultados acumulados pela simulação.

        Retorna:
            Dicionário com os dados produzidos.
        """
        return {
            "simulation_time_seconds": float(self.config.get("simulation", {}).get("duration_seconds", 0.0)),
            "wallclock_execution_time_seconds": self.wallclock_execution_time_seconds,
            "engine": "mininet_wifi",
            "engine_limitation": self.engine_limitation,
            "summary": self.metrics_collector.get_summary(),
            "cycles": self.metrics_collector.get_cycles(),
        }

    def export_metrics_json(self, output_path: str) -> "Simulation":
        """Exporta as métricas para JSON.

        Parâmetros:
            output_path: Caminho do arquivo de saída.

        Retorna:
            A própria instância, permitindo encadear operações.
        """
        self.metrics_collector.export_json(
            output_path,
            metadata={
                "simulation_time_seconds": self.config.get("simulation", {}).get("duration_seconds"),
                "wallclock_execution_time_seconds": self.wallclock_execution_time_seconds,
                "engine_limitation": self.engine_limitation,
            },
        )
        return self

    def export_metrics_csv(self, output_path: str) -> "Simulation":
        """Exporta as métricas para CSV.

        Parâmetros:
            output_path: Caminho do arquivo de saída.

        Retorna:
            A própria instância, permitindo encadear operações.
        """
        self.metrics_collector.export_csv(output_path)
        return self
