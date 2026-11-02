"""FastAPI service.

Clinical routes (SSO token or API key + rate limit when auth is enabled):
    POST /v1/analyze, /v1/upload, /v1/chat, /v1/feedback, /v1/fhir/bundle
    GET  /v1/me, /v1/cases, /v1/cases/{id};  DELETE /v1/cases/{id}
Public:  GET /v1/health, /v1/ready, /v1/models, /v1/evidence, /v1/auth/config
Admin:   GET /v1/audit, /v1/audit/verify, /metrics

Unversioned aliases (/analyze, /upload, ...) are kept for existing clients and
hidden from the OpenAPI schema."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import math
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

import pymupdf
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
if os.getenv("PYTHON_DOTENV_DISABLED", "").lower() not in ("1", "true"):
    load_dotenv(ROOT / ".env")

from . import agent, audit, cases, fhir, ml, phi, rag  # noqa: E402  (after load_dotenv so env is visible)
from .observability import METRICS, configure_logging, new_request_id, request_id_var  # noqa: E402
from .security import Principal, auth_enabled, auth_mode, authenticate, oidc_enabled, rate_limit, require_admin  # noqa: E402

configure_logging(os.getenv("LOG_FORMAT", "json"), os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("clinical.api")
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_PDF_PAGES = int(os.getenv("MAX_PDF_PAGES", "60"))
MAX_TEXT_CHARS = agent.MAX_TEXT_CHARS
EXT_TYPES = {".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/plain", ".png": "image/png",
             ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
ALLOWED = set(EXT_TYPES.values())
SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                    "Cache-Control": "no-store", "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
                    "Permissions-Policy": "camera=(), microphone=(), geolocation=()", "Cross-Origin-Opener-Policy": "same-origin"}
DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")
API_PREFIX = "/v1"


@asynccontextmanager
async def lifespan(_: FastAPI):
    if os.getenv("ENVIRONMENT", "development").lower() == "production" and not auth_enabled():
        raise RuntimeError("ENVIRONMENT=production requires API_KEYS or ADMIN_API_KEYS; refusing to start without authentication.")
    if oidc_enabled() and not os.getenv("OIDC_AUDIENCE"):
        raise RuntimeError("OIDC_ISSUER requires OIDC_AUDIENCE; tokens issued for other applications must not be accepted.")
    cases.validate_config()
    if cases.enabled():
        log.info("Case store enabled; purged %d expired case(s)", await asyncio.to_thread(cases.purge_expired))
    if not auth_enabled():
        log.warning("Authentication is DISABLED (no API_KEYS set). Use only for local development with synthetic data.")
    await asyncio.to_thread(rag.INDEX.build)   # build FAISS index
    await asyncio.to_thread(ml.model_info)     # load or train the ML models
    yield


docs_on = os.getenv("DOCS_ENABLED", "true").lower() not in ("0", "false", "no")
app = FastAPI(title="Clarity Clinical Decision Support", version=agent.VERSION, lifespan=lifespan,
              docs_url="/docs" if docs_on else None, redoc_url="/redoc" if docs_on else None, openapi_url="/openapi.json" if docs_on else None,
              description="Multimodal clinical decision support: PDF/text/image intake, NLP + LLM extraction with PHI redaction, "
                          "FAISS/PubMed RAG, tabular ML risk models, a LangChain agent pipeline, FHIR R4 export and a tamper-evident audit trail. "
                          "Research prototype - not a medical device.")
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["GET", "POST", "DELETE"],
                   allow_headers=["Authorization", "X-API-Key", "Content-Type", "X-Request-ID"], expose_headers=["X-Request-ID", "Retry-After"])


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = new_request_id(request.headers.get("x-request-id"))
    token = request_id_var.set(rid)
    request.state.request_id = rid
    t0 = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:  # noqa: BLE001 - last-resort handler; never echo internals
        log.error("Unhandled %s", type(exc).__name__)
        response = JSONResponse({"detail": "Internal server error.", "request_id": rid}, status_code=500)
    elapsed = time.perf_counter() - t0
    route = getattr(request.scope.get("route"), "path", "unmatched")   # template, not raw path: bounded label cardinality
    if request.url.path.startswith(API_PREFIX + "/") and not route.startswith(API_PREFIX):
        route = API_PREFIX + route   # included routers report their inner path
    METRICS.observe(request.method, route, response.status_code, elapsed)
    log.info("request", extra={"method": request.method, "route": route, "status": response.status_code, "ms": round(elapsed * 1000)})
    response.headers["X-Request-ID"] = rid
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    if not request.url.path.startswith(DOCS_PATHS):
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
    request_id_var.reset(token)
    return response


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse({"detail": exc.detail, "request_id": request_id_var.get()}, status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # drop the echoed 'input' so rejected clinical text is not reflected back or into logs
    errors = [{k: v for k, v in e.items() if k not in ("input", "ctx", "url")} for e in exc.errors()]
    return JSONResponse({"detail": errors, "request_id": request_id_var.get()}, status_code=422)


# ---------------------------------------------------------------- schemas
class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    risk_features: dict[str, float] = Field(default_factory=dict)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    context: str = Field(default="", max_length=MAX_TEXT_CHARS)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


class FeedbackRequest(BaseModel):
    request_id: str = Field(pattern=r"^[A-Za-z0-9._-]{8,64}$", description="X-Request-ID of the analysis being reviewed")
    target: Literal["summary", "condition", "action", "risk", "extraction", "evidence", "chat"]
    item: str = Field(default="", max_length=300, description="Which condition/action/etc. the verdict refers to")
    verdict: Literal["agree", "disagree", "unsure"]
    comment: str = Field(default="", max_length=2000)


# ---------------------------------------------------------------- helpers
def image_to_text(data: bytes | list[bytes], content_type: str) -> str:
    """Vision-model transcription of one image (or several page images)."""
    client = agent.llm_client()
    if not client:
        raise HTTPException(status_code=503, detail="Image interpretation requires OPENAI_API_KEY (backend/.env). Alternatively add typed notes describing the image.")
    images = data if isinstance(data, list) else [data]
    content: list[dict[str, Any]] = [{"type": "text", "text": "Transcribe all visible text (labs, vitals, medications, history) and describe image modality/visible features for clinician review. Do not diagnose. Replace any patient names, ID numbers, addresses, phone numbers and dates of birth with [REDACTED]."}]
    for img in images:
        encoded = base64.b64encode(img).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{encoded}"}})
    response = client.chat.completions.create(model=os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini"), temperature=0, messages=[
        {"role": "system", "content": "Extract only legible printed text and non-diagnostic visual descriptors from this medical image or report scan (X-ray, fundus, ECG, lab report). Do not diagnose, interpret radiology, or recommend treatment. State uncertainty and unreadable regions."},
        {"role": "user", "content": content}])
    return response.choices[0].message.content or "No readable content identified."


async def image_to_text_or_fallback(data: bytes | list[bytes], content_type: str, has_notes: bool) -> tuple[str, str | None]:
    try:
        return await asyncio.to_thread(image_to_text, data, content_type), None
    except HTTPException:
        if not has_notes:
            raise
    except Exception as exc:
        if not has_notes:
            raise HTTPException(status_code=503, detail="Image interpretation is unavailable. Add typed notes or try again when the image service is available.") from exc
    return "", "Image interpretation was unavailable; analysis used the typed notes only."


_PUA_LO, _PUA_HI = "\uf020", "\uf07e"   # Symbol-font private-use range


def fix_symbol_font(text: str) -> str:
    """Many lab-system PDFs use a Symbol-style font whose glyphs extract as U+F020..U+F0FF; map them back to ASCII."""
    return "".join(chr(ord(c) - 0xF000) if _PUA_LO <= c <= _PUA_HI else c for c in text)


def readable(text: str) -> bool:
    """False for empty text or PDFs whose fonts extract as boxes / private-use glyphs."""
    sample = text.strip()[:5000]
    if not sample:
        return False
    good = sum(1 for c in sample if c.isascii() and (c.isalnum() or c in " \n.,:;/%()-"))
    return good / len(sample) > 0.7


def sniff(data: bytes) -> str | None:
    """Content type from magic bytes - the client-declared type and extension are not trusted."""
    if b"%PDF-" in data[:1024]:
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" not in data[:8192]:
        return "text/plain"   # any encoding; decode_text() works out which
    return None


def decode_text(data: bytes) -> str:
    """UTF-8 (with or without BOM), UTF-16 with BOM, else Windows-1252 - the encodings clinical exports actually use."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def pdf_pages_as_png(data: bytes, max_pages: int = 4) -> list[bytes]:
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return [page.get_pixmap(dpi=130).tobytes("png") for page in list(doc)[:max_pages]]


