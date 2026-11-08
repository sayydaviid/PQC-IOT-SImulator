"""Archived calculations must retain their inputs and never overwrite a run."""

import json

import pytest

from pqc_iot_simulator import ArticleNumericalReanalysis
from pqc_iot_simulator.pqc_iot_sim.research import numerical_reanalysis


def test_changed_archive_is_rejected_before_creating_output(tmp_path, monkeypatch):
    source = tmp_path / "docs/reproducao"
    source.mkdir(parents=True)
    (source / "dados_numericos_artigo_manifesto.json").write_text(
        json.dumps({"archive_sha256": "0" * 64})
    )
    (source / "dados_numericos_artigo.json.gz").write_bytes(b"altered observations")
    monkeypatch.setattr(numerical_reanalysis, "ROOT", tmp_path)
    output = tmp_path / "new-analysis"
    with pytest.raises(ValueError, match="observations changed"):
        ArticleNumericalReanalysis(output).run()
    assert not output.exists()


def test_reanalysis_refuses_to_overwrite_existing_output(tmp_path):
    sentinel = tmp_path / "preserve.txt"
    sentinel.write_text("original")
    with pytest.raises(FileExistsError):
        ArticleNumericalReanalysis(tmp_path).run()
    assert sentinel.read_text() == "original"
    assert not (tmp_path / "inputs").exists()
