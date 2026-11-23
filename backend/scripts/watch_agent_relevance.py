"""The status board's "Agent relevance" section and its alerts (lx-relevancetest D; plan R5 live signals).

From the stored run records (agent_runs, agent_tool_calls), per UTC day:
- empty searches: search calls that returned nothing, of all search calls (and per tool over the last 7 days);
- results used: search calls whose result held citations and at least one of them is in the run's final answer;
- refused queries: graph queries (run_readonly_cypher) that failed, of all graph queries;
- lookups per answer: the median number of tool calls of a completed run that opens a thread. A follow-up in a thread
  ("what comes before each of those?") builds on the reads above it and takes few calls by design, so a day with many
  of them would look worse with no change in the agent.
A number worsens when the last complete day (with at least MIN_RUNS runs) is outside the range of the earlier qualifying
days of the week before (at least MIN_DAYS of them): same-settings days differ by that much on their own. A worsened
number is sent once, as a work message, to the job that owns it (OWNERS), with the numbers.
    set -a; . <app>/.env; set +a; PYTHONPATH=. python scripts/watch_agent_relevance.py --board <md> --state <json>
Reads through a read-only session; writes only the board file and the state file.

Origin drift: every relevance gate keeps its origin side (GATE_DIR/*.base.json, live data, read-only). Two origin
runs of the same judged set are compared over the queries both ran, judged on the same records; a kind with DRIFT_MIN_QUERIES+ judged queries whose
MRR or recall at 10 fell by more than DRIFT is sent to its owner (DRIFT_OWNERS). The gate itself cannot see such a
fall: it asks origin and the candidate on the same data, so a change in the data (new vectors from the embedding
sweep) moves both sides. Measured 17 Nov: the same code 35 minutes apart moved recall at 10 by 0.008; the sweep's
graph connection vectors moved meaning MRR 0.58 to 0.44 and phone search MRR 0.58 to 0.41 between 07:35 and 09:31.
"""
from __future__ import annotations

import argparse
import json
import os
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
GATE_DIR = "/mnt/owl-data/tmp/relevance-gate"
DRIFT = 0.05
DRIFT_MIN_QUERIES = 5
DRIFT_OWNERS = {"meaning": ("lx-embedall", "meaning search and the vectors it reads (D3)")}
DRIFT_DEFAULT_OWNER = ("lx-casesearch", "the case search service and the agent's search tools (D1/D12/D19)")


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
            if not r.get("follow_up"):
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


def _origin_rows(doc: dict, only: set) -> list[dict]:
    qs = (doc.get("runs") or [{}])[0].get("queries") or {}
    return [dict(kind=q["kind"], score=q["score"], id=k) if "score" in q else dict(kind=q["kind"], error=1, id=k)
            for k, q in qs.items() if k in only]


def origin_drift(docs: list[dict]) -> list[dict]:
    """Pure: the kinds whose numbers fell between the last two origin runs of one judged set (gate .base.json)."""
    from services.agent.relevance_eval import aggregate
    by_set = defaultdict(list)
    for d in docs:
        m = d.get("meta") or {}
        if m.get("at") and m.get("set_hash") and d.get("runs"):
            by_set[m["set_hash"]].append(d)
    out = []
    for docs_ in by_set.values():
        if len(docs_) < 2:
            continue
        prev, last = sorted(docs_, key=lambda d: d["meta"]["at"])[-2:]
        pq, lq = prev["runs"][0]["queries"], last["runs"][0]["queries"]
        # Only queries judged on the same records: a change in the judging is not a change in the search.
        common = {k for k in set(pq) & set(lq) if set((pq[k].get("score") or {}).get("ranks") or {})
                  == set((lq[k].get("score") or {}).get("ranks") or {})}
        pr, lr = _origin_rows(prev, common), _origin_rows(last, common)
        a, b = aggregate(pr), aggregate(lr)
        for kind in sorted(b):
            if kind == "all":
                continue
            judged = sum(1 for r in lr if r["kind"] == kind and r.get("score", {}).get("relevant"))
            if judged < DRIFT_MIN_QUERIES:
                continue
            fell = {m: (a[kind][m], b[kind][m]) for m in ("mrr", "recall_at_10")
                    if a[kind][m] is not None and b[kind][m] is not None and a[kind][m] - b[kind][m] > DRIFT}
            if not fell:
                continue
            found = lambda rows: {(r["id"], x) for r in rows if r["kind"] == kind and "score" in r
                                  for x in r["score"]["found_at_10"]}
            owner, owns = DRIFT_OWNERS.get(kind, DRIFT_DEFAULT_OWNER)
            out.append(dict(kind=kind, owner=owner, owns=owns, fell=fell, queries=judged,
                            prev_sha=prev["meta"].get("sha", "")[:12], prev_at=prev["meta"]["at"],
                            sha=last["meta"].get("sha", "")[:12], at=last["meta"]["at"],
                            out_of_top10=sorted("%s %s" % k for k in found(pr) - found(lr))))
    return out


