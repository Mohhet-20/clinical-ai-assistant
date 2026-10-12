"""Clinical NLP layer: dictionary entity extraction with negation handling,
vital-sign / lab extraction from free text, and a transparent rule-based
differential ("possible conditions") generator."""
from __future__ import annotations

import re
from typing import Any

# phrase -> (category, canonical display name)
SIGNALS: dict[str, tuple[str, str]] = {
    # symptoms
    "chest pain": ("symptom", "Chest pain"), "chest pressure": ("symptom", "Chest pressure"),
    "chest tightness": ("symptom", "Chest pressure"),
    "shortness of breath": ("symptom", "Shortness of breath"), "breathlessness": ("symptom", "Shortness of breath"),
    "difficulty breathing": ("symptom", "Shortness of breath"),
    "fatigue": ("symptom", "Fatigue"), "tiredness": ("symptom", "Fatigue"),
    "thirst": ("symptom", "Increased thirst"), "polydipsia": ("symptom", "Increased thirst"),
    "frequent urination": ("symptom", "Frequent urination"), "polyuria": ("symptom", "Frequent urination"),
    "headache": ("symptom", "Headache"), "dizziness": ("symptom", "Dizziness"),
    "lightheadedness": ("symptom", "Dizziness"), "fainting": ("symptom", "Fainting"),
    "syncope": ("symptom", "Fainting"), "blurred vision": ("symptom", "Blurred vision"),
    "blurry vision": ("symptom", "Blurred vision"), "weight loss": ("symptom", "Unintended weight loss"),
    "nausea": ("symptom", "Nausea"), "sweating": ("symptom", "Sweating"),
    "cold sweat": ("symptom", "Sweating"), "palpitations": ("symptom", "Palpitations"),
    "cough": ("symptom", "Cough"), "wheezing": ("symptom", "Wheezing"), "wheeze": ("symptom", "Wheezing"),
    "swelling in legs": ("symptom", "Leg swelling"), "leg swelling": ("symptom", "Leg swelling"),
    "edema": ("symptom", "Leg swelling"), "pallor": ("symptom", "Pallor"), "fever": ("symptom", "Fever"),
    "numbness": ("symptom", "Numbness / tingling"), "tingling": ("symptom", "Numbness / tingling"),
    # conditions
    "diabetes": ("condition", "Diabetes"), "type 2 diabetes": ("condition", "Diabetes"),
    "prediabetes": ("condition", "Prediabetes"), "hypertension": ("condition", "Hypertension"),
    "high blood pressure": ("condition", "Hypertension"), "heart disease": ("condition", "Heart disease"),
    "coronary artery disease": ("condition", "Heart disease"), "myocardial infarction": ("condition", "Heart disease"),
    "heart failure": ("condition", "Heart failure"), "asthma": ("condition", "Asthma"),
    "copd": ("condition", "COPD"), "chronic kidney disease": ("condition", "Chronic kidney disease"),
    "hyperlipidemia": ("condition", "Hyperlipidemia"), "high cholesterol": ("condition", "Hyperlipidemia"),
    "anemia": ("condition", "Anemia"), "stroke": ("condition", "Stroke"),
    # medications
    "metformin": ("medication", "Metformin"), "insulin": ("medication", "Insulin"),
    "glimepiride": ("medication", "Glimepiride"), "lisinopril": ("medication", "Lisinopril"),
    "losartan": ("medication", "Losartan"), "amlodipine": ("medication", "Amlodipine"),
    "metoprolol": ("medication", "Metoprolol"), "atorvastatin": ("medication", "Atorvastatin"),
    "aspirin": ("medication", "Aspirin"), "clopidogrel": ("medication", "Clopidogrel"),
    "salbutamol": ("medication", "Salbutamol"), "albuterol": ("medication", "Salbutamol"),
    # risk factors
    "smoking": ("risk factor", "Smoking"), "smoker": ("risk factor", "Smoking"),
    "family history": ("risk factor", "Family history"), "obesity": ("risk factor", "Obesity"),
    "obese": ("risk factor", "Obesity"), "sedentary": ("risk factor", "Sedentary lifestyle"),
    "alcohol": ("risk factor", "Alcohol use"),
}

URGENT_TERMS = ["severe chest pain", "chest pain", "chest pressure", "fainting", "blue lips", "can't breathe",
                "cannot breathe", "difficulty breathing", "slurred speech", "facial droop", "one-sided weakness"]

