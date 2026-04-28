from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .logger import Logger


@dataclass
class Packet:
    source: str
    destination: str
    payload: dict[str, Any]
    protocol: str | None = None
    crypto_mode: str | None = None
    timestamp: str = field(
        default_factory=lambda: datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    )


class Host:
    def __init__(
        self,
        host_id: str,
        host_type: str,
        logger: Logger | None = None,
        initial_energy: float = 100.0,
        protocol: str | None = None,
        crypto_mode: str | None = None,
        metadata: dict[str, Any] | None = None
    ):
        self.host_id = host_id
        self.host_type = host_type
        self.logger = logger or Logger(name="Host")
        self.initial_energy = initial_energy
        self.energy = initial_energy
        self.protocol = protocol
        self.crypto_mode = crypto_mode
        self.metadata = metadata or {}

        self.sent_packets: list[Packet] = []
        self.received_packets: list[Packet] = []
        self.forwarded_packets: list[Packet] = []

        self.logger.log(
            (
                f"{self._label()} criado e inicializado, "
                f"energia: {self._format_number(self.energy)}, "
                f"protocolo: {self._safe_label(self.protocol)}, "
                f"modo de criptografia: {self._crypto_label(self.crypto_mode)}"
            ),
            component=self.host_id
        )

    def _label(self):
        return self._label_from_id(self.host_id)

    def _label_from_id(self, host_id: str | None):
        if not host_id:
            return "Host"

        parts = str(host_id).split("_")

        if len(parts) != 2:
            return str(host_id)

        prefix, number = parts

        labels = {
            "iot": "IOT",
            "gateway": "Gateway",
            "server": "Servidor"
        }

        return f"{labels.get(prefix, prefix)} {number}"

    def _crypto_label(self, crypto_mode: str | None):
        labels = {
            "classical": "classica",
            "hybrid": "hibrida",
            "pqc": "pos quantica"
        }

        if crypto_mode is None:
            return "nao definido"

        return labels.get(crypto_mode, crypto_mode)

    def _reason_label(self, reason: str | None):
        labels = {
            "operation": "operacao",
            "crypto_protect": "protecao criptografica",
            "send_data": "envio de dados",
            "receive_data": "recebimento de dados",
            "forward_data": "encaminhamento de dados",
            "generate_sensor_data": "geracao de dado do sensor"
        }

        if reason is None:
            return "operacao"

        return labels.get(reason, reason)

    def _safe_label(self, value: Any):
        if value is None:
            return "nao definido"

        return value

    def _format_number(self, value: float):
        if isinstance(value, float):
            value = round(value, 6)

            if value.is_integer():
                return int(value)

        return value

    def set_protocol(self, protocol: str):
        self.protocol = protocol

        self.logger.log(
            f"{self._label()} configurado para usar o protocolo {protocol}",
            component=self.host_id
        )

        return self

    def set_crypto_mode(self, crypto_mode: str):
        self.crypto_mode = crypto_mode

        self.logger.log(
            (
                f"{self._label()} configurado com modo de criptografia "
                f"{self._crypto_label(crypto_mode)}"
            ),
            component=self.host_id
        )

        return self

    def set_energy(self, energy: float):
        self.energy = energy

        self.logger.log(
            f"{self._label()} agora possui energia: {self._format_number(self.energy)}",
            component=self.host_id
        )

        return self

    def consume_energy(self, amount: float, reason: str = "operation"):
        if amount < 0:
            raise ValueError("O consumo de energia nao pode ser negativo.")

        self.energy = max(0.0, self.energy - amount)

        self.logger.log(
            (
                f"{self._label()} consumiu {self._format_number(amount)} de energia "
                f"por {self._reason_label(reason)}, "
                f"energia restante: {self._format_number(self.energy)}"
            ),
            component=self.host_id
        )

        return self.energy

    def send_data(
        self,
        destination: str,
        payload: dict[str, Any],
        protocol: str | None = None,
        crypto_mode: str | None = None
    ):
        selected_protocol = protocol or self.protocol
        selected_crypto = crypto_mode or self.crypto_mode

        packet = Packet(
            source=self.host_id,
            destination=destination,
            payload=payload,
            protocol=selected_protocol,
            crypto_mode=selected_crypto
        )

        self.sent_packets.append(packet)

        self.consume_energy(
            amount=0.1,
            reason="send_data"
        )

        self.logger.log(
            (
                f"{self._label()} enviou pacote para {self._label_from_id(destination)}, "
                f"protocolo: {self._safe_label(packet.protocol)}, "
                f"criptografia: {self._crypto_label(packet.crypto_mode)}"
            ),
            component=self.host_id
        )

        return packet

    def receive_data(self, packet: Packet):
        self.received_packets.append(packet)

        self.consume_energy(
            amount=0.05,
            reason="receive_data"
        )

        self.logger.log(
            (
                f"{self._label()} recebeu pacote de {self._label_from_id(packet.source)} "
                f"com destino a {self._label_from_id(packet.destination)}, "
                f"protocolo: {self._safe_label(packet.protocol)}, "
                f"criptografia: {self._crypto_label(packet.crypto_mode)}"
            ),
            component=self.host_id
        )

        return packet

    def get_status(self):
        return {
            "host_id": self.host_id,
            "host_type": self.host_type,
            "initial_energy": self.initial_energy,
            "current_energy": self.energy,
            "energy_consumed": self.initial_energy - self.energy,
            "protocol": self.protocol,
            "crypto_mode": self.crypto_mode,
            "sent_packets": len(self.sent_packets),
            "received_packets": len(self.received_packets),
            "forwarded_packets": len(self.forwarded_packets),
            "metadata": self.metadata
        }