def valid_risk_features(features: dict[str, Any]) -> bool:
    try:
        return all(not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value))
                   for value in features.values())
    except (OverflowError, TypeError, ValueError):
        return False


def finish_analysis(principal: Principal, endpoint: str, text: str, result: dict[str, Any], file_sha: str | None = None) -> None:
    """Persist (if enabled) and audit. Audit holds hashes and structured outcomes only - it is not a copy of the record."""
    case_id = uuid.uuid4().hex   # server-generated: a client-chosen X-Request-ID must never address stored data
    stored = cases.save(case_id, principal.actor, result)
    result["case_id"] = case_id if stored else None
    audit.record("analysis", principal.actor, {"case_stored": bool(stored), "guardrail_flags": len(result["guardrails"]["input_flags"]),
        "news2": result["scores"]["news2"]["score"],
        "endpoint": endpoint, "input_sha256": audit.sha256(text), "input_chars": len(text), "file_sha256": file_sha,
        "modality": result.get("input_modality"), "urgent": result["urgent_attention"], "urgent_reasons": len(result.get("urgent_reasons", [])),
        "conditions": [c["condition"] for c in result["possible_conditions"]],
        "risks": {r["key"]: {"level": r["level"], "probability": r["probability"], "reliability": r.get("reliability")} for r in result["risks"] if r.get("available")},
        "evidence_ids": [e["id"] for e in result["evidence"]], "llm_used": result["llm_used"], "llm_errors": len(result.get("llm_errors", [])),
        "phi_redacted": result["privacy"]["phi_redacted"], "provenance": result["provenance"]})