_NEGATION = re.compile(
    r"\b(?:no|denies?|denied|without|negative for|not experiencing|not having|never had|no history of|family history of|free of|absence of)\b(?:\s+\w+){0,3}\s*$",
    re.IGNORECASE)


def affirmed_mention(text: str, phrase: str) -> bool:
    pattern = re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)", re.IGNORECASE)
    for clause in re.split(r"[\n.;!?]", text):
        for match in pattern.finditer(clause):
            if not _NEGATION.search(clause[max(0, match.start() - 60):match.start()]):
                return True
    return False


def extract_entities(text: str) -> list[dict[str, str]]:
    found: dict[tuple[str, str], None] = {}
    for phrase, (category, name) in SIGNALS.items():
        if affirmed_mention(text, phrase):
            found[(category, name)] = None
    return [{"category": c, "name": n} for c, n in found]


def has_urgent_language(text: str) -> bool:
    return any(affirmed_mention(text, term) for term in URGENT_TERMS)


# ---------------------------------------------------------------- vitals / labs
def _num(pattern: str, text: str, flags: int = re.IGNORECASE) -> re.Match[str] | None:
    return re.search(pattern, text, flags)


def extract_vitals(text: str) -> dict[str, Any]:
    """Pull simple numeric findings out of free text. Everything is optional."""
    v: dict[str, Any] = {}
    m = _num(r"(\d{1,3})[\s-]*(?:year|yr)s?[\s-]*old", text) or _num(r"\bage\b[\s:]*(\d{1,3})\b", text) or _num(r"\b(\d{1,3})\s*(?:years?|yrs?)\b(?!\s*(?:of|ago))", text) or _num(r"\b(\d{2})\s*(?:y/?o|yo)\b", text)
    if m and 0 < int(m.group(1)) < 120:
        v["age"] = int(m.group(1))
    if _num(r"\b(?:female|woman|girl)\b", text):
        v["sex"] = 0
    elif _num(r"\b(?:male|man|boy)\b", text):
        v["sex"] = 1
    m = _num(r"(?:\bbp\b|blood pressure)[^\d]{0,15}(\d{2,3})\s*/\s*(\d{2,3})", text) or _num(r"\b(\d{2,3})\s*/\s*(\d{2,3})\s*mm\s?hg", text)
    if m:
        sys_, dia = int(m.group(1)), int(m.group(2))
        if 60 <= sys_ <= 260 and 30 <= dia <= 160:
            v["systolic"], v["diastolic"] = sys_, dia
    m = _num(r"(?:glucose|blood sugar|\bfbs\b|\bfpg\b|\brbs\b)[^\d]{0,25}(\d{1,3}(?:\.\d+)?)\s*(mg/dl|mmol/l)?", text)
    if m:
        val = float(m.group(1))
        if (m.group(2) or "").lower() == "mmol/l" or val < 30:
            val *= 18.0
        if 30 <= val <= 800:
            v["glucose"] = round(val)
    m = _num(r"(?:hba1c|\ba1c\b)[^\d]{0,15}(\d{1,2}(?:\.\d+)?)", text)
    if m and 3 <= float(m.group(1)) <= 18:
        v["hba1c"] = float(m.group(1))
    m = _num(r"\bbmi\b[^\d]{0,10}(\d{2}(?:\.\d+)?)", text)
    if m and 10 <= float(m.group(1)) <= 80:
        v["bmi"] = float(m.group(1))
    m = _num(r"cholesterol[^\d]{0,20}(\d{2,3})", text)
    if m and 80 <= int(m.group(1)) <= 600:
        v["cholesterol"] = int(m.group(1))
    m = _num(r"(?:heart rate|\bhr\b|pulse)[^\d]{0,10}(\d{2,3})", text)
    if m and 30 <= int(m.group(1)) <= 220:
        v["heart_rate"] = int(m.group(1))
    return v


def vitals_to_model_features(v: dict[str, Any]) -> dict[str, float]:
    """Map extracted vitals onto the model feature names (UCI heart + Pima diabetes)."""
    f: dict[str, float] = {}
    for src, dst in (("age", "age"), ("sex", "sex"), ("systolic", "trestbps"), ("cholesterol", "chol")):
        if src in v:
            f[dst] = float(v[src])
    if "age" in v:
        f["Age"] = float(v["age"])
    if "glucose" in v:
        f["Glucose"] = float(v["glucose"])
    if "diastolic" in v:
        f["BloodPressure"] = float(v["diastolic"])
    if "bmi" in v:
        f["BMI"] = float(v["bmi"])
    return f


