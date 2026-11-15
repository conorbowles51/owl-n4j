"""Check the claims an earlier ingestion left unreviewed (lx-citeproof D), through the ingestion claim check itself.

Until 15 Nov 2026 the check stopped at 250 claims a file; the rest were stored ``unreviewed`` and kept out of the graph.
This reads them back from the claim ledger, rebuilds what the check is given at ingestion (the statement, the quote and
a window of the file's text around it, the same window ``extract_entities`` builds), and runs
``verify_claims.check_candidates``: same prompt, same model, same batches, the case's AI spending limit read before
each round, cost recorded to the case.

Cheapest first: cases with the fewest unreviewed claims, and inside a case the files with the fewest, so the most cases
and files are finished for the money. A stored claim keeps what it said before: its earlier status and reason move to
``object_value.previous_verification`` and the new verdict is written beside them. Nothing is deleted.
"""
from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text

from app.pipeline.extract_entities import _build_verification_context
from app.pipeline.verify_claims import check_candidates
from app.services.cost_tracking import ingestion_cost_context

logger = logging.getLogger(__name__)

STATUS = {"SUPPORTED": "verified", "REJECTED": "rejected", "UNCERTAIN": "uncertain"}
SYSTEM_DESCRIPTION = "Claim check of claims left unreviewed by an earlier ingestion (system run)"


@dataclass
class FileOutcome:
    evidence_file_id: str
    claims: int
    checked: int = 0
    verified: int = 0
    rejected: int = 0
    uncertain: int = 0
    left: int = 0
    stop_reason: str | None = None


@dataclass
class CaseOutcome:
    case_id: str
    before: int
    files: list[FileOutcome] = field(default_factory=list)

    @property
    def checked(self) -> int:
        return sum(f.checked for f in self.files)


async def unreviewed_counts(db) -> list[dict[str, Any]]:
    """Unreviewed claims per case and file, cheapest first."""
    rows = (await db.execute(text(
        "SELECT case_id::text AS case_id, evidence_file_id::text AS evidence_file_id, count(*) AS n "
        "FROM evidence_claims WHERE status = 'unreviewed' GROUP BY 1, 2"))).mappings().all()
    cases: dict[str, dict[str, Any]] = {}
    for row in rows:
        entry = cases.setdefault(row["case_id"], {"case_id": row["case_id"], "unreviewed": 0, "files": []})
        entry["unreviewed"] += int(row["n"])
        entry["files"].append({"evidence_file_id": row["evidence_file_id"], "unreviewed": int(row["n"])})
    for entry in cases.values():
        entry["files"].sort(key=lambda f: (f["unreviewed"], f["evidence_file_id"]))
    return sorted(cases.values(), key=lambda c: (c["unreviewed"], c["case_id"]))


def _statement(row: dict[str, Any], names: dict[str, str]) -> str | None:
    value = row["object_value"] or {}
    if row["claim_type"] == "entity_fact":
        return str(value.get("text") or "").strip() or None
    if row["claim_type"] == "relationship":
        source = names.get(row["subject_id"], row["subject_id"])
        target = names.get(str(value.get("target_entity_id") or ""), str(value.get("target_entity_id") or ""))
        return f"{source} {row['predicate']} {target}: {value.get('detail') or ''}".strip()
    return None


def _context(document: str | None, quote: str, location: dict[str, Any]) -> str:
    """The window ingestion gives the check: the quote at its stored offsets when the text still holds it there,
    else where the text holds it now, else the quote alone."""
    if not document:
        return quote
    start, end = location.get("quote_start_char"), location.get("quote_end_char")
    if isinstance(start, int) and isinstance(end, int) and document[start:end] == quote:
        return _build_verification_context(document, start, end)
    found = document.find(quote) if quote else -1
    if found >= 0:
        return _build_verification_context(document, found, found + len(quote))
    return quote


