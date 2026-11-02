"""PHI de-identification applied to every piece of text before it leaves the
service (LLM prompts, embeddings, PubMed queries).

Pattern-based redaction of common HIPAA Safe Harbor identifiers: names after
explicit labels/honorifics or starting with a common given name, MRN / account / SSN numbers, phone, email, URLs,
IP addresses, street addresses, ZIP codes and calendar dates. Clinical values
(vitals, labs, ages under 90) are preserved so downstream reasoning still
works. Pattern matching cannot guarantee complete de-identification; the
local pipeline always runs on the original text and nothing is persisted."""
from __future__ import annotations

import re
from typing import Any

_MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
# Capitalised words separated by single spaces (so table columns and all-caps labels like "MRN" are not swallowed).
_HONORIFIC = r"(?:Mr|Mrs|Ms|Miss|Dr|Prof|Sr|Smt|Shri)\b"
_WORD = rf"(?!{_HONORIFIC})[A-Z](?:[a-z]|'[A-Z])[a-zA-Z'\-]*"
_NAME = rf"{_WORD}(?: [A-Z]\.(?= ))?(?: {_WORD}){{0,2}}"
# Common given names (multi-regional) catch unlabelled mentions like "Is Jane Doe diabetic?". Words that are
# also ordinary English (May, Will, Grace, Hope, Mark, Faith, Joy...) are deliberately excluded.
_GIVEN = ("James John Robert Michael William David Richard Joseph Thomas Charles Christopher Daniel Matthew Anthony Donald Steven Paul "
          "Andrew Joshua Kenneth Kevin Brian George Timothy Ronald Edward Jason Jeffrey Ryan Jacob Gary Nicholas Eric Jonathan Stephen "
          "Larry Justin Scott Brandon Benjamin Samuel Gregory Alexander Patrick Jack Dennis Jerry Tyler Aaron Henry Douglas Peter Adam "
          "Nathan Zachary Walter Kyle Harold Carl Jeremy Keith Roger Gerald Ethan Arthur Terry Christian Sean Lawrence Austin Joe Noah "
          "Mary Patricia Jennifer Linda Elizabeth Barbara Susan Jessica Sarah Karen Lisa Nancy Betty Sandra Margaret Ashley Kimberly "
          "Emily Donna Michelle Carol Amanda Melissa Deborah Stephanie Rebecca Sharon Laura Cynthia Amy Kathleen Angela Shirley Brenda "
          "Emma Anna Pamela Nicole Samantha Katherine Christine Helen Debra Rachel Carolyn Janet Maria Catherine Heather Diane Olivia "
          "Julie Joyce Victoria Ruth Virginia Lauren Kelly Christina Joan Evelyn Judith Andrea Hannah Megan Cheryl Jacqueline Martha "
          "Madison Teresa Gloria Sara Janice Ann Kathryn Abigail Sophia Frances Jean Alice Judy Isabella Julia Denise Amber Doris "
          "Marilyn Danielle Beverly Theresa Diana Natalie Brittany Charlotte Marie Kayla Alexis Lori Jane Jose Juan Carlos Luis Miguel "
          "Jorge Pedro Alejandro Ana Sofia Lucia Carmen Rosa Elena Ahmed Mohammed Muhammad Mohamed Ali Omar Hassan Hussein Fatima "
          "Aisha Mariam Yusuf Ibrahim Rahul Priya Amit Anil Sunil Ravi Rajesh Ramesh Suresh Mahesh Vijay Sanjay Deepak Anjali Pooja "
          "Neha Kavita Sunita Lakshmi Arjun Mohit Rohit Ajay Arun Kiran Meena Geeta Sita Krishna Venkat Srinivas Ananya Aditya Vikram "
          "Manoj Prakash Sandeep Swati Divya Shreya Rakesh Ashok Harish Naveen Praveen Ganesh Murali Bala Balaji Karthik Gopal Wei "
          "Hiroshi Yuki Kenji Akira Olga Ivan Dmitri Sergei Natasha Hans Klaus Pierre Jean-Pierre Giovanni Marco Francesca Giulia")
