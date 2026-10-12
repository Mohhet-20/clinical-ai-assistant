from __future__ import annotations

from io import BytesIO

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app import main, ml, nlp, rag

HEART = {"age": 55, "sex": 1, "cp": 2, "trestbps": 130, "chol": 240, "fbs": 0, "restecg": 0, "thalach": 150, "exang": 0, "oldpeak": 1.0, "slope": 2, "ca": 0, "thal": 3}


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:   # runs lifespan: builds FAISS index, loads models
        yield c


def test_health_reports_capabilities(client) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["evidence_documents"] >= 10
    assert body["vector_store"] in ("faiss", "numpy")
    assert body["models"] == {"heart": True, "diabetes": True}


def test_models_endpoint_has_metrics(client) -> None:
    info = client.get("/models").json()
    assert info["heart"]["metrics"]["holdout_roc_auc"] > 0.8
    assert info["diabetes"]["metrics"]["holdout_roc_auc"] > 0.7


def test_negation_and_extraction(client) -> None:
    body = client.post("/analyze", json={"text": "Patient denies chest pain but reports frequent urination and thirst."}).json()
    assert body["urgent_attention"] is False
    assert "Frequent urination" in body["symptoms"] and "Chest pain" not in body["symptoms"]


def test_family_history_is_not_reported_as_patient_condition(client) -> None:
    body = client.post("/analyze", json={"text": "Family history of diabetes; the patient has no documented diagnosis."}).json()
    assert "Diabetes" not in body["conditions"]
    assert "Family history" in body["risk_factors"]


def test_urgent_detection(client) -> None:
    body = client.post("/analyze", json={"text": "Patient denies prior issues, but now has severe chest pain."}).json()
    assert body["urgent_attention"] is True
    assert body["recommended_actions"][0]["action"].startswith("Potential emergency")


def test_agent_trace_has_three_steps(client) -> None:
    body = client.post("/analyze", json={"text": "58 year old with thirst."}).json()
    assert [t["step"][:1] for t in body["agent_trace"]] == ["1", "2", "3"]


def test_vitals_feed_diabetes_model_and_differential(client) -> None:
    text = "45-year-old female, increased thirst and frequent urination. Fasting glucose 182 mg/dL, HbA1c 8.1%, BMI 33, BP 128/84."
    body = client.post("/analyze", json={"text": text}).json()
    assert body["vitals"]["glucose"] == 182 and body["vitals"]["hba1c"] == 8.1
    diab = next(r for r in body["risks"] if r["key"] == "diabetes")
    assert diab["available"] and diab["probability"] > 0.5 and diab["imputed"]
    assert body["possible_conditions"][0]["condition"].startswith("Diabetes")
    assert body["risk_score"]["disease"] == "Diabetes"
    assert any(a["evidence_ids"] for a in body["recommended_actions"])
    ids = {e["id"] for e in body["evidence"]}
    assert all(i in ids for a in body["recommended_actions"] for i in a["evidence_ids"])


def test_heart_model_with_all_inputs(client) -> None:
    body = client.post("/analyze", json={"text": "Clinical note.", "risk_features": HEART}).json()
    heart = next(r for r in body["risks"] if r["key"] == "heart")
    assert heart["available"] and 0 <= heart["probability"] <= 1 and heart["level"] in ("low", "moderate", "high")


def test_heart_model_reports_missing_inputs() -> None:
    r = ml.predict("heart", {"age": 55})
    assert not r["available"] and "sex" in r["message"]


def test_faiss_retrieval_is_relevant(client) -> None:
    hits = rag.INDEX.search("increased thirst and frequent urination, possible diabetes")
    assert hits and hits[0]["id"] in ("cdc-diabetes-symptoms", "ada-diabetes-diagnosis", "uspstf-diabetes-screening")


def test_pubmed_xml_parser() -> None:
    xml = b"""<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID><Article><Journal><Title>J Test</Title>
    <JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue></Journal><ArticleTitle>Diabetes screening</ArticleTitle>
    <Abstract><AbstractText>Screening works.</AbstractText></Abstract></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"""
    docs = rag.parse_pubmed_xml(xml)
    assert docs[0]["id"] == "pmid-123" and docs[0]["url"].endswith("/123/") and docs[0]["kind"] == "pubmed"


def test_pubmed_results_are_merged(client, monkeypatch) -> None:
    fake = {"id": "pmid-1", "title": "T", "source": "S", "url": "https://pubmed.ncbi.nlm.nih.gov/1/", "text": "x", "kind": "pubmed"}
    monkeypatch.setattr(rag, "pubmed_search", lambda q, retmax=3: [fake])
    body = client.post("/analyze", json={"text": "Thirst and frequent urination."}).json()
    assert any(e["id"] == "pmid-1" for e in body["evidence"])


def test_text_upload_with_notes_and_chat(client) -> None:
    up = client.post("/upload", files={"file": ("report.txt", "Fatigue and diabetes are documented.", "text/plain")}, data={"notes": "Also reports thirst."})
    assert up.status_code == 200
    body = up.json()
    assert body["document_name"] == "report.txt" and "Increased thirst" in body["symptoms"] and "Diabetes" in body["conditions"]
    chat = client.post("/chat", json={"message": "What evidence mentions diabetes?", "context": body["extracted_text"], "history": []})
    assert chat.status_code == 200 and chat.json()["evidence"]