async def _file_candidates(db, case_id: str, evidence_file_id: str) -> list[dict[str, Any]]:
    rows = (await db.execute(text(
        "SELECT id, claim_type, subject_id, predicate, object_value, quote, source_location, status "
        "FROM evidence_claims WHERE case_id = CAST(:c AS uuid) AND evidence_file_id = CAST(:f AS uuid)"),
        {"c": case_id, "f": evidence_file_id})).mappings().all()
    names = {r["subject_id"]: str((r["object_value"] or {}).get("name") or (r["object_value"] or {}).get("entity_name")
                                  or "") for r in rows if r["claim_type"] in ("entity_mention", "entity_fact")}
    names = {k: v for k, v in names.items() if v}
    document = await db.scalar(text("SELECT content FROM evidence_document_texts WHERE evidence_file_id = "
                                    "CAST(:f AS uuid)"), {"f": evidence_file_id})
    candidates = []
    for row in rows:
        if row["status"] != "unreviewed":
            continue
        statement = _statement(row, names)
        if not statement or not row["quote"]:
            continue
        value = row["object_value"] or {}
        candidate = {"candidate_id": row["id"], "claim_type": row["claim_type"], "statement": statement,
                     "evidence_quote": row["quote"],
                     "evidence_context": _context(document, row["quote"], row["source_location"] or {}),
                     "_row": row}
        if row["claim_type"] == "entity_fact":
            candidate["entity_name"] = names.get(row["subject_id"], value.get("entity_name") or "")
            candidate["importance"] = int(value.get("importance", 3) or 3)
        candidates.append(candidate)
    # the order ingestion uses: relationships, then higher-importance facts
    return sorted(candidates, key=lambda c: (0 if c["claim_type"] == "relationship" else 1,
                                             -int(c.get("importance", 0))))


async def _write(db, candidate: dict[str, Any], status: str, reason: str) -> None:
    row = candidate["_row"]
    value = dict(row["object_value"] or {})
    value["previous_verification"] = {"status": row["status"], "reason": value.get("verification_reason")}
    value["verification_reason"] = reason
    value["verification_run"] = SYSTEM_DESCRIPTION
    await db.execute(text("UPDATE evidence_claims SET status = :s, object_value = CAST(:v AS jsonb) WHERE id = :i "
                          "AND status = 'unreviewed'"),
                     {"s": status, "v": __import__("json").dumps(value, ensure_ascii=False, default=str),
                      "i": row["id"]})


async def check_case(session_factory, case_id: str, *, apply: bool, max_claims: int | None = None) -> CaseOutcome:
    """Check the case's unreviewed claims, cheapest file first. ``apply`` False: count only, no model call.
    ``max_claims``: stop after about this many claims (whole batches), the rest stay unreviewed and are counted."""
    async with session_factory() as db:
        counts = [c for c in await unreviewed_counts(db) if c["case_id"] == case_id]
    if not counts:
        return CaseOutcome(case_id, 0)
    outcome = CaseOutcome(case_id, counts[0]["unreviewed"])
    budget = max_claims
    for entry in counts[0]["files"]:
        file_id = entry["evidence_file_id"]
        async with session_factory() as db:
            candidates = await _file_candidates(db, case_id, file_id)
        result = FileOutcome(file_id, len(candidates))
        outcome.files.append(result)
        if not apply:
            result.left = len(candidates)
            continue
        if budget is not None and budget <= 0:
            result.left, result.stop_reason = len(candidates), "Over this run's claim limit."
            continue
        chosen = candidates if budget is None else candidates[:budget]
        async with ingestion_cost_context(case_id=uuid.UUID(case_id), source_evidence_file_id=uuid.UUID(file_id),
                                          description=SYSTEM_DESCRIPTION):
            check = await check_candidates(chosen, case_id=case_id)
        async with session_factory() as db:
            for candidate in check.checked:
                decision, reason = check.decisions.get(
                    candidate["candidate_id"], ("UNCERTAIN", "The verifier omitted a decision for this candidate."))
                status = STATUS.get(decision, "uncertain")
                await _write(db, candidate, status, reason)
                result.checked += 1
                setattr(result, status, getattr(result, status) + 1)
            await db.commit()
        result.left = len(candidates) - result.checked
        result.stop_reason = check.stop_reason
        if budget is not None:
            budget -= result.checked
        if check.stop_reason and "spending limit" in check.stop_reason:
            break  # the case's limit: the remaining files stay unreviewed, counted below
    return outcome


def summary(outcomes: list[CaseOutcome]) -> dict[str, Any]:
    by_status: dict[str, int] = defaultdict(int)
    for o in outcomes:
        for f in o.files:
            for key in ("verified", "rejected", "uncertain"):
                by_status[key] += getattr(f, key)
    return {"cases": len(outcomes), "before": sum(o.before for o in outcomes),
            "checked": sum(o.checked for o in outcomes), **by_status,
            "stopped": [{"case_id": o.case_id, "file": f.evidence_file_id, "reason": f.stop_reason, "left": f.left}
                        for o in outcomes for f in o.files if f.stop_reason]}