# ---------------------------------------------------------------- routes
router = APIRouter()


@router.get("/health", tags=["operations"])
def health() -> dict[str, Any]:
    """Liveness plus a capability summary. Does not require authentication."""
    return {"status": "ok", "service": "clinical-decision-support", "version": agent.VERSION, "llm_enabled": bool(os.getenv("OPENAI_API_KEY")),
            "vector_store": rag.INDEX.backend, "embeddings": rag.INDEX.embedder, "pubmed_live": rag.pubmed_enabled(),
            "evidence_documents": len(rag.INDEX.docs), "models": {k: v["available"] for k, v in ml.model_info().items()},
            "agent": "langchain-lcel: understand -> evidence -> recommend", "auth": auth_mode(),
            "audit_log": audit.enabled(), "phi_redaction": True, "case_store": cases.enabled(),
            "clinical_scores": ["NEWS2", "qSOFA", "eGFR (CKD-EPI 2021)"], "rate_limit_per_minute": int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))}


@router.get("/ready", tags=["operations"])
def ready() -> JSONResponse:
    """Readiness: evidence index built and both risk models loaded (503 otherwise)."""
    checks = {"evidence_index": bool(rag.INDEX.docs), **{f"model_{k}": v["available"] for k, v in ml.model_info().items()}}
    return JSONResponse({"ready": all(checks.values()), "checks": checks}, status_code=200 if all(checks.values()) else 503)


@router.get("/models", tags=["models"])
def models() -> dict[str, Any]:
    """Model cards: intended use, population, limitations, version, training-data hash and holdout metrics."""
    return ml.model_info()


@router.get("/evidence", tags=["evidence"])
def evidence_catalog() -> list[dict[str, Any]]:
    return rag.INDEX.docs


@router.post("/analyze", tags=["clinical"])
async def analyze(request: AnalyzeRequest, principal: Principal = Depends(rate_limit)) -> dict[str, Any]:
    if not valid_risk_features(request.risk_features):
        raise HTTPException(status_code=422, detail="risk_features must contain only finite numeric values")
    result = await asyncio.to_thread(agent.run_agent, request.text, request.risk_features, {"input_modality": "text", "request_id": request_id_var.get()})
    await asyncio.to_thread(finish_analysis, principal, "analyze", request.text, result)
    return result


