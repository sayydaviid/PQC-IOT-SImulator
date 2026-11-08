"""Reproducible security gates and counter/rollback experiments using real PQC."""

from __future__ import annotations

import copy
import statistics
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..crypto.session import ClientHandshake
from ..crypto.session import Gateway
from ..crypto.session import Identity
from ..crypto.session import Observer
from ..crypto.session import Rejected
from ..crypto.session import Root
from ..crypto.session import SealedStore
from ..crypto.session import Sender
from ..crypto.session import b64
from ..crypto.session import derive
from ..crypto.session import encode
from ..crypto.session import handshake
from ..crypto.session import unb64

FAULTS = ("clean_restart", "power_loss", "client_storage_rollback", "torn_checkpoint")


def restore_or_renew(store, policy, gateway, identity, server_public, now, block_size):
    """No optimistic record before key confirmation. Corruption triggers full auth."""
    fallback = False
    metrics = {"application_framed_bytes": 0, "host_handshake_ms": 0.0}
    try:
        saved = store.read("state")
        root = Root.load(saved["root"])
        if policy in ("full_pqc", "pqc_resume", "psk_resume"):
            client = ClientHandshake(
                identity, server_public, policy, root if policy != "full_pqc" else None
            )
            session, metrics = handshake(gateway, client, now)
            sender = Sender(session, client.root, store, policy, block_size)
        else:
            sender = Sender.restore(store, policy, block_size)
    except (Rejected, FileNotFoundError, KeyError, ValueError):
        fallback = True
        client = ClientHandshake(identity, server_public, "full_pqc")
        session, metrics = handshake(gateway, client, now)
        sender = Sender(session, client.root, store, policy, block_size)
    sender.checkpoint()
    return sender, metrics, fallback


def fault_case(
    directory,
    policy,
    fault,
    identity,
    server_identity,
    wrapping_key,
    messages=8,
    block_size=32,
):
    gateway = Gateway(server_identity, identity.public)
    client = ClientHandshake(identity, server_identity.public, "full_pqc")
    session, bootstrap = handshake(gateway, client)
    store = SealedStore(directory, wrapping_key)
    sender = Sender(session, client.root, store, policy, block_size)
    sender.checkpoint()
    snapshot = {
        p.name: p.read_bytes() for p in Path(directory).iterdir() if p.is_file()
    }
    observer = Observer()
    before_writes = store.writes
    for index in range(messages):
        plaintext = f"before:{index:08d}".encode()
        record = sender.encrypt(plaintext)
        observer.observe(sender.session, record, plaintext)
        assert gateway.accept(record, 0) == plaintext
    steady_writes = store.writes - before_writes
    if fault == "clean_restart":
        sender.checkpoint()
    elif fault == "client_storage_rollback":
        for name, raw in snapshot.items():
            (Path(directory) / name).write_bytes(raw)
    elif fault == "torn_checkpoint":
        (Path(directory) / "state").write_bytes(snapshot["state"][:19])
    elif fault != "power_loss":
        raise ValueError("unknown fault")
    # Drop the sender and reload authenticated files, never its Python counter.
    del sender
    sender, restart, fallback = restore_or_renew(
        store, policy, gateway, identity, server_identity.public, 1, block_size
    )
    accepted, rejected = 0, 0
    first_counter = sender.session.counter
    for index in range(messages):
        plaintext = f"after!:{index:08d}".encode()
        record = sender.encrypt(plaintext, 1)
        observer.observe(
            sender.session, record, plaintext
        )  # Observe before receiver rejection.
        try:
            assert gateway.accept(record, 1) == plaintext
            accepted += 1
        except Rejected:
            rejected += 1
    return {
        "policy": policy,
        "fault": fault,
        "messages_per_boot": messages,
        "block_size": block_size,
        "reused_key_nonce": observer.reused,
        "known_plaintext_recoveries": observer.known_plaintext_recoveries,
        "accepted_after_restart": accepted,
        "rejected_after_restart": rejected,
        "first_counter_after_restart": first_counter,
        "full_handshake_fallback": fallback,
        "bootstrap_framed_bytes": bootstrap["application_framed_bytes"],
        "restart_framed_bytes": restart["application_framed_bytes"],
        "restart_host_handshake_ms": restart["host_handshake_ms"],
        "steady_state_writes": steady_writes,
        "total_file_writes": store.writes,
        "total_file_bytes": store.bytes_written,
        "host_write_ms": store.host_write_ms,
    }


