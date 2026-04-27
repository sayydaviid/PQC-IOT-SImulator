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
            "Host criado",
            data={
                "host_id": self.host_id,
                "host_type": self.host_type,
                "energy": self.energy,
                "protocol": self.protocol,
                "crypto_mode": self.crypto_mode
            },
            component=self.host_id
        )

    def set_protocol(self, protocol: str):
        self.protocol = protocol

        self.logger.log(
            "Protocolo definido no host",
            data={
                "host_id": self.host_id,
                "protocol": protocol
            },
            component=self.host_id
        )

        return self

    def set_crypto_mode(self, crypto_mode: str):
        self.crypto_mode = crypto_mode

        self.logger.log(
            "Modo criptografico definido no host",
            data={
                "host_id": self.host_id,
                "crypto_mode": crypto_mode
            },
            component=self.host_id
        )

        return self

    def set_energy(self, energy: float):
        self.energy = energy

        self.logger.log(
            "Energia definida no host",
            data={
                "host_id": self.host_id,
                "energy": self.energy
            },
            component=self.host_id
        )

        return self

    def consume_energy(self, amount: float, reason: str = "operation"):
        if amount < 0:
            raise ValueError("O consumo de energia nao pode ser negativo.")

        self.energy = max(0.0, self.energy - amount)

        self.logger.log(
            "Energia consumida",
            data={
                "host_id": self.host_id,
                "amount": amount,
                "remaining_energy": self.energy,
                "reason": reason
            },
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
            "Pacote enviado",
            data={
                "source": packet.source,
                "destination": packet.destination,
                "protocol": packet.protocol,
                "crypto_mode": packet.crypto_mode,
                "payload": packet.payload
            },
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
            "Pacote recebido",
            data={
                "receiver": self.host_id,
                "source": packet.source,
                "destination": packet.destination,
                "protocol": packet.protocol,
                "crypto_mode": packet.crypto_mode,
                "payload": packet.payload
            },
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

        self.logger.log(
            "No IoT inicializado",
            data={
                "host_id": self.host_id,
                "sensor_type": self.sensor_type
            },
            component=self.host_id
        )

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
            "Dado de sensor gerado",
            data=data,
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

        self.logger.log(
            "Gateway inicializado",
            data={"host_id": self.host_id},
            component=self.host_id
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
            "Pacote encaminhado pelo gateway",
            data={
                "gateway": self.host_id,
                "original_source": packet.source,
                "new_destination": destination,
                "protocol": packet.protocol,
                "crypto_mode": packet.crypto_mode
            },
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

        self.logger.log(
            "Servidor de aplicacao inicializado",
            data={"host_id": self.host_id},
            component=self.host_id
        )

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
            "Dado processado pelo servidor",
            data=record,
            component=self.host_id
        )

        return record

    def get_application_data(self):
        return self.application_data