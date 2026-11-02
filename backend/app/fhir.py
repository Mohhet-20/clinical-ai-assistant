"""FHIR R4 export of an analysis result as a ``collection`` Bundle.

Vitals/labs -> Observation (LOINC where mapped), possible conditions ->
Condition with verificationStatus *provisional*, model signals ->
RiskAssessment (status *preliminary*), urgent signals -> DetectedIssue, and a
Device + Provenance pair recording which software version produced it. The
Patient resource is intentionally identifier-free; the receiving system links
it to its own record."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

VERSION = "2.1.0"
LOINC, UCUM, SNOMED = "http://loinc.org", "http://unitsofmeasure.org", "http://snomed.info/sct"
OBS_CAT = "http://terminology.hl7.org/CodeSystem/observation-category"
INTERP = "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation"

# vital key -> (LOINC, display, UCUM unit, human unit)
VITALS: dict[str, tuple[str, str, str, str]] = {
    "glucose": ("2345-7", "Glucose [Mass/volume] in Serum or Plasma", "mg/dL", "mg/dL"),
    "hba1c": ("4548-4", "Hemoglobin A1c/Hemoglobin.total in Blood", "%", "%"),
    "bmi": ("39156-5", "Body mass index (BMI) [Ratio]", "kg/m2", "kg/m2"),
    "cholesterol": ("2093-3", "Cholesterol [Mass/volume] in Serum or Plasma", "mg/dL", "mg/dL"),
    "heart_rate": ("8867-4", "Heart rate", "/min", "beats/minute"),
    "spo2": ("59408-5", "Oxygen saturation in Arterial blood by Pulse oximetry", "%", "%"),
    "temperature": ("8310-5", "Body temperature", "Cel", "°C"),
    "respiratory_rate": ("9279-1", "Respiratory rate", "/min", "breaths/minute"),
    "creatinine": ("2160-0", "Creatinine [Mass/volume] in Serum or Plasma", "mg/dL", "mg/dL"),
}
VITAL_SIGNS = {"heart_rate", "spo2", "temperature", "respiratory_rate", "bmi"}
UCUM_UNITS = {"mg/dL": "mg/dL", "mg/L": "mg/L", "g/dL": "g/dL", "g/L": "g/L", "ng/mL": "ng/mL", "ng/L": "ng/L", "mmol/L": "mmol/L",
              "%": "%", "U/L": "U/L", "IU/L": "[IU]/L", "pg/mL": "pg/mL", "mEq/L": "meq/L", "fL": "fL", "pg": "pg", "mm/hr": "mm/h"}
SNOMED_CONDITIONS = {
    "Diabetes mellitus": ("73211009", "Diabetes mellitus"), "Prediabetes": ("714628002", "Prediabetes"),
    "Acute coronary syndrome": ("394659003", "Acute coronary syndrome"), "Hypertension": ("38341003", "Hypertensive disorder"),
    "Heart failure": ("84114007", "Heart failure"), "Anaemia": ("271737000", "Anemia"),
    "Dyslipidaemia": ("370992007", "Dyslipidemia"),
}
FLAG_CODES = {"high": ("H", "High"), "low": ("L", "Low"), "normal": ("N", "Normal")}


def _urn() -> str:
    return f"urn:uuid:{uuid.uuid4()}"


def _quantity(value: float, unit: str, ucum: str | None) -> dict[str, Any]:
    q: dict[str, Any] = {"value": value, "unit": unit}
    if ucum:
        q |= {"system": UCUM, "code": ucum}
    return q


def _category(code: str) -> list[dict[str, Any]]:
    return [{"coding": [{"system": OBS_CAT, "code": code}]}]


def build_bundle(result: dict[str, Any], request_id: str | None = None) -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    patient_ref, device_ref = _urn(), _urn()
    entries: list[dict[str, Any]] = []

    def add(resource: dict[str, Any], full_url: str | None = None) -> str:
        url = full_url or _urn()
        entries.append({"fullUrl": url, "resource": resource})
        return url

    vitals = result.get("vitals") or {}
    patient: dict[str, Any] = {"resourceType": "Patient", "meta": {"tag": [{"code": "deidentified", "display": "No identifiers exported"}]}}
    if vitals.get("sex") in (0, 1):
        patient["gender"] = "female" if vitals["sex"] == 0 else "male"
    add(patient, patient_ref)
    add({"resourceType": "Device", "deviceName": [{"name": "Clarity clinical decision support", "type": "manufacturer-name"}],
         "version": [{"value": VERSION}], "type": {"text": "Clinical decision support software (research prototype)"}}, device_ref)

    subject = {"reference": patient_ref}
    common = {"status": "preliminary", "subject": subject, "issued": now, "device": {"reference": device_ref}}
    refs: list[str] = []

    if "systolic" in vitals and "diastolic" in vitals:
        refs.append(add({"resourceType": "Observation", **common, "category": _category("vital-signs"),
                         "code": {"coding": [{"system": LOINC, "code": "85354-9", "display": "Blood pressure panel with all children optional"}]},
                         "component": [
                             {"code": {"coding": [{"system": LOINC, "code": "8480-6", "display": "Systolic blood pressure"}]},
                              "valueQuantity": _quantity(vitals["systolic"], "mmHg", "mm[Hg]")},
                             {"code": {"coding": [{"system": LOINC, "code": "8462-4", "display": "Diastolic blood pressure"}]},
                              "valueQuantity": _quantity(vitals["diastolic"], "mmHg", "mm[Hg]")}]}))
    for key, (code, display, ucum, unit) in VITALS.items():
        if key in vitals:
            refs.append(add({"resourceType": "Observation", **common, "category": _category("vital-signs" if key in VITAL_SIGNS else "laboratory"),
                             "code": {"coding": [{"system": LOINC, "code": code, "display": display}]},
                             "valueQuantity": _quantity(vitals[key], unit, ucum)}))
    for lab in result.get("labs") or []:
        obs: dict[str, Any] = {"resourceType": "Observation", **common, "category": _category("laboratory"), "code": {"text": lab["test"]},
                               "valueQuantity": _quantity(lab["value"], lab["unit"], UCUM_UNITS.get(lab["unit"]))}
        if lab.get("reference"):
            obs["referenceRange"] = [{"text": lab["reference"]}]
        if lab.get("flag") in FLAG_CODES:
            c, d = FLAG_CODES[lab["flag"]]
            obs["interpretation"] = [{"coding": [{"system": INTERP, "code": c, "display": d}]}]
        refs.append(add(obs))

    sc = result.get("scores") or {}
    eg = sc.get("egfr") or {}
    if eg.get("value") is not None:
        refs.append(add({"resourceType": "Observation", **common, "category": _category("laboratory"),
                         "code": {"coding": [{"system": LOINC, "code": "98979-8", "display": "Glomerular filtration rate/1.73 sq M.predicted [Volume Rate/Area] in Serum, Plasma or Blood by Creatinine-based formula (CKD-EPI 2021)"}]},
                         "valueQuantity": _quantity(eg["value"], "mL/min/{1.73_m2}", "mL/min/{1.73_m2}"), "note": [{"text": eg.get("interpretation", "")}]}))
    n2 = sc.get("news2") or {}
    if n2.get("components"):
        refs.append(add({"resourceType": "Observation", **common, "category": _category("survey"), "code": {"text": "NEWS2 total score (RCP 2017)"}, "valueInteger": n2["score"],
                         "interpretation": [{"text": f"{n2['risk']} clinical risk"}],
                         "note": [{"text": n2.get("note") or n2.get("response", "")}]}))
    for med in result.get("medication_details") or []:
        dose = " ".join(str(x) for x in (f"{med['dose']:g}" if med.get("dose") is not None else None, med.get("unit"), med.get("frequency")) if x)
        refs.append(add({"resourceType": "MedicationStatement", "status": "unknown", "subject": subject, "dateAsserted": now,
                         "medicationCodeableConcept": {"text": med["name"]}, **({"dosage": [{"text": dose}]} if dose else {}),
                         "note": [{"text": "Extracted from free text; reconcile with the patient and medication record."}]}))
    allergies = result.get("allergies") or {}
    for item in allergies.get("items") or []:
        refs.append(add({"resourceType": "AllergyIntolerance", "patient": subject, "recordedDate": now, "code": {"text": item},
                         "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification", "code": "unconfirmed"}]}}))
    for cond in result.get("possible_conditions") or []:
        code: dict[str, Any] = {"text": cond["condition"]}
        for prefix, (sct, display) in SNOMED_CONDITIONS.items():
            if cond["condition"].startswith(prefix):
                code["coding"] = [{"system": SNOMED, "code": sct, "display": display}]
                break
        refs.append(add({"resourceType": "Condition", "subject": subject, "recordedDate": now, "code": code,
                         "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "provisional"}]},
                         **({"evidence": [{"code": [{"text": f} for f in cond["supporting_findings"]]}]} if cond.get("supporting_findings") else {}),
                         "note": [{"text": f"Decision-support suggestion ({cond.get('likelihood')}); requires clinician confirmation. Not a diagnosis."}]}))

    for risk in result.get("risks") or []:
        if not risk.get("available"):
            continue
        refs.append(add({"resourceType": "RiskAssessment", "status": "preliminary", "subject": subject, "occurrenceDateTime": now,
                         "device": {"reference": device_ref}, "method": {"text": risk.get("model", "")},
                         "prediction": [{"outcome": {"text": risk.get("target") or risk["disease"]}, "probabilityDecimal": risk["probability"],
                                         "qualitativeRisk": {"text": risk.get("level")}}],
                         "note": [{"text": risk.get("caveat", "")}]}))

    if result.get("urgent_attention"):
        reasons = result.get("urgent_reasons") or ["Potential emergency warning signs"]
        refs.append(add({"resourceType": "DetectedIssue", "status": "preliminary", "severity": "high", "patient": subject, "identifiedDateTime": now,
                         "code": {"text": "Potential emergency warning signs"}, "detail": "; ".join(reasons), "author": {"reference": device_ref}}))

    add({"resourceType": "Provenance", "target": [{"reference": r} for r in refs] or [subject], "recorded": now,
         "activity": {"text": "Automated extraction and decision-support analysis"},
         "agent": [{"type": {"text": "assembler"}, "who": {"reference": device_ref}}],
         **({"entity": [{"role": "source", "what": {"identifier": {"system": "urn:clarity:request-id", "value": request_id}}}]} if request_id else {})})

    bundle: dict[str, Any] = {"resourceType": "Bundle", "type": "collection", "timestamp": now, "entry": entries}
    if request_id:
        bundle["identifier"] = {"system": "urn:clarity:request-id", "value": request_id}
    return bundle
