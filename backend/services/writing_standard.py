"""Loupe's writing standard (docs/writing-standard.md) as code: one source, ``shared/writing-standard.json``.

* ``system_prompt(text, kind)`` adds the standard's instruction block to a system prompt. Every request to a model
  goes through it (``test_writing_standard`` lists the request paths and fails on one that bypasses it). Kinds:
  ``prose`` (text a person reads as written: answers, summaries, explanations, report sections), ``data`` (JSON
  whose free-text fields a person reads), ``reading`` (a page or layout reading whose output is values only: the
  prompt is left unchanged so reading accuracy is not moved by wording rules; the call is still recorded).
* ``find_problems(text)`` lists banned words, banned phrases and internal terms in a text (the lint and the post-check).
* ``post_check(text)`` cleans generated text a person reads: drops chatbot boilerplate sentences and makes a few
  safe word swaps, never inside quotes, code or links; everything else it finds is returned as a flag, not changed.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

KINDS = ("prose", "data", "reading")
MARKER = "Writing standard (Loupe):"


def _standard_path() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "shared" / "writing-standard.json"
        if candidate.is_file():
            return candidate
    # A deployed backend tree without the repo root: the copy shipped beside this module.
    return here.with_name("writing-standard.json")


@lru_cache(maxsize=1)
def standard() -> dict:
    return json.loads(_standard_path().read_text(encoding="utf-8"))


def instruction_block(kind: str = "prose") -> str:
    if kind not in KINDS:
        raise ValueError(f"Unknown writing kind {kind!r}; use one of {KINDS}")
    if kind == "reading":
        return ""
    data = standard()
    lines = data["prompt_block"] if kind == "prose" else data["data_block"]
    words = ", ".join(data["prompt_words"])
    body = "\n".join(lines)
    if kind == "prose":
        body += f"\n- Words never to use: {words}."
    return f"{MARKER}\n{body}"


def system_prompt(text: str | None, kind: str = "prose") -> str:
    """``text`` with the standard's block added once (idempotent: a prompt already carrying it is unchanged)."""
    text = text or ""
    block = instruction_block(kind)
    if not block or MARKER in text:
        return text
    return f"{text.rstrip()}\n\n{block}" if text.strip() else block


def reading_prompt(text: str) -> str:
    """A page or layout reading (kind ``reading``): the prompt is sent unchanged. Its answer is values copied from
    the page, checked by schema, so wording rules are kept out of it (changing it would move reading accuracy,
    which is measured by the statement benchmarks). Calling this marks the request as covered by the standard."""
    return text


@dataclass
class Problem:
    kind: str  # banned_word | banned_phrase | internal_term
    match: str
    why: str = ""
    start: int = 0


@lru_cache(maxsize=1)
def _patterns():
    data = standard()
    words = re.compile(r"(?<![\w-])(" + "|".join(re.escape(w) for w in sorted(data["banned_words"], key=len, reverse=True)) + r")(?![\w-])", re.I)
    phrases = [(p, re.compile(r"(?<!\w)" + re.escape(p).replace("'", "['’]") + (r"(?!\w)" if p[-1].isalnum() else ""), re.I))
               for p in data["banned_phrases"]]
    internal = [(re.compile(t["pattern"]), t["why"]) for t in data["internal_terms"]]
    return words, phrases, internal


# Spans never judged or changed: quoted text, code, Markdown link targets and bare links (evidence and citations).
_PROTECTED = re.compile(
    r"\"[^\"\n]{1,2000}\"|“[^”\n]{1,2000}”|`[^`\n]*`|```.*?```|\]\([^)]*\)|\b(?:https?|txn|doc|rec|file)://\S+",
    re.S,
)


def _protected_spans(text: str) -> list[tuple[int, int]]:
    return [m.span() for m in _PROTECTED.finditer(text)]


def _inside(spans, start: int, end: int) -> bool:
    return any(a <= start and end <= b for a, b in spans)


def find_problems(text: str, *, internal_terms: bool = True, skip_protected: bool = True) -> list[Problem]:
    if not text:
        return []
    words, phrases, internal = _patterns()
    spans = _protected_spans(text) if skip_protected else []
    found: list[Problem] = []
    for m in words.finditer(text):
        if not _inside(spans, *m.span()):
            found.append(Problem("banned_word", m.group(0), start=m.start()))
    for phrase, rx in phrases:
        for m in rx.finditer(text):
            if not _inside(spans, *m.span()):
                found.append(Problem("banned_phrase", m.group(0), start=m.start()))
    if internal_terms:
        for rx, why in internal:
            for m in rx.finditer(text):
                if not _inside(spans, *m.span()):
                    found.append(Problem("internal_term", m.group(0), why, m.start()))
    found.sort(key=lambda p: p.start)
    return found


@dataclass
class PostCheck:
    text: str
    changed: list[str] = field(default_factory=list)  # what was rewritten or dropped
    flagged: list[Problem] = field(default_factory=list)  # left as written, for a person to see

    def as_dict(self) -> dict:
        return {"changed": self.changed, "flagged": [{"kind": p.kind, "match": p.match, "why": p.why} for p in self.flagged]}


_SENTENCE = re.compile(r"[^.!?\n]*[.!?]+[ \t]*|[^.!?\n]+$|\n", re.M)


def post_check(text: str | None) -> PostCheck:
    """Clean generated text a person reads. Facts are never touched: numbers, names, quotes, code and links pass
    through unchanged; only boilerplate sentences and the standard's safe word swaps change."""
    if not text:
        return PostCheck(text or "")
    data = standard()
    drops = [d.lower() for d in data["drop_sentences"]]
    out: list[str] = []
    changed: list[str] = []
    for m in _SENTENCE.finditer(text):
        piece = m.group(0)
        low = piece.lower()
        if piece.strip() and not _PROTECTED.search(piece) and not re.search(r"\d", piece) and any(d in low for d in drops):
            changed.append(f"dropped: {piece.strip()}")
            continue
        out.append(piece)
    cleaned = "".join(out)
    for old, new in sorted(data["safe_rewrites"], key=lambda r: len(r[0]), reverse=True):
        rx = re.compile(r"(?<!\w)" + re.escape(old) + r"(?!\w)", re.I)
        spans = _protected_spans(cleaned)
        pieces, last = [], 0
        for m in rx.finditer(cleaned):
            if _inside(spans, *m.span()):
                continue
            repl = new[0].upper() + new[1:] if m.group(0)[0].isupper() else new
            pieces.append(cleaned[last:m.start()])
            pieces.append(repl)
            last = m.end()
            changed.append(f"{m.group(0)} -> {repl}")
        if pieces:
            pieces.append(cleaned[last:])
            cleaned = "".join(pieces)
    if cleaned != text:
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip() if cleaned.strip() != text.strip() else cleaned
    flagged = find_problems(cleaned, internal_terms=False)
    if changed or flagged:
        logger.info("writing standard post-check: %d changed, %d flagged", len(changed), len(flagged))
    return PostCheck(cleaned, changed, flagged)


def clean(text: str | None) -> str:
    """``post_check(text).text``: the cleaned text alone."""
    return post_check(text).text
