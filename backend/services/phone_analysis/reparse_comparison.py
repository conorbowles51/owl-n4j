"""Independent re-parse, compared with the report (05 section 17.3 points 4 and 5; approach code ``reparse_comparison``).

For each phone with a completed re-parse run (``phone_reparse_runs``, written by the evidence engine), the rows the
pinned tool read (``phone_reparse_rows``) are compared with the report's records of the same kind:

- sms, calls and WhatsApp messages: key (other party's identity, instant to the second, and the body for messages or
  direction and duration for calls), approach 12's natural key for these types (15.3 step 3);
- contacts: key (the sorted identities on the card), with the name compared;
- web history: key (URL, instant to the second), over the report's records of the apps the tool read (its rows'
  ``browser_name``); when the tool has one row per URL (ALEAPP's Chrome history: the URL's last visit and visit
  count), the report's visits are taken one item per URL with the latest visit, so an earlier visit to a URL the tool
  read is not "only in the report". Measured on P12: 1,246 of the report's 1,789 web history records were another
  app's, and its 509 Chrome visits were 301 URLs.

Each kind: exact key, one to one, is ``present_in_both``; same party and content at another instant is
``time_differs`` (both instants, both original strings, the difference in hours); same party and instant with
other content is ``value_differs``; what is left is ``only_in_reparse`` (a record the report did not decode, or a
deleted row the tool read) or ``only_in_report``. A kind whose totals differ also gets one ``count_differs``.

A kind is compared only when the tool wrote output for it on that phone (the run's ``artefact_counts.mapped``). When it
did not, the report's records of that kind are one ``not_compared`` result with the reason, never "only in the
report": measured on P12, the pinned ALEAPP reads WhatsApp only under ``com.whatsapp``, not WhatsApp Business.

The tool's rows are never merged into a captured record: a result names the report record and the tool's row
(run, artefact, row) side by side, and the screen shows the tool's row as "read by <tool> <version>".
"""
from __future__ import annotations

import hashlib
from collections import defaultdict

from sqlalchemy import text

CODE = "reparse_comparison"
VERSION = "17.3-3"
PARAMETERS = {
    "time_window_hours": {"default": 26, "min": 0, "max": 48},
}
KINDS = ("count_differs", "only_in_reparse", "only_in_report", "time_differs", "value_differs", "present_in_both",
         "not_compared")
KIND_WORDS = {"sms": "text messages", "call": "calls", "whatsapp_message": "WhatsApp messages", "contact": "contacts",
              "web_history": "web history"}
COMPARED = ("sms", "call", "whatsapp_message", "contact", "web_history")
TOOL_NAMES = {"aleapp": "ALEAPP", "ileapp": "iLEAPP"}
_last = {}


def _h(s) -> str:
    return hashlib.sha256((s or "").strip().encode("utf-8")).hexdigest()[:16]


def _sec(t):
    return int(t.timestamp()) if t is not None else None


def _identity(raw):
    from services.phone import identifiers
    i = identifiers.classify(raw)
    return i.identity_key if i else ("raw:" + str(raw).strip().casefold() if raw not in (None, "") else None)


def latest_runs(conn, case_id) -> list:
    """The newest completed re-parse run of each active phone of the case."""
    return [dict(r._mapping) for r in conn.execute(text(
        "SELECT DISTINCT ON (r.extraction_id) r.id::text AS run_id, r.extraction_id::text AS extraction_id, r.tool, "
        "r.tool_version, r.tool_commit, r.mapping_version, r.output_manifest_sha256, r.artefact_counts->'mapped' AS "
        "mapped FROM phone_reparse_runs r JOIN "
        "phone_extractions e ON e.id = r.extraction_id AND e.standing = 'active' WHERE r.case_id = :c AND r.status = "
        "'completed' ORDER BY r.extraction_id, r.finished_at DESC"), {"c": str(case_id)})]


def input_manifest(conn, case_id) -> dict:
    return {"reparse_runs": [{"run_id": r["run_id"], "output": r["output_manifest_sha256"]}
                             for r in latest_runs(conn, case_id)]}


SIGNALS = [{"code": "reparsed", "label": "Re-parsed records (an independent tool's reading)"}]


