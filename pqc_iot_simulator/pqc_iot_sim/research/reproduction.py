"""Execute and checkpoint the research notebook with new measurements."""

from __future__ import annotations

import hashlib
import json
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class NotebookReproduction:
    """Execute the actual notebook, enabling measurements and preserving its outputs.

    Checkpoints describe execution progress, not successful reproduction. The
    comparison of new data with article references is a separate analysis.
    """

    def __init__(self, *, directory, record_directory, blocks=10):
        self.directory = Path(directory).resolve()
        self.record_directory = Path(record_directory).resolve()
        self.blocks = blocks

    def run(self):
        import nbformat
        from nbclient import NotebookClient

        if self.directory.exists():
            raise FileExistsError(self.directory)
        self.record_directory.mkdir(parents=True, exist_ok=False)
        source = ROOT / "Pesquisa_Retomada_Sessoes.ipynb"
        notebook = nbformat.read(source, as_version=4)
        found = 0
        for cell in notebook.cells:
            if cell.cell_type == "code" and re.search(
                r"^REPRODUZIR = (True|False)$", cell.source, re.M
            ):
                cell.source = re.sub(
                    r"^REPRODUZIR = (True|False)$",
                    "REPRODUZIR = True",
                    cell.source,
                    flags=re.M,
                )
                cell.source = cell.source.replace(
                    "BLOCOS = 10", f"BLOCOS = {self.blocks}"
                )
                cell.source = cell.source.replace(
                    'Path("results/reproducao") / identificador',
                    f"Path({str(self.directory)!r})",
                )
                found += 1
        if found != 1:
            raise ValueError("the notebook execution configuration is ambiguous")
        record = {
            "status": "RUNNING",
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "blocks": self.blocks,
            "data_directory": str(self.directory),
            "source_notebook_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "configuration_changes": [
                "REPRODUZIR=True",
                f"BLOCOS={self.blocks}",
                "new output directory",
            ],
            "source_sha256": {
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted((ROOT / "pqc_iot_simulator").rglob("*.py"))
            },
        }

        def checkpoint():
            record["updated_utc"] = datetime.now(timezone.utc).isoformat()
            nbformat.write(notebook, self.record_directory / "notebook_executado.ipynb")
            target = self.record_directory / "execution.json"
            temporary = target.with_suffix(".tmp")
            temporary.write_text(json.dumps(record, indent=2) + "\n")
            temporary.replace(target)

        def start(cell, cell_index, **unused):
            record["cell_index"] = cell_index
            record["active_cell"] = cell.source
            checkpoint()
            print(
                json.dumps({"cell_started": cell_index, "source": cell.source}),
                flush=True,
            )

        def finished(cell, cell_index, **unused):
            record["last_finished_cell"] = cell_index
            checkpoint()
            print(json.dumps({"cell_finished": cell_index}), flush=True)

        checkpoint()
        client = NotebookClient(
            notebook,
            kernel_name="python3",
            timeout=None,
            startup_timeout=120,
            resources={"metadata": {"path": str(ROOT)}},
            on_cell_start=start,
            on_cell_executed=finished,
        )
        try:
            client.execute()
            changed = [
                name
                for name, digest in record["source_sha256"].items()
                if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest
            ]
            if changed:
                raise RuntimeError(
                    "sources changed during reproduction: " + ", ".join(changed)
                )
            record["status"] = "EXECUTED"
            record["note"] = (
                "New measurements executed; numerical agreement must be checked separately."
            )
        except BaseException:
            record["status"] = "FAILED"
            record["error"] = traceback.format_exc()
            raise
        finally:
            checkpoint()
        return self.record_directory
