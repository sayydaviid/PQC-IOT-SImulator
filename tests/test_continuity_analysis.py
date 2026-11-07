import pytest

from scripts.summarize_continuity import analyze, interval


def test_bootstrap_keeps_block_unit_and_reproduces_constant_effect():
    assert interval([25.0] * 10, resamples=1000) == (25.0, 25.0, 25.0)
    with pytest.raises(ValueError):
        interval([25.0])


def example_rows():
    rows = []
    for block, scale in enumerate((1, 10, 100)):
        for profile in ("classical", "hybrid", "pqc"):
            for treatment, ratio in (("full", 1), ("resume_volatile", .8), ("resume_preserved", .5)):
                rows.append(dict(phase="core", loss_pct=0, restart_fraction=.25, ack_fraction=.25,
                    profile=profile, deduplicate=True, treatment=treatment, block=block,
                    ipv4_bytes_per_reading=scale*100*ratio, ipv4_bytes_per_confirmed_reading=scale*100*ratio,
                    confirmed_readings=9, scheduled_readings=9, fully_confirmed=True, unplanned_unacknowledged=0, mean_sequence_ms_per_reading=scale*10*ratio,
                    median_reading_recovery_ms=scale*10*ratio, full_handshakes=1,
                    resumed_handshakes=8, retry_full_handshakes=0, duplicate_effects=0))
    return rows


def test_pairing_uses_each_blocks_own_reference():
    # Between-block load differs by 100x. The within-block savings stay constant.
    _, contrasts, _, _ = analyze(example_rows())
    assert len(contrasts) == 6
    for r in contrasts:
        expected = 50 if r["treatment"] == "resume_preserved" else 20
        assert r["median_paired_saving_pct"] == pytest.approx(expected)
        assert r["blocks"] == 3


def test_missing_matched_block_is_rejected():
    rows = example_rows()
    rows.pop()
    with pytest.raises(ValueError, match="missing paired comparator"):
        analyze(rows)


def test_censored_time_cannot_be_reported_as_faster_delivery():
    rows = example_rows()
    for row in rows:
        if row["profile"] == "pqc" and row["treatment"] == "resume_volatile" and row["block"] == 0:
            row["confirmed_readings"] = 8
            row["fully_confirmed"] = False
    _, contrasts, _, _ = analyze(rows)
    c = next(x for x in contrasts if x["profile"] == "pqc" and x["treatment"] == "resume_volatile")
    assert not c["all_deliveries_complete"]
    assert c["median_paired_time_delta_ms"] is None


def test_zero_confirmations_are_not_dropped_from_paired_byte_analysis():
    rows = example_rows()
    for row in rows:
        if row["profile"] == "pqc" and row["treatment"] == "resume_volatile" and row["block"] == 0:
            row["confirmed_readings"] = 0
            row["fully_confirmed"] = False
            row["ipv4_bytes_per_confirmed_reading"] = None
    _, contrasts, _, _ = analyze(rows)
    c = next(x for x in contrasts if x["profile"] == "pqc" and x["treatment"] == "resume_volatile")
    assert c["median_paired_saving_pct"] is None
    assert c["blocks"] == 3
