"""New measurements and published summaries use the same matched controls."""

import copy
import json
from pathlib import Path

import pytest

from pqc_iot_simulator.pqc_iot_sim.components.tls.diagnostics import TicketDiagnostics

ROOT = Path(__file__).resolve().parents[4]


def public():
    return json.loads(
        (
            ROOT
            / "pqc_iot_simulator/pqc_iot_sim/data/diagnostico_tickets_20261106.json"
        ).read_text()
    )


def test_matches_by_server_and_ca_instead_of_row_position():
    data = public()
    data["diagnostics"].reverse()
    ec, ml = TicketDiagnostics(data).matched_client_controls()
    assert ec["client_key"] == "EC" and ml["client_key"] == "ML-DSA-44"


def test_raw_measurements_can_include_the_wrong_identity_control_last():
    data = public()
    for row in data["diagnostics"]:
        row["include_root"] = row.pop("root")
        row["server"] = {"connections": row.pop("connections")}
        row["client_identity"] = "iot_1"
    wrong = copy.deepcopy(data["diagnostics"][-1])
    wrong["client_identity"] = "iot_2"
    data["diagnostics"].append(wrong)
    ec, ml = TicketDiagnostics(data).matched_client_controls()
    assert ec["root"] == ml["root"] == 0
    assert ec["connections"]


def test_changed_measured_sizes_are_not_replaced_by_reference_numbers():
    data = public()
    data["diagnostics"][-1]["connections"][0]["ticket_plaintext_session_der_bytes"] += 1
    _, ml = TicketDiagnostics(data).matched_client_controls()
    assert ml["connections"][0]["ticket_plaintext_session_der_bytes"] == 4171


def test_comparison_with_changed_ca_is_rejected():
    data = public()
    data["diagnostics"][-1]["certificates"]["ca"]["sha256"] = "different"
    with pytest.raises(ValueError, match="same server and CA"):
        TicketDiagnostics(data).matched_client_controls()
