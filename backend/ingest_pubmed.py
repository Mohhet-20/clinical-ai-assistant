"""Download PubMed abstracts for a topic list into data/pubmed.json so they are
embedded into the FAISS index at start-up (works offline afterwards).

    python ingest_pubmed.py                       # default clinical topics
    python ingest_pubmed.py "sepsis guideline" 5   # custom topic, 5 abstracts
"""
import json
import sys
from pathlib import Path

from app.rag import pubmed_search

TOPICS = ["type 2 diabetes diagnosis screening guideline", "hypertension management guideline",
          "acute coronary syndrome chest pain evaluation", "cardiovascular risk prediction machine learning",
          "heart failure diagnosis", "asthma COPD diagnosis"]

if __name__ == "__main__":
    topics = [sys.argv[1]] if len(sys.argv) > 1 else TOPICS
    per = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    out = Path(__file__).parent / "data" / "pubmed.json"
    docs = {}
    if out.exists():
        docs = {d["id"]: d for d in json.loads(out.read_text(encoding="utf-8"))}
    for t in topics:
        got = pubmed_search(f"({t}) AND hasabstract", retmax=per)
        print(f"{t}: {len(got)} abstracts")
        docs.update({d["id"]: d for d in got})
    out.write_text(json.dumps(list(docs.values()), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(docs)} abstracts to {out}")
