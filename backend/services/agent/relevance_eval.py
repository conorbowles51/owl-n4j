"""Relevance and report measurement for the case agent (lx-relevancetest, plan D21 / R5).

Pure scoring code: it never holds case material, names or answer keys. The judged sets and rubrics live beside the
answer keys under ``evidence-engine/tests/phone`` and are read by ``scripts/financial_agent_relevance.py``, which runs
the real agent tools and agent loop. Nothing here is given to the agent.

Three parts:
- retrieval: a tool's result is cut into the units the model reads (``result_units``), in the order it reads them;
  each judged query is scored for recall at 10 and 50, the rank of the first relevant unit, decoys in the top 10 and
  empty results (``score_query``), and the scores are summed per search kind (``aggregate``);
- reports: a long answer is scored against a rubric (facts stated, decoys linked, claims cited and saying why they
  matter) with a pass mark set in the rubric (``score_report``);
- the gate: repeated runs of a baseline and a candidate are compared, and a loss counts only outside the spread of
  same-settings runs (``compare``), with a plain verdict (``verdict_lines``).
"""
from __future__ import annotations

import json
import re
import statistics
import unicodedata
from typing import Any, Iterable

# The keys under which the agent tools put their result records. A unit is one record dict in such a list; the walk
# does not go inside a unit once taken, so an event's own connections or a hit's links stay part of that unit.
UNIT_KEYS = ("items", "results", "chunks", "entities", "events", "hits", "transactions", "messages", "rows",
             "matches", "records", "passages", "units")
KS = (10, 50)

_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})


def norm(text: Any) -> str:
    """Lower case, NFKC, straight quotes, single spaces: how judged patterns and unit text are compared."""
    s = unicodedata.normalize("NFKC", str(text or "")).translate(_QUOTES).lower()
    return re.sub(r"\s+", " ", s).strip()


