"""Define perfis físicos e o ciclo discreto do ESP32 com BME280."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from copy import deepcopy
from time import perf_counter
from typing import Any

from .crypto import CryptoManager, CryptoOperation, CryptoResult, SessionEstablishmentResult
from .energy import Battery, BatteryDepletedError, CalibrationRecord, EnergyEvent, EnergyModel, PowerState
from .protocol import (
    CoAPConfig,
    HTTPConfig,
    MQTTConfig,
    ProtocolModel,
    RadioConfig,
    RadioModel,
)
from .workload import EnvironmentalWorkloadGenerator, WorkloadConfig, serialize_payload, workload_from_mapping


REQUIRED_POWER_STATES = {
    "deep_sleep",
    "wake_up",
    "sensor_measurement",
    "cpu_processing",
    "crypto_processing",
    "wifi_association",
    "wifi_tx",
    "wifi_rx",
    "mqtt_wait_ack",
    "idle",
}


@dataclass(frozen=True)
class BatteryProfile:
    """Descreve os parâmetros elétricos de uma bateria."""
    chemistry: str
    nominal_voltage_v: float
    capacity_mah: float
    usable_fraction: float
    regulator_efficiency: float
    initial_soc_percent: float = 100.0
    minimum_voltage_v: float = 3.2
    maximum_voltage_v: float = 4.2
    source: str = "user_configured"
    regulator_quiescent_current_ua: float | None = None


@dataclass(frozen=True)
class SensorProfile:
    """Descreve o sensor e seus parâmetros de consumo."""
    model: str
    sampling_rate_hz: float
    average_current_ua: float
    sleep_current_ua: float
    source: str


@dataclass(frozen=True)
class CryptoSessionPolicy:
    """Define quando uma sessão criptográfica deve ser renovada."""
    lifetime_seconds: float = 3600.0
    max_messages: int = 100
    rekey_on_restart: bool = True
    rtc_state_write: dict[str, Any] | None = None
    rtc_state_restore: dict[str, Any] | None = None
    rtc_state_validation: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Valida e normaliza os campos após a criação do objeto."""
        if self.lifetime_seconds <= 0:
            raise ValueError("crypto session lifetime_seconds must be positive")
        if self.max_messages <= 0:
            raise ValueError("crypto session max_messages must be positive")
        for name, parameters in (
            ("rtc_state_write", self.rtc_state_write),
            ("rtc_state_restore", self.rtc_state_restore),
            ("rtc_state_validation", self.rtc_state_validation),
        ):
            if parameters is None:
                continue
            missing = {
                "duration_seconds", "current_ma", "voltage_v", "source"
            }.difference(parameters)
            if missing:
                raise ValueError(f"{name} is missing parameters: {sorted(missing)}")
            if float(parameters["duration_seconds"]) <= 0:
                raise ValueError(f"{name}.duration_seconds must be positive")


