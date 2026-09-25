"""Fornece primitivas para contabilização física de energia."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable
import csv


class BatteryDepletedError(RuntimeError):
    """Indica uma carga solicitada após o esgotamento da bateria."""


def load_energy_j(voltage_v: float, current_a: float, duration_seconds: float) -> float:
    """Calcula energia por E = V × I × t com validação estrita.

    Parâmetros:
        voltage_v: Tensão aplicada à carga, em volts.
        current_a: Corrente consumida pela carga, em ampères.
        duration_seconds: Duração da carga, em segundos.

    Retorna:
        Energia exigida pela carga, em joules.
    """

    if voltage_v <= 0:
        raise ValueError("voltage_v must be greater than zero")
    if current_a < 0:
        raise ValueError("current_a cannot be negative")
    if duration_seconds < 0:
        raise ValueError("duration_seconds cannot be negative")
    return voltage_v * current_a * duration_seconds


def battery_energy_j(load_energy: float, regulator_efficiency: float) -> float:
    """Converte joules da carga em joules retirados da bateria.

    Parâmetros:
        load_energy: Energia exigida pela carga, em joules.
        regulator_efficiency: Eficiência do regulador entre zero e um.

    Retorna:
        Energia retirada da bateria, em joules.
    """

    if load_energy < 0:
        raise ValueError("load_energy_j cannot be negative")
    if not 0 < regulator_efficiency <= 1:
        raise ValueError("regulator_efficiency must be in the interval (0, 1]")
    return load_energy / regulator_efficiency


@dataclass(frozen=True)
class PowerState:
    """Representa tensão, corrente e origem de um estado de energia."""
    name: str
    voltage_v: float
    current_ma: float
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Valida e normaliza os campos após a criação do objeto."""
        if not self.name:
            raise ValueError("PowerState.name cannot be empty")
        if self.voltage_v <= 0:
            raise ValueError("PowerState.voltage_v must be greater than zero")
        if self.current_ma < 0:
            raise ValueError("PowerState.current_ma cannot be negative")
        if not self.source:
            raise ValueError("PowerState.source cannot be empty")

    @property
    def current_a(self) -> float:
        """Retorna a corrente do estado em ampères.

        Retorna:
            Valor numérico calculado.
        """
        return self.current_ma / 1000.0

    @property
    def power_w(self) -> float:
        """Retorna a potência elétrica do estado em watts.

        Retorna:
            Valor numérico calculado.
        """
        return self.voltage_v * self.current_a


