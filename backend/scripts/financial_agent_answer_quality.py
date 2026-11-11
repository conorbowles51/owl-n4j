"""Score recorded agent answers with services.agent.answer_quality (lx-agentfit round 2, R2a). Read-only.

    python -m scripts.financial_agent_answer_quality --runs DIR[:LABEL] ... --outputs DIR [--json OUT]

Each run is a replay record (scripts/financial_agent_fit_replay.py: question, answer, budget_stop, key_score) and,
when the trace replay kept them, its tools' raw outputs (<outputs>/<label>-<name>.pkl). Without the outputs the
citation and figure counts read only the answer. Prints one row per answer and, when two labels share a question,
each count on which the second is worse (a loss blocks, whatever else gained). Counts only: no case content.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import pickle
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.agent import answer_quality as AQ  # noqa: E402

COLUMNS = ("claims", "cited", "uncited", "citations", "not_read", "in_record", "not_in_record",
           "unfinished_unstated", "other_side_missing", "certainty")


def _has_more(value, depth=0) -> int:
    if depth > 6:
        return 0
    if isinstance(value, dict):
        own = int(bool(value.get("has_more")))
        return own + sum(_has_more(v, depth + 1) for v in value.values() if isinstance(v, (dict, list)))
    if isinstance(value, list):
        return sum(_has_more(v, depth + 1) for v in value[:50])
    return 0


def score_dir(path: str, label: str, outputs_dir: str | None) -> dict[str, dict]:
    rows = {}
    for f in sorted(glob.glob(os.path.join(path, "*.json"))):
        name = os.path.basename(f)[:-5]
        rec = json.load(open(f))
        if rec.get("failed") or not rec.get("answer"):
            continue
        outputs, kept = [], False
        pkl = os.path.join(outputs_dir or "", f"{label}-{name}.pkl")
        if outputs_dir and os.path.exists(pkl):
            outputs = [o for _, o in pickle.load(open(pkl, "rb")) if isinstance(o, dict)]
            kept = True
        s = AQ.score(rec["answer"], outputs, question=rec.get("question") or "",
                     stopped_at_limit=bool(rec.get("budget_stop")),
                     results_with_more=sum(_has_more(o.get("data")) for o in outputs))
        s["outputs_kept"] = kept
        s["key"] = (rec.get("key_score") or {}).get("result")
        rows[name] = s
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True, help="DIR:LABEL (label names the outputs' prefix)")
    ap.add_argument("--outputs")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    states = {}
    for spec in a.runs:
        path, _, label = spec.partition(":")
        states[label or os.path.basename(path)] = score_dir(path, label or os.path.basename(path), a.outputs)
    for label, rows in states.items():
        print(f"## {label}: {len(rows)} answers")
        print("| run | " + " | ".join(COLUMNS) + " | key | outputs |")
        for name, s in rows.items():
            print(f"| {name} | " + " | ".join(str(int(s[c])) for c in COLUMNS) + f" | {s['key'] or ''} | "
                  f"{'yes' if s['outputs_kept'] else 'no'} |")
        print("| total | " + " | ".join(str(sum(int(s[c]) for s in rows.values())) for c in COLUMNS) + " | | |")
    labels = list(states)
    if len(labels) == 2:
        first, second = states[labels[0]], states[labels[1]]
        print(f"## losses {labels[0]} → {labels[1]} (same run name)")
        for name in sorted(set(first) & set(second)):
            lost = AQ.losses(first[name], second[name])
            if lost:
                print(f"- {name}: " + "; ".join(lost))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(states, f, indent=1, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