def test_pdf_upload_extracts_text(client) -> None:
    document = pymupdf.open()
    document.new_page().insert_text((72, 72), "Patient reports fatigue. BP 150/95 mmHg.")
    payload = document.tobytes()
    document.close()
    r = client.post("/upload", files={"file": ("report.pdf", BytesIO(payload), "application/pdf")})
    assert r.status_code == 200
    assert "fatigue" in r.json()["extracted_text"].lower() and r.json()["vitals"]["systolic"] == 150


def test_image_without_key_requires_notes(client) -> None:
    assert client.post("/upload", files={"file": ("x.png", b"img", "image/png")}).status_code == 503
    r = client.post("/upload", files={"file": ("x.png", b"img", "image/png")}, data={"notes": "Cough and wheezing for a week."})
    assert r.status_code == 200 and r.json()["input_modality"] == "image" and r.json()["image_note"]


def test_image_service_failure_falls_back_to_notes(client, monkeypatch) -> None:
    monkeypatch.setattr(main.agent, "llm_client", lambda: object())
    monkeypatch.setattr(main, "image_to_text", lambda *_: (_ for _ in ()).throw(RuntimeError("provider error")))
    r = client.post("/upload", files={"file": ("x.png", b"img", "image/png")}, data={"notes": "Cough and wheezing for a week."})
    assert r.status_code == 200 and r.json()["image_note"]
    assert "Cough" in r.json()["symptoms"] and "provider error" not in r.text


def test_upload_validation(client) -> None:
    assert client.post("/upload").status_code == 422
    assert client.post("/upload", files={"file": ("a.exe", b"x", "application/octet-stream")}).status_code == 415
    assert client.post("/upload", data={"notes": "x", "risk_features": "[1]"}).status_code == 422
    assert client.post("/upload", data={"notes": "x", "risk_features": '{"age":Infinity}'}).status_code == 422
    assert client.post("/analyze", content='{"text":"x","risk_features":{"age":1e999}}', headers={"content-type": "application/json"}).status_code == 422


def test_evidence_catalog(client) -> None:
    ids = {i["id"] for i in client.get("/evidence").json()}
    assert {"uci-cleveland-data", "ada-diabetes-diagnosis"} <= ids


def test_vitals_parser() -> None:
    v = nlp.extract_vitals("62 y/o male. Blood pressure: 182/124 mmHg, glucose 7.5 mmol/L, cholesterol 250")
    assert v["age"] == 62 and v["sex"] == 1 and v["systolic"] == 182 and v["glucose"] == 135 and v["cholesterol"] == 250


def test_unreadable_pdf_gets_clear_error(client) -> None:
    document = pymupdf.open()
    document.new_page()  # blank page => no text
    payload = document.tobytes()
    document.close()
    r = client.post("/upload", files={"file": ("scan.pdf", BytesIO(payload), "application/pdf")})
    assert r.status_code == 422 and "machine-readable" in r.json()["detail"]
    r = client.post("/upload", files={"file": ("scan.pdf", BytesIO(payload), "application/pdf")}, data={"notes": "Thirst and fatigue."})
    assert r.status_code == 200 and "Increased thirst" in r.json()["symptoms"]


def test_readable_heuristic() -> None:
    assert main.readable("Patient reports fatigue. BP 150/95 mmHg.")
    assert not main.readable("\ufffd\ufffd\ue000\ue001\ufffd\ufffd\ufffd\ufffd")


def test_symbol_font_pdf_text_is_decoded() -> None:
    garbled = "".join(chr(0xF000 + ord(c)) if c != "\n" else c for c in "Male 25 Years\nGlucose 182 mg/dL")
    fixed = main.fix_symbol_font(garbled)
    assert fixed == "Male 25 Years\nGlucose 182 mg/dL" and main.readable(fixed)


LAB_TEXT = """Age                : 25 Years
Gender            : Male
   GLUCOSE, FASTING (F), PLASMA         126          mg/dL                   70 - 100
   Cholesterol  Total                   245          mg/dL                   <200
   HbA1c                                6.9          %                       4.00 - 5.60

   Interpretation
   Diabetes and stroke risk tables, family history, obesity and heart disease are discussed here.
   | CARDIO CRP IN mg/L    | CARDIOVASCULAR RISK |

   LIPOPROTEIN(a); Lp(a), SERUM         10           mg/dL                   <20
"""


def test_lab_report_parsing_and_boilerplate(client) -> None:
    body = client.post("/analyze", json={"text": LAB_TEXT}).json()
    flags = {l["test"].lower(): l["flag"] for l in body["labs"]}
    assert flags["hba1c"] == "high" and flags["lipoprotein(a); lp(a), serum"] == "normal"
    assert body["vitals"]["age"] == 25 and body["vitals"]["glucose"] == 126 and body["vitals"]["cholesterol"] == 245
    assert body["conditions"] == [] and body["risk_factors"] == []   # no false positives from interpretation text
    assert "Out-of-range labs" in body["summary"]
