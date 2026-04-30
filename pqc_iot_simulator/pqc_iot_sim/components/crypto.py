from dataclasses import dataclass, field, asdict
from typing import Any
import base64
import hashlib
import json
import os
import time

from .logger import Logger


@dataclass
class CryptoResult:
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

    def to_dict(self):
        return asdict(self)


class CryptoManager:
    """
    Gerenciador criptografico.

    Modos suportados:

    classical:
        Usa X25519, Ed25519 e AES GCM pela biblioteca cryptography.

    pqc:
        Usa ML KEM, assinatura PQC e AES GCM usando liboqs e cryptography.

    hybrid:
        Usa X25519, Ed25519, ML KEM, assinatura PQC e AES GCM.
    """

    def __init__(
        self,
        mode: str = "classical",
        kem: str = "ML-KEM-512",
        pqc_signature: str = "ML-DSA-44",
        classical_signature: str = "ed25519",
        use_classical_signature: bool = True,
        use_pqc_signature: bool = True,
        logger: Logger | None = None,
        backend: str | None = None
    ):
        self.mode = mode
        self.kem = kem
        self.pqc_signature = pqc_signature
        self.classical_signature = classical_signature
        self.use_classical_signature = use_classical_signature
        self.use_pqc_signature = use_pqc_signature
        self.logger = logger or Logger(name="CryptoManager")

        self.valid_modes = [
            "classical",
            "pqc",
            "hybrid"
        ]

        self.backend = self._backend_from_mode(mode)

        self._validate_config()

        self.logger.log(
            "CryptoManager criado",
            data=self.get_config(),
            component="CryptoManager"
        )

    def configure(
        self,
        mode: str | None = None,
        kem: str | None = None,
        signature: str | None = None,
        pqc_signature: str | None = None,
        classical_signature: str | None = None,
        use_classical_signature: bool | None = None,
        use_pqc_signature: bool | None = None,
        backend: str | None = None
    ):
        if mode is not None:
            self.mode = mode

        if kem is not None:
            self.kem = kem

        if signature is not None and pqc_signature is None:
            self.pqc_signature = signature

            self.logger.log(
                "Parametro 'signature' esta obsoleto; use 'pqc_signature'.",
                level="WARNING",
                component="CryptoManager"
            )

        if pqc_signature is not None:
            self.pqc_signature = pqc_signature

        if classical_signature is not None:
            self.classical_signature = classical_signature

        if use_classical_signature is not None:
            self.use_classical_signature = use_classical_signature

        if use_pqc_signature is not None:
            self.use_pqc_signature = use_pqc_signature

        self.backend = self._backend_from_mode(self.mode)

        self._validate_config()

        self.logger.log(
            "CryptoManager configurado",
            data=self.get_config(),
            component="CryptoManager"
        )

        return self

    def protect(self, payload: dict[str, Any]):
        if self.mode == "classical":
            return self._protect_classical_real(payload)

        if self.mode == "pqc":
            return self._protect_pqc_real(payload)

        if self.mode == "hybrid":
            return self._protect_hybrid_real(payload)

        raise ValueError(f"Modo criptográfico nao suportado: {self.mode}")

    def _protect_classical_real(self, payload: dict[str, Any]):
        start = time.perf_counter()

        message = self._serialize_payload(payload)

        key_exchange = self._run_x25519_key_exchange()

        signature_data = {}

        if self.use_classical_signature:
            signature_data = self._run_ed25519_signature(message)

        encryption_data = self._encrypt_payload_with_aes_gcm(
            shared_secret=key_exchange["shared_secret"],
            payload=payload
        )

        operation_time = time.perf_counter() - start

        original_size = len(message)

        overhead = (
            key_exchange["sender_public_key_size"]
            + key_exchange["receiver_public_key_size"]
            + signature_data.get("public_key_size", 0)
            + signature_data.get("signature_size", 0)
            + encryption_data["nonce_size"]
            + encryption_data["tag_size"]
        )

        protected_size = encryption_data["ciphertext_size"] + overhead

        metadata = {
            "classical_kex": {
                "algorithm": "X25519",
                "sender_public_key_size": key_exchange["sender_public_key_size"],
                "receiver_public_key_size": key_exchange["receiver_public_key_size"],
                "shared_secret_size": key_exchange["shared_secret_size"],
                "shared_secret_valid": key_exchange["shared_secret_valid"]
            },
            "classical_signature": signature_data,
            "encryption": encryption_data
        }

        protected_payload = self._build_protected_payload(
            mode="classical",
            backend="cryptography",
            payload=payload,
            metadata=metadata,
            original_size_bytes=original_size,
            protected_size_bytes=protected_size,
            overhead_bytes=overhead,
            encryption_data=encryption_data
        )

        result = CryptoResult(
            mode="classical",
            backend="cryptography",
            algorithm="X25519 + Ed25519 + AES GCM",
            payload=protected_payload,
            original_size_bytes=original_size,
            protected_size_bytes=protected_size,
            overhead_bytes=overhead,
            operation_time_seconds=round(operation_time, 6),
            energy_cost=self._estimate_energy_cost(
                operation_time_seconds=operation_time,
                protected_size_bytes=protected_size,
                overhead_bytes=overhead
            ),
            metadata=metadata
        )

        self.logger.log(
            "Payload protegido com criptografia classica",
            data={
                "algorithm": result.algorithm,
                "overhead_bytes": result.overhead_bytes,
                "operation_time_seconds": result.operation_time_seconds,
                "energy_cost": result.energy_cost
            },
            component="CryptoManager"
        )

        return result

    def _protect_pqc_real(self, payload: dict[str, Any]):
        start = time.perf_counter()

        oqs = self._import_oqs()
        self._validate_liboqs_kem(oqs)

        if self.use_pqc_signature:
            self._validate_liboqs_signature(oqs)

        message = self._serialize_payload(payload)

        kem_data = self._run_pqc_kem(oqs)

        signature_data = {}

        if self.use_pqc_signature:
            signature_data = self._run_pqc_signature(oqs, message)

        encryption_data = self._encrypt_payload_with_aes_gcm(
            shared_secret=kem_data["shared_secret"],
            payload=payload
        )

        operation_time = time.perf_counter() - start

        original_size = len(message)

        overhead = (
            kem_data["public_key_size"]
            + kem_data["ciphertext_size"]
            + signature_data.get("public_key_size", 0)
            + signature_data.get("signature_size", 0)
            + encryption_data["nonce_size"]
            + encryption_data["tag_size"]
        )

        protected_size = encryption_data["ciphertext_size"] + overhead

        metadata = {
            "pqc_kem": {
                "algorithm": self.kem,
                "public_key_size": kem_data["public_key_size"],
                "ciphertext_size": kem_data["ciphertext_size"],
                "shared_secret_size": kem_data["shared_secret_size"],
                "shared_secret_valid": kem_data["shared_secret_valid"]
            },
            "pqc_signature": signature_data,
            "encryption": encryption_data
        }

        protected_payload = self._build_protected_payload(
            mode="pqc",
            backend="liboqs",
            payload=payload,
            metadata=metadata,
            original_size_bytes=original_size,
            protected_size_bytes=protected_size,
            overhead_bytes=overhead,
            encryption_data=encryption_data
        )

        result = CryptoResult(
            mode="pqc",
            backend="liboqs",
            algorithm=f"{self.kem} + {self.pqc_signature} + AES GCM",
            payload=protected_payload,
            original_size_bytes=original_size,
            protected_size_bytes=protected_size,
            overhead_bytes=overhead,
            operation_time_seconds=round(operation_time, 6),
            energy_cost=self._estimate_energy_cost(
                operation_time_seconds=operation_time,
                protected_size_bytes=protected_size,
                overhead_bytes=overhead
            ),
            metadata=metadata
        )

        self.logger.log(
            "Payload protegido com criptografia pos quântica",
            data={
                "kem": self.kem,
                "signature": self.pqc_signature if self.use_pqc_signature else None,
                "overhead_bytes": result.overhead_bytes,
                "operation_time_seconds": result.operation_time_seconds,
                "energy_cost": result.energy_cost
            },
            component="CryptoManager"
        )

        return result

    def _protect_hybrid_real(self, payload: dict[str, Any]):
        start = time.perf_counter()

        oqs = self._import_oqs()
        self._validate_liboqs_kem(oqs)

        if self.use_pqc_signature:
            self._validate_liboqs_signature(oqs)

        message = self._serialize_payload(payload)

        classical_kex = self._run_x25519_key_exchange()
        pqc_kem = self._run_pqc_kem(oqs)

        combined_secret = self._combine_shared_secrets(
            classical_secret=classical_kex["shared_secret"],
            pqc_secret=pqc_kem["shared_secret"]
        )

        classical_signature_data = {}

        if self.use_classical_signature:
            classical_signature_data = self._run_ed25519_signature(message)

        pqc_signature_data = {}

        if self.use_pqc_signature:
            pqc_signature_data = self._run_pqc_signature(oqs, message)

        encryption_data = self._encrypt_payload_with_aes_gcm(
            shared_secret=combined_secret,
            payload=payload
        )

        operation_time = time.perf_counter() - start

        original_size = len(message)

        overhead = (
            classical_kex["sender_public_key_size"]
            + classical_kex["receiver_public_key_size"]
            + pqc_kem["public_key_size"]
            + pqc_kem["ciphertext_size"]
            + classical_signature_data.get("public_key_size", 0)
            + classical_signature_data.get("signature_size", 0)
            + pqc_signature_data.get("public_key_size", 0)
            + pqc_signature_data.get("signature_size", 0)
            + encryption_data["nonce_size"]
            + encryption_data["tag_size"]
        )

        protected_size = encryption_data["ciphertext_size"] + overhead

        metadata = {
            "classical_kex": {
                "algorithm": "X25519",
                "sender_public_key_size": classical_kex["sender_public_key_size"],
                "receiver_public_key_size": classical_kex["receiver_public_key_size"],
                "shared_secret_size": classical_kex["shared_secret_size"],
                "shared_secret_valid": classical_kex["shared_secret_valid"]
            },
            "pqc_kem": {
                "algorithm": self.kem,
                "public_key_size": pqc_kem["public_key_size"],
                "ciphertext_size": pqc_kem["ciphertext_size"],
                "shared_secret_size": pqc_kem["shared_secret_size"],
                "shared_secret_valid": pqc_kem["shared_secret_valid"]
            },
            "classical_signature": classical_signature_data,
            "pqc_signature": pqc_signature_data,
            "hybrid_secret": {
                "combination": "SHA256 de segredo classico concatenado com segredo PQC",
                "combined_secret_size": len(combined_secret)
            },
            "encryption": encryption_data
        }

        protected_payload = self._build_protected_payload(
            mode="hybrid",
            backend="cryptography + liboqs",
            payload=payload,
            metadata=metadata,
            original_size_bytes=original_size,
            protected_size_bytes=protected_size,
            overhead_bytes=overhead,
            encryption_data=encryption_data
        )

        result = CryptoResult(
            mode="hybrid",
            backend="cryptography + liboqs",
            algorithm=f"X25519 + Ed25519 + {self.kem} + {self.pqc_signature} + AES GCM",
            payload=protected_payload,
            original_size_bytes=original_size,
            protected_size_bytes=protected_size,
            overhead_bytes=overhead,
            operation_time_seconds=round(operation_time, 6),
            energy_cost=self._estimate_energy_cost(
                operation_time_seconds=operation_time,
                protected_size_bytes=protected_size,
                overhead_bytes=overhead
            ),
            metadata=metadata
        )

        self.logger.log(
            "Payload protegido com criptográfia hibrida",
            data={
                "algorithm": result.algorithm,
                "overhead_bytes": result.overhead_bytes,
                "operation_time_seconds": result.operation_time_seconds,
                "energy_cost": result.energy_cost
            },
            component="CryptoManager"
        )

        return result

    def _run_x25519_key_exchange(self):
        self._import_cryptography()

        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import x25519

        sender_private_key = x25519.X25519PrivateKey.generate()
        receiver_private_key = x25519.X25519PrivateKey.generate()

        sender_public_key = sender_private_key.public_key()
        receiver_public_key = receiver_private_key.public_key()

        sender_public_bytes = sender_public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )

        receiver_public_bytes = receiver_public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )

        sender_secret = sender_private_key.exchange(receiver_public_key)
        receiver_secret = receiver_private_key.exchange(sender_public_key)

        if sender_secret != receiver_secret:
            raise RuntimeError("Falha no X25519: segredos compartilhados diferentes.")

        return {
            "shared_secret": sender_secret,
            "sender_public_key_size": len(sender_public_bytes),
            "receiver_public_key_size": len(receiver_public_bytes),
            "shared_secret_size": len(sender_secret),
            "shared_secret_valid": True
        }

    def _run_ed25519_signature(self, message: bytes):
        self._import_cryptography()

        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519

        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        public_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )

        signature = private_key.sign(message)

        try:
            public_key.verify(signature, message)
            is_valid = True

        except InvalidSignature as exc:
            raise RuntimeError("Falha na assinatura Ed25519: verificacao invalida.") from exc

        return {
            "algorithm": "Ed25519",
            "public_key_size": len(public_bytes),
            "signature_size": len(signature),
            "signature_valid": is_valid
        }

    def _run_pqc_kem(self, oqs):
        kem_client = oqs.KeyEncapsulation(self.kem)
        kem_server = oqs.KeyEncapsulation(self.kem)

        public_key = kem_server.generate_keypair()
        ciphertext, shared_secret_client = kem_client.encap_secret(public_key)
        shared_secret_server = kem_server.decap_secret(ciphertext)

        if shared_secret_client != shared_secret_server:
            raise RuntimeError("Falha no KEM PQC: segredos compartilhados diferentes.")

        return {
            "shared_secret": shared_secret_client,
            "public_key_size": len(public_key),
            "ciphertext_size": len(ciphertext),
            "shared_secret_size": len(shared_secret_client),
            "shared_secret_valid": True
        }

    def _run_pqc_signature(self, oqs, message: bytes):
        signer = oqs.Signature(self.pqc_signature)

        public_key = signer.generate_keypair()
        signature = signer.sign(message)
        is_valid = signer.verify(message, signature, public_key)

        if not is_valid:
            raise RuntimeError("Falha na assinatura PQC: verificação invalida.")

        return {
            "algorithm": self.pqc_signature,
            "public_key_size": len(public_key),
            "signature_size": len(signature),
            "signature_valid": bool(is_valid)
        }

    def _encrypt_payload_with_aes_gcm(
        self,
        shared_secret: bytes,
        payload: dict[str, Any]
    ):
        self._import_cryptography()

        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF

        serialized_payload = self._serialize_payload(payload)

        salt = b"pqc_iot_simulator"
        info = b"payload_protection"

        key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=info
        ).derive(shared_secret)

        nonce = os.urandom(12)

        aesgcm = AESGCM(key)

        ciphertext = aesgcm.encrypt(
            nonce,
            serialized_payload,
            None
        )

        tag_size = 16

        return {
            "algorithm": "AES GCM",
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            "nonce_size": len(nonce),
            "ciphertext_size": len(ciphertext),
            "tag_size": tag_size,
            "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
            "nonce_sha256": hashlib.sha256(nonce).hexdigest()
        }

    def _combine_shared_secrets(
        self,
        classical_secret: bytes,
        pqc_secret: bytes
    ):
        return hashlib.sha256(
            classical_secret + pqc_secret
        ).digest()

    def _build_protected_payload(
        self,
        mode: str,
        backend: str,
        payload: dict[str, Any],
        metadata: dict[str, Any],
        original_size_bytes: int,
        protected_size_bytes: int,
        overhead_bytes: int,
        encryption_data: dict[str, Any]
    ):
        return {
            "crypto_mode": mode,
            "crypto_backend": backend,
            "encrypted": True,
            "ciphertext": encryption_data.get("ciphertext"),
            "nonce": encryption_data.get("nonce"),
            "tag_size": encryption_data.get("tag_size"),
            "payload_original_sha256": hashlib.sha256(
                self._serialize_payload(payload)
            ).hexdigest(),
            "original_size_bytes": original_size_bytes,
            "protected_size_bytes": protected_size_bytes,
            "overhead_bytes": overhead_bytes,
            "crypto_metadata": metadata
        }

    def _estimate_energy_cost(
        self,
        operation_time_seconds: float,
        protected_size_bytes: int,
        overhead_bytes: int
    ):
        time_cost = operation_time_seconds
        size_cost = protected_size_bytes * 0.00001
        overhead_cost = overhead_bytes * 0.000005

        return round(time_cost + size_cost + overhead_cost, 6)

    def _serialize_payload(self, payload: Any):
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            default=str
        ).encode("utf-8")

    def _import_cryptography(self):
        try:
            import cryptography

            return cryptography

        except ImportError as exc:
            raise RuntimeError(
                "A biblioteca cryptography nao foi encontrada. Instale com: pip install cryptography"
            ) from exc

    def _import_oqs(self):
        try:
            import contextlib
            import importlib
            import io
            import sys

            if "oqs" in sys.modules:
                return sys.modules["oqs"]

            buffer_stdout = io.StringIO()
            buffer_stderr = io.StringIO()

            with contextlib.redirect_stdout(buffer_stdout), contextlib.redirect_stderr(buffer_stderr):
                oqs = importlib.import_module("oqs")

            return oqs

        except ImportError as exc:
            raise RuntimeError(
                "O pacote oqs nao foi encontrado. Instale liboqs e liboqs python."
            ) from exc

    def _validate_config(self):
        if self.mode not in self.valid_modes:
            raise ValueError(
                f"Modo criptografico invalido: {self.mode}. "
                f"Use um destes: {self.valid_modes}"
            )

        self.backend = self._backend_from_mode(self.mode)

        if self.classical_signature != "ed25519":
            raise ValueError(
                "Assinatura classica nao suportada ainda. Use classical_signature='ed25519'."
            )

    def _validate_liboqs_kem(self, oqs):
        enabled_kems = oqs.get_enabled_kem_mechanisms()

        if self.kem not in enabled_kems:
            raise ValueError(
                f"KEM nao disponivel na liboqs: {self.kem}. "
                "Use oqs.get_enabled_kem_mechanisms() para verificar os nomes disponiveis."
            )

    def _validate_liboqs_signature(self, oqs):
        enabled_signatures = oqs.get_enabled_sig_mechanisms()

        if self.pqc_signature not in enabled_signatures:
            raise ValueError(
                f"Assinatura nao disponivel na liboqs: {self.pqc_signature}. "
                "Use oqs.get_enabled_sig_mechanisms() para verificar os nomes disponiveis."
            )

    def _backend_from_mode(self, mode: str):
        if mode == "classical":
            return "cryptography"

        if mode == "pqc":
            return "liboqs"

        if mode == "hybrid":
            return "cryptography + liboqs"

        return "unknown"

    def get_config(self):
        return {
            "mode": self.mode,
            "backend": self.backend,
            "kem": self.kem,
            "pqc_signature": self.pqc_signature,
            "classical_signature": self.classical_signature,
            "use_classical_signature": self.use_classical_signature,
            "use_pqc_signature": self.use_pqc_signature
        }