def coverage(conn, case_id) -> dict:
    """Per phone: whether a completed re-parse exists, with the tool and version (3.6 format)."""
    from services.phone import readings
    runs = {r["extraction_id"]: r for r in latest_runs(conn, case_id)}
    labels = readings.phone_labels(conn, case_id)
    phones = {}
    for (ext,) in conn.execute(text("SELECT id::text FROM phone_extractions WHERE case_id = :c AND standing = "
                                    "'active' ORDER BY id"), {"c": str(case_id)}):
        r = runs.get(ext)
        phones[ext] = {"label": labels.get(ext, "A phone"), "signals": {"reparsed": {
            "carries_signal": r is not None,
            "tool": "%s %s" % (TOOL_NAMES[r["tool"]], r["tool_version"]) if r else None}}}
    return {"phones": phones, "signals": SIGNALS}


# --- the report's side --------------------------------------------------------------------------------------------

def _comm(conn, ext, kind):
    from services.phone.compare import family
    if kind == "whatsapp_message":
        cond, ek = "e.kind = 'message' AND lower(coalesce(e.app, '')) LIKE 'whatsapp%'", "message"
    else:
        cond, ek = "e.kind = :k", "message" if kind == "sms" else "call"
    rows = conn.execute(text(
        "SELECT e.record_uid::text AS record_uid, e.app, e.sort_instant, e.body, e.direction, e.call_duration_s, "
        "(SELECT p.identity_key FROM pv_comm_party p WHERE p.event_uid = e.event_uid AND p.is_phone_owner IS NOT TRUE AND "
        " p.identity_key IS NOT NULL ORDER BY p.role, p.identity_key LIMIT 1) AS party, "
        "(SELECT t.original_text FROM pv_time t WHERE t.record_uid = e.record_uid AND t.instant = e.sort_instant "
        " LIMIT 1) AS instant_text FROM pv_comm_event e WHERE e.extraction_id = :e AND " + cond),
        {"e": ext, "k": ek}).fetchall()
    out = []
    for r in rows:
        if kind == "sms" and family("message", r.app) != "sms":
            continue
        if kind == "call" and family("call", r.app) != "phone":
            continue
        out.append({"record_uid": r.record_uid, "party": r.party, "instant": r.sort_instant,
                    "instant_text": r.instant_text, "content": _content(kind, r.body, r.direction, r.call_duration_s),
                    "shown": {"body": r.body, "direction": r.direction, "duration_s": r.call_duration_s}})
    return out


def _content(kind, body, direction, duration):
    if kind == "call":
        return "%s|%s" % (_direction(direction), "" if duration in (None, "") else int(float(duration)))
    return _h(body)


def _direction(v) -> str:
    s = str(v if v is not None else "").strip().casefold()
    if s in ("1", "incoming", "received", "in", "false", "0") or s.startswith("incoming") or s.startswith("received"):
        return "incoming"
    if s in ("2", "outgoing", "sent", "out", "true") or s.startswith("outgoing") or s.startswith("sent"):
        return "outgoing"
    if s in ("3", "missed") or s.startswith("missed"):
        return "missed"
    return s


def _contacts(conn, ext):
    by = defaultdict(lambda: {"ids": set(), "name": None})
    for r in conn.execute(text(
            "SELECT card_record_uid::text AS card, identity_key, name_alongside FROM pv_identity_sighting WHERE "
            "extraction_id = :e AND context = 'listed_on_card' AND card_record_uid IS NOT NULL"), {"e": ext}):
        c = by[r.card]
        if r.identity_key:
            c["ids"].add(r.identity_key)
        c["name"] = c["name"] or r.name_alongside
    return [{"record_uid": k, "party": "|".join(sorted(v["ids"])), "instant": None, "instant_text": None,
             "content": _h((v["name"] or "").casefold()), "shown": {"name": v["name"]}}
            for k, v in by.items() if v["ids"]]


def _web(conn, ext):
    rows = defaultdict(dict)
    for r in conn.execute(text(
            "SELECT t.record_uid::text AS uid, t.field_path, t.value FROM pv_text t WHERE t.extraction_id = :e AND "
            "t.model_type = 'VisitedPage' AND t.field_path IN ('Url', 'Title', 'Source')"), {"e": ext}):
        rows[r.uid][r.field_path] = r.value
    times = {r.uid: (r.instant, r.original_text) for r in conn.execute(text(
        "SELECT DISTINCT ON (t.record_uid) t.record_uid::text AS uid, t.instant, t.original_text FROM pv_time t JOIN "
        "pv_record p ON p.record_uid = t.record_uid WHERE t.extraction_id = :e AND p.model_type = 'VisitedPage' "
        "ORDER BY t.record_uid, (t.field_path = 'LastVisited') DESC"), {"e": ext})}
    return [{"record_uid": u, "party": (v.get("Url") or "").strip(), "instant": times.get(u, (None, None))[0],
             "instant_text": times.get(u, (None, None))[1], "content": "", "app": (v.get("Source") or "").strip(),
             "shown": {"url": v.get("Url"), "title": v.get("Title")}}
            for u, v in rows.items() if v.get("Url")]


