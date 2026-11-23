"""An answer that says none of a kind was found, when a read in the same run returned that kind.

Demo P4 (22 Nov 2026, followups m112223403612703): phone_messages with kinds=email between the two people returned
1 email (rec://819b84ac, the price list); the answer, written from 948k prompt tokens, said "No emails appear in those
windows" and never cited it. Before the answer is shown, each sentence saying "no emails", "no calls" or "no messages"
is compared with the run's own phone reads: a record of that kind the run read and the answer does not cite sends the
writer back once with the record in view. A contradiction left after that is named under the answer's checks.

Decision: code only (no model call). Only records of a read that asked for that kind by name, and that the answer does
not cite, count: an answer that quotes the email and says "no emails on 12 May" is left alone. Measured on 186 live
runs with phone reads (30 days to 22 Nov 2026): 23 say none of a kind, 1 contradicts its own read (this one). Reverse
if a measured answer is made worse by the extra step.
"""
from __future__ import annotations

import json
import re
from typing import Any

# the words an answer uses for a kind, as phone records name it (services.phone.filters.Kind)
_KIND_WORDS = {"email": r"e-?mails?", "call": r"(?:phone\s+)?calls?", "message": r"(?:text\s+)?messages?|text(?=\s+(?:to|from|between)\b)",
               "voicemail": r"voicemails?"}
_WORD_KIND = [(kind, re.compile(r"^(?:%s)$" % words, re.I)) for kind, words in _KIND_WORDS.items()]
_ALL = "|".join("(?:%s)" % w for w in _KIND_WORDS.values())
# "No emails appear", "no calls or messages", "there were no e-mails", "none of the emails", "zero calls"
_ABSENCE = re.compile(r"\b(?:no|zero|none\s+of\s+(?:the|their|these|those)|not\s+(?:a\s+single|any))\s+"
                      r"(?:(?:other|further|more|direct|such|recorded|phone)\s+)?"
                      r"((?:%s)(?:\s*(?:,|or|and|nor)\s*(?:%s))*)\b"
                      # "no message text", "no call log": a part of a record, not the record
                      r"(?![-\w])(?!\s+(?:text|body|bodies|content|thread|threads|log|logs|history|record|records|time|"
                      r"date|sender|subject|id|ids|window|windows|states|contains|mentions|matching|says|names|"
                      r"refers|includes|quotes|uses)\b)" % (_ALL, _ALL), re.I)
# the answer's own check sections (source check, figures, lint) quote sentences and sources: not the answer's claims
_CHECK_HEADINGS = ("**Source check**", "**Figures to check", "**Checks this answer did not pass**")
_SENTENCE = re.compile(r"[^.!?\n]+[.!?]?")
_REC = re.compile(r"rec://([0-9a-f-]{36})", re.I)
MAX_SHOWN = 5


def _kinds(words: str) -> set[str]:
    out = set()
    for part in re.split(r"\s*(?:,|\bor\b|\band\b|\bnor\b)\s*", words.strip(), flags=re.I):
        for kind, rx in _WORD_KIND:
            if part and rx.match(part.strip()):
                out.add(kind)
    return out


def absences(answer: str) -> list[tuple[str, set[str]]]:
    """(sentence, kinds) for each sentence saying none of a kind of phone record was found."""
    out = []
    text = answer or ""
    cut = min([i for i in (text.find(h) for h in _CHECK_HEADINGS) if i >= 0] or [len(text)])
    for m in _SENTENCE.finditer(text[:cut]):
        sentence = m.group(0).strip()
        kinds = set()
        for a in _ABSENCE.finditer(sentence):
            kinds |= _kinds(a.group(1))
        if kinds:
            out.append((sentence, kinds))
    return out


