"""Clinical NLP layer: dictionary entity extraction with negation handling,
vital-sign / lab extraction from free text, and a transparent rule-based
differential ("possible conditions") generator."""
from __future__ import annotations

import bisect
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
    "diaphoresis": ("symptom", "Sweating"), "diaphoretic": ("symptom", "Sweating"),
    "dyspnea": ("symptom", "Shortness of breath"), "dyspnoea": ("symptom", "Shortness of breath"),
    "cold sweat": ("symptom", "Sweating"), "palpitations": ("symptom", "Palpitations"),
    "cough": ("symptom", "Cough"), "wheezing": ("symptom", "Wheezing"), "wheeze": ("symptom", "Wheezing"),
    "swelling in legs": ("symptom", "Leg swelling"), "leg swelling": ("symptom", "Leg swelling"),
    "edema": ("symptom", "Leg swelling"), "pallor": ("symptom", "Pallor"), "fever": ("symptom", "Fever"),
    "confusion": ("symptom", "Confusion"), "confused": ("symptom", "Confusion"), "febrile": ("symptom", "Fever"),
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
    "ramipril": ("medication", "Ramipril"), "enalapril": ("medication", "Enalapril"), "hydrochlorothiazide": ("medication", "Hydrochlorothiazide"),
    "furosemide": ("medication", "Furosemide"), "spironolactone": ("medication", "Spironolactone"), "bisoprolol": ("medication", "Bisoprolol"),
    "carvedilol": ("medication", "Carvedilol"), "warfarin": ("medication", "Warfarin"), "apixaban": ("medication", "Apixaban"),
    "rivaroxaban": ("medication", "Rivaroxaban"), "simvastatin": ("medication", "Simvastatin"), "rosuvastatin": ("medication", "Rosuvastatin"),
    "empagliflozin": ("medication", "Empagliflozin"), "dapagliflozin": ("medication", "Dapagliflozin"), "sitagliptin": ("medication", "Sitagliptin"),
    "semaglutide": ("medication", "Semaglutide"), "levothyroxine": ("medication", "Levothyroxine"), "omeprazole": ("medication", "Omeprazole"),
    "prednisone": ("medication", "Prednisone"), "prednisolone": ("medication", "Prednisolone"), "nitroglycerin": ("medication", "Nitroglycerin"),
    "glyceryl trinitrate": ("medication", "Nitroglycerin"),
    # risk factors
    "smoking": ("risk factor", "Smoking"), "smoker": ("risk factor", "Smoking"),
    "family history": ("risk factor", "Family history"), "obesity": ("risk factor", "Obesity"),
    "obese": ("risk factor", "Obesity"), "sedentary": ("risk factor", "Sedentary lifestyle"),
    "alcohol": ("risk factor", "Alcohol use"),
}

URGENT_TERMS = ["severe chest pain", "chest pain", "chest pressure", "fainting", "blue lips", "can't breathe",
                "cannot breathe", "difficulty breathing", "slurred speech", "facial droop", "one-sided weakness",
                "syncope", "confusion", "suicidal", "anaphylaxis", "hemoptysis", "coughing blood", "vomiting blood", "seizure"]

_NEGATION = re.compile(
    r"\b(?P<cue>no|not|denies?|denied|without|negative for|never had|no history of|family history of|free of|absence of|ruled out"
    # a relative's diagnosis is not the patient's ("Mother has diabetes"); captured as Family history instead
    r"|(?:mother|father|mom|dad|brother|sister|sibling|parents?|grand(?:mother|father|parent)|aunt|uncle|son|daughter|cousin)(?:'s)?\s+"
    r"(?:has|had|have|with|diagnosed with|died of|suffers? from))\b(?:\s+\w+){0,3}\s*$",
    re.IGNORECASE)
# Post-negation triggers follow the finding: "chest pain resolved", "MI was ruled out".
_POST_NEGATION = re.compile(r"^\s*(?:has |have |had |was |were |is |are |now )?(?:resolved|ruled out|absent|negative|unlikely|denied|excluded)\b", re.IGNORECASE)
# NegEx-style scope terminators: a negation before one of these does not reach findings after it
# ("denies fever but reports cough" -> cough is affirmed).
_TERMINATOR = re.compile(r"\b(?:but|however|although|though|except|apart from|aside from|reports?|presents? with|complains? of|now has|admits? to)\b", re.IGNORECASE)