def _app(name) -> str:
    return " ".join(str(name or "").split()).casefold()


def web_scope(rep: list, tool: list):
    """The report's web history records the tool could have read, and the rest counted by app.

    Compared: records whose app is one the tool's rows name (``browser_name``, else the mapping's app). When the
    tool's rows are one per (app, URL), the report's records are taken one per (app, URL), the latest visit standing
    for the URL with the number of visits shown; otherwise each record stands alone."""
    apps = {_app(t.get("browser") or t.get("app")) for t in tool} - {""}
    keep, other = [], defaultdict(int)
    for r in rep:
        if _app(r.get("app")) in apps:
            keep.append(r)
        else:
            other[r.get("app") or "no app named"] += 1
    keys = [(_app(t.get("browser") or t.get("app")), t["party"]) for t in tool]
    if len(set(keys)) != len(keys):
        return keep, dict(other)
    latest = {}
    for r in keep:
        k = (_app(r["app"]), r["party"])
        r = dict(r, visits=1)
        cur = latest.get(k)
        if cur is None:
            latest[k] = r
        else:
            newer = r if (_sec(r["instant"]) or float("-inf")) > (_sec(cur["instant"]) or float("-inf")) else cur
            latest[k] = dict(newer, visits=cur["visits"] + 1,
                             shown=dict(newer["shown"], visits=cur["visits"] + 1))
    return list(latest.values()), dict(other)


def report_side(conn, ext, kind):
    if kind in ("sms", "call", "whatsapp_message"):
        return _comm(conn, ext, kind)
    if kind == "contact":
        return _contacts(conn, ext)
    return _web(conn, ext)


# --- the tool's side ----------------------------------------------------------------------------------------------

def tool_side(conn, run_id, kind):
    out = []
    for r in conn.execute(text(
            "SELECT artefact, row_index, instant, instant_text, values FROM phone_reparse_rows WHERE run_id = :r AND "
            "kind = :k ORDER BY artefact, row_index"), {"r": run_id, "k": kind}):
        roles = (r.values or {}).get("roles") or {}
        if kind == "contact":
            ids = sorted({i for i in (_identity(x.strip()) for x in str(roles.get("identifiers") or "")
                                      .replace(";", ",").split(",") if x.strip()) if i})
            party, content = "|".join(ids), _h(str(roles.get("name") or "").casefold())
        elif kind == "web_history":
            party, content = str(roles.get("url") or "").strip(), ""
            browser = str(((r.values or {}).get("row") or {}).get("browser_name") or "").strip()
        else:
            party = _identity(roles.get("party"))
            content = _content(kind, roles.get("body"), roles.get("direction"), roles.get("duration"))
        if kind != "web_history":
            browser = ""
        out.append({"locator": "reparse:%s:%s:%s" % (run_id, r.artefact, r.row_index), "artefact": r.artefact,
                    "browser": browser, "app": str((r.values or {}).get("app") or ""),
                    "row_index": r.row_index, "party": party, "instant": r.instant, "instant_text": r.instant_text,
                    "content": content, "shown": roles})
    return out


# --- matching -----------------------------------------------------------------------------------------------------

def compare(report: list, tool: list, window_hours: float) -> dict:
    """Pairs and leftovers, each item once: {present, time, value, only_report, only_tool}."""
    left_r, left_t = list(range(len(report))), list(range(len(tool)))
    out = {"present": [], "time": [], "value": []}

    def take(keyf, kind, near=None):
        nonlocal left_r, left_t
        idx = defaultdict(list)
        for j in left_t:
            idx[keyf(tool[j])].append(j)
        used_t, keep_r = set(), []
        for i in left_r:
            cands = [j for j in idx.get(keyf(report[i]), []) if j not in used_t]
            if near is not None:
                cands = [j for j in cands if near(report[i], tool[j])]
                cands.sort(key=lambda j: abs((_sec(tool[j]["instant"]) or 0) - (_sec(report[i]["instant"]) or 0)))
            if cands:
                used_t.add(cands[0])
                out[kind].append((i, cands[0]))
            else:
                keep_r.append(i)
        left_r, left_t = keep_r, [j for j in left_t if j not in used_t]

    take(lambda x: (x["party"], _sec(x["instant"]), x["content"]), "present")
    window = window_hours * 3600

    def near(a, b):
        return (a["instant"] is not None and b["instant"] is not None and
                abs(_sec(a["instant"]) - _sec(b["instant"])) <= window)
    take(lambda x: (x["party"], x["content"]), "time", near)
    take(lambda x: (x["party"], _sec(x["instant"])), "value")
    out["only_report"], out["only_tool"] = left_r, left_t
    return out


