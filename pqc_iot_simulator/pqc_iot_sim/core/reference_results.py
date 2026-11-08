"""Read the published reference tables without changing experiment data."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from pqc_iot_simulator.pqc_iot_sim.resources import DATA

ROOT = Path(__file__).resolve().parents[3]


class ReferenceResults:
    """Reference costs, paired comparisons and diagnostic results for the study."""

    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else DATA / "context"

    def table(self, name):
        import pandas as pd

        choices = {
            "chains": "cadeias_custos_absolutos.csv",
            "chain_comparisons": "cadeias_comparacoes_mesma_repeticao.csv",
            "amortization": "amortizacao_custos_absolutos.csv",
            "amortization_comparisons": "amortizacao_comparacoes_mesma_repeticao.csv",
            "root_effect": "efeito_retirada_raiz.csv",
        }
        if name not in choices:
            raise ValueError("unknown reference table: " + name)
        return pd.read_csv(self.directory / choices[name])

    def verify(self):
        """Check versioned reference files; does not audit unshared raw captures."""
        manifest = json.loads((DATA / "referencias_sha256.json").read_text())
        for filename, expected in manifest.items():
            if hashlib.sha256((DATA / filename).read_bytes()).hexdigest() != expected:
                raise RuntimeError("reference file changed: " + filename)
        return {
            "status": "PASS",
            "files": len(manifest),
            "scope": "versioned reference data",
        }

    def compare(self, analysis_directory):
        """Show absolute new and reference costs, without requiring identical timing."""
        import pandas as pd

        directory = Path(analysis_directory)
        comparisons = []
        for table, filename, keys in (
            (
                "chains",
                "cadeias_custos_absolutos.csv",
                [
                    "restart_fraction",
                    "ack_fraction",
                    "profile",
                    "include_root",
                    "treatment",
                ],
            ),
            (
                "amortization",
                "amortizacao_custos_absolutos.csv",
                ["recovery", "batch_size", "profile", "treatment"],
            ),
        ):
            reference = self.table(table)
            new = pd.read_csv(directory / filename)
            value = "median_ipv4_bytes_per_confirmed_reading"
            result = reference[keys + [value]].merge(
                new[keys + [value]],
                on=keys,
                how="outer",
                suffixes=("_reference", "_new"),
                validate="one_to_one",
                indicator=True,
            )
            if not result["_merge"].eq("both").all():
                raise ValueError(
                    "new results do not have the same experimental conditions"
                )
            result["difference_pct"] = 100 * (
                result[value + "_new"] / result[value + "_reference"] - 1
            )
            result["experiment"] = table
            comparisons.append(result.drop(columns="_merge"))
        return pd.concat(comparisons, ignore_index=True)
