"""Fault scheduling and negotiated-profile controls for the expanded campaign."""
import pytest

from scripts.continuity_design import PROFILES, cells, check_tls, schedule


def test_factorial_and_loss_slice_have_no_duplicate_cells():
    assert len(cells("core")) == len(set(cells("core"))) == 162
    assert len(cells("loss")) == len(set(cells("loss"))) == 18
    assert all(c[0] == 0 for c in cells("core"))
    assert all(c[1:3] == (0.25, 0.25) and c[-1] for c in cells("loss"))


@pytest.mark.parametrize("fraction,count", [(0, 0), (0.25, 2), (1, 8)])
def test_exact_fault_counts_and_no_fault_on_initial_reading(fraction, count):
    s = schedule(9, fraction, fraction, 3)
    assert len(s["restart_before"]) == len(s["drop_first_ack"]) == count
    assert 0 not in s["restart_before"] + s["drop_first_ack"]


def test_schedule_reproducible_and_changes_across_blocks():
    assert schedule(9, 0.25, 0.25, 0) == schedule(9, 0.25, 0.25, 0)
    assert len({str(schedule(9, 0.25, 0.25, b)) for b in range(10)}) > 5


@pytest.mark.parametrize("n,fraction", [(4, 0.25), (8, 0.25), (9, 0.5)])
def test_unsupported_frequency_cannot_be_silently_rounded(n, fraction):
    with pytest.raises(ValueError):
        schedule(n, fraction, 0, 0)


def good(profile):
    p = PROFILES[profile]
    return dict(version="TLSv1.3", cipher="TLS_AES_256_GCM_SHA384", group=p["group"].lower(),
                verify_result=0, peer_key_type=p["key_type"], client_share_sha256="c",
                server_share_sha256="s", reused=0, certificate_verify_tx_scheme=p["signature_code"],
                certificate_verify_rx_scheme=p["signature_code"])


@pytest.mark.parametrize("profile", PROFILES)
def test_full_handshake_requires_exact_mutual_signature_and_group(profile):
    row = good(profile)
    check_tls(row, profile, False)
    row["certificate_verify_rx_scheme"] = 0
    with pytest.raises(RuntimeError):
        check_tls(row, profile, False)
    row = good(profile)
    row["group"] = "secp256r1"
    with pytest.raises(RuntimeError):
        check_tls(row, profile, False)


def test_unexpected_resumption_and_invalid_identity_fail_closed():
    row = good("pqc")
    with pytest.raises(RuntimeError):
        check_tls(row, "pqc", True)
    row["verify_result"] = 20
    with pytest.raises(RuntimeError):
        check_tls(row, "pqc")
