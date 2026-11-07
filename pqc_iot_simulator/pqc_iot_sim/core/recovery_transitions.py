"""Phase 2: interrupted handshakes, wasted flights and application ACK loss.

Uses the frozen phase-1 crypto unchanged. These are logical fault boundaries
with actual encrypted files and PQC operations, not packet-loss measurements.
An application retry is intentionally distinct from a cryptographic replay.
"""

from __future__ import annotations

import json
from collections import Counter

from ..components.recovery import (
    FRAME,
    MODES,
    ClientHandshake,
    Gateway,
    Observer,
    Rejected,
    Root,
    Sender,
    encode,
)

SCENARIOS = (
    "no_fault",
    "after_client_hello",
    "after_server_hello",
    "after_client_finished",
    "after_gateway_commit",
    "after_key_confirmation",
    "after_checkpoint",
    "after_record_encryption",
    "lost_reading_ack",
    "torn_checkpoint",
    "gateway_lost_before_start",
)


class Interrupted(RuntimeError):
    """A single injected client interruption; it never carries secret state."""


class Flights:
    def __init__(self):
        self.bytes = 0
        self.types = []

    def sent(self, kind, value):
        self.bytes += FRAME.size + len(encode(value))
        self.types.append(kind)


def attempt(gateway, client, flights, now, stop=None):
    """Count messages sent, including a lost server confirmation, not CPU cost."""

    def interrupt(stage):
        if stage == stop:
            raise Interrupted(stage)

    flights.sent("client_hello", client.hello)
    interrupt("after_client_hello")
    reply = gateway.begin(client.hello, now)
    flights.sent("server_hello", reply)
    interrupt("after_server_hello")
    final = client.respond(reply)
    flights.sent("client_finished", final)
    interrupt("after_client_finished")
    ack = gateway.finish(final, now)
    flights.sent("server_finished", ack)
    interrupt("after_gateway_commit")
    session = client.complete(ack)
    interrupt("after_key_confirmation")
    return session


def recover(
    gateway, identity, server_public, store, policy, flights, now, force_full=False
):
    """Reconstruct from disk; count a failed resumption request before fallback."""
    fallback = False
    try:
        if force_full:
            raise Rejected("server already rejected the saved root")
        saved = store.read("state")
        root = Root.load(saved["root"])
        client = ClientHandshake(
            identity, server_public, policy, root if policy != "full_pqc" else None
        )
        session = attempt(gateway, client, flights, now)
    except (Rejected, FileNotFoundError, KeyError, ValueError):
        fallback = True
        client = ClientHandshake(identity, server_public, "full_pqc")
        session = attempt(gateway, client, flights, now)
    sender = Sender(session, client.root, store, policy)
    sender.checkpoint()
    return sender, fallback


