"""Prompts that get better every time (lx-agentfit round 2, R12), with nothing lost on the way (rule 2).

The loop, all in this module and ``scripts/agent_prompt_loop.py``:

1. Versions. Every prompt part (both system prompt layers, the final-answer prompt and request, the answer
   requirements, the case briefing, the agent-fit switches, each tool's definition) is part of the run's prompt
   version (``run_record.prompt_version_source``), stored whole in ``agent_prompt_versions`` and named on every run.
   ``part_versions`` splits a stored version into one short hash per part, so two runs can be compared part by part.
2. Outcomes. ``run_outcomes`` reads each run's signals, read-only: how it ended, the rule check of its answer
   (``answer_quality``, from the result previews the run kept), whether the person's next message in the thread
   asked to continue or retry, whether the answer was accepted into a dossier, and whether a record it cited was
   corrected or confirmed in the manual-change feed after it.
3. Candidates are drafted from the failures and reviewed as code; they live behind a switch (``fit``).
4. ``decide`` accepts a candidate only when it scores better on the question set and loses nothing on any question,
   held-out questions included: a question it was not written from (``held_out``) must be among those checked.
   The demo key is one count among the others, never the target.
5. ``record`` keeps each decision and its numbers in ``prompt_history.jsonl`` beside this file, so a version can be
   rolled back to the one before it.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Iterable

from services.agent import answer_quality as AQ

HISTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompt_history.jsonl")
HELD_OUT_SHARE = 0.3
_CONTINUE = re.compile(r"^\s*(?:continue|carry on|keep going|go on|go ahead|retry|try again|again|finish|"
                       r"contin[uú]a\w*|sigue|reintenta\w*)\b", re.I)
_KEY_RANK = {"wrong": 0, "missed": 1, None: 1, "found": 2}


def _h(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:12]


def part_versions(prompt_text: dict[str, Any] | None, tool_schemas: list[dict] | None) -> dict[str, str]:
    """{part: short hash} for a stored prompt version: each prompt part, and each tool's definition by name."""
    parts = {f"prompt:{name}": _h(value) for name, value in sorted((prompt_text or {}).items())}
    for tool in tool_schemas or []:
        name = (tool.get("function") or {}).get("name") or tool.get("name")
        if name:
            parts[f"tool:{name}"] = _h(tool)
    return parts


def changed_parts(a: dict[str, str], b: dict[str, str]) -> list[str]:
    """The parts that differ between two versions (added, removed or changed)."""
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


