"""State-preservation and fault-frequency campaign, with matched TLS profiles.

Old TLS/prototype sources and frozen results are never modified. Main comparisons
use identical stateless tickets; the STEK is regenerated or preserved at restart.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.continuity_credentials import provision
from scripts.continuity_design import PROBE, PROFILES, cells, check_tls, schedule
from scripts.tls_capture import tls_capture
from scripts.continuity_capture import covered_attempt

SOURCES = [
    "docs/plano_campanha_continuidade.md", "docs/comparacao_catoni_completa.md",
    "experiments/continuity/native.c", "experiments/continuity/Dockerfile",
    "experiments/continuity/compose.yml", "scripts/continuity_credentials.py",
    "scripts/continuity_design.py", "scripts/run_continuity_campaign.py", "scripts/continuity_capture.py",
    "pqc_iot_simulator/pqc_iot_sim/continuity_probe.py",
    "pqc_iot_simulator/pqc_iot_sim/components/reading_ledger.py",
    "pqc_iot_simulator/pqc_iot_sim/components/recovery.py",
    "pqc_iot_simulator/pqc_iot_sim/engines/mininet_wifi_engine.py",
    "scripts/tls_capture.py", "scripts/verify_recovery_network.py",
]


def hashes():
    return {n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in SOURCES}


def completed_blocks(directory, phase, blocks, readings, source_hashes):
    """Recover whole blocks only. Interrupted blocks remain in the source archive."""
    manifest = json.loads((directory / "manifest.json").read_text())
    if (manifest["phase"], manifest["blocks"], manifest["readings"]) != (phase, blocks, readings):
        raise ValueError("continuation design differs")
    old_hashes = manifest["source_sha256"]
    for name, value in source_hashes.items():
        if name != "scripts/run_continuity_campaign.py" and old_hashes.get(name) != value:
            raise ValueError("experimental source differs: " + name)
    snapshot = ROOT / "experiments/continuity/run_campaign_v3.py"
    if hashlib.sha256(snapshot.read_bytes()).hexdigest() != old_hashes["scripts/run_continuity_campaign.py"]:
        raise ValueError("original runner snapshot differs")
    recovered, complete = [], set()
    for loss in sorted({c[0] for c in cells(phase)}):
        for block in range(blocks):
            ids = [f"l{loss}_b{block}_r{r:g}_a{a:g}_{p}_{t}_d{int(d)}"
                   for l, r, a, p, t, d in cells(phase) if l == loss]
            if not all((directory / i / "case.json").exists() for i in ids):
                continue
            for i in ids:
                case = json.loads((directory / i / "case.json").read_text())
                if case["case_id"] != i or case["readings"] != readings or case["block"] != block:
                    raise ValueError("recovered case identity differs")
                recovered.append(case)
            complete.add((loss, block))
    return manifest, recovered, complete


class LocalNode:
    """Smoke verification only. Publication campaign uses separate namespaces."""
    @staticmethod
    def popen(*args, **kwargs):
        return subprocess.Popen(*args, **kwargs)


def execute_case(station, destination, client_ip, server_ip, interface, directory,
                 private, credentials, profile, treatment, deduplicate, faults, readings,
                 block, capture_enabled=True, max_attempts=3):
    directory.mkdir()
    private.mkdir(mode=0o700)
    port = 39911
    state, ledger, ticket_path = private / "state", private / "ledger.db", private / "ticket.key"
    if treatment == "resume_preserved":
        ticket_path.write_bytes(os.urandom(80))
        ticket_path.chmod(0o600)
    rows, server_rows, gateways, logs, processes = [], [], [], [], []
    tcpdump = gateway = gateway_output = gateway_stop = counts = None
    ticket_epoch, gateway_epoch = None, -1
    restarts, drops = set(faults["restart_before"]), set(faults["drop_first_ack"])
    if capture_enabled:
        tcpdump = destination.popen(["tcpdump", "--immediate-mode", "-U", "-n", "-s", "0", "-i", interface,
            "-w", str(directory / "traffic.pcap"), "tcp", "port", str(port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        from pqc_iot_simulator.pqc_iot_sim.engines.mininet_wifi_engine import MininetWiFiEngine
        ok, detail = MininetWiFiEngine._wait_for_tcpdump_ready(tcpdump)
        if not ok:
            tcpdump.terminate()
            raise RuntimeError("capture not ready: " + detail)

    def reading_id(i):
        return hashlib.sha256(f"block={block};reading={i}".encode()).hexdigest()[:32]

    def collect_gateway():
        nonlocal counts
        gateway_stop.write_text("stop")
        if gateway.wait(timeout=20):
            raise RuntimeError("gateway failed; see server log")
        data = json.loads(gateway_output.read_text())
        server_rows.extend(data["connections"])
        counts = {k: data[k] for k in ("unique_readings", "application_effects", "duplicate_effects")}

    trial_started = time.perf_counter_ns()
    unconfirmed = []
    try:
        for reading in range(readings):
            reading_started = time.perf_counter_ns()
            startup_ms = 0.0
            if reading == 0 or reading in restarts:
                gateway_epoch += 1
                if gateway is not None:
                    collect_gateway()
                ready = private / f"ready_{reading}"
                gateway_stop = private / f"stop_{reading}"
                gateway_output = directory / f"server_{reading}.json"
                log = open(directory / f"server_{reading}.log", "w")
                logs.append(log)
                command = [sys.executable, PROBE, "server", "--host", server_ip, "--port", str(port),
                    "--credentials", str(credentials), "--ledger", str(ledger), "--ready", str(ready),
                    "--output", str(gateway_output), "--profile", profile, "--connections", "100000",
                    "--stop-file", str(gateway_stop), "--drop-reading-id", *[reading_id(i) for i in sorted(drops)]]
                if deduplicate:
                    command.append("--deduplicate")
                if treatment == "resume_preserved":
                    command.extend(["--ticket-key", str(ticket_path)])
                start = time.perf_counter_ns()
                gateway = destination.popen(command, stdout=log, stderr=subprocess.STDOUT)
                processes.append(gateway)
                gateways.append(gateway.pid)
                deadline = time.monotonic() + 15
                while not ready.exists() and gateway.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.005)
                if not ready.exists():
                    raise RuntimeError("gateway failed to start; see " + str(log.name))
                startup_ms = (time.perf_counter_ns() - start) / 1e6
            rid = reading_id(reading)
            payload = private / "reading.bin"
            payload.write_bytes(f"synthetic block={block:03} reading={reading:03}".encode())
            for retry in range(max_attempts):
                output = directory / f"client_{reading}_{retry}.json"
                command = [sys.executable, PROBE, "client", "--host", server_ip, "--port", str(port),
                    "--bind-host", client_ip, "--credentials", str(credentials), "--state", str(state),
                    "--profile", profile, "--mode", "full" if treatment == "full" else "resume",
                    "--payload", str(payload), "--reading-id", rid, "--output", str(output)]
                saved_path = state / "state"
                state_before = hashlib.sha256(saved_path.read_bytes()).hexdigest() if saved_path.exists() else None
                start = time.perf_counter_ns()
                client = station.popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                processes.append(client)
                watchdog = False
                try:
                    log, _ = client.communicate(timeout=95)
                except subprocess.TimeoutExpired:
                    watchdog = True
                    client.terminate()
                    client.communicate(timeout=5)
                    row = dict(pid=client.pid, mode="full" if treatment == "full" else "resume",
                        reading_id=rid, session_offered=treatment != "full" and state_before is not None,
                        local_state_fallback=False, acknowledged=False, resumable_session_saved=False,
                        stage="watchdog", error="client watchdog: confirmation unobserved within 95 seconds",
                        watchdog_censored=True)
                    output.write_text(json.dumps(row, indent=2))
                if not watchdog:
                    if client.returncode not in (0, 2) or not output.is_file():
                        raise RuntimeError("endpoint execution failed: " + log)
                    row = json.loads(output.read_text())
                row["process_ms"] = (time.perf_counter_ns() - start) / 1e6
                active_epoch = 0 if treatment == "resume_preserved" else gateway_epoch
                expected_offered = treatment != "full" and ticket_epoch is not None
                if bool(row["session_offered"]) != expected_offered or row["local_state_fallback"]:
                    raise RuntimeError("unexpected local ticket availability")
                if "version" in row:
                    check_tls(row, profile, expected_offered and ticket_epoch == active_epoch)
                elif row["acknowledged"]:
                    raise RuntimeError("confirmation without a verified TLS handshake")
                if "certificate verify failed" in row.get("error", "").lower():
                    raise RuntimeError("unexpected trust failure in registered valid configuration")
                if row["resumable_session_saved"] or (watchdog and saved_path.exists()
                        and hashlib.sha256(saved_path.read_bytes()).hexdigest() != state_before):
                    ticket_epoch = active_epoch
                row.update(reading=reading, retry=retry, gateway_started_ms=startup_ms if retry == 0 else 0,
                           restarted_before=reading in restarts and retry == 0)
                if row["acknowledged"]:
                    ack_ns = row["ack_monotonic_ns"]
                    if not reading_started <= ack_ns <= time.perf_counter_ns():
                        raise RuntimeError("client/controller monotonic clocks differ")
                    row["controller_reading_start_ns"] = reading_started
                    row["reading_recovery_ms"] = (ack_ns - reading_started) / 1e6
                    row["reading_observation_ms"] = row["reading_recovery_ms"]
                rows.append(row)
                if row["acknowledged"]:
                    break
            if not rows[-1]["acknowledged"]:
                unconfirmed.append(reading)
                rows[-1]["reading_observation_ms"] = (time.perf_counter_ns() - reading_started) / 1e6
        terminal_ns = rows[-1].get("ack_monotonic_ns", time.perf_counter_ns())
        sequence_ms = (terminal_ns - trial_started) / 1e6
        collect_gateway()
        received = [s for s in server_rows if s["reading_received"]]
        actual_unique = len({s["reading_id"] for s in received})
        if counts != {"unique_readings": actual_unique,
                      "application_effects": actual_unique if deduplicate else len(received),
                      "duplicate_effects": 0 if deduplicate else len(received)-actual_unique}:
            raise RuntimeError("durable application outcome mismatch")
        for row in rows:
            peers = [s for s in server_rows if s.get("client_tcp_port") == row.get("client_tcp_port")
                     and ("client_share_sha256" not in row or s.get("client_share_sha256") == row["client_share_sha256"])]
            row["injected_ack_drop"] = any(s.get("ack_dropped_after_durable_commit", False) for s in peers)
            row["unplanned_unacknowledged"] = not row["acknowledged"] and not row["injected_ack_drop"] and not row.get("watchdog_censored", False)
            if row["injected_ack_drop"] and row["acknowledged"]:
                raise RuntimeError("programmed ACK drop was acknowledged")
        if len({r["pid"] for r in rows}) != len(rows):
            raise RuntimeError("client process reused")
        negotiated = [r for r in rows if "version" in r]
        for field in ("client_share_sha256", "server_share_sha256"):
            if len({r[field] for r in negotiated}) != len(negotiated):
                raise RuntimeError("public key share reused")
        result = dict(profile=profile, treatment=treatment, deduplicate=deduplicate, block=block,
            readings=readings, fault_schedule=faults, clients=rows, servers=server_rows,
            gateway_processes=len(gateways), sequence_ms=sequence_ms, max_attempts=max_attempts,
            confirmed_readings=readings-len(unconfirmed), unconfirmed_readings=unconfirmed,
            delivery_status="complete" if not unconfirmed else "budget_exhausted",
            verified_tls_connections=len(negotiated), failed_handshake_or_watchdog_attempts=len(rows)-len(negotiated), **counts)
    finally:
        if tcpdump is not None:
            tcpdump.send_signal(signal.SIGINT)
            _, capture_log = tcpdump.communicate(timeout=10)
            (directory / "tcpdump.log").write_text(capture_log)
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)
        for log in logs:
            log.close()
    if capture_enabled:
        if "0 packets dropped by kernel" not in capture_log:
            raise RuntimeError("capture kernel drops or missing capture statistics")
        result["capture"] = tls_capture(directory / "traffic.pcap", client_ip)
        result["capture_transport_gap_flows"] = sum(any(f.get(d+"_contiguous_payload") != f.get(d+"_unique_payload")
            for d in ("tx", "rx")) for f in result["capture"]["tcp_flows"].values())
        if not all(covered_attempt(result["capture"], r, server_rows) for r in rows):
            raise RuntimeError("incomplete capture coverage")
    (directory / "case.json").write_text(json.dumps(result, indent=2))
    return result


def environment():
    def command(args):
        p = subprocess.run(args, capture_output=True, text=True)
        return {"returncode": p.returncode, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}
    return {"kernel": platform.uname()._asdict(), "python": sys.version,
            "os_release": Path("/etc/os-release").read_text(), "cpu": command(["lscpu"]),
            "memory": command(["free", "-b"]), "limits": Path("/proc/self/cgroup").read_text(),
            "mininet_wifi": command(["git", "-C", "/opt/mininet-wifi", "rev-parse", "HEAD"]),
            "tc": command(["tc", "-V"]), "openssl": command(["/opt/pqc-tls/bin/openssl", "version", "-a"]),
            "openssl_commit": Path("/opt/pqc-tls/source-commit").read_text().strip(),
            "native_module_sha256": hashlib.sha256(
                Path(__import__("_continuity_tls").__file__).read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--blocks", type=int, default=10)
    parser.add_argument("--readings", type=int, default=9)
    parser.add_argument("--phase", choices=("core", "loss", "smoke", "network_smoke"), default="core")
    parser.add_argument("--resume-from", type=Path,
                        help="Import complete blocks from an interrupted v3 campaign; rerun partial blocks whole")
    args = parser.parse_args()
    if args.blocks < 1:
        parser.error("blocks must be positive")
    schedule(args.readings, 0.25, 0.25, 0)
    args.output.mkdir(parents=True, exist_ok=False)
    initial_hashes = hashes()
    imported, complete_blocks = [], set()
    continuation = None
    if args.resume_from:
        if args.phase not in ("core", "loss"):
            parser.error("continuation requires a registered factorial phase")
        original, imported, complete_blocks = completed_blocks(
            args.resume_from, args.phase, args.blocks, args.readings, initial_hashes)
        continuation = dict(source=str(args.resume_from), original_manifest=original,
            original_manifest_sha256=hashlib.sha256((args.resume_from / "manifest.json").read_bytes()).hexdigest(),
            complete_blocks=sorted(complete_blocks), imported_cases=len(imported),
            policy="whole completed blocks retained; interrupted blocks rerun whole; original archive retained",
            case_sha256={c["case_id"]: hashlib.sha256(
                (args.resume_from / c["case_id"] / "case.json").read_bytes()).hexdigest() for c in imported})
        for c in imported:
            shutil.copytree(args.resume_from / c["case_id"], args.output / c["case_id"])
        for loss, block in complete_blocks:
            shutil.copy2(args.resume_from / f"network_loss{loss}_block{block}.json", args.output)
    if initial_hashes["experiments/continuity/native.c"] != hashlib.sha256(Path("/opt/pqc-tls/continuity/native.c").read_bytes()).hexdigest():
        raise RuntimeError("runtime built from another native source")
    design = cells(args.phase) if args.phase in ("core", "loss") else [
        (0, 1, 1, p, t, d) for p in PROFILES for t in ("full", "resume_volatile", "resume_preserved") for d in (False, True)]
    manifest = dict(started_utc=datetime.now(timezone.utc).isoformat(), source_sha256=initial_hashes,
                    continuation=continuation,
                    environment=environment(), phase=args.phase, blocks=args.blocks,
                    readings=args.readings, max_attempts_per_reading=3, client_watchdog_seconds=95,
                    planned_cases=args.blocks * len(design), design=design,
                    criteria=["bounded retries; confirmation failures retained as outcomes", "fresh public shares in every established TLS connection",
                              "exact negotiated mutual authentication profile", "expected resumption after every restart",
                              "zero duplicate effects with preserved dedup history; control effects equal actual ingestions",
                              "complete TLS byte coverage in server capture; zero kernel capture drops"],
                    measurement="block is repetition; schedule matched across comparators; packet-loss realizations not paired; no energy/physical actuator claim")
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    results = imported
    if imported:
        print(json.dumps({"imported_complete_cases": len(imported), "blocks": sorted(complete_blocks)}), flush=True)
    with tempfile.TemporaryDirectory(prefix="continuity-private-") as tmp:
        private = Path(tmp)
        for profile in PROFILES:
            provision(private / profile, profile)
        from pqc_iot_simulator.pqc_iot_sim.components.network import Network
        from pqc_iot_simulator.pqc_iot_sim.engines.mininet_wifi_engine import MininetWiFiEngine
        for loss in sorted({c[0] for c in design}):
            for block in range(args.blocks):
                if (loss, block) in complete_blocks:
                    continue
                order = [c for c in design if c[0] == loss]
                random.Random(20261018 + block).shuffle(order)
                engine = None
                try:
                    if args.phase == "smoke":
                        station = destination = LocalNode()
                        client_ip = server_ip = "127.0.0.1"
                        interface = "lo"
                        qdiscs = []
                    else:
                        network = Network(verbose=False, log_level="silent")
                        network.set_ready_topology("star", nodes=1)
                        network.create_hosts()
                        engine = MininetWiFiEngine(network, verbose=False, log_level="silent",
                                                   default_delay="2ms", default_loss=0, association_wait_seconds=5)
                        engine.build()
                        engine.start()
                        if engine.last_association_report["failed"] or len(engine.last_association_report["associated"]) != 1:
                            raise RuntimeError("Wi-Fi association failed")
                        station, destination = engine.get_mininet_node("iot_1"), engine.get_mininet_node("server_1")
                        client_ip, server_ip = engine.get_ip("iot_1"), engine.get_ip("server_1")
                        intf = destination.defaultIntf()
                        interface = intf.name
                        other = intf.link.intf1 if intf.link.intf2 is intf else intf.link.intf2
                        qdiscs = []
                        for endpoint in (intf, other):
                            error = endpoint.node.cmd(f"tc qdisc replace dev {endpoint.name} root netem limit 1000 delay 2ms loss {loss}%")
                            if error.strip():
                                raise RuntimeError("netem failed: " + error)
                            qdisc = endpoint.node.cmd(f"tc -s qdisc show dev {endpoint.name}")
                            if "netem" not in qdisc or "delay 2ms" not in qdisc:
                                raise RuntimeError("netem not applied")
                            qdiscs.append(qdisc)
                        (args.output / f"network_loss{loss}_block{block}.json").write_text(json.dumps({
                            "qdiscs": qdiscs, "server_interface": destination.cmd(f"ip -details link show {interface}"),
                            "station_interfaces": station.cmd("ip -details link show")}, indent=2))
                    for _, restart, ack, profile, treatment, dedup in order:
                        case_id = f"l{loss}_b{block}_r{restart:g}_a{ack:g}_{profile}_{treatment}_d{int(dedup)}"
                        faults = schedule(args.readings, restart, ack, block)
                        case = execute_case(station, destination, client_ip, server_ip, interface,
                                            args.output / case_id, private / case_id, private / profile,
                                            profile, treatment, dedup, faults, args.readings, block,
                                            capture_enabled=args.phase != "smoke")
                        case.update(case_id=case_id, loss_pct=loss, restart_fraction=restart, ack_fraction=ack,
                                    qdiscs=qdiscs)
                        results.append(case)
                        # Each case is recoverable even if a later execution fails. Only
                        # a complete manifest+results pair is a completed campaign.
                        (args.output / case_id / "case.json").write_text(json.dumps(case, indent=2))
                        with (args.output / "progress.jsonl").open("a") as stream:
                            stream.write(json.dumps({"completed": len(results), "case": case_id, "status": "PASS"}) + "\n")
                        print(json.dumps({"completed": len(results), "planned": manifest["planned_cases"],
                                          "case": case_id, "status": "PASS"}), flush=True)
                finally:
                    if engine is not None:
                        engine.stop()
    if hashes() != initial_hashes:
        raise RuntimeError("source changed during campaign")
    (args.output / "results.json").write_text(json.dumps({"status": "PASS", "cases": results}, indent=2))
    print(json.dumps({"status": "PASS", "cases": len(results), "output": str(args.output)}), flush=True)


if __name__ == "__main__":
    main()
