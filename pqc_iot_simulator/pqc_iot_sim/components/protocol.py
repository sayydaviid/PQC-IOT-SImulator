"""Modela explicitamente o tráfego analítico de MQTT, CoAP e HTTP."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import ceil
from random import Random
from typing import Any, Mapping, Sequence


def mqtt_remaining_length_bytes(remaining_length: int) -> int:
    """Calcula os bytes do campo Remaining Length do MQTT.

    Parâmetros:
        remaining_length: Valor do campo Remaining Length do MQTT.

    Retorna:
        Valor numérico calculado.
    """
    if not 0 <= remaining_length <= 268_435_455:
        raise ValueError("MQTT Remaining Length is outside the 3.1.1 range")
    count, value = 0, remaining_length
    while True:
        count += 1
        value //= 128
        if value == 0:
            return count


@dataclass(frozen=True)
class MQTTConfig:
    """Armazena parâmetros do modelo MQTT 3.1.1."""
    topic: str
    qos: int = 1
    persistent_session: bool = True
    client_id: str = "pqc-iot-esp32-01"
    clean_session: bool = False
    username: str | None = None
    password: str | None = None
    version: str = "3.1.1"
    tcp_ack_policy: str = "response_piggyback"
    connection_close_policy: str = "abandon_before_deep_sleep_no_fin_modelled"

    def __post_init__(self) -> None:
        """Valida e normaliza os campos após a criação do objeto."""
        if not self.topic or not self.client_id:
            raise ValueError("MQTT topic and client_id cannot be empty")
        if self.qos not in (0, 1, 2):
            raise ValueError("MQTT qos must be 0, 1, or 2")
        if self.version != "3.1.1":
            raise ValueError("only MQTT 3.1.1 is modelled")
        if self.tcp_ack_policy not in {"response_piggyback", "explicit_ack"}:
            raise ValueError("invalid TCP ACK policy")


@dataclass(frozen=True)
class CoAPConfig:
    """Armazena parâmetros do modelo CoAP."""
    resource_path: str = "sensors/environment"
    confirmable: bool = True
    token_length_bytes: int = 2
    content_format: int = 50  # application/json
    version: str = "1"

    def __post_init__(self) -> None:
        """Valida e normaliza os campos após a criação do objeto."""
        if not self.resource_path.strip("/"):
            raise ValueError("CoAP resource_path cannot be empty")
        if not 0 <= self.token_length_bytes <= 8:
            raise ValueError("CoAP token length must be in [0, 8]")
        if self.content_format < 0:
            raise ValueError("CoAP content_format cannot be negative")
        if self.version != "1":
            raise ValueError("only CoAP version 1 is modelled")


@dataclass(frozen=True)
class HTTPConfig:
    """Armazena parâmetros do modelo HTTP/1.1."""
    host: str = "server.local"
    path: str = "/telemetry"
    method: str = "POST"
    version: str = "HTTP/1.1"
    content_type: str = "application/octet-stream"
    response_status: str = "204 No Content"
    tcp_ack_policy: str = "response_piggyback"
    connection_close_policy: str = "connection_close_after_response"

    def __post_init__(self) -> None:
        """Valida e normaliza os campos após a criação do objeto."""
        if not self.host:
            raise ValueError("HTTP host cannot be empty")
        if not self.path.startswith("/"):
            raise ValueError("HTTP path must start with '/'")
        if self.method != "POST":
            raise ValueError("only HTTP POST is modelled")
        if self.version != "HTTP/1.1":
            raise ValueError("only HTTP/1.1 is modelled")
        if self.tcp_ack_policy not in {"response_piggyback", "explicit_ack"}:
            raise ValueError("invalid TCP ACK policy")


@dataclass
class WireMessage:
    """Representa uma mensagem lógica pronta para o transporte."""
    sequence: int
    direction: str
    protocol: str
    logical_type: str
    logical_payload_bytes: int
    transport_segments: int
    tcp_header_bytes: int
    ip_header_bytes: int
    wifi_frames: int
    wifi_link_overhead_bytes: int
    base_wire_bytes: int
    wait_phase: str | None = None
    wait_rtt_fraction: float = 0.0
    handshake_material_bytes: int = 0
    handshake_protocol_overhead_bytes: int = 0
    mqtt_bytes: int = 0
    expected_attempts: float = 1.0
    retransmitted_bytes: float = 0.0
    effective_wire_bytes: float = 0.0
    delivered: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    udp_header_bytes: int = 0
    application_protocol_bytes: int = 0

    @property
    def transport_overhead_bytes(self) -> int:
        """Calcula os bytes adicionais do transporte.

        Retorna:
            Valor numérico calculado.
        """
        return self.tcp_header_bytes + self.udp_header_bytes + self.ip_header_bytes

    def to_dict(self) -> dict[str, Any]:
        """Converte o objeto em um dicionário serializável.

        Retorna:
            Dicionário com os dados produzidos.
        """
        return asdict(self)


@dataclass
class MessageSizeBreakdown:
    """Detalha os bytes de aplicação, transporte e enlace."""
    application_payload_bytes: int
    crypto_payload_bytes: int
    crypto_handshake_bytes: int
    handshake_protocol_overhead_bytes: int
    mqtt_connect_bytes: int
    mqtt_connack_bytes: int
    mqtt_publish_bytes: int
    mqtt_ack_bytes: int
    tcp_control_bytes: int
    tcp_header_bytes: int
    ip_header_bytes: int
    wifi_link_overhead_bytes: int
    transport_overhead_bytes: int
    link_overhead_bytes: int
    retransmitted_bytes: float
    total_wire_bytes: float
    tx_base_wire_bytes: int
    rx_base_wire_bytes: int
    wire_messages: list[WireMessage] = field(default_factory=list)
    tcp_ack_policy: str = "response_piggyback"
    connection_close_policy: str = "abandon_before_deep_sleep_no_fin_modelled"
    protocol_name: str = "mqtt"
    protocol_request_bytes: int = 0
    protocol_response_bytes: int = 0
    application_protocol_bytes: int = 0
    udp_header_bytes: int = 0

    @property
    def protected_message_bytes(self) -> int:
        """Soma os bytes protegidos das mensagens.

        Retorna:
            Valor numérico calculado.
        """
        return self.crypto_payload_bytes

    @property
    def handshake_bytes(self) -> int:
        """Soma os bytes das mensagens de handshake.

        Retorna:
            Valor numérico calculado.
        """
        return self.crypto_handshake_bytes

    @property
    def mqtt_bytes(self) -> int:
        """Soma os bytes específicos do MQTT.

        Retorna:
            Valor numérico calculado.
        """
        return sum((self.mqtt_connect_bytes, self.mqtt_connack_bytes,
                    self.mqtt_publish_bytes, self.mqtt_ack_bytes))

    def to_dict(self) -> dict[str, Any]:
        """Converte o objeto em um dicionário serializável.

        Retorna:
            Dicionário com os dados produzidos.
        """
        return asdict(self)


class MQTTProtocolModel:
    """Modela MQTT 3.1.1 sobre TCP/IPv4 e Wi-Fi analítico."""

    def __init__(self, config: MQTTConfig, *, ip_header_bytes: int = 20,
                 tcp_header_bytes: int = 20,
                 link_overhead_bytes_per_frame: int = 38,
                 link_mtu_bytes: int = 1500) -> None:
        """Inicializa a instância e prepara seu estado interno.

        Parâmetros:
            config: Dicionário de configuração.
            ip_header_bytes: Tamanho do cabeçalho IPv4, em bytes.
            tcp_header_bytes: Tamanho do cabeçalho TCP, em bytes.
            link_overhead_bytes_per_frame: Sobrecarga de enlace por quadro, em bytes.
            link_mtu_bytes: MTU do enlace, em bytes.
        """
        for name, value in {
            "ip_header_bytes": ip_header_bytes,
            "tcp_header_bytes": tcp_header_bytes,
            "link_overhead_bytes_per_frame": link_overhead_bytes_per_frame,
            "link_mtu_bytes": link_mtu_bytes,
        }.items():
            if value < 0:
                raise ValueError(f"{name} cannot be negative")
        if link_mtu_bytes <= ip_header_bytes + tcp_header_bytes:
            raise ValueError("link_mtu_bytes is too small")
        self.config = config
        self.ip_header_bytes = ip_header_bytes
        self.tcp_header_bytes = tcp_header_bytes
        self.link_overhead_bytes_per_frame = link_overhead_bytes_per_frame
        self.link_mtu_bytes = link_mtu_bytes

    @staticmethod
    def _utf8_field(value: str) -> int:
        """Codifica um campo textual MQTT com seu comprimento UTF-8."""
        return 2 + len(value.encode("utf-8"))

    def connect_size_bytes(self) -> int:
        """Calcula o tamanho da mensagem MQTT CONNECT.

        Retorna:
            Valor numérico calculado.
        """
        variable = self._utf8_field("MQTT") + 1 + 1 + 2
        payload = self._utf8_field(self.config.client_id)
        if self.config.username is not None:
            payload += self._utf8_field(self.config.username)
        if self.config.password is not None:
            payload += self._utf8_field(self.config.password)
        remaining = variable + payload
        return 1 + mqtt_remaining_length_bytes(remaining) + remaining

    @staticmethod
    def connack_size_bytes() -> int:
        """Calcula o tamanho da resposta MQTT CONNACK.

        Retorna:
            Valor numérico calculado.
        """
        return 4

    def publish_size_bytes(self, payload_bytes: int) -> int:
        """Calcula o tamanho da mensagem MQTT PUBLISH.

        Parâmetros:
            payload_bytes: Tamanho do conteúdo útil, em bytes.

        Retorna:
            Valor numérico calculado.
        """
        if payload_bytes < 0:
            raise ValueError("payload_bytes cannot be negative")
        variable = self._utf8_field(self.config.topic) + (2 if self.config.qos else 0)
        remaining = variable + payload_bytes
        return 1 + mqtt_remaining_length_bytes(remaining) + remaining

    def ack_size_bytes(self) -> int:
        """Calcula o tamanho da confirmação do protocolo.

        Retorna:
            Valor numérico calculado.
        """
        return 0 if self.config.qos == 0 else 4 if self.config.qos == 1 else 8

    def _message(self, *, sequence: int, direction: str, protocol: str,
                 logical_type: str, payload_bytes: int,
                 wait_phase: str | None = None, wait_rtt_fraction: float = 0.0,
                 handshake_material_bytes: int = 0,
                 handshake_protocol_overhead_bytes: int = 0,
                 mqtt_bytes: int = 0, force_segment: bool = False,
                 metadata: Mapping[str, Any] | None = None) -> WireMessage:
        """Cria uma mensagem lógica com metadados de protocolo e transporte."""
        if payload_bytes < 0:
            raise ValueError("logical payload bytes cannot be negative")
        capacity = self.link_mtu_bytes - self.ip_header_bytes - self.tcp_header_bytes
        segments = max(1 if force_segment else 0, ceil(payload_bytes / capacity))
        tcp = segments * self.tcp_header_bytes
        ip = segments * self.ip_header_bytes
        wifi = segments * self.link_overhead_bytes_per_frame
        total = payload_bytes + tcp + ip + wifi
        return WireMessage(
            sequence, direction, protocol, logical_type, payload_bytes, segments,
            tcp, ip, segments, wifi, total, wait_phase, wait_rtt_fraction,
            handshake_material_bytes, handshake_protocol_overhead_bytes,
            mqtt_bytes, effective_wire_bytes=float(total), metadata=dict(metadata or {}),
            application_protocol_bytes=mqtt_bytes,
        )

    def build_cycle_messages(self, *, crypto_payload_bytes: int,
                             handshake_flights: Sequence[Mapping[str, Any]] = (),
                             include_tcp_connect: bool = True,
                             include_mqtt_connect: bool = True) -> list[WireMessage]:
        """Cria as mensagens lógicas de um ciclo.

        Parâmetros:
            crypto_payload_bytes: Quantidade de bytes produzidos pela criptografia.
            handshake_flights: Etapas de mensagens que compõem o handshake.
            include_tcp_connect: Indica se a abertura TCP será incluída.
            include_mqtt_connect: Indica se CONNECT e CONNACK serão incluídos.

        Retorna:
            Lista com os elementos produzidos.
        """
        messages: list[WireMessage] = []
        if include_tcp_connect:
            messages.extend([
                self._message(sequence=0, direction="iot_to_server", protocol="tcp",
                              logical_type="tcp_syn", payload_bytes=0,
                              force_segment=True, metadata={"tcp_control": True}),
                self._message(sequence=0, direction="server_to_iot", protocol="tcp",
                              logical_type="tcp_syn_ack", payload_bytes=0,
                              wait_phase="tcp_connect", wait_rtt_fraction=1.0,
                              force_segment=True, metadata={"tcp_control": True}),
                self._message(sequence=0, direction="iot_to_server", protocol="tcp",
                              logical_type="tcp_ack", payload_bytes=0,
                              force_segment=True, metadata={"tcp_control": True}),
            ])
        for flight in handshake_flights:
            material = int(flight.get("cryptographic_material_bytes", flight.get("payload_bytes", 0)))
            overhead = int(flight.get("protocol_overhead_bytes", 0))
            payload = int(flight.get("payload_bytes", material + overhead))
            rtt_fraction = float(flight.get("wait_rtt_fraction", 0.0))
            messages.append(self._message(
                sequence=0, direction=str(flight["direction"]),
                protocol="authenticated_key_establishment",
                logical_type=str(flight["logical_type"]), payload_bytes=payload,
                wait_phase="crypto_handshake" if rtt_fraction else None,
                wait_rtt_fraction=rtt_fraction,
                handshake_material_bytes=material,
                handshake_protocol_overhead_bytes=overhead,
                metadata={"flight_number": flight.get("flight_number")},
            ))
        if include_mqtt_connect:
            connect, connack = self.connect_size_bytes(), self.connack_size_bytes()
            messages.extend([
                self._message(sequence=0, direction="iot_to_server", protocol="mqtt_3_1_1",
                              logical_type="mqtt_connect", payload_bytes=connect,
                              mqtt_bytes=connect, metadata={
                                  "client_id": self.config.client_id,
                                  "clean_session": self.config.clean_session,
                                  "persistent_session": self.config.persistent_session,
                                  "username_present": self.config.username is not None,
                                  "password_present": self.config.password is not None,
                                  "tls_included": False,
                                  "post_handshake_operations_boundary": True,
                              }),
                self._message(sequence=0, direction="server_to_iot", protocol="mqtt_3_1_1",
                              logical_type="mqtt_connack", payload_bytes=connack,
                              mqtt_bytes=connack, wait_phase="mqtt_connect",
                              wait_rtt_fraction=1.0),
            ])
        publish = self.publish_size_bytes(crypto_payload_bytes)
        messages.append(self._message(
            sequence=0, direction="iot_to_server", protocol="mqtt_3_1_1",
            logical_type="mqtt_publish_qos1" if self.config.qos == 1 else "mqtt_publish",
            payload_bytes=publish, mqtt_bytes=publish,
            metadata={
                "qos": self.config.qos,
                "topic": self.config.topic,
                "crypto_message_carrier": True,
                "post_handshake_operations_boundary": True,
            },
        ))
        ack = self.ack_size_bytes()
        if ack:
            messages.append(self._message(
                sequence=0, direction="server_to_iot", protocol="mqtt_3_1_1",
                logical_type="mqtt_puback" if self.config.qos == 1 else "mqtt_qos2_acknowledgements",
                payload_bytes=ack, mqtt_bytes=ack, wait_phase="mqtt_publish",
                wait_rtt_fraction=1.0,
            ))
        if self.config.tcp_ack_policy == "explicit_ack":
            expanded: list[WireMessage] = []
            for message in messages:
                expanded.append(message)
                if message.logical_payload_bytes and message.protocol != "tcp":
                    reverse = "server_to_iot" if message.direction == "iot_to_server" else "iot_to_server"
                    expanded.append(self._message(
                        sequence=0, direction=reverse, protocol="tcp",
                        logical_type=f"tcp_ack_for_{message.logical_type}",
                        payload_bytes=0, force_segment=True,
                        metadata={"tcp_control": True, "explicit_ack": True},
                    ))
            messages = expanded
        for number, message in enumerate(messages, 1):
            message.sequence = number
        return messages

    def size_cycle(self, *, application_payload_bytes: int,
                   crypto_payload_bytes: int,
                   handshake_flights: Sequence[Mapping[str, Any]] = (),
                   include_tcp_connect: bool = True,
                   include_mqtt_connect: bool = True) -> MessageSizeBreakdown:
        """Calcula os tamanhos das mensagens de um ciclo.

        Parâmetros:
            application_payload_bytes: Quantidade de bytes úteis da aplicação.
            crypto_payload_bytes: Quantidade de bytes produzidos pela criptografia.
            handshake_flights: Etapas de mensagens que compõem o handshake.
            include_tcp_connect: Indica se a abertura TCP será incluída.
            include_mqtt_connect: Indica se CONNECT e CONNACK serão incluídos.

        Retorna:
            Detalhamento dos tamanhos das mensagens do ciclo.
        """
        messages = self.build_cycle_messages(
            crypto_payload_bytes=crypto_payload_bytes,
            handshake_flights=handshake_flights,
            include_tcp_connect=include_tcp_connect,
            include_mqtt_connect=include_mqtt_connect,
        )
        tx = sum(m.base_wire_bytes for m in messages if m.direction == "iot_to_server")
        rx = sum(m.base_wire_bytes for m in messages if m.direction == "server_to_iot")
        tcp_headers = sum(m.tcp_header_bytes for m in messages)
        ip_headers = sum(m.ip_header_bytes for m in messages)
        wifi = sum(m.wifi_link_overhead_bytes for m in messages)
        # TCP control bytes are TCP bytes only.  IP and Wi-Fi envelopes are
        # already exported separately and must not be hidden in this field.
        tcp_control = sum(m.tcp_header_bytes for m in messages if m.metadata.get("tcp_control"))
        logical = lambda kind: sum(m.logical_payload_bytes for m in messages if m.logical_type == kind)
        return MessageSizeBreakdown(
            application_payload_bytes=application_payload_bytes,
            crypto_payload_bytes=crypto_payload_bytes,
            crypto_handshake_bytes=sum(m.handshake_material_bytes for m in messages),
            handshake_protocol_overhead_bytes=sum(m.handshake_protocol_overhead_bytes for m in messages),
            mqtt_connect_bytes=logical("mqtt_connect"),
            mqtt_connack_bytes=logical("mqtt_connack"),
            mqtt_publish_bytes=sum(m.mqtt_bytes for m in messages if m.logical_type.startswith("mqtt_publish")),
            mqtt_ack_bytes=sum(m.mqtt_bytes for m in messages if m.logical_type in {"mqtt_puback", "mqtt_qos2_acknowledgements"}),
            tcp_control_bytes=tcp_control, tcp_header_bytes=tcp_headers,
            ip_header_bytes=ip_headers, wifi_link_overhead_bytes=wifi,
            transport_overhead_bytes=tcp_headers + ip_headers,
            link_overhead_bytes=wifi, retransmitted_bytes=0.0,
            total_wire_bytes=float(tx + rx), tx_base_wire_bytes=tx,
            rx_base_wire_bytes=rx, wire_messages=messages,
            tcp_ack_policy=self.config.tcp_ack_policy,
            connection_close_policy=self.config.connection_close_policy,
            protocol_name="mqtt",
            protocol_request_bytes=sum(
                m.application_protocol_bytes for m in messages
                if m.direction == "iot_to_server"
            ),
            protocol_response_bytes=sum(
                m.application_protocol_bytes for m in messages
                if m.direction == "server_to_iot"
            ),
            application_protocol_bytes=sum(
                m.application_protocol_bytes for m in messages
            ),
        )

    def size_message(self, *, application_payload_bytes: int,
                     crypto_payload_bytes: int, handshake_tx_bytes: int = 0,
                     handshake_rx_bytes: int = 0) -> MessageSizeBreakdown:
        """Mantém compatibilidade e separa a entrada em duas etapas.

        Parâmetros:
            application_payload_bytes: Tamanho do conteúdo útil da aplicação, em bytes.
            crypto_payload_bytes: Tamanho do conteúdo após proteção criptográfica, em bytes.
            handshake_tx_bytes: Bytes transmitidos durante o handshake.
            handshake_rx_bytes: Bytes recebidos durante o handshake.

        Retorna:
            Detalhamento dos tamanhos da mensagem modelada.
        """
        flights = []
        if handshake_tx_bytes:
            flights.append({"flight_number": 1, "direction": "iot_to_server",
                            "logical_type": "compatibility_handshake_client_flight",
                            "payload_bytes": handshake_tx_bytes,
                            "cryptographic_material_bytes": handshake_tx_bytes})
        if handshake_rx_bytes:
            flights.append({"flight_number": 2, "direction": "server_to_iot",
                            "logical_type": "compatibility_handshake_server_flight",
                            "payload_bytes": handshake_rx_bytes,
                            "cryptographic_material_bytes": handshake_rx_bytes,
                            "wait_rtt_fraction": 1.0})
        return self.size_cycle(application_payload_bytes=application_payload_bytes,
                               crypto_payload_bytes=crypto_payload_bytes,
                               handshake_flights=flights)


class CoAPProtocolModel:
    """Modela CoAP confirmável sobre UDP/IPv4 e Wi-Fi."""

    def __init__(self, config: CoAPConfig, *, ip_header_bytes: int = 20,
                 udp_header_bytes: int = 8,
                 link_overhead_bytes_per_frame: int = 38,
                 link_mtu_bytes: int = 1500) -> None:
        """Inicializa a instância e prepara seu estado interno.

        Parâmetros:
            config: Dicionário de configuração.
            ip_header_bytes: Tamanho do cabeçalho IPv4, em bytes.
            udp_header_bytes: Tamanho do cabeçalho UDP, em bytes.
            link_overhead_bytes_per_frame: Sobrecarga de enlace por quadro, em bytes.
            link_mtu_bytes: MTU do enlace, em bytes.
        """
        for name, value in {
            "ip_header_bytes": ip_header_bytes,
            "udp_header_bytes": udp_header_bytes,
            "link_overhead_bytes_per_frame": link_overhead_bytes_per_frame,
            "link_mtu_bytes": link_mtu_bytes,
        }.items():
            if value < 0:
                raise ValueError(f"{name} cannot be negative")
        if link_mtu_bytes <= ip_header_bytes + udp_header_bytes:
            raise ValueError("link_mtu_bytes is too small")
        self.config = config
        self.ip_header_bytes = ip_header_bytes
        self.udp_header_bytes = udp_header_bytes
        self.link_overhead_bytes_per_frame = link_overhead_bytes_per_frame
        self.link_mtu_bytes = link_mtu_bytes

    @staticmethod
    def _option_size(delta: int, length: int) -> int:
        """Calcula os bytes usados por uma opção CoAP."""
        if delta < 0 or length < 0:
            raise ValueError("CoAP option delta/length cannot be negative")
        delta_extension = 0 if delta < 13 else 1 if delta < 269 else 2
        length_extension = 0 if length < 13 else 1 if length < 269 else 2
        return 1 + delta_extension + length_extension + length

    def request_size_bytes(self, payload_bytes: int) -> int:
        """Calcula o tamanho da requisição.

        Parâmetros:
            payload_bytes: Tamanho do conteúdo útil, em bytes.

        Retorna:
            Valor numérico calculado.
        """
        if payload_bytes < 0:
            raise ValueError("payload_bytes cannot be negative")
        options = 0
        previous_number = 0
        for segment in self.config.resource_path.strip("/").split("/"):
            encoded = segment.encode("utf-8")
            options += self._option_size(11 - previous_number, len(encoded))
            previous_number = 11
        content_format_length = max(
            1, (self.config.content_format.bit_length() + 7) // 8
        )
        options += self._option_size(12 - previous_number, content_format_length)
        payload_marker = 1 if payload_bytes else 0
        return (
            4 + self.config.token_length_bytes + options
            + payload_marker + payload_bytes
        )

    def response_size_bytes(self) -> int:
        # Piggybacked 2.04 Changed response echoes the request token.
        """Calcula o tamanho da resposta.

        Retorna:
            Valor numérico calculado.
        """
        return 4 + self.config.token_length_bytes

    def _message(self, *, sequence: int, direction: str, protocol: str,
                 logical_type: str, payload_bytes: int,
                 wait_phase: str | None = None, wait_rtt_fraction: float = 0.0,
                 handshake_material_bytes: int = 0,
                 handshake_protocol_overhead_bytes: int = 0,
                 application_protocol_bytes: int = 0,
                 metadata: Mapping[str, Any] | None = None) -> WireMessage:
        """Cria uma mensagem lógica com metadados de protocolo e transporte."""
        if payload_bytes < 0:
            raise ValueError("logical payload bytes cannot be negative")
        fragment_capacity = self.link_mtu_bytes - self.ip_header_bytes
        fragments = max(
            1,
            ceil((payload_bytes + self.udp_header_bytes) / fragment_capacity),
        )
        ip = fragments * self.ip_header_bytes
        wifi = fragments * self.link_overhead_bytes_per_frame
        total = payload_bytes + self.udp_header_bytes + ip + wifi
        return WireMessage(
            sequence=sequence,
            direction=direction,
            protocol=protocol,
            logical_type=logical_type,
            logical_payload_bytes=payload_bytes,
            transport_segments=fragments,
            tcp_header_bytes=0,
            ip_header_bytes=ip,
            wifi_frames=fragments,
            wifi_link_overhead_bytes=wifi,
            base_wire_bytes=total,
            wait_phase=wait_phase,
            wait_rtt_fraction=wait_rtt_fraction,
            handshake_material_bytes=handshake_material_bytes,
            handshake_protocol_overhead_bytes=handshake_protocol_overhead_bytes,
            effective_wire_bytes=float(total),
            metadata=dict(metadata or {}),
            udp_header_bytes=self.udp_header_bytes,
            application_protocol_bytes=application_protocol_bytes,
        )

    def build_cycle_messages(self, *, crypto_payload_bytes: int,
                             handshake_flights: Sequence[Mapping[str, Any]] = (),
                             include_tcp_connect: bool = True,
                             include_mqtt_connect: bool = True) -> list[WireMessage]:
        # Compatibility arguments are accepted intentionally. CoAP uses UDP,
        # so no TCP or MQTT connection exchange is emitted.
        """Cria as mensagens lógicas de um ciclo.

        Parâmetros:
            crypto_payload_bytes: Quantidade de bytes produzidos pela criptografia.
            handshake_flights: Etapas de mensagens que compõem o handshake.
            include_tcp_connect: Indica se a abertura TCP será incluída.
            include_mqtt_connect: Indica se CONNECT e CONNACK serão incluídos.

        Retorna:
            Lista com os elementos produzidos.
        """
        del include_tcp_connect, include_mqtt_connect
        messages: list[WireMessage] = []
        for flight in handshake_flights:
            material = int(
                flight.get("cryptographic_material_bytes", flight.get("payload_bytes", 0))
            )
            overhead = int(flight.get("protocol_overhead_bytes", 0))
            payload = int(flight.get("payload_bytes", material + overhead))
            rtt_fraction = float(flight.get("wait_rtt_fraction", 0.0))
            messages.append(self._message(
                sequence=0,
                direction=str(flight["direction"]),
                protocol="authenticated_key_establishment",
                logical_type=str(flight["logical_type"]),
                payload_bytes=payload,
                wait_phase="crypto_handshake" if rtt_fraction else None,
                wait_rtt_fraction=rtt_fraction,
                handshake_material_bytes=material,
                handshake_protocol_overhead_bytes=overhead,
                metadata={"flight_number": flight.get("flight_number")},
            ))
        request = self.request_size_bytes(crypto_payload_bytes)
        messages.append(self._message(
            sequence=0,
            direction="iot_to_server",
            protocol="coap_1_udp",
            logical_type="coap_confirmable_post",
            payload_bytes=request,
            application_protocol_bytes=request,
            metadata={
                "resource_path": self.config.resource_path,
                "confirmable": self.config.confirmable,
                "content_format": self.config.content_format,
                "crypto_message_carrier": True,
                "post_handshake_operations_boundary": True,
                "dtls_included": False,
                "oscore_included": False,
            },
        ))
        response = self.response_size_bytes()
        messages.append(self._message(
            sequence=0,
            direction="server_to_iot",
            protocol="coap_1_udp",
            logical_type="coap_ack_2_04_changed",
            payload_bytes=response,
            application_protocol_bytes=response,
            wait_phase="coap_response",
            wait_rtt_fraction=1.0 if self.config.confirmable else 0.0,
            metadata={"response_code": "2.04 Changed"},
        ))
        for number, message in enumerate(messages, 1):
            message.sequence = number
        return messages

    def size_cycle(self, *, application_payload_bytes: int,
                   crypto_payload_bytes: int,
                   handshake_flights: Sequence[Mapping[str, Any]] = (),
                   include_tcp_connect: bool = True,
                   include_mqtt_connect: bool = True) -> MessageSizeBreakdown:
        """Calcula os tamanhos das mensagens de um ciclo.

        Parâmetros:
            application_payload_bytes: Quantidade de bytes úteis da aplicação.
            crypto_payload_bytes: Quantidade de bytes produzidos pela criptografia.
            handshake_flights: Etapas de mensagens que compõem o handshake.
            include_tcp_connect: Indica se a abertura TCP será incluída.
            include_mqtt_connect: Indica se CONNECT e CONNACK serão incluídos.

        Retorna:
            Detalhamento dos tamanhos das mensagens do ciclo.
        """
        messages = self.build_cycle_messages(
            crypto_payload_bytes=crypto_payload_bytes,
            handshake_flights=handshake_flights,
            include_tcp_connect=include_tcp_connect,
            include_mqtt_connect=include_mqtt_connect,
        )
        tx = sum(
            m.base_wire_bytes for m in messages
            if m.direction == "iot_to_server"
        )
        rx = sum(
            m.base_wire_bytes for m in messages
            if m.direction == "server_to_iot"
        )
        ip_headers = sum(m.ip_header_bytes for m in messages)
        udp_headers = sum(m.udp_header_bytes for m in messages)
        wifi = sum(m.wifi_link_overhead_bytes for m in messages)
        return MessageSizeBreakdown(
            application_payload_bytes=application_payload_bytes,
            crypto_payload_bytes=crypto_payload_bytes,
            crypto_handshake_bytes=sum(
                m.handshake_material_bytes for m in messages
            ),
            handshake_protocol_overhead_bytes=sum(
                m.handshake_protocol_overhead_bytes for m in messages
            ),
            mqtt_connect_bytes=0,
            mqtt_connack_bytes=0,
            mqtt_publish_bytes=0,
            mqtt_ack_bytes=0,
            tcp_control_bytes=0,
            tcp_header_bytes=0,
            ip_header_bytes=ip_headers,
            wifi_link_overhead_bytes=wifi,
            transport_overhead_bytes=udp_headers + ip_headers,
            link_overhead_bytes=wifi,
            retransmitted_bytes=0.0,
            total_wire_bytes=float(tx + rx),
            tx_base_wire_bytes=tx,
            rx_base_wire_bytes=rx,
            wire_messages=messages,
            tcp_ack_policy="not_applicable_udp",
            connection_close_policy="connectionless_udp",
            protocol_name="coap",
            protocol_request_bytes=sum(
                m.application_protocol_bytes for m in messages
                if m.direction == "iot_to_server"
            ),
            protocol_response_bytes=sum(
                m.application_protocol_bytes for m in messages
                if m.direction == "server_to_iot"
            ),
            application_protocol_bytes=sum(
                m.application_protocol_bytes for m in messages
            ),
            udp_header_bytes=udp_headers,
        )

    def size_message(self, *, application_payload_bytes: int,
                     crypto_payload_bytes: int, handshake_tx_bytes: int = 0,
                     handshake_rx_bytes: int = 0) -> MessageSizeBreakdown:
        """Calcula o tamanho de uma mensagem.

        Parâmetros:
            application_payload_bytes: Quantidade de bytes úteis da aplicação.
            crypto_payload_bytes: Quantidade de bytes produzidos pela criptografia.
            handshake_tx_bytes: Bytes transmitidos durante o handshake.
            handshake_rx_bytes: Bytes recebidos durante o handshake.

        Retorna:
            Detalhamento dos tamanhos da mensagem modelada.
        """
        flights = []
        if handshake_tx_bytes:
            flights.append({
                "direction": "iot_to_server",
                "logical_type": "compatibility_handshake_client_flight",
                "payload_bytes": handshake_tx_bytes,
                "cryptographic_material_bytes": handshake_tx_bytes,
            })
        if handshake_rx_bytes:
            flights.append({
                "direction": "server_to_iot",
                "logical_type": "compatibility_handshake_server_flight",
                "payload_bytes": handshake_rx_bytes,
                "cryptographic_material_bytes": handshake_rx_bytes,
                "wait_rtt_fraction": 1.0,
            })
        return self.size_cycle(
            application_payload_bytes=application_payload_bytes,
            crypto_payload_bytes=crypto_payload_bytes,
            handshake_flights=flights,
        )


class HTTPProtocolModel(MQTTProtocolModel):
    """Modela HTTP/1.1 sobre TCP/IPv4 e Wi-Fi analítico."""

    def __init__(self, config: HTTPConfig, *, ip_header_bytes: int = 20,
                 tcp_header_bytes: int = 20,
                 link_overhead_bytes_per_frame: int = 38,
                 link_mtu_bytes: int = 1500) -> None:
        """Inicializa a instância e prepara seu estado interno.

        Parâmetros:
            config: Dicionário de configuração.
            ip_header_bytes: Tamanho do cabeçalho IPv4, em bytes.
            tcp_header_bytes: Tamanho do cabeçalho TCP, em bytes.
            link_overhead_bytes_per_frame: Sobrecarga de enlace por quadro, em bytes.
            link_mtu_bytes: MTU do enlace, em bytes.
        """
        for name, value in {
            "ip_header_bytes": ip_header_bytes,
            "tcp_header_bytes": tcp_header_bytes,
            "link_overhead_bytes_per_frame": link_overhead_bytes_per_frame,
            "link_mtu_bytes": link_mtu_bytes,
        }.items():
            if value < 0:
                raise ValueError(f"{name} cannot be negative")
        if link_mtu_bytes <= ip_header_bytes + tcp_header_bytes:
            raise ValueError("link_mtu_bytes is too small")
        self.config = config
        self.ip_header_bytes = ip_header_bytes
        self.tcp_header_bytes = tcp_header_bytes
        self.link_overhead_bytes_per_frame = link_overhead_bytes_per_frame
        self.link_mtu_bytes = link_mtu_bytes

    def request_size_bytes(self, payload_bytes: int) -> int:
        """Calcula o tamanho da requisição.

        Parâmetros:
            payload_bytes: Tamanho do conteúdo útil, em bytes.

        Retorna:
            Valor numérico calculado.
        """
        if payload_bytes < 0:
            raise ValueError("payload_bytes cannot be negative")
        header = (
            f"{self.config.method} {self.config.path} {self.config.version}\r\n"
            f"Host: {self.config.host}\r\n"
            f"Content-Type: {self.config.content_type}\r\n"
            f"Content-Length: {payload_bytes}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        return len(header) + payload_bytes

    def response_size_bytes(self) -> int:
        """Calcula o tamanho da resposta.

        Retorna:
            Valor numérico calculado.
        """
        return len((
            f"{self.config.version} {self.config.response_status}\r\n"
            "Content-Length: 0\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii"))

    def build_cycle_messages(self, *, crypto_payload_bytes: int,
                             handshake_flights: Sequence[Mapping[str, Any]] = (),
                             include_tcp_connect: bool = True,
                             include_mqtt_connect: bool = True) -> list[WireMessage]:
        """Cria as mensagens lógicas de um ciclo.

        Parâmetros:
            crypto_payload_bytes: Quantidade de bytes produzidos pela criptografia.
            handshake_flights: Etapas de mensagens que compõem o handshake.
            include_tcp_connect: Indica se a abertura TCP será incluída.
            include_mqtt_connect: Indica se CONNECT e CONNACK serão incluídos.

        Retorna:
            Lista com os elementos produzidos.
        """
        del include_mqtt_connect
        messages: list[WireMessage] = []
        if include_tcp_connect:
            messages.extend([
                self._message(
                    sequence=0, direction="iot_to_server", protocol="tcp",
                    logical_type="tcp_syn", payload_bytes=0,
                    force_segment=True, metadata={"tcp_control": True},
                ),
                self._message(
                    sequence=0, direction="server_to_iot", protocol="tcp",
                    logical_type="tcp_syn_ack", payload_bytes=0,
                    wait_phase="tcp_connect", wait_rtt_fraction=1.0,
                    force_segment=True, metadata={"tcp_control": True},
                ),
                self._message(
                    sequence=0, direction="iot_to_server", protocol="tcp",
                    logical_type="tcp_ack", payload_bytes=0,
                    force_segment=True, metadata={"tcp_control": True},
                ),
            ])
        for flight in handshake_flights:
            material = int(
                flight.get("cryptographic_material_bytes", flight.get("payload_bytes", 0))
            )
            overhead = int(flight.get("protocol_overhead_bytes", 0))
            payload = int(flight.get("payload_bytes", material + overhead))
            rtt_fraction = float(flight.get("wait_rtt_fraction", 0.0))
            messages.append(self._message(
                sequence=0,
                direction=str(flight["direction"]),
                protocol="authenticated_key_establishment",
                logical_type=str(flight["logical_type"]),
                payload_bytes=payload,
                wait_phase="crypto_handshake" if rtt_fraction else None,
                wait_rtt_fraction=rtt_fraction,
                handshake_material_bytes=material,
                handshake_protocol_overhead_bytes=overhead,
                metadata={"flight_number": flight.get("flight_number")},
            ))
        request = self.request_size_bytes(crypto_payload_bytes)
        messages.append(self._message(
            sequence=0,
            direction="iot_to_server",
            protocol="http_1_1",
            logical_type="http_post",
            payload_bytes=request,
            metadata={
                "method": self.config.method,
                "path": self.config.path,
                "content_type": self.config.content_type,
                "crypto_message_carrier": True,
                "post_handshake_operations_boundary": True,
                "tls_included": False,
            },
        ))
        messages[-1].application_protocol_bytes = request
        response = self.response_size_bytes()
        messages.append(self._message(
            sequence=0,
            direction="server_to_iot",
            protocol="http_1_1",
            logical_type="http_204_response",
            payload_bytes=response,
            wait_phase="http_response",
            wait_rtt_fraction=1.0,
            metadata={"status": self.config.response_status},
        ))
        messages[-1].application_protocol_bytes = response
        if self.config.tcp_ack_policy == "explicit_ack":
            expanded: list[WireMessage] = []
            for message in messages:
                expanded.append(message)
                if message.logical_payload_bytes and message.protocol != "tcp":
                    reverse = (
                        "server_to_iot"
                        if message.direction == "iot_to_server"
                        else "iot_to_server"
                    )
                    expanded.append(self._message(
                        sequence=0,
                        direction=reverse,
                        protocol="tcp",
                        logical_type=f"tcp_ack_for_{message.logical_type}",
                        payload_bytes=0,
                        force_segment=True,
                        metadata={"tcp_control": True, "explicit_ack": True},
                    ))
            messages = expanded
        for number, message in enumerate(messages, 1):
            message.sequence = number
        return messages

    def size_cycle(self, *, application_payload_bytes: int,
                   crypto_payload_bytes: int,
                   handshake_flights: Sequence[Mapping[str, Any]] = (),
                   include_tcp_connect: bool = True,
                   include_mqtt_connect: bool = True) -> MessageSizeBreakdown:
        """Calcula os tamanhos das mensagens de um ciclo.

        Parâmetros:
            application_payload_bytes: Quantidade de bytes úteis da aplicação.
            crypto_payload_bytes: Quantidade de bytes produzidos pela criptografia.
            handshake_flights: Etapas de mensagens que compõem o handshake.
            include_tcp_connect: Indica se a abertura TCP será incluída.
            include_mqtt_connect: Indica se CONNECT e CONNACK serão incluídos.

        Retorna:
            Detalhamento dos tamanhos das mensagens do ciclo.
        """
        messages = self.build_cycle_messages(
            crypto_payload_bytes=crypto_payload_bytes,
            handshake_flights=handshake_flights,
            include_tcp_connect=include_tcp_connect,
            include_mqtt_connect=include_mqtt_connect,
        )
        tx = sum(
            m.base_wire_bytes for m in messages
            if m.direction == "iot_to_server"
        )
        rx = sum(
            m.base_wire_bytes for m in messages
            if m.direction == "server_to_iot"
        )
        tcp_headers = sum(m.tcp_header_bytes for m in messages)
        ip_headers = sum(m.ip_header_bytes for m in messages)
        wifi = sum(m.wifi_link_overhead_bytes for m in messages)
        tcp_control = sum(
            m.tcp_header_bytes for m in messages
            if m.metadata.get("tcp_control")
        )
        return MessageSizeBreakdown(
            application_payload_bytes=application_payload_bytes,
            crypto_payload_bytes=crypto_payload_bytes,
            crypto_handshake_bytes=sum(
                m.handshake_material_bytes for m in messages
            ),
            handshake_protocol_overhead_bytes=sum(
                m.handshake_protocol_overhead_bytes for m in messages
            ),
            mqtt_connect_bytes=0,
            mqtt_connack_bytes=0,
            mqtt_publish_bytes=0,
            mqtt_ack_bytes=0,
            tcp_control_bytes=tcp_control,
            tcp_header_bytes=tcp_headers,
            ip_header_bytes=ip_headers,
            wifi_link_overhead_bytes=wifi,
            transport_overhead_bytes=tcp_headers + ip_headers,
            link_overhead_bytes=wifi,
            retransmitted_bytes=0.0,
            total_wire_bytes=float(tx + rx),
            tx_base_wire_bytes=tx,
            rx_base_wire_bytes=rx,
            wire_messages=messages,
            tcp_ack_policy=self.config.tcp_ack_policy,
            connection_close_policy=self.config.connection_close_policy,
            protocol_name="http",
            protocol_request_bytes=sum(
                m.application_protocol_bytes for m in messages
                if m.direction == "iot_to_server"
            ),
            protocol_response_bytes=sum(
                m.application_protocol_bytes for m in messages
                if m.direction == "server_to_iot"
            ),
            application_protocol_bytes=sum(
                m.application_protocol_bytes for m in messages
            ),
        )

    def size_message(self, *, application_payload_bytes: int,
                     crypto_payload_bytes: int, handshake_tx_bytes: int = 0,
                     handshake_rx_bytes: int = 0) -> MessageSizeBreakdown:
        """Calcula o tamanho de uma mensagem.

        Parâmetros:
            application_payload_bytes: Quantidade de bytes úteis da aplicação.
            crypto_payload_bytes: Quantidade de bytes produzidos pela criptografia.
            handshake_tx_bytes: Bytes transmitidos durante o handshake.
            handshake_rx_bytes: Bytes recebidos durante o handshake.

        Retorna:
            Detalhamento dos tamanhos da mensagem modelada.
        """
        flights = []
        if handshake_tx_bytes:
            flights.append({
                "direction": "iot_to_server",
                "logical_type": "compatibility_handshake_client_flight",
                "payload_bytes": handshake_tx_bytes,
                "cryptographic_material_bytes": handshake_tx_bytes,
            })
        if handshake_rx_bytes:
            flights.append({
                "direction": "server_to_iot",
                "logical_type": "compatibility_handshake_server_flight",
                "payload_bytes": handshake_rx_bytes,
                "cryptographic_material_bytes": handshake_rx_bytes,
                "wait_rtt_fraction": 1.0,
            })
        return self.size_cycle(
            application_payload_bytes=application_payload_bytes,
            crypto_payload_bytes=crypto_payload_bytes,
            handshake_flights=flights,
        )


@dataclass(frozen=True)
class RadioConfig:
    """Armazena os parâmetros do modelo de rádio."""
    effective_bitrate_bps: float
    retry_model: str = "expected"
    max_retries: int = 4
    association_duration_seconds: float = 0.25
    mqtt_ack_wait_seconds: float = 0.0
    handshake_round_trips: int = 1
    wifi_reconnect_energy_model: str = "incremental_direct_proxy"
    wifi_reconnect_proxy_multiplier: float = 1.0

    def __post_init__(self) -> None:
        """Valida e normaliza os campos após a criação do objeto."""
        if self.effective_bitrate_bps <= 0 or self.max_retries < 0:
            raise ValueError("invalid radio rate/retry configuration")
        if self.retry_model not in {"expected", "stochastic"}:
            raise ValueError("invalid retry model")
        if self.association_duration_seconds < 0 or self.mqtt_ack_wait_seconds < 0:
            raise ValueError("radio durations cannot be negative")
        if self.wifi_reconnect_energy_model not in {
            "incremental_direct_proxy", "state_based_vit", "disabled_for_sensitivity"
        }:
            raise ValueError("invalid Wi-Fi reconnect energy model")
        if self.wifi_reconnect_proxy_multiplier < 0:
            raise ValueError("Wi-Fi reconnect proxy multiplier cannot be negative")


@dataclass
class RadioTransfer:
    """Registra tentativas, tempos e bytes de uma transferência."""
    effective_bitrate_bps: float
    packet_loss_percent: float
    tx_bytes: float
    rx_bytes: float
    retransmitted_bytes: float
    tx_duration_seconds: float
    rx_duration_seconds: float
    response_wait_seconds: float
    expected_attempts: float
    delivered: bool
    wire_messages: list[dict[str, Any]] = field(default_factory=list)
    phase_wait_seconds: dict[str, float] = field(default_factory=dict)
    retry_interpretation: str = "expected_attempts_not_observed_events"


class RadioModel:
    """Calcula tentativas e duração de transferências pelo rádio."""
    def __init__(self, config: RadioConfig, *, random_seed: int = 42) -> None:
        """Inicializa a instância e prepara seu estado interno.

        Parâmetros:
            config: Dicionário de configuração.
            random_seed: Semente usada para tornar a geração reproduzível.
        """
        self.config, self.random = config, Random(random_seed)

    @staticmethod
    def expected_attempts(loss_probability: float, max_retries: int) -> float:
        """Calcula a quantidade esperada de tentativas.

        Parâmetros:
            loss_probability: Probabilidade de perda em cada tentativa.
            max_retries: Número máximo de retransmissões.

        Retorna:
            Valor numérico calculado.
        """
        if not 0 <= loss_probability <= 1:
            raise ValueError("loss_probability must be in [0, 1]")
        return sum(loss_probability**attempt for attempt in range(max_retries + 1))

    def _stochastic_attempts(self, probability: float) -> tuple[int, bool]:
        """Sorteia tentativas de transmissão conforme a perda configurada."""
        for attempt in range(1, self.config.max_retries + 2):
            if self.random.random() >= probability:
                return attempt, True
        return self.config.max_retries + 1, False

    def transfer(self, sizes: MessageSizeBreakdown, *, packet_loss_percent: float = 0.0,
                 effective_bitrate_bps: float | None = None,
                 rtt_ms: float | None = None, wait_for_mqtt_ack: bool = True,
                 include_handshake_wait: bool = False) -> RadioTransfer:
        """Calcula duração, tentativas e bytes da transferência.

        Parâmetros:
            sizes: Detalhamento dos tamanhos das mensagens.
            packet_loss_percent: Perda de pacotes em porcentagem.
            effective_bitrate_bps: Taxa efetiva do rádio, em bits por segundo.
            rtt_ms: Tempo de ida e volta do enlace, em milissegundos.
            wait_for_mqtt_ack: Indica se a espera pelo ACK MQTT será incluída.
            include_handshake_wait: Indica se a espera do handshake será contabilizada.

        Retorna:
            Resultado da transferência pelo modelo de rádio.
        """
        if not 0 <= packet_loss_percent <= 100:
            raise ValueError("packet_loss_percent must be in [0, 100]")
        bitrate = effective_bitrate_bps or self.config.effective_bitrate_bps
        probability = packet_loss_percent / 100.0
        tx = rx = retransmitted = 0.0
        delivered, attempts_list, output = True, [], []
        waits: dict[str, float] = {}
        rtt = max(0.0, (rtt_ms or 0.0) / 1000.0)
        for message in sizes.wire_messages:
            if self.config.retry_model == "expected":
                attempts = self.expected_attempts(probability, self.config.max_retries)
                success = probability < 1.0
            else:
                count, success = self._stochastic_attempts(probability)
                attempts = float(count)
            effective = message.base_wire_bytes * attempts
            retry_bytes = message.base_wire_bytes * max(0.0, attempts - 1.0)
            message.expected_attempts, message.delivered = attempts, success
            message.effective_wire_bytes, message.retransmitted_bytes = effective, retry_bytes
            attempts_list.append(attempts)
            retransmitted += retry_bytes
            delivered = delivered and success
            if message.direction == "iot_to_server":
                tx += effective
            elif success:
                rx += effective
            if message.wait_phase and success:
                waits[message.wait_phase] = waits.get(message.wait_phase, 0.0) + message.wait_rtt_fraction * rtt
            output.append(message.to_dict())
        sizes.retransmitted_bytes, sizes.total_wire_bytes = retransmitted, tx + rx
        return RadioTransfer(
            bitrate, packet_loss_percent, tx, rx, retransmitted,
            tx * 8.0 / bitrate, rx * 8.0 / bitrate, sum(waits.values()),
            sum(attempts_list) / len(attempts_list) if attempts_list else 1.0,
            delivered, output, waits,
            "expected_attempts_per_logical_message_not_observed_events"
            if self.config.retry_model == "expected"
            else "seeded_stochastic_attempts_per_logical_message",
        )


class ProtocolModel:
    """Cria modelos de protocolo a partir das configurações correspondentes."""

    @staticmethod
    def create(
        name: str,
        config: MQTTConfig | CoAPConfig | HTTPConfig,
        **kwargs: int,
    ) -> MQTTProtocolModel | CoAPProtocolModel | HTTPProtocolModel:
        """Cria o modelo do protocolo solicitado.

        Parâmetros:
            name: Nome usado para identificar o objeto ou protocolo.
            config: Dicionário de configuração.
            **kwargs: Argumentos nomeados adicionais.

        Retorna:
            Modelo MQTT, CoAP ou HTTP correspondente ao nome informado.
        """
        normalized = name.lower()
        model_types = {
            "mqtt": (MQTTConfig, MQTTProtocolModel),
            "coap": (CoAPConfig, CoAPProtocolModel),
            "http": (HTTPConfig, HTTPProtocolModel),
        }
        if normalized not in model_types:
            raise ValueError(f"physical protocol model not implemented: {name}")
        expected_type, model_type = model_types[normalized]
        if not isinstance(config, expected_type):
            raise TypeError(
                f"{normalized} requires {expected_type.__name__}, "
                f"got {type(config).__name__}"
            )
        return model_type(config, **kwargs)
