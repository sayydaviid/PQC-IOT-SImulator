"""Measure the cost of offering a valid or rejected mTLS 1.3 ticket."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import random
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from ..metadata import RunMetadata
from ..crypto.tls.credentials import provision
from ..crypto.tls.design import PROFILES, check_tls
from ..crypto.tls.capture import tls_capture
from ..crypto.tls.continuity_capture import covered_attempt
from ..crypto.tls.context_capture import capture_client_hellos
from ..control.identity_scenarios import replace_client
from .tls_chains import PROBE, certificate_sizes, topology
from .tls_continuity import environment
from .mininet_wifi_engine import MininetWiFiEngine


class ResumptionOfferEngine:
    """Separate context availability from ACK loss using matched, fresh connections.

    Every measured connection follows an identical gateway restart. The ticket
    key is either retained or replaced. A full warm-up, outside measurement,
    supplies the same authenticated ticket snapshot to the three comparators.
    No early data, lost ACK, or payload change is used to obtain an acceptance.
    """

    def __init__(self, *, output, network=None, source="iot_1", destination="server_1",
                 blocks=10, batches=(1, 10, 100), profiles=("classical", "hybrid", "pqc", "pqc_ec_client"),
                 probabilities=(0, .25, .5, .75, 1), attempts=4, payload_bytes=512, delay_ms=2,
                 validation_batches=(1,), seed=20261116):
        self.output = Path(output)
        self.network, self.source, self.destination = network, source, destination
        for name, value in (("blocks", blocks), ("attempts", attempts), ("payload_bytes", payload_bytes)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(name + " deve ser inteiro positivo")
        if payload_bytes > 4096:
            raise ValueError("payload máximo: 4096 bytes")
        self.blocks, self.attempts, self.payload_bytes = blocks, attempts, payload_bytes
        self.batches, self.profiles = tuple(batches), tuple(profiles)
        self.probabilities = tuple(probabilities)
        self.validation_batches = tuple(validation_batches)
        if not self.batches or len(set(self.batches)) != len(self.batches) or any(isinstance(n, bool) or not isinstance(n, int) or n < 1 for n in self.batches):
            raise ValueError("limites de leituras inválidos")
        if not self.profiles or len(set(self.profiles)) != len(self.profiles) or not set(self.profiles) <= set(PROFILES) | {"pqc_ec_client"}:
            raise ValueError("configurações TLS inválidas")
        if not set(self.validation_batches) <= set(self.batches) or len(set(self.validation_batches)) != len(self.validation_batches):
            raise ValueError("lotes de validação devem pertencer aos lotes medidos")
        if len(set(self.probabilities)) != len(self.probabilities) or any(isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1 or not math.isclose(p * attempts, round(p * attempts)) for p in self.probabilities):
            raise ValueError("cada probabilidade precisa corresponder a uma quantidade inteira de tentativas")
        if isinstance(delay_ms, bool) or not isinstance(delay_ms, (int, float)) or not math.isfinite(delay_ms) or delay_ms < 0:
            raise ValueError("atraso inválido")
        self.delay_ms, self.seed = delay_ms, seed

    @staticmethod
    def write(path, data):
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, indent=2) + "\n")
        temporary.replace(path)

    @staticmethod
    def wait_ready(process, ready, log):
        deadline = time.monotonic() + 20
        while not ready.exists():
            if process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("gateway não iniciou: " + log.read_text(errors="replace"))
            time.sleep(.005)

    def trial(self, *, station, gateway, cip, sip, interface, private, output, credentials,
              profile, outcome, batch, snapshot=None, key=None, capture=True):
        private.mkdir(mode=0o700)
        output.mkdir()
        base_profile = "pqc" if profile == "pqc_ec_client" else profile
        env = dict(os.environ, CONTEXT_CHAIN_ROOT="0", CONTEXT_BATCH_SERVER="1",
                   CONTEXT_SIGNATURES="mldsa44:ecdsa_secp256r1_sha256" if profile == "pqc_ec_client" else PROFILES[base_profile]["sigalgs"])
        ticket_key = private / "ticket.key"
        ticket_key.write_bytes(key if outcome != "rejected" else os.urandom(80))
        ticket_key.chmod(0o600)
        state = private / "state"
        if snapshot is not None:
            shutil.copytree(snapshot, state)
        ready, stop = private / "ready", private / "stop"
        server_output = output / "server.json"
        log_path = output / "server.log"
        processes, capture_process = [], None
        payload = private / "payload"
        payload.write_bytes(b"x" * self.payload_bytes)
        items = [{"reading_id": f"{i:032x}", "payload": str(payload)} for i in range(batch)]
        item_file = private / "items.json"
        item_file.write_text(json.dumps(items))
        try:
            with log_path.open("w") as server_log, (output / "client.log").open("w") as client_log:
                server = gateway.popen([sys.executable, PROBE, "server", "--host", sip, "--port", "39911",
                    "--credentials", str(credentials), "--profile", base_profile, "--device-id", self.source,
                    "--ledger", str(private / "ledger"), "--ready", str(ready), "--output", str(server_output),
                    "--stop-file", str(stop), "--ticket-key", str(ticket_key), "--deduplicate"],
                    env=env, stdout=server_log, stderr=subprocess.STDOUT)
                processes.append(server)
                started = time.perf_counter_ns()
                self.wait_ready(server, ready, log_path)
                startup_ms = (time.perf_counter_ns() - started) / 1e6
                if capture:
                    capture_process = gateway.popen(["tcpdump", "-B", "16384", "--immediate-mode", "-U", "-n", "-s", "0", "-i", interface,
                        "-w", str(output / "traffic.pcap"), "tcp", "port", "39911"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
                    ok, detail = MininetWiFiEngine._wait_for_tcpdump_ready(capture_process)
                    if not ok:
                        raise RuntimeError("captura não iniciou: " + detail)
                client_output = output / "client.json"
                mode = "full" if outcome == "full" else "resume"
                started = time.perf_counter_ns()
                client = station.popen([sys.executable, PROBE, "client", "--host", sip, "--port", "39911", "--bind-host", cip,
                    "--credentials", str(credentials), "--profile", base_profile, "--device-id", self.source,
                    "--state", str(state), "--mode", mode, "--output", str(client_output)],
                    env=dict(env, CONTEXT_BATCH_FILE=str(item_file)), stdout=client_log, stderr=subprocess.STDOUT)
                processes.append(client)
                returncode = client.wait(timeout=95)
                process_ms = (time.perf_counter_ns() - started) / 1e6
                if returncode or not client_output.exists():
                    raise RuntimeError("tentativa falhou: " + (output / "client.log").read_text(errors="replace"))
                row = json.loads(client_output.read_text())
                stop.write_text("stop")
                if server.wait(timeout=20) or not server_output.exists():
                    raise RuntimeError("gateway não concluiu: " + log_path.read_text(errors="replace"))
                server_data = json.loads(server_output.read_text())
            expected_reused = outcome == "accepted"
            if not row["acknowledged"] or len(row["confirmed"]) != batch or row["local_state_fallback"]:
                raise RuntimeError("leitura não confirmada ou fallback local inesperado")
            if bool(row["session_offered"]) != (outcome != "full") or bool(row["reused"]) != expected_reused:
                raise RuntimeError("caminho TLS observado difere do planejado")
            if profile != "pqc_ec_client":
                check_tls(row, base_profile, expected_reused)
            else:
                if (row["version"] != "TLSv1.3" or row["cipher"] != "TLS_AES_256_GCM_SHA384" or row["group"].lower() != "x25519mlkem768" or row["verify_result"] != 0 or row["peer_key_type"] != "ML-DSA-44"):
                    raise RuntimeError("configuração mista inválida")
                if not expected_reused and (row["certificate_verify_tx_scheme"] != 0x0403 or row["certificate_verify_rx_scheme"] != 0x0904):
                    raise RuntimeError("assinaturas do controle misto inválidas")
            if server_data["unique_readings"] != batch or server_data["application_effects"] != batch or server_data["duplicate_effects"]:
                raise RuntimeError("efeitos no banco inconsistentes")
            if not expected_reused and (len(row["wire_cert_tx_der_bytes"]) != 1 or len(row["wire_cert_rx_der_bytes"]) != 1):
                raise RuntimeError("a raiz foi transmitida")
            if any(s.get("dedup_device") != self.source for s in server_data["connections"]):
                raise RuntimeError("identidade autenticada inconsistente")
            result = dict(profile=profile, outcome=outcome, batch_size=batch, payload_bytes=self.payload_bytes,
                startup_ms=startup_ms, process_ms=process_ms, client=row,
                confirmed_readings=batch, duplicate_effects=0,
                ticket_key_preserved=outcome != "rejected", server=server_data)
        finally:
            if capture_process is not None:
                capture_process.send_signal(signal.SIGINT)
                _, capture_log = capture_process.communicate(timeout=10)
                (output / "tcpdump.log").write_text(capture_log)
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)
        if capture:
            if "0 packets dropped by kernel" not in capture_log:
                raise RuntimeError("captura com descartes")
            trace = tls_capture(output / "traffic.pcap", cip)
            if not covered_attempt(trace, row, server_data["connections"]):
                raise RuntimeError("captura incompleta")
            hellos = capture_client_hellos(output / "traffic.pcap")
            if len(hellos) != 1 or bool(hellos[0]["psk_identity_count"]) != (outcome != "full"):
                raise RuntimeError("oferta PSK difere do tráfego público")
            result.update(capture=trace, clienthello=hellos[0],
                ipv4_bytes=trace["iot_tx_ip_bytes"] + trace["iot_rx_ip_bytes"],
                capture_sha256=hashlib.sha256((output / "traffic.pcap").read_bytes()).hexdigest())
        self.write(output / "case.json", result)
        return result, state

    def run(self):
        self.output.mkdir(parents=True, exist_ok=False)
        hashes = RunMetadata.source_hashes()
        matrix = list(itertools.product(self.profiles, self.batches))
        planned = self.blocks * len(self.profiles) * (len(self.batches) * 3 + len(self.validation_batches) * len(self.probabilities) * self.attempts)
        manifest = dict(started_utc=datetime.now(timezone.utc).isoformat(), blocks=self.blocks, profiles=self.profiles,
            batches=self.batches, probabilities=self.probabilities, attempts=self.attempts,
            validation_batches=self.validation_batches,
            payload_bytes=self.payload_bytes, delay_ms=self.delay_ms, seed=self.seed,
            planned_cases=planned, source=self.source, destination=self.destination,
            source_sha256=hashes, environment=environment(), include_root=0, ack_loss_fraction=0, packet_loss_pct=0,
            measurement="one connection through final ACK, with TCP/TLS closures in IPv4; warm-up, context creation and gateway startup excluded from TCP-to-ACK; reported separately",
            ticket_snapshot="same full-handshake ticket reused as independent offer, fresh key shares, no 0-RTT",
            inference="means within block; block bootstrap; validation probabilities independent of ACK loss")
        self.write(self.output / "manifest.json", manifest)
        rows, total = [], 0
        with tempfile.TemporaryDirectory(prefix="offer-private-") as tmp:
            private = Path(tmp)
            for block in range(self.blocks):
                creds, snapshots, keys = {}, {}, {}
                for profile in self.profiles:
                    base = "pqc" if profile == "pqc_ec_client" else profile
                    credentials = private / f"credentials_b{block}_{profile}"
                    if profile == "pqc_ec_client" and "pqc" in creds:
                        shutil.copytree(creds["pqc"], credentials)
                        replace_client(credentials, "EC", self.source)
                    else:
                        provision(credentials, base, device_id=self.source)
                        if profile == "pqc_ec_client":
                            replace_client(credentials, "EC", self.source)
                    creds[profile] = credentials
                sizes = {p: certificate_sizes(c) for p, c in creds.items()}
                if "pqc" in creds and "pqc_ec_client" in creds:
                    for name in ("server", "ca"):
                        if sizes["pqc"][name]["sha256"] != sizes["pqc_ec_client"][name]["sha256"]:
                            raise RuntimeError("controle de identidade mudou servidor ou CA")
                self.write(self.output / f"certificates_block{block}.json", sizes)
                engine = None
                try:
                    engine, station, gateway, cip, sip, interface, qdiscs = topology(network=self.network,
                        source=self.source, destination=self.destination, delay_ms=self.delay_ms)
                    self.write(self.output / f"network_block{block}.json", qdiscs)
                    for profile in self.profiles:
                        keys[profile] = os.urandom(80)
                        cid = f"warmup_b{block}_{profile}"
                        warmup, state = self.trial(station=station, gateway=gateway, cip=cip, sip=sip, interface=interface,
                            private=private / cid, output=self.output / cid, credentials=creds[profile],
                            profile=profile, outcome="full", batch=1, key=keys[profile], capture=False)
                        if not warmup["client"]["resumable_session_saved"]:
                            raise RuntimeError("warm-up não produziu ticket utilizável")
                        snapshots[profile] = state
                    jobs = []
                    for profile, batch in matrix:
                        jobs.extend((profile, batch, "calibration", -1, i, outcome) for i, outcome in enumerate(("full", "accepted", "rejected")))
                        for p in self.probabilities if batch in self.validation_batches else ():
                            outcomes = ["accepted"] * round(p * self.attempts) + ["rejected"] * (self.attempts - round(p * self.attempts))
                            random.Random(f"{self.seed}/{block}/{profile}/{batch}/{p}").shuffle(outcomes)
                            jobs.extend((profile, batch, "validation", p, i, outcome) for i, outcome in enumerate(outcomes))
                    random.Random(self.seed + block).shuffle(jobs)
                    for profile, batch, kind, p, index, outcome in jobs:
                        cid = f"b{block}_{profile}_n{batch}_{kind}_p{p:g}_i{index}_{outcome}"
                        result, _ = self.trial(station=station, gateway=gateway, cip=cip, sip=sip, interface=interface,
                            private=private / cid, output=self.output / cid, credentials=creds[profile], profile=profile,
                            outcome=outcome, batch=batch, snapshot=snapshots[profile], key=keys[profile])
                        result.update(case_id=cid, block=block, sample=kind, probability=p, attempt_index=index)
                        self.write(self.output / cid / "case.json", result)
                        rows.append(result)
                        total += 1
                        with (self.output / "progress.jsonl").open("a") as f:
                            f.write(json.dumps(dict(completed=total, planned=planned, case=cid)) + "\n")
                        print(json.dumps(dict(completed=total, planned=planned, case=cid)), flush=True)
                finally:
                    if engine is not None:
                        engine.stop()
        if hashes != RunMetadata.source_hashes():
            raise RuntimeError("fontes alteradas durante a execução")
        for field in ("client_share_sha256", "server_share_sha256"):
            shares = [r["client"][field] for r in rows]
            if len(shares) != len(set(shares)):
                raise RuntimeError("compartilhamento público repetido")
        self.write(self.output / "results.json", dict(status="PASS", cases=rows))
        return self.output
