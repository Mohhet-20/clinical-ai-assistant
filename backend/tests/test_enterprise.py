"""Security, privacy, governance, interoperability and clinical-safety behaviour."""
from __future__ import annotations

import json
from io import BytesIO
from types import SimpleNamespace

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app import agent, audit, fhir, main, ml, nlp, phi, security

DIABETES_NOTE = "45-year-old female, increased thirst. Fasting glucose 182 mg/dL, HbA1c 8.1%, BMI 33, BP 128/84."
PHI_NOTE = ("Patient Name: Jane Q. Doe  MRN: A99887766  DOB: 04/12/1971. Phone 555-867-5309, jane.doe@example.org, 12 Elm Street. "
            "Seen by Dr. Rivera on March 3, 2026. Reports thirst and frequent urination. Glucose 182 mg/dL, BMI 33, age 54.")


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("API_KEYS", "clin-key-123")
    monkeypatch.setenv("ADMIN_API_KEYS", "admin-key-456")
    return {"clin": {"Authorization": "Bearer clin-key-123"}, "admin": {"X-API-Key": "admin-key-456"}}


@pytest.fixture
def fresh_audit(monkeypatch, tmp_path):
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    audit.reset_cache()
    yield tmp_path / "audit.jsonl"
    audit.reset_cache()


class FakeLLM:
    """Records every prompt sent to the 'external' provider."""

    def __init__(self, reply: str = '{"symptoms": ["thirst"]}') -> None:
        self.sent: list[str] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.reply = reply

    def _create(self, **kwargs):
        self.sent.append(json.dumps(kwargs["messages"]))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.reply))])


# ---------------------------------------------------------------- auth & rate limiting
def test_auth_disabled_by_default_and_reported(client) -> None:
    assert client.get("/v1/health").json()["auth"] == "disabled"
    assert client.post("/v1/analyze", json={"text": "thirst"}).status_code == 200