class IoTNode(Host):
    def __init__(
        self,
        host_id: str,
        logger: Logger | None = None,
        sensor_type: str = "generic",
        initial_energy: float = 100.0,
        protocol: str | None = None,
        crypto_mode: str | None = None,
        metadata: dict[str, Any] | None = None
    ):
        super().__init__(
            host_id=host_id,
            host_type="iot",
            logger=logger,
            initial_energy=initial_energy,
            protocol=protocol,
            crypto_mode=crypto_mode,
            metadata=metadata
        )

        self.sensor_type = sensor_type

    def generate_sensor_data(self, value: Any | None = None):
        data = {
            "node_id": self.host_id,
            "sensor_type": self.sensor_type,
            "value": value,
            "timestamp": datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        }

        self.consume_energy(
            amount=0.02,
            reason="generate_sensor_data"
        )

        self.logger.log(
            (
                f"{self._label()} gerou dado do sensor, "
                f"tipo: {self.sensor_type}, "
                f"valor: {self._safe_label(value)}"
            ),
            component=self.host_id
        )

        return data

    def send_sensor_data(
        self,
        destination: str,
        value: Any | None = None
    ):
        payload = self.generate_sensor_data(value=value)

        return self.send_data(
            destination=destination,
            payload=payload
        )


class GatewayNode(Host):
    def __init__(
        self,
        host_id: str,
        logger: Logger | None = None,
        initial_energy: float = 500.0,
        protocol: str | None = None,
        crypto_mode: str | None = None,
        metadata: dict[str, Any] | None = None
    ):
        super().__init__(
            host_id=host_id,
            host_type="gateway",
            logger=logger,
            initial_energy=initial_energy,
            protocol=protocol,
            crypto_mode=crypto_mode,
            metadata=metadata
        )

    def forward_data(
        self,
        packet: Packet,
        destination: str
    ):
        forwarded_packet = Packet(
            source=packet.source,
            destination=destination,
            payload=packet.payload,
            protocol=packet.protocol,
            crypto_mode=packet.crypto_mode
        )

        self.forwarded_packets.append(forwarded_packet)

        self.consume_energy(
            amount=0.08,
            reason="forward_data"
        )

        self.logger.log(
            (
                f"{self._label()} encaminhou pacote de {self._label_from_id(packet.source)} "
                f"para {self._label_from_id(destination)}, "
                f"protocolo: {self._safe_label(packet.protocol)}, "
                f"criptografia: {self._crypto_label(packet.crypto_mode)}"
            ),
            component=self.host_id
        )

        return forwarded_packet


class ApplicationServer(Host):
    def __init__(
        self,
        host_id: str,
        logger: Logger | None = None,
        initial_energy: float = 1000.0,
        protocol: str | None = None,
        crypto_mode: str | None = None,
        metadata: dict[str, Any] | None = None
    ):
        super().__init__(
            host_id=host_id,
            host_type="server",
            logger=logger,
            initial_energy=initial_energy,
            protocol=protocol,
            crypto_mode=crypto_mode,
            metadata=metadata
        )

        self.application_data: list[dict[str, Any]] = []

    def process_data(self, packet: Packet):
        self.receive_data(packet)

        record = {
            "server_id": self.host_id,
            "source": packet.source,
            "payload": packet.payload,
            "protocol": packet.protocol,
            "crypto_mode": packet.crypto_mode,
            "received_at": datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        }

        self.application_data.append(record)

        self.logger.log(
            (
                f"{self._label()} processou pacote recebido de {self._label_from_id(packet.source)}, "
                f"protocolo: {self._safe_label(packet.protocol)}, "
                f"criptografia: {self._crypto_label(packet.crypto_mode)}"
            ),
            component=self.host_id
        )

        return record

    def get_application_data(self):
        return self.application_data