# ---------------------------------------------------------------- differential
def _bp(v: dict[str, Any], s: int, d: int) -> bool:
    return v.get("systolic", 0) >= s or v.get("diastolic", 0) >= d


# (label, [(entity name, weight)], [(vitals predicate, weight, description)], reference ids)
RULES: list[dict[str, Any]] = [
    {"label": "Diabetes mellitus / hyperglycaemia", "refs": ["ada-diabetes-diagnosis", "cdc-diabetes-symptoms", "uspstf-diabetes-screening"],
     "names": {"Increased thirst": 1, "Frequent urination": 1, "Fatigue": .5, "Blurred vision": .5, "Unintended weight loss": .5,
               "Diabetes": 2, "Metformin": 1.5, "Insulin": 1.5, "Glimepiride": 1.5, "Obesity": .5, "Family history": .3, "Numbness / tingling": .3},
     "vitals": [(lambda v: v.get("glucose", 0) >= 126, 2, "glucose ≥126 mg/dL"), (lambda v: v.get("hba1c", 0) >= 6.5, 2, "HbA1c ≥6.5%"),
                (lambda v: v.get("bmi", 0) >= 30, .5, "BMI ≥30")]},
    {"label": "Prediabetes / impaired glucose regulation", "refs": ["ada-diabetes-diagnosis", "uspstf-diabetes-screening"],
     "names": {"Prediabetes": 2, "Obesity": .5},
     "vitals": [(lambda v: 5.7 <= v.get("hba1c", 0) < 6.5, 2, "HbA1c 5.7–6.4%"), (lambda v: 100 <= v.get("glucose", 0) < 126, 1.5, "glucose 100–125 mg/dL")]},
    {"label": "Acute coronary syndrome / ischaemic heart disease", "refs": ["aha-heart-attack-warning-signs", "aha-chest-pain-guideline", "acc-aha-primary-prevention"],
     "names": {"Chest pain": 2, "Chest pressure": 2, "Shortness of breath": 1, "Sweating": 1, "Nausea": .5, "Heart disease": 1.5,
               "Hypertension": .5, "Smoking": .5, "Diabetes": .5, "Hyperlipidemia": .5, "Palpitations": .3},
     "vitals": [(lambda v: v.get("cholesterol", 0) >= 240, .5, "cholesterol ≥240 mg/dL")]},
    {"label": "Hypertension", "refs": ["acc-aha-hypertension", "who-hypertension"],
     "names": {"Hypertension": 2, "Lisinopril": 1.5, "Losartan": 1.5, "Amlodipine": 1.5, "Headache": .5, "Dizziness": .5},
     "vitals": [(lambda v: _bp(v, 130, 80), 2, "BP ≥130/80 mmHg")]},
    {"label": "Heart failure", "refs": ["aha-heart-attack-warning-signs"],
     "names": {"Shortness of breath": 1, "Leg swelling": 1.5, "Fatigue": .5, "Heart failure": 2, "Heart disease": 1, "Hypertension": .5}, "vitals": []},
    {"label": "Asthma / COPD (obstructive airway disease)", "refs": ["gina-asthma"],
     "names": {"Wheezing": 1.5, "Cough": 1, "Shortness of breath": 1, "Asthma": 2, "COPD": 2, "Smoking": .5, "Salbutamol": 1}, "vitals": []},
    {"label": "Anaemia", "refs": [],
     "names": {"Fatigue": 1, "Dizziness": 1, "Pallor": 1, "Palpitations": .5, "Anemia": 2}, "vitals": []},
    {"label": "Dyslipidaemia / elevated cardiovascular risk", "refs": ["acc-aha-primary-prevention"],
     "names": {"Hyperlipidemia": 2, "Atorvastatin": 1.5}, "vitals": [(lambda v: v.get("cholesterol", 0) >= 240, 2, "cholesterol ≥240 mg/dL")]},
]


