"""Executa um traço TCP ou UDP bidirecional nos namespaces do Mininet."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import socket
import struct
import sys
import time
from pathlib import Path
from typing import Any


LENGTH = struct.Struct("!Q")
COMPLETION = b"OK"


def _arguments() -> argparse.Namespace:
    """Lê e valida os argumentos recebidos pela sonda de transporte."""
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=("server", "client"))
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--plan-base64", required=True)
    parser.add_argument("--transfer-id", required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--transport", choices=("tcp", "udp"), default="tcp")
    parser.add_argument("--bind-host", default=None)
    parser.add_argument("--ready-file", default=None)
    return parser.parse_args()


def _decode_plan(encoded: str) -> list[dict[str, Any]]:
    """Decodifica o plano de mensagens recebido em Base64."""
    raw = base64.urlsafe_b64decode(encoded.encode("ascii"))
    plan = json.loads(raw.decode("utf-8"))
    if not isinstance(plan, list):
        raise ValueError("trace plan must be a list")
    for message in plan:
        if message.get("direction") not in {"iot_to_server", "server_to_iot"}:
            raise ValueError(f"invalid trace direction: {message.get('direction')}")
        if int(message.get("logical_payload_bytes", -1)) < 0:
            raise ValueError("logical_payload_bytes cannot be negative")
    return plan


def _payload(transfer_id: str, message: dict[str, Any]) -> bytes:
    """Gera um conteúdo determinístico com o tamanho solicitado."""
    size = int(message["logical_payload_bytes"])
    identity = "|".join(
        (
            transfer_id,
            str(message["sequence"]),
            str(message["direction"]),
            str(message["logical_type"]),
            str(size),
        )
    ).encode("utf-8")
    return hashlib.shake_256(identity).digest(size)


def _receive_exact(connection: socket.socket, size: int) -> bytes:
    """Recebe exatamente a quantidade de bytes solicitada."""
    output = bytearray()
    while len(output) < size:
        part = connection.recv(size - len(output))
        if not part:
            raise ConnectionError(
                f"connection closed after {len(output)}/{size} expected bytes"
            )
        output.extend(part)
    return bytes(output)


def _send_record(connection: socket.socket, payload: bytes) -> None:
    """Envia um registro com enquadramento de tamanho."""
    connection.sendall(LENGTH.pack(len(payload)))
    connection.sendall(payload)


def _receive_record(connection: socket.socket, expected: bytes) -> None:
    """Recebe um registro completo com enquadramento de tamanho."""
    declared = LENGTH.unpack(_receive_exact(connection, LENGTH.size))[0]
    if declared != len(expected):
        raise ValueError(f"record length mismatch: {declared} != {len(expected)}")
    received = _receive_exact(connection, declared)
    if not hashlib.sha256(received).digest() == hashlib.sha256(expected).digest():
        raise ValueError("record SHA-256 mismatch")


def _run_trace(
    connection: socket.socket,
    *,
    role: str,
    plan: list[dict[str, Any]],
    transfer_id: str,
) -> list[dict[str, Any]]:
    """Executa o traço bidirecional por uma conexão TCP."""
    records: list[dict[str, Any]] = []
    for message in plan:
        payload = _payload(transfer_id, message)
        sender = (
            role == "client" and message["direction"] == "iot_to_server"
        ) or (
            role == "server" and message["direction"] == "server_to_iot"
        )
        started_ns = time.perf_counter_ns()
        if sender:
            _send_record(connection, payload)
            action = "sent"
        else:
            _receive_record(connection, payload)
            action = "received_and_sha256_verified"
        finished_ns = time.perf_counter_ns()
        records.append(
            {
                "sequence": int(message["sequence"]),
                "logical_type": str(message["logical_type"]),
                "direction": str(message["direction"]),
                "logical_payload_bytes": len(payload),
                "action": action,
                "started_ns": started_ns,
                "finished_ns": finished_ns,
                "duration_seconds": (finished_ns - started_ns) / 1_000_000_000.0,
                "payload_sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    return records


def _run_udp_trace(
    connection: socket.socket,
    *,
    role: str,
    plan: list[dict[str, Any]],
    transfer_id: str,
    peer: tuple[str, int] | None,
) -> tuple[list[dict[str, Any]], tuple[str, int] | None]:
    """Executa o traço bidirecional por datagramas UDP."""
    records: list[dict[str, Any]] = []
    for message in plan:
        payload = _payload(transfer_id, message)
        if len(payload) > 65_507:
            raise ValueError(
                f"UDP payload exceeds 65507 bytes: {len(payload)}"
            )
        sender = (
            role == "client" and message["direction"] == "iot_to_server"
        ) or (
            role == "server" and message["direction"] == "server_to_iot"
        )
        started_ns = time.perf_counter_ns()
        if sender:
            if role == "server":
                if peer is None:
                    raise RuntimeError(
                        "UDP server cannot send before learning the client address"
                    )
                sent = connection.sendto(payload, peer)
            else:
                sent = connection.send(payload)
            if sent != len(payload):
                raise ConnectionError(f"partial UDP datagram: {sent}/{len(payload)}")
            action = "sent"
        else:
            if role == "server":
                received, observed_peer = connection.recvfrom(65_535)
                peer = observed_peer
            else:
                received = connection.recv(65_535)
            if len(received) != len(payload):
                raise ValueError(
                    f"UDP datagram length mismatch: {len(received)} != {len(payload)}"
                )
            if hashlib.sha256(received).digest() != hashlib.sha256(payload).digest():
                raise ValueError("UDP datagram SHA-256 mismatch")
            action = "received_and_sha256_verified"
        finished_ns = time.perf_counter_ns()
        records.append(
            {
                "sequence": int(message["sequence"]),
                "logical_type": str(message["logical_type"]),
                "direction": str(message["direction"]),
                "logical_payload_bytes": len(payload),
                "action": action,
                "started_ns": started_ns,
                "finished_ns": finished_ns,
                "duration_seconds": (
                    finished_ns - started_ns
                ) / 1_000_000_000.0,
                "payload_sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    return records, peer


def _open_server(host: str, port: int, timeout: float) -> tuple[socket.socket, socket.socket]:
    """Abre o socket TCP do servidor."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.settimeout(timeout)
    listener.bind((host, port))
    listener.listen(1)
    connection, _ = listener.accept()
    connection.settimeout(timeout)
    connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return listener, connection