def _rec(ext, uid, role):
    return {"extraction_id": ext, "record_uid": uid, "field_path": None, "role": role}


def _tool_rec(ext, t):
    return {"extraction_id": ext, "record_uid": None, "field_path": t["locator"], "role": "reparse_row"}


def _iso(t):
    return t.isoformat() if t is not None else None


def run(conn, case_id, params, ctx) -> list:
    results, counts = [], {"phones": 0, "by_kind": {}}
    runs = latest_runs(conn, case_id)
    for n, rn in enumerate(runs):
        ext, run_id = rn["extraction_id"], rn["run_id"]
        read_by = "read by %s %s" % (TOOL_NAMES[rn["tool"]], rn["tool_version"])
        tool_meta = {"run_id": run_id, "tool": TOOL_NAMES[rn["tool"]], "version": rn["tool_version"],
                     "commit": rn["tool_commit"], "mapping_version": rn["mapping_version"], "read_by": read_by}
        counts["phones"] += 1
        wrote = set((rn.get("mapped") or {}).keys())
        for kind in COMPARED:
            if kind not in wrote:
                rep = report_side(conn, ext, kind)
                if rep:
                    c = counts["by_kind"].setdefault(kind, defaultdict(int))
                    c["report"] += len(rep)
                    c["not_compared"] += len(rep)
                    results.append({"kind": "not_compared", "strength": "observation",
                                    "measures": dict(tool_meta, compared=kind, report_count=len(rep), reason=(
                                        "%s %s wrote no %s for this phone, so the report's %s %s are not compared."
                                        % (tool_meta["tool"], tool_meta["version"], KIND_WORDS[kind],
                                           format(len(rep), ","), KIND_WORDS[kind]))),
                                    "directions": {}, "records": [{"extraction_id": ext, "record_uid": None,
                                                                   "field_path": "not_compared:%s:%s" % (run_id, kind),
                                                                   "role": "count"}]})
                continue
            rep, tool = report_side(conn, ext, kind), tool_side(conn, run_id, kind)
            if kind == "web_history":
                all_rep = len(rep)
                rep, other = web_scope(rep, tool)
                if other:
                    n_other = sum(other.values())
                    c = counts["by_kind"].setdefault(kind, defaultdict(int))
                    c["not_compared"] += n_other
                    read = sorted({t.get("browser") or t.get("app") for t in tool} - {""})
                    results.append({"kind": "not_compared", "strength": "observation",
                                    "measures": dict(tool_meta, compared=kind, report_count=n_other,
                                                     report_total=all_rep, by_app=other, reason=(
                                        "%s %s read web history from %s only, so the report's %s web history records "
                                        "from other apps (%s) are not compared." % (
                                            tool_meta["tool"], tool_meta["version"], ", ".join(read) or "no app",
                                            format(n_other, ","), ", ".join(
                                                "%s %s" % (a, format(v, ",")) for a, v in
                                                sorted(other.items(), key=lambda x: (-x[1], x[0])))))),
                                    "directions": {}, "records": [{"extraction_id": ext, "record_uid": None,
                                                                   "field_path": "not_compared:%s:%s" % (run_id, kind),
                                                                   "role": "count"}]})
            if not rep and not tool:
                continue
            m = compare(rep, tool, params["time_window_hours"])
            c = counts["by_kind"].setdefault(kind, defaultdict(int))
            c["report"] += len(rep)
            c["reparse"] += len(tool)
            if len(rep) != len(tool):
                results.append({"kind": "count_differs", "strength": "observation",
                                "measures": dict(tool_meta, compared=kind, report_count=len(rep),
                                                 reparse_count=len(tool), **_unit(rep)),
                                "directions": {}, "records": [{"extraction_id": ext, "record_uid": None,
                                                               "field_path": "count:%s:%s" % (run_id, kind),
                                                               "role": "count"}]})
            for i, j in m["present"]:
                results.append(_pair("present_in_both", kind, ext, rep[i], tool[j], tool_meta))
            for i, j in m["time"]:
                r = _pair("time_differs", kind, ext, rep[i], tool[j], tool_meta)
                hours = round((_sec(tool[j]["instant"]) - _sec(rep[i]["instant"])) / 3600.0, 4)
                r["measures"]["difference_hours"] = hours
                r["directions"] = {"supports": [], "undercuts": [
                    {"code": "zone_conversion", "detail": "The difference is a whole number of hours.", "locators": []}]
                    if hours and float(hours).is_integer() else []}
                results.append(r)
            for i, j in m["value"]:
                results.append(_pair("value_differs", kind, ext, rep[i], tool[j], tool_meta))
            for i in m["only_report"]:
                results.append({"kind": "only_in_report", "strength": "observation",
                                "measures": dict(tool_meta, compared=kind, report=_side(rep[i])),
                                "directions": {}, "period_start": rep[i]["instant"], "period_end": rep[i]["instant"],
                                "records": [_rec(ext, rep[i]["record_uid"], "report_record"),
                                            {"extraction_id": ext, "record_uid": None,
                                             "field_path": "run:%s" % run_id, "role": "reparse_run"}]})
            for j in m["only_tool"]:
                results.append({"kind": "only_in_reparse", "strength": "observation",
                                "measures": dict(tool_meta, compared=kind, reparse=_side(tool[j])),
                                "directions": {"supports": [], "undercuts": [
                                    {"code": "not_decoded_or_deleted_row", "detail": "A record the report did not "
                                     "decode, or a deleted row the tool read.", "locators": []}]},
                                "period_start": tool[j]["instant"], "period_end": tool[j]["instant"],
                                "records": [_tool_rec(ext, tool[j])]})
            for k, v in (("present_in_both", m["present"]), ("time_differs", m["time"]), ("value_differs", m["value"]),
                         ("only_in_report", m["only_report"]), ("only_in_reparse", m["only_tool"])):
                c[k] += len(v)
        if ctx is not None:
            ctx.progress(n + 1, len(runs), phone=ext)
    _last.clear()
    _last.update({"phones": counts["phones"],
                  "compared": {k: dict(v) for k, v in counts["by_kind"].items()}})
    return results


