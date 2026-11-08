import pytest
from pqc_iot_simulator.pqc_iot_sim.components.continuity_metrics import (
    ContinuityMetrics,
)


def factorial():
    rows = []
    for p in ("classical", "hybrid", "pqc"):
        for d in (False, True):
            for b in range(3):
                for r in (0, 0.25, 1):
                    for a in (0, 0.25, 1):
                        for t in ("resume_volatile", "resume_preserved"):
                            effect = 10 * r + 20 * a + 40 * r * a
                            rows.append(
                                dict(
                                    phase="core",
                                    loss_pct=0,
                                    profile=p,
                                    deduplicate=d,
                                    block=b,
                                    restart_fraction=r,
                                    ack_fraction=a,
                                    treatment=t,
                                    confirmed_readings=9,
                                    ipv4_bytes_per_confirmed_reading=1000 * b
                                    + 100
                                    + (effect if t == "resume_volatile" else 0),
                                )
                            )
    return rows


def test_four_corner_contrast_removes_additive_effects_and_block_offsets():
    result = ContinuityMetrics.fault_interactions(factorial())
    assert len(result) == 24
    for r in result:
        expected = 40 * r["restart_fraction"] * r["ack_fraction"]
        assert r["median_interaction_bytes_per_confirmed_reading"] == expected
        assert r["bootstrap95_low"] == r["bootstrap95_high"] == expected


def test_missing_corner_is_rejected_instead_of_changing_block_sample():
    rows = factorial()
    rows.pop()
    with pytest.raises(ValueError, match="missing factorial interaction corner"):
        ContinuityMetrics.fault_interactions(rows)


def test_unconfirmed_corner_makes_cost_interaction_undefined():
    rows = factorial()
    rows[0]["confirmed_readings"] = 0
    rows[0]["ipv4_bytes_per_confirmed_reading"] = None
    result = ContinuityMetrics.fault_interactions(rows)
    missing = [
        r for r in result if r["profile"] == "classical" and (not r["deduplicate"])
    ]
    assert all(
        (r["median_interaction_bytes_per_confirmed_reading"] is None for r in missing)
    )
