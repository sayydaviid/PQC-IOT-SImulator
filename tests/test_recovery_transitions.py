"""Interrupted flights must preserve cryptographic safety and count real costs."""

import os

import pytest

from pqc_iot_simulator.pqc_iot_sim.components.recovery import (
    Identity,
    MODES,
    SealedStore,
)
from pqc_iot_simulator.pqc_iot_sim.core.recovery_transitions import (
    SCENARIOS,
    assess,
    transition_case,
)


@pytest.fixture(scope="module")
def identities():
    return Identity.generate(), Identity.generate()


@pytest.mark.parametrize("policy", MODES)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_interrupted_flights_and_application_ack_control(
    tmp_path, identities, policy, scenario
):
    row = transition_case(
        SealedStore(tmp_path, os.urandom(32)), policy, scenario, *identities
    )
    assert row["nonce_reuses"] == 0
    assert not row["stale_record_accepted"]
    assert row["application_acceptances"] == (
        2 if scenario == "lost_reading_ack" else 1
    )
    assert row["application_duplicates"] == (scenario == "lost_reading_ack")
    assert row["full_fallback"] == (
        scenario == "torn_checkpoint"
        or (scenario == "gateway_lost_before_start" and policy != "full_pqc")
    )
    if scenario == "after_gateway_commit":
        assert row["initial_flights_sent"][-1] == "server_finished"
        assert row["retry_handshake_bytes"] > 0


def test_total_cost_includes_failed_resume_and_rejects_false_positive(
    tmp_path, identities
):
    rows = []
    for scenario in SCENARIOS:
        for policy in MODES:
            row = transition_case(
                SealedStore(tmp_path / scenario / policy, os.urandom(32)),
                policy,
                scenario,
                *identities,
            )
            row["repetition"] = 0
            rows.append(row)
    result = assess(rows)
    assert result["status"] == "PASS"
    assert not result["pqc_always_smaller"]
    lost = next(
        c
        for c in result["byte_comparisons"]
        if c["scenario"] == "gateway_lost_before_start"
    )
    assert lost["pqc_bytes"] > lost["full_bytes"]
    rows[0]["nonce_reuses"] = 1
    assert assess(rows)["status"] == "FAILED_GATE"