def _unit(rep) -> dict:
    """Web history taken one item per URL says so, with the report's visits behind those URLs."""
    if rep and all("visits" in r for r in rep):
        return {"report_unit": "url", "report_records": sum(r["visits"] for r in rep)}
    return {}


def _side(x) -> dict:
    out = {"instant": _iso(x["instant"]), "original": x["instant_text"], "shown": x["shown"]}
    if "locator" in x:
        out.update(artefact=x["artefact"], row_index=x["row_index"])
    else:
        out["record_uid"] = x["record_uid"]
    return out


def _pair(kind_out, kind, ext, rep, tool, meta) -> dict:
    return {"kind": kind_out, "strength": "observation",
            "measures": dict(meta, compared=kind, report=_side(rep), reparse=_side(tool)),
            "directions": {}, "period_start": rep["instant"], "period_end": rep["instant"],
            "records": [_rec(ext, rep["record_uid"], "report_record"), _tool_rec(ext, tool)]}


def last_counts() -> dict:
    return dict(_last)


def reparse_for_record(conn, case_id, record_uid) -> list:
    """The tool's rows paired with one report record by the newest completed comparison, each labelled
    "read by <tool> <version>"; shown beside the report's record, never in place of it."""
    return [{"kind": r.kind, "read_by": r.measures.get("read_by"), "artefact": (r.measures.get("reparse") or {})
             .get("artefact"), "reparse": r.measures.get("reparse"), "difference_hours": r.measures.get(
             "difference_hours"), "compared": r.measures.get("compared")}
            for r in conn.execute(text(
                "SELECT res.kind, res.measures FROM phone_analysis_result_records rr JOIN phone_analysis_results res ON "
                "res.id = rr.result_id JOIN phone_analysis_runs run ON run.id = res.run_id AND run.status = 'completed' "
                "WHERE rr.record_uid = CAST(:u AS uuid) AND res.case_id = :c AND run.approach = :a "
                "AND res.kind IN ('present_in_both', 'time_differs', 'value_differs') ORDER BY res.kind"),
                {"u": str(record_uid), "c": str(case_id), "a": CODE})]
