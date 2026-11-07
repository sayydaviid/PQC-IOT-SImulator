"""Notebook interfaces and reference preservation introduced by the reorganization."""

import hashlib
import json
from pathlib import Path

import pytest

from pqc_iot_simulator.pqc_iot_sim.research import RecoveryStudy, ReferenceResults
from pqc_iot_simulator.pqc_iot_sim.research.experiments import continuity
from pqc_iot_simulator.pqc_iot_sim.research.experiments.chains import hashes
from pqc_iot_simulator.pqc_iot_sim.research.experiments.amortization import (
    hashes as amortization_hashes,
)

ROOT = Path(__file__).resolve().parents[5]


@pytest.mark.parametrize("blocks", [0, -1, True, 1.5])
def test_invalid_repetition_count_does_not_create_outputs(tmp_path, blocks):
    target = tmp_path / "new"
    with pytest.raises(ValueError):
        RecoveryStudy(target, blocks=blocks)
    assert not target.exists()


def test_reference_tables_still_have_the_published_bytes():
    assert ReferenceResults().verify()["status"] == "PASS"


def test_experiment_source_manifests_point_to_existing_files():
    assert hashes()
    assert amortization_hashes()


def test_new_reproduction_does_not_reuse_completed_output(tmp_path):
    study = RecoveryStudy(tmp_path / "existing")
    study.directory.mkdir()
    sentinel = study.directory / "results.json"
    sentinel.write_text("keep original results")
    from pqc_iot_simulator.pqc_iot_sim.research.experiments.chains import (
        CertificateChainExperiment,
    )

    with pytest.raises(FileExistsError):
        CertificateChainExperiment(output=study.directory, blocks=1).run()
    assert sentinel.read_text() == "keep original results"


def test_notebooks_use_classes_and_tutorial_is_unchanged():
    note = json.loads((ROOT / "Pesquisa_Retomada_Sessoes.ipynb").read_text())
    code = "\n".join(
        "".join(c["source"]) for c in note["cells"] if c["cell_type"] == "code"
    )
    assert "RecoveryStudy" in code
    assert "scripts/" not in code and "subprocess" not in code
    assert (
        hashlib.sha256((ROOT / "Tutorial_Execucao.ipynb").read_bytes()).hexdigest()
        == "e9095dac203f80e0693979a63309de58e4a24e334e5b50547ee5d44ce4fbaaaa"
    )


def test_chains_do_not_override_the_continuity_endpoint():
    before = continuity.PROBE
    from pqc_iot_simulator.pqc_iot_sim.research.experiments.chains import (
        CertificateChainExperiment,
    )

    CertificateChainExperiment(output="/tmp/unused-class-construction", blocks=1)
    assert continuity.PROBE == before
