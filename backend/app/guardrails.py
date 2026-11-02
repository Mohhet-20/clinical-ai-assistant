"""Input and output guardrails around the optional LLM.

Input:  prompt-injection screening. A record containing instructions aimed at
        the model is still analysed by the local pipeline, but the LLM is
        skipped for that request, which is the safe default.
Output: every generated summary/chat reply is checked before it is shown:
        - citations must reference evidence that was actually supplied
          (unknown ``[id]`` tokens are stripped and counted);
        - prescribing / dosing directives cause the text to be rejected in
          favour of the deterministic rules-mode output;
        - uncited text is flagged when evidence was available."""
from __future__ import annotations

import re
from typing import Any

_INJECTION = re.compile(
    r"(?:ignore|disregard|forget|override)\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above|earlier|system)\s+(?:instructions?|prompts?|rules?|messages?)"
    r"|\byou are now\b|\bact as (?:an?|the) (?!clinician|doctor)\w+|\bsystem prompt\b|\bdeveloper mode\b|\bjailbreak\b"
    r"|<\s*/?\s*(?:system|assistant|instructions?)\s*>|\bnew instructions?\s*:|\breveal (?:your|the) (?:prompt|instructions)", re.I)
_DIRECTIVE = re.compile(
    r"\b(?:prescribe(?!d|r|s)|start (?:the patient|him|her|them) on|administer|give (?:the patient )?\d+\s*(?:mg|mcg|units?|ml)|"
    r"increase (?:the )?dose (?:to|by)|titrate (?:up )?to|take \d+\s*(?:mg|mcg|units?|tablets?)|discontinue (?:all )?(?:his|her|their) )", re.I)
_CITATION = re.compile(r"\[([a-z0-9][a-z0-9._-]{1,80})\]", re.I)


def screen_input(text: str) -> list[str]:
    hits = {m.group(0).strip().lower()[:60] for m in _INJECTION.finditer(text)}
    return [f"Possible prompt injection: '{h}'" for h in sorted(hits)]


def check_output(text: str, valid_ids: set[str]) -> tuple[str | None, dict[str, Any]]:
    """Return (text or None if rejected, report)."""
    cited = [m.group(1) for m in _CITATION.finditer(text)]
    unknown = sorted({c for c in cited if c not in valid_ids})
    cleaned = _CITATION.sub(lambda m: m.group(0) if m.group(1) in valid_ids else "", text) if unknown else text
    directives = sorted({m.group(0).lower() for m in _DIRECTIVE.finditer(cleaned)})
    report: dict[str, Any] = {"citations": len(cited) - len([c for c in cited if c in unknown]), "unknown_citations_removed": unknown,
                              "directive_language": directives, "uncited": bool(valid_ids) and not (set(cited) - set(unknown)), "rejected": bool(directives)}
    return (None if directives else re.sub(r"[ \t]{2,}", " ", cleaned).strip()), report
