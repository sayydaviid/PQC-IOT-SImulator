"""Gera cargas ambientais reproduzíveis para sensores BME280."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from random import Random
from typing import Any
import csv
import json
import math


@dataclass(frozen=True)
class EnvironmentalBounds:
    """Define limites válidos para variáveis ambientais."""
    temperature_c: tuple[float, float] = (-40.0, 85.0)
    humidity_percent: tuple[float, float] = (0.0, 100.0)
    pressure_hpa: tuple[float, float] = (300.0, 1100.0)


@dataclass
class WorkloadConfig:
    """Armazena parâmetros da carga de trabalho ambiental."""
    sample_interval_seconds: float = 60.0
    reconnect_wifi_each_cycle: bool = True
    payload_format: str = "compact_json"
    base_temperature_c: float = 28.0
    base_humidity_percent: float = 75.0
    base_pressure_hpa: float = 1008.0
    daily_temperature_amplitude_c: float = 0.0
    daily_humidity_amplitude_percent: float = 0.0
    daily_pressure_amplitude_hpa: float = 0.0
    temperature_noise_stddev_c: float = 0.2
    humidity_noise_stddev_percent: float = 0.5
    pressure_noise_stddev_hpa: float = 0.2
    synthetic_padding_bytes: int = 0
    csv_input: str | None = None
    wake_up_seconds: float = 0.005
    sensor_measurement_seconds: float = 0.010
    cpu_processing_seconds: float = 0.003
    bounds: EnvironmentalBounds = field(default_factory=EnvironmentalBounds)

    def __post_init__(self) -> None:
        """Valida e normaliza os campos após a criação do objeto."""
        if self.sample_interval_seconds <= 0:
            raise ValueError("sample_interval_seconds must be greater than zero")
        for name in (
            "temperature_noise_stddev_c",
            "humidity_noise_stddev_percent",
            "pressure_noise_stddev_hpa",
            "wake_up_seconds",
            "sensor_measurement_seconds",
            "cpu_processing_seconds",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.synthetic_padding_bytes < 0:
            raise ValueError("synthetic_padding_bytes cannot be negative")
        if self.payload_format != "compact_json":
            raise ValueError("only compact_json is currently supported")


def serialize_payload(payload: dict[str, Any], payload_format: str = "compact_json") -> bytes:
    """Serializa a telemetria no formato configurado.

    Parâmetros:
        payload: Conteúdo útil da mensagem.
        payload_format: Formato usado para serializar a telemetria.

    Retorna:
        Telemetria serializada em bytes.
    """
    if payload_format != "compact_json":
        raise ValueError(f"unsupported payload format: {payload_format}")
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


class EnvironmentalWorkloadGenerator:
    """Gera telemetria ambiental sintética e reproduzível."""
    def __init__(
        self,
        config: WorkloadConfig,
        *,
        random_seed: int,
        start_datetime: datetime,
    ) -> None:
        """Inicializa a instância e prepara seu estado interno.

        Parâmetros:
            config: Dicionário de configuração.
            random_seed: Semente usada para tornar a geração reproduzível.
            start_datetime: Data e hora de início da carga ambiental.
        """
        self.config = config
        self.random = Random(random_seed)
        self.start_datetime = start_datetime
        self._csv_rows = self._load_csv(config.csv_input) if config.csv_input else []

    @staticmethod
    def _load_csv(path: str) -> list[dict[str, str]]:
        """Carrega amostras ambientais de um arquivo CSV."""
        csv_path = Path(path)
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"temperature_c", "humidity_percent", "pressure_hpa"}
            missing = required.difference(reader.fieldnames or [])
            if missing:
                raise ValueError(f"workload CSV is missing columns: {sorted(missing)}")
            rows = list(reader)
        if not rows:
            raise ValueError("workload CSV cannot be empty")
        return rows

    @staticmethod
    def _clamp(value: float, limits: tuple[float, float]) -> float:
        """Limita um valor ao intervalo permitido."""
        lower, upper = limits
        if lower > upper:
            raise ValueError("environmental lower bound cannot exceed upper bound")
        return min(upper, max(lower, value))

    def _modeled_value(
        self,
        base: float,
        amplitude: float,
        noise_stddev: float,
        simulation_time_seconds: float,
        phase_radians: float,
    ) -> float:
        """Gera uma variável ambiental com ciclo diário e ruído."""
        daily = amplitude * math.sin(
            2.0 * math.pi * simulation_time_seconds / 86_400.0 + phase_radians
        )
        return base + daily + self.random.gauss(0.0, noise_stddev)

    def generate(
        self,
        *,
        device_id: str,
        sequence: int,
        simulation_time_seconds: float,
        battery_voltage_v: float,
        battery_soc_percent: float,
    ) -> dict[str, Any]:
        """Gera uma amostra de telemetria ambiental.

        Parâmetros:
            device_id: Identificador do dispositivo IoT.
            sequence: Número sequencial da amostra ou do ciclo.
            simulation_time_seconds: Instante simulado do ciclo, em segundos.
            battery_voltage_v: Tensão atual da bateria, em volts.
            battery_soc_percent: Estado de carga atual da bateria, em porcentagem.

        Retorna:
            Dicionário com os dados produzidos.
        """
        if sequence <= 0:
            raise ValueError("sequence must be positive")
        if simulation_time_seconds < 0:
            raise ValueError("simulation_time_seconds cannot be negative")

        if self._csv_rows:
            row = self._csv_rows[(sequence - 1) % len(self._csv_rows)]
            temperature = float(row["temperature_c"])
            humidity = float(row["humidity_percent"])
            pressure = float(row["pressure_hpa"])
        else:
            temperature = self._modeled_value(
                self.config.base_temperature_c,
                self.config.daily_temperature_amplitude_c,
                self.config.temperature_noise_stddev_c,
                simulation_time_seconds,
                -math.pi / 2.0,
            )
            humidity = self._modeled_value(
                self.config.base_humidity_percent,
                self.config.daily_humidity_amplitude_percent,
                self.config.humidity_noise_stddev_percent,
                simulation_time_seconds,
                math.pi / 2.0,
            )
            pressure = self._modeled_value(
                self.config.base_pressure_hpa,
                self.config.daily_pressure_amplitude_hpa,
                self.config.pressure_noise_stddev_hpa,
                simulation_time_seconds,
                0.0,
            )

        payload: dict[str, Any] = {
            "device_id": device_id,
            "sequence": sequence,
            "timestamp": (self.start_datetime + timedelta(seconds=simulation_time_seconds)).isoformat(),
            "temperature_c": round(
                self._clamp(temperature, self.config.bounds.temperature_c), 2
            ),
            "humidity_percent": round(
                self._clamp(humidity, self.config.bounds.humidity_percent), 2
            ),
            "pressure_hpa": round(
                self._clamp(pressure, self.config.bounds.pressure_hpa), 2
            ),
            "battery_voltage_v": round(battery_voltage_v, 3),
            "battery_soc_percent": round(battery_soc_percent, 3),
        }
        if self.config.synthetic_padding_bytes:
            # Explicitly experimental and deterministic; never confused with a sensor field.
            payload["experimental_padding"] = "0" * self.config.synthetic_padding_bytes
        return payload


def workload_from_mapping(data: dict[str, Any]) -> WorkloadConfig:
    """Cria a carga de trabalho a partir de um dicionário.

    Parâmetros:
        data: Dados processados pela operação.

    Retorna:
        Configuração validada da carga de trabalho.
    """
    bounds_data = data.get("limits", {}) or {}
    bounds = EnvironmentalBounds(
        temperature_c=tuple(bounds_data.get("temperature_c", (-40.0, 85.0))),
        humidity_percent=tuple(bounds_data.get("humidity_percent", (0.0, 100.0))),
        pressure_hpa=tuple(bounds_data.get("pressure_hpa", (300.0, 1100.0))),
    )
    return WorkloadConfig(
        sample_interval_seconds=float(data.get("sample_interval_seconds", 60.0)),
        reconnect_wifi_each_cycle=bool(data.get("reconnect_wifi_each_cycle", True)),
        payload_format=str(data.get("payload_format", "compact_json")),
        base_temperature_c=float(data.get("base_temperature_c", 28.0)),
        base_humidity_percent=float(data.get("base_humidity_percent", 75.0)),
        base_pressure_hpa=float(data.get("base_pressure_hpa", 1008.0)),
        daily_temperature_amplitude_c=float(data.get("daily_temperature_amplitude_c", 0.0)),
        daily_humidity_amplitude_percent=float(data.get("daily_humidity_amplitude_percent", 0.0)),
        daily_pressure_amplitude_hpa=float(data.get("daily_pressure_amplitude_hpa", 0.0)),
        temperature_noise_stddev_c=float(data.get("temperature_noise_stddev_c", 0.2)),
        humidity_noise_stddev_percent=float(data.get("humidity_noise_stddev_percent", 0.5)),
        pressure_noise_stddev_hpa=float(data.get("pressure_noise_stddev_hpa", 0.2)),
        synthetic_padding_bytes=int(data.get("synthetic_padding_bytes", 0)),
        csv_input=data.get("csv_input"),
        wake_up_seconds=float(data.get("wake_up_seconds", 0.005)),
        sensor_measurement_seconds=float(data.get("sensor_measurement_seconds", 0.010)),
        cpu_processing_seconds=float(data.get("cpu_processing_seconds", 0.003)),
        bounds=bounds,
    )