def transition_case(store, policy, scenario, identity, server_identity):
    if policy not in MODES or scenario not in SCENARIOS:
        raise ValueError("unknown policy/scenario")
    gateway = Gateway(server_identity, identity.public)
    bootstrap = ClientHandshake(identity, server_identity.public, "full_pqc")
    session = attempt(gateway, bootstrap, Flights(), 0)
    sender = Sender(session, bootstrap.root, store, policy)
    observer = Observer()
    initial_plaintext = encode({"reading_id": "initial", "value": 19})
    initial_record = sender.encrypt(initial_plaintext, 0)
    observer.observe(sender.session, initial_record, initial_plaintext)
    if gateway.accept(initial_record, 0) != initial_plaintext:
        raise RuntimeError("bootstrap record verification failed")
    sender.checkpoint()
    durable_root = Root.load(store.read("state")["root"])
    del sender, session, bootstrap  # Recover from files, not a kept client counter.
    if scenario == "gateway_lost_before_start":
        gateway = Gateway(server_identity, identity.public)
    client = ClientHandshake(
        identity,
        server_identity.public,
        policy,
        durable_root if policy != "full_pqc" else None,
    )
    initial_flights, retry_flights = Flights(), Flights()
    interrupted, fallback, rejected_resume = False, False, False
    application = Counter()
    pending_reading = encode({"reading_id": "pending", "value": 23})
    writes_before = store.writes

    def deliver(sender, record):
        plaintext = gateway.accept(record, 2)
        if plaintext != pending_reading:
            raise RuntimeError("application plaintext verification failed")
        application[json.loads(plaintext)["reading_id"]] += 1

    try:
        session = attempt(gateway, client, initial_flights, 1, scenario)
        sender = Sender(session, client.root, store, policy)
        if scenario == "torn_checkpoint":
            # Corrupt a previously authenticated file, not a fabricated root.
            previous = (store.directory / "state").read_bytes()
            (store.directory / "state").write_bytes(previous[:19])
            raise Interrupted(scenario)
        if scenario == "after_checkpoint":
            sender.checkpoint()
            raise Interrupted(scenario)
        record = sender.encrypt(pending_reading, 1)
        observer.observe(sender.session, record, pending_reading)
        if scenario == "after_record_encryption":
            raise Interrupted(scenario)
        deliver(sender, record)
        if scenario == "lost_reading_ack":
            # Receiver accepted, client cannot distinguish this from a loss.
            # Retry the same application ID under a NEW cryptographic session.
            raise Interrupted(scenario)
        sender.checkpoint()
    except Interrupted:
        interrupted = True
    except Rejected:
        if scenario != "gateway_lost_before_start" or policy == "full_pqc":
            raise
        rejected_resume = True

    if interrupted or rejected_resume:
        # All volatile client state is discarded. The server authority survives
        # except in the explicit gateway-loss scenario.
        del client
        sender, fallback = recover(
            gateway,
            identity,
            server_identity.public,
            store,
            policy,
            retry_flights,
            2,
            force_full=rejected_resume,
        )
        record = sender.encrypt(pending_reading, 2)
        observer.observe(sender.session, record, pending_reading)
        deliver(sender, record)
        sender.checkpoint()
    stale_accepted = False
    try:
        gateway.accept(initial_record, 2)
        stale_accepted = True
    except Rejected:
        pass
    return {
        "policy": policy,
        "scenario": scenario,
        "client_interrupted": interrupted,
        "unknown_root_rejected": rejected_resume,
        "full_fallback": fallback,
        "nonce_reuses": observer.reused,
        "stale_record_accepted": stale_accepted,
        "application_acceptances": application["pending"],
        "application_duplicates": max(0, application["pending"] - 1),
        "initial_attempt_handshake_bytes": initial_flights.bytes,
        "retry_handshake_bytes": retry_flights.bytes,
        "total_handshake_bytes": initial_flights.bytes + retry_flights.bytes,
        "initial_flights_sent": initial_flights.types,
        "retry_flights_sent": retry_flights.types,
        "checkpoint_writes_after_bootstrap": store.writes - writes_before,
    }


def assess(rows):
    if not rows:
        raise ValueError("empty transition campaign")
    security = all(
        r["nonce_reuses"] == 0
        and not r["stale_record_accepted"]
        and r["application_acceptances"] >= 1
        for r in rows
    )
    ack_control = all(
        r["application_duplicates"] == (r["scenario"] == "lost_reading_ack")
        for r in rows
    )
    fallbacks = all(
        r["full_fallback"]
        == (
            r["scenario"] == "torn_checkpoint"
            or (
                r["scenario"] == "gateway_lost_before_start"
                and r["policy"] != "full_pqc"
            )
        )
        for r in rows
    )
    comparisons = []
    for repetition in sorted({r["repetition"] for r in rows}):
        for scenario in SCENARIOS:
            pair = {
                r["policy"]: r
                for r in rows
                if r["repetition"] == repetition and r["scenario"] == scenario
            }
            if set(pair) != set(MODES):
                raise ValueError("incomplete paired experiment")
            full, pqc = (
                pair["full_pqc"]["total_handshake_bytes"],
                pair["pqc_resume"]["total_handshake_bytes"],
            )
            comparisons.append(
                {
                    "repetition": repetition,
                    "scenario": scenario,
                    "full_bytes": full,
                    "pqc_bytes": pqc,
                    "pqc_saving_pct": 100 * (1 - pqc / full),
                }
            )
    return {
        "status": "PASS" if security and ack_control and fallbacks else "FAILED_GATE",
        "criteria": {
            "fresh_key_security_and_eventual_delivery": security,
            "lost_ack_duplicates_demonstrated": ack_control,
            "full_fallbacks_match_faults": fallbacks,
        },
        "pqc_always_smaller": all(c["pqc_saving_pct"] > 0 for c in comparisons),
        "byte_comparisons": comparisons,
        "scope": "one logical fault, bounded retry, live gateway or explicit root loss; no packet-loss or exactly-once guarantee",
    }