def differential(entities: list[dict[str, str]], vitals: dict[str, Any], risk_boost: dict[str, float] | None = None) -> list[dict[str, Any]]:
    names = {e["name"] for e in entities}
    out = []
    for rule in RULES:
        score, support = 0.0, []
        for name, weight in rule["names"].items():
            if name in names:
                score += weight
                support.append(name)
        for pred, weight, desc in rule["vitals"]:
            if pred(vitals):
                score += weight
                support.append(desc)
        for key, extra in (risk_boost or {}).items():
            if key.lower() in rule["label"].lower():
                score += extra
                support.append("ML risk model signal")
        if score >= 2:
            out.append({"condition": rule["label"], "score": round(score, 1), "likelihood": "stronger match" if score >= 3 else "possible",
                        "supporting_findings": support, "evidence_ids": rule["refs"]})
    return sorted(out, key=lambda x: -x["score"])


# ---------------------------------------------------------------- lab reports
_HEADING = re.compile(r"^\s*(?:\|)?\s*(interpretation|comments?|note|notes|clinical significance|reference|method|recommended|disclaimer|limitations?)\b", re.I)
_TEST_ROW = re.compile(r"^\s{0,6}[A-Z][A-Z0-9 ,;()\-/+.]{5,}(?:\s{2,}|$)")


def strip_boilerplate(text: str) -> str:
    """Drop educational text in lab reports (interpretation tables, comments, notes) so that disease names in
    boilerplate are not mistaken for the patient's own conditions."""
    out, skipping = [], False
    for line in text.splitlines():
        if _HEADING.match(line):
            skipping = True
            continue
        if skipping and (_TEST_ROW.match(line) or re.search(r"Page \d+ of \d+", line)):
            skipping = False
        if skipping or re.match(r"^\s*[|+-][-|+ ]{6,}", line) or line.strip().startswith("|"):
            continue
        out.append(line)
    return "\n".join(out)


_UNITS = r"(mg/dL|mg/L|g/dL|g/L|ng/L|ng/mL|ng/dL|mmol/L|%|U/L|IU/L|[µu]IU/mL|mIU/L|pg/mL|mEq/L|fL|pg|/cmm|cells/[µu]L|thou/[µu]L|million/[µu]L|mm/hr)"
_LAB_ROW = re.compile(rf"^\s*([A-Za-z][A-Za-z0-9 ,;()\-/+.]{{3,70}}?)\s{{2,}}([<>]?\d+(?:\.\d+)?)\s+{_UNITS}\s*([<>]?\s*\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?)?\s*$")


def _flag(value: float, ref: str | None) -> str:
    if not ref:
        return "n/a"
    ref = ref.replace(" ", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)", ref)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return "low" if value < lo else "high" if value > hi else "normal"
    m = re.fullmatch(r"<(\d+(?:\.\d+)?)", ref)
    if m:
        x = float(m.group(1))
        return "normal" if value < x else "borderline" if value == x else "high"
    m = re.fullmatch(r">(\d+(?:\.\d+)?)", ref)
    if m:
        x = float(m.group(1))
        return "normal" if value > x else "borderline" if value == x else "low"
    return "n/a"


def extract_labs(text: str) -> list[dict[str, Any]]:
    """Parse tabular lab rows ("TEST NAME   value  unit  ref-range") and flag out-of-range values."""
    labs = []
    for line in text.splitlines():
        m = _LAB_ROW.match(line)
        if not m:
            continue
        name, raw, unit, ref = m.group(1).strip(" ,;"), m.group(2), m.group(3), (m.group(4) or "").strip() or None
        try:
            value = float(raw.lstrip("<>"))
        except ValueError:
            continue
        labs.append({"test": name.title() if name.isupper() else name, "value": value, "unit": unit, "reference": ref, "flag": _flag(value, ref)})
    return labs


def labs_to_vitals(labs: list[dict[str, Any]]) -> dict[str, Any]:
    v: dict[str, Any] = {}
    for lab in labs:
        n = lab["test"].lower()
        if "glucose" in n and lab["unit"] == "mg/dL" and ("fasting" in n or "plasma" in n or "random" in n):
            v.setdefault("glucose", round(lab["value"]))
        elif ("hba1c" in n or "glycosylated" in n or "glycated" in n) and lab["unit"] == "%":
            v.setdefault("hba1c", lab["value"])
        elif "cholesterol" in n and "total" in n and lab["unit"] == "mg/dL":
            v.setdefault("cholesterol", round(lab["value"]))
    return v