@dataclass
class DeviceProfile:
    """Agrupa os parâmetros físicos e lógicos de um dispositivo IoT."""
    name: str
    board: str
    sensor: SensorProfile
    supply_voltage_v: float
    power_states: dict[str, PowerState]
    battery: BatteryProfile
    workload: WorkloadConfig
    mqtt: MQTTConfig
    coap: CoAPConfig
    http: HTTPConfig
    radio: RadioConfig
    crypto_session: CryptoSessionPolicy
    protocol: str = "mqtt"
    parameter_sources: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Valida e normaliza os campos após a criação do objeto."""
        if self.supply_voltage_v <= 0:
            raise ValueError("device supply_voltage_v must be positive")
        missing = REQUIRED_POWER_STATES.difference(self.power_states)
        if missing:
            raise ValueError(f"device profile is missing power states: {sorted(missing)}")

    @classmethod
    def from_mapping(cls, name: str, data: dict[str, Any]) -> "DeviceProfile":
        """Cria o objeto a partir de um dicionário de configuração.

        Parâmetros:
            name: Nome usado para identificar o objeto ou protocolo.
            data: Dados processados pela operação.

        Retorna:
            A própria instância, permitindo encadear operações.
        """
        voltage = float(data["supply_voltage_v"])
        power_states = {
            state_name: PowerState(
                name=state_name,
                voltage_v=float(state_data.get("voltage_v", voltage)),
                current_ma=float(state_data["current_ma"]),
                source=str(state_data["source"]),
                metadata=state_data.get("metadata", {}) or {},
            )
            for state_name, state_data in (data.get("power_states", {}) or {}).items()
        }
        sensor_data = data.get("sensor", {}) or {}
        battery_data = data.get("battery", {}) or {}
        mqtt_data = data.get("mqtt", {}) or {}
        coap_data = data.get("coap", {}) or {}
        http_data = data.get("http", {}) or {}
        radio_data = data.get("radio", {}) or {}
        session_data = data.get("crypto_session", {}) or {}
        return cls(
            name=name,
            board=str(data["board"]),
            sensor=SensorProfile(
                model=str(sensor_data["model"]),
                sampling_rate_hz=float(sensor_data.get("sampling_rate_hz", 1.0)),
                average_current_ua=float(sensor_data["average_current_ua"]),
                sleep_current_ua=float(sensor_data["sleep_current_ua"]),
                source=str(sensor_data["source"]),
            ),
            supply_voltage_v=voltage,
            power_states=power_states,
            battery=BatteryProfile(
                chemistry=str(battery_data["chemistry"]),
                nominal_voltage_v=float(battery_data["nominal_voltage_v"]),
                capacity_mah=float(battery_data["capacity_mah"]),
                usable_fraction=float(battery_data["usable_fraction"]),
                regulator_efficiency=float(battery_data["regulator_efficiency"]),
                initial_soc_percent=float(battery_data.get("initial_soc_percent", 100.0)),
                minimum_voltage_v=float(battery_data.get("minimum_voltage_v", 3.2)),
                maximum_voltage_v=float(battery_data.get("maximum_voltage_v", 4.2)),
                source=str(battery_data.get("source", "user_configured")),
                regulator_quiescent_current_ua=(
                    float(battery_data["regulator_quiescent_current_ua"])
                    if battery_data.get("regulator_quiescent_current_ua") is not None
                    else None
                ),
            ),
            workload=workload_from_mapping(data.get("workload", {}) or {}),
            mqtt=MQTTConfig(
                topic=str(mqtt_data["topic"]),
                qos=int(mqtt_data.get("qos", 1)),
                persistent_session=bool(mqtt_data.get("persistent_session", True)),
                client_id=str(mqtt_data.get("client_id", "pqc-iot-esp32-01")),
                clean_session=bool(mqtt_data.get("clean_session", False)),
                username=mqtt_data.get("username"),
                password=mqtt_data.get("password"),
                version=str(mqtt_data.get("version", "3.1.1")),
                tcp_ack_policy=str(mqtt_data.get("tcp_ack_policy", "response_piggyback")),
                connection_close_policy=str(
                    mqtt_data.get(
                        "connection_close_policy",
                        "abandon_before_deep_sleep_no_fin_modelled",
                    )
                ),
            ),
            coap=CoAPConfig(
                resource_path=str(
                    coap_data.get("resource_path", "sensors/environment")
                ),
                confirmable=bool(coap_data.get("confirmable", True)),
                token_length_bytes=int(coap_data.get("token_length_bytes", 2)),
                content_format=int(coap_data.get("content_format", 50)),
                version=str(coap_data.get("version", "1")),
            ),
            http=HTTPConfig(
                host=str(http_data.get("host", "server.local")),
                path=str(http_data.get("path", "/telemetry")),
                method=str(http_data.get("method", "POST")),
                version=str(http_data.get("version", "HTTP/1.1")),
                content_type=str(
                    http_data.get("content_type", "application/octet-stream")
                ),
                response_status=str(
                    http_data.get("response_status", "204 No Content")
                ),
                tcp_ack_policy=str(
                    http_data.get("tcp_ack_policy", "response_piggyback")
                ),
                connection_close_policy=str(
                    http_data.get(
                        "connection_close_policy",
                        "connection_close_after_response",
                    )
                ),
            ),
            radio=RadioConfig(
                effective_bitrate_bps=float(radio_data["effective_bitrate_bps"]),
                retry_model=str(radio_data.get("retry_model", "expected")),
                max_retries=int(radio_data.get("max_retries", 4)),
                association_duration_seconds=float(radio_data.get("association_duration_seconds", 0.25)),
                mqtt_ack_wait_seconds=float(radio_data.get("mqtt_ack_wait_seconds", 0.05)),
                handshake_round_trips=int(radio_data.get("handshake_round_trips", 1)),
                wifi_reconnect_energy_model=str(
                    radio_data.get("wifi_reconnect_energy_model", "incremental_direct_proxy")
                ),
                wifi_reconnect_proxy_multiplier=float(
                    radio_data.get("wifi_reconnect_proxy_multiplier", 1.0)
                ),
            ),
            crypto_session=CryptoSessionPolicy(
                lifetime_seconds=float(session_data.get("lifetime_seconds", 3600.0)),
                max_messages=int(session_data.get("max_messages", 100)),
                rekey_on_restart=bool(session_data.get("rekey_on_restart", True)),
                rtc_state_write=session_data.get("rtc_state_write"),
                rtc_state_restore=session_data.get("rtc_state_restore"),
                rtc_state_validation=session_data.get("rtc_state_validation"),
            ),
            protocol=str(data.get("protocol", "mqtt")),
            parameter_sources=data.get("parameter_sources", {}) or {},
        )


@dataclass
class DeviceCycleResult:
    """Registra as métricas produzidas por um ciclo do dispositivo."""
    device_id: str
    crypto_mode: str
    sequence: int
    simulation_time_seconds: float
    cycle_duration_seconds: float
    active_cycle_duration_seconds: float
    sleep_duration_seconds: float
    wallclock_execution_time_seconds: float
    status: str
    delivered: bool
    payload: dict[str, Any]
    energy_sensor_j: float
    energy_cpu_j: float
    energy_crypto_j: float
    energy_wifi_reconnect_initialization_proxy_j: float
    # Legacy alias retained for existing consumers.
    energy_wifi_association_j: float
    energy_tx_j: float
    energy_rx_j: float
    energy_sleep_j: float
    energy_rtc_state_j: float
    energy_total_iot_j: float
    energy_iot_node_j: float
    energy_gateway_j: float | None
    energy_server_j: float | None
    energy_network_total_j: float | None
    battery_remaining_j: float
    battery_remaining_wh: float
    battery_soc_percent: float
    estimated_battery_lifetime_hours: float | None
    estimated_battery_lifetime_days: float | None
    application_payload_bytes: int
    protected_message_bytes: int
    crypto_payload_bytes: int
    handshake_bytes: int
    handshake_protocol_overhead_bytes: int
    mqtt_connect_bytes: int
    mqtt_connack_bytes: int
    mqtt_publish_bytes: int
    mqtt_ack_bytes: int
    mqtt_bytes: int
    application_protocol: str
    protocol_request_bytes: int
    protocol_response_bytes: int
    application_protocol_bytes: int
    udp_header_bytes: int
    tcp_control_bytes: int
    tcp_header_bytes: int
    ip_header_bytes: int
    wifi_link_overhead_bytes: int
    transport_overhead_bytes: int
    link_overhead_bytes: int
    total_wire_bytes: float
    retransmitted_bytes: float
    handshake_count: int
    messages_in_session: int
    messages_attempted: int
    messages_delivered: int
    messages_lost: int
    deadline_missed: bool
    energy_confidence: str
    calibration_status: str
    energy_per_delivered_message_j: float | None
    energy_per_application_byte_j: float | None
    handshake_energy_in_measurement_j: float
    # Compatibility field.  It must not be interpreted as observed
    # amortization in the preexisting-state experiment.
    amortized_handshake_energy_j: float
    crypto_energy_percent: float
    communication_energy_percent: float
    radio_energy_percent: float
    link_latency_ms: float | None
    link_rtt_ms: float | None
    link_packet_loss_percent: float
    effective_bitrate_bps: float
    association_wait_seconds: float
    tcp_connect_wait_seconds: float
    crypto_handshake_wait_seconds: float
    mqtt_connect_wait_seconds: float
    mqtt_publish_wait_seconds: float
    protocol_response_wait_seconds: float
    tcp_ack_policy: str
    connection_close_policy: str
    battery_projection_interpretation: str
    battery_nominal_voltage_v: float
    battery_capacity_mah: float
    battery_usable_fraction: float
    regulator_efficiency: float
    publication_interval_seconds: float
    regulator_quiescent_current_ua: float | None
    rtc_state_write_energy_j: float | None
    rtc_state_restore_energy_j: float | None
    rtc_state_validation_energy_j: float | None
    rtc_state_write_status: str
    rtc_state_restore_status: str
    rtc_state_validation_status: str
    energy_events: list[dict[str, Any]] = field(default_factory=list)
    crypto_operations: list[dict[str, Any]] = field(default_factory=list)
    wire_messages: list[dict[str, Any]] = field(default_factory=list)
    handshake_plan: dict[str, Any] | None = None
    legacy_energy_fields_deprecated: bool = True
    crypto_energy_cost: float = 0.0
    total_energy_consumed: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Converte o objeto em um dicionário serializável.

        Retorna:
            Dicionário com os dados produzidos.
        """
        return asdict(self)


