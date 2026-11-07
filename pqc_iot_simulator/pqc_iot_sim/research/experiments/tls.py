"""Registered Mininet pilot: native PQC TLS, process failures and durable IDs."""

from __future__ import annotations

import hashlib
import json
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
from pqc_iot_simulator.pqc_iot_sim.components.network import Network  # noqa: E402
from pqc_iot_simulator.pqc_iot_sim.engines.mininet_wifi_engine import MininetWiFiEngine  # noqa: E402
from pqc_iot_simulator.pqc_iot_sim.research.tls.baseline_credentials import provision  # noqa: E402
from pqc_iot_simulator.pqc_iot_sim.research.tls.capture import tls_capture, covered  # noqa: E402
from pqc_iot_simulator.pqc_iot_sim.research.validation.tls_baseline import (
    check_tls,
    PROBE,
)  # noqa: E402


def execute_case(engine, directory, private, credentials, mode, deduplicate, block):
    directory.mkdir()
    private.mkdir(mode=0o700)
    station = engine.get_mininet_node("iot_1")
    destination = engine.get_mininet_node("server_1")
    client_ip, server_ip = engine.get_ip("iot_1"), engine.get_ip("server_1")
    port = 39900
    capture = directory / "traffic.pcap"
    processes = []
    rows = []
    server_rows = []
    sealed_snapshot = None
    tcpdump = destination.popen(
        [
            "tcpdump",
            "--immediate-mode",
            "-U",
            "-n",
            "-s",
            "0",
            "-i",
            "h1-eth0",
            "-w",
            str(capture),
            "tcp",
            "port",
            str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    ready_capture, detail = engine._wait_for_tcpdump_ready(tcpdump)
    if not ready_capture:
        tcpdump.terminate()
        raise RuntimeError("capture failed: " + detail)
    ledger, state = private / "ledger.db", private / "state"
    try:
        for phase, boots in ((0, (0, 1)), (1, (2, 3, 4))):
            ready = private / f"ready{phase}"
            server_output = directory / f"server_{phase}.json"
            server_log = open(directory / f"server_{phase}.log", "w")
            command = [
                sys.executable,
                "-m",
                PROBE,
                "server",
                "--host",
                server_ip,
                "--port",
                str(port),
                "--credentials",
                str(credentials),
                "--ledger",
                str(ledger),
                "--ready",
                str(ready),
                "--output",
                str(server_output),
                "--connections",
                "2" if phase == 0 else "4",
                "--drop-ack",
                "-1" if phase == 0 else "1",
            ]
            if deduplicate:
                command.append("--deduplicate")
            gateway = destination.popen(
                command, stdout=server_log, stderr=subprocess.STDOUT
            )
            processes.append(gateway)
            try:
                deadline = time.monotonic() + 10
                while (
                    not ready.exists()
                    and gateway.poll() is None
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.05)
                if not ready.exists():
                    raise RuntimeError("TLS gateway failed to start")
                for boot in boots:
                    if boot == 4:
                        if sealed_snapshot is None:
                            raise RuntimeError("missing authenticated ticket snapshot")
                        (state / "state").write_bytes(sealed_snapshot)
                    rid = hashlib.sha256(
                        f"block={block};boot={boot}".encode()
                    ).hexdigest()[:32]
                    payload = private / f"reading_{boot}"
                    payload.write_bytes(
                        f"synthetic block={block} reading={boot}".encode()
                    )
                    reading_started = time.perf_counter_ns()
                    for retry in range(2 if boot == 3 else 1):
                        output = directory / f"client_{boot}_{retry}.json"
                        process_started = time.perf_counter_ns()
                        client = station.popen(
                            [
                                sys.executable,
                                "-m",
                                PROBE,
                                "client",
                                "--host",
                                server_ip,
                                "--port",
                                str(port),
                                "--bind-host",
                                client_ip,
                                "--credentials",
                                str(credentials),
                                "--state",
                                str(state),
                                "--mode",
                                mode,
                                "--payload",
                                str(payload),
                                "--reading-id",
                                rid,
                                "--output",
                                str(output),
                            ],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                        )
                        processes.append(client)
                        log, _ = client.communicate(timeout=25)
                        if client.returncode not in (0, 2) or not output.is_file():
                            raise RuntimeError("TLS client process failed: " + log)
                        row = json.loads(output.read_text())
                        row["process_ms"] = (
                            time.perf_counter_ns() - process_started
                        ) / 1e6
                        check_tls(row)
                        expected_ack = not (boot == 3 and retry == 0)
                        if row["acknowledged"] != expected_ack:
                            raise RuntimeError("unexpected reading delivery outcome")
                        if mode == "full" and row["reused"]:
                            raise RuntimeError("full comparator silently resumed")
                        if mode == "resume" and boot == 1 and not row["reused"]:
                            raise RuntimeError("warm TLS connection did not resume")
                        if boot == 2 and row["reused"]:
                            raise RuntimeError(
                                "lost server context unexpectedly resumed"
                            )
                        row.update({"boot": boot, "retry": retry})
                        if row["acknowledged"]:
                            row["reading_recovery_ms"] = (
                                time.perf_counter_ns() - reading_started
                            ) / 1e6
                        rows.append(row)
                    if boot == 2:
                        sealed_snapshot = (state / "state").read_bytes()
                if gateway.wait(timeout=20):
                    raise RuntimeError("gateway process failed")
                server_result = json.loads(server_output.read_text())
                server_rows.extend(server_result["connections"])
                if phase == 1:
                    final_counts = {
                        k: server_result[k]
                        for k in (
                            "unique_readings",
                            "application_effects",
                            "duplicate_effects",
                        )
                    }
            finally:
                if gateway.poll() is None:
                    gateway.terminate()
                    gateway.wait(timeout=3)
                server_log.close()
        if (
            len({r["pid"] for r in rows}) != 6
            or len({r["client_share_sha256"] for r in rows}) != 6
            or len({r["server_share_sha256"] for r in rows}) != 6
        ):
            raise RuntimeError("TLS process/key-share freshness failed")
        if final_counts != {
            "unique_readings": 5,
            "application_effects": 5 if deduplicate else 6,
            "duplicate_effects": 0 if deduplicate else 1,
        }:
            raise RuntimeError("durable application count mismatch")
        deadline = time.monotonic() + 4
        complete = False
        while time.monotonic() < deadline:
            try:
                captured = tls_capture(capture, client_ip)
                complete = all(covered(captured, row) for row in rows)
            except RuntimeError:
                complete = False
            if complete:
                break
            time.sleep(0.05)
        if not complete:
            raise RuntimeError("TLS record bytes do not match captured TCP streams")
        result = {
            "mode": mode,
            "deduplicate": deduplicate,
            "block": block,
            "clients": rows,
            "server_connections": server_rows,
            "application": final_counts,
            "capture": captured,
            "status": "PASS",
        }
        (directory / "case.json").write_text(json.dumps(result, indent=2))
        return result
    finally:
        tcpdump.send_signal(signal.SIGINT)
        _, log = tcpdump.communicate(timeout=5)
        (directory / "tcpdump.log").write_text(log)
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=3)


class TLSExperiment:
    """Registered Mininet pilot: native PQC TLS, process failures and durable IDs.

    Configure once, then call ``run()`` from a notebook.
    """

    def __init__(self, *, output, blocks=5, losses=(0, 1, 5)):
        self.blocks = blocks
        if self.blocks < 1:
            raise ValueError("blocks must be positive")
        self.losses = losses
        self.output = Path(output) if output is not None else None

    def run(self):
        args = self
        if args.blocks < 1 or any((not 0 <= loss <= 5 for loss in args.losses)):
            raise ValueError("positive blocks, losses from 0 to 5 percent required")
        args.output.mkdir(parents=True, exist_ok=False)
        source_names = [
            "pqc_iot_simulator/pqc_iot_sim/research/runtime/native/tls/native.c",
            "docker/tls/Dockerfile",
            "docker/tls/compose.yml",
            "pqc_iot_simulator/pqc_iot_sim/tls_probe.py",
            "pqc_iot_simulator/pqc_iot_sim/components/reading_ledger.py",
            "pqc_iot_simulator/pqc_iot_sim/components/recovery.py",
            "pqc_iot_simulator/pqc_iot_sim/research/tls/baseline_credentials.py",
            "pqc_iot_simulator/pqc_iot_sim/research/validation/tls_baseline.py",
            "pqc_iot_simulator/pqc_iot_sim/research/validation/recovery_network.py",
            "pqc_iot_simulator/pqc_iot_sim/research/tls/capture.py",
            "pqc_iot_simulator/pqc_iot_sim/research/experiments/tls.py",
            "pqc_iot_simulator/pqc_iot_sim/engines/mininet_wifi_engine.py",
        ]
        hashes = {
            n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in source_names
        }
        if (
            hashes["pqc_iot_simulator/pqc_iot_sim/research/runtime/native/tls/native.c"]
            != hashlib.sha256(
                Path("/opt/pqc-tls/native/native.c").read_bytes()
            ).hexdigest()
        ):
            raise RuntimeError("native source differs from compiled image")
        manifest = {
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "source_sha256": hashes,
            "openssl": subprocess.check_output(
                ["openssl", "version"], text=True
            ).strip(),
            "openssl_commit": Path("/opt/pqc-tls/source-commit").read_text().strip(),
            "parameters": {
                "blocks": args.blocks,
                "loss_pct": args.losses,
                "boots": 5,
                "modes": ["full", "resume"],
                "deduplication": [False, True],
            },
            "registered_criteria": [
                "verified mutual PQ identity",
                "actual warm resumption and forced full fallback after server context loss",
                "fresh asymmetric shares in every new client process",
                "reading retry after intentionally lost ACK",
                "contiguous TLS/TCP data coverage; closing alerts accounted separately for intentionally interrupted ACK",
                "durable dedup zero duplicate effects; negative control one duplicate effect",
            ],
            "fault_schedule": {
                "boot2": "gateway process restarted; ledger preserved",
                "boot3": "ACK dropped AFTER durable ingestion; new-process retry",
                "boot4": "restore sealed client ticket from boot2; gateway stays live",
            },
            "network": "one IoT station; independent netem loss on both directions of AP-server wired link; 2ms delay each direction",
            "statistics": "pilot; block is repetition unit; no robust P95/ESP energy claim",
        }
        (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2))
        cases = []
        with tempfile.TemporaryDirectory(prefix="tls-network-secrets-") as name:
            private = Path(name)
            provision(private / "credentials")
            for loss in args.losses:
                for block in range(args.blocks):
                    network = Network(verbose=False, log_level="silent")
                    network.set_ready_topology("star", nodes=1)
                    network.create_hosts()
                    engine = MininetWiFiEngine(
                        network,
                        verbose=False,
                        log_level="silent",
                        default_delay="2ms",
                        default_loss=0,
                        association_wait_seconds=5,
                    )
                    try:
                        engine.build()
                        engine.start()
                        if (
                            engine.last_association_report["failed"]
                            or len(engine.last_association_report["associated"]) != 1
                        ):
                            raise RuntimeError("Wi-Fi association incomplete")
                        destination = engine.get_mininet_node("server_1")
                        interface = destination.defaultIntf()
                        other = (
                            interface.link.intf1
                            if interface.link.intf2 is interface
                            else interface.link.intf2
                        )
                        qdiscs = []
                        for endpoint in (interface, other):
                            command = f"tc qdisc replace dev {endpoint.name} root netem delay 2ms loss {loss}%"
                            error = endpoint.node.cmd(command)
                            if error.strip():
                                raise RuntimeError(
                                    "netem configuration failed: " + error
                                )
                            actual = endpoint.node.cmd(
                                f"tc qdisc show dev {endpoint.name}"
                            )
                            if "netem" not in actual or "delay 2ms" not in actual:
                                raise RuntimeError(
                                    "configured qdisc not active: " + actual
                                )
                            qdiscs.append(actual.strip())
                        order = [
                            ("full", False),
                            ("resume", False),
                            ("full", True),
                            ("resume", True),
                        ]
                        order = order[block % 4 :] + order[: block % 4]
                        for mode, deduplicate in order:
                            case_id = f"loss{loss:g}_block{block}_{mode}_dedup{int(deduplicate)}"
                            result = execute_case(
                                engine,
                                args.output / case_id,
                                private / case_id,
                                private / "credentials",
                                mode,
                                deduplicate,
                                block,
                            )
                            result.update({"loss_pct": loss, "qdisc": qdiscs})
                            cases.append(result)
                            print(
                                json.dumps(
                                    {
                                        "completed_cases": len(cases),
                                        "case": case_id,
                                        "status": "PASS",
                                    }
                                ),
                                flush=True,
                            )
                    finally:
                        engine.stop()
        for n in source_names:
            if hashlib.sha256((ROOT / n).read_bytes()).hexdigest() != hashes[n]:
                raise RuntimeError("source changed during registered pilot")
        (args.output / "results.json").write_text(
            json.dumps({"status": "PASS", "cases": cases}, indent=2)
        )
        print(
            json.dumps(
                {"status": "PASS", "cases": len(cases), "output": str(args.output)},
                indent=2,
            )
        )
        return args.output