@router.post("/upload", tags=["clinical"])
async def upload(file: UploadFile | None = File(default=None), notes: str = Form(default="", max_length=MAX_TEXT_CHARS), risk_features: str = Form(default="{}"),
                 principal: Principal = Depends(rate_limit)) -> dict[str, Any]:
    """Multimodal intake: a PDF / TXT / image (X-ray, fundus, ECG) and/or typed symptoms, analysed together."""
    if file is None and not notes.strip():
        raise HTTPException(status_code=422, detail="Provide a file and/or symptom notes.")
    try:
        features = json.loads(risk_features or "{}")
        if not isinstance(features, dict) or not valid_risk_features(features):
            raise ValueError("risk_features must be a JSON object of finite numeric values")
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    parts: list[str] = [notes.strip()] if notes.strip() else []
    modality, name, image_note, file_sha = "text", None, None, None
    if file is not None:
        name = Path(file.filename or "upload").name
        declared = file.content_type if file.content_type in ALLOWED else EXT_TYPES.get(Path(name).suffix.lower(), "")
        if declared not in ALLOWED:
            raise HTTPException(status_code=415, detail="Upload a PDF, TXT, PNG, JPEG, or WebP file.")
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File exceeds the 12 MB limit.")
        ctype = sniff(data)
        if ctype is None or (ctype.startswith("image/") != declared.startswith("image/")) or (ctype == "application/pdf") != (declared == "application/pdf"):
            raise HTTPException(status_code=415, detail="File content does not match its type. Upload a genuine PDF, TXT, PNG, JPEG, or WebP file.")
        file_sha = audit.sha256(data)
        try:
            if ctype == "application/pdf":
                with pymupdf.open(stream=data, filetype="pdf") as doc:
                    if doc.page_count > MAX_PDF_PAGES:
                        raise HTTPException(status_code=413, detail=f"PDF has {doc.page_count} pages; the limit is {MAX_PDF_PAGES}.")
                    text = fix_symbol_font("\n".join(page.get_text("text", sort=True) for page in doc))
                modality = "document"
                if not readable(text):
                    # scanned / custom-font PDF: fall back to the vision model on rendered pages
                    if agent.llm_client() is None:
                        if parts:
                            text, image_note = "", "The PDF text could not be read (scanned or unusual fonts) and no OPENAI_API_KEY is set; analysis used the typed notes only."
                        else:
                            raise HTTPException(status_code=422, detail="This PDF has no machine-readable text (scanned or unusual fonts). Add OPENAI_API_KEY to enable page-image reading, or paste the text into the notes box.")
                    else:
                        text, image_note = await image_to_text_or_fallback(await asyncio.to_thread(pdf_pages_as_png, data), "image/png", bool(parts))
                        if text.strip():
                            image_note = "PDF text was not machine-readable, so the first pages were read with the vision model (transcription only)."
            elif ctype == "text/plain":
                text, modality = decode_text(data), "document"
            else:
                modality = "image"
                if agent.llm_client() is None and parts:
                    text, image_note = "", "Image received but not interpreted (no OPENAI_API_KEY); analysis used the typed notes only."
                else:
                    text, image_note = await image_to_text_or_fallback(data, ctype, bool(parts))
                    if text.strip():
                        image_note = "Image content transcribed by the configured vision model (non-diagnostic)."
        except HTTPException:
            raise
        except Exception as exc:
            if type(exc).__module__.startswith("openai"):
                raise HTTPException(status_code=503, detail="The configured image service is unavailable. Add typed notes or try again later.") from exc
            log.warning("Upload processing failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=400, detail=f"Could not read the uploaded file ({type(exc).__name__}). Check file integrity and format.") from exc
        if text.strip():
            parts.append(text)
    combined = "\n\n".join(parts)
    if not combined.strip():
        raise HTTPException(status_code=422, detail="No readable text found.")
    result = await asyncio.to_thread(agent.run_agent, combined, features, {
        "document_name": name, "extracted_text": combined[:MAX_TEXT_CHARS], "input_modality": modality, "image_note": image_note,
        "request_id": request_id_var.get()})
    await asyncio.to_thread(finish_analysis, principal, "upload", combined, result, file_sha)
    return result


@router.post("/chat", tags=["clinical"])
async def chat(request: ChatRequest, principal: Principal = Depends(rate_limit)) -> dict[str, Any]:
    result = await asyncio.to_thread(agent.chat_reply, request.message, request.context, [t.model_dump() for t in request.history])
    await asyncio.to_thread(audit.record, "chat", principal.actor, {"message_sha256": audit.sha256(request.message), "context_sha256": audit.sha256(request.context),
                                           "evidence_ids": [e["id"] for e in result["evidence"]]})
    return {**result, "request_id": request_id_var.get()}


@router.post("/feedback", tags=["clinical"], status_code=201)
def feedback(body: FeedbackRequest, principal: Principal = Depends(rate_limit)) -> dict[str, Any]:
    """Clinician verdict on part of an analysis (human-in-the-loop review), appended to the audit trail."""
    rec = audit.record("clinician_feedback", principal.actor, {"analysis_request_id": body.request_id, "target": body.target,
                                                               "item": phi.redact(body.item), "verdict": body.verdict, "comment": phi.redact(body.comment)})
    METRICS.inc(f"feedback_{body.verdict}")
    return {"status": "recorded", "audit_seq": rec["seq"] if rec else None}


@router.post("/fhir/bundle", tags=["interoperability"])
def fhir_bundle(result: dict[str, Any], principal: Principal = Depends(rate_limit)) -> JSONResponse:
    """Convert an /analyze or /upload response into a FHIR R4 collection Bundle."""
    if not isinstance(result.get("risks"), list) or not isinstance(result.get("possible_conditions"), list):
        raise HTTPException(status_code=422, detail="Body must be an /analyze or /upload response.")
    try:
        bundle = fhir.build_bundle(result, result.get("request_id"))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Malformed analysis result ({type(exc).__name__}).") from exc
    audit.record("fhir_export", principal.actor, {"analysis_request_id": result.get("request_id"), "resources": len(bundle["entry"])})
    return JSONResponse(bundle, media_type="application/fhir+json")


@router.get("/auth/config", tags=["operations"])
def auth_config() -> dict[str, Any]:
    """What the UI needs to sign users in (OIDC authorization-code + PKCE). Contains no secrets."""
    return {"mode": auth_mode(), "oidc": {"issuer": os.getenv("OIDC_ISSUER"), "client_id": os.getenv("OIDC_CLIENT_ID"),
                                          "scope": os.getenv("OIDC_SCOPE", "openid profile email")} if oidc_enabled() else None}


@router.get("/me", tags=["operations"])
def me(principal: Principal = Depends(authenticate)) -> dict[str, Any]:
    return {"actor": principal.actor, "role": principal.role, "name": principal.name}


def _scope(principal: Principal) -> str | None:
    return None if principal.role == "admin" else principal.actor


@router.get("/cases", tags=["cases"])
def list_cases(limit: int = 50, principal: Principal = Depends(rate_limit)) -> dict[str, Any]:
    """Case worklist: your own unexpired cases (admins: all). Index metadata only."""
    if not cases.enabled():
        return {"enabled": False, "cases": []}
    return {"enabled": True, "retention_days": cases.retention_seconds() / 86400, "cases": cases.list_cases(_scope(principal), min(max(limit, 1), 200))}


@router.get("/cases/{case_id}", tags=["cases"])
def get_case(case_id: str, principal: Principal = Depends(rate_limit)) -> dict[str, Any]:
    case = cases.get(case_id, _scope(principal))
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found or expired.")
    audit.record("case_viewed", principal.actor, {"case_id": case_id, "owner_match": case["owner"] == principal.actor})
    return case


@router.delete("/cases/{case_id}", tags=["cases"], status_code=204)
def delete_case(case_id: str, principal: Principal = Depends(rate_limit)) -> None:
    if not cases.delete(case_id, _scope(principal)):
        raise HTTPException(status_code=404, detail="Case not found or expired.")
    audit.record("case_deleted", principal.actor, {"case_id": case_id})


@router.get("/audit", tags=["governance"])
def audit_log(limit: int = 50, event: str | None = None, request_id: str | None = None, _: Principal = Depends(require_admin)) -> dict[str, Any]:
    """Most recent audit records (newest first). Admin only."""
    return {"records": audit.recent(min(max(limit, 1), 500), event, request_id)}


@router.get("/audit/verify", tags=["governance"])
def audit_verify(_: Principal = Depends(require_admin)) -> dict[str, Any]:
    """Recompute the hash chain and report whether the log has been altered. Admin only."""
    return audit.verify()


app.include_router(router, prefix=API_PREFIX)
app.include_router(router, include_in_schema=False)   # legacy unversioned paths


@app.get("/metrics", tags=["operations"], response_class=PlainTextResponse)
def metrics(_: Principal = Depends(require_admin)) -> str:
    """Prometheus exposition format. Admin key required when auth is enabled."""
    return METRICS.render()
