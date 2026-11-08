"""Recalculate historical article tables from per-execution observations."""

from __future__ import annotations
import csv
import gzip
import hashlib
import json
from pathlib import Path
from pqc_iot_simulator.pqc_iot_sim.resources import DATA

ROOT = Path(__file__).resolve().parents[3]


class ArticleNumericalReanalysis:
    """Recompute published numbers; never label archived data as new experiments.

    The versioned export contains numeric observations, not credentials or PCAP.
    Network execution and capture validation belong to RecoverySimulation instead.
    """

    def __init__(self, directory):
        self.directory = Path(directory)

    def run(self):
        from pqc_iot_simulator.pqc_iot_sim.components.context_metrics import (
            SessionCostMetrics,
        )
        from pqc_iot_simulator.pqc_iot_sim.components.continuity_metrics import (
            ContinuityMetrics,
        )

        source = DATA
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
        SessionCostMetrics(
            chains=self.directory / "inputs/chains",
            amortization=self.directory / "inputs/amortization",
            output=self.directory / "context_analysis",
        ).run()
        rows = []
        for phase in ("core", "loss"):
            (_, cases) = ContinuityMetrics.validate(self.directory / "inputs" / phase)
            rows.extend(
                (dict(ContinuityMetrics.metrics(case), phase=phase) for case in cases)
            )
        (aggregates, contrasts, state, migration) = ContinuityMetrics.analyze(rows)
        target = self.directory / "continuity_analysis"
        target.mkdir()
        for filename, values in (
            ("ensaios.csv", rows),
            ("medianas.csv", aggregates),
            ("contrastes_pareados.csv", contrasts),
            ("preservacao_contexto.csv", state),
            ("custos_migracao.csv", migration),
            ("interacoes_falhas.csv", ContinuityMetrics.fault_interactions(rows)),
        ):
            ContinuityMetrics.write_csv(target / filename, values)

        def read(path):
            with path.open(newline="") as handle:
                return list(csv.DictReader(handle))

        equal = {}
        for folder, reference in (
            ("context_analysis", "context"),
            ("continuity_analysis", "continuity"),
        ):
            for path in sorted((self.directory / folder).glob("*.csv")):
                equal[f"{folder}/{path.name}"] = read(path) == read(
                    DATA / reference / path.name
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
                    Path(__file__).resolve().parents[1]
                    / "components/context_metrics.py",
                    Path(__file__).resolve().parents[1]
                    / "components/continuity_metrics.py",
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
