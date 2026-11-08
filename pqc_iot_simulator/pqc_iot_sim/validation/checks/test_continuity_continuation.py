import json

import pytest

import pqc_iot_simulator.pqc_iot_sim.engines.tls_continuity as campaign


@pytest.fixture
def interrupted(tmp_path, monkeypatch):
    monkeypatch.setattr(
        campaign,
        "cells",
        lambda phase: [(0, 0, 0, "pqc", t, True) for t in ("full", "resume_preserved")],
    )
    old = {
        "pqc_iot_simulator/pqc_iot_sim/engines/tls_continuity.py": "current-runner",
        "endpoint.py": "unchanged",
    }
    new = dict(old)
    source = tmp_path / "source"
    source.mkdir()
    (source / "manifest.json").write_text(
        json.dumps(dict(phase="core", blocks=2, readings=9, source_sha256=old))
    )
    # Block 0 is whole, including an exhausted delivery budget. Block 1 is partial.
    for block, treatments in [(0, ("full", "resume_preserved")), (1, ("full",))]:
        for treatment in treatments:
            name = f"l0_b{block}_r0_a0_pqc_{treatment}_d1"
            directory = source / name
            directory.mkdir()
            (directory / "case.json").write_text(
                json.dumps(
                    dict(case_id=name, block=block, readings=9, confirmed_readings=8)
                )
            )
    return source, new


def test_retains_whole_blocks_including_failed_deliveries(interrupted):
    source, hashes = interrupted
    _, rows, blocks = campaign.completed_blocks(source, "core", 2, 9, hashes)
    assert blocks == {(0, 0)}
    assert len(rows) == 2
    assert all(r["confirmed_readings"] == 8 for r in rows)


def test_rejects_changed_experimental_endpoint(interrupted):
    source, hashes = interrupted
    with pytest.raises(ValueError, match="experimental source differs"):
        campaign.completed_blocks(
            source, "core", 2, 9, {**hashes, "endpoint.py": "changed"}
        )


def test_rejects_incompatible_design(interrupted):
    source, hashes = interrupted
    with pytest.raises(ValueError, match="design differs"):
        campaign.completed_blocks(source, "core", 2, 5, hashes)


def test_rejects_changed_runner(interrupted):
    source, hashes = interrupted
    changed = {
        **hashes,
        "pqc_iot_simulator/pqc_iot_sim/engines/tls_continuity.py": "another-runner",
    }
    with pytest.raises(ValueError, match="experimental source differs"):
        campaign.completed_blocks(source, "core", 2, 9, changed)
