import sqlite3

import pytest

from pqc_iot_simulator.pqc_iot_sim.components.reading_ledger import (
    ReadingConflict,
    ReadingLedger,
)


@pytest.mark.parametrize("deduplicate", (False, True))
def test_ack_loss_retry_after_restart(tmp_path, deduplicate):
    path = tmp_path / "ledger.db"
    ledger = ReadingLedger(path, deduplicate)
    first = ledger.ingest("iot_1", "sample-1", b"known reading")
    assert first["effect_applied"]
    ledger.close()  # Commit survived; delivery ACK was lost.
    ledger = ReadingLedger(path, deduplicate)
    retry = ledger.ingest("iot_1", "sample-1", b"known reading")
    assert retry["duplicate"]
    assert retry["effect_applied"] == (not deduplicate)
    assert ledger.counts() == {
        "unique_readings": 1,
        "application_effects": 1 if deduplicate else 2,
        "duplicate_effects": 0 if deduplicate else 1,
    }
    ledger.close()


def test_conflicting_content_fails_without_new_effect(tmp_path):
    ledger = ReadingLedger(tmp_path / "ledger.db")
    ledger.ingest("iot_1", "sample-1", b"original")
    with pytest.raises(ReadingConflict):
        ledger.ingest("iot_1", "sample-1", b"changed")
    assert ledger.counts()["application_effects"] == 1
    assert ledger.ingest("iot_1", "sample-1", b"original")["duplicate"]
    assert not ledger.ingest("iot_2", "sample-1", b"other device")["duplicate"]
    ledger.close()


def test_failed_effect_insert_rolls_back_the_id(tmp_path):
    ledger = ReadingLedger(tmp_path / "ledger.db")
    ledger.connection.execute(
        "CREATE TRIGGER injected_failure BEFORE INSERT ON effects BEGIN SELECT RAISE(ABORT,'injected'); END"
    )
    with pytest.raises(sqlite3.IntegrityError):
        ledger.ingest("iot_1", "sample-1", b"reading")
    assert ledger.counts()["unique_readings"] == 0
    ledger.connection.execute("DROP TRIGGER injected_failure")
    assert ledger.ingest("iot_1", "sample-1", b"reading")["effect_applied"]
    ledger.close()


def test_full_ledger_rollback_is_not_prevented(tmp_path):
    path, snapshot = tmp_path / "ledger.db", tmp_path / "snapshot.db"
    ledger = ReadingLedger(path)
    with sqlite3.connect(snapshot) as target:
        ledger.connection.backup(target)
    ledger.ingest("iot_1", "sample-1", b"reading")
    ledger.close()
    with sqlite3.connect(snapshot) as source, sqlite3.connect(path) as target:
        source.backup(target)
    restored = ReadingLedger(path)
    assert restored.ingest("iot_1", "sample-1", b"reading")["effect_applied"]
    restored.close()  # A second external effect is possible after full rollback.
