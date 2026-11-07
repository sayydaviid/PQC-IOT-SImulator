"""Security regressions: faults exercise persisted files, not mirrored formulas."""

import os

import pytest

from pqc_iot_simulator.pqc_iot_sim.components.recovery import (
    ClientHandshake,
    Gateway,
    Identity,
    Observer,
    POLICIES,
    Rejected,
    Root,
    SealedStore,
    Sender,
    Session,
    handshake,
)
from pqc_iot_simulator.pqc_iot_sim.core.recovery_experiment import (
    FAULTS,
    fault_case,
    restore_or_renew,
    security_gates,
    verdict,
)


def sender_at(path, policy):
    store = SealedStore(path, os.urandom(32))
    sender = Sender(
        Session(os.urandom(32), "test-epoch", os.urandom(8), 100),
        Root(os.urandom(32), "test-root", 100),
        store,
        policy,
        16,
    )
    sender.checkpoint()
    return sender


def test_checkpoint_restoration_leaks_despite_authenticated_storage(tmp_path):
    sender = sender_at(tmp_path, "checkpoint")
    saved = (tmp_path / "state").read_bytes()
    observer = Observer()
    plaintext = b"known plaintext!"
    record = sender.encrypt(plaintext)
    observer.observe(sender.session, record, plaintext)
    sender.checkpoint()
    (tmp_path / "state").write_bytes(saved)
    restored = Sender.restore(sender.store, "checkpoint")
    plaintext = b"other plaintext!"
    record = restored.encrypt(plaintext)
    observer.observe(restored.session, record, plaintext)
    assert observer.reused == 1
    assert observer.known_plaintext_recoveries == 1


def test_second_encryption_of_identical_plaintext_still_reuses_nonce(tmp_path):
    sender = sender_at(tmp_path, "checkpoint")
    observer = Observer()
    plaintext = b"same sensor value"
    record = sender.encrypt(plaintext)
    observer.observe(sender.session, record, plaintext)
    restored = Sender.restore(sender.store, "checkpoint")
    repeated = restored.encrypt(plaintext)
    assert repeated == record  # Deterministic AEAD output is not a new nonce.
    observer.observe(restored.session, repeated, plaintext)
    assert observer.reused == 1
    assert observer.known_plaintext_recoveries == 0


@pytest.mark.parametrize("policy", ["persist_each", "reserve_blocks"])
def test_partial_use_and_crash_before_encrypt_skip_reserved_nonces(tmp_path, policy):
    sender = sender_at(tmp_path, policy)
    sender.encrypt(b"one")
    restored = Sender.restore(sender.store, policy, 16)
    assert restored.session.counter > 0
    restored.reserve()
    before = restored.session.counter
    after_crash = Sender.restore(sender.store, policy, 16)
    assert after_crash.session.counter > before
    assert after_crash.encrypt(b"after crash")["header"]["counter"] > before


def test_torn_atomic_replacement_leaves_previous_checkpoint(tmp_path, monkeypatch):
    sender = sender_at(tmp_path, "checkpoint")
    raw = (tmp_path / "state").read_bytes()
    sender.encrypt(b"one")

    def fail_replace(*args):
        raise OSError("injected crash before rename")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError):
        sender.checkpoint()
    assert (tmp_path / "state").read_bytes() == raw
    assert not list(tmp_path.glob(".pending-*"))
    assert Sender.restore(sender.store, "checkpoint").session.counter == 0


def test_store_rejects_tampering_and_cross_file_substitution(tmp_path):
    sender = sender_at(tmp_path, "persist_each")
    (tmp_path / "state").write_bytes((tmp_path / "journal").read_bytes())
    with pytest.raises(Rejected):
        Sender.restore(sender.store, "persist_each")


@pytest.mark.parametrize("policy", ["psk_resume", "pqc_resume", "full_pqc"])
def test_fresh_key_policies_do_not_persist_old_traffic_keys(tmp_path, policy):
    sender = sender_at(tmp_path, policy)
    state = sender.store.read("state")
    assert set(state) == {"root"}
    assert sender.session.key.hex().encode() not in str(state).encode()


@pytest.mark.parametrize("policy", ["persist_each", "reserve_blocks"])
def test_failed_durable_reservation_stops_before_encrypt(tmp_path, monkeypatch, policy):
    sender = sender_at(tmp_path, policy)
    store = sender.store

    def failed_write(*args):
        raise OSError("injected persistence failure")

    monkeypatch.setattr(store, "write", failed_write)
    for _ in range(2):  # A retry in the same process must also fail closed.
        with pytest.raises(OSError):
            sender.encrypt(b"must not be encrypted")
    assert sender.session.counter == 0
    assert sender.ceiling == 0
    assert store.read("journal")["next"] == 0


@pytest.fixture(scope="module")
def identities():
    try:
        __import__("oqs")
    except ImportError:
        pytest.fail("real liboqs bindings required; PQC tests cannot be skipped")
    return Identity.generate(), Identity.generate()


@pytest.mark.parametrize("policy", POLICIES)
@pytest.mark.parametrize("fault", FAULTS)
def test_real_pqc_fault_matrix(tmp_path, identities, policy, fault):
    row = fault_case(tmp_path, policy, fault, *identities, os.urandom(32))
    vulnerable = (
        policy == "checkpoint" and fault in ("power_loss", "client_storage_rollback")
    ) or (
        policy in ("persist_each", "reserve_blocks")
        and fault == "client_storage_rollback"
    )
    assert row["reused_key_nonce"] == (8 if vulnerable else 0)
    assert row["known_plaintext_recoveries"] == (8 if vulnerable else 0)
    assert row["accepted_after_restart"] == (0 if vulnerable else 8)
    assert row["full_handshake_fallback"] == (fault == "torn_checkpoint")


def test_real_pqc_security_gates_and_registered_verdict(tmp_path, identities):
    key = os.urandom(32)
    checks = security_gates(tmp_path / "gates", *identities, key)
    assert checks and all(c["pass"] for c in checks)
    rows = [
        fault_case(tmp_path / policy / fault, policy, fault, *identities, key)
        for policy in POLICIES
        for fault in FAULTS
    ]
    result = verdict(rows, checks)
    assert result["status"] == "SUPPORTED_IN_TESTED_MODEL"
    # A real confidentiality failure must invalidate the result, even if all
    # other rows and byte savings look favorable.
    next(r for r in rows if r["policy"] == "pqc_resume")["reused_key_nonce"] = 1
    assert verdict(rows, checks)["status"] == "FAILED_GATE"


@pytest.mark.parametrize("policy", ["psk_resume", "pqc_resume"])
def test_gateway_ledger_loss_forces_full_reauthentication(tmp_path, identities, policy):
    identity, server = identities
    gateway = Gateway(server, identity.public)
    client = ClientHandshake(identity, server.public, "full_pqc")
    session, _ = handshake(gateway, client)
    store = SealedStore(tmp_path, os.urandom(32))
    sender = Sender(session, client.root, store, policy)
    sender.checkpoint()
    old_epoch = session.epoch
    del gateway
    empty_gateway = Gateway(server, identity.public)
    restored, metrics, fallback = restore_or_renew(
        store, policy, empty_gateway, identity, server.public, 1, 32
    )
    assert fallback
    assert metrics["application_framed_bytes"] > 0
    assert restored.session.epoch != old_epoch
    assert (
        empty_gateway.accept(restored.encrypt(b"after gateway reboot", 1), 1)
        == b"after gateway reboot"
    )
