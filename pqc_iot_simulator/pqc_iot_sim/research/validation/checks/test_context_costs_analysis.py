"""The scientific estimand is a matched block contrast, not a ratio of medians."""

import itertools
import json
import sys
import pytest
from pqc_iot_simulator.pqc_iot_sim.research.analysis.context import (
    bpr,
    contrasts,
    summarize,
)


def case(block, treatment, total, confirmed=1):
    return {
        "block": block,
        "profile": "pqc",
        "treatment": treatment,
        "include_root": 0,
        "restart_fraction": 1,
        "ack_fraction": 1,
        "capture": {"iot_tx_ip_bytes": total, "iot_rx_ip_bytes": 0},
        "confirmed_readings": confirmed,
        "unconfirmed_readings": [] if confirmed else [0],
        "readings": 1,
        "delivery_status": "complete" if confirmed else "budget_exhausted",
        "sequence_ms": 10,
        "clients": [],
        "duplicate_effects": 0,
    }


def test_cost_reduction_is_computed_within_each_block():
    rows = []
    for block, (base, cost) in enumerate([(100, 50), (100, 200), (1000, 500)]):
        rows.extend(
            [
                case(block, "full", base),
                case(block, "resume_volatile", cost),
                case(block, "resume_preserved", cost),
            ]
        )
    result = contrasts(rows, ["profile", "include_root"])
    assert all(r["median_savings_pct"] == 50 for r in result)
    assert all(r["median_bytes_difference_per_reading"] == -50 for r in result)
    # A ratio of the two medians would incorrectly report a 100% increase.
    assert result[0]["median_savings_pct"] != -100


def test_zero_confirmations_are_retained_as_undefined_cost():
    rows = [
        case(0, "full", 100),
        case(0, "resume_volatile", 90, 0),
        case(0, "resume_preserved", 50),
    ]
    assert bpr(rows[1]) is None
    result = {r["treatment"]: r for r in contrasts(rows, ["profile", "include_root"])}
    assert result["resume_volatile"]["median_savings_pct"] is None
    assert result["resume_volatile"]["median_ms_difference_per_reading"] is None
    assert result["resume_volatile"]["median_bytes_difference_per_reading"] is None
    assert result["resume_volatile"]["blocks"] == 1
    assert result["resume_preserved"]["median_savings_pct"] == 50


def test_missing_matched_comparator_is_not_silently_omitted():
    rows = [case(0, "full", 100), case(0, "resume_preserved", 50)]
    with pytest.raises(KeyError):
        contrasts(rows, ["profile", "include_root"])


def test_duplicate_block_does_not_inflate_independent_repetitions():
    rows = [case(0, "full", 100), case(0, "full", 120)]
    with pytest.raises(AssertionError):
        summarize(rows, ["profile", "include_root", "treatment"])


@pytest.mark.parametrize("exhausted", [False, True])
def test_complete_design_is_analyzed_without_losing_a_factor(
    tmp_path, monkeypatch, capsys, exhausted
):
    from pqc_iot_simulator.pqc_iot_sim.research.analysis.context import (
        ContextCostAnalysis,
    )

    profiles = ["classical", "hybrid", "pqc"]
    treatments = ["full", "resume_volatile", "resume_preserved"]
    chains = []
    for i, (fraction, profile, treatment, root) in enumerate(
        itertools.product([0, 0.25, 1], profiles, treatments, [0, 1])
    ):
        row = case(0, treatment, 1000 if treatment == "full" else 500)
        row.update(
            case_id=f"chain{i}",
            profile=profile,
            include_root=root,
            restart_fraction=fraction,
            ack_fraction=fraction,
        )
        if exhausted and i == 0:
            row.update(
                confirmed_readings=0,
                unconfirmed_readings=[0],
                delivery_status="budget_exhausted",
            )
        chains.append(row)
    amort = []
    for i, (profile, treatment, batch, recovery) in enumerate(
        itertools.product(profiles, treatments, [1, 10, 100], [False, True])
    ):
        row = case(0, treatment, 1000 if treatment == "full" else 500)
        row.update(
            case_id=f"amort{i}", profile=profile, batch_size=batch, recovery=recovery
        )
        amort.append(row)
    for name, rows in [("chains", chains), ("amort", amort)]:
        directory = tmp_path / name
        directory.mkdir()
        (directory / "manifest.json").write_text(
            json.dumps({"blocks": 1, "planned_cases": 54})
        )
        (directory / "results.json").write_text(
            json.dumps({"status": "PASS", "cases": rows})
        )
    ContextCostAnalysis(
        chains=tmp_path / "chains",
        amortization=tmp_path / "amort",
        output=tmp_path / "analysis",
    ).run()
    audit = json.loads((tmp_path / "analysis/audit.json").read_text())
    assert audit["chain_cases"] == audit["amortization_cases"] == 54
    assert audit["chain_confirmed"] == (53 if exhausted else 54)
    assert (
        len(
            (tmp_path / "analysis/cadeias_custos_absolutos.csv")
            .read_text()
            .splitlines()
        )
        == 55
    )
    assert (
        len(
            (tmp_path / "analysis/amortizacao_custos_absolutos.csv")
            .read_text()
            .splitlines()
        )
        == 55
    )
    from pqc_iot_simulator.pqc_iot_sim.research.analysis.report import ContextReport

    ContextReport(analysis=tmp_path / "analysis", output=tmp_path / "report.md").run()
    assert "100%" in (tmp_path / "report.md").read_text()
    if exhausted:
        assert "indefinido" in (tmp_path / "report.md").read_text()
