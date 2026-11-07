"""Create temporary ML-DSA CA and mutually authenticated endpoint credentials."""

from pathlib import Path
import os
import subprocess


def provision(directory: Path):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)

    def openssl(*args):
        result = subprocess.run(
            ["/opt/pqc-tls/bin/openssl", *map(str, args)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if result.returncode:
            raise RuntimeError("credential provisioning: " + result.stderr.decode())

    openssl("genpkey", "-algorithm", "ML-DSA-44", "-out", directory / "ca.key")
    openssl(
        "req",
        "-new",
        "-x509",
        "-key",
        directory / "ca.key",
        "-out",
        directory / "ca.crt",
        "-days",
        "2",
        "-subj",
        "/CN=PQC Research CA",
        "-addext",
        "basicConstraints=critical,CA:TRUE",
        "-addext",
        "keyUsage=critical,keyCertSign,cRLSign",
    )
    for name, common, purpose in (
        ("server", "gateway.local", "serverAuth"),
        ("client", "iot_1", "clientAuth"),
    ):
        openssl(
            "genpkey", "-algorithm", "ML-DSA-44", "-out", directory / (name + ".key")
        )
        openssl(
            "req",
            "-new",
            "-key",
            directory / (name + ".key"),
            "-out",
            directory / (name + ".csr"),
            "-subj",
            "/CN=" + common,
        )
        extensions = directory / (name + ".ext")
        extensions.write_text(
            "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage="
            + purpose
            + "\nsubjectAltName=DNS:"
            + common
            + "\n"
        )
        openssl(
            "x509",
            "-req",
            "-in",
            directory / (name + ".csr"),
            "-CA",
            directory / "ca.crt",
            "-CAkey",
            directory / "ca.key",
            "-set_serial",
            "1" if name == "server" else "2",
            "-days",
            "2",
            "-extfile",
            extensions,
            "-out",
            directory / (name + ".crt"),
        )
    (directory / "wrapping.key").write_bytes(os.urandom(32))
    for path in directory.iterdir():
        path.chmod(0o600)
