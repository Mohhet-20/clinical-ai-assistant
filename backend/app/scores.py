"""Validated, deterministic clinical scores computed from parsed findings.

    NEWS2  - Royal College of Physicians National Early Warning Score 2 (2017), SpO2 scale 1
    qSOFA  - Sepsis-3 quick SOFA (Singer et al., JAMA 2016)
    eGFR   - CKD-EPI 2021 creatinine equation, race-free (Inker et al., NEJM 2021)

Unlike the ML models these are published rule sets that clinicians already
use, so they are shown as scores rather than "signals". A score with missing
parameters is reported as *incomplete* with the parameters needed; its
partial total is a lower bound, never a reassurance."""
from __future__ import annotations

import re
from typing import Any

_ALTERED = re.compile(r"\b(?:confus(?:ed|ion)|disorient(?:ed|ation)|drows(?:y|iness)|letharg(?:ic|y)|obtunded|unresponsive|"
                      r"responds? (?:only )?to (?:voice|pain)|gcs\s*(?:of\s*)?(?:[3-9]|1[0-4])\b|altered mental|new delirium)", re.I)
_NOT_ALTERED = re.compile(r"\b(?:alert(?: and oriented)?|a\s*&\s*o\s*x\s*[34]|aox[34]|gcs\s*(?:of\s*)?15)\b", re.I)
_OXYGEN = re.compile(r"\b(?:on (?:supplemental )?oxygen|on o2|\d+(?:\.\d+)?\s*l(?:/min)?\s*(?:o2|oxygen|nc|via)|nasal cannula|"
                     r"non-?rebreather|venturi|face ?mask|hfnc|high-flow)\b", re.I)
_ROOM_AIR = re.compile(r"\b(?:on room air|\bra\b|room air)\b", re.I)


def consciousness(text: str) -> str | None:
    """'cvpu' (new confusion/voice/pain/unresponsive), 'alert', or None when the record does not say."""
    from .nlp import affirmed_mention
    if _ALTERED.search(text) and any(affirmed_mention(text, m.group(0)) for m in _ALTERED.finditer(text)):
        return "cvpu"
    return "alert" if _NOT_ALTERED.search(text) else None


def supplemental_oxygen(text: str) -> bool | None:
    if _OXYGEN.search(text):
        return True
    return False if _ROOM_AIR.search(text) else None


def _band(value: float, bands: list[tuple[float, int]], top: int) -> int:
    for upper, points in bands:
        if value <= upper:
            return points
    return top


def news2(v: dict[str, Any], text: str) -> dict[str, Any]:
    parts: dict[str, int] = {}
    if "respiratory_rate" in v:
        parts["respiratory_rate"] = _band(v["respiratory_rate"], [(8, 3), (11, 1), (20, 0), (24, 2)], 3)
    if "spo2" in v:
        parts["spo2"] = _band(v["spo2"], [(91, 3), (93, 2), (95, 1)], 0)
    if "systolic" in v:
        parts["systolic"] = _band(v["systolic"], [(90, 3), (100, 2), (110, 1), (219, 0)], 3)
    if "heart_rate" in v:
        parts["heart_rate"] = _band(v["heart_rate"], [(40, 3), (50, 1), (90, 0), (110, 1), (130, 2)], 3)
    if "temperature" in v:
        parts["temperature"] = _band(v["temperature"], [(35.0, 3), (36.0, 1), (38.0, 0), (39.0, 1)], 2)
    o2, avpu = supplemental_oxygen(text), consciousness(text)
    if o2 is not None:
        parts["supplemental_oxygen"] = 2 if o2 else 0
    if avpu is not None:
        parts["consciousness"] = 3 if avpu == "cvpu" else 0
    required = ["respiratory_rate", "spo2", "systolic", "heart_rate", "temperature", "supplemental_oxygen", "consciousness"]
    missing = [p for p in required if p not in parts]
    total = sum(parts.values())
    if total >= 7:
        risk, response = "high", "Emergency assessment by a clinical team with critical-care competencies."
    elif total >= 5:
        risk, response = "medium", "Urgent review by a clinician skilled in assessing acute illness."
    elif any(p == 3 for p in parts.values()):
        risk, response = "low-medium", "A single parameter scores 3: urgent ward-based review."
    else:
        risk, response = "low", "Continue routine monitoring per local policy."
    return {"name": "NEWS2", "score": total, "risk": risk, "response": response, "components": parts, "complete": not missing,
            "missing": missing, "reference": "Royal College of Physicians. National Early Warning Score (NEWS) 2. 2017.",
            "note": None if not missing else f"Incomplete: {', '.join(m.replace('_', ' ') for m in missing)} not documented, so {total} is a lower bound."}


