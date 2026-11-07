"""Run real-crypto recovery faults. Results contain no credentials or plaintexts."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pqc_iot_simulator.pqc_iot_sim.components.recovery import Identity, POLICIES  # noqa: E402
from pqc_iot_simulator.pqc_iot_sim.core.recovery_experiment import (  # noqa: E402
    FAULTS,
    fault_case,
    security_gates,
    verdict,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument("--messages", type=int, default=8)
    parser.add_argument("--block-size", type=int, default=32)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.repetitions < 1 or args.messages < 1 or args.messages >= args.block_size:
        parser.error(
            "positive repetitions/messages, with messages < block-size, required"
        )
    output = args.output or ROOT / "results/raw" / (
        "recovery_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    output.mkdir(parents=True, exist_ok=False)
    paths = [
        Path(__file__),
        ROOT / "pqc_iot_simulator/pqc_iot_sim/components/recovery.py",
        ROOT / "pqc_iot_simulator/pqc_iot_sim/core/recovery_experiment.py",
    ]
    manifest = {
        "source_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths
        },
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "parameters": {
            "repetitions": args.repetitions,
            "messages": args.messages,
            "block_size": args.block_size,
        },
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("cryptography", "liboqs-python")
        },
        "clock": "logical seconds for security; host perf_counter for descriptive timing",
        "criteria_registered": [
            "negative control exposes plaintext",
            "fresh-key policies preserve uniqueness and delivery",
            "durable counter safe only with journal preserved",
            "all security gates pass",
            "PQC resume fewer framed bytes than full",
        ],
        "energy": "NOT_MEASURED",
        "timing_inference": "descriptive host timing only",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    identity, server_identity = Identity.generate(), Identity.generate()
    rows = []
    with tempfile.TemporaryDirectory(prefix="pqc-recovery-secrets-") as temporary:
        private = Path(temporary)
        key = os.urandom(32)
        checks = security_gates(private / "gates", identity, server_identity, key)
        for repetition in range(args.repetitions):
            for policy in POLICIES:
                for fault in FAULTS:
                    row = fault_case(
                        private / str(repetition) / policy / fault,
                        policy,
                        fault,
                        identity,
                        server_identity,
                        key,
                        args.messages,
                        args.block_size,
                    )
                    row["repetition"] = repetition
                    rows.append(row)
            print(
                json.dumps(
                    {"completed_repetitions": repetition + 1, "cases": len(rows)}
                ),
                flush=True,
            )
    for p in paths:
        if (
            hashlib.sha256(p.read_bytes()).hexdigest()
            != manifest["source_sha256"][str(p.relative_to(ROOT))]
        ):
            raise RuntimeError("source changed during campaign")
    result = {
        "verdict": verdict(rows, checks),
        "security_checks": checks,
        "cases": rows,
    }
    (output / "results.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({"output": str(output), **result["verdict"]}, indent=2))
    if result["verdict"]["status"] != "SUPPORTED_IN_TESTED_MODEL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
