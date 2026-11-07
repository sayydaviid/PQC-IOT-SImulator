"""Resume analysis after a documented capture-reader correction.

Completed measurements remain unchanged. The failed notebook record is kept;
only analysis and figure cells run in a fresh kernel with the corrected reader.
"""

from __future__ import annotations

import hashlib
import json
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class PostprocessingContinuation:
    def __init__(self, *, directory, original_record, record_directory):
        self.directory = Path(directory).resolve()
        self.original_record = Path(original_record).resolve()
        self.record_directory = Path(record_directory).resolve()

    def wait_and_run(self):
        while True:
            record = json.loads(self.original_record.read_text())
            if record["status"] != "RUNNING":
                break
            time.sleep(15)
        if record["status"] == "EXECUTED":
            from .article_comparison import ArticleReproductionAudit

            return ArticleReproductionAudit(
                directory=self.directory, output=self.record_directory / "comparison"
            ).run()
        error = record.get("error", "")
        if record["status"] != "FAILED" or not any(
            text in error
            for text in ("missing ClientHello", "sources changed during reproduction:")
        ):
            raise RuntimeError(
                "Unexpected notebook failure; refusing to ignore it: " + error
            )
        correction = json.loads(
            (ROOT / "docs/reproducao/correcao_analise_portas_20261107.json").read_text()
        )
        changed = {
            name
            for name, digest in record["source_sha256"].items()
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest
        }
        if changed != {correction["file"]}:
            raise RuntimeError("Undocumented source changes: " + repr(changed))
        if (
            hashlib.sha256((ROOT / correction["file"]).read_bytes()).hexdigest()
            != correction["after_sha256"]
        ):
            raise RuntimeError("Analysis correction differs from its registered source")
        return self.run()

    def run(self):
        import nbformat
        from nbclient import NotebookClient

        self.record_directory.mkdir(parents=True, exist_ok=False)
        inputs = {}
        for stage in (
            "prototype",
            "transitions",
            "core",
            "loss",
            "chains",
            "amortization",
            "identity_tickets",
            "persistence",
            "tls_persistence",
            "continuity_security",
        ):
            path = self.directory / stage / "results.json"
            data = json.loads(path.read_text())
            if data.get(
                "status",
                data.get("assessment", {}).get(
                    "status", data.get("verdict", {}).get("status")
                ),
            ) not in ("PASS", "SUPPORTED_IN_TESTED_MODEL"):
                raise RuntimeError("Measurement stage did not pass: " + stage)
            inputs[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        old = self.directory / "postprocessing_previous_attempt"
        for name in (
            "continuity_analysis",
            "context_analysis",
            "figures",
            "prototype_figures",
        ):
            path = self.directory / name
            if path.exists():
                old.mkdir(exist_ok=True)
                path.rename(old / name)
        source = nbformat.read(ROOT / "Pesquisa_Retomada_Sessoes.ipynb", as_version=4)
        start = next(
            i
            for i, c in enumerate(source.cells)
            if c.cell_type == "code" and "estudo.analyze_continuity()" in c.source
        )
        note = nbformat.v4.new_notebook(metadata=source.metadata)
        note.cells = [
            nbformat.v4.new_markdown_cell(
                "# Continuação do pós-processamento\n\nMedições completas preservadas da execução original. "
                "O kernel original carregou o leitor anterior nas verificações; duas capturas com portas iguais exigiram a correção documentada. "
                "Este notebook executa somente análise e figuras em um kernel novo. O registro da falha original é mantido."
            ),
            nbformat.v4.new_code_cell(
                "from pathlib import Path\nfrom IPython.display import display, Image\n"
                "from pqc_iot_simulator import RecoveryStudy, ReferenceResults\n"
                f"REPRODUZIR = True\nBLOCOS = 10\nestudo = RecoveryStudy(Path({str(self.directory)!r}), blocks=BLOCOS)\n"
                "referencia = ReferenceResults()\n"
            ),
        ] + source.cells[start:]
        state = {
            "status": "RUNNING",
            "scope": "postprocessing only; no new measurements",
            "upstream_record": str(self.original_record),
            "upstream_record_sha256": hashlib.sha256(
                self.original_record.read_bytes()
            ).hexdigest(),
            "input_results_sha256": inputs,
            "correction": json.loads(
                (
                    ROOT / "docs/reproducao/correcao_analise_portas_20261107.json"
                ).read_text()
            ),
        }

        def save():
            nbformat.write(
                note, self.record_directory / "notebook_pos_processamento.ipynb"
            )
            (self.record_directory / "execution.json").write_text(
                json.dumps(state, indent=2) + "\n"
            )

        def started(cell, cell_index, **unused):
            state["cell_index"] = cell_index
            state["active_cell"] = cell.source
            save()

        save()
        try:
            NotebookClient(
                note,
                kernel_name="python3",
                timeout=None,
                startup_timeout=120,
                resources={"metadata": {"path": str(ROOT)}},
                on_cell_start=started,
            ).execute()
            if any(
                hashlib.sha256(Path(p).read_bytes()).hexdigest() != digest
                for p, digest in inputs.items()
            ):
                raise RuntimeError("Measurement results changed during analysis")
            from .article_comparison import ArticleReproductionAudit

            audit = ArticleReproductionAudit(
                directory=self.directory, output=self.record_directory / "comparison"
            ).run()
            state["status"] = "EXECUTED"
            state["comparison_summary"] = {
                k: audit[k]
                for k in (
                    "all_findings_reproduced",
                    "all_article_numbers_equal_at_reported_precision",
                )
            }
        except BaseException:
            state["status"] = "FAILED"
            state["error"] = traceback.format_exc()
            raise
        finally:
            save()
        return state