def security_gates(directory, identity, server_identity, wrapping_key):
    """Tampering/replay/expiry, crash ordering, root disclosure and gateway loss."""
    checks = []

    def rejected(name, operation):
        try:
            operation()
        except Rejected:
            checks.append({"check": name, "pass": True})
        else:
            checks.append({"check": name, "pass": False})

    def fixture(lifetime=3600, limit=10000):
        gateway = Gateway(server_identity, identity.public, lifetime, limit)
        client = ClientHandshake(identity, server_identity.public, "full_pqc")
        session, _ = handshake(gateway, client)
        return gateway, client, session

    for mode in ("full_pqc", "psk_resume", "pqc_resume"):
        gateway, first, _ = fixture()
        client = ClientHandshake(
            identity,
            server_identity.public,
            mode,
            first.root if mode != "full_pqc" else None,
        )
        reply = gateway.begin(client.hello, 1)
        changed = copy.deepcopy(reply)
        changed["expires"] += 10
        rejected(mode + ":tampered_server_limits", lambda: client.respond(changed))
        changed = copy.deepcopy(reply)
        changed["hello"]["mode"] = (
            "psk_resume" if mode != "psk_resume" else "pqc_resume"
        )
        rejected(mode + ":downgrade", lambda: client.respond(changed))
        other = ClientHandshake(
            identity,
            server_identity.public,
            mode,
            first.root if mode != "full_pqc" else None,
        )
        rejected(mode + ":old_reply_new_boot", lambda: other.respond(reply))
        final = client.respond(reply)
        ack = gateway.finish(final, 1)
        session = client.complete(ack)
        rejected(mode + ":replayed_finished", lambda: gateway.finish(final, 1))
        changed = {"finished": "0" * 64}
        rejected(mode + ":forged_server_finished", lambda: client.complete(changed))
        store = SealedStore(Path(directory) / mode, wrapping_key)
        sender = Sender(session, client.root, store, mode)
        record = sender.encrypt(b"synthetic-reading", 1)
        changed = copy.deepcopy(record)
        raw = bytearray(unb64(changed["ciphertext"]))
        raw[0] ^= 1
        changed["ciphertext"] = b64(bytes(raw))
        rejected(mode + ":ciphertext_forgery", lambda: gateway.accept(changed, 1))
        changed = copy.deepcopy(record)
        changed["header"]["device"] = "iot_2"
        rejected(mode + ":wrong_identity", lambda: gateway.accept(changed, 1))
        changed = copy.deepcopy(record)
        changed["header"]["counter"] += 1
        rejected(mode + ":changed_nonce", lambda: gateway.accept(changed, 1))
        assert gateway.accept(record, 1) == b"synthetic-reading"
        rejected(mode + ":identical_record_replay", lambda: gateway.accept(record, 1))
        old_record = record
        newer = ClientHandshake(
            identity,
            server_identity.public,
            mode,
            client.root if mode != "full_pqc" else None,
        )
        handshake(gateway, newer, 2)
        rejected(mode + ":old_epoch", lambda: gateway.accept(old_record, 2))
        unknown = Gateway(server_identity, identity.public)
        rejected(
            mode + ":gateway_lost_ledger_record", lambda: unknown.accept(old_record, 2)
        )
        if mode != "full_pqc":
            rejected(mode + ":gateway_lost_root", lambda: unknown.begin(newer.hello, 2))
            invalid = copy.deepcopy(newer.hello)
            invalid["binder"] = "0" * 64
            rejected(mode + ":forged_client_binder", lambda: gateway.begin(invalid, 2))

    # Invalid client authentication cannot install a traffic epoch.
    for mode in ("full_pqc", "psk_resume", "pqc_resume"):
        gateway, first, _ = fixture()
        previous_epoch = next(iter(gateway.sessions))
        client = ClientHandshake(
            identity,
            server_identity.public,
            mode,
            first.root if mode != "full_pqc" else None,
        )
        reply = gateway.begin(client.hello, 1)
        final = client.respond(reply)
        final["finished"] = "0" * 64
        rejected(mode + ":forged_client_finished", lambda: gateway.finish(final, 1))
        checks.append(
            {
                "check": mode + ":failure_does_not_install_key",
                "pass": next(iter(gateway.sessions)) == previous_epoch,
            }
        )
        client = ClientHandshake(
            identity,
            server_identity.public,
            mode,
            first.root if mode != "full_pqc" else None,
        )
        reply = gateway.begin(client.hello, 2)
        final = client.respond(reply)
        rejected(mode + ":challenge_timeout", lambda: gateway.finish(final, 32))

    wrong = Identity.generate()
    gateway, client, _ = fixture()
    rogue_client = ClientHandshake(wrong, server_identity.public, "full_pqc")
    reply = gateway.begin(rogue_client.hello, 1)
    final = rogue_client.respond(reply)
    rejected("full_pqc:unpinned_client_identity", lambda: gateway.finish(final, 1))
    rogue_gateway = Gateway(wrong, identity.public)
    reply = rogue_gateway.begin(client.hello, 1)
    rejected("full_pqc:unpinned_server_identity", lambda: client.respond(reply))

    # Client checkpoint rollback cannot extend server-side age or message budget.
    for mode in ("psk_resume", "pqc_resume"):
        gateway, client, session = fixture(lifetime=2, limit=1)
        saved_root = Root.load(client.root.dump())
        sender = Sender(
            session,
            client.root,
            SealedStore(Path(directory) / (mode + "budget"), wrapping_key),
            mode,
        )
        record = sender.encrypt(b"budget")
        gateway.accept(record, 0)
        resumed = ClientHandshake(identity, server_identity.public, mode, saved_root)
        rejected(
            mode + ":server_budget_rollback", lambda: gateway.begin(resumed.hello, 1)
        )
        gateway, client, _ = fixture(lifetime=2)
        resumed = ClientHandshake(identity, server_identity.public, mode, client.root)
        rejected(
            mode + ":server_expiry_rollback", lambda: gateway.begin(resumed.hello, 2)
        )
        reply = gateway.begin(resumed.hello, 1)
        final = resumed.respond(reply)
        rejected(mode + ":expiry_during_handshake", lambda: gateway.finish(final, 2))

    gateway, client, session = fixture(lifetime=2)
    sender = Sender(
        session,
        client.root,
        SealedStore(Path(directory) / "expiredrecord", wrapping_key),
        "checkpoint",
    )
    record = sender.encrypt(b"expires on receiver", 0)
    rejected("record:gateway_expiry", lambda: gateway.accept(record, 2))
    rejected("record:client_expiry", lambda: sender.encrypt(b"expired", 2))

    for policy in ("persist_each", "reserve_blocks"):
        gateway, client, session = fixture()
        store = SealedStore(Path(directory) / (policy + "crash"), wrapping_key)
        sender = Sender(session, client.root, store, policy, 16)
        sender.checkpoint()
        sender.reserve()  # Inject crash after fsync BEFORE first encryption.
        restored = Sender.restore(store, policy, 16)
        checks.append(
            {
                "check": policy + ":crash_after_reservation",
                "pass": restored.session.counter
                == (1 if policy == "persist_each" else 16),
            }
        )
        record = restored.encrypt(b"post-crash")
        assert gateway.accept(record, 0) == b"post-crash"
        restored.session.counter = 2**32
        rejected(policy + ":counter_exhaustion", lambda: restored.encrypt(b"overflow"))
        raw = bytearray((store.directory / "journal").read_bytes())
        raw[-1] ^= 1
        (store.directory / "journal").write_bytes(raw)
        rejected(
            policy + ":tampered_journal", lambda: Sender.restore(store, policy, 16)
        )

    # Passive attacker: disclose only the retained PSK AFTER session completion.
    # For PQC resume, a failed PSK-only decrypt is a functional check, not an FS proof.
    for mode in ("psk_resume", "pqc_resume"):
        gateway, first, _ = fixture()
        saved_secret = first.root.secret
        client = ClientHandshake(identity, server_identity.public, mode, first.root)
        session, metrics = handshake(gateway, client, 1)
        sender = Sender(
            session,
            client.root,
            SealedStore(Path(directory) / (mode + "disclosure"), wrapping_key),
            mode,
        )
        plaintext = b"past synthetic sensor reading"
        record = sender.encrypt(plaintext, 1)
        candidate = derive(saved_secret, encode(metrics["transcript"]), "traffic")
        decrypted = False
        try:
            recovered = AESGCM(candidate).decrypt(
                session.prefix + bytes(4),
                unb64(record["ciphertext"]),
                encode(record["header"]),
            )
            decrypted = recovered == plaintext
        except InvalidTag:
            pass
        checks.append(
            {
                "check": mode + ":late_psk_only_decrypt",
                "pass": decrypted == (mode == "psk_resume"),
                "past_plaintext_recovered": decrypted,
            }
        )
    # Deliberately violate the fresh-entropy assumption for the PSK control.
    # Replaying the entire old server flight then regenerates its traffic key.
    gateway, first, _ = fixture()
    client = ClientHandshake(identity, server_identity.public, "psk_resume", first.root)
    reply = gateway.begin(client.hello, 1)
    final = client.respond(reply)
    ack = gateway.finish(final, 1)
    old_session = client.complete(ack)
    rolled_rng = ClientHandshake(
        identity, server_identity.public, "psk_resume", first.root
    )
    rolled_rng.hello = copy.deepcopy(client.hello)
    rolled_rng.respond(reply)
    repeated = rolled_rng.complete(ack)
    checks.append(
        {
            "check": "psk_resume:repeated_entropy_negative_control",
            "pass": old_session.key == repeated.key
            and old_session.prefix == repeated.prefix,
            "assumption_violated": "fresh client entropy; active replay of old handshake",
        }
    )
    return checks


