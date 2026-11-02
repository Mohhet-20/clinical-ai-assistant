"""Tamper-evident audit trail (append-only JSONL, SHA-256 hash chain).

Each record holds who/when/what and *hashes* of inputs plus structured outcome
metadata (risk levels, flags, model versions) - never clinical free text - so
the log itself is not a PHI store. Editing, deleting or reordering any line
breaks the chain, which ``verify()`` reports.

    AUDIT_LOG        true (default) | false
    AUDIT_LOG_PATH   default backend/logs/audit.jsonl"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from .observability import request_id_var

log = logging.getLogger("clinical.audit")
GENESIS = "0" * 64
_lock = threading.Lock()
_state: dict[str, Any] = {}   # path -> (seq, last hash), cached per path


def enabled() -> bool:
    return os.getenv("AUDIT_LOG", "true").lower() not in ("0", "false", "no", "off")


def path() -> Path:
    return Path(os.getenv("AUDIT_LOG_PATH") or Path(__file__).resolve().parents[1] / "logs" / "audit.jsonl")


def sha256(data: str | bytes) -> str:
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def _digest(record: dict[str, Any]) -> str:
    body = {k: v for k, v in record.items() if k != "hash"}
    return sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=str))


def _tail(p: Path) -> tuple[int, str]:
    if not p.exists():
        return 0, GENESIS
    last = None
    with p.open("rb") as fh:
        for line in fh:
            if line.strip():
                last = line
    if last is None:
        return 0, GENESIS
    rec = json.loads(last)
    return int(rec["seq"]), rec["hash"]


def record(event: str, actor: str, data: dict[str, Any]) -> dict[str, Any] | None:
    """Append one event. Audit failures are logged, never raised to the caller."""
    if not enabled():
        return None
    p = path()
    try:
        with _lock:
            key = str(p)
            if key not in _state:
                p.parent.mkdir(parents=True, exist_ok=True)
                _state[key] = _tail(p)
            seq, prev = _state[key]
            rec = {"seq": seq + 1, "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"),
                   "request_id": request_id_var.get(), "actor": actor, "event": event, "data": data, "prev_hash": prev}
            rec["hash"] = _digest(rec)
            with p.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, separators=(",", ":"), default=str) + "\n")
            _state[key] = (rec["seq"], rec["hash"])
            return rec
    except Exception as exc:  # noqa: BLE001 - auditing must not take the clinical path down
        log.error("Audit write failed (%s)", type(exc).__name__)
        return None


def verify() -> dict[str, Any]:
    p = path()
    if not p.exists():
        return {"enabled": enabled(), "valid": True, "records": 0, "head": GENESIS}
    prev, count = GENESIS, 0
    with p.open("r", encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                return {"enabled": enabled(), "valid": False, "records": count, "broken_at_line": n, "reason": "unparseable record"}
            if rec.get("prev_hash") != prev or _digest(rec) != rec.get("hash") or rec.get("seq") != count + 1:
                return {"enabled": enabled(), "valid": False, "records": count, "broken_at_line": n, "reason": "hash chain mismatch"}
            prev, count = rec["hash"], count + 1
    return {"enabled": enabled(), "valid": True, "records": count, "head": prev}


def recent(limit: int = 50, event: str | None = None, request_id: str | None = None) -> list[dict[str, Any]]:
    p = path()
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rec = json.loads(line)
                if (event is None or rec["event"] == event) and (request_id is None or rec["request_id"] == request_id):
                    out.append(rec)
    return out[-limit:][::-1]


def reset_cache() -> None:
    """Forget cached chain heads (tests switch AUDIT_LOG_PATH between runs)."""
    with _lock:
        _state.clear()
