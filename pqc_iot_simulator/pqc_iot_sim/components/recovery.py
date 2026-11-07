"""Experimental restart protocol. Not TLS and not a production security library.

Real ML-KEM/ML-DSA, transcript-bound key derivation, AES-GCM records and sealed
atomic checkpoints. Logical time is injected to make expiry faults reproducible.
The gateway remains authoritative; client snapshots are explicitly untrusted age.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import struct
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

VERSION = "pqc-recovery-v1"
KEM = "ML-KEM-512"
SIGNATURE = "ML-DSA-44"
MODES = ("full_pqc", "psk_resume", "pqc_resume")
POLICIES = ("checkpoint", "persist_each", "reserve_blocks", *MODES)
FRAME = struct.Struct("!I")


class Rejected(ValueError):
    """Authentication, freshness or policy validation failed."""


def encode(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def unb64(value: str) -> bytes:
    return base64.b64decode(value, validate=True)


def derive(material: bytes, transcript: bytes, label: str) -> bytes:
    return HKDF(
        algorithm=SHA256(),
        length=32,
        salt=hashlib.sha256(transcript).digest(),
        info=(VERSION + "/" + label).encode(),
    ).derive(material)


def mac(key: bytes, label: str, value: Any) -> str:
    return hmac.new(
        key, label.encode() + b"\x00" + encode(value), hashlib.sha256
    ).hexdigest()


def require_mac(key: bytes, label: str, value: Any, received: str) -> None:
    if not hmac.compare_digest(mac(key, label, value), received):
        raise Rejected("invalid MAC: " + label)


def oqs_module():
    import oqs  # Never substitute modeled bytes/random secrets for real PQC.

    return oqs


@dataclass
class Identity:
    public: bytes
    private: bytes = field(repr=False)

    @classmethod
    def generate(cls):
        with oqs_module().Signature(SIGNATURE) as signer:
            public = signer.generate_keypair()
            return cls(public, signer.export_secret_key())

    def sign(self, value: Any) -> str:
        with oqs_module().Signature(SIGNATURE, self.private) as signer:
            return b64(signer.sign(encode(value)))

    @staticmethod
    def verify(public: bytes, value: Any, signature: str) -> None:
        with oqs_module().Signature(SIGNATURE) as verifier:
            if not verifier.verify(encode(value), unb64(signature), public):
                raise Rejected("invalid ML-DSA signature")


@dataclass
class Root:
    secret: bytes = field(repr=False)
    root_id: str
    expires: float
    used: int = 0
    limit: int = 10000

    def valid(self, now: float):
        if now >= self.expires or self.used >= self.limit:
            raise Rejected("root expired or message budget exhausted")

    def dump(self):
        return {
            "secret": b64(self.secret),
            "root_id": self.root_id,
            "expires": self.expires,
            "used": self.used,
            "limit": self.limit,
        }

    @classmethod
    def load(cls, value):
        return cls(
            unb64(value["secret"]),
            value["root_id"],
            value["expires"],
            value["used"],
            value["limit"],
        )


@dataclass
class Session:
    key: bytes = field(repr=False)
    epoch: str
    prefix: bytes
    expires: float
    counter: int = 0
    device: str = "iot_1"
    server: str = "server_1"

    def dump(self):
        return {
            "key": b64(self.key),
            "epoch": self.epoch,
            "prefix": b64(self.prefix),
            "expires": self.expires,
            "counter": self.counter,
            "device": self.device,
            "server": self.server,
        }

    @classmethod
    def load(cls, value):
        return cls(
            unb64(value["key"]),
            value["epoch"],
            unb64(value["prefix"]),
            value["expires"],
            value["counter"],
            value["device"],
            value["server"],
        )


def traffic(material: bytes, transcript: dict, expires: float) -> Session:
    raw = encode(transcript)
    hello = transcript["hello"]
    return Session(
        derive(material, raw, "traffic"),
        hashlib.sha256(raw).hexdigest(),
        derive(material, raw, "nonce-prefix")[:8],
        expires,
        device=hello["device"],
        server=hello["server"],
    )


class ClientHandshake:
    def __init__(
        self,
        identity: Identity,
        server_public: bytes,
        mode: str,
        root: Root | None = None,
        device="iot_1",
        server="server_1",
    ):
        if mode not in MODES or (mode != "full_pqc" and root is None):
            raise ValueError("invalid handshake mode/root")
        self.identity, self.server_public, self.root = identity, server_public, root
        self.hello = {
            "version": VERSION,
            "device": device,
            "server": server,
            "mode": mode,
            "client_nonce": b64(os.urandom(32)),
            "root_id": root.root_id if mode != "full_pqc" else None,
        }
        if mode != "full_pqc":
            self.hello["binder"] = mac(root.secret, "client-hello", self.hello)

    def respond(self, reply: dict) -> dict:
        body = {k: v for k, v in reply.items() if k != "auth"}
        if body.get("hello") != self.hello:
            raise Rejected("server hello bound to a different request")
        mode = self.hello["mode"]
        if mode == "full_pqc":
            Identity.verify(self.server_public, body, reply["auth"])
        else:
            require_mac(self.root.secret, "server-hello", body, reply["auth"])
        ciphertext, shared = None, b""
        if mode != "psk_resume":
            with oqs_module().KeyEncapsulation(KEM) as encapsulator:
                ct, shared = encapsulator.encap_secret(unb64(body["kem_public"]))
                ciphertext = b64(ct)
        elif body["kem_public"] is not None:
            raise Rejected("unexpected key share")
        self.transcript = {
            "hello": self.hello,
            "reply": reply,
            "ciphertext": ciphertext,
        }
        material = shared + (self.root.secret if mode != "full_pqc" else b"")
        self.session = traffic(material, self.transcript, body["expires"])
        if mode == "full_pqc":
            self.root = Root(
                derive(material, encode(self.transcript), "resumption-root"),
                self.session.epoch,
                body["expires"],
                limit=body["limit"],
            )
        final = {
            "challenge": body["server_nonce"],
            "ciphertext": ciphertext,
            "finished": mac(self.session.key, "client-finished", self.transcript),
        }
        if mode == "full_pqc":
            final["signature"] = self.identity.sign(self.transcript)
        return final

    def complete(self, acknowledgement: dict) -> Session:
        require_mac(
            self.session.key,
            "server-finished",
            self.transcript,
            acknowledgement["finished"],
        )
        return self.session


class Gateway:
    """Live authority. Losing this ledger requires full reauthentication.

    Experiments intentionally keep this authority outside client rollback scope.
    Pending KEM secret keys are discarded after one finish or a 30 s deadline.
    Python cannot promise physical zeroization of copies in interpreter memory.
    """

    def __init__(
        self,
        identity: Identity,
        client_public: bytes,
        lifetime=3600.0,
        message_limit=10000,
    ):
        self.identity, self.client_public = identity, client_public
        self.lifetime, self.message_limit = lifetime, message_limit
        self.roots: dict[str, Root] = {}
        self.sessions: dict[str, Session] = {}
        self.highwater: dict[str, int] = {}
        self.pending: dict[str, dict] = {}

    def begin(self, hello: dict, now: float) -> dict:
        if (
            hello.get("version") != VERSION
            or hello.get("device") != "iot_1"
            or hello.get("server") != "server_1"
            or hello.get("mode") not in MODES
            or len(unb64(hello.get("client_nonce", ""))) != 32
        ):
            raise Rejected("invalid context")
        self.pending = {k: v for k, v in self.pending.items() if now < v["deadline"]}
        if len(self.pending) >= 32:
            raise Rejected("too many pending handshakes")
        mode, root = hello["mode"], None
        if mode != "full_pqc":
            root = self.roots.get(hello["root_id"])
            if root is None:
                raise Rejected("unknown root; full reauthentication required")
            root.valid(now)
            require_mac(
                root.secret,
                "client-hello",
                {k: v for k, v in hello.items() if k != "binder"},
                hello["binder"],
            )
        public, private = None, None
        if mode != "psk_resume":
            with oqs_module().KeyEncapsulation(KEM) as kem:
                public = b64(kem.generate_keypair())
                private = kem.export_secret_key()
        reply = {
            "hello": hello,
            "server_nonce": b64(os.urandom(32)),
            "kem_public": public,
            "expires": root.expires if root else now + self.lifetime,
            "limit": root.limit if root else self.message_limit,
        }
        reply["auth"] = (
            self.identity.sign(reply)
            if root is None
            else mac(root.secret, "server-hello", reply)
        )
        self.pending[reply["server_nonce"]] = {
            "reply": reply,
            "private": private,
            "deadline": now + 30,
            "root": root,
        }
        return reply

    def finish(self, final: dict, now: float) -> dict:
        pending = self.pending.pop(final["challenge"], None)
        if pending is None or now >= pending["deadline"]:
            raise Rejected("unknown, replayed or expired challenge")
        reply, root = pending["reply"], pending["root"]
        if root is not None:
            root.valid(now)
            if self.roots.get(root.root_id) is not root:
                raise Rejected("root was replaced")
        elif now >= reply["expires"]:
            raise Rejected("full handshake expired")
        mode = reply["hello"]["mode"]
        transcript = {
            "hello": reply["hello"],
            "reply": reply,
            "ciphertext": final["ciphertext"],
        }
        shared = b""
        if mode == "full_pqc":
            Identity.verify(self.client_public, transcript, final["signature"])
        if mode != "psk_resume":
            with oqs_module().KeyEncapsulation(KEM, pending["private"]) as kem:
                shared = kem.decap_secret(unb64(final["ciphertext"]))
        elif final["ciphertext"] is not None:
            raise Rejected("unexpected ciphertext")
        material = shared + (root.secret if root else b"")
        session = traffic(material, transcript, reply["expires"])
        require_mac(session.key, "client-finished", transcript, final["finished"])
        if root is None:
            root = Root(
                derive(material, encode(transcript), "resumption-root"),
                session.epoch,
                reply["expires"],
                limit=reply["limit"],
            )
            self.roots = {
                root.root_id: root
            }  # One pinned IoT identity in this experiment.
        self.sessions = {session.epoch: session}
        self.highwater = {session.epoch: -1}
        self.active_root = root.root_id
        return {"finished": mac(session.key, "server-finished", transcript)}

    def accept(self, record: dict, now: float) -> bytes:
        header = record["header"]
        session = self.sessions.get(header["epoch"])
        if session is None:
            raise Rejected("unknown/stale epoch")
        root = self.roots[self.active_root]
        root.valid(now)
        if now >= session.expires:
            raise Rejected("session expired")
        expected = {
            "version": VERSION,
            "device": session.device,
            "server": session.server,
            "epoch": session.epoch,
            "counter": header["counter"],
        }
        if header != expected or type(header["counter"]) is not int:
            raise Rejected("invalid record context")
        counter = header["counter"]
        if not 0 <= counter < 2**32 or counter <= self.highwater[session.epoch]:
            raise Rejected("replayed/out-of-order nonce")
        nonce = session.prefix + counter.to_bytes(4, "big")
        try:
            plaintext = AESGCM(session.key).decrypt(
                nonce, unb64(record["ciphertext"]), encode(header)
            )
        except Exception as error:
            raise Rejected("invalid AES-GCM record") from error
        self.highwater[session.epoch] = counter
        root.used += 1
        return plaintext


def handshake(gateway: Gateway, client: ClientHandshake, now=0.0):
    """In-process transport for fault tests; measure actual four encoded flights."""
    started = time.perf_counter_ns()
    reply = gateway.begin(client.hello, now)
    final = client.respond(reply)
    ack = gateway.finish(final, now)
    session = client.complete(ack)
    wire_bytes = sum(
        FRAME.size + len(encode(x)) for x in (client.hello, reply, final, ack)
    )
    return session, {
        "application_framed_bytes": wire_bytes,
        "host_handshake_ms": (time.perf_counter_ns() - started) / 1e6,
        "transcript": client.transcript,
    }


class SealedStore:
    """Atomic authenticated file. It detects tampering, NOT old valid snapshots.

    Wrapping key belongs to trusted provisioning, outside snapshot scope. fsync
    timings describe this host filesystem only, not ESP flash or energy.
    """

    def __init__(self, directory: Path, wrapping_key: bytes):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.directory, 0o700)
        self.key = wrapping_key
        self.writes, self.bytes_written, self.host_write_ms = 0, 0, 0.0

    def write(self, name: str, value: dict):
        if name not in ("state", "journal"):
            raise ValueError("unknown checkpoint")
        started = time.perf_counter_ns()
        nonce = os.urandom(12)
        raw = nonce + AESGCM(self.key).encrypt(
            nonce, encode(value), (VERSION + name).encode()
        )
        fd, temporary = tempfile.mkstemp(dir=self.directory, prefix=".pending-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.directory / name)
            dfd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        finally:
            Path(temporary).unlink(missing_ok=True)
        self.writes += 1
        self.bytes_written += len(raw)
        self.host_write_ms += (time.perf_counter_ns() - started) / 1e6

    def read(self, name: str) -> dict:
        raw = (self.directory / name).read_bytes()
        try:
            return json.loads(
                AESGCM(self.key).decrypt(raw[:12], raw[12:], (VERSION + name).encode())
            )
        except Exception as error:
            raise Rejected("corrupt or unauthenticated checkpoint") from error


class Sender:
    """Counter-policy sender. Reserve-before-use journal is independent of RAM.

    Restart from reserve_blocks skips the remainder of the reserved range.
    Restoring state AND journal can still roll the counter backwards.
    """

    def __init__(
        self,
        session: Session,
        root: Root,
        store: SealedStore,
        policy: str,
        block_size=32,
        restoring=False,
    ):
        if policy not in POLICIES or not 1 <= block_size <= 2**32:
            raise ValueError("invalid policy/block size")
        self.session, self.root, self.store = session, root, store
        self.policy, self.block_size = policy, block_size
        self.ceiling = session.counter
        if policy in ("persist_each", "reserve_blocks"):
            if restoring:
                journal = store.read("journal")
                if journal["epoch"] != session.epoch:
                    raise Rejected("journal belongs to another epoch")
                if (
                    type(journal["next"]) is not int
                    or not 0 <= journal["next"] <= 2**32
                ):
                    raise Rejected("invalid counter journal")
                session.counter = max(session.counter, journal["next"])
                self.ceiling = session.counter
            else:
                store.write(
                    "journal", {"epoch": session.epoch, "next": session.counter}
                )

    def checkpoint(self):
        state = {"root": self.root.dump()}
        if self.policy not in MODES:
            state["session"] = self.session.dump()
        # Fresh-key recovery needs only its resumption credential. Persisting
        # old traffic keys would defeat erasure-based secrecy of past sessions.
        self.store.write("state", state)

    @classmethod
    def restore(cls, store, policy, block_size=32):
        state = store.read("state")
        return cls(
            Session.load(state["session"]),
            Root.load(state["root"]),
            store,
            policy,
            block_size,
            restoring=True,
        )

    def reserve(self):
        if self.session.counter >= 2**32:
            raise Rejected("nonce counter exhausted")
        if (
            self.policy in ("persist_each", "reserve_blocks")
            and self.session.counter >= self.ceiling
        ):
            step = 1 if self.policy == "persist_each" else self.block_size
            ceiling = min(2**32, self.session.counter + step)
            self.store.write("journal", {"epoch": self.session.epoch, "next": ceiling})
            self.ceiling = ceiling

    def encrypt(self, plaintext: bytes, now=0.0) -> dict:
        if now >= self.session.expires:
            raise Rejected("session expired")
        self.root.valid(now)
        self.reserve()  # Durable reservation must finish BEFORE any encryption.
        counter = self.session.counter
        header = {
            "version": VERSION,
            "device": self.session.device,
            "server": self.session.server,
            "epoch": self.session.epoch,
            "counter": counter,
        }
        nonce = self.session.prefix + counter.to_bytes(4, "big")
        ciphertext = AESGCM(self.session.key).encrypt(nonce, plaintext, encode(header))
        self.session.counter += 1
        self.root.used += 1
        return {"header": header, "ciphertext": b64(ciphertext)}


class Observer:
    """Privileged test oracle; keys/plaintexts never go to exported result files."""

    def __init__(self):
        self.seen = {}
        self.reused = 0
        self.known_plaintext_recoveries = 0

    def observe(self, session: Session, record: dict, plaintext: bytes):
        nonce = session.prefix + record["header"]["counter"].to_bytes(4, "big")
        identity = (session.key, nonce)
        ciphertext = unb64(record["ciphertext"])[:-16]
        previous = self.seen.get(identity)
        # Called once per actual encrypt() invocation, never on TCP retries.
        # Identical plaintext/ciphertext does not excuse a second encryption
        # under the same key/nonce. A wire retransmission is a separate event.
        if previous is not None:
            self.reused += 1
            old_ciphertext, known_plaintext = previous
            recovered = bytes(
                a ^ b ^ c
                for a, b, c in zip(old_ciphertext, ciphertext, known_plaintext)
            )
            if (
                previous[1] != plaintext
                and len(recovered) == len(plaintext)
                and recovered == plaintext
            ):
                self.known_plaintext_recoveries += 1
        self.seen[identity] = (ciphertext, plaintext)


def send_frame(connection, value: dict):
    raw = encode(value)
    connection.sendall(FRAME.pack(len(raw)) + raw)


def receive_frame(connection) -> dict:
    def exact(size):
        result = bytearray()
        while len(result) < size:
            part = connection.recv(size - len(result))
            if not part:
                raise EOFError("incomplete frame")
            result.extend(part)
        return bytes(result)

    size = FRAME.unpack(exact(FRAME.size))[0]
    if not 1 <= size <= 65536:
        raise Rejected("invalid frame length")
    value = json.loads(exact(size))
    if not isinstance(value, dict):
        raise Rejected("frame must be an object")
    return value
