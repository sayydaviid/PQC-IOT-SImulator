"""Mininet-WiFi recovery with real client process restarts and packet capture.

This is a correctness integration check, not a calibrated latency/energy study.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import struct
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
from pqc_iot_simulator.pqc_iot_sim.components.network import Network  # noqa: E402
from pqc_iot_simulator.pqc_iot_sim.components.recovery import Identity, b64  # noqa: E402
from pqc_iot_simulator.pqc_iot_sim.engines.mininet_wifi_engine import MininetWiFiEngine  # noqa: E402

PROBE = "pqc_iot_simulator.pqc_iot_sim.recovery_probe"


def pcap_counts(path, client_ip):
    """Classic libpcap Ethernet/IPv4 parsing; counts IP bytes including retransmits."""
    raw = Path(path).read_bytes()
    if len(raw) < 24 or raw[:4] not in (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4"):
        raise RuntimeError("unsupported/incomplete capture")
    order = "<" if raw[:4] == b"\xd4\xc3\xb2\xa1" else ">"
    if struct.unpack(order + "I", raw[20:24])[0] != 1:
        raise RuntimeError("Ethernet capture required")
    tx, rx, packets, position = 0, 0, 0, 24
    flows = {}
    intervals = {}
    client = bytes(map(int, client_ip.split(".")))
    while position < len(raw):
        if position + 16 > len(raw):
            raise RuntimeError("truncated packet header")
        size = struct.unpack(order + "IIII", raw[position : position + 16])[2]
        position += 16
        data = raw[position : position + size]
        position += size
        if len(data) != size:
            raise RuntimeError("truncated packet")
        if len(data) < 34 or data[12:14] != b"\x08\x00":
            continue
        ip = data[14:]
        length = int.from_bytes(ip[2:4], "big")
        if len(ip) < length:
            raise RuntimeError("incomplete captured IP packet")
        outgoing = ip[12:16] == client
        incoming = ip[16:20] == client
        if (outgoing or incoming) and ip[9] == 6:
            ihl = (ip[0] & 15) * 4
            tcp = ip[ihl:]
            tcp_header = (tcp[12] >> 4) * 4
            port = int.from_bytes(tcp[:2] if outgoing else tcp[2:4], "big")
            flow = flows.setdefault(str(port), {"tx_payload": 0, "rx_payload": 0})
            flow["tx_payload" if outgoing else "rx_payload"] += (
                length - ihl - tcp_header
            )
            payload = length - ihl - tcp_header
            if payload > 0:
                start = int.from_bytes(tcp[4:8], "big")
                end = start + payload
                spans = intervals.setdefault(
                    (str(port), "tx" if outgoing else "rx"), []
                )
                spans.append((start, min(end, 2**32)))
                if end > 2**32:
                    spans.append((0, end - 2**32))
        if ip[12:16] == client:
            tx += length
            packets += 1
        elif ip[16:20] == client:
            rx += length
            packets += 1
    if tx <= 0 or rx <= 0:
        raise RuntimeError("bidirectional IPv4 traffic missing")
    for (port, direction), spans in intervals.items():
        total, ceiling = 0, -1
        for start, end in sorted(spans):
            total += max(0, end - max(start, ceiling))
            ceiling = max(ceiling, end)
        flows[port][direction + "_unique_payload"] = total
    return {
        "iot_tx_ip_bytes": tx,
        "iot_rx_ip_bytes": rx,
        "ipv4_packets": packets,
        "tcp_flows": flows,
        "pcap_sha256": hashlib.sha256(raw).hexdigest(),
    }


class RecoveryNetworkValidation:
    """Mininet-WiFi recovery with real client process restarts and packet capture.

    Configure once, then call ``run()`` from a notebook.
    """

    def __init__(self, *, boots=6, output=None):
        self.boots = boots
        self.output = Path(output) if output is not None else None

    def run(self):
        args = self
        if args.boots < 2:
            raise ValueError("at least two boots required")
        output = args.output or ROOT / "results/raw" / (
            "recovery_network_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        )
        output.mkdir(parents=True, exist_ok=False)
        paths = [
            Path(__file__),
            ROOT / "pqc_iot_simulator/pqc_iot_sim/components/recovery.py",
            ROOT / "pqc_iot_simulator/pqc_iot_sim/recovery_probe.py",
            ROOT / "pqc_iot_simulator/pqc_iot_sim/components/network.py",
            ROOT / "pqc_iot_simulator/pqc_iot_sim/engines/mininet_wifi_engine.py",
        ]
        manifest = {
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "source_sha256": {
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in paths
            },
            "parameters": {
                "boots_per_policy": args.boots,
                "sensors": 1,
                "transport": "TCP",
                "injected_loss_pct": 0,
            },
            "clock": "logical zero for protocol age; host perf_counter for descriptive network timing",
            "limitations": [
                "no ESP energy",
                "gateway authority stays live",
                "fresh entropy outside rollback",
                "experimental protocol, no TLS interoperability",
            ],
        }
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
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
        processes = []
        results = []
        try:
            engine.build()
            engine.start()
            if (
                engine.last_association_report["failed"]
                or len(engine.last_association_report["associated"]) != 1
            ):
                raise RuntimeError("Wi-Fi association incomplete")
            (station, destination) = (
                engine.get_mininet_node("iot_1"),
                engine.get_mininet_node("server_1"),
            )
            (client_ip, server_ip) = (engine.get_ip("iot_1"), engine.get_ip("server_1"))
            (client_identity, server_identity) = (
                Identity.generate(),
                Identity.generate(),
            )
            with tempfile.TemporaryDirectory(
                prefix="pqc-recovery-network-secrets-"
            ) as private_name:
                private = Path(private_name)
                (client_credentials, server_credentials) = (
                    private / "client.json",
                    private / "server.json",
                )
                client_credentials.write_text(
                    json.dumps(
                        {
                            "public": b64(client_identity.public),
                            "private": b64(client_identity.private),
                            "peer_public": b64(server_identity.public),
                            "wrapping_key": b64(os.urandom(32)),
                        }
                    )
                )
                server_credentials.write_text(
                    json.dumps(
                        {
                            "public": b64(server_identity.public),
                            "private": b64(server_identity.private),
                            "peer_public": b64(client_identity.public),
                        }
                    )
                )
                for path in (client_credentials, server_credentials):
                    path.chmod(384)
                for index, policy in enumerate(
                    ("full_pqc", "psk_resume", "pqc_resume")
                ):
                    port = 39881 + index
                    (ready, state) = (private / (policy + ".ready"), private / policy)
                    capture = output / (policy + ".pcap")
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
                    processes.append(tcpdump)
                    (available, detail) = engine._wait_for_tcpdump_ready(tcpdump)
                    if not available:
                        raise RuntimeError("capture not ready: " + detail)
                    server_log = open(output / (policy + "_server.log"), "w")
                    gateway = destination.popen(
                        [
                            sys.executable,
                            "-m",
                            PROBE,
                            "server",
                            "--host",
                            server_ip,
                            "--port",
                            str(port),
                            "--credentials",
                            str(server_credentials),
                            "--output",
                            str(output / (policy + "_server.json")),
                            "--ready",
                            str(ready),
                            "--boots",
                            str(args.boots),
                        ],
                        stdout=server_log,
                        stderr=subprocess.STDOUT,
                    )
                    processes.append(gateway)
                    deadline = time.monotonic() + 20
                    while (
                        not ready.exists()
                        and time.monotonic() < deadline
                        and (gateway.poll() is None)
                    ):
                        time.sleep(0.05)
                    if not ready.exists():
                        raise RuntimeError("gateway failed to start; see server log")
                    (boots, old_snapshot) = ([], None)
                    try:
                        for boot in range(args.boots):
                            if old_snapshot is not None:
                                (state / "state").write_bytes(old_snapshot)
                            process = station.popen(
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
                                    str(client_credentials),
                                    "--state",
                                    str(state),
                                    "--policy",
                                    policy,
                                    "--boot-index",
                                    str(boot),
                                    "--output",
                                    str(output / f"{policy}_boot_{boot}.json"),
                                ],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True,
                            )
                            processes.append(process)
                            (log, _) = process.communicate(timeout=25)
                            if process.returncode:
                                raise RuntimeError("client failed: " + log)
                            boots.append(
                                json.loads(
                                    (output / f"{policy}_boot_{boot}.json").read_text()
                                )
                            )
                            if old_snapshot is None:
                                old_snapshot = (state / "state").read_bytes()
                        if gateway.wait(timeout=20):
                            raise RuntimeError("gateway failed; see server log")
                        deadline = time.monotonic() + 4
                        complete = False
                        while time.monotonic() < deadline:
                            try:
                                captured = pcap_counts(capture, client_ip)
                                complete = all(
                                    (
                                        str(b["client_tcp_port"])
                                        in captured["tcp_flows"]
                                        and captured["tcp_flows"][
                                            str(b["client_tcp_port"])
                                        ].get("tx_unique_payload")
                                        == b["total_framed_tx_bytes"]
                                        and (
                                            captured["tcp_flows"][
                                                str(b["client_tcp_port"])
                                            ].get("rx_unique_payload")
                                            == b["total_framed_rx_bytes"]
                                        )
                                        for b in boots
                                    )
                                )
                            except RuntimeError:
                                complete = False
                            if complete:
                                break
                            time.sleep(0.05)
                        if not complete:
                            raise RuntimeError(
                                "PCAP missing a process flow or unique application bytes"
                            )
                    finally:
                        tcpdump.send_signal(signal.SIGINT)
                        (_, capture_log) = tcpdump.communicate(timeout=5)
                        (output / (policy + "_tcpdump.log")).write_text(capture_log)
                        server_log.close()
                    epochs = {b["traffic_epoch"] for b in boots}
                    pids = {b["client_pid"] for b in boots}
                    if (
                        len(epochs) != args.boots
                        or len(pids) != args.boots
                        or (not all((b["delivered_and_authenticated"] for b in boots)))
                    ):
                        raise RuntimeError(
                            "restart isolation/epoch/remote validation failed"
                        )
                    result = {
                        "policy": policy,
                        "boots": args.boots,
                        "client_storage_rollbacks": args.boots - 1,
                        "distinct_client_processes": len(pids),
                        "distinct_traffic_epochs": len(epochs),
                        "capture_interface": "h1-eth0",
                        "boots_results": boots,
                        **pcap_counts(capture, client_ip),
                    }
                    results.append(result)
                    print(
                        json.dumps(
                            {"policy": policy, "status": "PASS", "boots": len(boots)}
                        ),
                        flush=True,
                    )
            for path in paths:
                if (
                    hashlib.sha256(path.read_bytes()).hexdigest()
                    != manifest["source_sha256"][str(path.relative_to(ROOT))]
                ):
                    raise RuntimeError("source changed during network verification")
            report = {
                "status": "PASS",
                "association": engine.last_association_report,
                "scope": "one sensor, process restart and valid storage rollback, TCP, no injected loss",
                "configured_wired_delay": "2ms",
                "energy": "NOT_MEASURED",
                "cases": results,
            }
            (output / "network_results.json").write_text(json.dumps(report, indent=2))
            print(json.dumps({"status": "PASS", "output": str(output)}, indent=2))
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
            engine.stop()
        return output