@dataclass
class EnergyEvent:
    """Registra o consumo energético de um componente em um intervalo."""
    host_id: str
    component: str
    state: str
    reason: str
    started_at: float
    duration_seconds: float
    current_ma: float
    voltage_v: float
    load_energy_j: float
    battery_energy_j: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Converte o objeto em um dicionário serializável.

        Retorna:
            Dicionário com os dados produzidos.
        """
        return asdict(self)


@dataclass
class Battery:
    """Modela capacidade, carga restante e estado de uma bateria."""
    chemistry: str
    nominal_voltage_v: float
    capacity_mah: float
    usable_fraction: float = 1.0
    initial_soc_percent: float = 100.0
    consumed_j: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        """Valida e normaliza os campos após a criação do objeto."""
        if self.nominal_voltage_v <= 0:
            raise ValueError("nominal_voltage_v must be greater than zero")
        if self.capacity_mah < 0:
            raise ValueError("capacity_mah cannot be negative")
        if not 0 < self.usable_fraction <= 1:
            raise ValueError("usable_fraction must be in the interval (0, 1]")
        if not 0 <= self.initial_soc_percent <= 100:
            raise ValueError("initial_soc_percent must be in the interval [0, 100]")
        if not self.chemistry:
            raise ValueError("chemistry cannot be empty")

    @property
    def nominal_capacity_wh(self) -> float:
        """Calcula a capacidade nominal da bateria em watt-hora.

        Retorna:
            Valor numérico calculado.
        """
        return self.nominal_voltage_v * self.capacity_mah / 1000.0

    @property
    def usable_capacity_wh(self) -> float:
        """Calcula a capacidade utilizável da bateria em watt-hora.

        Retorna:
            Valor numérico calculado.
        """
        return self.nominal_capacity_wh * self.usable_fraction

    @property
    def capacity_j(self) -> float:
        """Calcula a capacidade utilizável da bateria em joules.

        Retorna:
            Valor numérico calculado.
        """
        return self.usable_capacity_wh * 3600.0

    @property
    def initial_j(self) -> float:
        """Calcula a energia disponível na carga inicial.

        Retorna:
            Valor numérico calculado.
        """
        return self.capacity_j * self.initial_soc_percent / 100.0

    @property
    def remaining_j(self) -> float:
        """Retorna a energia restante da bateria em joules.

        Retorna:
            Valor numérico calculado.
        """
        return max(0.0, self.initial_j - self.consumed_j)

    @property
    def remaining_wh(self) -> float:
        """Retorna a energia restante da bateria em watt-hora.

        Retorna:
            Valor numérico calculado.
        """
        return self.remaining_j / 3600.0

    @property
    def state_of_charge_percent(self) -> float:
        """Calcula o estado de carga restante em porcentagem.

        Retorna:
            Valor numérico calculado.
        """
        if self.capacity_j == 0:
            return 0.0
        return 100.0 * self.remaining_j / self.capacity_j

    @property
    def is_depleted(self) -> bool:
        """Informa se a bateria está esgotada.

        Retorna:
            True quando a condição é satisfeita; caso contrário, False.
        """
        return self.remaining_j <= 0.0

    def consume_joules(self, energy_j: float, *, reason: str = "load") -> float:
        """Retira da bateria a energia solicitada.

        Parâmetros:
            energy_j: Energia consumida, em joules.
            reason: Motivo associado ao estado ou à falha.

        Retorna:
            Valor numérico calculado.
        """
        if energy_j < 0:
            raise ValueError("energy_j cannot be negative")
        if energy_j == 0:
            if self.is_depleted:
                raise BatteryDepletedError(
                    f"battery is depleted; cannot account for {reason}"
                )
            return self.remaining_j
        if self.is_depleted:
            raise BatteryDepletedError(
                f"battery is depleted; cannot supply {energy_j:.9f} J for {reason}"
            )
        if energy_j > self.remaining_j + 1e-12:
            raise BatteryDepletedError(
                f"battery has {self.remaining_j:.9f} J but {energy_j:.9f} J "
                f"is required for {reason}"
            )
        self.consumed_j = min(self.initial_j, self.consumed_j + energy_j)
        return self.remaining_j

    def exhaust(self, *, reason: str = "unsatisfied load") -> None:
        """Invalida a energia restante após uma queda de tensão.

        Parâmetros:
            reason: Motivo registrado para o esgotamento ou débito.
        """

        if self.is_depleted:
            raise BatteryDepletedError(f"battery already depleted during {reason}")
        self.consumed_j = self.initial_j

    def estimated_runtime(self, average_power_w: float) -> float | None:
        """Retorna a autonomia em segundos ou None para potência zero.

        Parâmetros:
            average_power_w: Potência média consumida, em watts.

        Retorna:
            Autonomia restante em segundos ou None para potência zero.
        """

        if average_power_w < 0:
            raise ValueError("average_power_w cannot be negative")
        if average_power_w == 0:
            return None
        return self.remaining_j / average_power_w


class EnergyModel:
    """Consome a bateria e mantém um histórico auditável."""

    def __init__(
        self,
        host_id: str,
        battery: Battery,
        regulator_efficiency: float,
    ) -> None:
        """Inicializa a instância e prepara seu estado interno.

        Parâmetros:
            host_id: Identificador do host.
            battery: Bateria consumida pelo modelo energético.
            regulator_efficiency: Eficiência do regulador entre zero e um.
        """
        if not host_id:
            raise ValueError("host_id cannot be empty")
        if not 0 < regulator_efficiency <= 1:
            raise ValueError("regulator_efficiency must be in the interval (0, 1]")
        self.host_id = host_id
        self.battery = battery
        self.regulator_efficiency = regulator_efficiency
        self.events: list[EnergyEvent] = []

    def consume_state(
        self,
        state: PowerState,
        duration_seconds: float,
        *,
        component: str,
        reason: str,
        started_at: float,
        metadata: dict[str, Any] | None = None,
        load_energy_override_j: float | None = None,
    ) -> EnergyEvent:
        """Contabiliza o consumo de um estado elétrico.

        Parâmetros:
            state: Estado energético que será consumido.
            duration_seconds: Duração da operação, em segundos.
            component: Componente responsável pelo evento.
            reason: Motivo associado ao estado ou à falha.
            started_at: Instante em que a operação começou.
            metadata: Metadados adicionais associados ao objeto.
            load_energy_override_j: Energia da carga fornecida por calibração, em joules.

        Retorna:
            Evento energético registrado.
        """
        analytical_load_j = load_energy_j(state.voltage_v, state.current_a, duration_seconds)
        if load_energy_override_j is not None and load_energy_override_j < 0:
            raise ValueError("load_energy_override_j cannot be negative")
        load_j = analytical_load_j if load_energy_override_j is None else load_energy_override_j
        from_battery_j = battery_energy_j(load_j, self.regulator_efficiency)
        brownout = False
        supplied_battery_j = from_battery_j
        supplied_load_j = load_j
        supplied_duration = duration_seconds
        try:
            self.battery.consume_joules(from_battery_j, reason=reason)
        except BatteryDepletedError:
            available_j = self.battery.remaining_j
            if available_j <= 0:
                raise
            brownout = True
            supplied_battery_j = available_j
            supplied_load_j = available_j * self.regulator_efficiency
            supplied_duration = (
                duration_seconds * supplied_battery_j / from_battery_j
                if from_battery_j > 0
                else 0.0
            )
            self.battery.consume_joules(available_j, reason=f"partial {reason}")
        event = EnergyEvent(
            host_id=self.host_id,
            component=component,
            state=state.name,
            reason=reason,
            started_at=started_at,
            duration_seconds=supplied_duration,
            current_ma=state.current_ma,
            voltage_v=state.voltage_v,
            load_energy_j=supplied_load_j,
            battery_energy_j=supplied_battery_j,
            metadata={
                "parameter_source": state.source,
                **state.metadata,
                **(metadata or {}),
                **(
                    {
                        "energy_accounting": "direct_load_energy_override",
                        "analytical_load_energy_j": analytical_load_j,
                    }
                    if load_energy_override_j is not None
                    else {"energy_accounting": "voltage_current_duration"}
                ),
                **({"brownout": True, "requested_battery_energy_j": from_battery_j} if brownout else {}),
            },
        )
        self.events.append(event)
        if brownout:
            raise BatteryDepletedError(
                f"battery depleted while supplying {reason}; "
                f"provided {supplied_battery_j:.9f} J of {from_battery_j:.9f} J"
            )
        return event

    def events_since(self, index: int) -> list[EnergyEvent]:
        """Retorna eventos registrados a partir de um índice.

        Parâmetros:
            index: Índice inicial usado na seleção.

        Retorna:
            Lista com os elementos produzidos.
        """
        return self.events[index:]

    def energy_by_component(self, events: Iterable[EnergyEvent] | None = None) -> dict[str, float]:
        """Soma a energia consumida por componente.

        Parâmetros:
            events: Eventos energéticos que serão agregados.

        Retorna:
            Dicionário com os dados produzidos.
        """
        totals: dict[str, float] = {}
        for event in events if events is not None else self.events:
            totals[event.component] = totals.get(event.component, 0.0) + event.battery_energy_j
        return totals


@dataclass(frozen=True)
class CalibrationRecord:
    """Representa um registro de calibração de tempo e consumo."""
    device: str
    operation: str
    voltage_v: float
    current_ma: float
    duration_seconds: float
    energy_j: float
    source: str
    energy_model: str = "v_i_t"
    throughput_bytes_per_second: float | None = None
    fixed_cost_seconds: float = 0.0
    estimation_status: str = "configured"
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        """Valida e normaliza os campos após a criação do objeto."""
        if self.voltage_v <= 0:
            raise ValueError("calibration voltage_v must be greater than zero")
        if self.current_ma < 0:
            raise ValueError("calibration current_ma cannot be negative")
        if self.duration_seconds < 0:
            raise ValueError("calibration duration_seconds cannot be negative")
        if self.energy_j < 0:
            raise ValueError("calibration energy_j cannot be negative")
        if self.throughput_bytes_per_second is not None and self.throughput_bytes_per_second <= 0:
            raise ValueError("throughput_bytes_per_second must be positive")
        if self.fixed_cost_seconds < 0:
            raise ValueError("fixed_cost_seconds cannot be negative")
        if self.energy_model not in {"v_i_t", "direct_event"}:
            raise ValueError("calibration energy_model must be v_i_t or direct_event")


def load_calibration_csv(path: str | Path) -> dict[str, CalibrationRecord]:
    """Carrega calibração de hardware e tempo sem alterar o código.

    Parâmetros:
        path: Caminho do arquivo de calibração.

    Retorna:
        Calibrações indexadas pelo nome da operação.
    """

    csv_path = Path(path)
    required = {
        "device",
        "operation",
        "voltage_v",
        "current_ma",
        "duration_seconds",
        "energy_j",
        "source",
    }
    records: dict[str, CalibrationRecord] = {}
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"calibration CSV is missing columns: {sorted(missing)}")
        for row in reader:
            record = CalibrationRecord(
                device=row["device"].strip(),
                operation=row["operation"].strip(),
                voltage_v=float(row["voltage_v"]),
                current_ma=float(row["current_ma"]),
                duration_seconds=float(row["duration_seconds"]),
                energy_j=float(row["energy_j"]),
                source=row["source"].strip(),
                energy_model=(row.get("energy_model") or "v_i_t").strip(),
                throughput_bytes_per_second=(
                    float(row["throughput_bytes_per_second"])
                    if (row.get("throughput_bytes_per_second") or "").strip()
                    else None
                ),
                fixed_cost_seconds=float(row.get("fixed_cost_seconds") or 0.0),
                estimation_status=(row.get("estimation_status") or "configured").strip(),
                metadata={
                    key: value.strip() if isinstance(value, str) else value
                    for key, value in row.items()
                    if key not in required
                    and key not in {
                        "energy_model", "throughput_bytes_per_second",
                        "fixed_cost_seconds", "estimation_status",
                    }
                    and value not in (None, "")
                },
            )
            if record.operation in records:
                raise ValueError(f"duplicate calibration operation: {record.operation}")
            records[record.operation] = record
    return records