class PhysicalIoTDevice:
    """Simula o ciclo físico e energético de um dispositivo IoT."""
    def __init__(
        self,
        device_id: str,
        profile: DeviceProfile,
        crypto_manager: CryptoManager,
        workload_generator: EnvironmentalWorkloadGenerator,
        *,
        destination: str = "server_1",
        random_seed: int = 42,
        calibrations: dict[str, Any] | None = None,
    ) -> None:
        """Inicializa a instância e prepara seu estado interno.

        Parâmetros:
            device_id: Identificador do dispositivo IoT.
            profile: Nome do perfil físico.
            crypto_manager: Gerenciador criptográfico do dispositivo.
            workload_generator: Gerador de telemetria ambiental.
            destination: Identificador do destino.
            random_seed: Semente usada para tornar a geração reproduzível.
            calibrations: Registros de calibração disponíveis.
        """
        self.device_id = device_id
        self.profile = profile
        self.crypto_manager = crypto_manager
        self.workload_generator = workload_generator
        self.destination = destination
        self.battery = Battery(
            chemistry=profile.battery.chemistry,
            nominal_voltage_v=profile.battery.nominal_voltage_v,
            capacity_mah=profile.battery.capacity_mah,
            usable_fraction=profile.battery.usable_fraction,
            initial_soc_percent=profile.battery.initial_soc_percent,
        )
        self.energy_model = EnergyModel(
            device_id,
            self.battery,
            profile.battery.regulator_efficiency,
        )
        protocol_configs = {
            "mqtt": profile.mqtt,
            "coap": profile.coap,
            "http": profile.http,
        }
        protocol_name = profile.protocol.lower()
        if protocol_name not in protocol_configs:
            raise ValueError(f"unsupported physical protocol: {profile.protocol}")
        self.protocol_model = ProtocolModel.create(
            protocol_name,
            protocol_configs[protocol_name],
        )
        self.radio_model = RadioModel(profile.radio, random_seed=random_seed)
        self.sequence = 0
        self.wifi_connected = False
        self.messages_attempted = 0
        self.messages_delivered = 0
        self.messages_lost = 0
        self.handshake_energy_j = 0.0
        self.calibrations = calibrations or {}
        # ESP32 deep-sleep wake-up follows the reset boot path.  The flag is
        # consumed by the next cycle so rekey_on_restart can be honoured while
        # still allowing an explicitly retained session when the policy is off.
        self._woke_from_deep_sleep = False

    def _calibrated_state(
        self,
        operation: str,
        default_state_name: str,
        default_duration_seconds: float,
    ) -> tuple[PowerState, float]:
        """Obtém um estado elétrico calibrado ou usa o estado padrão."""
        default = self.profile.power_states[default_state_name]
        calibration = self.calibrations.get(operation)
        if isinstance(calibration, CalibrationRecord):
            calibration_metadata: dict[str, Any] = {
                "operation": operation,
                "energy_model": calibration.energy_model,
            }
            if calibration.energy_model == "direct_event":
                calibration_metadata["calibrated_load_energy_j"] = calibration.energy_j
            return (
                PowerState(
                    name=default_state_name,
                    voltage_v=calibration.voltage_v,
                    current_ma=calibration.current_ma,
                    source=calibration.source,
                    metadata=calibration_metadata,
                ),
                calibration.duration_seconds,
            )
        if isinstance(calibration, dict) and "duration_seconds" in calibration:
            calibration_metadata = {"operation": operation}
            calibration_metadata["energy_model"] = str(calibration.get("energy_model", "v_i_t"))
            if calibration_metadata["energy_model"] == "direct_event" and "energy_j" in calibration:
                calibration_metadata["calibrated_load_energy_j"] = float(calibration["energy_j"])
            return (
                PowerState(
                    name=default_state_name,
                    voltage_v=float(calibration.get("voltage_v", default.voltage_v)),
                    current_ma=float(calibration.get("current_ma", default.current_ma)),
                    source=str(calibration.get("source", "user_configured")),
                    metadata=calibration_metadata,
                ),
                float(calibration["duration_seconds"]),
            )
        return default, default_duration_seconds

    def _battery_voltage(self) -> float:
        """Calcula a tensão instantânea estimada da bateria."""
        battery = self.profile.battery
        fraction = self.battery.state_of_charge_percent / 100.0
        return battery.minimum_voltage_v + fraction * (
            battery.maximum_voltage_v - battery.minimum_voltage_v
        )

    def _wifi_reconnect_state(self) -> tuple[PowerState, float]:
        """Monta o estado energético usado na reconexão Wi-Fi."""
        model = self.profile.radio.wifi_reconnect_energy_model
        default = self.profile.power_states["wifi_association"]
        duration = self.profile.radio.association_duration_seconds
        calibration = self.calibrations.get("wifi_reconnect_initialization_proxy")
        if calibration is None:
            calibration = self.calibrations.get("wifi_association")  # legacy alias
        if model == "state_based_vit" or calibration is None:
            return default, duration
        if model == "disabled_for_sensitivity":
            return (
                PowerState(
                    "wifi_association", default.voltage_v, 0.0,
                    "configured_disabled_for_sensitivity",
                    metadata={
                        "energy_model": model,
                        "provenance": "configured_sensitivity_not_measurement",
                    },
                ),
                duration,
            )
        base_energy = (
            calibration.energy_j
            if isinstance(calibration, CalibrationRecord)
            else float(calibration["energy_j"])
        )
        source = (
            calibration.source
            if isinstance(calibration, CalibrationRecord)
            else str(calibration.get("source", "literature_derived_proxy"))
        )
        calibrated_duration = (
            calibration.duration_seconds
            if isinstance(calibration, CalibrationRecord)
            else float(calibration.get("duration_seconds", duration))
        )
        multiplier = self.profile.radio.wifi_reconnect_proxy_multiplier
        return (
            PowerState(
                "wifi_reconnect_initialization_proxy", default.voltage_v, 0.0,
                source,
                metadata={
                    "calibrated_load_energy_j": base_energy * multiplier,
                    "energy_model": "incremental_direct_proxy",
                    "provenance": "literature_derived_proxy",
                    "derivation_formula": "238.2_mJ_minus_19.8_mJ",
                    "original_source": "Wi-LE_HotNets_2019_aggregate_regimes",
                    "scope": "wake_initialization_wifi_association_dhcp_arp_message_incremental_proxy",
                    "scope_overlap_possible": True,
                    "proxy_multiplier": multiplier,
                    "regulator_efficiency": self.profile.battery.regulator_efficiency,
                },
            ),
            calibrated_duration,
        )

    def _consume(
        self,
        state_name: str,
        duration_seconds: float,
        *,
        component: str,
        reason: str,
        started_at: float,
        metadata: dict[str, Any] | None = None,
        override_state: PowerState | None = None,
    ) -> EnergyEvent:
        """Registra o consumo de um estado energético do dispositivo."""
        state = override_state or self.profile.power_states[state_name]
        calibrated_load_energy_j = state.metadata.get("calibrated_load_energy_j")
        return self.energy_model.consume_state(
            state,
            duration_seconds,
            component=component,
            reason=reason,
            started_at=started_at,
            metadata=metadata,
            load_energy_override_j=(
                float(calibrated_load_energy_j)
                if calibrated_load_energy_j is not None
                else None
            ),
        )

    def _consume_crypto_operations(
        self,
        operations: list[CryptoOperation],
        *,
        started_at: float,
        reason_prefix: str,
    ) -> tuple[float, float]:
        """Contabiliza energia e tempo das operações criptográficas."""
        cursor = started_at
        duration = 0.0
        energy = 0.0
        default_state = self.profile.power_states["crypto_processing"]
        for operation in operations:
            if operation.participant not in {"source", "iot_client"}:
                # This implementation deliberately excludes uncalibrated
                # gateway/server energy from IoT battery autonomy.
                operation.energy_j = None
                continue
            voltage = float(operation.metadata.get("voltage_v", default_state.voltage_v))
            current = float(operation.metadata.get("current_ma", default_state.current_ma))
            source = operation.timing_source
            state = PowerState(
                name="crypto_processing",
                voltage_v=voltage,
                current_ma=current,
                source=source,
                metadata={
                    "operation": operation.operation,
                    **(
                        {"calibrated_load_energy_j": operation.metadata["calibrated_load_energy_j"]}
                        if "calibrated_load_energy_j" in operation.metadata
                        else {}
                    ),
                },
            )
            event = self._consume(
                "crypto_processing",
                operation.duration_seconds,
                component="crypto",
                reason=f"{reason_prefix}:{operation.operation}",
                started_at=cursor,
                metadata={
                    "algorithm": operation.algorithm,
                    "participant": operation.participant,
                    "timing_source": operation.timing_source,
                    "calibration_status": operation.metadata.get("calibration_status"),
                },
                override_state=state,
            )
            operation.energy_j = event.battery_energy_j
            operation.current_ma = current
            operation.voltage_v = voltage
            operation.included_in_primary_energy_budget = True
            energy += event.battery_energy_j
            duration += operation.duration_seconds
            cursor += operation.duration_seconds
        return duration, energy

    def _consume_optional_rtc_state(
        self,
        state_name: str,
        parameters: dict[str, Any] | None,
        *,
        started_at: float,
    ) -> tuple[float, float | None, str]:
        """Contabiliza um estado RTC opcional quando calibrado."""
        if parameters is None:
            return 0.0, None, "excluded_no_reliable_parameter"
        duration = float(parameters["duration_seconds"])
        state = PowerState(
            name=state_name,
            voltage_v=float(parameters["voltage_v"]),
            current_ma=float(parameters["current_ma"]),
            source=str(parameters["source"]),
            metadata={
                "parameter_status": str(parameters.get("parameter_status", "configured")),
                "scope": "iot_client_rtc_session_state",
            },
        )
        event = self._consume(
            "crypto_processing", duration, component="rtc_state",
            reason=state_name, started_at=started_at, override_state=state,
        )
        return duration, event.battery_energy_j, "configured_included"

    @staticmethod
    def _link_value(network_conditions: dict[str, Any], *names: str) -> float | None:
        """Obtém uma condição do enlace com conversão e valor padrão."""
        for name in names:
            value = network_conditions.get(name)
            if value is not None:
                return float(value)
        return None

    def run_cycle(
        self,
        simulation_time_seconds: float,
        *,
        network_conditions: dict[str, Any] | None = None,
        cycle_budget_seconds: float | None = None,
        payload_override: dict[str, Any] | None = None,
    ) -> DeviceCycleResult:
        """Executa um ciclo de coleta, proteção e transmissão do dispositivo.

        Parâmetros:
            simulation_time_seconds: Instante simulado do ciclo, em segundos.
            network_conditions: Banda, atraso e perda usados no ciclo.
            cycle_budget_seconds: Janela máxima disponível para o ciclo.
            payload_override: Conteúdo opcional que substitui a amostra gerada.

        Retorna:
            Resultado completo do ciclo físico do dispositivo.
        """
        wall_started = perf_counter()
        conditions = network_conditions or {}
        interval = cycle_budget_seconds or self.profile.workload.sample_interval_seconds
        if interval <= 0:
            raise ValueError("cycle budget must be positive")
        if self.battery.is_depleted:
            raise BatteryDepletedError(f"{self.device_id} battery is depleted")

        event_index = len(self.energy_model.events)
        battery_before = self.battery.remaining_j
        self.sequence += 1
        self.messages_attempted += 1
        cursor = simulation_time_seconds
        active_duration = 0.0
        handshake: SessionEstablishmentResult | None = None
        message_result: CryptoResult | None = None
        status = "delivered"
        payload: dict[str, Any] = {}
        sizes = None
        transfer = None
        phase_waits: dict[str, float] = {}
        association_wait_seconds = 0.0
        session_preexisting_at_cycle_start = (
            (self.device_id, self.destination) in self.crypto_manager.sessions
        )
        rtc_energy: dict[str, float | None] = {
            "write": None, "restore": None, "validation": None,
        }
        rtc_status = {
            "write": (
                "excluded_preexisting_state_creation_outside_measurement"
                if session_preexisting_at_cycle_start else "not_applicable"
            ),
            "restore": "not_applicable",
            "validation": "not_applicable",
        }

        try:
            workload = self.profile.workload
            self._consume("wake_up", workload.wake_up_seconds, component="cpu", reason="wake_up", started_at=cursor)
            cursor += workload.wake_up_seconds
            active_duration += workload.wake_up_seconds

            if session_preexisting_at_cycle_start:
                for short_name, parameters in (
                    ("restore", self.profile.crypto_session.rtc_state_restore),
                    ("validation", self.profile.crypto_session.rtc_state_validation),
                ):
                    seconds, energy, status_value = self._consume_optional_rtc_state(
                        f"rtc_state_{short_name}", parameters, started_at=cursor,
                    )
                    cursor += seconds
                    active_duration += seconds
                    rtc_energy[short_name] = energy
                    rtc_status[short_name] = status_value

            self._consume("sensor_measurement", workload.sensor_measurement_seconds, component="sensor", reason=f"{self.profile.sensor.model}_forced_measurement", started_at=cursor)
            cursor += workload.sensor_measurement_seconds
            active_duration += workload.sensor_measurement_seconds

            payload = deepcopy(payload_override) if payload_override is not None else self.workload_generator.generate(
                device_id=self.device_id,
                sequence=self.sequence,
                simulation_time_seconds=simulation_time_seconds,
                battery_voltage_v=self._battery_voltage(),
                battery_soc_percent=self.battery.state_of_charge_percent,
            )
            self._consume("cpu_processing", workload.cpu_processing_seconds, component="cpu", reason="serialize_compact_json", started_at=cursor)
            cursor += workload.cpu_processing_seconds
            active_duration += workload.cpu_processing_seconds

            association_required = workload.reconnect_wifi_each_cycle or not self.wifi_connected
            if association_required:
                association_state, association_seconds = self._wifi_reconnect_state()
                self._consume(
                    "wifi_association", association_seconds,
                    component="wifi_association",
                    reason="wifi_reconnect_initialization_proxy",
                    started_at=cursor,
                    metadata={
                        "energy_model": self.profile.radio.wifi_reconnect_energy_model,
                        "parameter_status": "literature_proxy",
                    },
                    override_state=association_state,
                )
                cursor += association_seconds
                active_duration += association_seconds
                association_wait_seconds = association_seconds
                self.wifi_connected = True

            needs_handshake = self.crypto_manager.should_rekey(
                self.device_id,
                self.destination,
                simulation_time_seconds,
                device_restarted=(
                    self._woke_from_deep_sleep
                    and self.profile.crypto_session.rekey_on_restart
                ),
            )
            if needs_handshake:
                handshake = self.crypto_manager.establish_session(
                    self.device_id,
                    self.destination,
                    simulation_time_seconds,
                )

            message_result = self.crypto_manager.protect_message(
                payload,
                source=self.device_id,
                destination=self.destination,
                simulation_time_seconds=simulation_time_seconds,
            )
            application_bytes = len(serialize_payload(payload, workload.payload_format))
            sizes = self.protocol_model.size_cycle(
                application_payload_bytes=application_bytes,
                crypto_payload_bytes=message_result.protected_size_bytes,
                handshake_flights=(
                    handshake.handshake_plan.wire_flights()
                    if handshake and handshake.handshake_plan else ()
                ),
                include_tcp_connect=association_required,
                include_mqtt_connect=association_required,
            )
            loss = self._link_value(conditions, "packet_loss_percent", "loss_percent") or 0.0
            bandwidth_mbps = self._link_value(conditions, "bandwidth_mbps", "configured_bandwidth_mbps")
            bitrate = self.profile.radio.effective_bitrate_bps
            if bandwidth_mbps is not None and bandwidth_mbps > 0:
                bitrate = min(bitrate, bandwidth_mbps * 1_000_000.0)
            rtt_ms = self._link_value(conditions, "rtt_avg_ms", "latency_ms")
            transfer = self.radio_model.transfer(
                sizes,
                packet_loss_percent=loss,
                effective_bitrate_bps=bitrate,
                rtt_ms=rtt_ms,
                wait_for_mqtt_ack=True,
                include_handshake_wait=handshake is not None,
            )
            handshake_iot = [
                operation for operation in (handshake.operations if handshake else [])
                if operation.participant in {"source", "iot_client"}
            ]
            client_flight_names = {"x25519_keygen", "ml_kem_encaps"}
            client_flight_ops = [
                operation for operation in handshake_iot
                if operation.operation in client_flight_names
            ]
            post_response_ops = [
                operation for operation in handshake_iot
                if operation.operation not in client_flight_names
            ]
            handshake_energy = 0.0
            message_energy = 0.0
            client_ops_consumed = post_ops_consumed = message_ops_consumed = False

            for wire in transfer.wire_messages:
                logical_type = str(wire["logical_type"])
                wire_metadata = dict(wire.get("metadata") or {})
                if logical_type == "client_key_establishment" and not client_ops_consumed:
                    seconds, energy = self._consume_crypto_operations(
                        client_flight_ops, started_at=cursor,
                        reason_prefix="crypto_handshake_client_flight",
                    )
                    cursor += seconds
                    active_duration += seconds
                    handshake_energy += energy
                    client_ops_consumed = True
                if (
                    wire_metadata.get("post_handshake_operations_boundary")
                    and not post_ops_consumed
                ):
                    seconds, energy = self._consume_crypto_operations(
                        post_response_ops, started_at=cursor,
                        reason_prefix="crypto_handshake_post_response",
                    )
                    cursor += seconds
                    active_duration += seconds
                    handshake_energy += energy
                    post_ops_consumed = True
                    if handshake is not None:
                        seconds, rtc_write_energy, rtc_write_status = (
                            self._consume_optional_rtc_state(
                                "rtc_state_write",
                                self.profile.crypto_session.rtc_state_write,
                                started_at=cursor,
                            )
                        )
                        cursor += seconds
                        active_duration += seconds
                        rtc_energy["write"] = rtc_write_energy
                        rtc_status["write"] = rtc_write_status
                if (
                    wire_metadata.get("crypto_message_carrier")
                    and not message_ops_consumed
                ):
                    seconds, energy = self._consume_crypto_operations(
                        message_result.operations, started_at=cursor,
                        reason_prefix="crypto_message",
                    )
                    cursor += seconds
                    active_duration += seconds
                    message_energy += energy
                    message_ops_consumed = True

                wait_phase = wire.get("wait_phase")
                if wait_phase:
                    wait_seconds = float(wire.get("wait_rtt_fraction") or 0.0) * max(
                        0.0, (rtt_ms or 0.0) / 1000.0
                    )
                    phase_waits[str(wait_phase)] = (
                        phase_waits.get(str(wait_phase), 0.0) + wait_seconds
                    )
                    if wait_seconds:
                        wait_state = (
                            "mqtt_wait_ack"
                            if wait_phase in {
                                "mqtt_publish", "coap_response", "http_response"
                            }
                            else "wifi_rx"
                        )
                        self._consume(
                            wait_state, wait_seconds, component="rx",
                            reason=f"{wait_phase}_response_wait",
                            started_at=cursor,
                            metadata={"rtt_source": "network_conditions", "rtt_ms": rtt_ms},
                        )
                        cursor += wait_seconds
                        active_duration += wait_seconds

                wire_seconds = float(wire["effective_wire_bytes"]) * 8.0 / bitrate
                state_name = "wifi_tx" if wire["direction"] == "iot_to_server" else "wifi_rx"
                component = "tx" if state_name == "wifi_tx" else "rx"
                self._consume(
                    state_name, wire_seconds, component=component,
                    reason=f"wire_message:{logical_type}", started_at=cursor,
                    metadata={
                        "wire_message_sequence": wire["sequence"],
                        "protocol": wire["protocol"],
                        "direction": wire["direction"],
                        "base_wire_bytes": wire["base_wire_bytes"],
                        "effective_wire_bytes": wire["effective_wire_bytes"],
                        "retransmitted_bytes": wire["retransmitted_bytes"],
                        "retry_interpretation": transfer.retry_interpretation,
                        "bitrate_bps": bitrate,
                    },
                )
                cursor += wire_seconds
                active_duration += wire_seconds

            self.handshake_energy_j += handshake_energy
            message_result.energy_cost = message_energy

            delivered = transfer.delivered
            if delivered:
                self.messages_delivered += 1
            else:
                status = "lost"
                self.messages_lost += 1

            deadline_missed = active_duration > interval
            sleep_duration = max(0.0, interval - active_duration)
            if sleep_duration:
                self._consume("deep_sleep", sleep_duration, component="sleep", reason="cycle_deep_sleep", started_at=cursor)
            self._woke_from_deep_sleep = sleep_duration > 0
            if workload.reconnect_wifi_each_cycle:
                self.wifi_connected = False

        except BatteryDepletedError:
            status = "battery_depleted"
            delivered = False
            self.messages_lost += 1
            if not self.battery.is_depleted:
                self.battery.exhaust(reason="cycle brown-out")
            deadline_missed = active_duration > interval
            sleep_duration = 0.0

        new_events = self.energy_model.events_since(event_index)
        component_energy = self.energy_model.energy_by_component(new_events)
        total_iot = battery_before - self.battery.remaining_j
        elapsed_for_average = max(simulation_time_seconds + max(interval, active_duration), 1e-12)
        average_power_w = self.battery.consumed_j / elapsed_for_average
        lifetime_seconds = self.battery.estimated_runtime(average_power_w) if average_power_w > 0 else None
        total_radio = sum(component_energy.get(name, 0.0) for name in ("wifi_association", "tx", "rx"))
        energy_crypto = component_energy.get("crypto", 0.0)
        calibration_status = message_result.calibration_status if message_result else "required"
        confidence = message_result.energy_confidence if message_result else "provisional"
        if handshake and handshake.calibration_status == "required":
            calibration_status = "required"
            confidence = "provisional"
        session = self.crypto_manager.sessions.get((self.device_id, self.destination))
        application_payload_bytes = sizes.application_payload_bytes if sizes else len(serialize_payload(payload)) if payload else 0
        operations = (handshake.operations if handshake else []) + (message_result.operations if message_result else [])
        result = DeviceCycleResult(
            device_id=self.device_id,
            crypto_mode=self.crypto_manager.mode,
            sequence=self.sequence,
            simulation_time_seconds=simulation_time_seconds,
            cycle_duration_seconds=max(interval, active_duration),
            active_cycle_duration_seconds=active_duration,
            sleep_duration_seconds=sleep_duration,
            wallclock_execution_time_seconds=perf_counter() - wall_started,
            status=status,
            delivered=delivered,
            payload=payload,
            energy_sensor_j=component_energy.get("sensor", 0.0),
            energy_cpu_j=component_energy.get("cpu", 0.0),
            energy_crypto_j=energy_crypto,
            energy_wifi_reconnect_initialization_proxy_j=component_energy.get(
                "wifi_association", 0.0
            ),
            energy_wifi_association_j=component_energy.get("wifi_association", 0.0),
            energy_tx_j=component_energy.get("tx", 0.0),
            energy_rx_j=component_energy.get("rx", 0.0),
            energy_sleep_j=component_energy.get("sleep", 0.0),
            energy_rtc_state_j=component_energy.get("rtc_state", 0.0),
            energy_total_iot_j=total_iot,
            energy_iot_node_j=total_iot,
            energy_gateway_j=None,
            energy_server_j=None,
            energy_network_total_j=None,
            battery_remaining_j=self.battery.remaining_j,
            battery_remaining_wh=self.battery.remaining_wh,
            battery_soc_percent=self.battery.state_of_charge_percent,
            estimated_battery_lifetime_hours=lifetime_seconds / 3600.0 if lifetime_seconds is not None else None,
            estimated_battery_lifetime_days=lifetime_seconds / 86_400.0 if lifetime_seconds is not None else None,
            application_payload_bytes=application_payload_bytes,
            protected_message_bytes=sizes.crypto_payload_bytes if sizes else 0,
            crypto_payload_bytes=sizes.crypto_payload_bytes if sizes else 0,
            handshake_bytes=sizes.crypto_handshake_bytes if sizes else 0,
            handshake_protocol_overhead_bytes=(
                sizes.handshake_protocol_overhead_bytes if sizes else 0
            ),
            mqtt_connect_bytes=sizes.mqtt_connect_bytes if sizes else 0,
            mqtt_connack_bytes=sizes.mqtt_connack_bytes if sizes else 0,
            mqtt_publish_bytes=sizes.mqtt_publish_bytes if sizes else 0,
            mqtt_ack_bytes=sizes.mqtt_ack_bytes if sizes else 0,
            mqtt_bytes=sizes.mqtt_bytes if sizes else 0,
            application_protocol=sizes.protocol_name if sizes else self.profile.protocol,
            protocol_request_bytes=sizes.protocol_request_bytes if sizes else 0,
            protocol_response_bytes=sizes.protocol_response_bytes if sizes else 0,
            application_protocol_bytes=(
                sizes.application_protocol_bytes if sizes else 0
            ),
            udp_header_bytes=sizes.udp_header_bytes if sizes else 0,
            tcp_control_bytes=sizes.tcp_control_bytes if sizes else 0,
            tcp_header_bytes=sizes.tcp_header_bytes if sizes else 0,
            ip_header_bytes=sizes.ip_header_bytes if sizes else 0,
            wifi_link_overhead_bytes=(sizes.wifi_link_overhead_bytes if sizes else 0),
            transport_overhead_bytes=sizes.transport_overhead_bytes if sizes else 0,
            link_overhead_bytes=sizes.link_overhead_bytes if sizes else 0,
            total_wire_bytes=sizes.total_wire_bytes if sizes else 0.0,
            retransmitted_bytes=sizes.retransmitted_bytes if sizes else 0.0,
            handshake_count=self.crypto_manager.handshake_count,
            messages_in_session=session.messages if session else 0,
            messages_attempted=self.messages_attempted,
            messages_delivered=self.messages_delivered,
            messages_lost=self.messages_lost,
            deadline_missed=deadline_missed,
            energy_confidence=confidence,
            calibration_status=calibration_status,
            energy_per_delivered_message_j=total_iot if delivered else None,
            energy_per_application_byte_j=total_iot / application_payload_bytes if application_payload_bytes else None,
            handshake_energy_in_measurement_j=handshake_energy if handshake else 0.0,
            amortized_handshake_energy_j=self.handshake_energy_j / max(self.messages_attempted, 1),
            crypto_energy_percent=100.0 * energy_crypto / total_iot if total_iot else 0.0,
            communication_energy_percent=100.0 * total_radio / total_iot if total_iot else 0.0,
            radio_energy_percent=100.0 * total_radio / total_iot if total_iot else 0.0,
            link_latency_ms=self._link_value(conditions, "latency_ms"),
            link_rtt_ms=self._link_value(conditions, "rtt_avg_ms"),
            link_packet_loss_percent=self._link_value(conditions, "packet_loss_percent", "loss_percent") or 0.0,
            effective_bitrate_bps=transfer.effective_bitrate_bps if transfer else self.profile.radio.effective_bitrate_bps,
            association_wait_seconds=association_wait_seconds,
            tcp_connect_wait_seconds=phase_waits.get("tcp_connect", 0.0),
            crypto_handshake_wait_seconds=phase_waits.get("crypto_handshake", 0.0),
            mqtt_connect_wait_seconds=phase_waits.get("mqtt_connect", 0.0),
            mqtt_publish_wait_seconds=phase_waits.get("mqtt_publish", 0.0),
            protocol_response_wait_seconds=sum(
                phase_waits.get(name, 0.0)
                for name in ("mqtt_publish", "coap_response", "http_response")
            ),
            tcp_ack_policy=(
                sizes.tcp_ack_policy if sizes else "not_available"
            ),
            connection_close_policy=(
                sizes.connection_close_policy if sizes else "not_available"
            ),
            battery_projection_interpretation=(
                "analytical_projection_invariant_cycle_not_discharge_test"
            ),
            battery_nominal_voltage_v=self.profile.battery.nominal_voltage_v,
            battery_capacity_mah=self.profile.battery.capacity_mah,
            battery_usable_fraction=self.profile.battery.usable_fraction,
            regulator_efficiency=self.profile.battery.regulator_efficiency,
            publication_interval_seconds=interval,
            regulator_quiescent_current_ua=(
                self.profile.battery.regulator_quiescent_current_ua
            ),
            rtc_state_write_energy_j=rtc_energy["write"],
            rtc_state_restore_energy_j=rtc_energy["restore"],
            rtc_state_validation_energy_j=rtc_energy["validation"],
            rtc_state_write_status=rtc_status["write"],
            rtc_state_restore_status=rtc_status["restore"],
            rtc_state_validation_status=rtc_status["validation"],
            energy_events=[event.to_dict() for event in new_events],
            crypto_operations=[asdict(operation) for operation in operations],
            wire_messages=(transfer.wire_messages if transfer else []),
            handshake_plan=(
                handshake.handshake_plan.to_dict()
                if handshake and handshake.handshake_plan else None
            ),
            crypto_energy_cost=energy_crypto,
            total_energy_consumed=total_iot,
        )
        return result


def load_device_profiles(config: dict[str, Any]) -> dict[str, DeviceProfile]:
    """Carrega e valida os perfis físicos da configuração.

    Parâmetros:
        config: Dicionário de configuração.

    Retorna:
        Dicionário com os dados produzidos.
    """
    profiles_data = config.get("device_profiles", {}) or {}
    return {
        name: DeviceProfile.from_mapping(name, data)
        for name, data in profiles_data.items()
    }
