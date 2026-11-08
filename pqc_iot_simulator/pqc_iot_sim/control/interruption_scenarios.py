"""Run phase-2 recovery transitions and report wasted handshake bytes."""

from __future__ import annotations
from ..metadata import RunMetadata
import csv
import hashlib
import importlib.metadata
import json
import os
import statistics
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
from ..crypto.session import Identity
from ..crypto.session import MODES
from ..crypto.session import SealedStore
from .interruption_model import SCENARIOS
from .interruption_model import assess
from .interruption_model import transition_case


class RecoveryTransitionScenario:
    """Run phase-2 recovery transitions and report wasted handshake bytes.

    Configure once, then call ``run()`` from a notebook.
    """

    def __init__(self, *, repetitions=10, output=None, report=None):
        self.repetitions = repetitions
        if self.repetitions < 1:
            raise ValueError("repetitions must be positive")
        self.output = Path(output) if output is not None else None
        self.report = Path(report) if report is not None else None

    def run(self):
        args = self
        if args.repetitions < 1:
            raise ValueError("positive repetitions required")
        output = args.output or ROOT / "results/raw" / (
            "recovery_transitions_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        )
        output.mkdir(parents=True, exist_ok=False)
        sources = RunMetadata.source_files()
        manifest = {
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "source_sha256": RunMetadata.source_hashes(),
            "parameters": {
                "repetitions": args.repetitions,
                "scenarios": list(SCENARIOS),
                "policies": list(MODES),
            },
            "packages": {
                p: importlib.metadata.version(p)
                for p in ("cryptography", "liboqs-python")
            },
            "criteria_registered": [
                "zero nonce reuses",
                "no stale epoch accepted",
                "reading eventually delivered with one bounded fault",
                "lost reading ACK permits application duplicates without a dedup ledger",
                "corruption/unknown roots counted as full fallbacks",
            ],
            "cost_hypothesis": "assess rather than require universal PQC byte savings, including rejected and lost flights",
            "clock": "logical seconds; no inference about network latency or energy",
            "transport": "in-process logical fault boundary; real PQC and encrypted files",
        }
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
        (identity, server) = (Identity.generate(), Identity.generate())
        rows = []
        with tempfile.TemporaryDirectory(prefix="pqc-transition-secrets-") as temporary:
            key = os.urandom(32)
            for repetition in range(args.repetitions):
                for scenario in SCENARIOS:
                    for policy in MODES[repetition % 3 :] + MODES[: repetition % 3]:
                        store = SealedStore(
                            Path(temporary) / str(repetition) / scenario / policy, key
                        )
                        row = transition_case(store, policy, scenario, identity, server)
                        row["repetition"] = repetition
                        rows.append(row)
                print(
                    json.dumps(
                        {"repetitions_completed": repetition + 1, "cases": len(rows)}
                    ),
                    flush=True,
                )
        for path in sources:
            if (
                hashlib.sha256(path.read_bytes()).hexdigest()
                != manifest["source_sha256"][str(path.relative_to(ROOT))]
            ):
                raise RuntimeError("source changed during campaign")
        assessment = assess(rows)
        (output / "results.json").write_text(
            json.dumps({"assessment": assessment, "cases": rows}, indent=2)
        )
        summary = []
        for scenario in SCENARIOS:
            comparison = [
                c for c in assessment["byte_comparisons"] if c["scenario"] == scenario
            ]
            pqc = [
                r
                for r in rows
                if r["scenario"] == scenario and r["policy"] == "pqc_resume"
            ]
            summary.append(
                {
                    "scenario": scenario,
                    "full_median_bytes": statistics.median(
                        (c["full_bytes"] for c in comparison)
                    ),
                    "pqc_median_bytes": statistics.median(
                        (c["pqc_bytes"] for c in comparison)
                    ),
                    "pqc_median_saving_pct": statistics.median(
                        (c["pqc_saving_pct"] for c in comparison)
                    ),
                    "pqc_full_fallbacks": sum((r["full_fallback"] for r in pqc)),
                    "pqc_application_duplicates": sum(
                        (r["application_duplicates"] for r in pqc)
                    ),
                }
            )
        with (output / "summary.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
            writer.writeheader()
            writer.writerows(summary)
        if args.report:
            table = "\n".join(
                (
                    f"| `{s['scenario']}` | {s['full_median_bytes']:g} | {s['pqc_median_bytes']:g} | {s['pqc_median_saving_pct']:.2f}% | {s['pqc_full_fallbacks']} | {s['pqc_application_duplicates']} |"
                    for s in summary
                )
            )
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                f"# Fase 2: interrupções de retomada e confirmação perdida\n\nEstado: **{assessment['status']}** nos critérios de segurança e recuperação registrados. Foram executados **{len(rows)} casos** ({args.repetitions} repetições × 11 cenários × 3 políticas), com ML-KEM/ML-DSA reais e arquivos de estado cifrados. É uma injeção lógica de falhas; não mede perda de pacotes, tempo de ESP32 ou energia.\n\nO critério de recuperar a leitura refere-se a um único evento de falha, seguido de tentativa sem novas falhas. Não garante disponibilidade diante de interrupção contínua. As políticas da fase 1 e seus fontes criptográficos foram mantidos.\n\n| Ponto de falha | Bytes: completo | Bytes: retomada ML-KEM | Economia ML-KEM | Fallbacks completos ML-KEM | Duplicações na aplicação ML-KEM |\n|---|---:|---:|---:|---:|---:|\n{table}\n\nOs bytes acumulam as mensagens enquadradas do primeiro handshake e das novas tentativas, inclusive confirmação perdida e pedido de retomada rejeitado. O bootstrap, os registros de leitura e cabeçalhos IP ficam fora desta comparação. O pedido rejeitado não inclui mensagem de erro na rede, ausente neste transporte de teste.\n\n**“Retomada ML-KEM sempre usa menos bytes” = {assessment['pqc_always_smaller']}.** Quando a raiz desaparece do gateway, a tentativa de retomada falha e acrescenta custo ao estabelecimento completo. A redução de bytes depende de contexto retomável disponível. O controle de ACK perdido demonstra que proteção contra replay criptográfico não fornece deduplicação da aplicação: a mesma leitura pode ser aceita novamente em uma sessão nova, embora o par chave/nonce seja diferente.\n\nInvariantes verificados: {json.dumps(assessment['criteria'], ensure_ascii=False)}. A duplicação é um controle negativo esperado da aplicação sem ledger de IDs; não indica reutilização de nonce. Toda leitura final é comparada ao conteúdo decifrado pelo gateway. Os checkpoints das políticas de chave nova persistem somente a raiz de retomada.\n\nDados: `{output}`; SHA-256 de results.json: `{hashlib.sha256((output / 'results.json').read_bytes()).hexdigest()}`. Manifesto e CSV agregado ficam no mesmo diretório. Segredos e checkpoints experimentais são temporários e apagados; o resultado não exporta chaves ou plaintexts.\n\nPróxima avaliação: baseline padronizado e mensagens efetivas em rede com interrupções controladas, contagem dos pedidos rejeitados e identificação persistente de leituras. Esta campanha ainda não estabelece novidade frente a protocolos existentes.\n"
            )
        print(
            json.dumps(
                {
                    "output": str(output),
                    "status": assessment["status"],
                    "pqc_always_smaller": assessment["pqc_always_smaller"],
                },
                indent=2,
            )
        )
        if assessment["status"] != "PASS":
            raise SystemExit(1)
        return output
