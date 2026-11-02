"""Encrypted case history with retention.

Off by default: nothing clinical is persisted unless explicitly enabled.

    CASE_STORE              true to keep analysis results
    CASE_ENCRYPTION_KEY     required when enabled; Fernet key(s), comma-separated
                            (first encrypts, all decrypt - rotate by prepending a new key).
                            Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    CASE_RETENTION_DAYS     default 30; expired cases are purged on startup and on every write
    CASE_DB_PATH            default backend/logs/cases.db

The full result (including extracted text) is encrypted at rest with Fernet
(AES-128-CBC + HMAC-SHA256). Only non-identifying index metadata - owner,
timestamps, modality, condition labels, urgency, NEWS2 - is stored in clear so
worklists can be listed without decrypting every record. Owners see their
own cases; admins see all."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

_lock = threading.Lock()


def enabled() -> bool:
    return os.getenv("CASE_STORE", "false").lower() in ("1", "true", "yes", "on")


def validate_config() -> None:
    if not enabled():
        return
    if not os.getenv("CASE_ENCRYPTION_KEY"):
        raise RuntimeError("CASE_STORE=true requires CASE_ENCRYPTION_KEY; refusing to store clinical data unencrypted.")
    _cipher()   # raises on malformed keys


def retention_seconds() -> float:
    return float(os.getenv("CASE_RETENTION_DAYS", "30")) * 86400


def _cipher() -> MultiFernet:
    keys = [k.strip() for k in os.environ["CASE_ENCRYPTION_KEY"].split(",") if k.strip()]
    return MultiFernet([Fernet(k) for k in keys])


def _db() -> sqlite3.Connection:
    path = Path(os.getenv("CASE_DB_PATH") or Path(__file__).resolve().parents[1] / "logs" / "cases.db")
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""CREATE TABLE IF NOT EXISTS cases (
        id TEXT PRIMARY KEY, owner TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL,
        meta TEXT NOT NULL, blob BLOB NOT NULL)""")
    con.execute("CREATE INDEX IF NOT EXISTS cases_owner ON cases(owner, created)")
    return con


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    """Commit on success, roll back on error, and always close."""
    con = _db()
    try:
        with con:
            yield con
    finally:
        con.close()


def purge_expired(now: float | None = None) -> int:
    if not enabled():
        return 0
    with _lock, _conn() as con:
        return con.execute("DELETE FROM cases WHERE expires < ?", (now or time.time(),)).rowcount


def save(case_id: str, owner: str, result: dict[str, Any]) -> dict[str, Any] | None:
    if not enabled():
        return None
    now = time.time()
    meta = {"modality": result.get("input_modality"), "document_name": bool(result.get("document_name")),
            "conditions": [c["condition"] for c in result.get("possible_conditions", [])][:5], "urgent": result.get("urgent_attention"),
            "news2": (result.get("scores") or {}).get("news2", {}).get("score"), "risk": result.get("risk_score")}
    blob = _cipher().encrypt(json.dumps(result, default=str).encode())
    with _lock, _conn() as con:
        con.execute("DELETE FROM cases WHERE expires < ?", (now,))
        con.execute("INSERT INTO cases VALUES (?,?,?,?,?,?)", (case_id, owner, now, now + retention_seconds(), json.dumps(meta), blob))
    return {"id": case_id, "expires": now + retention_seconds()}


def _row(r: tuple) -> dict[str, Any]:
    return {"id": r[0], "owner": r[1], "created": r[2], "expires": r[3], **json.loads(r[4])}


def list_cases(owner: str | None, limit: int = 50) -> list[dict[str, Any]]:
    if not enabled():
        return []
    with _lock, _conn() as con:
        if owner:
            rows = con.execute("SELECT id, owner, created, expires, meta FROM cases WHERE expires >= ? AND owner = ? ORDER BY created DESC LIMIT ?",
                               (time.time(), owner, limit))
        else:
            rows = con.execute("SELECT id, owner, created, expires, meta FROM cases WHERE expires >= ? ORDER BY created DESC LIMIT ?", (time.time(), limit))
        return [_row(r) for r in rows]


def get(case_id: str, owner: str | None) -> dict[str, Any] | None:
    """Decrypted case, or None if missing, expired, or not owned (callers return 404 either way - no existence oracle)."""
    if not enabled():
        return None
    with _lock, _conn() as con:
        r = con.execute("SELECT id, owner, created, expires, meta, blob FROM cases WHERE id = ? AND expires >= ?", (case_id, time.time())).fetchone()
    if r is None or (owner and r[1] != owner):
        return None
    try:
        result = json.loads(_cipher().decrypt(r[5]))
    except InvalidToken:
        return {**_row(r[:5]), "result": None, "error": "Case could not be decrypted with the configured key(s)."}
    return {**_row(r[:5]), "result": result}


def delete(case_id: str, owner: str | None) -> bool:
    if not enabled():
        return False
    with _lock, _conn() as con:
        q, args = ("DELETE FROM cases WHERE id = ? AND owner = ?", (case_id, owner)) if owner else ("DELETE FROM cases WHERE id = ?", (case_id,))
        return con.execute(q, args).rowcount > 0
