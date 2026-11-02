"""Precompute the UI's offline demo results by running the real pipeline on the shared sample cases.

    python export_demo.py      # writes ../frontend/src/demo-results.json

The UI shows these only when the API cannot be reached (e.g. a free-tier cold
start) and labels them "Offline demo: precomputed". They are genuine pipeline
outputs in rules mode, not hand-written mock-ups. Re-run after pipeline changes."""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ["PUBMED_LIVE"] = "false"
os.environ.pop("OPENAI_API_KEY", None)

from app import agent, rag  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "frontend" / "src" / "samples.json"
OUT = ROOT / "frontend" / "src" / "demo-results.json"


def main() -> None:
    rag.INDEX.build()
    out = {}
    for s in json.loads(SAMPLES.read_text(encoding="utf-8")):
        features = {k: float(v) for k, v in s["features"].items()}
        result = agent.run_agent(s["text"], features, {"input_modality": "text", "request_id": f"demo-{s['id']}"})
        out[s["id"]] = {**result, "case_id": None}
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB, {len(out)} cases)")


if __name__ == "__main__":
    main()