def _negation_trigger(clause: str, start: int, end: int) -> re.Match[str] | None:
    """The pre- or post-negation trigger that applies to clause[start:end], if any."""
    window = clause[max(0, start - 60):start]
    cuts = list(_TERMINATOR.finditer(window))
    if cuts:
        window = window[cuts[-1].end():]
    return _NEGATION.search(window) or _POST_NEGATION.match(clause[end:end + 40])


def affirmed_mention(text: str, phrase: str) -> bool:
    pattern = re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)", re.IGNORECASE)
    for clause in re.split(r"[\n.;!?]", text):
        for match in pattern.finditer(clause):
            if not _negation_trigger(clause, match.start(), match.end()):
                return True
    return False


# Clinical shorthand -> words the lexicon understands. Case-sensitive (upper-case abbreviations only) so "cp"
# inside ordinary words is never touched. Ambiguity is resolved toward the acute adult reading (CP = chest pain),
# the safer error for an urgent-signal screen.
ABBREVIATIONS: dict[str, str] = {
    "SOB": "shortness of breath", "DOE": "shortness of breath on exertion", "CP": "chest pain", "HTN": "hypertension",
    "DM": "diabetes", "DM2": "type 2 diabetes", "T2DM": "type 2 diabetes", "T1DM": "diabetes", "IDDM": "diabetes", "NIDDM": "type 2 diabetes",
    "MI": "myocardial infarction", "NSTEMI": "myocardial infarction", "STEMI": "myocardial infarction", "CAD": "coronary artery disease",
    "IHD": "coronary artery disease", "CHF": "heart failure", "HF": "heart failure", "HFrEF": "heart failure", "HFpEF": "heart failure",
    "HLD": "hyperlipidemia", "CKD": "chronic kidney disease", "CVA": "stroke", "TIA": "stroke", "N/V": "nausea and vomiting",
    "LOC": "fainting", "ASA": "aspirin", "GTN": "glyceryl trinitrate", "HCTZ": "hydrochlorothiazide",
}
_ABBR = re.compile(r"(?<![A-Za-z0-9/])(" + "|".join(sorted(map(re.escape, ABBREVIATIONS), key=len, reverse=True)) + r")(?![A-Za-z0-9/])")
_SHORTHAND = [(re.compile(r"\bc/o\b", re.I), "complains of"), (re.compile(r"\bh/o\b|\bhx of\b|\bpmhx?\b:?", re.I), "history of"),
              (re.compile(r"\bw/o\b", re.I), "without"), (re.compile(r"\bdiaphoretic\b|\bdiaphoresis\b", re.I), "sweating"),
              (re.compile(r"\bdyspno?ea\b|\bdyspneic\b", re.I), "shortness of breath")]
_RELATIVE = r"(?:mother|father|mom|dad|brother|sister|sibling|parents?|grand(?:mother|father|parent)|aunt|uncle|son|daughter|cousin)"
_RELATIVE_CTX = re.compile(rf"\b{_RELATIVE}(?:'s)?\s+(?:has|had|have|with|diagnosed with|died of|suffers? from)\b", re.I)


def normalize(text: str) -> str:
    """Expand clinical abbreviations and shorthand. Idempotent."""
    text = _ABBR.sub(lambda m: ABBREVIATIONS[m.group(1)], text)
    for pattern, repl in _SHORTHAND:
        text = pattern.sub(repl, text)
    return text


