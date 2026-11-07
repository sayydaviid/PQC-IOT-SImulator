"""TLS 1.3 endpoint using the isolated native OpenSSL, no size-only traffic."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import struct
import time
from pathlib import Path
import importlib.util
import sys

import _continuity_tls as native

# Execute as an isolated endpoint script: importing the simulator package would
# initialize unrelated engines/plotting code in every simulated device boot.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

def load_component(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / "components" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

_ledger = load_component("_continuity_ledger", "reading_ledger.py")
_checkpoint = load_component("_continuity_checkpoint", "recovery.py")
ReadingConflict, ReadingLedger = _ledger.ReadingConflict, _ledger.ReadingLedger
SealedStore, b64, unb64 = _checkpoint.SealedStore, _checkpoint.b64, _checkpoint.unb64
PROFILES = load_component("_continuity_design", "../research/tls/design.py").PROFILES

LENGTH = struct.Struct("!I")


def exact(peer, size):
    output = bytearray()
    while len(output) < size:
        output.extend(native.read(peer, size - len(output)))
    return bytes(output)


def receive(peer):
    size = LENGTH.unpack(exact(peer, 4))[0]
    if not 1 <= size <= 8192:
        raise ValueError("invalid application frame")
    return exact(peer, size)


def send(peer, payload):
    data = LENGTH.pack(len(payload)) + payload
    position = 0
    while position < len(data):
        position += native.write(peer, data[position:])


def configure_socket(connection):
    connection.setblocking(True)
    connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    timeout = struct.pack("ll", 15, 0)
    connection.setsockopt(socket.SOL_SOCKET, socket.SO_RCVTIMEO, timeout)
    connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDTIMEO, timeout)


def retransmissions(connection):
    # Linux UAPI tcp_info: first 8 bytes + 24 u32 fields; total_retrans
    # is at byte 100. Captures after netem cannot see every dropped copy.
    info = connection.getsockopt(socket.IPPROTO_TCP, socket.TCP_INFO, 104)
    return struct.unpack_from("=I", info, 100)[0]


def shutdown(peer):
    try:
        if native.shutdown(peer) == 0:
            native.shutdown(peer)
    except OSError:
        pass


def context(args, server):
    private = Path(args.credentials)
    profile = PROFILES[args.profile]
    ticket = b""
    if server:
        ticket = Path(args.ticket_key).read_bytes() if args.ticket_key else os.urandom(80)
    return native.context(
        str(private / ("server.crt" if server else "client.crt")),
        str(private / ("server.key" if server else "client.key")),
        str(private / "ca.crt"),
        profile["group"],
        int(server),
        profile["sigalgs"],
        ticket,
    )


def client(args):
    ctx = context(args, False)
    private = Path(args.credentials)
    store = SealedStore(Path(args.state), (private / "wrapping.key").read_bytes())
    ca_hash = hashlib.sha256((private / "ca.crt").read_bytes()).hexdigest()
    saved = b""
    local_fallback = False
    if args.mode == "resume" and (store.directory / "state").exists():
        try:
            state = store.read("state")
            if state["hostname"] != "gateway.local" or state["ca_sha256"] != ca_hash:
                raise ValueError("stored session belongs to a different trust context")
            saved = unb64(state["der"])
        except ValueError:
            local_fallback = True
    payload = Path(args.payload).read_bytes()
    record = json.dumps(
        {"reading_id": args.reading_id, "payload": b64(payload)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    result = {
        "pid": os.getpid(),
        "mode": args.mode,
        "reading_id": args.reading_id,
        "session_offered": bool(saved),
        "local_state_fallback": local_fallback,
        "acknowledged": False,
        "resumable_session_saved": False,
        "stage": "tcp_connect",
    }
    peer = None
    with socket.socket() as connection:
        configure_socket(connection)
        started = time.perf_counter_ns()
        try:
            connection.bind((args.bind_host, 0))
            result["client_tcp_port"] = connection.getsockname()[1]
            connection.connect((args.host, args.port))
            started = time.perf_counter_ns()
            result["stage"] = "tls_handshake"
            peer = native.handshake(ctx, connection.fileno(), 0, "gateway.local", saved)
            result["handshake_ms"] = (time.perf_counter_ns() - started) / 1e6
            result["stage"] = "application"
            send(peer, record)
            result["tx_data_tls_bytes"] = native.metadata(peer)["tx_tls_bytes"]
            answer = json.loads(receive(peer))
            if (
                answer.get("reading_id") != args.reading_id
                or answer.get("sha256") != hashlib.sha256(payload).hexdigest()
            ):
                raise ValueError("TLS peer did not confirm the expected reading")
            if not answer.get("accepted"):
                raise ValueError("server rejected reading content")
            result["acknowledged"] = True
            result["stage"] = "confirmed"
            result["duplicate"] = answer["duplicate"]
            result["ack_monotonic_ns"] = time.perf_counter_ns()
            result["rx_confirmed_tls_bytes"] = native.metadata(peer)["rx_tls_bytes"]
            result["first_reading_ack_ms"] = (result["ack_monotonic_ns"] - started) / 1e6
        except (OSError, ValueError) as error:
            result["error"] = str(error)
        finally:
            if peer is not None:
                result["attempt_ms"] = (time.perf_counter_ns() - started) / 1e6
                der = native.session(peer)
                if der:
                    store.write(
                        "state",
                        {
                            "der": b64(der),
                            "hostname": "gateway.local",
                            "ca_sha256": ca_hash,
                        },
                    )
                result["resumable_session_saved"] = bool(der)
                shutdown(peer)
                result.update(native.metadata(peer))
                result["tcp_retransmitted_segments"] = retransmissions(connection)
    Path(args.output).write_text(json.dumps(result, indent=2))
    if not result["acknowledged"]:
        raise SystemExit(2)


def server(args):
    ctx = context(args, True)
    ledger = ReadingLedger(Path(args.ledger), args.deduplicate)
    results = []
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((args.host, args.port))
    listener.listen(4)
    listener.settimeout(0.05 if args.stop_file else 90)
    pending_drops = set(args.drop_reading_id)
    Path(args.ready).write_text("ready")
    try:
        number = 0
        while number < args.connections:
            if args.stop_file and Path(args.stop_file).exists():
                break
            try:
                connection, address = listener.accept()
            except socket.timeout:
                if args.stop_file:
                    continue
                raise
            configure_socket(connection)
            row = {
                "connection": number,
                "client_tcp_port": address[1],
                "reading_received": False,
            }
            peer = None
            with connection:
                try:
                    peer = native.handshake(ctx, connection.fileno(), 1, "", b"")
                    record = json.loads(receive(peer))
                    if (
                        set(record) != {"reading_id", "payload"}
                        or len(record["reading_id"]) != 32
                    ):
                        raise ValueError("invalid reading")
                    payload = unb64(record["payload"])
                    row["reading_id"] = record["reading_id"]
                    answer = ledger.ingest("iot_1", record["reading_id"], payload)
                    row["reading_received"] = True
                    row.update(answer)
                    if number in args.drop_ack or record["reading_id"] in pending_drops:
                        pending_drops.discard(record["reading_id"])
                        row["ack_dropped_after_durable_commit"] = True
                        # Hard close: a process interruption, NOT TCP packet loss.
                    else:
                        answer["accepted"] = True
                        send(
                            peer,
                            json.dumps(
                                answer, sort_keys=True, separators=(",", ":")
                            ).encode(),
                        )
                        shutdown(peer)
                except (OSError, ValueError, ReadingConflict) as error:
                    row["error"] = str(error)
                finally:
                    if peer is not None:
                        row.update(native.metadata(peer))
                        row["tcp_retransmitted_segments"] = retransmissions(connection)
            results.append(row)
            number += 1
            Path(args.output).write_text(
                json.dumps({"connections": results, **ledger.counts()}, indent=2)
            )
    finally:
        listener.close()
        ledger.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("client", "server"))
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--credentials", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--profile", choices=tuple(PROFILES), default="pqc")
    parser.add_argument("--mode", choices=("full", "resume"), default="resume")
    parser.add_argument("--state")
    parser.add_argument("--payload")
    parser.add_argument("--reading-id")
    parser.add_argument("--bind-host", default="0.0.0.0")
    parser.add_argument("--ledger")
    parser.add_argument("--ready")
    parser.add_argument("--connections", type=int, default=6)
    parser.add_argument("--drop-ack", type=int, nargs="*", default=[])
    parser.add_argument("--ticket-key")
    parser.add_argument("--drop-reading-id", nargs="*", default=[])
    parser.add_argument("--stop-file")
    parser.add_argument("--deduplicate", action="store_true")
    args = parser.parse_args()
    (server if args.role == "server" else client)(args)


if __name__ == "__main__":
    main()
