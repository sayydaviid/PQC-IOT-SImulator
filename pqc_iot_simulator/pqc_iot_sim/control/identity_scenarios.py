"""Public size diagnostics and authenticated-device negative controls.

No private key, resumption secret, session DER or ticket contents are exported.
"""

import hashlib, json, os, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
from ..crypto.tls.credentials import provision
from ..crypto.tls.design import PROFILES
from ..runtime.tls_chains import PROBE
from ..runtime.tls_chains import certificate_sizes

OPENSSL = "/opt/pqc-tls/bin/openssl"


def openssl(*args):
    r = subprocess.run([OPENSSL, *map(str, args)], capture_output=True)
    if r.returncode:
        raise RuntimeError("openssl operation failed")
    return r.stdout


def replace_client(cred, algorithm, identity="iot_1"):
    opts = (
        ["EC", "-pkeyopt", "ec_paramgen_curve:P-256"]
        if algorithm == "EC"
        else ["ML-DSA-44"]
    )
    openssl("genpkey", "-algorithm", *opts, "-out", cred / "client.key")
    openssl(
        "req",
        "-new",
        "-key",
        cred / "client.key",
        "-out",
        cred / "client.csr",
        "-subj",
        "/CN=" + identity,
    )
    ext = cred / "client.ext"
    ext.write_text(
        "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=clientAuth\nsubjectAltName=DNS:"
        + identity
        + "\n"
    )
    openssl(
        "x509",
        "-req",
        "-in",
        cred / "client.csr",
        "-CA",
        cred / "ca.crt",
        "-CAkey",
        cred / "ca.key",
        "-set_serial",
        "2",
        "-days",
        "2",
        "-extfile",
        ext,
        "-out",
        cred / "client.crt",
    )


def wait_ready(process, path):
    deadline = time.monotonic() + 15
    while not path.exists():
        if process.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError("server not ready")
        time.sleep(0.01)


def run_case(
    private, profile, root, client_key=None, identity="iot_1", shared_credentials=None
):
    private.mkdir()
    cred = shared_credentials or private / "credentials"
    if shared_credentials is None:
        provision(cred, profile)
    if client_key or identity != "iot_1":
        replace_client(cred, client_key or PROFILES[profile]["key_type"], identity)
    ticket = private / "stek"
    ticket.write_bytes(os.urandom(80))
    payload = private / "payload"
    payload.write_bytes(b"diagnostic telemetry")
    ready = private / "ready"
    out = private / "server.json"
    log = private / "server.log"
    env = dict(
        os.environ,
        CONTEXT_CHAIN_ROOT=str(root),
        CONTEXT_SIGNATURES="mldsa44:ecdsa_secp256r1_sha256",
    )
    with log.open("w") as stream:
        server = subprocess.Popen(
            [
                sys.executable,
                PROBE,
                "server",
                "--host",
                "127.0.0.1",
                "--port",
                "39921",
                "--credentials",
                str(cred),
                "--profile",
                profile,
                "--ledger",
                str(private / "db"),
                "--ready",
                str(ready),
                "--connections",
                "3" if identity == "iot_1" else "1",
                "--ticket-key",
                str(ticket),
                "--deduplicate",
                "--output",
                str(out),
            ],
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
        clients = []
        try:
            wait_ready(server, ready)
            for i in range(3 if identity == "iot_1" else 1):
                cout = private / f"client{i}.json"
                r = subprocess.run(
                    [
                        sys.executable,
                        PROBE,
                        "client",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "39921",
                        "--credentials",
                        str(cred),
                        "--profile",
                        profile,
                        "--state",
                        str(private / "state"),
                        "--mode",
                        "resume",
                        "--payload",
                        str(payload),
                        "--reading-id",
                        f"{i:032x}",
                        "--output",
                        str(cout),
                    ],
                    env=env,
                    capture_output=True,
                    timeout=30,
                )
                if r.returncode not in (0, 2) or not cout.exists():
                    raise RuntimeError("client diagnostic failed")
                clients.append(json.loads(cout.read_text()))
            if server.wait(timeout=20):
                raise RuntimeError("server diagnostic failed: " + log.read_text())
        finally:
            if server.poll() is None:
                server.kill()
                server.wait()
    s = json.loads(out.read_text())
    pub = certificate_sizes(cred)
    for name in pub:
        pem = openssl("x509", "-in", cred / (name + ".crt"), "-pubkey", "-noout")
        pub[name]["spki_der_bytes"] = len(
            subprocess.check_output(
                [OPENSSL, "pkey", "-pubin", "-outform", "DER"],
                input=pem,
                stderr=subprocess.DEVNULL,
            )
        )
    return {
        "profile": profile,
        "include_root": root,
        "client_key": client_key or PROFILES[profile]["key_type"],
        "client_identity": identity,
        "certificates": pub,
        "clients": clients,
        "server": s,
    }


class IdentityScenarios:
    """Public size diagnostics and authenticated-device negative controls.

    Configure once, then call ``run()`` from a notebook.
    """

    def __init__(self, *, output):
        self.output = Path(output) if output is not None else None

    def run(self):
        args = self
        args.output.mkdir(parents=True, exist_ok=False)
        rows = []
        with tempfile.TemporaryDirectory(prefix="ticket-diagnostics-private-") as tmp:
            base = Path(tmp)
            for profile in PROFILES:
                for root in [-1, 0, 1]:
                    row = run_case(base / f"{profile}_{root}", profile, root)
                    rows.append(row)
                    assert all((c["acknowledged"] for c in row["clients"]))
                    assert [c["reused"] for c in row["clients"]] == [0, 1, 1]
                    expected = 1 if root == 0 else 2
                    assert (
                        len(row["clients"][0]["wire_cert_tx_der_bytes"])
                        == len(row["clients"][0]["wire_cert_rx_der_bytes"])
                        == expected
                    )
                    assert all(
                        (
                            s["dedup_device"] == "iot_1"
                            for s in row["server"]["connections"]
                        )
                    )
            mixed = base / "mixed_credentials"
            provision(mixed, "pqc")
            for key in ["EC", "ML-DSA-44"]:
                row = run_case(
                    base / f"mixed_{key}",
                    "pqc",
                    0,
                    client_key=key,
                    shared_credentials=mixed,
                )
                rows.append(row)
            assert (
                rows[-1]["certificates"]["server"]["sha256"]
                == rows[-2]["certificates"]["server"]["sha256"]
            )
            assert (
                rows[-1]["certificates"]["ca"]["sha256"]
                == rows[-2]["certificates"]["ca"]["sha256"]
            )
            wrong = run_case(base / "wrong_identity", "pqc", 0, identity="iot_2")
            rows.append(wrong)
            assert not wrong["clients"][0]["acknowledged"]
            assert (
                wrong["server"]["application_effects"]
                == wrong["server"]["unique_readings"]
                == 0
            )
        data = {
            "status": "PASS",
            "diagnostics": rows,
            "limits": "Localhost diagnostic, separate from Mininet cost samples. Only public sizes/identities; all private credentials, sessions and ticket keys removed.",
            "sources": {
                f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest()
                for f in [
                    "pqc_iot_simulator/pqc_iot_sim/control/identity_scenarios.py",
                    "pqc_iot_simulator/pqc_iot_sim/runtime/native/context_costs/native.c",
                    "pqc_iot_simulator/pqc_iot_sim/runtime/endpoints/session.py",
                ]
            },
        }
        (args.output / "results.json").write_text(json.dumps(data, indent=2))
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "cases": len(rows),
                    "valid_other_identity_rejected": True,
                }
            )
        )
        return args.output