def held_out(question_ids: Iterable[str], share: float = HELD_OUT_SHARE) -> set[str]:
    """A fixed share of questions kept out of drafting: chosen by a hash of the id, so a question stays on its side
    as the set grows and a new question joins one side for good."""
    return {q for q in question_ids if int(hashlib.sha256(q.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF < share}


def decide(current: dict[str, dict], candidate: dict[str, dict], *, held: set[str],
           written_from: Iterable[str] = ()) -> dict[str, Any]:
    """Whether ``candidate`` replaces ``current``. Both map a question id to its ``answer_quality.score`` (plus
    ``key`` for a demo question). Accepted only when: no question loses on any count; at least one count gains;
    and at least one held-out question that the candidate was not written from was checked."""
    written = set(written_from)
    common = sorted(set(current) & set(candidate))
    losses, gains = {}, {}
    for q in common:
        lost = AQ.losses(current[q], candidate[q])
        before_key, after_key = current[q].get("key"), candidate[q].get("key")
        if _KEY_RANK.get(after_key, 1) < _KEY_RANK.get(before_key, 1):
            lost.append(f"key {before_key} → {after_key}")
        if lost:
            losses[q] = lost
        won = AQ.gains(current[q], candidate[q])
        if _KEY_RANK.get(after_key, 1) > _KEY_RANK.get(before_key, 1):
            won.append(f"key {before_key} → {after_key}")
        if won:
            gains[q] = won
    missing = sorted(set(current) - set(candidate))
    checked_held = sorted(q for q in common if q in held and q not in written)
    reasons = []
    if losses:
        reasons.append(f"{len(losses)} question(s) lose on a count")
    if missing:
        reasons.append(f"{len(missing)} question(s) have no candidate answer")
    if not gains:
        reasons.append("no count gains")
    if not checked_held:
        reasons.append("no held-out question was checked")
    return {"accepted": not reasons, "reasons": reasons, "questions": len(common), "losses": losses,
            "gains": gains, "missing": missing, "held_out_checked": checked_held}


def record(decision: dict[str, Any], *, part: str, current: str, candidate: str, note: str = "",
           path: str = HISTORY) -> dict[str, Any]:
    """Append one decision, accepted or not, with its numbers; the line before an accepted one is the rollback."""
    line = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "part": part, "current": current,
            "candidate": candidate, "accepted": decision["accepted"], "reasons": decision["reasons"],
            "questions": decision["questions"], "losses": decision["losses"], "gains": decision["gains"],
            "held_out_checked": decision["held_out_checked"], "note": note}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n")
    return line


def history(path: str = HISTORY) -> list[dict[str, Any]]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def run_outcomes(db, *, since: datetime, case_id=None, limit: int = 2000) -> list[dict[str, Any]]:
    """Each run's signals since ``since``, read-only, newest first. Counts and ids only (no case content)."""
    from sqlalchemy import text
    params = {"since": since, "lim": int(limit)}
    where = "r.started_at >= :since"
    if case_id:
        where += " AND r.case_id = :case"
        params["case"] = str(case_id)
    rows = db.execute(text(
        f"SELECT r.id, r.thread_id, r.case_id, r.status, r.prompt_version, r.prompt_version_label, r.tool_budget, "
        f"r.tool_calls_used, r.input_message, r.final_answer, r.completed_at, r.started_at FROM agent_runs r "
        f"WHERE {where} ORDER BY r.started_at DESC LIMIT :lim"), params).mappings().all()
    out = []
    for r in rows:
        nxt = db.execute(text(
            "SELECT n.input_message FROM agent_runs n WHERE n.thread_id = :t AND n.started_at > :s "
            "ORDER BY n.started_at LIMIT 1"),
            {"t": r["thread_id"], "s": r["started_at"]}).scalar()
        accepted = db.execute(text(
            "SELECT count(*) FROM dossier_assessments a JOIN agent_messages m ON m.id = a.agent_message_id "
            "WHERE m.run_id = :r"), {"r": r["id"]}).scalar()
        previews = [p for (p,) in db.execute(text(
            "SELECT result_preview FROM agent_tool_calls WHERE run_id = :r ORDER BY sequence_number"),
            {"r": r["id"]}) if p]
        answer = r["final_answer"] or ""
        cited = sorted({link.split("/", 3)[2] for link in AQ._LINK.findall(answer) if link.count("/") >= 2})
        corrected = 0
        if cited and r["completed_at"]:
            corrected = db.execute(text(
                "SELECT count(DISTINCT subject_id) FROM manual_changes WHERE case_id = :c AND NOT is_test AND "
                "created_at > :t AND subject_id = ANY(:ids)"),
                {"c": r["case_id"], "t": r["completed_at"], "ids": cited}).scalar()
        stop = bool(r["tool_budget"] and (r["tool_calls_used"] or 0) >= r["tool_budget"])
        score = AQ.score(answer, previews, question=r["input_message"] or "", stopped_at_limit=stop)
        out.append({"run": str(r["id"]), "prompt_version": r["prompt_version_label"], "status": r["status"],
                    "limit_stop": stop, "followed_by_continue": bool(nxt and _CONTINUE.search(nxt)),
                    "accepted_into_dossier": int(accepted or 0), "cited_records_changed_after": int(corrected or 0),
                    "score": {k: score[k] for k in ("claims", "cited", "uncited", "citations", "not_read",
                                                    "in_record", "not_in_record", "unfinished_unstated",
                                                    "other_side_missing", "certainty")},
                    "score_from": "result previews the run kept (not the whole results)"})
    return out


def by_version(outcomes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per prompt version: runs, how they ended, and the summed signals and rule-check counts."""
    table: dict[str, dict[str, Any]] = {}
    for o in outcomes:
        row = table.setdefault(o["prompt_version"] or "not recorded", {
            "runs": 0, "limit_stops": 0, "followed_by_continue": 0, "accepted_into_dossier": 0,
            "cited_records_changed_after": 0, "statuses": {}, "score": {}})
        row["runs"] += 1
        row["limit_stops"] += int(o["limit_stop"])
        row["followed_by_continue"] += int(o["followed_by_continue"])
        row["accepted_into_dossier"] += int(bool(o["accepted_into_dossier"]))
        row["cited_records_changed_after"] += int(bool(o["cited_records_changed_after"]))
        row["statuses"][o["status"]] = row["statuses"].get(o["status"], 0) + 1
        for k, v in o["score"].items():
            row["score"][k] = row["score"].get(k, 0) + int(v)
    return table
