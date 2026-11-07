"""Negative identity/content checks against the real TLS endpoint."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.tls_credentials import provision  # noqa: E402
from scripts.verify_tls_baseline import PROBE  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    checks = []
    with tempfile.TemporaryDirectory(prefix="tls-security-secrets-") as name:
        private = Path(name)
        for case in (
            "wrong_client_name",
            "wrong_server_name",
            "wrong_ca",
            "conflicting_reading",
        ):
            directory = private / case
            creds = directory / "credentials"
            provision(creds)
            if case in ("wrong_client_name", "wrong_server_name"):
                leaf = "client" if case == "wrong_client_name" else "server"
                ext = creds / (leaf + ".ext")
                ext.write_text(
                    ext.read_text()
                    .replace("DNS:iot_1", "DNS:iot_2")
                    .replace("DNS:gateway.local", "DNS:impostor.local")
                )
                subprocess.run(
                    [
                        "openssl",
                        "x509",
                        "-req",
                        "-in",
                        str(creds / (leaf + ".csr")),
                        "-CA",
                        str(creds / "ca.crt"),
                        "-CAkey",
                        str(creds / "ca.key"),
                        "-set_serial",
                        "3",
                        "-days",
                        "2",
                        "-extfile",
                        str(ext),
                        "-out",
                        str(creds / (leaf + ".crt")),
                    ],
                    check=True,
                    capture_output=True,
                )
            client_creds = creds
            if case == "wrong_ca":
                client_creds = directory / "wrong-trust"
                provision(client_creds)
            payload = directory / "reading"
            payload.write_bytes(b"original reading")
            ready, ledger = directory / "ready", directory / "ledger.db"
            server_output = args.output / (case + "_server.json")
            log = open(args.output / (case + ".log"), "w")
            gateway = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    PROBE,
                    "server",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "39892",
                    "--credentials",
                    str(creds),
                    "--ledger",
                    str(ledger),
                    "--ready",
                    str(ready),
                    "--output",
                    str(server_output),
                    "--connections",
                    "2" if case == "conflicting_reading" else "1",
                    "--deduplicate",
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 10
                while (
                    not ready.exists()
                    and gateway.poll() is None
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.05)
                if not ready.exists():
                    raise RuntimeError("negative-test server failed to start")
                for attempt in range(2 if case == "conflicting_reading" else 1):
                    if attempt:
                        payload.write_bytes(b"changed reading")
                    output = args.output / f"{case}_client_{attempt}.json"
                    process = subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            PROBE,
                            "client",
                            "--host",
                            "127.0.0.1",
                            "--port",
                            "39892",
                            "--credentials",
                            str(client_creds),
                            "--state",
                            str(directory / "state"),
                            "--mode",
                            "full",
                            "--payload",
                            str(payload),
                            "--reading-id",
                            "0" * 32,
                            "--output",
                            str(output),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=25,
                    )
                    accepted = case == "conflicting_reading" and attempt == 0
                    if (
                        process.returncode != (0 if accepted else 2)
                        or not output.is_file()
                    ):
                        raise RuntimeError(
                            "unexpected negative-test process outcome: "
                            + process.stderr
                        )
                    result = json.loads(output.read_text())
                    if result["acknowledged"] != accepted:
                        raise RuntimeError("identity/content rejection failed")
                if gateway.wait(timeout=20):
                    raise RuntimeError("negative-test server failed")
                server_result = json.loads(server_output.read_text())
                expected = 1 if case == "conflicting_reading" else 0
                if (
                    server_result["application_effects"] != expected
                    or server_result["unique_readings"] != expected
                ):
                    raise RuntimeError("unauthorized/conflicting application effect")
                checks.append({"check": case, "pass": True})
            finally:
                if gateway.poll() is None:
                    gateway.terminate()
                    gateway.wait(timeout=3)
                log.close()
    (args.output / "results.json").write_text(
        json.dumps({"status": "PASS", "checks": checks}, indent=2)
    )
    print(json.dumps({"status": "PASS", "checks": len(checks)}, indent=2))


if __name__ == "__main__":
    main()