def read_records(trace: list[dict]) -> list[dict[str, Any]]:
    """Phone records the run's reads returned: kind, record id, time, people, subject or body, and the call."""
    out, seen = [], set()
    for t in trace or []:
        preview = t.get("result_preview")
        if t.get("status") != "success" or not str(t.get("name") or "").startswith("phone_") \
                or not isinstance(preview, dict):
            continue
        arguments = t.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except ValueError:
                arguments = {}
        asked = set(arguments.get("kinds") or [])
        for item in preview.get("items") or []:
            if not isinstance(item, dict) or not item.get("record_uid") or item.get("kind") not in _KIND_WORDS:
                continue
            if item["kind"] not in asked:
                # only a read that asked for this kind by name: a read of everyone's messages holds records of other
                # people (a contact named "Mateo" on a number the case does not tie to Mateo Ruiz, demo 0d8a1723)
                continue
            uid = str(item["record_uid"]).lower()
            if uid in seen:
                continue
            seen.add(uid)
            out.append({"kind": item["kind"], "record_uid": uid, "time": item.get("time"), "from": item.get("from"),
                        "to": item.get("to") or [], "text": item.get("subject") or item.get("body") or item.get("call"),
                        "tool": t.get("name"), "arguments": arguments})
    return out


def contradictions(answer: str, trace: list[dict]) -> list[dict[str, Any]]:
    """Each sentence saying none of a kind, with the records of that kind the run read and the answer does not cite."""
    cited = {m.group(1).lower() for m in _REC.finditer(answer or "")}
    records = [r for r in read_records(trace) if r["record_uid"] not in cited]
    out = []
    for sentence, kinds in absences(answer):
        found = [r for r in records if r["kind"] in kinds]
        if found:
            out.append({"sentence": sentence, "kinds": sorted(kinds), "records": found})
    return out


_CITE = re.compile(r"\]\(\s*<?((?:rec|txn|doc|entity)://[^)>\s]+)")


def keeps_citations(old: str, new: str) -> bool:
    """A rewrite is taken only when it keeps the citations of the answer it replaces (it may add some)."""
    before = set(_CITE.findall(old or ""))
    return before <= set(_CITE.findall(new or ""))


def _record_line(r: dict) -> str:
    to = ", ".join(str(x) for x in r["to"][:3])
    text = re.sub(r"\s+", " ", str(r["text"] or "")).strip()
    text = text if len(text) <= 160 else text[:157].rstrip() + "..."
    return "rec://%s: %s, %s, %s to %s%s (read by %s)" % (
        r["record_uid"], r["kind"], r["time"] or "no time", r["from"] or "unknown sender", to or "unknown",
        ': "%s"' % text if text else "", r["tool"])


def repair_request(found: list[dict]) -> str:
    rows = []
    for f in found[:5]:
        rows.append("- The answer says: \"%s\" This run read %d %s record%s the answer does not cite:\n%s" % (
            f["sentence"][:300], len(f["records"]), " or ".join(f["kinds"]), "" if len(f["records"]) == 1 else "s",
            "\n".join("  " + _record_line(r) for r in f["records"][:MAX_SHOWN])
            + ("\n  and %d more." % (len(f["records"]) - MAX_SHOWN) if len(f["records"]) > MAX_SHOWN else "")))
    return ("Automated check, not a new instruction from the person. The answer says none of a kind of record was "
            "found, but this run read such records:\n%s\nRewrite the answer in full. Where a record belongs to what "
            "the sentence is about (the same people and window), quote and cite it and correct the sentence. Where "
            "the sentence is about other people or another window, keep it and name that window or those people. "
            "Keep every other citation and fact." % "\n".join(rows))


def check_lines(found: list[dict]) -> list[str]:
    """What the answer's checks say when the rewrite still leaves a contradiction."""
    return ["The answer says \"%s\", but this run read %s it does not cite: %s." % (
        f["sentence"][:200], " or ".join(f["kinds"]) + " records",
        ", ".join("rec://" + r["record_uid"] for r in f["records"][:MAX_SHOWN])) for f in found]
