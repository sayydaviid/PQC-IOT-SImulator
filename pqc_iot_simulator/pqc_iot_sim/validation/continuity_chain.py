"""Post-hoc public chain diagnostic for the unchanged campaign TLS context.

Capture s_client output privately: never print or save session/PSK diagnostics.
Only certificate counts, public DER lengths and root inclusion are exported.
"""

import hashlib
import json
import re
import ssl
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
from pqc_iot_simulator.pqc_iot_sim.components.tls.credentials import provision
from pqc_iot_simulator.pqc_iot_sim.components.tls.design import PROBE
from pqc_iot_simulator.pqc_iot_sim.components.tls.design import PROFILES


class ContinuityChainValidation:
    """Post-hoc public chain diagnostic for the unchanged campaign TLS context.

    Configure once, then call ``run()`` from a notebook.
    """

    def __init__(self, *, output):
        self.output = Path(output) if output is not None else None

    def run(self):
        args = self
        args.output.mkdir(parents=True, exist_ok=False)
        rows = []
        with tempfile.TemporaryDirectory(prefix="continuity-chain-") as tmp:
            private = Path(tmp)
            for profile, params in PROFILES.items():
                credentials = private / profile
                provision(credentials, profile)
                (ready, outcome) = (credentials / "ready", credentials / "server.json")
                process = subprocess.Popen(
                    [
                        sys.executable,
                        PROBE,
                        "server",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "39921",
                        "--credentials",
                        str(credentials),
                        "--profile",
                        profile,
                        "--connections",
                        "1",
                        "--ready",
                        str(ready),
                        "--ledger",
                        str(credentials / "db"),
                        "--output",
                        str(outcome),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                try:
                    deadline = time.monotonic() + 15
                    while not ready.exists():
                        if process.poll() is not None or time.monotonic() > deadline:
                            raise RuntimeError(
                                "diagnostic server failed to become ready"
                            )
                        time.sleep(0.02)
                    result = subprocess.run(
                        [
                            "/opt/pqc-tls/bin/openssl",
                            "s_client",
                            "-connect",
                            "127.0.0.1:39921",
                            "-tls1_3",
                            "-servername",
                            "gateway.local",
                            "-verify_hostname",
                            "gateway.local",
                            "-verify_return_error",
                            "-CAfile",
                            str(credentials / "ca.crt"),
                            "-cert",
                            str(credentials / "client.crt"),
                            "-key",
                            str(credentials / "client.key"),
                            "-groups",
                            params["group"],
                            "-sigalgs",
                            params["sigalgs"],
                            "-ciphersuites",
                            "TLS_AES_256_GCM_SHA384",
                            "-showcerts",
                            "-no_ign_eof",
                        ],
                        input=b"",
                        capture_output=True,
                        timeout=20,
                    )
                    chain = re.findall(
                        b"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
                        result.stdout,
                        re.S,
                    )
                    ders = [ssl.PEM_cert_to_DER_cert(p.decode()) for p in chain]
                    root = ssl.PEM_cert_to_DER_cert(
                        (credentials / "ca.crt").read_text()
                    )
                    if not ders or b"Verification: OK" not in result.stdout:
                        raise RuntimeError("missing verified public certificate chain")
                    rows.append(
                        dict(
                            profile=profile,
                            certificates_sent=len(ders),
                            certificate_der_bytes=list(map(len, ders)),
                            root_sent=root in ders,
                            public_sha256=[hashlib.sha256(d).hexdigest() for d in ders],
                        )
                    )
                    process.communicate(timeout=20)
                finally:
                    if process.poll() is None:
                        process.terminate()
                        process.communicate(timeout=5)
        data = dict(
            status="PASS",
            post_hoc=True,
            note="New temporary credentials, same native context; no new cost estimate",
            source_sha256={
                name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                for name in (
                    "pqc_iot_simulator/pqc_iot_sim/validation/continuity_chain.py",
                    "pqc_iot_simulator/pqc_iot_sim/components/tls/credentials.py",
                    "pqc_iot_simulator/pqc_iot_sim/engines/native/continuity/native.c",
                    "pqc_iot_simulator/pqc_iot_sim/continuity_probe.py",
                )
            },
            checks=rows,
        )
        (args.output / "results.json").write_text(json.dumps(data, indent=2))
        print(json.dumps(data, indent=2))
        return args.output