def qsofa(v: dict[str, Any], text: str) -> dict[str, Any]:
    parts: dict[str, int] = {}
    if "respiratory_rate" in v:
        parts["respiratory_rate_ge_22"] = int(v["respiratory_rate"] >= 22)
    if "systolic" in v:
        parts["systolic_le_100"] = int(v["systolic"] <= 100)
    avpu = consciousness(text)
    if avpu is not None:
        parts["altered_mentation"] = int(avpu == "cvpu")
    missing = [p for p in ("respiratory_rate_ge_22", "systolic_le_100", "altered_mentation") if p not in parts]
    total = sum(parts.values())
    return {"name": "qSOFA", "score": total, "positive": total >= 2, "components": parts, "complete": not missing, "missing": missing,
            "interpretation": "≥2 with suspected infection identifies higher risk of poor outcome; assess for sepsis." if total >= 2
            else "Below the qSOFA threshold; a negative qSOFA does not exclude sepsis.",
            "reference": "Singer M, et al. Sepsis-3. JAMA. 2016;315(8):801-810.",
            "note": None if not missing else f"Incomplete: {', '.join(m.split('_')[0] if m != 'altered_mentation' else 'mentation' for m in missing)} not documented."}


def egfr(v: dict[str, Any]) -> dict[str, Any] | None:
    scr, age, sex = v.get("creatinine"), v.get("age"), v.get("sex")
    if scr is None:
        return None
    missing = [n for n, x in (("age", age), ("sex", sex)) if x is None]
    if missing:
        return {"name": "eGFR (CKD-EPI 2021)", "value": None, "complete": False, "missing": missing,
                "note": f"Creatinine found, but {' and '.join(missing)} not documented; eGFR not calculated."}
    female = sex == 0
    kappa, alpha = (0.7, -0.241) if female else (0.9, -0.302)
    ratio = scr / kappa
    value = 142 * min(ratio, 1) ** alpha * max(ratio, 1) ** -1.200 * 0.9938 ** age * (1.012 if female else 1)
    stage = next(s for lim, s in ((90, "G1"), (60, "G2"), (45, "G3a"), (30, "G3b"), (15, "G4"), (0, "G5")) if value >= lim)
    return {"name": "eGFR (CKD-EPI 2021)", "value": round(value), "unit": "mL/min/1.73m²", "stage": stage, "complete": True, "missing": [],
            "inputs": {"creatinine_mg_dl": scr, "age": age, "sex": "female" if female else "male"},
            "interpretation": "CKD requires persistence for >3 months and/or markers of kidney damage; a single value does not stage CKD.",
            "reference": "Inker LA, et al. N Engl J Med. 2021;385:1737-1749."}


def compute(v: dict[str, Any], text: str) -> dict[str, Any]:
    out: dict[str, Any] = {"news2": news2(v, text), "qsofa": qsofa(v, text)}
    e = egfr(v)
    if e:
        out["egfr"] = e
    return out


def urgent_from_scores(s: dict[str, Any]) -> list[str]:
    reasons = []
    n = s["news2"]
    if n["score"] >= 7:
        reasons.append(f"NEWS2 {n['score']}{'' if n['complete'] else '+'} (high clinical risk)")
    elif n["score"] >= 5:
        reasons.append(f"NEWS2 {n['score']}{'' if n['complete'] else '+'} (medium clinical risk, urgent review threshold)")
    if s["qsofa"]["positive"]:
        reasons.append(f"qSOFA {s['qsofa']['score']} (≥2: assess for sepsis)")
    e = s.get("egfr")
    if e and e.get("value") is not None and e["value"] < 15:
        reasons.append(f"eGFR {e['value']} mL/min/1.73m² (G5 range)")
    return reasons
