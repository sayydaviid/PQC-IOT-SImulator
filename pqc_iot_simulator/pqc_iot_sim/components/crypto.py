"""Modela criptografia clássica, pós-quântica e híbrida orientada a sessões."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable
import base64
import hashlib
import hmac
import importlib
import json
import os
import time
import uuid

from .energy import CalibrationRecord
from .logger import Logger


ALGORITHM_WIRE_SIZES: dict[str, dict[str, int]] = {
    "X25519": {"public_key": 32, "signature_public_key": 32, "signature": 64},
    "ML-KEM-512": {"public_key": 800, "ciphertext": 768},
    "ML-DSA-44": {"public_key": 1312, "signature": 2420},
}

HANDSHAKE_MODEL_VERSION = "pqc-iot-authenticated-ke-v1"
HKDF_DOMAIN_LABEL = b"pqc-iot-session-v1"

# Table 4 of HySecure (Electronics 2025, 14, 3908).  The simulator keeps its
# standardized algorithm-size contract and uses the published total as an
# explicit full-handshake traffic envelope.  It does not claim TLS byte parity.
HYSECURE_FULL_HANDSHAKE = {
    "classical": {"certificate_bytes": 592, "total_traffic_bytes": 2048},
    "pqc": {"certificate_bytes": 3404, "total_traffic_bytes": 16997},
    "hybrid": {"certificate_bytes": 3996, "total_traffic_bytes": 18463},
}


@dataclass
class ParticipantOperation:
    """Representa uma operação criptográfica executada por um participante."""
    participant: str
    operation: str
    algorithm: str
    phase: str
    before_send: bool
    included_in_primary_energy_budget: bool


@dataclass
class HandshakeMessage:
    """Representa uma mensagem lógica trocada durante o handshake."""
    logical_type: str
    materials: list[dict[str, Any]]
    cryptographic_material_bytes: int
    protocol_overhead_bytes: int = 0

    @property
    def payload_bytes(self) -> int:
        """Calcula o tamanho do conteúdo útil em bytes.

        Retorna:
            Valor numérico calculado.
        """
        return self.cryptographic_material_bytes + self.protocol_overhead_bytes


@dataclass
class HandshakeFlight:
    """Agrupa mensagens enviadas na mesma etapa do handshake."""
    flight_number: int
    origin: str
    destination: str
    direction: str
    logical_type: str
    message: HandshakeMessage
    operations_before_send: list[ParticipantOperation]
    wait_rtt_fraction: float
    credential_provisioning: dict[str, str]
    algorithms: list[str]

    def to_wire_dict(self) -> dict[str, Any]:
        """Converte a mensagem para o formato serializável do transporte.

        Retorna:
            Dicionário com os dados produzidos.
        """
        return {
            "flight_number": self.flight_number,
            "origin": self.origin,
            "destination": self.destination,
            "direction": self.direction,
            "logical_type": self.logical_type,
            "payload_bytes": self.message.payload_bytes,
            "cryptographic_material_bytes": self.message.cryptographic_material_bytes,
            "protocol_overhead_bytes": self.message.protocol_overhead_bytes,
            "wait_rtt_fraction": self.wait_rtt_fraction,
        }


@dataclass
class HandshakePlan:
    """Descreve mensagens, etapas e tamanhos de um handshake."""
    model_version: str
    mode: str
    authentication_model: str
    credential_provisioning: dict[str, str]
    transcript_hash_hex: str
    transcript_fields: dict[str, Any]
    flights: list[HandshakeFlight]
    protocol_overhead_bytes: int = 0
    post_response_operations: list[ParticipantOperation] = field(default_factory=list)
    handshake_variant: str = "preprovisioned"
    reference_traffic_total_bytes: int | None = None
    reference_source: str | None = None

    @property
    def cryptographic_material_bytes(self) -> int:
        """Calcula os bytes ocupados pelo material criptográfico.

        Retorna:
            Valor numérico calculado.
        """
        return sum(f.message.cryptographic_material_bytes for f in self.flights)

    @property
    def payload_bytes(self) -> int:
        """Calcula o tamanho do conteúdo útil em bytes.

        Retorna:
            Valor numérico calculado.
        """
        return sum(f.message.payload_bytes for f in self.flights)

    def to_dict(self) -> dict[str, Any]:
        """Converte o objeto em um dicionário serializável.

        Retorna:
            Dicionário com os dados produzidos.
        """
        return asdict(self)

    def wire_flights(self) -> list[dict[str, Any]]:
        """Retorna as etapas do handshake que trafegam pela rede.

        Retorna:
            Dicionário com os dados produzidos.
        """
        return [flight.to_wire_dict() for flight in self.flights]


@dataclass
class CryptoOperation:
    """Registra uma operação criptográfica e seu custo."""
    operation: str
    participant: str
    algorithm: str
    duration_seconds: float
    input_bytes: int
    output_bytes: int
    energy_j: float | None
    timing_source: str
    host_wallclock_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    current_ma: float | None = None
    voltage_v: float | None = None
    parameter_source: str | None = None
    parameter_status: str = "configured"
    included_in_primary_energy_budget: bool = False
    primitive_execution: str = "analytical_size_only"
    target_timing_seconds: float | None = None
    wire_size_model: str = "algorithm_or_protocol_size_contract"


@dataclass
class CryptoSession:
    """Mantém o estado de uma sessão criptográfica reutilizável."""
    session_id: str
    source: str
    destination: str
    mode: str
    established_at_seconds: float
    lifetime_seconds: float
    max_messages: int
    session_key: bytes = field(repr=False)
    handshake_bytes: int = 0
    handshake_tx_bytes: int = 0
    handshake_rx_bytes: int = 0
    handshake_operations: list[CryptoOperation] = field(default_factory=list)
    handshake_plan: HandshakePlan | None = None
    transcript_hash: bytes = field(default=b"", repr=False)
    nonce_prefix: bytes = field(default=b"", repr=False)
    nonce_counter: int = 0
    messages: int = 0
    closed: bool = False


@dataclass
class SessionEstablishmentResult:
    """Reúne o resultado da criação de uma sessão criptográfica."""
    session: CryptoSession
    handshake_bytes: int
    handshake_tx_bytes: int
    handshake_rx_bytes: int
    operations: list[CryptoOperation]
    calibration_status: str
    energy_confidence: str
    handshake_plan: HandshakePlan | None = None
    transcript_hash_hex: str = ""
    handshake_protocol_overhead_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Converte o objeto em um dicionário serializável.

        Retorna:
            Dicionário com os dados produzidos.
        """
        data = asdict(self)
        data["session"]["session_key"] = "<redacted>"
        return data


