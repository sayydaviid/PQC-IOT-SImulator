"""Registered design and invariants shared by runner, probe and tests."""

import hashlib
import itertools
import random
from pathlib import Path

PROFILES = {
    "classical": {
        "group": "X25519",
        "sigalgs": "ecdsa_secp256r1_sha256",
        "key_type": "EC",
        "signature_code": 0x0403,
    },
    "hybrid": {
        "group": "X25519MLKEM768",
        "sigalgs": "ecdsa_secp256r1_sha256",
        "key_type": "EC",
        "signature_code": 0x0403,
    },
    "pqc": {
        "group": "X25519MLKEM768",
        "sigalgs": "mldsa44",
        "key_type": "ML-DSA-44",
        "signature_code": 0x0904,
    },
}
TREATMENTS = ("full", "resume_volatile", "resume_preserved")
FREQUENCIES = (0, 0.25, 1)
PROBE = str(
    Path(__file__).resolve().parents[4]
    / "pqc_iot_simulator/pqc_iot_sim/continuity_probe.py"
)


def schedule(readings, restart_fraction, ack_fraction, block, seed=20261018):
    """One initial reading, faults on exactly sampled eligible subsequent readings.

    Matched across TLS profiles/treatments/dedup. Independent restart/ACK draws.
    Overlap is allowed and recorded. This is not a paired kernel-loss realization.
    """
    if readings < 5 or (readings - 1) % 4:
        raise ValueError("readings must be 1 plus a positive multiple of four")
    masks = []
    for label, fraction in (("restart", restart_fraction), ("ack", ack_fraction)):
        if fraction not in FREQUENCIES:
            raise ValueError("unsupported fault frequency")
        material = f"{seed}/{block}/{label}"
        rng = random.Random(int(hashlib.sha256(material.encode()).hexdigest(), 16))
        population = list(range(1, readings))
        rng.shuffle(population)
        masks.append(sorted(population[: round(fraction * len(population))]))
    return {"restart_before": masks[0], "drop_first_ack": masks[1]}


def cells(phase):
    if phase == "core":
        return list(
            itertools.product(
                (0,), FREQUENCIES, FREQUENCIES, PROFILES, TREATMENTS, (False, True)
            )
        )
    if phase == "loss":
        return list(
            itertools.product((1, 5), (0.25,), (0.25,), PROFILES, TREATMENTS, (True,))
        )
    raise ValueError("unknown campaign phase")


def check_tls(row, profile, reused=None):
    p = PROFILES[profile]
    if (
        row.get("version") != "TLSv1.3"
        or row.get("cipher") != "TLS_AES_256_GCM_SHA384"
        or row.get("group", "").lower() != p["group"].lower()
        or row.get("verify_result") != 0
        or row.get("peer_key_type") != p["key_type"]
        or not row.get("client_share_sha256")
        or not row.get("server_share_sha256")
    ):
        raise RuntimeError("TLS profile/identity/share verification failed")
    if reused is not None and bool(row["reused"]) != reused:
        raise RuntimeError(f"expected resumption={reused}, observed {row['reused']}")
    if not row["reused"] and (
        row["certificate_verify_tx_scheme"] != p["signature_code"]
        or row["certificate_verify_rx_scheme"] != p["signature_code"]
    ):
        raise RuntimeError("unexpected mutual CertificateVerify signature scheme")
