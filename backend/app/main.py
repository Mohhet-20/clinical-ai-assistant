"""FastAPI service: /upload, /analyze, /chat (+ /health, /evidence, /models)."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import math
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pymupdf
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

from . import agent, ml, rag  # noqa: E402  (after load_dotenv so env is visible)

logging.basicConfig(level=logging.INFO)
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_TEXT_CHARS = agent.MAX_TEXT_CHARS
EXT_TYPES = {".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/plain", ".png": "image/png",
             ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
ALLOWED = set(EXT_TYPES.values())


@asynccontextmanager
async def lifespan(_: FastAPI):
    await asyncio.to_thread(rag.INDEX.build)   # build FAISS index
    await asyncio.to_thread(ml.model_info)     # load or train the ML models
    yield


app = FastAPI(title="Clarity Clinical Decision Support", version="2.0.0", lifespan=lifespan,
              description="Multimodal clinical assistant: PDF/text/image intake, NLP + LLM extraction, FAISS/PubMed RAG, "
                          "tabular ML risk models and a LangChain agent pipeline.")
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    risk_features: dict[str, float] = Field(default_factory=dict)


class ChatTurn(BaseModel):
    role: str
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    context: str = Field(default="", max_length=MAX_TEXT_CHARS)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


def image_to_text(data: bytes | list[bytes], content_type: str) -> str:
    """Vision-model transcription of one image (or several page images)."""
    client = agent.llm_client()
    if not client:
        raise HTTPException(status_code=503, detail="Image interpretation requires OPENAI_API_KEY (backend/.env). Alternatively add typed notes describing the image.")
    images = data if isinstance(data, list) else [data]
    content: list[dict[str, Any]] = [{"type": "text", "text": "Transcribe all visible text (labs, vitals, medications, history) and describe image modality/visible features for clinician review. Do not diagnose."}]
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
    except Exception:
        if not has_notes:
            raise HTTPException(status_code=503, detail="Image interpretation is unavailable. Add typed notes or try again when the image service is available.")
    return "", "Image interpretation was unavailable; analysis used the typed notes only."


def fix_symbol_font(text: str) -> str:
    """Many lab-system PDFs use a Symbol-style font whose glyphs extract as U+F020..U+F0FF; map them back to ASCII."""
    return "".join(chr(ord(c) - 0xF000) if "\uf020" <= c <= "\uf07e" else c for c in text)


def readable(text: str) -> bool:
    """False for empty text or PDFs whose fonts extract as boxes / private-use glyphs."""
    sample = text.strip()[:5000]
    if not sample:
        return False
    good = sum(1 for c in sample if c.isascii() and (c.isalnum() or c in " \n.,:;/%()-"))
    return good / len(sample) > 0.7


def pdf_pages_as_png(data: bytes, max_pages: int = 4) -> list[bytes]:
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return [page.get_pixmap(dpi=130).tobytes("png") for page in list(doc)[:max_pages]]


def valid_risk_features(features: dict[str, Any]) -> bool:
    try:
        return all(not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value))
                   for value in features.values())
    except (OverflowError, TypeError, ValueError):
        return False


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "clinical-decision-support", "llm_enabled": bool(os.getenv("OPENAI_API_KEY")),
            "vector_store": rag.INDEX.backend, "embeddings": rag.INDEX.embedder, "pubmed_live": rag.pubmed_enabled(),
            "evidence_documents": len(rag.INDEX.docs), "models": {k: v["available"] for k, v in ml.model_info().items()},
            "agent": "langchain-lcel: understand -> evidence -> recommend"}


@app.get("/models")
def models() -> dict[str, Any]:
    return ml.model_info()


@app.get("/evidence")
def evidence_catalog() -> list[dict[str, Any]]:
    return rag.INDEX.docs


@app.post("/analyze")
async def analyze(request: AnalyzeRequest) -> dict[str, Any]:
    if not valid_risk_features(request.risk_features):
        raise HTTPException(status_code=422, detail="risk_features must contain only finite numeric values")
    return await asyncio.to_thread(agent.run_agent, request.text, request.risk_features, {"input_modality": "text"})


@app.post("/upload")
async def upload(file: UploadFile | None = File(default=None), notes: str = Form(default="", max_length=MAX_TEXT_CHARS), risk_features: str = Form(default="{}")) -> dict[str, Any]:
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
    modality, name, image_note = "text", None, None
    if file is not None:
        name = Path(file.filename or "upload").name
        ctype = file.content_type if file.content_type in ALLOWED else EXT_TYPES.get(Path(name).suffix.lower(), "")
        if ctype not in ALLOWED:
            raise HTTPException(status_code=415, detail="Upload a PDF, TXT, PNG, JPEG, or WebP file.")
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File exceeds the 12 MB limit.")
        try:
            if ctype == "application/pdf":
                with pymupdf.open(stream=data, filetype="pdf") as doc:
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
                text, modality = data.decode("utf-8", errors="replace"), "document"
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
            logging.getLogger("clinical.upload").warning("Upload processing failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=400, detail=f"Could not read the uploaded file ({type(exc).__name__}). Check file integrity and format.") from exc
        if text.strip():
            parts.append(text)
    combined = "\n\n".join(parts)
    if not combined.strip():
        raise HTTPException(status_code=422, detail="No readable text found.")
    result = await asyncio.to_thread(agent.run_agent, combined, features, {
        "document_name": name, "extracted_text": combined[:MAX_TEXT_CHARS], "input_modality": modality, "image_note": image_note})
    return result


@app.post("/chat")
async def chat(request: ChatRequest) -> dict[str, Any]:
    return await asyncio.to_thread(agent.chat_reply, request.message, request.context, [t.model_dump() for t in request.history])
