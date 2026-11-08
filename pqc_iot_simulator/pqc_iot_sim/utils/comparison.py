"""Compare independently measured repetitions with the article's reference data.

Numerical equality and replication of the experimental findings are reported
separately. No tolerance is chosen to turn differences into agreement.
"""

from __future__ import annotations
import csv
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from .resources import DATA

ROOT = Path(__file__).resolve().parents[3]


class ArticleReproductionAudit:
    """Produce the comparison without changing the article or its reference files."""

    @staticmethod
    def read_csv(path):
        with Path(path).open(newline="") as handle:
            return list(csv.DictReader(handle))

    @staticmethod
    def canonical(value):
        text = str(value)
        try:
            return str(Decimal(text).normalize())
        except InvalidOperation:
            return text.lower()

    @staticmethod
    def selected(rows, **where):
        matches = [
            r
            for r in rows
            if all(
                (
                    ArticleReproductionAudit.canonical(r[k])
                    == ArticleReproductionAudit.canonical(v)
                    for (k, v) in where.items()
                )
            )
        ]
        if len(matches) != 1:
            raise ValueError(f"expected one condition {where}, found {len(matches)}")
        return matches[0]

    def __init__(self, *, directory, output):
        self.directory = Path(directory)
        self.output = Path(output)

    def run(self):
        self.output.mkdir(parents=True, exist_ok=False)
        reference_context = DATA / "context"
        reference_continuity = DATA / "continuity"
        context = self.directory / "context_analysis"
        continuity = self.directory / "continuity_analysis"
        specs = [
            (
                "chain_costs",
                reference_context,
                context,
                "cadeias_custos_absolutos.csv",
                [
                    "restart_fraction",
                    "ack_fraction",
                    "profile",
                    "include_root",
                    "treatment",
                ],
                [
                    "median_ipv4_bytes_per_confirmed_reading",
                    "median_ms_per_reading",
                    "median_full_handshakes",
                    "median_resumed_handshakes",
                ],
            ),
            (
                "chain_comparisons",
                reference_context,
                context,
                "cadeias_comparacoes_mesma_repeticao.csv",
                [
                    "restart_fraction",
                    "ack_fraction",
                    "profile",
                    "include_root",
                    "treatment",
                ],
                ["median_savings_pct", "median_ms_difference_per_reading"],
            ),
            (
                "amortization_costs",
                reference_context,
                context,
                "amortizacao_custos_absolutos.csv",
                ["recovery", "batch_size", "profile", "treatment"],
                [
                    "median_ipv4_bytes_per_confirmed_reading",
                    "median_ms_per_reading",
                    "median_full_handshakes",
                    "median_resumed_handshakes",
                ],
            ),
            (
                "amortization_comparisons",
                reference_context,
                context,
                "amortizacao_comparacoes_mesma_repeticao.csv",
                ["recovery", "batch_size", "profile", "treatment"],
                ["median_savings_pct", "median_ms_difference_per_reading"],
            ),
            (
                "continuity_costs",
                reference_continuity,
                continuity,
                "medianas.csv",
                [
                    "phase",
                    "loss_pct",
                    "restart_fraction",
                    "ack_fraction",
                    "profile",
                    "deduplicate",
                    "treatment",
                ],
                [
                    "median_ipv4_bytes_per_reading",
                    "median_mean_sequence_ms_per_reading",
                    "median_full_handshakes",
                    "median_resumed_handshakes",
                ],
            ),
            (
                "continuity_comparisons",
                reference_continuity,
                continuity,
                "contrastes_pareados.csv",
                [
                    "phase",
                    "loss_pct",
                    "restart_fraction",
                    "ack_fraction",
                    "profile",
                    "deduplicate",
                    "treatment",
                ],
                ["median_paired_saving_pct", "median_paired_time_delta_ms"],
            ),
        ]
        (differences, inputs) = ([], {})
        for experiment, old_dir, new_dir, filename, keys, metrics in specs:
            (old_path, new_path) = (old_dir / filename, new_dir / filename)
            for path in (old_path, new_path):
                inputs[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
            (old, new) = (
                ArticleReproductionAudit.read_csv(old_path),
                ArticleReproductionAudit.read_csv(new_path),
            )

            def index(rows):
                result = {}
                for row in rows:
                    key = tuple(
                        (ArticleReproductionAudit.canonical(row[k]) for k in keys)
                    )
                    if key in result:
                        raise ValueError("duplicated condition in " + experiment)
                    result[key] = row
                return result

            (original, repeated) = (index(old), index(new))
            if original.keys() != repeated.keys():
                raise ValueError("experimental conditions differ in " + experiment)
            for key in original:
                for metric in metrics:
                    (left, right) = (original[key][metric], repeated[key][metric])
                    (a, b) = (
                        float(left) if left else None,
                        float(right) if right else None,
                    )
                    differences.append(
                        {
                            "experiment": experiment,
                            "condition": json.dumps(
                                dict(zip(keys, key)), sort_keys=True
                            ),
                            "metric": metric,
                            "reference": a,
                            "new": b,
                            "difference": b - a
                            if a is not None and b is not None
                            else None,
                            "relative_difference_pct": 100 * (b / a - 1)
                            if a and b is not None
                            else None,
                            "same_at_two_decimals": round(a, 2) == round(b, 2)
                            if a is not None and b is not None
                            else a == b,
                        }
                    )
        with (self.output / "comparacao_completa.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(differences[0]))
            writer.writeheader()
            writer.writerows(differences)
        chains = ArticleReproductionAudit.read_csv(
            context / "cadeias_custos_absolutos.csv"
        )
        chain_pct = ArticleReproductionAudit.read_csv(
            context / "cadeias_comparacoes_mesma_repeticao.csv"
        )
        amort = ArticleReproductionAudit.read_csv(
            context / "amortizacao_custos_absolutos.csv"
        )
        amort_pct = ArticleReproductionAudit.read_csv(
            context / "amortizacao_comparacoes_mesma_repeticao.csv"
        )
        comparisons = []
        for label, rows, where, metric, digits in [
            (
                "Cadeias: completo PQC sem raiz, falhas 100%",
                chains,
                dict(
                    profile="pqc",
                    include_root=0,
                    restart_fraction=1,
                    ack_fraction=1,
                    treatment="full",
                ),
                "median_ipv4_bytes_per_confirmed_reading",
                0,
            ),
            (
                "Cadeias: contexto perdido PQC sem raiz, falhas 100%",
                chains,
                dict(
                    profile="pqc",
                    include_root=0,
                    restart_fraction=1,
                    ack_fraction=1,
                    treatment="resume_volatile",
                ),
                "median_ipv4_bytes_per_confirmed_reading",
                0,
            ),
            (
                "Cadeias: contexto preservado PQC sem raiz, falhas 100%",
                chains,
                dict(
                    profile="pqc",
                    include_root=0,
                    restart_fraction=1,
                    ack_fraction=1,
                    treatment="resume_preserved",
                ),
                "median_ipv4_bytes_per_confirmed_reading",
                0,
            ),
        ]:
            before = ArticleReproductionAudit.selected(
                ArticleReproductionAudit.read_csv(
                    reference_context / "cadeias_custos_absolutos.csv"
                ),
                **where,
            )
            after = ArticleReproductionAudit.selected(rows, **where)
            (a, b) = (float(before[metric]), float(after[metric]))
            comparisons.append(
                dict(
                    claim=label,
                    reference=a,
                    new=b,
                    difference=b - a,
                    same_at_article_precision=round(a, digits) == round(b, digits),
                )
            )
        for root in (0, 1):
            for treatment in ("resume_volatile", "resume_preserved"):
                where = dict(
                    profile="pqc",
                    include_root=root,
                    restart_fraction=1,
                    ack_fraction=1,
                    treatment=treatment,
                )
                a = float(
                    ArticleReproductionAudit.selected(
                        ArticleReproductionAudit.read_csv(
                            reference_context
                            / "cadeias_comparacoes_mesma_repeticao.csv"
                        ),
                        **where,
                    )["median_savings_pct"]
                )
                b = float(
                    ArticleReproductionAudit.selected(chain_pct, **where)[
                        "median_savings_pct"
                    ]
                )
                comparisons.append(
                    dict(
                        claim=f"Economia PQC, raiz={root}, {treatment}, falhas 100%",
                        reference=a,
                        new=b,
                        difference=b - a,
                        same_at_article_precision=round(a, 2) == round(b, 2),
                    )
                )
        for recovery, batch, treatment in [
            (False, 1, "resume_preserved"),
            (False, 10, "resume_preserved"),
            (False, 100, "resume_preserved"),
            (True, 100, "resume_volatile"),
            (True, 100, "resume_preserved"),
        ]:
            where = dict(
                profile="pqc", recovery=recovery, batch_size=batch, treatment=treatment
            )
            a = float(
                ArticleReproductionAudit.selected(
                    ArticleReproductionAudit.read_csv(
                        reference_context
                        / "amortizacao_comparacoes_mesma_repeticao.csv"
                    ),
                    **where,
                )["median_savings_pct"]
            )
            b = float(
                ArticleReproductionAudit.selected(amort_pct, **where)[
                    "median_savings_pct"
                ]
            )
            comparisons.append(
                dict(
                    claim=f"Amortização PQC, recuperação={recovery}, limite={batch}, {treatment}",
                    reference=a,
                    new=b,
                    difference=b - a,
                    same_at_article_precision=round(a, 2) == round(b, 2),
                )
            )
        findings = {}
        for profile in ("classical", "hybrid", "pqc"):
            for root in (0, 1):
                (full, lost, preserved) = [
                    float(
                        ArticleReproductionAudit.selected(
                            chains,
                            profile=profile,
                            include_root=root,
                            restart_fraction=1,
                            ack_fraction=1,
                            treatment=t,
                        )["median_ipv4_bytes_per_confirmed_reading"]
                    )
                    for t in ("full", "resume_volatile", "resume_preserved")
                ]
                findings[f"chain_order_{profile}_root{root}"] = preserved < full < lost
        findings["pqc_full_cost_decreases_with_connection_sharing"] = all(
            (
                a > b
                for (a, b) in zip(
                    [
                        float(
                            ArticleReproductionAudit.selected(
                                amort,
                                profile="pqc",
                                recovery=False,
                                batch_size=n,
                                treatment="full",
                            )["median_ipv4_bytes_per_confirmed_reading"]
                        )
                        for n in (1, 10)
                    ],
                    [
                        float(
                            ArticleReproductionAudit.selected(
                                amort,
                                profile="pqc",
                                recovery=False,
                                batch_size=n,
                                treatment="full",
                            )["median_ipv4_bytes_per_confirmed_reading"]
                        )
                        for n in (10, 100)
                    ],
                )
            )
        )
        for treatment in ("full", "resume_volatile", "resume_preserved"):
            row = ArticleReproductionAudit.selected(
                amort,
                profile="pqc",
                recovery=False,
                batch_size=100,
                treatment=treatment,
            )
            findings[f"no_failure_100_readings_one_full_{treatment}"] = (
                float(row["median_full_handshakes"]),
                float(row["median_resumed_handshakes"]),
            ) == (1, 0)
            row = ArticleReproductionAudit.selected(
                amort, profile="pqc", recovery=True, batch_size=100, treatment=treatment
            )
            findings[f"recovery_100_readings_handshakes_{treatment}"] = (
                float(row["median_full_handshakes"]),
                float(row["median_resumed_handshakes"]),
            ) == ((1, 2) if treatment == "resume_preserved" else (3, 0))
        audit = json.loads((continuity / "audit.json").read_text())
        findings["zero_duplicate_effects_with_deduplication"] = (
            audit["duplicate_effects_enabled"] == 0
        )
        findings["2700_duplicate_effects_without_suppression"] = (
            audit["duplicate_effects_disabled"] == 2700
        )
        findings["16200_confirmed_main_readings"] = (
            audit["confirmed_logical_readings"] == 16200
            and audit["unconfirmed_logical_readings"] == 0
        )
        context_audit = json.loads((context / "audit.json").read_text())
        findings["58860_confirmed_complementary_readings"] = (
            context_audit["chain_confirmed"] + context_audit["amortization_confirmed"]
            == 58860
        )
        findings["zero_duplicates_complementary_readings"] = (
            context_audit["chain_duplicate_effects"]
            + context_audit["amortization_duplicate_effects"]
            == 0
        )
        from ..crypto.tls.diagnostics import TicketDiagnostics

        (ec, ml) = TicketDiagnostics(
            json.loads((self.directory / "identity_tickets/results.json").read_text())
        ).matched_client_controls()
        findings["ml_dsa_client_increases_certificate_state_and_ticket"] = all(
            (
                a < b
                for (a, b) in zip(
                    [
                        ec["certificates"]["client"]["der_bytes"],
                        ec["connections"][0]["ticket_plaintext_session_der_bytes"],
                        ec["connections"][0]["tickets_tx_bytes"][0],
                    ],
                    [
                        ml["certificates"]["client"]["der_bytes"],
                        ml["connections"][0]["ticket_plaintext_session_der_bytes"],
                        ml["connections"][0]["tickets_tx_bytes"][0],
                    ],
                )
            )
        )
        result = {
            "status": "COMPARED",
            "comparison_source_sha256": hashlib.sha256(
                Path(__file__).read_bytes()
            ).hexdigest(),
            "article_zip_sha256": json.loads(
                (DATA / "article_identity.json").read_text()
            )["article_zip_sha256"],
            "reference_files_sha256": inputs,
            "claims": comparisons,
            "findings": findings,
            "all_findings_reproduced": all(findings.values()),
            "all_article_numbers_equal_at_reported_precision": all(
                (r["same_at_article_precision"] for r in comparisons)
            ),
            "note": "Numerical differences are reported without a post-hoc acceptance tolerance; timing and IPv4 traffic are measurements, not fixed constants.",
        }
        (self.output / "comparacao.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        )
        lines = [
            "# Comparação da reprodução com o artigo",
            "",
            "Dados novos: `" + str(self.directory) + "`.",
            "",
            "| Resultado | Referência | Novo | Diferença | Mesmo arredondamento do artigo |",
            "|---|---:|---:|---:|---|",
        ]
        for row in comparisons:
            lines.append(
                f"| {row['claim']} | {row['reference']:.5f} | {row['new']:.5f} | {row['difference']:+.5f} | {('Sim' if row['same_at_article_precision'] else 'Não')} |"
            )
        lines += ["", "| Propriedade observada | Reproduzida |", "|---|---|"]
        lines += [
            f"| {name} | {('Sim' if passed else 'Não')} |"
            for (name, passed) in findings.items()
        ]
        lines += [
            "",
            result["note"],
            "",
            "As diferenças de todas as condições e métricas estão em `comparacao_completa.csv`. Os dados históricos não foram substituídos.",
        ]
        (self.output / "COMPARACAO.md").write_text("\n".join(lines) + "\n")
        return result
