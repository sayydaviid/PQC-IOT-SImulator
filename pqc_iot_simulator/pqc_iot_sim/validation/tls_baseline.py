"""Validate native PQC TLS, sealed session restart and application durability."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
from pqc_iot_simulator.pqc_iot_sim.components.tls.baseline_credentials import provision  # noqa: E402

PROBE = "pqc_iot_simulator.pqc_iot_sim.tls_probe"


def check_tls(row, reused=None):
    if (
        row.get("version") != "TLSv1.3"
        or row.get("cipher") != "TLS_AES_256_GCM_SHA384"
        or row.get("group") != "X25519MLKEM768"
        or row.get("verify_result") != 0
    ):
        raise RuntimeError("unexpected negotiated TLS parameters: " + json.dumps(row))
    if (
        row.get("peer_key_type") != "ML-DSA-44"
        or not row.get("client_share_sha256")
        or not row.get("server_share_sha256")
    ):
        raise RuntimeError("missing PQ identity/fresh asymmetric share evidence")
    if reused is not None and bool(row["reused"]) != reused:
        raise RuntimeError(
            "resumption/full handshake expectation failed: " + json.dumps(row)
        )
    if not row["reused"] and not (
        row["certificate_verify_tx_scheme"] and row["certificate_verify_rx_scheme"]
    ):
        raise RuntimeError("mutual full authentication not observed")


class TLSBaselineValidation:
    """Validate native PQC TLS, sealed session restart and application durability.

    Configure once, then call ``run()`` from a notebook.
    """

    def __init__(self, *, output):
        self.output = Path(output) if output is not None else None

    def run(self):
        args = self
        args.output.mkdir(parents=True, exist_ok=False)
        sources = [
            ROOT / "pqc_iot_simulator/pqc_iot_sim/engines/native/tls/native.c",
            ROOT / "pqc_iot_simulator/pqc_iot_sim/tls_probe.py",
            ROOT / "pqc_iot_simulator/pqc_iot_sim/components/reading_ledger.py",
            Path(__file__),
            ROOT
            / "pqc_iot_simulator/pqc_iot_sim/components/tls/baseline_credentials.py",
        ]
        hashes = {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sources
        }
        manifest = {
            "source_sha256": hashes,
            "openssl": subprocess.check_output(
                ["openssl", "version"], text=True
            ).strip(),
            "openssl_commit": Path("/opt/pqc-tls/source-commit").read_text().strip(),
            "native_source_sha256": hashlib.sha256(
                Path("/opt/pqc-tls/native/native.c").read_bytes()
            ).hexdigest(),
            "criteria": [
                "TLS1.3 with verified ML-DSA mutual auth",
                "X25519MLKEM768 share in every connection",
                "sealed DER restored in new process",
                "real resumption",
                "new shares after process restart",
                "ACK-loss idempotence survives gateway process restart",
            ],
        }
        if (
            hashes["pqc_iot_simulator/pqc_iot_sim/engines/native/tls/native.c"]
            != manifest["native_source_sha256"]
        ):
            raise RuntimeError("native TLS module built from different source")
        (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2))
        rows = []
        with tempfile.TemporaryDirectory(prefix="tls-baseline-secrets-") as name:
            private = Path(name)
            provision(private / "credentials")
            payload = private / "reading"
            payload.write_bytes(b"synthetic calibrated-free reading")
            (ledger, ready) = (private / "ledger.db", private / "ready")
            (credentials, state) = (private / "credentials", private / "state")
            for phase, connections, drop in ((0, 3, 1), (1, 1, -1)):
                ready.unlink(missing_ok=True)
                server_log = open(args.output / f"server_{phase}.log", "w")
                server_output = args.output / f"server_{phase}.json"
                gateway = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        PROBE,
                        "server",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "39891",
                        "--credentials",
                        str(credentials),
                        "--ledger",
                        str(ledger),
                        "--ready",
                        str(ready),
                        "--output",
                        str(server_output),
                        "--connections",
                        str(connections),
                        "--drop-ack",
                        str(drop),
                        "--deduplicate",
                    ],
                    stdout=server_log,
                    stderr=subprocess.STDOUT,
                )
                try:
                    deadline = time.monotonic() + 10
                    while (
                        not ready.exists()
                        and gateway.poll() is None
                        and (time.monotonic() < deadline)
                    ):
                        time.sleep(0.05)
                    if not ready.exists():
                        raise RuntimeError("TLS server did not become ready")
                    for boot in range(connections):
                        index = len(rows)
                        rid = ("0" if index == 0 else "1") * 32
                        output = args.output / f"client_{index}.json"
                        result = subprocess.run(
                            [
                                sys.executable,
                                "-m",
                                PROBE,
                                "client",
                                "--host",
                                "127.0.0.1",
                                "--port",
                                "39891",
                                "--credentials",
                                str(credentials),
                                "--state",
                                str(state),
                                "--payload",
                                str(payload),
                                "--reading-id",
                                rid,
                                "--mode",
                                "full" if index == 0 else "resume",
                                "--output",
                                str(output),
                            ],
                            capture_output=True,
                            text=True,
                            timeout=25,
                        )
                        if result.returncode not in (0, 2) or not output.is_file():
                            raise RuntimeError(
                                "TLS client failed: " + result.stdout + result.stderr
                            )
                        row = json.loads(output.read_text())
                        check_tls(row, reused=index == 1 if index != 2 else None)
                        if row["acknowledged"] != (index != 1):
                            raise RuntimeError("unexpected ACK outcome")
                        rows.append(row)
                    if gateway.wait(timeout=20):
                        raise RuntimeError("TLS gateway failed")
                finally:
                    if gateway.poll() is None:
                        gateway.terminate()
                        gateway.wait(timeout=3)
                    server_log.close()
            if (
                len({r["pid"] for r in rows}) != len(rows)
                or len({r["client_share_sha256"] for r in rows}) != len(rows)
                or len({r["server_share_sha256"] for r in rows}) != len(rows)
            ):
                raise RuntimeError("TLS processes or key shares were reused")
            summary = json.loads((args.output / "server_1.json").read_text())
            if (
                summary["unique_readings"] != 2
                or summary["application_effects"] != 2
                or summary["duplicate_effects"] != 0
            ):
                raise RuntimeError("application idempotence lost across restart")
        for p in sources:
            if (
                hashlib.sha256(p.read_bytes()).hexdigest()
                != hashes[str(p.relative_to(ROOT))]
            ):
                raise RuntimeError("source changed during TLS validation")
        (args.output / "results.json").write_text(
            json.dumps({"status": "PASS", "clients": rows, "ledger": summary}, indent=2)
        )
        print(
            json.dumps(
                {"status": "PASS", "clients": len(rows), "output": str(args.output)},
                indent=2,
            )
        )
        return args.output
