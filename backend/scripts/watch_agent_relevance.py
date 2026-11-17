"""The status board's "Agent relevance" section and its alerts (lx-relevancetest D; plan R5 live signals).

From the stored run records (agent_runs, agent_tool_calls), per UTC day:
- empty searches: search calls that returned nothing, of all search calls (and per tool over the last 7 days);
- results used: search calls whose result held citations and at least one of them is in the run's final answer;
- refused queries: graph queries (run_readonly_cypher) that failed, of all graph queries;
- lookups per answer: the median number of tool calls of a completed run.
A number worsens when the last complete day (with at least MIN_RUNS runs) is outside the range of the earlier qualifying
days of the week before (at least MIN_DAYS of them): same-settings days differ by that much on their own. A worsened
number is sent once, as a work message, to the job that owns it (OWNERS), with the numbers.
    set -a; . <app>/.env; set +a; PYTHONPATH=. python scripts/watch_agent_relevance.py --board <md> --state <json>
Reads through a read-only session; writes only the board file and the state file.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

TELL = "/mnt/owl-data/fin-wt/headless/tell.sh"
SEARCH_TOOLS = ("search_case", "search_by_meaning", "search_documents", "search_exact_words", "search_graph_entities",
                "get_financial_transactions", "phone_messages", "get_casework", "get_timeline_events",
                "search_graph_entities_many", "case_search")
CYPHER = "run_readonly_cypher"
MIN_RUNS = 10
MIN_DAYS = 3
WEEK = 7
CITE = re.compile(r"(?:rec|doc|txn)://[^\s\"')\]\\]+")
# metric: (label, worse when it goes, owner job, what the owner owns)
OWNERS = {
    "empty_share": ("empty searches", "up", "lx-casesearch", "the case search service (D1/D12/D19)"),
    "used_share": ("share of search results the answer uses", "down", "lx-deepinvest",
                   "reading and using what the searches return (D13/D18)"),
    "refused_share": ("graph queries refused", "up", "lx-agentquick", "the graph query forms the prompt teaches (D8)"),
    "lookups_median": ("lookups per answer (median)", "down", "lx-deepinvest", "the plan and completeness check (D18)"),
}


def _empty(call: dict) -> bool:
    if call.get("status") != "success":
        return False
    if call.get("returned") is not None:
        return call["returned"] == 0
    return call.get("total") == 0


def day_metrics(runs: list[dict], calls: list[dict]) -> dict:
    """Pure: {day: metrics} from completed runs ({id, day, final_answer}) and their calls ({run_id, name, status,
    returned, total, preview})."""
    by_run = defaultdict(list)
    for c in calls:
        by_run[c["run_id"]].append(c)
    out = {}
    days = defaultdict(list)
    for r in runs:
        days[r["day"]].append(r)
    for day, rs in days.items():
        search = empty = cited = used = cy = cy_bad = 0
        lookups = []
        for r in rs:
            cs = by_run.get(r["id"], [])
            lookups.append(len(cs))
            answer = r.get("final_answer") or ""
            for c in cs:
                if c["name"] in SEARCH_TOOLS:
                    search += 1
                    empty += _empty(c)
                    cites = set(CITE.findall(c.get("preview") or ""))
                    if cites:
                        cited += 1
                        used += any(x in answer for x in cites)
                if c["name"] == CYPHER:
                    cy += 1
                    cy_bad += c.get("status") != "success"
        out[day] = dict(runs=len(rs), search_calls=search,
                        empty_share=round(empty / search, 3) if search else None,
                        used_share=round(used / cited, 3) if cited else None,
                        refused_share=round(cy_bad / cy, 3) if cy else None, cypher_calls=cy,
                        lookups_median=statistics.median(lookups) if lookups else None)
    return out


def per_tool(calls: list[dict]) -> dict:
    t = defaultdict(lambda: [0, 0])
    for c in calls:
        if c["name"] in SEARCH_TOOLS:
            t[c["name"]][0] += 1
            t[c["name"]][1] += _empty(c)
    return {k: dict(calls=v[0], empty=v[1]) for k, v in t.items()}


def worsened(metrics: dict, today: date) -> list[dict]:
    """Pure: the numbers of the last complete qualifying day outside the range of the week before it."""
    days = sorted(d for d, m in metrics.items() if d < today and m["runs"] >= MIN_RUNS)
    if not days:
        return []
    last = days[-1]
    prior = [d for d in days[:-1] if last - timedelta(days=WEEK) <= d < last]
    out = []
    for metric, (label, worse, owner, owns) in OWNERS.items():
        now = metrics[last].get(metric)
        before = [metrics[d][metric] for d in prior if metrics[d].get(metric) is not None]
        if now is None or len(before) < MIN_DAYS:
            continue
        lo, hi = min(before), max(before)
        if (worse == "up" and now > hi) or (worse == "down" and now < lo):
            out.append(dict(metric=metric, label=label, owner=owner, owns=owns, day=last.isoformat(), value=now,
                            low=lo, high=hi, days=len(before)))
    return out


def board_lines(metrics: dict, tools: dict, alerts: list[dict], today: date) -> list[str]:
    def f(v, pct=True):
        return "-" if v is None else ("%.0f%%" % (100 * v) if pct else ("%g" % v))
    lines = ["| Day (UTC) | Answers | Search calls | Empty searches | Results used | Graph queries refused | "
             "Lookups per answer |", "|---|---|---|---|---|---|---|"]
    for d in sorted(metrics, reverse=True)[:WEEK]:
        m = metrics[d]
        lines.append("| %s | %d | %d | %s | %s | %s of %d | %s |" % (
            d.isoformat(), m["runs"], m["search_calls"], f(m["empty_share"]), f(m["used_share"]),
            f(m["refused_share"]), m["cypher_calls"], f(m["lookups_median"], pct=False)))
    if tools:
        worst = sorted(tools.items(), key=lambda kv: -(kv[1]["empty"] / kv[1]["calls"]))
        lines.append("- Empty searches by tool, last 7 days: " + "; ".join(
            "%s %d of %d" % (k, v["empty"], v["calls"]) for k, v in worst if v["calls"]))
    for a in alerts:
        lines.append("- **%s worsened on %s: %s (the week before: %s to %s over %d days); sent to %s**" % (
            a["label"], a["day"], a["value"], a["low"], a["high"], a["days"], a["owner"]))
    lines.append("- A day counts with %d+ answers; a number worsens outside the range of the week before. "
                 "Gate for releases: scripts/financial_agent_relevance.py gate." % MIN_RUNS)
    return lines


def alert_text(a: dict) -> str:
    return ("Agent relevance watch: %s worsened on %s: %s, outside the week before's range %s to %s (%d days with "
            "%d+ answers; numbers from agent_runs/agent_tool_calls, board section 'Agent relevance'). You own %s: "
            "find the change that moved it and fix it with a test that fails on the old code."
            % (a["label"], a["day"], a["value"], a["low"], a["high"], a["days"], MIN_RUNS, a["owns"]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--days", type=int, default=15)
    ap.add_argument("--no-tell", action="store_true")
    args = ap.parse_args(argv)
    from sqlalchemy import text
    from services.agent.tools import _financial_session
    today = datetime.now(timezone.utc).date()
    since = today - timedelta(days=args.days)
    with _financial_session() as s:
        s.execute(text("SET TRANSACTION READ ONLY"))
        runs = [dict(id=str(r.id), day=r.day, final_answer=r.final_answer) for r in s.execute(text(
            "SELECT id, (started_at AT TIME ZONE 'UTC')::date AS day, final_answer FROM agent_runs "
            "WHERE status = 'completed' AND started_at >= :since"), dict(since=since))]
        calls = [dict(run_id=str(c.run_id), name=c.name, status=c.status, returned=c.returned, total=c.total,
                      preview=c.preview, at=c.created_at) for c in s.execute(text(
            "SELECT c.run_id, c.name, c.status, c.returned, c.total, c.created_at, "
            "CASE WHEN c.name = ANY(:search) THEN left(c.result_preview::text, 60000) END AS preview "
            "FROM agent_tool_calls c JOIN agent_runs r ON r.id = c.run_id "
            "WHERE r.status = 'completed' AND r.started_at >= :since"), dict(since=since, search=list(SEARCH_TOOLS)))]
    metrics = day_metrics(runs, calls)
    week = datetime.now(timezone.utc) - timedelta(days=WEEK)
    tools = per_tool([c for c in calls if c["at"] and c["at"] >= week])
    try:
        state = json.load(open(args.state))
    except (OSError, ValueError):
        state = {}
    sent = set(state.get("sent") or [])
    alerts = worsened(metrics, today)
    for a in alerts:
        key = "%s:%s" % (a["metric"], a["day"])
        if key in sent or args.no_tell:
            continue
        res = subprocess.run([TELL, a["owner"], "relevance-watch", alert_text(a)], capture_output=True, text=True,
                             timeout=60)
        if res.returncode == 0:
            sent.add(key)
        else:
            print("tell failed: exit %s %s" % (res.returncode, res.stderr[-200:]), file=sys.stderr)
    with open(args.board + ".tmp", "w") as f:
        f.write("\n".join(board_lines(metrics, tools, alerts, today)) + "\n")
    import os
    os.replace(args.board + ".tmp", args.board)
    with open(args.state, "w") as f:
        json.dump(dict(sent=sorted(sent)[-200:], at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())), f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