_GIVEN_RE = rf"\b(?:{'|'.join(sorted(set(_GIVEN.split()), key=len, reverse=True))})\b(?: [A-Z]\.(?= ))?(?: {_WORD}){{0,2}}"

# (category, pattern, group to replace or 0 for whole match). Order matters: specific before generic.
PATTERNS: list[tuple[str, re.Pattern[str], int]] = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), 0),
    ("URL", re.compile(r"\bhttps?://\S+|\bwww\.\S+", re.I), 0),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), 0),
    ("ID", re.compile(r"\b(?:mrn|medical record(?: number| no\.?)?|patient id|account(?: no\.?| number)?|acct|insurance id|member id|uhid|reg(?:istration)? no\.?|ip no\.?|op no\.?)\s*[:#]?\s*([A-Z0-9][A-Z0-9\-/]{3,})", re.I), 1),
    ("PHONE", re.compile(r"(?<![\w/.])(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]\d{3}[\s.-]\d{4}(?!\w)"), 0),
    ("IP", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), 0),
    ("DATE", re.compile(rf"\b(?:\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}}|\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}}\s+{_MONTHS},?\s+\d{{4}}|{_MONTHS}\s+\d{{1,2}},?\s+\d{{4}})\b", re.I), 0),
    ("ADDRESS", re.compile(r"\b\d{1,5}\s+(?:[A-Z][a-z]+\s+){1,3}(?:street|st|avenue|ave|road|rd|boulevard|blvd|lane|ln|drive|dr|court|ct|way|place|pl)\b\.?", re.I), 0),
    ("ZIP", re.compile(r"(?<=[A-Z]{2}\s)\d{5}(?:-\d{4})?\b"), 0),
    ("NAME", re.compile(rf"\b(?i:patient(?: name)?|name|pt|mr|mrs|ms|miss|dr|prof|smt|shri|doctor|physician|referred by|attending)\.?\s*[:\-]?\s+({_NAME})"), 1),
    ("NAME", re.compile(_GIVEN_RE), 0),
    ("AGE90", re.compile(r"\b(9\d|1[01]\d)(?=[\s-]*(?:years?|yrs?|y/?o)\b)", re.I), 1),
]


def deidentify(text: str) -> tuple[str, dict[str, int]]:
    """Return (redacted text, counts per category). Never raises."""
    counts: dict[str, int] = {}
    for category, pattern, group in PATTERNS:
        def repl(m: re.Match[str], category: str = category, group: int = group) -> str:
            counts[category] = counts.get(category, 0) + 1
            if group == 0:
                return f"[{category}]"
            start, end = m.start(group) - m.start(), m.end(group) - m.start()
            whole = m.group(0)
            # ages 90+ are aggregated (Safe Harbor) rather than removed
            token = "90+" if category == "AGE90" else f"[{category}]"
            return whole[:start] + token + whole[end:]
        text = pattern.sub(repl, text)
    return text, counts


def find(text: str) -> list[tuple[int, int, str]]:
    """(start, end, category) of each identifier in the *original* text, for highlighting. Earlier patterns win overlaps."""
    hits: list[tuple[int, int, str]] = []
    for category, pattern, group in PATTERNS:
        for m in pattern.finditer(text):
            s, e = (m.start(group), m.end(group)) if group else (m.start(), m.end())
            if not any(s < he and hs < e for hs, he, _ in hits):
                hits.append((s, e, "AGE 90+" if category == "AGE90" else category))
    return sorted(hits)


def redact(text: str) -> str:
    return deidentify(text)[0]


def report(counts: dict[str, int]) -> dict[str, Any]:
    return {"phi_redacted": sum(counts.values()), "categories": sorted(counts),
            "note": "Identifiers were redacted before any external LLM or PubMed call." if counts else
                    "No identifiers detected by pattern screening; do not submit identifiable data."}
