"""Retrieval layer: FAISS vector index over curated guidelines (+ cached PubMed
abstracts) and optional live PubMed search via NCBI E-utilities.

Embeddings: OpenAI `text-embedding-3-small` when OPENAI_API_KEY is set,
otherwise a local TF-IDF vectoriser, so the whole pipeline runs offline."""
from __future__ import annotations

import json
import logging
import os
import threading
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

try:  # FAISS is the intended vector store; fall back to numpy if it is not installable.
    import faiss  # type: ignore
except Exception:  # pragma: no cover
    faiss = None

log = logging.getLogger("clinical.rag")
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _normalize(m: np.ndarray) -> np.ndarray:
    m = np.ascontiguousarray(m, dtype="float32")
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return m / norms


class EvidenceIndex:
    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []
        self.backend = "faiss" if faiss is not None else "numpy"
        self.embedder = "tfidf"
        self._vec: TfidfVectorizer | None = None
        self._index: Any = None
        self._matrix: np.ndarray | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------ build
    def load_documents(self) -> list[dict[str, Any]]:
        docs = json.loads((DATA_DIR / "evidence.json").read_text(encoding="utf-8"))
        cache = DATA_DIR / "pubmed.json"
        if cache.exists():
            try:
                docs += json.loads(cache.read_text(encoding="utf-8"))
            except Exception:
                log.warning("Ignoring unreadable pubmed.json")
        for d in docs:
            d.setdefault("kind", "guideline")
        return docs

    def _openai_embed(self, texts: list[str]) -> np.ndarray:
        from openai import OpenAI
        resp = OpenAI().embeddings.create(model=os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small"), input=texts)
        return np.array([d.embedding for d in resp.data], dtype="float32")

    def build(self) -> None:
        with self._lock:
            self.docs = self.load_documents()
            texts = [f"{d['title']}. {d['text']}" for d in self.docs]
            matrix = None
            if os.getenv("OPENAI_API_KEY") and os.getenv("EMBEDDINGS", "auto") != "tfidf":
                try:
                    matrix = self._openai_embed(texts)
                    self.embedder, self._vec = "openai", None
                except Exception as exc:
                    log.warning("OpenAI embeddings unavailable (%s); using TF-IDF vectors", type(exc).__name__)
            if matrix is None:
                self._vec = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", sublinear_tf=True)
                matrix = self._vec.fit_transform(texts).toarray()
                self.embedder = "tfidf"
            self._matrix = _normalize(matrix)
            if faiss is not None:
                self._index = faiss.IndexFlatIP(self._matrix.shape[1])
                self._index.add(self._matrix)

    # ------------------------------------------------------------ search
    def _embed_query(self, text: str) -> np.ndarray:
        if self.embedder == "openai":
            try:
                return _normalize(self._openai_embed([text]))
            except Exception as exc:
                log.warning("Query embedding failed (%s); returning no semantic match", type(exc).__name__)
                return np.zeros((1, self._matrix.shape[1]), dtype="float32")  # type: ignore[union-attr]
        assert self._vec is not None
        return _normalize(self._vec.transform([text]).toarray())

    def search(self, text: str, k: int = 4, min_score: float = 0.03) -> list[dict[str, Any]]:
        if not self.docs:
            self.build()
        q = self._embed_query(text[:8000])
        k = min(k, len(self.docs))
        if self._index is not None:
            scores, ids = self._index.search(q, k)
            pairs = list(zip(ids[0].tolist(), scores[0].tolist()))
        else:
            s = (self._matrix @ q[0])  # type: ignore[operator]
            idx = np.argsort(-s)[:k]
            pairs = [(int(i), float(s[i])) for i in idx]
        floor = min_score if self.embedder == "tfidf" else 0.2
        return [{**self.docs[i], "relevance": round(float(sc), 3)} for i, sc in pairs if i >= 0 and sc > floor]


INDEX = EvidenceIndex()


# ---------------------------------------------------------------- PubMed
_cache: dict[str, list[dict[str, Any]]] = {}


def pubmed_enabled() -> bool:
    return os.getenv("PUBMED_LIVE", "true").lower() not in ("0", "false", "no")


def _get(url: str, timeout: float = 6.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "clarity-clinical-assistant/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed https host
        return r.read()


def parse_pubmed_xml(xml_bytes: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_bytes)
    out = []
    for art in root.iter("PubmedArticle"):
        pmid = (art.findtext(".//MedlineCitation/PMID") or "").strip()
        title = "".join(art.find(".//ArticleTitle").itertext()).strip() if art.find(".//ArticleTitle") is not None else ""
        abstract = " ".join("".join(n.itertext()).strip() for n in art.findall(".//Abstract/AbstractText")).strip()
        journal = art.findtext(".//Journal/Title") or "PubMed"
        year = art.findtext(".//JournalIssue/PubDate/Year") or (art.findtext(".//JournalIssue/PubDate/MedlineDate") or "")[:4]
        if pmid and title and abstract:
            out.append({"id": f"pmid-{pmid}", "title": title, "source": f"{journal} ({year}) · PubMed PMID {pmid}",
                        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", "text": abstract[:1500], "kind": "pubmed", "pmid": pmid})
    return out


def pubmed_search(query: str, retmax: int = 3) -> list[dict[str, Any]]:
    """Live PubMed lookup; never raises (returns [] when offline)."""
    if not pubmed_enabled() or not query.strip():
        return []
    if query in _cache:
        return _cache[query]
    params = {"db": "pubmed", "retmode": "json", "retmax": str(retmax), "sort": "relevance", "term": query}
    key = os.getenv("NCBI_API_KEY")
    if key:
        params["api_key"] = key
    try:
        ids = json.loads(_get(f"{EUTILS}/esearch.fcgi?{urllib.parse.urlencode(params)}"))["esearchresult"].get("idlist", [])
        if not ids:
            _cache[query] = []
            return []
        fetch = {"db": "pubmed", "retmode": "xml", "rettype": "abstract", "id": ",".join(ids)}
        if key:
            fetch["api_key"] = key
        docs = parse_pubmed_xml(_get(f"{EUTILS}/efetch.fcgi?{urllib.parse.urlencode(fetch)}"))
        _cache[query] = docs
        return docs
    except Exception as exc:
        log.info("PubMed unavailable (%s); continuing with indexed evidence", type(exc).__name__)
        return []


def retrieve(text: str, pubmed_query: str = "", k: int = 4, pubmed_k: int = 3) -> list[dict[str, Any]]:
    results = INDEX.search(text, k=k)
    seen = {r["id"] for r in results}
    for doc in pubmed_search(pubmed_query, retmax=pubmed_k) if pubmed_query else []:
        if doc["id"] not in seen:
            results.append({**doc, "relevance": None})
    return results