def drift_text(d: dict) -> str:
    nums = "; ".join("%s %.2f to %.2f" % (m.replace("_at_", "@"), a, b) for m, (a, b) in d["fell"].items())
    lost = ", ".join(d["out_of_top10"][:8]) + (" and %d more" % (len(d["out_of_top10"]) - 8)
                                               if len(d["out_of_top10"]) > 8 else "")
    return ("Agent relevance watch: origin's %s search fell between two gate runs of the same judged set (%d judged "
            "queries; a fall over %.2f counts): %s. Origin %s at %s to %s at %s, both read the live data at the time. "
            "Out of the top 10: %s. Files: %s/*-vs-<origin>.base.json. If no search code changed between the two "
            "(git log %s..%s), the data moved (new vectors from the embedding sweep). You own %s: find the cause and "
            "fix it with a test that fails on the old code."
            % (d["kind"], d["queries"], DRIFT, nums, d["prev_sha"], d["prev_at"], d["sha"], d["at"], lost or "none",
               GATE_DIR, d["prev_sha"], d["sha"], d["owns"]))


def board_lines(metrics: dict, tools: dict, alerts: list[dict], today: date, drift: list[dict] = ()) -> list[str]:
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
    for d in drift:
        lines.append("- **Origin %s search fell, %s to %s: %s; sent to %s**" % (
            d["kind"], d["prev_at"], d["at"], "; ".join("%s %.2f to %.2f" % (m.replace("_at_", "@"), a, b)
                                                       for m, (a, b) in d["fell"].items()), d["owner"]))
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
    ap.add_argument("--gate-dir", default=GATE_DIR)
    args = ap.parse_args(argv)
    from sqlalchemy import text
    from services.agent.tools import _financial_session
    today = datetime.now(timezone.utc).date()
    since = today - timedelta(days=args.days)
    with _financial_session() as s:
        s.execute(text("SET TRANSACTION READ ONLY"))
        runs = [dict(id=str(r.id), day=r.day, final_answer=r.final_answer, follow_up=r.follow_up)
                for r in s.execute(text(
            "SELECT id, (started_at AT TIME ZONE 'UTC')::date AS day, final_answer, "
            "EXISTS (SELECT 1 FROM agent_runs p WHERE p.thread_id = agent_runs.thread_id "
            "AND p.started_at < agent_runs.started_at) AS follow_up FROM agent_runs "
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
    import glob
    docs = []
    for path in glob.glob(os.path.join(args.gate_dir, "*.base.json")):
        try:
            docs.append(json.load(open(path)))
        except (OSError, ValueError):
            print("unreadable gate file %s" % path, file=sys.stderr)
    drift = origin_drift(docs)
    for d in drift:
        key = "drift:%s:%s:%s" % (d["kind"], d["prev_at"], d["at"])
        if key in sent or args.no_tell:
            continue
        res = subprocess.run([TELL, d["owner"], "relevance-watch", drift_text(d)], capture_output=True, text=True,
                             timeout=60)
        if res.returncode == 0:
            sent.add(key)
        else:
            print("tell failed: exit %s %s" % (res.returncode, res.stderr[-200:]), file=sys.stderr)
    with open(args.board + ".tmp", "w") as f:
        f.write("\n".join(board_lines(metrics, tools, alerts, today, drift)) + "\n")
    os.replace(args.board + ".tmp", args.board)
    with open(args.state, "w") as f:
        json.dump(dict(sent=sorted(sent)[-200:], at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())), f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
