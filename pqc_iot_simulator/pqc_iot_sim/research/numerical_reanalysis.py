"""Recalculate historical article tables from per-execution observations."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class ArticleNumericalReanalysis:
    """Recompute published numbers; never label archived data as new experiments.

    The versioned export contains numeric observations, not credentials or PCAP.
    Network execution and capture validation belong to RecoveryStudy instead.
    """

    def __init__(self, directory):
        self.directory = Path(directory)

    def run(self):
        from .analysis.context import ContextCostAnalysis
        from .analysis.continuity import (
            analyze,
            fault_interactions,
            metrics,
            validate,
            write_csv,
        )

        source = ROOT / "docs/reproducao"
        manifest = json.loads(
            (source / "dados_numericos_artigo_manifesto.json").read_text()
        )
        archive = source / "dados_numericos_artigo.json.gz"
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != manifest["archive_sha256"]:
            raise ValueError("historical numeric observations changed")
        bundle = json.loads(gzip.decompress(archive.read_bytes()))
        if bundle["schema"] != 1:
            raise ValueError("unsupported numeric observation schema")
        self.directory.mkdir(parents=True, exist_ok=False)
        for name in ("chains", "amortization", "core", "loss"):
            dataset = bundle["datasets"][name]
            path = self.directory / "inputs" / name
            path.mkdir(parents=True)
            for filename in ("results", "manifest"):
                (path / f"{filename}.json").write_text(json.dumps(dataset[filename]))

        ContextCostAnalysis(
            chains=self.directory / "inputs/chains",
            amortization=self.directory / "inputs/amortization",
            output=self.directory / "context_analysis",
        ).run()
        rows = []
        for phase in ("core", "loss"):
            _, cases = validate(self.directory / "inputs" / phase)
            rows.extend(dict(metrics(case), phase=phase) for case in cases)
        aggregates, contrasts, state, migration = analyze(rows)
        target = self.directory / "continuity_analysis"
        target.mkdir()
        for filename, values in (
            ("ensaios.csv", rows),
            ("medianas.csv", aggregates),
            ("contrastes_pareados.csv", contrasts),
            ("preservacao_contexto.csv", state),
            ("custos_migracao.csv", migration),
            ("interacoes_falhas.csv", fault_interactions(rows)),
        ):
            write_csv(target / filename, values)

        def read(path):
            with path.open(newline="") as handle:
                return list(csv.DictReader(handle))

        equal = {}
        for folder, reference in (
            ("context_analysis", "resultados_contexto_20261106"),
            ("continuity_analysis", "resultados_continuidade_20261021_v5"),
        ):
            for path in sorted((self.directory / folder).glob("*.csv")):
                equal[f"{folder}/{path.name}"] = read(path) == read(
                    ROOT / "docs" / reference / path.name
                )
        result = {
            "status": "PASS" if all(equal.values()) else "MISMATCH",
            "scope": bundle["scope"],
            "archive_sha256": digest,
            "exact_table_equality": equal,
            "source_sha256": {
                str(path.relative_to(ROOT)): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in (
                    Path(__file__),
                    Path(__file__).with_name("analysis") / "context.py",
                    Path(__file__).with_name("analysis") / "continuity.py",
                )
            },
        }
        (self.directory / "comparacao_exata.json").write_text(
            json.dumps(result, indent=2) + "\n"
        )
        if result["status"] != "PASS":
            raise ValueError(
                "recalculated tables differ from the article; see comparacao_exata.json"
            )
        return result
