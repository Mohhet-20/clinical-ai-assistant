"""Measure pipeline quality against the annotated synthetic gold set.

    python evaluate.py                      # report
    python evaluate.py --json report.json   # also write machine-readable results
    python evaluate.py --gate               # exit 1 if any metric is below THRESHOLDS (used in CI)

Runs fully offline (rules mode, no PubMed). Gold labels in eval/gold.jsonl are
clinical truth written independently of the system's output, so failures are
real misses to investigate - not label noise to tune away."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("PUBMED_LIVE", "false")
os.environ.pop("OPENAI_API_KEY", None)

from app import agent  # noqa: E402

GOLD = Path(__file__).parent / "eval" / "gold.jsonl"
# Regression floors. Raise them as the system improves; never lower them to make a change pass.
THRESHOLDS = {"entity_precision": 0.95, "entity_recall": 0.95, "negation_accuracy": 0.95, "urgent_sensitivity": 1.0,
              "urgent_specificity": 0.9, "vitals_accuracy": 0.95, "top_condition_accuracy": 0.9, "score_accuracy": 1.0}


def _ratio(a: int, b: int) -> float:
    return round(a / b, 3) if b else 1.0


def evaluate(path: Path = GOLD) -> dict:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    tp = fn = fp = neg_ok = neg_total = 0
    urg = {"tp": 0, "fn": 0, "tn": 0, "fp": 0}
    vit_ok = vit_total = cond_ok = cond_total = score_ok = score_total = 0
    failures: list[dict] = []
    for c in cases:
        r = agent.run_agent(c["text"])
        found = set(r["symptoms"] + r["conditions"] + r["medications"] + r["risk_factors"])
        miss = [e for e in c["present"] if e not in found]
        wrong = [e for e in c["absent"] if e in found]
        tp, fn, fp = tp + len(c["present"]) - len(miss), fn + len(miss), fp + len(wrong)
        neg_total, neg_ok = neg_total + len(c["absent"]), neg_ok + len(c["absent"]) - len(wrong)
        urg[("tp" if r["urgent_attention"] else "fn") if c["urgent"] else ("fp" if r["urgent_attention"] else "tn")] += 1
        bad_vitals = {k: (v, r["vitals"].get(k)) for k, v in c.get("vitals", {}).items() if r["vitals"].get(k) != v}
        vit_total, vit_ok = vit_total + len(c.get("vitals", {})), vit_ok + len(c.get("vitals", {})) - len(bad_vitals)
        top = r["possible_conditions"][0]["condition"] if r["possible_conditions"] else None
        cond_miss = "top_condition" in c and not (top or "").startswith(c["top_condition"])
        if "top_condition" in c:
            cond_total, cond_ok = cond_total + 1, cond_ok + (not cond_miss)
        score_miss = {}
        if "news2" in c:
            score_total += 1
            got = r["scores"]["news2"]["score"]
            score_ok += got == c["news2"]
            if got != c["news2"]:
                score_miss["news2"] = (c["news2"], got)
        if "egfr" in c:
            score_total += 1
            got = (r["scores"].get("egfr") or {}).get("value")
            score_ok += got == c["egfr"]
            if got != c["egfr"]:
                score_miss["egfr"] = (c["egfr"], got)
        if miss or wrong or bad_vitals or cond_miss or score_miss or r["urgent_attention"] != c["urgent"]:
            failures.append({"id": c["id"], "missed": miss, "false_positive": wrong, "vitals": bad_vitals, "urgent": (c["urgent"], r["urgent_attention"]),
                             "top_condition": (c.get("top_condition"), top) if cond_miss else None, "scores": score_miss or None})
    p, rc = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
    metrics = {"entity_precision": p, "entity_recall": rc, "entity_f1": round(2 * p * rc / (p + rc), 3) if p + rc else 0.0,
               "negation_accuracy": _ratio(neg_ok, neg_total), "urgent_sensitivity": _ratio(urg["tp"], urg["tp"] + urg["fn"]),
               "urgent_specificity": _ratio(urg["tn"], urg["tn"] + urg["fp"]), "vitals_accuracy": _ratio(vit_ok, vit_total),
               "top_condition_accuracy": _ratio(cond_ok, cond_total), "score_accuracy": _ratio(score_ok, score_total)}
    return {"cases": len(cases), "metrics": metrics, "counts": {"entities": tp + fn, "negations": neg_total, "urgent": urg, "vitals": vit_total,
                                                                "conditions": cond_total, "scores": score_total}, "failures": failures}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--gate", action="store_true")
    args = ap.parse_args()
    rep = evaluate()
    print(f"Gold cases: {rep['cases']}\n")
    print(f"{'metric':26} {'value':>7} {'floor':>7}")
    below = []
    for k, v in rep["metrics"].items():
        floor = THRESHOLDS.get(k)
        flag = "" if floor is None or v >= floor else "  BELOW FLOOR"
        if flag:
            below.append(k)
        print(f"{k:26} {v:7.3f} {floor if floor is not None else '':>7}{flag}")
    for f in rep["failures"]:
        print("  miss:", json.dumps(f, ensure_ascii=False))
    if args.json:
        args.json.write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    return 1 if args.gate and below else 0


if __name__ == "__main__":
    sys.exit(main())