def verdict(rows, checks):
    unsafe = [
        r
        for r in rows
        if r["policy"] == "checkpoint" and r["fault"] == "client_storage_rollback"
    ]
    rollback_safe = [
        r for r in rows if r["policy"] in ("psk_resume", "pqc_resume", "full_pqc")
    ]
    durable = [
        r
        for r in rows
        if r["policy"] in ("persist_each", "reserve_blocks")
        and r["fault"] == "power_loss"
    ]
    durable_rollback = [
        r
        for r in rows
        if r["policy"] in ("persist_each", "reserve_blocks")
        and r["fault"] == "client_storage_rollback"
    ]
    full = [
        r["restart_framed_bytes"]
        for r in rows
        if r["policy"] == "full_pqc" and r["fault"] != "torn_checkpoint"
    ]
    pqc = [
        r["restart_framed_bytes"]
        for r in rows
        if r["policy"] == "pqc_resume" and r["fault"] != "torn_checkpoint"
    ]
    criteria = {
        "negative_control_recovers_plaintext": bool(unsafe)
        and all(r["known_plaintext_recoveries"] > 0 for r in unsafe),
        "renewed_keys_no_nonce_reuse_all_delivered": bool(rollback_safe)
        and all(
            r["reused_key_nonce"] == 0
            and r["accepted_after_restart"] == r["messages_per_boot"]
            for r in rollback_safe
        ),
        "durable_counter_survives_power_loss": bool(durable)
        and all(
            r["reused_key_nonce"] == 0
            and r["accepted_after_restart"] == r["messages_per_boot"]
            for r in durable
        ),
        "durable_counter_not_rollback_proof": bool(durable_rollback)
        and all(r["reused_key_nonce"] > 0 for r in durable_rollback),
        "security_gates": bool(checks) and all(c["pass"] for c in checks),
        "pqc_resume_smaller_than_full": bool(pqc)
        and bool(full)
        and max(pqc) < min(full),
    }
    return {
        "status": "SUPPORTED_IN_TESTED_MODEL"
        if all(criteria.values())
        else "FAILED_GATE",
        "criteria": criteria,
        "median_resume_byte_reduction_pct": (
            100 * (1 - statistics.median(pqc) / statistics.median(full))
        )
        if pqc and full
        else None,
        "publication_novelty": "NOT_ESTABLISHED",
        "scope": "client rollback; live gateway authority; fresh entropy; no 0-RTT; no formal protocol proof",
    }
