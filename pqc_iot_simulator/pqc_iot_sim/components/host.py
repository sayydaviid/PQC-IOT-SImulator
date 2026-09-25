"""Define os tipos de nós e pacotes da topologia lógica."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .logger import Logger


@dataclass
class Packet:
    """Representa um pacote lógico transmitido pela rede."""
    source: str
    destination: str
    payload: dict[str, Any]
    protocol: str | None = None
    crypto_mode: str | None = None
    timestamp: str = field(
        default_factory=lambda: datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    )


class Host:
    """Representa um nó lógico capaz de enviar e receber dados."""
    def __init__(
        self,
        host_id: str,
        host_type: str,
        logger: Logger | None = None,
        initial_energy: float | None = None,
        protocol: str | None = None,
        crypto_mode: str | None = None,
        metadata: dict[str, Any] | None = None
    ):
        """Inicializa a instância e prepara seu estado interno.

        Parâmetros:
            host_id: Identificador do host.
            host_type: Tipo lógico do host.
            logger: Registrador usado pelo componente.
            initial_energy: Energia inicial atribuída ao host.
            protocol: Protocolo de aplicação utilizado.
            crypto_mode: Modo criptográfico clássico, PQC ou híbrido.
            metadata: Metadados adicionais associados ao objeto.
        """
        self.host_id = host_id
        self.host_type = host_type
        self.logger = logger or Logger(name="Host")
        if initial_energy is not None and initial_energy < 0:
            raise ValueError("initial_energy is expressed in joules and cannot be negative")
        self.initial_energy = float(initial_energy or 0.0)
        self.energy = self.initial_energy
        self.energy_is_calibrated = initial_energy is not None
        self.protocol = protocol
        self.crypto_mode = crypto_mode
        self.metadata = metadata or {}

        self.sent_packets: list[Packet] = []
        self.received_packets: list[Packet] = []
        self.forwarded_packets: list[Packet] = []

        self.logger.log(
            (
                f"{self._label()} criado e inicializado, "
                f"energia fisica: {'configurada' if self.energy_is_calibrated else 'nao calibrada'}, "
                f"protocolo: {self._safe_label(self.protocol)}, "
                f"modo de criptografia: {self._crypto_label(self.crypto_mode)}"
            ),
            component=self.host_id
        )

    def _label(self):
        """Converte um identificador interno em texto legível."""
        return self._label_from_id(self.host_id)

    def _label_from_id(self, host_id: str | None):
        """Produz um rótulo legível a partir de um identificador."""
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
        """Converte o modo criptográfico em um rótulo legível."""
        labels = {
            "classical": "classica",
            "hybrid": "hibrida",
            "pqc": "pos quantica"
        }

        if crypto_mode is None:
            return "nao definido"

        return labels.get(crypto_mode, crypto_mode)

    def _reason_label(self, reason: str | None):
        """Converte o motivo interno em um rótulo legível."""
        labels = {
            "operation": "operacao",
            "crypto_protect": "protecao criptografica",
            "send_data": "envio de dados",
            "receive_data": "recebimento de dados",
            "forward_data": "encaminhamento de dados",
        }

        if reason is None:
            return "operacao"

        return labels.get(reason, reason)

    def _safe_label(self, value: Any):
        """Normaliza um texto antes de exibi-lo em logs."""
        if value is None:
            return "nao definido"

        return value

    def _format_number(self, value: float):
        """Formata um número para exibição nos logs."""
        if isinstance(value, float):
            value = round(value, 6)

            if value.is_integer():
                return int(value)

        return value

    def set_protocol(self, protocol: str):
        """Define o protocolo de aplicação usado pelo componente.

        Parâmetros:
            protocol: Protocolo de aplicação utilizado.
        """
        self.protocol = protocol

        self.logger.log(
            f"{self._label()} configurado para usar o protocolo {protocol}",
            component=self.host_id
        )

        return self

    def set_crypto_mode(self, crypto_mode: str):
        """Define o modo criptográfico usado pelo componente.

        Parâmetros:
            crypto_mode: Modo criptográfico clássico, PQC ou híbrido.
        """
        self.crypto_mode = crypto_mode

        self.logger.log(
            (
                f"{self._label()} configurado com modo de criptografia "
                f"{self._crypto_label(crypto_mode)}"
            ),
            component=self.host_id
        )

        return self

    def consume_energy(self, amount: float, reason: str = "operation"):
        """Debita joules pela interface antiga apenas em hosts calibrados.

        Parâmetros:
            amount: Energia debitada do host, em joules.
            reason: Motivo registrado para o esgotamento ou débito.
        """
        if amount < 0:
            raise ValueError("O consumo de energia nao pode ser negativo.")

        if not self.energy_is_calibrated:
            raise RuntimeError(
                f"host {self.host_id} has no calibrated physical energy model"
            )
        if amount > self.energy:
            raise RuntimeError(
                f"host {self.host_id} has {self.energy:.9f} J but {amount:.9f} J was requested"
            )
        self.energy -= amount

        self.logger.log(
            (
                f"{self._label()} consumiu {self._format_number(amount)} J "
                f"por {self._reason_label(reason)}, "
                f"energia restante: {self._format_number(self.energy)} J"
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
        """Cria e envia dados para outro nó.

        Parâmetros:
            destination: Identificador do destino.
            payload: Conteúdo útil da mensagem.
            protocol: Protocolo de aplicação utilizado.
            crypto_mode: Modo criptográfico clássico, PQC ou híbrido.
        """
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
        """Recebe e registra um pacote destinado ao nó.

        Parâmetros:
            packet: Pacote lógico processado pelo nó.
        """
        self.received_packets.append(packet)

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
        """Retorna o estado atual do componente."""
        initial_j = self.initial_energy if self.energy_is_calibrated else None
        current_j = self.energy if self.energy_is_calibrated else None
        consumed_j = self.initial_energy - self.energy if self.energy_is_calibrated else None
        return {
            "host_id": self.host_id,
            "host_type": self.host_type,
            "initial_energy_j": initial_j,
            "current_energy_j": current_j,
            "energy_consumed_j": consumed_j,
            "energy_model_status": "legacy_explicit_joules" if self.energy_is_calibrated else "not_calibrated",
            "initial_energy": initial_j,
            "current_energy": current_j,
            "energy_consumed": consumed_j,
            "legacy_energy_fields_deprecated": True,
            "protocol": self.protocol,
            "crypto_mode": self.crypto_mode,
            "sent_packets": len(self.sent_packets),
            "received_packets": len(self.received_packets),
            "forwarded_packets": len(self.forwarded_packets),
            "metadata": self.metadata
        }


class IoTNode(Host):
    """Representa um dispositivo IoT na topologia lógica."""
    def __init__(
        self,
        host_id: str,
        logger: Logger | None = None,
        initial_energy: float | None = None,
        protocol: str | None = None,
        crypto_mode: str | None = None,
        metadata: dict[str, Any] | None = None
    ):
        """Inicializa a instância e prepara seu estado interno.

        Parâmetros:
            host_id: Identificador do host.
            logger: Registrador usado pelo componente.
            initial_energy: Energia inicial atribuída ao host.
            protocol: Protocolo de aplicação utilizado.
            crypto_mode: Modo criptográfico clássico, PQC ou híbrido.
            metadata: Metadados adicionais associados ao objeto.
        """
        super().__init__(
            host_id=host_id,
            host_type="iot",
            logger=logger,
            initial_energy=initial_energy,
            protocol=protocol,
            crypto_mode=crypto_mode,
            metadata=metadata
        )


class GatewayNode(Host):
    """Representa um gateway que encaminha dados na topologia."""
    def __init__(
        self,
        host_id: str,
        logger: Logger | None = None,
        initial_energy: float | None = None,
        protocol: str | None = None,
        crypto_mode: str | None = None,
        metadata: dict[str, Any] | None = None
    ):
        """Inicializa a instância e prepara seu estado interno.

        Parâmetros:
            host_id: Identificador do host.
            logger: Registrador usado pelo componente.
            initial_energy: Energia inicial atribuída ao host.
            protocol: Protocolo de aplicação utilizado.
            crypto_mode: Modo criptográfico clássico, PQC ou híbrido.
            metadata: Metadados adicionais associados ao objeto.
        """
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
        """Encaminha um pacote ao próximo nó do caminho.

        Parâmetros:
            packet: Pacote lógico processado pelo nó.
            destination: Identificador do destino.
        """
        forwarded_packet = Packet(
            source=packet.source,
            destination=destination,
            payload=packet.payload,
            protocol=packet.protocol,
            crypto_mode=packet.crypto_mode
        )

        self.forwarded_packets.append(forwarded_packet)

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
    """Representa o servidor que recebe e processa telemetria."""
    def __init__(
        self,
        host_id: str,
        logger: Logger | None = None,
        initial_energy: float | None = None,
        protocol: str | None = None,
        crypto_mode: str | None = None,
        metadata: dict[str, Any] | None = None
    ):
        """Inicializa a instância e prepara seu estado interno.

        Parâmetros:
            host_id: Identificador do host.
            logger: Registrador usado pelo componente.
            initial_energy: Energia inicial atribuída ao host.
            protocol: Protocolo de aplicação utilizado.
            crypto_mode: Modo criptográfico clássico, PQC ou híbrido.
            metadata: Metadados adicionais associados ao objeto.
        """
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
        """Processa e registra os dados recebidos pelo servidor.

        Parâmetros:
            packet: Pacote lógico processado pelo nó.
        """
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
