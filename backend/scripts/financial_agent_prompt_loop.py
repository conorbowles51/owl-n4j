"""The prompt loop's commands (lx-agentfit round 2, R12; services.agent.prompt_loop). Read-only on the database.

    outcomes [--days N] [--case ID] [--json OUT]   per prompt version: runs, limit stops, typed continue/retry,
                                                    answers accepted into a dossier, cited records changed after,
                                                    and the rule-check counts (live: bash live-run.sh <tree> ...)
    parts A B                                       the prompt parts that differ between two stored versions (labels)
    decide CURRENT CANDIDATE --part P [--written-from IDS] [--record]
                                                    CURRENT/CANDIDATE: score files of financial_agent_answer_quality
                                                    (--json), one state each; accept only with no question worse,
                                                    a gain, and a held-out question checked; --record keeps the
                                                    decision in services/agent/prompt_history.jsonl
Counts and ids only: no case content is printed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['PGOPTIONS'] = (os.environ.get('PGOPTIONS', '') + ' -c default_transaction_read_only=on').strip()


def _question_id(run_name: str) -> str:
    """demo-Q1-2 → demo-Q1; real-<id>-1 → real-<id>: repeats of one question share an id."""
    return re.sub(r"-\d+$", "", run_name)


def _per_question(state: dict) -> dict:
    """One score per question: the worst of its repeats on each count (a loss in any repeat counts)."""
    from services.agent import answer_quality as AQ
    out: dict = {}
    for name, s in state.items():
        q = _question_id(name)
        if q not in out:
            out[q] = dict(s)
            continue
        cur = out[q]
        for k in AQ.WORSE_HIGHER:
            cur[k] = max(int(cur.get(k, 0)), int(s.get(k, 0)))
        for k in AQ.BETTER_HIGHER:
            cur[k] = min(int(cur.get(k, 0)), int(s.get(k, 0)))
        rank = {"wrong": 0, "missed": 1, None: 1, "found": 2}
        if rank.get(s.get("key"), 1) < rank.get(cur.get("key"), 1):
            cur["key"] = s.get("key")
    return out


def _runs_by_question(state: dict) -> dict:
    """Every repeat of each question, as a list (decide_range compares against their spread)."""
    out: dict = {}
    for name, s in state.items():
        out.setdefault(_question_id(name), []).append(dict(s))
    return out


def _load_state(path: str) -> dict:
    data = json.load(open(path))
    if len(data) == 1 and isinstance(next(iter(data.values())), dict) and all(
            isinstance(v, dict) and "claims" in v for v in next(iter(data.values())).values()):
        data = next(iter(data.values()))
    return data


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("outcomes")
    o.add_argument("--days", type=int, default=30)
    o.add_argument("--case")
    o.add_argument("--json")
    p = sub.add_parser("parts")
    p.add_argument("a")
    p.add_argument("b")
    d = sub.add_parser("decide")
    d.add_argument("current")
    d.add_argument("candidate")
    d.add_argument("--part", required=True)
    d.add_argument("--written-from", default="", help="comma-separated question ids the candidate was drafted from")
    d.add_argument("--record", action="store_true")
    d.add_argument("--single", action="store_true", help=(
        "compare one score per question (worst of its repeats) instead of the same-settings range"))
    a = ap.parse_args(argv)
    from services.agent import prompt_loop as PL
    if a.cmd == "decide":
        written = [x for x in a.written_from.split(",") if x]
        if a.single:
            cur, cand = _per_question(_load_state(a.current)), _per_question(_load_state(a.candidate))
            held = PL.held_out(set(cur) | set(cand))
            decision = PL.decide(cur, cand, held=held, written_from=written)
        else:
            cur, cand = _runs_by_question(_load_state(a.current)), _runs_by_question(_load_state(a.candidate))
            held = PL.held_out(set(cur) | set(cand))
            decision = PL.decide_range(cur, cand, held=held, written_from=written)
        print(json.dumps({k: decision[k] for k in ("accepted", "reasons", "questions", "held_out_checked")},
                         indent=1))
        for q, lost in decision["losses"].items():
            print(f"- loses {q}: " + "; ".join(lost))
        if a.record:
            PL.record(decision, part=a.part, current=os.path.basename(a.current),
                      candidate=os.path.basename(a.candidate))
        return 0 if decision["accepted"] else 1
    from sqlalchemy import text
    from postgres.session import _get_engine
    from sqlalchemy.orm import Session
    engine = _get_engine()
    with Session(engine) as db:
        if db.execute(text("SHOW default_transaction_read_only")).scalar() != "on":
            raise SystemExit("refusing to run: sessions are not read-only")
        if a.cmd == "parts":
            from postgres.models.agent import AgentPromptVersion
            rows = {r.label: r for r in db.query(AgentPromptVersion).all()}
            va, vb = rows.get(a.a), rows.get(a.b)
            if not va or not vb:
                raise SystemExit("no stored prompt version with that label")
            print("\n".join(PL.changed_parts(PL.part_versions(va.prompt_text, va.tool_schemas),
                                             PL.part_versions(vb.prompt_text, vb.tool_schemas))))
            return 0
        since = datetime.now(timezone.utc) - timedelta(days=a.days)
        outcomes = PL.run_outcomes(db, since=since, case_id=a.case)
    table = PL.by_version(outcomes)
    print(json.dumps(table, indent=1, sort_keys=True))
    if a.json:
        with open(a.json, "w") as f:
            json.dump({"outcomes": outcomes, "by_version": table}, f, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
