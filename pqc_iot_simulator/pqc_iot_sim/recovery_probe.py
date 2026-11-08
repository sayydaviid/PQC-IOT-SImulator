"""Real authenticated recovery flights over TCP, for namespace/process checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
import time
from pathlib import Path

from pqc_iot_simulator.pqc_iot_sim.components.recovery import ClientHandshake
from pqc_iot_simulator.pqc_iot_sim.components.recovery import FRAME
from pqc_iot_simulator.pqc_iot_sim.components.recovery import Gateway
from pqc_iot_simulator.pqc_iot_sim.components.recovery import Identity
from pqc_iot_simulator.pqc_iot_sim.components.recovery import Root
from pqc_iot_simulator.pqc_iot_sim.components.recovery import SealedStore
from pqc_iot_simulator.pqc_iot_sim.components.recovery import Sender
from pqc_iot_simulator.pqc_iot_sim.components.recovery import encode
from pqc_iot_simulator.pqc_iot_sim.components.recovery import mac
from pqc_iot_simulator.pqc_iot_sim.components.recovery import receive_frame
from pqc_iot_simulator.pqc_iot_sim.components.recovery import require_mac
from pqc_iot_simulator.pqc_iot_sim.components.recovery import send_frame
from pqc_iot_simulator.pqc_iot_sim.components.recovery import unb64


def server(args, credentials):
    identity = Identity(unb64(credentials["public"]), unb64(credentials["private"]))
    gateway = Gateway(identity, unb64(credentials["peer_public"]))
    result = {"connections": 0, "accepted": 0, "errors": []}
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.settimeout(45)
        listener.bind((args.host, args.port))
        listener.listen(4)
        Path(args.ready).write_text("ready")
        for _ in range(args.boots):
            connection, _ = listener.accept()
            with connection:
                connection.settimeout(15)
                connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                try:
                    hello = receive_frame(connection)
                    reply = gateway.begin(hello, 0)
                    send_frame(connection, reply)
                    final = receive_frame(connection)
                    ack = gateway.finish(final, 0)
                    send_frame(connection, ack)
                    record = receive_frame(connection)
                    plaintext = gateway.accept(record, 0)
                    result["accepted"] += 1
                    answer = {
                        "accepted": True,
                        "sha256": hashlib.sha256(plaintext).hexdigest(),
                        "counter": record["header"]["counter"],
                    }
                    session = gateway.sessions[record["header"]["epoch"]]
                    answer["auth"] = mac(session.key, "reading-ack", answer)
                    send_frame(connection, answer)
                except Exception as error:
                    result["errors"].append(type(error).__name__ + ": " + str(error))
            result["connections"] += 1
    Path(args.output).write_text(json.dumps(result, indent=2))
    if result["errors"] or result["accepted"] != args.boots:
        raise SystemExit(1)


def client(args, credentials):
    identity = Identity(unb64(credentials["public"]), unb64(credentials["private"]))
    store = SealedStore(Path(args.state), unb64(credentials["wrapping_key"]))
    mode, root = "full_pqc", None
    if (store.directory / "state").exists() and args.policy != "full_pqc":
        root = Root.load(store.read("state")["root"])
        mode = args.policy
    hs = ClientHandshake(identity, unb64(credentials["peer_public"]), mode, root)
    frames = [hs.hello]
    with socket.socket() as connection:
        connection.settimeout(15)
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        connection.bind((args.bind_host, 0))
        connection.connect((args.host, args.port))
        local_port = connection.getsockname()[1]
        started = time.perf_counter_ns()
        send_frame(connection, hs.hello)
        reply = receive_frame(connection)
        final = hs.respond(reply)
        send_frame(connection, final)
        ack = receive_frame(connection)
        session = hs.complete(ack)
        finished = time.perf_counter_ns()
        frames.extend((reply, final, ack))
        sender = Sender(session, hs.root, store, args.policy)
        plaintext = f"synthetic reading boot={args.boot_index:04d}".encode()
        record = sender.encrypt(plaintext, 0)
        send_frame(connection, record)
        answer = receive_frame(connection)
        require_mac(
            session.key,
            "reading-ack",
            {k: v for k, v in answer.items() if k != "auth"},
            answer["auth"],
        )
        if (
            not answer["accepted"]
            or answer["sha256"] != hashlib.sha256(plaintext).hexdigest()
        ):
            raise RuntimeError("remote plaintext validation failed")
        sender.checkpoint()
    result = {
        "policy": args.policy,
        "mode_on_wire": mode,
        "boot_index": args.boot_index,
        "client_pid": __import__("os").getpid(),
        "client_tcp_port": local_port,
        "delivered_and_authenticated": True,
        "traffic_epoch": session.epoch,
        "counter": record["header"]["counter"],
        "handshake_framed_bytes": sum(FRAME.size + len(encode(f)) for f in frames),
        "total_framed_tx_bytes": sum(
            FRAME.size + len(encode(f)) for f in (hs.hello, final, record)
        ),
        "total_framed_rx_bytes": sum(
            FRAME.size + len(encode(f)) for f in (reply, ack, answer)
        ),
        "handshake_network_host_ms": (finished - started) / 1e6,
        "file_writes": store.writes,
        "file_bytes": store.bytes_written,
    }
    Path(args.output).write_text(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("server", "client"))
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--credentials", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--ready")
    parser.add_argument("--boots", type=int, default=6)
    parser.add_argument("--bind-host", default="0.0.0.0")
    parser.add_argument("--state")
    parser.add_argument("--boot-index", type=int, default=0)
    parser.add_argument(
        "--policy",
        choices=("full_pqc", "psk_resume", "pqc_resume"),
        default="pqc_resume",
    )
    args = parser.parse_args()
    credentials = json.loads(Path(args.credentials).read_text())
    (server if args.role == "server" else client)(args, credentials)


if __name__ == "__main__":
    main()
