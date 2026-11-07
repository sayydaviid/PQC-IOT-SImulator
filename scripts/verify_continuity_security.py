"""Negative controls for stateless tickets, trust and application conflicts."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import _continuity_tls as native
from scripts.continuity_credentials import provision
from scripts.continuity_design import PROFILES, PROBE, check_tls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    checks = []
    with tempfile.TemporaryDirectory(prefix="continuity-negative-") as tmp:
        root = Path(tmp)
        for profile, parameters in PROFILES.items():
            credentials, rogue = root / profile, root / (profile + "-untrusted")
            provision(credentials, profile)
            provision(rogue, profile)
            try:
                native.context(str(credentials / "server.crt"), str(credentials / "server.key"),
                               str(credentials / "ca.crt"), parameters["group"], 1,
                               parameters["sigalgs"], b"truncated-key")
            except ValueError:
                checks.append(profile + ":invalid_ticket_key_rejected")
            else:
                raise RuntimeError("invalid STEK length accepted")
            for negative in ("untrusted_ca", "content_conflict", "tampered_checkpoint"):
                private = root / (profile + negative)
                private.mkdir()
                directory = args.output / (profile + "_" + negative)
                directory.mkdir()
                ready = private / "ready"
                server_output = directory / "server.json"
                log = open(directory / "server.log", "w")
                connections = 1 if negative == "untrusted_ca" else 2
                gateway = subprocess.Popen([sys.executable, PROBE, "server", "--host", "127.0.0.1",
                    "--port", "39912", "--credentials", str(credentials), "--profile", profile,
                    "--ledger", str(private / "ledger.db"), "--ready", str(ready), "--output", str(server_output),
                    "--connections", str(connections), "--deduplicate"], stdout=log, stderr=subprocess.STDOUT)
                try:
                    deadline = time.monotonic() + 10
                    while not ready.exists() and gateway.poll() is None and time.monotonic() < deadline:
                        time.sleep(0.01)
                    if not ready.exists():
                        raise RuntimeError("negative-control gateway did not start")
                    for i in range(connections):
                        payload = private / "reading"
                        payload.write_bytes(b"conflicting-content" if negative == "content_conflict" and i == 1 else b"same-reading")
                        if negative == "tampered_checkpoint" and i == 1:
                            checkpoint = private / "state" / "state"
                            value = bytearray(checkpoint.read_bytes())
                            value[len(value)//2] ^= 1
                            checkpoint.write_bytes(value)
                        output = directory / f"client_{i}.json"
                        result = subprocess.run([sys.executable, PROBE, "client", "--host", "127.0.0.1",
                            "--port", "39912", "--credentials", str(rogue if negative == "untrusted_ca" else credentials),
                            "--profile", profile, "--state", str(private / "state"), "--payload", str(payload),
                            "--reading-id", "a"*32, "--mode", "resume", "--output", str(output)],
                            capture_output=True, text=True, timeout=25)
                        if not output.exists():
                            raise RuntimeError("negative client failed without result: " + result.stderr)
                        row = json.loads(output.read_text())
                        if negative == "untrusted_ca" or (negative == "content_conflict" and i == 1):
                            if result.returncode != 2 or row["acknowledged"]:
                                raise RuntimeError("invalid identity or conflicting reading accepted")
                        else:
                            if result.returncode or not row["acknowledged"]:
                                raise RuntimeError("valid recovery failed")
                            check_tls(row, profile, False if negative == "tampered_checkpoint" else None)
                            if negative == "tampered_checkpoint" and i == 1 and not row["local_state_fallback"]:
                                raise RuntimeError("tampered checkpoint was not rejected")
                    if gateway.wait(timeout=10):
                        raise RuntimeError("negative gateway crashed")
                    server = json.loads(server_output.read_text())
                    expected = 0 if negative == "untrusted_ca" else 1
                    if server["unique_readings"] != expected or server["application_effects"] != expected:
                        raise RuntimeError("unexpected effects after negative test")
                    checks.append(profile + ":" + negative)
                finally:
                    if gateway.poll() is None:
                        gateway.terminate()
                        gateway.wait(timeout=5)
                    log.close()
    sources = ["experiments/continuity/native.c", "pqc_iot_simulator/pqc_iot_sim/continuity_probe.py",
               "scripts/verify_continuity_security.py", "scripts/continuity_credentials.py"]
    result = {"status": "PASS", "checks": checks,
              "source_sha256": {n: hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sources}}
    (args.output / "results.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({"status": "PASS", "checks": len(checks)}), flush=True)


if __name__ == "__main__":
    main()