def _open_client(
    host: str,
    port: int,
    timeout: float,
    bind_host: str | None = None,
) -> socket.socket:
    """Abre o socket TCP do cliente e conecta ao servidor."""
    deadline = time.monotonic() + timeout
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connection.settimeout(max(0.05, deadline - time.monotonic()))
        try:
            if bind_host is not None:
                connection.bind((bind_host, 0))
            connection.connect((host, port))
            connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            return connection
        except OSError as exc:
            last_error = exc
            connection.close()
            time.sleep(0.05)
    raise TimeoutError(f"TCP connection to {host}:{port} failed: {last_error}")


def _open_udp_server(host: str, port: int, timeout: float) -> socket.socket:
    """Abre o socket UDP do servidor."""
    connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    connection.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    connection.settimeout(timeout)
    connection.bind((host, port))
    return connection


def _open_udp_client(
    host: str,
    port: int,
    timeout: float,
    bind_host: str | None = None,
) -> socket.socket:
    """Abre o socket UDP do cliente."""
    connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    connection.settimeout(timeout)
    if bind_host is not None:
        connection.bind((bind_host, 0))
    connection.connect((host, port))
    return connection


def main() -> int:
    """Executa o fluxo principal deste módulo.

    Retorna:
        Valor numérico calculado.
    """
    args = _arguments()
    started_ns = time.perf_counter_ns()
    listener: socket.socket | None = None
    connection: socket.socket | None = None
    report: dict[str, Any] = {
        "role": args.role,
        "transfer_id": args.transfer_id,
        "delivered": False,
        "records": [],
    }
    try:
        plan = _decode_plan(args.plan_base64)
        peer: tuple[str, int] | None = None
        if args.transport == "tcp" and args.role == "server":
            listener, connection = _open_server(
                args.host, args.port, args.timeout
            )
        elif args.transport == "tcp":
            connection = _open_client(
                args.host, args.port, args.timeout, args.bind_host
            )
        elif args.role == "server":
            connection = _open_udp_server(args.host, args.port, args.timeout)
            if args.ready_file is not None:
                Path(args.ready_file).write_text("ready\n", encoding="ascii")
        else:
            connection = _open_udp_client(
                args.host, args.port, args.timeout, args.bind_host
            )
        report["local_address"] = list(connection.getsockname())
        if args.transport == "tcp":
            report["peer_address"] = list(connection.getpeername())
            report["records"] = _run_trace(
                connection,
                role=args.role,
                plan=plan,
                transfer_id=args.transfer_id,
            )
            if args.role == "server":
                connection.sendall(COMPLETION)
            elif _receive_exact(connection, len(COMPLETION)) != COMPLETION:
                raise ValueError("invalid server completion marker")
        else:
            report["records"], peer = _run_udp_trace(
                connection,
                role=args.role,
                plan=plan,
                transfer_id=args.transfer_id,
                peer=peer,
            )
            if args.role == "server":
                if peer is None:
                    raise RuntimeError("UDP client address was not observed")
                connection.sendto(COMPLETION, peer)
                report["peer_address"] = list(peer)
            else:
                if connection.recv(len(COMPLETION)) != COMPLETION:
                    raise ValueError("invalid UDP server completion marker")
                report["peer_address"] = list(connection.getpeername())
        report["delivered"] = True
        return_code = 0
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        return_code = 1
    finally:
        if connection is not None:
            connection.close()
        if listener is not None:
            listener.close()
        finished_ns = time.perf_counter_ns()
        report["started_ns"] = started_ns
        report["finished_ns"] = finished_ns
        report["duration_seconds"] = (finished_ns - started_ns) / 1_000_000_000.0
        print(json.dumps(report, ensure_ascii=True, separators=(",", ":")))
    return return_code


if __name__ == "__main__":
    sys.exit(main())