def result_units(payload: Any) -> list[Any]:
    """The records of one tool result in the order the model reads them (depth first, keys in their stored order).

    ``payload`` is the tool's return value (``{"data": ...}``) or its data. A result with no record list at all but
    some content is one unit (a scalar answer); an empty result has none."""
    data = payload.get("data", payload) if isinstance(payload, dict) and "result_id" in payload else payload
    found: list[Any] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in UNIT_KEYS and isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
                    found.extend(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    return found


def unit_text(unit: Any) -> str:
    return norm(unit if isinstance(unit, str) else json.dumps(unit, ensure_ascii=False, default=str))


def matches(text: str, judged: dict) -> bool:
    """A unit (normalised text) is this judged record when it holds one of ``any`` and every one of ``all``."""
    anys = [norm(p) for p in judged.get("any") or []]
    alls = [norm(p) for p in judged.get("all") or []]
    if not anys and not alls:
        return False
    return (not anys or any(p in text for p in anys)) and all(p in text for p in alls)


def score_query(texts: list[str], relevant: list[dict], decoys: list[dict] | None = None) -> dict:
    """One query's scores from its units' texts (rank order). Ranks are 1-based; None: not returned."""
    decoys = decoys or []
    ranks = {}
    for item in relevant:
        ranks[item["id"]] = next((i + 1 for i, t in enumerate(texts) if matches(t, item)), None)
    decoy_ranks = {d["id"]: next((i + 1 for i, t in enumerate(texts) if matches(t, d)), None) for d in decoys}
    first = min((r for r in ranks.values() if r), default=None)
    out = dict(units=len(texts), zero=len(texts) == 0, relevant=len(relevant), ranks=ranks,
               first_relevant=first, rr=(1.0 / first) if first else 0.0, decoy_ranks=decoy_ranks,
               decoys_top10=sorted(k for k, r in decoy_ranks.items() if r and r <= 10))
    for k in KS:
        out["found_at_%d" % k] = sorted(i for i, r in ranks.items() if r and r <= k)
        out["recall_at_%d" % k] = (len(out["found_at_%d" % k]) / len(relevant)) if relevant else None
    return out


def aggregate(rows: Iterable[dict]) -> dict:
    """Scores summed per search kind and over all kinds. ``rows``: {kind, score} or {kind, error}.

    recall_at_k is micro (relevant records found / relevant records judged); mrr is over queries that have relevant
    records; zero_rate and decoy counts are over every query that ran; errors are queries whose tool crashed."""
    by: dict[str, list[dict]] = {}
    for row in rows:
        by.setdefault(row["kind"], []).append(row)
        by.setdefault("all", []).append(row)
    out = {}
    for kind, items in by.items():
        ran = [r["score"] for r in items if "score" in r]
        judged = [s for s in ran if s["relevant"]]
        m = dict(queries=len(items), errors=len(items) - len(ran))
        rel = sum(s["relevant"] for s in judged)
        for k in KS:
            m["recall_at_%d" % k] = round(sum(len(s["found_at_%d" % k]) for s in judged) / rel, 4) if rel else None
        m["mrr"] = round(sum(s["rr"] for s in judged) / len(judged), 4) if judged else None
        m["zero_rate"] = round(sum(1 for s in ran if s["zero"]) / len(ran), 4) if ran else None
        m["decoy_queries_top10"] = sum(1 for s in ran if s["decoys_top10"])
        m["decoys_top10"] = sum(len(s["decoys_top10"]) for s in ran)
        m["relevant_judged"] = rel
        out[kind] = m
    return out


# ---- the noise-aware gate ----------------------------------------------------------------------------------------

HIGHER_BETTER = ("recall_at_10", "recall_at_50", "mrr")
LOWER_BETTER = ("zero_rate", "decoys_top10", "errors")
# A difference smaller than this is rounding, never a loss.
EPS = 1e-9


def _spread(values: list[float]) -> float:
    return (max(values) - min(values)) if len(values) > 1 else 0.0


def compare(base_runs: list[dict], cand_runs: list[dict]) -> dict:
    """Compare repeated runs. Each run: {"aggregate": aggregate(...), "queries": {qid: {"kind", "score"|"error"}}}.

    A metric is a loss when the candidate's mean is worse than the baseline's mean by more than the larger of the two
    spreads (same-settings runs differ by that much on their own). A judged record is lost when every baseline run
    found it in the top 50 and no candidate run found it at all: a record the search found before and finds no more.
    A record that moved out of the top 10 is listed, and counts through recall at 10. Gains are listed the same way."""
    losses, gains, lost, moved, regained = [], [], [], [], []
    kinds = sorted({k for r in base_runs + cand_runs for k in r["aggregate"]})
    for kind in kinds:
        for metric in HIGHER_BETTER + LOWER_BETTER:
            b = [r["aggregate"].get(kind, {}).get(metric) for r in base_runs]
            c = [r["aggregate"].get(kind, {}).get(metric) for r in cand_runs]
            if any(v is None for v in b + c):
                continue
            band = max(_spread(b), _spread(c))
            diff = statistics.mean(c) - statistics.mean(b)
            worse = -diff if metric in HIGHER_BETTER else diff
            entry = dict(kind=kind, metric=metric, base=round(statistics.mean(b), 4),
                         cand=round(statistics.mean(c), 4), noise=round(band, 4))
            if worse > band + EPS:
                losses.append(entry)
            elif -worse > band + EPS:
                gains.append(entry)
    qids = sorted({q for r in base_runs for q in r["queries"]} & {q for r in cand_runs for q in r["queries"]})
    for qid in qids:
        bs = [r["queries"][qid].get("score") for r in base_runs]
        cs = [r["queries"][qid].get("score") for r in cand_runs]
        if any(s is None for s in bs) or not bs:
            continue
        for rid in bs[0]["ranks"]:
            b50 = all(s["ranks"].get(rid) and s["ranks"][rid] <= 50 for s in bs)
            b10 = all(s["ranks"].get(rid) and s["ranks"][rid] <= 10 for s in bs)
            if any(s is None for s in cs):
                if b50:
                    lost.append(dict(query=qid, record=rid, why="the candidate's tool failed"))
                continue
            c_any = any(s["ranks"].get(rid) for s in cs)
            c10 = any(s["ranks"].get(rid) and s["ranks"][rid] <= 10 for s in cs)
            if b50 and not c_any:
                lost.append(dict(query=qid, record=rid, why="found before, not found now"))
            elif b10 and not c10:
                moved.append(dict(query=qid, record=rid))
            elif not any(s["ranks"].get(rid) for s in bs) and all(s["ranks"].get(rid) for s in cs):
                regained.append(dict(query=qid, record=rid))
    verdict = "FAIL" if losses or lost else "PASS"
    return dict(verdict=verdict, losses=losses, lost_records=lost, moved_out_of_top10=moved, gains=gains,
                newly_found=regained, base_runs=len(base_runs), cand_runs=len(cand_runs))


def verdict_lines(cmp: dict, base_agg: dict, cand_agg: dict, label: str = "retrieval") -> list[str]:
    """The plain verdict a job quotes: the result, then the numbers per kind, then what was lost or gained."""
    lines = ["%s gate: %s (%d baseline run(s), %d candidate run(s); a loss counts only beyond the spread of "
             "same-settings runs)" % (label, cmp["verdict"], cmp["base_runs"], cmp["cand_runs"])]
    lines.append("%-12s %8s %8s %8s %8s %8s %6s" % ("kind", "rec@10", "rec@50", "mrr", "zero", "decoys", "errors"))

    def fmt(v):
        return "-" if v is None else ("%.2f" % v if isinstance(v, float) else str(v))

    for kind in sorted(set(base_agg) | set(cand_agg), key=lambda k: (k == "all", k)):
        b, c = base_agg.get(kind, {}), cand_agg.get(kind, {})
        cells = ["%s>%s" % (fmt(b.get(m)), fmt(c.get(m))) if b.get(m) != c.get(m) else fmt(c.get(m))
                 for m in ("recall_at_10", "recall_at_50", "mrr", "zero_rate", "decoys_top10", "errors")]
        lines.append("%-12s %8s %8s %8s %8s %8s %6s" % tuple([kind] + cells))
    for e in cmp["losses"]:
        lines.append("LOSS %s %s: %s -> %s (noise %s)" % (e["kind"], e["metric"], e["base"], e["cand"], e["noise"]))
    for e in cmp["lost_records"]:
        lines.append("LOST %s %s: %s" % (e["query"], e["record"], e["why"]))
    for e in cmp["moved_out_of_top10"]:
        lines.append("moved out of top 10: %s %s" % (e["query"], e["record"]))
    for e in cmp["gains"]:
        lines.append("gain %s %s: %s -> %s (noise %s)" % (e["kind"], e["metric"], e["base"], e["cand"], e["noise"]))
    for e in cmp["newly_found"]:
        lines.append("newly found: %s %s" % (e["query"], e["record"]))
    return lines


# ---- reports -----------------------------------------------------------------------------------------------------

# journeys/demo-key-score.mjs and scripts/financial_agent_fit_replay.py, kept identical (shared cases test).
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_DATE = re.compile(r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{2,4}")


def expect_hit(term: str, text: str) -> bool:
    """journeys/demo-key-score.mjs expectHit: a word counts as a whole word; a number never counts as a calendar day
    or part of a written date."""
    t, s = str(term).lower(), str(text or "").lower()
    if t.isdigit():
        dates = [m.span() for m in _DATE.finditer(s)]
        for m in re.finditer(r"(?<!\d)(?<!\d,)%s(?!\d|,\d)" % re.escape(t), s):
            start, end = m.span()
            if any(start >= a and end <= b for a, b in dates):
                continue
            if re.search(_MONTH + r"\s*$", s[max(0, start - 12):start]) or \
                    re.match(r"\s*(?:st|nd|rd|th)?\s*(?:of\s+)?" + _MONTH, s[end:end + 14]):
                continue
            return True
        return False
    left = r"(?<![^\W])" if re.match(r"\w", t) else ""
    right = r"(?![^\W])" if re.search(r"\w$", t) else ""
    return re.search(left + re.escape(t) + right, s) is not None


_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
CITATION = re.compile(r"(?:doc|rec|txn)://\S+|\[\^?\d+\]|\[[^\]]{1,80}\]\([^)]+\)|\b(?=[0-9a-f]{0,7}\d)(?=[0-9a-f]{0,7}[a-f])[0-9a-f]{8}\b"
                      r"|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
# Words that say why a claim matters to the question: an inference drawn, a consequence, a contrast with the other
# side's case. Calibrated on the sample report (the standard) and thin reports (tests/test_agent_relevance_eval.py).
WHY = re.compile(r"\b(?:why it matters|matters|because|this means|which means|so the|shows? that|suggests?|undermines?|"
                 r"contradicts?|supports?|consistent with|inconsistent with|inference|implies|points? to|rebuts?|"
                 r"against the state|for the defen[cs]e|the state'?s (?:case|theory|claim)|alibi|explains?|"
                 r"significan(?:t|ce)|relevan(?:t|ce)|therefore|so it|indicates?)\b", re.I)


def claims(text: str) -> list[dict]:
    """The report's findings, each with whether it is cited and says why it matters. A finding is a top-level list
    item together with its indented sub-items (a numbered finding and its "Fact." / "Inference." bullets), a body
    paragraph, or a table body row; headings, code and table header rows are not findings, nor is anything under
    eight words. Measured on the sample report (the standard): citing per sentence counted 14% because summary
    bullets point to the cited sections below; per finding it counts what a reader checks."""
    out: list[dict] = []
    cur: list[str] = []

    def close():
        body = " ".join(x.strip() for x in cur).strip()
        cur.clear()
        if len(body.split()) >= 8:
            out.append(dict(text=body, cited=bool(CITATION.search(body)), why=bool(WHY.search(body))))

    fence = False
    for line in str(text or "").splitlines():
        if line.strip().startswith("```"):
            fence = not fence
            close()
            continue
        if fence:
            continue
        if not line.strip() or re.match(r"^\s{0,3}#{1,6}\s", line):
            close()
            continue
        if line.lstrip().startswith("|"):
            close()
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                cur.append(" ".join(cells))
                close()
            continue
        if re.match(r"^(?:[-*+]|\d+[.)])\s", line):
            close()
        cur.append(line)
    close()
    return out


def score_report(text: str, rubric: dict) -> dict:
    """A report against a rubric: facts stated (``all`` terms and one of ``any``), decoys linked (a ``wrong`` pattern
    in a sentence with no ``explained`` pattern), claims cited and saying why, and the rubric's pass mark."""
    t = str(text or "")
    facts = []
    for f in rubric.get("facts", []):
        found = all(expect_hit(w, t) for w in f.get("all") or []) and \
            (not f.get("any") or any(expect_hit(w, t) for w in f["any"]))
        facts.append(dict(id=f["id"], found=found))
    sents = [s for s in _SENTENCE.split(t) if s.strip()]
    decoys = []
    for d in rubric.get("decoys", []):
        bad = any(any(re.search(w, s, re.I | re.U) for w in d.get("wrong") or []) and
                  not any(re.search(e, s, re.I | re.U) for e in d.get("explained") or []) for s in sents)
        decoys.append(dict(id=d["id"], wrong=bad))
    cl = claims(t)
    cited = sum(1 for c in cl if c["cited"])
    why = sum(1 for c in cl if c["why"])
    found = [f["id"] for f in facts if f["found"]]
    out = dict(facts_found=len(found), facts_of=len(facts), found=found,
               missed=[f["id"] for f in facts if not f["found"]],
               decoys_wrong=[d["id"] for d in decoys if d["wrong"]], claims=len(cl),
               cited_share=round(cited / len(cl), 3) if cl else 0.0, why_share=round(why / len(cl), 3) if cl else 0.0,
               words=len(t.split()))
    mark = rubric.get("pass") or {}
    reasons = []
    if out["facts_found"] < mark.get("facts_min", 0):
        reasons.append("states %d of %d facts (pass mark %d)" % (out["facts_found"], out["facts_of"], mark["facts_min"]))
    for fid in mark.get("must_state") or []:
        if fid not in found:
            reasons.append("misses %s" % fid)
    if len(out["decoys_wrong"]) > mark.get("decoys_max", 0):
        reasons.append("links decoy(s) %s" % ", ".join(out["decoys_wrong"]))
    if out["cited_share"] < mark.get("cited_min", 0):
        reasons.append("%.0f%% of claims cited (pass mark %.0f%%)" % (100 * out["cited_share"], 100 * mark["cited_min"]))
    if out["why_share"] < mark.get("why_min", 0):
        reasons.append("%.0f%% of claims say why they matter (pass mark %.0f%%)" % (100 * out["why_share"],
                                                                                 100 * mark["why_min"]))
    out["passed"] = not reasons
    out["fails_because"] = reasons
    return out


def compare_reports(base: list[dict], cand: list[dict], must_state: Iterable[str] = ()) -> dict:
    """Noise-aware comparison of repeated report scores (score_report outputs). Facts found is a loss when the
    candidate's mean is below the baseline's by more than the larger spread; a fact the baseline stated in every run
    and the candidate in none is lost; a decoy the candidate links in every run and the baseline in none is new.
    The cited and say-why shares are pass-mark floors only, never compared: measured 17 Nov, the sample report (the
    standard) cites 35% of its findings and the thin DeepSeek reports 44-50%, so a fuller report can cite a smaller
    share."""
    if not base or not cand:
        return dict(verdict="NO DATA", losses=[], lost_facts=[], new_decoys=[])
    losses = []
    b, c = [s["facts_found"] for s in base], [s["facts_found"] for s in cand]
    band = max(_spread(b), _spread(c))
    if statistics.mean(b) - statistics.mean(c) > band + EPS:
        losses.append(dict(metric="facts_found", base=round(statistics.mean(b), 3), cand=round(statistics.mean(c), 3),
                           noise=round(band, 3)))
    fids = set().union(*[set(s["found"]) | set(s["missed"]) for s in base])
    lost = sorted(f for f in fids if all(f in s["found"] for s in base) and not any(f in s["found"] for s in cand))
    new_decoys = sorted({d for s in cand for d in s["decoys_wrong"]} - {d for s in base for d in s["decoys_wrong"]})
    new_decoys = [d for d in new_decoys if all(d in s["decoys_wrong"] for s in cand)]
    below = [s for s in cand if any("cited" in r or "say why" in r for r in s.get("fails_because") or [])]
    verdict = "FAIL" if losses or lost or new_decoys or below else "PASS"
    return dict(verdict=verdict, losses=losses, lost_facts=lost, new_decoys=new_decoys,
                below_floor=len(below), base_facts=b, cand_facts=c)