def extract_entities(text: str) -> list[dict[str, str]]:
    text = normalize(text)
    found: dict[tuple[str, str], None] = {}
    for phrase, (category, name) in SIGNALS.items():
        if affirmed_mention(text, phrase):
            found[(category, name)] = None
    if _RELATIVE_CTX.search(text):
        found[("risk factor", "Family history")] = None
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
    m = _num(r"(?:heart rate|\bhr\b|pulse(?!\s*ox))[^\d]{0,10}(\d{2,3})", text)   # "pulse ox 89%" is a saturation, not a heart rate
    if m and 30 <= int(m.group(1)) <= 220:
        v["heart_rate"] = int(m.group(1))
    m = _num(r"(?:\bspo2\b|\bsao2\b|\bsp02\b|o2 sat(?:uration)?s?|oxygen saturation|pulse ?ox(?:imetry)?|\bsats?\b)[^\d]{0,12}(\d{2,3})\s*%?", text)
    if m and 50 <= int(m.group(1)) <= 100:
        v["spo2"] = int(m.group(1))
    # "temp 38.5" / "temperature 101 F", or the charting shorthand "T 38.5" (capital T, Celsius with a decimal, to avoid "T 2 DM")
    m = _num(r"(?:\btemp(?:erature)?\b)[^\d]{0,10}(\d{2,3}(?:\.\d+)?)\s*°?\s*([CF])?\b", text) or _num(r"\bT\s*[:=]?\s*((?:3[4-9]|4[0-3])\.\d)()\s*°?\s*C?\b", text, 0)
    if m:
        t = float(m.group(1))
        if (m.group(2) or "").upper() == "F" or t > 50:
            t = (t - 32) * 5 / 9
        if 30 <= t <= 45:
            v["temperature"] = round(t, 1)
    m = _num(r"(?:respiratory rate|\bresp(?:irations)?\b|\brr\b)[^\d]{0,10}(\d{1,2})\b", text)
    if m and 4 <= int(m.group(1)) <= 70:
        v["respiratory_rate"] = int(m.group(1))
    m = _num(r"(?<![/-])(?<!to )(?:\bcreatinine\b|\bcreat\b|\bscr\b)(?!\s*(?:clearance|ratio|kinase|/))[^\d]{0,15}(\d{1,4}(?:\.\d+)?)\s*(mg/dl|[µu]mol/l)?", text)
    if m:
        scr = float(m.group(1))
        if (m.group(2) or "").lower().endswith("mol/l") or scr > 20:   # µmol/L -> mg/dL
            scr /= 88.4
        if 0.1 <= scr <= 20:
            v["creatinine"] = round(scr, 2)
    return v


_DOSE_UNIT = r"(mg|mcg|µg|g|units?|iu|ml|puffs?)"
_FREQ = (r"(once daily|twice daily|three times (?:a day|daily)|four times (?:a day|daily)|daily|nightly|at night|every morning|"
         r"b\.?i\.?d\.?|t\.?i\.?d\.?|q\.?i\.?d\.?|\bod\b|\bbd\b|\bqd\b|qhs|prn|as needed|weekly|every \d+ hours|q\d+h)")


