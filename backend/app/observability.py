"""Request correlation, PHI-safe structured logging and Prometheus metrics.

Logs and metrics carry only method, route template, status, latency and the
request id - never request bodies, notes, file names or model inputs."""
from __future__ import annotations

import contextvars
import json
import logging
import re
import threading
import time
import uuid
from collections import defaultdict
from typing import Any

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def new_request_id(incoming: str | None) -> str:
    return incoming if incoming and _VALID_ID.match(incoming) else uuid.uuid4().hex


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + "Z",
                               "level": record.levelname, "logger": record.name, "msg": record.getMessage(),
                               "request_id": request_id_var.get()}
        for key in ("method", "route", "status", "ms"):
            if hasattr(record, key):
                out[key] = getattr(record, key)
        if record.exc_info and record.exc_info[0]:
            out["exc_type"] = record.exc_info[0].__name__   # type only: tracebacks can echo PHI from locals/messages
        return json.dumps(out)


def configure_logging(fmt: str = "json", level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter() if fmt == "json" else logging.Formatter("%(levelname)s %(name)s [%(request_id)s] %(message)s"))
    if fmt != "json":
        handler.addFilter(lambda r: setattr(r, "request_id", request_id_var.get()) or True)
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    logging.getLogger("uvicorn.access").disabled = True   # replaced by our PHI-safe access log


# ---------------------------------------------------------------- metrics
_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.requests: dict[tuple[str, str, str], int] = defaultdict(int)
        self.latency: dict[tuple[str, str], list[float]] = {}
        self.events: dict[str, int] = defaultdict(int)
        self.started = time.time()

    def observe(self, method: str, route: str, status: int, seconds: float) -> None:
        with self._lock:
            self.requests[(method, route, str(status))] += 1
            h = self.latency.setdefault((method, route), [0.0] * (len(_BUCKETS) + 2))  # buckets..., sum, count
            for i, b in enumerate(_BUCKETS):
                if seconds <= b:
                    h[i] += 1
            h[-2] += seconds
            h[-1] += 1

    def inc(self, event: str, n: int = 1) -> None:
        with self._lock:
            self.events[event] += n

    def render(self) -> str:
        lines = ["# HELP clarity_http_requests_total HTTP requests by route and status.", "# TYPE clarity_http_requests_total counter"]
        with self._lock:
            for (m, r, s), n in sorted(self.requests.items()):
                lines.append(f'clarity_http_requests_total{{method="{m}",route="{r}",status="{s}"}} {n}')
            lines += ["# HELP clarity_http_request_duration_seconds Request latency.", "# TYPE clarity_http_request_duration_seconds histogram"]
            for (m, r), h in sorted(self.latency.items()):
                for i, b in enumerate(_BUCKETS):
                    lines.append(f'clarity_http_request_duration_seconds_bucket{{method="{m}",route="{r}",le="{b}"}} {int(h[i])}')
                lines.append(f'clarity_http_request_duration_seconds_bucket{{method="{m}",route="{r}",le="+Inf"}} {int(h[-1])}')
                lines.append(f'clarity_http_request_duration_seconds_sum{{method="{m}",route="{r}"}} {h[-2]:.6f}')
                lines.append(f'clarity_http_request_duration_seconds_count{{method="{m}",route="{r}"}} {int(h[-1])}')
            lines += ["# HELP clarity_events_total Clinical pipeline events (analyses, urgent flags, LLM fallbacks, PHI redactions).",
                      "# TYPE clarity_events_total counter"]
            for e, n in sorted(self.events.items()):
                lines.append(f'clarity_events_total{{event="{e}"}} {n}')
        lines += ["# TYPE clarity_uptime_seconds gauge", f"clarity_uptime_seconds {time.time() - self.started:.0f}"]
        return "\n".join(lines) + "\n"


METRICS = Metrics()