@dataclass
class CryptoResult:
    """Reúne o resultado da proteção criptográfica de uma mensagem."""
    mode: str
    backend: str
    algorithm: str
    payload: dict[str, Any]
    original_size_bytes: int
    protected_size_bytes: int
    overhead_bytes: int
    operation_time_seconds: float
    energy_cost: float
    metadata: dict[str, Any] = field(default_factory=dict)
    handshake_size_bytes: int = 0
    operations: list[CryptoOperation] = field(default_factory=list)
    timing_source: str = "host_wallclock"
    calibration_status: str = "not_applicable"
    energy_confidence: str = "provisional"

    @property
    def energy_j(self) -> float:
        """Calcula a energia total consumida pela operação.

        Retorna:
            Valor numérico calculado.
        """
        return self.energy_cost

    def to_dict(self) -> dict[str, Any]:
        """Converte o objeto em um dicionário serializável.

        Retorna:
            Dicionário com os dados produzidos.
        """
        return asdict(self)


class CryptoManager:
    """Gerencia sessões reutilizáveis e operações por participante."""

    def __init__(
        self,
        mode: str = "classical",
        kem: str = "ML-KEM-512",
        pqc_signature: str = "ML-DSA-44",
        classical_signature: str = "ed25519",
        use_classical_signature: bool = True,
        use_pqc_signature: bool = True,
        logger: Logger | None = None,
        backend: str | None = None,
        timing_mode: str = "host_wallclock",
        target_operations: dict[str, Any] | None = None,
        target_metadata: dict[str, Any] | None = None,
        session_lifetime_seconds: float = 3600.0,
        session_max_messages: int = 100,
        strict_target_calibration: bool = False,
        server_classical_credential_id: str = "server-ed25519-identity-v1",
        server_pqc_credential_id: str = "server-mldsa44-identity-v1",
        server_kem_credential_id: str = "server-mlkem512-static-v1",
        session_context: str = "mqtt-qos1-telemetry",
        handshake_variant: str = "preprovisioned",
    ) -> None:
        """Inicializa a instância e prepara seu estado interno.

        Parâmetros:
            mode: Modo selecionado.
            kem: Algoritmo de encapsulamento de chaves.
            pqc_signature: Algoritmo pós-quântico de assinatura.
            classical_signature: Algoritmo clássico de assinatura.
            use_classical_signature: Indica se a assinatura clássica será usada.
            use_pqc_signature: Indica se a assinatura pós-quântica será usada.
            logger: Registrador usado pelo componente.
            backend: Backend criptográfico utilizado.
            timing_mode: Origem usada para os tempos criptográficos.
            target_operations: Calibrações das operações no dispositivo-alvo.
            target_metadata: Metadados do dispositivo usado como alvo.
            session_lifetime_seconds: Validade máxima da sessão, em segundos.
            session_max_messages: Quantidade máxima de mensagens por sessão.
            strict_target_calibration: Exige calibração completa do dispositivo-alvo quando verdadeiro.
            server_classical_credential_id: Identificador da credencial clássica do servidor.
            server_pqc_credential_id: Identificador da credencial PQC do servidor.
            server_kem_credential_id: Identificador da credencial KEM do servidor.
            session_context: Contexto associado à derivação das chaves da sessão.
            handshake_variant: Variante usada para estabelecer a sessão.
        """
        self.mode = mode
        self.kem = kem
        self.pqc_signature = pqc_signature
        self.classical_signature = classical_signature
        self.use_classical_signature = use_classical_signature
        self.use_pqc_signature = use_pqc_signature
        self.logger = logger or Logger(name="CryptoManager")
        self.timing_mode = timing_mode
        self.target_operations = target_operations or {}
        self.target_metadata = target_metadata or {}
        self.session_lifetime_seconds = float(session_lifetime_seconds)
        self.session_max_messages = int(session_max_messages)
        self.strict_target_calibration = bool(strict_target_calibration)
        self.server_classical_credential_id = server_classical_credential_id
        self.server_pqc_credential_id = server_pqc_credential_id
        self.server_kem_credential_id = server_kem_credential_id
        self.session_context = session_context
        self.handshake_variant = handshake_variant
        self.valid_modes = ["classical", "pqc", "hybrid"]
        self.backend = backend or self._backend_from_mode(mode)
        self.sessions: dict[tuple[str, str], CryptoSession] = {}
        self.operation_log: list[CryptoOperation] = []
        self.handshake_count = 0
        self._validate_config()

    def configure(
        self,
        mode: str | None = None,
        kem: str | None = None,
        signature: str | None = None,
        pqc_signature: str | None = None,
        classical_signature: str | None = None,
        use_classical_signature: bool | None = None,
        use_pqc_signature: bool | None = None,
        backend: str | None = None,
        timing_mode: str | None = None,
        target_operations: dict[str, Any] | None = None,
        target_metadata: dict[str, Any] | None = None,
        session_lifetime_seconds: float | None = None,
        session_max_messages: int | None = None,
        strict_target_calibration: bool | None = None,
        handshake_variant: str | None = None,
        **_: Any,
    ) -> "CryptoManager":
        """Atualiza os parâmetros usados pelo componente.

        Parâmetros:
            mode: Modo selecionado.
            kem: Algoritmo de encapsulamento de chaves.
            signature: Algoritmo de assinatura selecionado.
            pqc_signature: Algoritmo pós-quântico de assinatura.
            classical_signature: Algoritmo clássico de assinatura.
            use_classical_signature: Indica se a assinatura clássica será usada.
            use_pqc_signature: Indica se a assinatura pós-quântica será usada.
            backend: Backend criptográfico utilizado.
            timing_mode: Origem usada para os tempos criptográficos.
            target_operations: Calibrações das operações no dispositivo-alvo.
            target_metadata: Metadados do dispositivo usado como alvo.
            session_lifetime_seconds: Validade máxima da sessão, em segundos.
            session_max_messages: Quantidade máxima de mensagens por sessão.
            strict_target_calibration: Exige calibração completa do dispositivo-alvo quando verdadeiro.
            handshake_variant: Variante usada para estabelecer a sessão.
            **_: Argumento posicional ignorado pela função.

        Retorna:
            A própria instância, permitindo encadear operações.
        """
        if mode is not None:
            self.mode = mode
        if kem is not None:
            self.kem = kem
        if signature is not None and pqc_signature is None:
            self.pqc_signature = signature
        if pqc_signature is not None:
            self.pqc_signature = pqc_signature
        if classical_signature is not None:
            self.classical_signature = classical_signature
        if use_classical_signature is not None:
            self.use_classical_signature = use_classical_signature
        if use_pqc_signature is not None:
            self.use_pqc_signature = use_pqc_signature
        if timing_mode is not None:
            self.timing_mode = timing_mode
        if target_operations is not None:
            self.target_operations = target_operations
        if target_metadata is not None:
            self.target_metadata = target_metadata
        if session_lifetime_seconds is not None:
            self.session_lifetime_seconds = float(session_lifetime_seconds)
        if session_max_messages is not None:
            self.session_max_messages = int(session_max_messages)
        if strict_target_calibration is not None:
            self.strict_target_calibration = bool(strict_target_calibration)
        if handshake_variant is not None:
            self.handshake_variant = handshake_variant
        self.backend = backend or self._backend_from_mode(self.mode)
        self._validate_config()
        return self

    def should_rekey(
        self,
        source: str,
        destination: str,
        simulation_time_seconds: float,
        *,
        device_restarted: bool = False,
    ) -> bool:
        """Informa se a sessão atual precisa ser renovada.

        Parâmetros:
            source: Identificador da origem.
            destination: Identificador do destino.
            simulation_time_seconds: Instante simulado do ciclo, em segundos.
            device_restarted: Indica se o dispositivo reiniciou.

        Retorna:
            True quando a condição é satisfeita; caso contrário, False.
        """
        session = self.sessions.get((source, destination))
        if session is None or session.closed or device_restarted:
            return True
        age = simulation_time_seconds - session.established_at_seconds
        return age >= session.lifetime_seconds or session.messages >= session.max_messages

    def establish_session(
        self,
        source: str,
        destination: str,
        simulation_time_seconds: float = 0.0,
    ) -> SessionEstablishmentResult:
        """Estabelece uma nova sessão criptográfica.

        Parâmetros:
            source: Identificador da origem.
            destination: Identificador do destino.
            simulation_time_seconds: Instante simulado do ciclo, em segundos.

        Retorna:
            Resultado do estabelecimento da sessão.
        """
        if simulation_time_seconds < 0:
            raise ValueError("simulation_time_seconds cannot be negative")
        old = self.sessions.get((source, destination))
        if old is not None:
            old.closed = True

        operations: list[CryptoOperation] = []
        secrets: list[tuple[str, bytes]] = []
        materials: dict[str, bytes] = {}

        if self.mode in {"classical", "hybrid"}:
            classical_secret, classical_ops, classical_materials = (
                self._establish_classical(source, destination)
            )
            secrets.append(("x25519", classical_secret))
            operations.extend(classical_ops)
            materials.update(classical_materials)
            if not classical_materials:
                materials["x25519_client_public"] = self._analytical_bytes(
                    source, destination, simulation_time_seconds, "x25519-client", 32
                )
                materials["x25519_server_public"] = self._analytical_bytes(
                    source, destination, simulation_time_seconds, "x25519-server", 32
                )

        if self.mode in {"pqc", "hybrid"}:
            pqc_secret, pqc_ops, pqc_materials = self._establish_pqc(
                source, destination
            )
            secrets.append(("ml_kem_512", pqc_secret))
            operations.extend(pqc_ops)
            materials.update(pqc_materials)
            if not pqc_materials:
                materials["ml_kem_ciphertext"] = self._analytical_bytes(
                    source, destination, simulation_time_seconds,
                    "ml-kem-ciphertext", 768,
                )

        transcript_fields = self._transcript_fields(source, destination, materials)
        transcript = json.dumps(
            transcript_fields, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        transcript_hash = hashlib.sha256(transcript).digest()
        operations.extend(
            self._transcript_authentication_operations(
                source, destination, transcript_hash
            )
        )
        for operation in operations:
            if operation.operation in {"ed25519_sign", "ed25519_verify", "ml_dsa_sign", "ml_dsa_verify"}:
                operation.metadata["authenticated_transcript_hash"] = transcript_hash.hex()
                operation.input_bytes = len(transcript_hash)

        encoded_secrets = b"".join(
            len(secret).to_bytes(4, "big") + secret for _, secret in secrets
        )
        salt = hashlib.sha256(
            (HANDSHAKE_MODEL_VERSION + "|" + source + "|" + destination).encode("utf-8")
        ).digest()
        info = HKDF_DOMAIN_LABEL + transcript_hash + self.session_context.encode("utf-8")
        prk = self._hkdf_extract(salt, encoded_secrets)
        session_key = self._hkdf_expand(prk, info, 32)
        for participant, host_id in (("iot_client", source), ("server", destination)):
            operations.extend(
                [
                    self._operation(
                        "hkdf_extract", participant, "HKDF-Extract/HMAC-SHA-256",
                        len(encoded_secrets), len(prk), host_id=host_id,
                        callback=lambda: self._hkdf_extract(salt, encoded_secrets),
                    ),
                    self._operation(
                        "hkdf_expand", participant, "HKDF-Expand/HMAC-SHA-256",
                        len(info), len(session_key), host_id=host_id,
                        callback=lambda: self._hkdf_expand(prk, info, 32),
                    ),
                ]
            )

        plan = self._build_handshake_plan(
            source, destination, transcript_fields, transcript_hash, operations
        )
        tx_bytes = sum(
            flight.message.payload_bytes for flight in plan.flights
            if flight.direction == "iot_to_server"
        )
        rx_bytes = sum(
            flight.message.payload_bytes for flight in plan.flights
            if flight.direction == "server_to_iot"
        )

        session = CryptoSession(
            session_id=str(uuid.uuid4()),
            source=source,
            destination=destination,
            mode=self.mode,
            established_at_seconds=simulation_time_seconds,
            lifetime_seconds=self.session_lifetime_seconds,
            max_messages=self.session_max_messages,
            session_key=session_key,
            handshake_bytes=tx_bytes + rx_bytes,
            handshake_tx_bytes=tx_bytes,
            handshake_rx_bytes=rx_bytes,
            handshake_operations=operations,
            handshake_plan=plan,
            transcript_hash=transcript_hash,
            nonce_prefix=hashlib.sha256(
                (source + "|" + destination + "|" + transcript_hash.hex()).encode("utf-8")
            ).digest()[:8],
        )
        self.sessions[(source, destination)] = session
        self.operation_log.extend(operations)
        self.handshake_count += 1
        status, confidence = self._calibration_assessment(operations)
        return SessionEstablishmentResult(
            session=session,
            handshake_bytes=session.handshake_bytes,
            handshake_tx_bytes=tx_bytes,
            handshake_rx_bytes=rx_bytes,
            operations=operations,
            calibration_status=status,
            energy_confidence=confidence,
            handshake_plan=plan,
            transcript_hash_hex=transcript_hash.hex(),
            handshake_protocol_overhead_bytes=plan.protocol_overhead_bytes,
        )

    def protect_message(
        self,
        payload: dict[str, Any],
        *,
        source: str,
        destination: str,
        simulation_time_seconds: float = 0.0,
    ) -> CryptoResult:
        """Protege uma mensagem com a sessão criptográfica ativa.

        Parâmetros:
            payload: Conteúdo útil da mensagem.
            source: Identificador da origem.
            destination: Identificador do destino.
            simulation_time_seconds: Instante simulado do ciclo, em segundos.

        Retorna:
            Resultado da proteção criptográfica da mensagem.
        """
        if self.should_rekey(source, destination, simulation_time_seconds):
            raise RuntimeError("no valid crypto session; call establish_session first")
        session = self.sessions[(source, destination)]
        message = self._serialize_payload(payload)

        if session.nonce_counter >= 2**32:
            raise RuntimeError("AES-GCM nonce counter exhausted; rekey is required")
        nonce_counter = session.nonce_counter
        nonce = session.nonce_prefix + nonce_counter.to_bytes(4, "big")
        session.nonce_counter += 1
        primitive_execution = "analytical_size_only"

        if self.timing_mode == "host_wallclock":
            try:
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            except ImportError as exc:
                raise RuntimeError(
                    "cryptography is required for host_wallclock AES-GCM execution"
                ) from exc
            aes = AESGCM(session.session_key)
            primitive_execution = "AESGCM_from_cryptography"
            encrypted_holder: dict[str, bytes] = {}

            def encrypt() -> bytes:
                """Criptografa os dados com a chave e o nonce informados.

                Retorna:
                    Texto cifrado autenticado.
                """
                if aes is None:
                    raise RuntimeError("AES-GCM backend is unavailable")
                encrypted_holder["ciphertext"] = aes.encrypt(nonce, message, None)
                return encrypted_holder["ciphertext"]

            encrypt_op = self._operation(
                "aes_gcm_encrypt",
                "iot_client",
                "AES-256-GCM",
                len(message),
                len(message) + 16,
                host_id=source,
                callback=encrypt,
            )
            ciphertext = encrypted_holder["ciphertext"]
            decrypt_op = self._operation(
                "aes_gcm_decrypt",
                "server",
                "AES-256-GCM",
                len(ciphertext),
                len(message),
                host_id=destination,
                callback=lambda: aes.decrypt(nonce, ciphertext, None) if aes is not None else None,
            )
        else:
            # No substitute cipher is executed in analytical mode.  Only the
            # AES-GCM wire contract (ciphertext length plus 16-byte tag) is used.
            ciphertext = None
            encrypt_op = self._operation(
                "aes_gcm_encrypt",
                "iot_client",
                "AES-256-GCM",
                len(message),
                len(message) + 16,
                host_id=source,
            )
            decrypt_op = self._operation(
                "aes_gcm_decrypt",
                "server",
                "AES-256-GCM",
                len(message) + 16,
                len(message),
                host_id=destination,
            )

        operations = [encrypt_op, decrypt_op]
        self.operation_log.extend(operations)
        session.messages += 1
        protected_size = len(message) + 12 + 16
        status, confidence = self._calibration_assessment(operations)
        source_energy = sum(
            operation.energy_j or 0.0
            for operation in operations
            if operation.participant == "iot_client"
        )
        protected_payload = {
            "crypto_mode": self.mode,
            "crypto_backend": self.backend,
            # In analytical mode no ciphertext is produced.  Calling that
            # execution "encrypted" would conflate a wire-size contract with
            # execution of the primitive.
            "encrypted": ciphertext is not None,
            "protection_size_model_applied": True,
            "ciphertext": (
                base64.b64encode(ciphertext).decode("ascii")
                if ciphertext is not None else None
            ),
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "original_size_bytes": len(message),
            "protected_size_bytes": protected_size,
            "overhead_bytes": protected_size - len(message),
            "session_id": session.session_id,
        }
        return CryptoResult(
            mode=self.mode,
            backend=self.backend,
            algorithm=f"{self._session_algorithm()} / AES-256-GCM session",
            payload=protected_payload,
            original_size_bytes=len(message),
            protected_size_bytes=protected_size,
            overhead_bytes=protected_size - len(message),
            operation_time_seconds=sum(op.duration_seconds for op in operations),
            energy_cost=source_energy,
            metadata={
                "session_id": session.session_id,
                "messages_in_session": session.messages,
                "handshake_material_in_message": False,
                "timing_source": self.timing_mode,
                "primitive_execution": primitive_execution,
                "wire_size_model": "aes_gcm_plaintext_plus_12_byte_nonce_plus_16_byte_tag",
                "nonce_strategy": "per_session_64_bit_prefix_plus_32_bit_monotonic_counter",
                "nonce_counter": nonce_counter,
                "nonce_unique_within_session": True,
            },
            operations=operations,
            timing_source=self.timing_mode,
            calibration_status=status,
            energy_confidence=confidence,
        )

    def close_session(self, source: str, destination: str) -> None:
        """Encerra e remove a sessão criptográfica ativa.

        Parâmetros:
            source: Identificador da origem.
            destination: Identificador do destino.
        """
        session = self.sessions.get((source, destination))
        if session is not None:
            session.closed = True

    def protect(self, payload: dict[str, Any]) -> CryptoResult:
        """Mantém compatibilidade; novas simulações usam sessões persistentes.

        Parâmetros:
            payload: Conteúdo da aplicação que será protegido.

        Retorna:
            Resultado da proteção criptográfica.
        """

        source = "legacy_iot_source"
        destination = "legacy_destination"
        establishment = self.establish_session(source, destination, 0.0)
        result = self.protect_message(
            payload,
            source=source,
            destination=destination,
            simulation_time_seconds=0.0,
        )
        result.handshake_size_bytes = establishment.handshake_bytes
        result.operations = establishment.operations + result.operations
        result.operation_time_seconds = sum(op.duration_seconds for op in result.operations)
        result.protected_size_bytes += establishment.handshake_bytes
        result.overhead_bytes = result.protected_size_bytes - result.original_size_bytes
        result.payload["protected_size_bytes"] = result.protected_size_bytes
        result.payload["overhead_bytes"] = result.overhead_bytes
        result.metadata["compatibility_wrapper"] = True
        result.metadata["handshake_material_in_message"] = True
        return result

    def _establish_classical(
        self, source: str, destination: str
    ) -> tuple[bytes, list[CryptoOperation], dict[str, bytes]]:
        """Executa as operações do estabelecimento clássico de sessão."""
        operations: list[CryptoOperation] = []
        if self.timing_mode in {"target_profile", "analytical_size_only"}:
            for name, participant, algorithm, input_size, output_size, host_id in [
                ("x25519_keygen", "iot_client", "X25519", 0, 32, source),
                ("x25519_keygen", "server", "X25519", 0, 32, destination),
                ("x25519_exchange", "iot_client", "X25519", 32, 32, source),
                ("x25519_exchange", "server", "X25519", 32, 32, destination),
            ]:
                operations.append(self._operation(name, participant, algorithm, input_size, output_size, host_id=host_id))
            return os.urandom(32), operations, {}

        from cryptography.hazmat.primitives.asymmetric import x25519
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

        source_key: dict[str, Any] = {}
        destination_key: dict[str, Any] = {}
        operations.append(self._operation("x25519_keygen", "iot_client", "X25519", 0, 32, host_id=source, callback=lambda: source_key.setdefault("key", x25519.X25519PrivateKey.generate())))
        operations.append(self._operation("x25519_keygen", "server", "X25519", 0, 32, host_id=destination, callback=lambda: destination_key.setdefault("key", x25519.X25519PrivateKey.generate())))
        shared: dict[str, bytes] = {}
        operations.append(self._operation("x25519_exchange", "iot_client", "X25519", 32, 32, host_id=source, callback=lambda: shared.setdefault("source", source_key["key"].exchange(destination_key["key"].public_key()))))
        operations.append(self._operation("x25519_exchange", "server", "X25519", 32, 32, host_id=destination, callback=lambda: shared.setdefault("destination", destination_key["key"].exchange(source_key["key"].public_key()))))
        if shared["source"] != shared["destination"]:
            raise RuntimeError("X25519 participants derived different secrets")
        materials = {
            "x25519_client_public": source_key["key"].public_key().public_bytes(
                Encoding.Raw, PublicFormat.Raw
            ),
            "x25519_server_public": destination_key["key"].public_key().public_bytes(
                Encoding.Raw, PublicFormat.Raw
            ),
        }
        return shared["source"], operations, materials

    def _establish_pqc(
        self, source: str, destination: str
    ) -> tuple[bytes, list[CryptoOperation], dict[str, bytes]]:
        """Executa as operações do estabelecimento pós-quântico de sessão."""
        operations: list[CryptoOperation] = []
        kem_sizes = self._algorithm_sizes(self.kem)
        if self.timing_mode in {"target_profile", "analytical_size_only"}:
            operations.extend([
                self._operation("ml_kem_encaps", "iot_client", self.kem, kem_sizes["public_key"], kem_sizes["ciphertext"], host_id=source),
                self._operation("ml_kem_decaps", "server", self.kem, kem_sizes["ciphertext"], 32, host_id=destination),
            ])
            return os.urandom(32), operations, {}

        oqs = self._import_oqs()
        self._validate_liboqs(oqs)
        server = oqs.KeyEncapsulation(self.kem)
        client = oqs.KeyEncapsulation(self.kem)
        values: dict[str, bytes] = {}
        # Server KEM key generation is provisioning outside the measured flight.
        values["public"] = server.generate_keypair()

        def encapsulate() -> bytes:
            """Executa a encapsulação do segredo compartilhado.

            Retorna:
                Ciphertext do ML-KEM enviado ao servidor.
            """
            ciphertext, secret = client.encap_secret(values["public"])
            values["ciphertext"] = ciphertext
            values["source_secret"] = secret
            return ciphertext

        operations.append(self._operation("ml_kem_encaps", "iot_client", self.kem, len(values["public"]), kem_sizes["ciphertext"], host_id=source, callback=encapsulate))
        operations.append(self._operation("ml_kem_decaps", "server", self.kem, len(values["ciphertext"]), 32, host_id=destination, callback=lambda: values.setdefault("destination_secret", server.decap_secret(values["ciphertext"]))))
        if values["source_secret"] != values["destination_secret"]:
            raise RuntimeError("ML-KEM participants derived different secrets")
        return (
            values["source_secret"],
            operations,
            {"ml_kem_ciphertext": values["ciphertext"]},
        )

    def _transcript_authentication_operations(
        self, source: str, destination: str, transcript_hash: bytes
    ) -> list[CryptoOperation]:
        """Cria as operações de autenticação do transcript do handshake."""
        operations: list[CryptoOperation] = []
        if self.timing_mode in {"target_profile", "analytical_size_only"}:
            if self.mode in {"classical", "hybrid"} and self.use_classical_signature:
                operations.extend([
                    self._operation("ed25519_sign", "server", "Ed25519", 32, 64, host_id=destination),
                    self._operation("ed25519_verify", "iot_client", "Ed25519", 32, 0, host_id=source),
                ])
            if self.mode in {"pqc", "hybrid"} and self.use_pqc_signature:
                operations.extend([
                    self._operation("ml_dsa_sign", "server", self.pqc_signature, 32, 2420, host_id=destination),
                    self._operation("ml_dsa_verify", "iot_client", self.pqc_signature, 32, 0, host_id=source),
                ])
            return operations

        if self.mode in {"classical", "hybrid"} and self.use_classical_signature:
            from cryptography.hazmat.primitives.asymmetric import ed25519
            signer = ed25519.Ed25519PrivateKey.generate()  # provisioned outside timing
            signature: dict[str, bytes] = {}
            operations.extend([
                self._operation("ed25519_sign", "server", "Ed25519", 32, 64,
                                host_id=destination,
                                callback=lambda: signature.setdefault("value", signer.sign(transcript_hash))),
                self._operation("ed25519_verify", "iot_client", "Ed25519", 32, 0,
                                host_id=source,
                                callback=lambda: signer.public_key().verify(signature["value"], transcript_hash)),
            ])
        if self.mode in {"pqc", "hybrid"} and self.use_pqc_signature:
            oqs = self._import_oqs()
            signer = oqs.Signature(self.pqc_signature)
            public = signer.generate_keypair()  # provisioned outside timing
            signature: dict[str, bytes] = {}
            operations.extend([
                self._operation("ml_dsa_sign", "server", self.pqc_signature, 32, 2420,
                                host_id=destination,
                                callback=lambda: signature.setdefault("value", signer.sign(transcript_hash))),
                self._operation("ml_dsa_verify", "iot_client", self.pqc_signature, 32, 0,
                                host_id=source,
                                callback=lambda: self._require_true(
                                    signer.verify(transcript_hash, signature["value"], public),
                                    "ML-DSA transcript signature verification failed",
                                )),
            ])
        return operations

    @staticmethod
    def _require_true(value: bool, message: str) -> bool:
        """Interrompe a operação quando uma verificação criptográfica falha."""
        if not value:
            raise RuntimeError(message)
        return value

    @staticmethod
    def _hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
        """Executa a etapa Extract do HKDF com HMAC-SHA-256."""
        return hmac.new(salt, ikm, hashlib.sha256).digest()

    @staticmethod
    def _hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
        """Executa a etapa Expand do HKDF com HMAC-SHA-256."""
        if not 0 < length <= 255 * hashlib.sha256().digest_size:
            raise ValueError("invalid HKDF output length")
        output, previous, counter = bytearray(), b"", 1
        while len(output) < length:
            previous = hmac.new(
                prk, previous + info + bytes([counter]), hashlib.sha256
            ).digest()
            output.extend(previous)
            counter += 1
        return bytes(output[:length])

    @staticmethod
    def _analytical_bytes(
        source: str, destination: str, simulation_time_seconds: float,
        label: str, length: int,
    ) -> bytes:
        """Obtém o tamanho analítico de uma mensagem de handshake."""
        seed = (
            f"{HANDSHAKE_MODEL_VERSION}|{source}|{destination}|"
            f"{simulation_time_seconds:.9f}|{label}"
        ).encode("utf-8")
        return hashlib.shake_256(seed).digest(length)

    def _transcript_fields(
        self, source: str, destination: str, materials: dict[str, bytes]
    ) -> dict[str, Any]:
        """Monta os campos autenticados do transcript do handshake."""
        algorithms = {
            "key_agreement": (
                ["X25519", self.kem] if self.mode == "hybrid"
                else ["X25519"] if self.mode == "classical" else [self.kem]
            ),
            "authentication": (
                ["Ed25519", self.pqc_signature] if self.mode == "hybrid"
                else ["Ed25519"] if self.mode == "classical" else [self.pqc_signature]
            ),
            "kdf": "HKDF-SHA-256",
            "record_protection": "AES-256-GCM",
        }
        return {
            "model_version": HANDSHAKE_MODEL_VERSION,
            "client_id": source,
            "server_id": destination,
            "mode": self.mode,
            "algorithms": algorithms,
            "x25519_client_public_b64": (
                base64.b64encode(materials["x25519_client_public"]).decode("ascii")
                if "x25519_client_public" in materials else None
            ),
            "x25519_server_public_b64": (
                base64.b64encode(materials["x25519_server_public"]).decode("ascii")
                if "x25519_server_public" in materials else None
            ),
            "ml_kem_ciphertext_b64": (
                base64.b64encode(materials["ml_kem_ciphertext"]).decode("ascii")
                if "ml_kem_ciphertext" in materials else None
            ),
            "provisioned_credential_ids": {
                "classical_identity": (
                    self.server_classical_credential_id
                    if self.mode in {"classical", "hybrid"} else None
                ),
                "pqc_identity": (
                    self.server_pqc_credential_id
                    if self.mode in {"pqc", "hybrid"} else None
                ),
                "server_kem": (
                    self.server_kem_credential_id
                    if self.mode in {"pqc", "hybrid"} else None
                ),
            },
            "session_context": self.session_context,
        }

    @staticmethod
    def _participant_operation(
        operation: CryptoOperation, phase: str, before_send: bool = True
    ) -> ParticipantOperation:
        """Registra uma operação criptográfica para um participante."""
        return ParticipantOperation(
            participant=operation.participant,
            operation=operation.operation,
            algorithm=operation.algorithm,
            phase=phase,
            before_send=before_send,
            included_in_primary_energy_budget=(operation.participant == "iot_client"),
        )

    def _build_handshake_plan(
        self, source: str, destination: str, transcript_fields: dict[str, Any],
        transcript_hash: bytes, operations: list[CryptoOperation],
    ) -> HandshakePlan:
        """Cria o plano de mensagens do handshake selecionado."""
        by_name: dict[str, list[CryptoOperation]] = {}
        for operation in operations:
            by_name.setdefault(operation.operation, []).append(operation)

        def selected(
            names: set[str], participant: str, *, before_send: bool = True
        ) -> list[ParticipantOperation]:
            """Informa se uma operação pertence ao conjunto selecionado.

            Parâmetros:
                names: Nomes das operações que devem ser incluídas.
                participant: Participante que executa as operações.
                before_send: Indica se a operação ocorre antes do envio.

            Retorna:
                Operações do participante convertidas para o plano do handshake.
            """
            return [
                self._participant_operation(
                    operation, "authenticated_handshake", before_send
                )
                for name in names for operation in by_name.get(name, [])
                if operation.participant == participant
            ]

        client_materials: list[dict[str, Any]] = []
        server_materials: list[dict[str, Any]] = []
        if self.mode in {"classical", "hybrid"}:
            client_materials.append({"name": "x25519_client_ephemeral_public", "bytes": 32, "algorithm": "X25519"})
            server_materials.extend([
                {"name": "x25519_server_ephemeral_public", "bytes": 32, "algorithm": "X25519"},
                {"name": "ed25519_transcript_signature", "bytes": 64, "algorithm": "Ed25519"},
            ])
        if self.mode in {"pqc", "hybrid"}:
            client_materials.append({"name": "ml_kem_512_ciphertext", "bytes": 768, "algorithm": self.kem})
            server_materials.append({"name": "ml_dsa_44_transcript_signature", "bytes": 2420, "algorithm": self.pqc_signature})
        provisioning_status = (
            "certificate_bundle_transmitted"
            if self.handshake_variant == "full_certificate"
            else "preprovisioned_not_transmitted"
        )
        provisioning = {
            "server_ed25519_identity_public_key": provisioning_status,
            "server_mldsa44_identity_public_key": provisioning_status,
            "server_mlkem512_public_key": provisioning_status,
            "server_mlkem512_key_generation": "provisioning_or_renewal_outside_measured_handshake",
        }
        reference_total: int | None = None
        reference_source: str | None = None
        protocol_overhead = 0
        if self.handshake_variant == "full_certificate":
            reference = HYSECURE_FULL_HANDSHAKE[self.mode]
            certificate_bytes = int(reference["certificate_bytes"])
            server_materials.append({
                "name": "server_certificate_and_identity_key_bundle",
                "bytes": certificate_bytes,
                "algorithm": "HySecure certificate traffic envelope",
            })
            reference_total = int(reference["total_traffic_bytes"])
            material_total = sum(item["bytes"] for item in client_materials + server_materials)
            protocol_overhead = reference_total - material_total
            if protocol_overhead < 0:
                raise ValueError(
                    f"HySecure traffic envelope is smaller than modeled material for {self.mode}"
                )
            reference_source = "HySecure_Electronics_2025_Table_4"
        flights = [
            HandshakeFlight(
                1, source, destination, "iot_to_server", "client_key_establishment",
                HandshakeMessage("client_key_establishment", client_materials,
                                 sum(item["bytes"] for item in client_materials)),
                selected({"x25519_keygen", "ml_kem_encaps"}, "iot_client"),
                0.0, provisioning,
                [item["algorithm"] for item in client_materials],
            ),
            HandshakeFlight(
                2, destination, source, "server_to_iot", "server_authenticated_response",
                HandshakeMessage("server_authenticated_response", server_materials,
                                 sum(item["bytes"] for item in server_materials),
                                 protocol_overhead_bytes=protocol_overhead),
                selected({"x25519_keygen", "x25519_exchange", "ml_kem_decaps",
                          "ed25519_sign", "ml_dsa_sign"}, "server"),
                1.0, provisioning,
                [item["algorithm"] for item in server_materials],
            ),
        ]
        return HandshakePlan(
            model_version=HANDSHAKE_MODEL_VERSION,
            mode=self.mode,
            authentication_model="analytical_authenticated_key_establishment_not_tls",
            credential_provisioning=provisioning,
            transcript_hash_hex=transcript_hash.hex(),
            transcript_fields=transcript_fields,
            flights=flights,
            protocol_overhead_bytes=protocol_overhead,
            post_response_operations=selected(
                {"x25519_exchange", "ed25519_verify", "ml_dsa_verify",
                 "hkdf_extract", "hkdf_expand"}, "iot_client",
                before_send=False,
            ),
            handshake_variant=self.handshake_variant,
            reference_traffic_total_bytes=reference_total,
            reference_source=reference_source,
        )

    def _operation(
        self,
        name: str,
        participant: str,
        algorithm: str,
        input_bytes: int,
        output_bytes: int,
        *,
        host_id: str,
        callback: Callable[[], Any] | None = None,
    ) -> CryptoOperation:
        """Executa ou estima uma operação criptográfica e registra seu custo."""
        metadata: dict[str, Any] = {
            "host_id": host_id,
            **{key: value for key, value in self.target_metadata.items() if value is not None},
        }
        if self.timing_mode == "host_wallclock":
            if callback is None:
                raise RuntimeError(f"host_wallclock operation {name} has no implementation")
            started = time.perf_counter()
            callback()
            duration = time.perf_counter() - started
            return CryptoOperation(
                operation=name,
                participant=participant,
                algorithm=algorithm,
                duration_seconds=duration,
                input_bytes=input_bytes,
                output_bytes=output_bytes,
                energy_j=None,
                timing_source="host_wallclock",
                host_wallclock_seconds=duration,
                metadata={**metadata, "calibration_status": "not_target_timing"},
                parameter_source="host_perf_counter",
                parameter_status="host_only",
                included_in_primary_energy_budget=(participant == "iot_client"),
                primitive_execution="real_host_primitive",
                target_timing_seconds=None,
                wire_size_model="algorithm_or_protocol_size_contract",
            )

        # The campaign calibrations describe the ESP32 IoT client.  Reusing
        # those numbers for the server would silently model a second ESP32 and
        # would give server operations false provenance.  Server/gateway target
        # timings therefore remain excluded until a participant-specific
        # profile is supplied.
        calibration = (
            self.target_operations.get(name)
            if participant == "iot_client"
            else None
        )
        if isinstance(calibration, CalibrationRecord):
            duration = (
                calibration.fixed_cost_seconds
                + input_bytes / calibration.throughput_bytes_per_second
                if calibration.throughput_bytes_per_second is not None
                else calibration.duration_seconds
            )
            metadata.update({
                "device": calibration.device,
                "voltage_v": calibration.voltage_v,
                "current_ma": calibration.current_ma,
                "energy_model": calibration.energy_model,
                "calibration_status": "available",
                "estimation_status": calibration.estimation_status,
                "throughput_bytes_per_second": calibration.throughput_bytes_per_second,
                "fixed_cost_seconds": calibration.fixed_cost_seconds,
                **calibration.metadata,
            })
            if calibration.energy_model == "direct_event" and calibration.throughput_bytes_per_second is None:
                metadata["calibrated_load_energy_j"] = calibration.energy_j
            source = calibration.source
        elif isinstance(calibration, dict):
            duration = float(calibration.get("duration_seconds", 0.0))
            source = str(calibration.get("source", "user_configured"))
            metadata.update({key: calibration[key] for key in ("device", "voltage_v", "current_ma", "energy_j", "firmware", "compiler", "implementation") if key in calibration})
            metadata["calibration_status"] = "available" if "duration_seconds" in calibration else "required"
        else:
            duration = 0.0
            source = "target_profile_missing"
            metadata["calibration_status"] = (
                "required" if participant == "iot_client" else "excluded_unknown_server_timing"
            )
        if duration < 0:
            raise ValueError(f"negative target duration for {name}")
        if (
            self.strict_target_calibration
            and participant == "iot_client"
            and (metadata.get("calibration_status") != "available" or duration <= 0)
        ):
            raise RuntimeError(
                f"strict_target_calibration_missing:{self.mode}:{participant}:{name}"
            )
        current_ma = (
            float(metadata["current_ma"]) if metadata.get("current_ma") is not None else None
        )
        voltage_v = (
            float(metadata["voltage_v"]) if metadata.get("voltage_v") is not None else None
        )
        return CryptoOperation(
            operation=name,
            participant=participant,
            algorithm=algorithm,
            duration_seconds=duration,
            input_bytes=input_bytes,
            output_bytes=output_bytes,
            energy_j=None,
            timing_source=source,
            metadata=metadata,
            current_ma=current_ma,
            voltage_v=voltage_v,
            parameter_source=source,
            parameter_status=(
                "literature_proxy"
                if metadata.get("calibration_status") == "available"
                else "excluded"
            ),
            included_in_primary_energy_budget=(participant == "iot_client"),
            primitive_execution="analytical_size_only",
            target_timing_seconds=duration,
            wire_size_model="algorithm_or_protocol_size_contract",
        )

    def _calibration_assessment(self, operations: list[CryptoOperation]) -> tuple[str, str]:
        """Avalia se a calibração necessária está disponível."""
        source_ops = [operation for operation in operations if operation.participant == "iot_client"]
        if self.timing_mode == "host_wallclock":
            return "host_only", "provisional"
        if any(op.metadata.get("calibration_status") == "required" for op in source_ops):
            return "required", "provisional"
        if source_ops and all(op.timing_source == "hardware_measurement" for op in source_ops):
            return "calibrated", "measured"
        return "configured", "provisional"

    def _algorithm_sizes(self, algorithm: str) -> dict[str, int]:
        """Retorna os tamanhos publicados dos artefatos de um algoritmo."""
        try:
            return ALGORITHM_WIRE_SIZES[algorithm]
        except KeyError as exc:
            raise ValueError(
                f"wire sizes are not configured for algorithm {algorithm}"
            ) from exc

    def _validate_config(self) -> None:
        """Valida algoritmos, modo e parâmetros criptográficos."""
        if self.mode not in self.valid_modes:
            raise ValueError(f"invalid crypto mode {self.mode}; use {self.valid_modes}")
        if self.timing_mode not in {"host_wallclock", "target_profile", "analytical_size_only"}:
            raise ValueError(
                "timing_mode must be host_wallclock, target_profile or analytical_size_only"
            )
        if self.classical_signature != "ed25519":
            raise ValueError("only ed25519 classical signatures are supported")
        if self.handshake_variant not in {"preprovisioned", "full_certificate"}:
            raise ValueError(
                "handshake_variant must be preprovisioned or full_certificate"
            )
        if self.session_lifetime_seconds <= 0:
            raise ValueError("session_lifetime_seconds must be greater than zero")
        if self.session_max_messages <= 0:
            raise ValueError("session_max_messages must be greater than zero")
        if self.kem not in ALGORITHM_WIRE_SIZES:
            raise ValueError(f"unknown KEM size profile: {self.kem}")
        if self.pqc_signature not in ALGORITHM_WIRE_SIZES:
            raise ValueError(f"unknown PQC signature size profile: {self.pqc_signature}")
        self.backend = self._backend_from_mode(self.mode)

    def _validate_liboqs(self, oqs: Any) -> None:
        """Confirma que os algoritmos exigidos existem na liboqs."""
        if self.kem not in oqs.get_enabled_kem_mechanisms():
            raise ValueError(f"KEM is unavailable in liboqs: {self.kem}")
        if self.use_pqc_signature and self.pqc_signature not in oqs.get_enabled_sig_mechanisms():
            raise ValueError(f"signature is unavailable in liboqs: {self.pqc_signature}")

    @staticmethod
    def _import_oqs() -> Any:
        """Importa os bindings da liboqs e relata uma falha compreensível."""
        try:
            return importlib.import_module("oqs")
        except ImportError as exc:
            raise RuntimeError(
                "liboqs-python is required for host_wallclock PQC execution; "
                "use target_profile for calibrated target timing"
            ) from exc

    @staticmethod
    def _serialize_payload(payload: Any) -> bytes:
        """Converte o conteúdo da aplicação em bytes."""
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")

    def _session_algorithm(self) -> str:
        """Descreve os algoritmos usados pela sessão atual."""
        if self.mode == "classical":
            return "X25519 + Ed25519"
        if self.mode == "pqc":
            return f"{self.kem} + {self.pqc_signature}"
        return f"X25519 + {self.kem} + Ed25519 + {self.pqc_signature}"

    @staticmethod
    def _backend_from_mode(mode: str) -> str:
        """Seleciona o backend criptográfico correspondente ao modo."""
        return {
            "classical": "cryptography",
            "pqc": "liboqs",
            "hybrid": "cryptography + liboqs",
        }.get(mode, "unknown")

    def get_config(self) -> dict[str, Any]:
        """Retorna a configuração criptográfica efetivamente utilizada.

        Retorna:
            Dicionário com os dados produzidos.
        """
        return {
            "mode": self.mode,
            "backend": self.backend,
            "kem": self.kem,
            "pqc_signature": self.pqc_signature,
            "classical_signature": self.classical_signature,
            "use_classical_signature": self.use_classical_signature,
            "use_pqc_signature": self.use_pqc_signature,
            "timing_mode": self.timing_mode,
            "session_lifetime_seconds": self.session_lifetime_seconds,
            "session_max_messages": self.session_max_messages,
            "target_metadata": self.target_metadata,
            "calibration_status": (
                "required"
                if self.timing_mode in {"target_profile", "analytical_size_only"}
                and not self.target_operations else "configured"
            ),
        }