def test_auth_required_when_keys_configured(client, keys) -> None:
    r = client.post("/v1/analyze", json={"text": "thirst"})
    assert r.status_code == 401 and r.headers["WWW-Authenticate"] == "Bearer" and r.json()["request_id"]
    assert client.post("/v1/analyze", json={"text": "thirst"}, headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.post("/v1/analyze", json={"text": "thirst"}, headers=keys["clin"]).status_code == 200
    assert client.get("/v1/health").status_code == 200          # liveness stays public


def test_admin_routes_need_admin_role(client, keys) -> None:
    assert client.get("/v1/audit/verify", headers=keys["clin"]).status_code == 403
    assert client.get("/metrics", headers=keys["clin"]).status_code == 403
    assert client.get("/v1/audit/verify", headers=keys["admin"]).status_code == 200
    assert client.get("/metrics", headers=keys["admin"]).status_code == 200


def test_rate_limit_returns_429_with_retry_after(client, monkeypatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "2")
    monkeypatch.setattr(security, "LIMITER", security.RateLimiter())
    codes = [client.post("/v1/chat", json={"message": "diabetes criteria?"}).status_code for _ in range(3)]
    assert codes[:2] == [200, 200] and codes[2] == 429
    r = client.post("/v1/chat", json={"message": "again"})
    assert int(r.headers["Retry-After"]) >= 1


def test_production_without_keys_refuses_to_start(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="requires API_KEYS"):
        with TestClient(main.app):
            pass


# ---------------------------------------------------------------- HTTP hygiene
def test_request_id_and_security_headers(client) -> None:
    r = client.get("/v1/health", headers={"X-Request-ID": "trace-abc-12345"})
    assert r.headers["X-Request-ID"] == "trace-abc-12345"
    assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["Cache-Control"] == "no-store"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert client.get("/v1/health", headers={"X-Request-ID": "bad id with spaces"}).headers["X-Request-ID"] != "bad id with spaces"


def test_validation_errors_do_not_echo_input(client) -> None:
    secret = "Jane Doe MRN 12345 " * 2000   # over the length limit
    r = client.post("/v1/analyze", json={"text": secret})
    assert r.status_code == 422 and "Jane Doe" not in r.text and r.json()["request_id"]


def test_legacy_routes_still_work_but_are_hidden(client) -> None:
    assert client.post("/analyze", json={"text": "thirst"}).status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    assert "/v1/analyze" in paths and "/analyze" not in paths


def test_ready_endpoint(client) -> None:
    body = client.get("/v1/ready").json()
    assert body["ready"] and body["checks"]["model_heart"] and body["checks"]["evidence_index"]


def test_metrics_exposition(client) -> None:
    client.post("/v1/analyze", json={"text": "Severe chest pain."})
    text = client.get("/metrics").text
    assert 'clarity_http_requests_total{method="POST",route="/v1/analyze",status="200"}' in text
    assert 'clarity_events_total{event="urgent_flags"}' in text and "clarity_http_request_duration_seconds_bucket" in text


# ---------------------------------------------------------------- uploads
def test_spoofed_file_types_are_rejected(client) -> None:
    exe = b"MZ\x90\x00\x03\x00\x00\x00" + bytes(64)
    assert client.post("/v1/upload", files={"file": ("scan.png", exe, "image/png")}).status_code == 415
    assert client.post("/v1/upload", files={"file": ("note.pdf", b"just text", "application/pdf")}).status_code == 415


def test_pdf_page_limit(client, monkeypatch) -> None:
    monkeypatch.setattr(main, "MAX_PDF_PAGES", 2)
    doc = pymupdf.open()
    for _ in range(3):
        doc.new_page().insert_text((72, 72), "Fatigue.")
    r = client.post("/v1/upload", files={"file": ("big.pdf", BytesIO(doc.tobytes()), "application/pdf")})
    assert r.status_code == 413 and "limit is 2" in r.json()["detail"]


# ---------------------------------------------------------------- privacy
def test_deidentify_removes_identifiers_and_keeps_clinical_values() -> None:
    red, counts = phi.deidentify(PHI_NOTE)
    for ident in ("Jane", "Doe", "A99887766", "04/12/1971", "555-867-5309", "jane.doe@example.org", "12 Elm Street", "Rivera", "March 3, 2026"):
        assert ident not in red, ident
    assert {"NAME", "ID", "DATE", "PHONE", "EMAIL", "ADDRESS"} <= set(counts)
    for kept in ("182 mg/dL", "BMI 33", "age 54", "thirst"):
        assert kept in red


def test_deidentify_does_not_damage_clinical_text() -> None:
    text = "BP 150/95 mmHg. HbA1c 8.1%. Ref 70 - 100. 58-year-old. Glucose 7.5 mmol/L"
    assert phi.deidentify(text) == (text, {})
    assert phi.redact("A 94 year old woman") == "A 90+ year old woman"


def test_no_phi_reaches_the_llm(client, monkeypatch) -> None:
    fake = FakeLLM()
    monkeypatch.setattr(agent, "llm_client", lambda: fake)
    body = client.post("/v1/analyze", json={"text": PHI_NOTE}).json()
    chat = FakeLLM("Answer [ada-diabetes-diagnosis]")
    monkeypatch.setattr(agent, "llm_client", lambda: chat)
    client.post("/v1/chat", json={"message": "Is Jane Doe (MRN A99887766) diabetic?", "context": PHI_NOTE,
                                  "history": [{"role": "user", "content": "Call 555-867-5309"}]})
    sent = " ".join(fake.sent + chat.sent)
    assert fake.sent and chat.sent
    for ident in ("Jane", "Doe", "A99887766", "555-867-5309", "jane.doe@example.org", "Rivera"):
        assert ident not in sent, ident
    assert body["privacy"]["phi_redacted"] >= 6 and "Increased thirst" in body["symptoms"]   # local NLP still used full text


def test_pubmed_query_is_redacted(client, monkeypatch) -> None:
    queries: list[str] = []
    monkeypatch.setattr(agent.rag, "pubmed_search", lambda q, retmax=3: queries.append(q) or [])
    client.post("/v1/chat", json={"message": "Diabetes criteria for patient Mr. Henderson, MRN 77812345?"})
    assert queries and "Henderson" not in queries[0] and "77812345" not in queries[0] and "[" not in queries[0].split(")")[0]


# ---------------------------------------------------------------- audit trail
def test_analysis_is_audited_without_clinical_text(client, fresh_audit) -> None:
    r = client.post("/v1/analyze", json={"text": PHI_NOTE})
    rid = r.headers["X-Request-ID"]
    assert r.json()["request_id"] == rid
    raw = fresh_audit.read_text()
    assert "Jane" not in raw and "thirst" not in raw.lower() and "182" not in raw
    rec = client.get("/v1/audit", params={"request_id": rid}).json()["records"][0]
    assert rec["event"] == "analysis" and rec["data"]["input_sha256"] == audit.sha256(PHI_NOTE)
    assert rec["data"]["provenance"]["models"]["diabetes"].startswith("diabetes-lr-")


def test_audit_chain_detects_tampering(client, fresh_audit) -> None:
    for t in ("thirst", "fatigue", "cough"):
        client.post("/v1/analyze", json={"text": t})
    assert client.get("/v1/audit/verify").json() == {**client.get("/v1/audit/verify").json(), "valid": True, "records": 3}
    lines = fresh_audit.read_text().splitlines()
    lines[1] = lines[1].replace('"urgent":false', '"urgent":true')
    fresh_audit.write_text("\n".join(lines) + "\n")
    v = client.get("/v1/audit/verify").json()
    assert v["valid"] is False and v["broken_at_line"] == 2


def test_clinician_feedback_is_recorded_and_redacted(client, fresh_audit) -> None:
    rid = client.post("/v1/analyze", json={"text": DIABETES_NOTE}).headers["X-Request-ID"]
    r = client.post("/v1/feedback", json={"request_id": rid, "target": "condition", "item": "Diabetes mellitus / hyperglycaemia",
                                          "verdict": "agree", "comment": "Confirmed with Dr. Alvarez, call 555-222-3333"})
    assert r.status_code == 201 and r.json()["audit_seq"] == 2
    rec = client.get("/v1/audit", params={"event": "clinician_feedback"}).json()["records"][0]
    assert rec["data"]["analysis_request_id"] == rid and "Alvarez" not in rec["data"]["comment"] and "555" not in rec["data"]["comment"]
    assert client.post("/v1/feedback", json={"request_id": rid, "target": "condition", "verdict": "maybe"}).status_code == 422


# ---------------------------------------------------------------- FHIR
def test_fhir_bundle_export(client) -> None:
    result = client.post("/v1/analyze", json={"text": DIABETES_NOTE + " SpO2 88%. Severe chest pain."}).json()
    r = client.post("/v1/fhir/bundle", json=result)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/fhir+json")
    bundle = r.json()
    types = [e["resource"]["resourceType"] for e in bundle["entry"]]
    assert bundle["resourceType"] == "Bundle" and bundle["identifier"]["value"] == result["request_id"]
    assert {"Patient", "Device", "Observation", "Condition", "RiskAssessment", "DetectedIssue", "Provenance"} <= set(types)
    res = [e["resource"] for e in bundle["entry"]]
    codes = {c["code"] for x in res if x["resourceType"] == "Observation" for c in x["code"].get("coding", [])}
    assert {"85354-9", "2345-7", "4548-4", "39156-5", "59408-5"} <= codes
    cond = next(x for x in res if x["resourceType"] == "Condition" and x["code"]["text"].startswith("Diabetes"))
    assert cond["verificationStatus"]["coding"][0]["code"] == "provisional" and cond["code"]["coding"][0]["code"] == "73211009"
    patient = next(x for x in res if x["resourceType"] == "Patient")
    assert patient["gender"] == "female" and "identifier" not in patient and "name" not in patient
    assert all(v != [] for x in res for v in x.values())   # FHIR forbids empty arrays
    assert client.post("/v1/fhir/bundle", json={"hello": "world"}).status_code == 422


def test_fhir_lab_interpretation() -> None:
    b = fhir.build_bundle({"labs": [{"test": "HbA1c", "value": 6.9, "unit": "%", "reference": "4.0 - 5.6", "flag": "high"}],
                           "risks": [], "possible_conditions": []})
    obs = next(e["resource"] for e in b["entry"] if e["resource"]["resourceType"] == "Observation")
    assert obs["interpretation"][0]["coding"][0]["code"] == "H" and obs["valueQuantity"]["code"] == "%"


# ---------------------------------------------------------------- clinical NLP safety
@pytest.mark.parametrize("text,present,absent", [
    ("Denies fever but reports cough.", ["Cough"], ["Fever"]),
    ("Denies chest pain and shortness of breath.", [], ["Chest pain", "Shortness of breath"]),
    ("No headache; however complains of dizziness.", ["Dizziness"], ["Headache"]),
])
def test_negation_scope(text, present, absent) -> None:
    names = {e["name"] for e in nlp.extract_entities(text)}
    assert set(present) <= names and not set(absent) & names


def test_new_vitals_and_explainable_urgency(client) -> None:
    body = client.post("/v1/analyze", json={"text": "Cough. SpO2 86% on room air, temp 102.4 F, RR 32, HR 128, BP 85/50."}).json()
    v = body["vitals"]
    assert v["spo2"] == 86 and v["temperature"] == 39.1 and v["respiratory_rate"] == 32
    assert body["urgent_attention"] and any("SpO2 86%" in r for r in body["urgent_reasons"]) and any("Hypotension" in r for r in body["urgent_reasons"])
    assert "SpO2 86%" in body["recommended_actions"][0]["rationale"]


def test_normal_vitals_are_not_urgent(client) -> None:
    body = client.post("/v1/analyze", json={"text": "Routine review. Temp 37.0 C, SpO2 98%, RR 14, HR 72, BP 122/78."}).json()
    assert body["urgent_attention"] is False and body["urgent_reasons"] == []


def test_hypoglycaemia_is_urgent() -> None:
    assert any("hypoglycaemia" in r for r in nlp.urgent_findings("", {"glucose": 45}))


# ---------------------------------------------------------------- model governance
def test_model_cards_and_metrics(client) -> None:
    info = client.get("/v1/models").json()
    for key in ("heart", "diabetes"):
        m = info[key]
        assert m["version"].startswith(f"{key}-lr-") and len(m["data_sha256"]) == 64
        assert m["card"]["intended_use"] and m["card"]["limitations"] and m["card"]["out_of_scope"]
        assert 0 < m["metrics"]["holdout_brier"] < 0.25 and m["metrics"]["holdout_sensitivity"] and m["metrics"]["holdout_specificity"]


def test_out_of_range_inputs_lower_reliability() -> None:
    r = ml.predict("diabetes", {"Glucose": 182, "BMI": 95, "Age": 45})
    assert r["reliability"] == "low" and "BMI=95" in r["out_of_range"][0] and "unreliable" in r["caveat"]


def test_imputed_or_assumed_inputs_are_never_drivers() -> None:
    r = ml.predict("diabetes", {"Glucose": 182, "BMI": 33, "Age": 45})
    named = {d["feature"] for d in r["drivers"]}
    assert not named & (set(r["imputed"]) | {"Pregnancies"}) and "assumed to be 0" in r["caveat"]


def test_tampered_model_artifact_is_not_loaded(monkeypatch, tmp_path) -> None:
    spec = dict(ml.SPECS["heart"], path=tmp_path / "heart.joblib")
    monkeypatch.setitem(ml.SPECS, "heart", spec)
    monkeypatch.setattr(ml, "_loaded", {})
    ml.get_model("heart")
    good = spec["path"].read_bytes()
    spec["path"].write_bytes(good + b"tamper")
    monkeypatch.setattr(ml, "_loaded", {})
    loaded = []
    monkeypatch.setattr(ml.joblib, "load", lambda p: loaded.append(p))
    assert ml.get_model("heart") is not None and loaded == []   # retrained instead of deserialising the tampered file


def test_provenance_in_every_result(client) -> None:
    p = client.post("/v1/analyze", json={"text": "thirst"}).json()["provenance"]
    assert p["service_version"] == agent.VERSION and p["models"]["heart"] and p["evidence_corpus"] and p["llm"] is None


def test_pubmed_parser_rejects_entity_expansion() -> None:
    from app import rag
    bomb = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><PubmedArticleSet>&b;</PubmedArticleSet>'
    with pytest.raises(ValueError):
        rag.parse_pubmed_xml(bomb)
    assert rag.pubmed_search.__doc__ and "never raises" in rag.pubmed_search.__doc__   # callers rely on swallow-and-continue