def medication_details(text: str) -> list[dict[str, Any]]:
    """Dose and frequency for each affirmed medication mention, e.g. 'metformin 500 mg twice daily'."""
    out: dict[str, dict[str, Any]] = {}
    for phrase, (category, name) in SIGNALS.items():
        if category != "medication" or name in out or not affirmed_mention(text, phrase):
            continue
        item: dict[str, Any] = {"name": name, "dose": None, "unit": None, "frequency": None}
        m = re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)[\s,(:]*(\d+(?:\.\d+)?)\s*{_DOSE_UNIT}\b([^\n.;]{{0,30}})", text, re.I)
        if m:
            item["dose"], item["unit"] = float(m.group(1)), m.group(2).lower()
            f = re.search(_FREQ, m.group(3), re.I)
            if f:
                item["frequency"] = f.group(1).lower()
        out[name] = item
    return list(out.values())


_ALLERGY = re.compile(r"\b(?:allerg(?:y|ies|ic)(?:\s+to)?|intolerant of)\s*[:\-]?\s*([a-z][a-z ,/\-]{2,80}?)(?=[.;\n]|\band\s+(?:no|denies)\b|$)", re.I)


def extract_allergies(text: str) -> dict[str, Any]:
    """{'status': 'nkda' | 'documented' | 'not documented', 'items': [...]}"""
    if re.search(r"\b(?:nkda|nka|no known (?:drug )?allergies)\b", text, re.I):
        return {"status": "nkda", "items": []}
    items: list[str] = []
    for m in _ALLERGY.finditer(text):
        for part in re.split(r",|/|\band\b", m.group(1)):
            part = part.strip(" -").lower()
            if part and part not in ("none", "nil", "unknown") and len(part) <= 40 and part not in items:
                items.append(part)
    return {"status": "documented" if items else "not documented", "items": items[:10]}


def urgent_findings(text: str, vitals: dict[str, Any]) -> list[str]:
    """Every reason the record warrants urgent attention, so the flag is explainable (and auditable)."""
    text = normalize(text)
    terms = [t for t in URGENT_TERMS if affirmed_mention(text, t)]
    terms = [t for t in terms if not any(t != o and t in o for o in terms)]   # 'severe chest pain' subsumes 'chest pain'
    reasons = [f"Warning-sign language: '{t}'" for t in terms]
    checks = [
        (vitals.get("systolic", 0) > 180 or vitals.get("diastolic", 0) > 120, f"Severely elevated blood pressure ({vitals.get('systolic')}/{vitals.get('diastolic')} mmHg)"),
        (0 < vitals.get("systolic", 999) < 90, f"Hypotension (systolic {vitals.get('systolic')} mmHg)"),
        (0 < vitals.get("spo2", 100) < 92, f"Low oxygen saturation (SpO2 {vitals.get('spo2')}%)"),
        (vitals.get("heart_rate", 80) > 130 or 0 < vitals.get("heart_rate", 80) < 40, f"Abnormal heart rate ({vitals.get('heart_rate')}/min)"),
        (vitals.get("respiratory_rate", 16) >= 30 or 0 < vitals.get("respiratory_rate", 16) < 8, f"Abnormal respiratory rate ({vitals.get('respiratory_rate')}/min)"),
        (vitals.get("temperature", 37) >= 40 or 0 < vitals.get("temperature", 37) < 35, f"Abnormal temperature ({vitals.get('temperature')} °C)"),
        (vitals.get("glucose", 100) >= 400, f"Severe hyperglycaemia (glucose {vitals.get('glucose')} mg/dL)"),
        (0 < vitals.get("glucose", 100) < 54, f"Clinically significant hypoglycaemia (glucose {vitals.get('glucose')} mg/dL)"),
    ]
    return reasons + [msg for hit, msg in checks if hit]


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
    {"label": "Sepsis / serious infection", "refs": ["sepsis-3-qsofa", "rcp-news2"],
     "names": {"Fever": 1, "Confusion": 1, "Cough": .3},
     "vitals": [(lambda v: v.get("temperature", 37) >= 38 or 0 < v.get("temperature", 37) < 36, 1, "temperature ≥38 or <36 °C"),
                (lambda v: v.get("heart_rate", 0) > 90, .5, "heart rate >90/min"), (lambda v: v.get("respiratory_rate", 0) >= 22, 1, "respiratory rate ≥22/min"),
                (lambda v: 0 < v.get("systolic", 999) <= 100, 1, "systolic BP ≤100 mmHg")]},
    {"label": "Lower respiratory tract infection", "refs": [],
     "names": {"Cough": 1, "Fever": 1, "Shortness of breath": .5},
     "vitals": [(lambda v: 0 < v.get("spo2", 100) < 94, .5, "SpO2 <94%"), (lambda v: v.get("respiratory_rate", 0) >= 22, .5, "respiratory rate ≥22/min")]},
    {"label": "Kidney impairment (AKI or CKD)", "refs": ["ckd-epi-2021"],
     "names": {"Chronic kidney disease": 2},
     "vitals": [(lambda v: v.get("creatinine", 0) >= 1.5, 2, "creatinine ≥1.5 mg/dL")]},
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


def _boilerplate_mask(lines: list[str]) -> list[bool]:
    """True for each line that is report boilerplate (interpretation tables, comments, notes)."""
    mask, skipping = [], False
    for line in lines:
        if _HEADING.match(line):
            skipping = True
            mask.append(True)
            continue
        if skipping and (_TEST_ROW.match(line) or re.search(r"Page \d+ of \d+", line)):
            skipping = False
        mask.append(skipping or bool(re.match(r"^\s*[|+-][-|+ ]{6,}", line)) or line.strip().startswith("|"))
    return mask


def strip_boilerplate(text: str) -> str:
    """Drop educational text in lab reports (interpretation tables, comments, notes) so that disease names in
    boilerplate are not mistaken for the patient's own conditions."""
    lines = text.splitlines()
    return "\n".join(line for line, skip in zip(lines, _boilerplate_mask(lines), strict=True) if not skip)


# ---------------------------------------------------------------- explainability
_MEASURE = re.compile(
    r"\b(?:bp|blood pressure|spo2|sao2|o2 sat\w*|pulse ?ox\w*|hr|heart rate|pulse|rr|respiratory rate|temp(?:erature)?|t(?=\s*[:=]?\s*[34]\d\.\d)|"
    r"glucose|fbs|fpg|hba1c|a1c|bmi|cholesterol|creatinine|creat)\b[^\n.;,\d]{0,14}\d{1,4}(?:\.\d+)?(?:\s*/\s*\d{2,3})?"
    r"\s*(?:%|mg/dl|mmol/l|mm\s?hg|°\s*[cf]\b|[cf]\b|/min|bpm|[µu]mol/l|kg/m2)?", re.IGNORECASE)
_ANNOTATE_TERMS = sorted({*SIGNALS, *ABBREVIATIONS}, key=len, reverse=True)
_TERM_RE = re.compile(r"(?<![\w/])(" + "|".join(re.escape(t) for t in _ANNOTATE_TERMS) + r")(?![\w/])", re.IGNORECASE)


def annotate(text: str) -> list[dict[str, Any]]:
    """Character spans over ``text`` explaining what the pipeline saw: findings (affirmed / negated /
    family history / ignored report boilerplate, with the trigger that decided it), measurements and
    identifiers redacted before external calls. Non-overlapping, sorted by start."""
    from .phi import find as find_phi
    spans: list[dict[str, Any]] = [{"start": s, "end": e, "kind": "phi", "label": cat} for s, e, cat in find_phi(text)]
    lines = text.split("\n")
    mask, offset, boiler = _boilerplate_mask(lines), 0, []
    for line, skip in zip(lines, mask, strict=True):
        if skip:
            boiler.append((offset, offset + len(line)))
        offset += len(line) + 1
    for clause in re.finditer(r"[^\n.;!?]+", text):
        body, base = clause.group(0), clause.start()
        for m in _TERM_RE.finditer(body):
            surface = m.group(1)
            if surface in ABBREVIATIONS:              # abbreviations are case-sensitive ("CP", never "cp")
                canonical = ABBREVIATIONS[surface]
            elif surface.lower() in SIGNALS:
                canonical = surface.lower()
            else:
                continue
            pre, post = normalize(body[:m.start()]), normalize(body[m.end():])
            trigger = _negation_trigger(pre + canonical + post, len(pre), len(pre) + len(canonical))
            # expansions such as "nausea and vomiting" resolve to the lexicon phrase they contain
            category, name = SIGNALS.get(canonical) or next((SIGNALS[p] for p in sorted(SIGNALS, key=len, reverse=True) if p in canonical),
                                                            ("finding", canonical.capitalize()))
            start, end = base + m.start(), base + m.end()
            if any(a <= start < b for a, b in boiler):
                status, why = "ignored", "report boilerplate (not about this patient)"
            elif trigger and re.match(_RELATIVE, cue := (trigger.groupdict().get("cue") or trigger.group(0)).strip(), re.I):
                status, why = "family", f"relative: '{cue}'"
            elif trigger:
                status, why = "negated", f"negation: '{cue}'"
            else:
                status, why = "affirmed", None
            spans.append({"start": start, "end": end, "kind": "finding", "label": name, "category": category, "status": status,
                          "reason": why, **({"expanded": canonical} if surface in ABBREVIATIONS else {})})
    for m in _MEASURE.finditer(text):
        spans.append({"start": m.start(), "end": m.end(), "kind": "measurement", "label": m.group(0).strip()})
    priority = {"phi": 0, "finding": 1, "measurement": 2}
    starts: list[int] = []
    kept: list[dict[str, Any]] = []   # sorted by start, non-overlapping: each check is a bisect, not a scan
    for s in sorted(spans, key=lambda x: (priority[x["kind"]], x["start"], -(x["end"] - x["start"]))):
        i = bisect.bisect_left(starts, s["start"])
        if (i > 0 and kept[i - 1]["end"] > s["start"]) or (i < len(kept) and kept[i]["start"] < s["end"]):
            continue
        starts.insert(i, s["start"])
        kept.insert(i, s)
    return kept


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
        item = {"test": name.title() if name.isupper() else name, "value": value, "unit": unit, "reference": ref, "flag": _flag(value, ref)}
        if not any(l["test"].lower() == item["test"].lower() and l["value"] == value for l in labs):   # reports often repeat rows across pages
            labs.append(item)
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
        elif "creatinine" in n and "clearance" not in n and "ratio" not in n and lab["unit"] == "mg/dL":
            v.setdefault("creatinine", lab["value"])
    return v
