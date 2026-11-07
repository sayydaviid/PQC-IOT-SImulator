"""Durable application idempotency. This ledger is NOT rollback-resistant."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path


class ReadingConflict(ValueError):
    pass


class ReadingLedger:
    def __init__(self, path: Path, deduplicate=True):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.connection = sqlite3.connect(path, timeout=10, isolation_level=None)
        os.chmod(path, 0o600)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS readings (device TEXT, id TEXT, digest TEXT, PRIMARY KEY(device,id))"
        )
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS effects (device TEXT, id TEXT, digest TEXT)"
        )
        self.deduplicate = deduplicate

    def ingest(self, device: str, reading_id: str, payload: bytes) -> dict:
        digest = hashlib.sha256(payload).hexdigest()
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            old = self.connection.execute(
                "SELECT digest FROM readings WHERE device=? AND id=?",
                (device, reading_id),
            ).fetchone()
            if old and old[0] != digest:
                raise ReadingConflict("same reading ID has different content")
            duplicate = old is not None
            if not old:
                self.connection.execute(
                    "INSERT INTO readings VALUES (?,?,?)", (device, reading_id, digest)
                )
            if not duplicate or not self.deduplicate:
                self.connection.execute(
                    "INSERT INTO effects VALUES (?,?,?)", (device, reading_id, digest)
                )
            self.connection.execute("COMMIT")  # Durable decision BEFORE ACK.
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        return {
            "reading_id": reading_id,
            "sha256": digest,
            "duplicate": duplicate,
            "effect_applied": not duplicate or not self.deduplicate,
        }

    def counts(self):
        unique = self.connection.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
        effects = self.connection.execute("SELECT COUNT(*) FROM effects").fetchone()[0]
        return {
            "unique_readings": unique,
            "application_effects": effects,
            "duplicate_effects": effects - unique,
        }

    def close(self):
        self.connection.close()
