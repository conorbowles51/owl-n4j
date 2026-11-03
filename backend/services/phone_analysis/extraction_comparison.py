"""Approach 12: extraction comparison (docs/cellebrite/05 section 15; unit 05-S15).

For each pair of the case's active extractions: whether they are of one device (15.3 step 1), and when they are,
which records are in both, only in the earlier or only in the later, which changed deleted state, and which changed a
field outside their key (step 4), with the reason a record is in one only where the extractions account for it
(step 5): the other extraction did not select or did not decode that type, or the record is newer than the earlier
extraction's end. Records with no such reason are ``unexplained``.

The gate (15.6) failed on the corpus (the two C1 reports are not shown to be one device, and the second C8 export
is only on the Mac); the approach is built on a synthetic pair by Neil's brief, and the A-C8 control waits for that
copy.

Decisions (05 section 19):

- 19.S15-a Natural keys (15.3 step 3): a message or email is its kind, app, sender identity, time and body digest; a
  call its kind, other party, time, direction and duration; any other top-level record its type and its sorted
  non-volatile text fields. Volatile fields (counters and last-use times, ``VOLATILE``) are left out of keys. Equal
  keys are paired in order of the record's own time, so two copies of one key pair with two. Reverse when 02's
  reviewed mappings give a natural key per type.
- 19.S15-b Earlier and later are read from each report's extraction start time, else the time it was added.
- 19.S15-c ``same_device_indicated`` needs an equal non-empty owner number set and installed-app similarity of at
  least ``app_jaccard`` (default 0.6, 15.3 step 1). Owner numbers are 02's header (tier 1) owner numbers.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import text

from services.phone import identities
from services.phone_analysis import fields as FV

CODE = "extraction_comparison"
VERSION = "12.1"
PARAMETERS = {"app_jaccard": {"default": 0.6, "min": 0.1, "max": 1.0}}
KINDS = ("identity_check", "type_summary", "only_in_earlier", "only_in_later", "state_changed", "field_changed")
SUPPORTS = ("hardware_equal", "owner_equal", "apps_similar", "created_after_first")
UNDERCUTS = ("hardware_differs", "identifiers_contradict", "not_selected_in_other", "decoder_differs", "unexplained",
             "method_differs", "reset_between")
DIRECTION_CODES = SUPPORTS + UNDERCUTS
SIGNALS = [{"code": "header", "label": "Device identifiers in the report header"}]
HARDWARE = ("IMEI", "Serial", "Factory number", "DeviceInfoAndroidID", "DeviceInfoSerial")
VOLATILE = frozenset({"VisitCount", "LastVisited", "LastAccessed", "LastAccessTime", "LastUsedDate", "LastUsed",
                      "Frequency", "TimesContacted", "LastTimeContacted", "UsageCount", "UsagePattern", "TimeModified",
                      "LastModified", "Modification", "LastConnected", "LastConnection", "LastAutoConnection"})
_last = {"counts": {}}


def _d(code, detail, locators=()):
    return {"code": code, "detail": detail, "locators": [str(x) for x in locators]}


def _norm(v):
    return "".join(ch for ch in (v or "") if ch.isalnum()).casefold()


def coverage(conn, case_id) -> dict:
    phones = {}
    for ext, label in FV.active_phones(conn, case_id).items():
        n = sum(len(v) for k, v in identities.header_items(conn, ext).items() if k in HARDWARE)
        phones[ext] = {"label": label, "signals": {"header": {"carries_signal": n > 0, "records": n}}}
    return {"phones": phones, "signals": SIGNALS}


def _parse(items, names):
    """The first header time among ``names`` that reads; a time with no offset is read as UTC."""
    for name in names:
        for v in items.get(name, ()):
            try:
                t = datetime.fromisoformat(v.strip().replace("Z", "+00:00").replace(" ", "T", 1))
            except ValueError:
                continue
            return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    return None


def _when(items, conn, ext):
    return _parse(items, ("DeviceInfoExtractionStartDateTime", "DeviceInfoExtractionEndDateTime")) or conn.execute(
        text("SELECT created_at FROM phone_extractions WHERE id = :e"), {"e": ext}).scalar()


def _end(items):
    return _parse(items, ("DeviceInfoExtractionEndDateTime",))


def _markers(conn, ext):
    owners = {r[0] for r in conn.execute(text(
        "SELECT identity_key FROM pv_owner_candidate WHERE extraction_id = :e AND tier = 1 AND identity_key IS NOT "
        "NULL"), {"e": ext})}
    apps = {r[0] for r in conn.execute(text(
        "SELECT DISTINCT lower(value) FROM pv_text WHERE extraction_id = :e AND model_type = 'InstalledApplication' AND "
        "field_path = 'Identifier'"), {"e": ext})}
    return owners, apps


def identity(conn, x, y, params) -> dict:
    """15.3 step 1: ``{"verdict", "equal", "different", "owners_equal", "app_jaccard", "contradiction"}``."""
    ix, iy = identities.header_items(conn, x), identities.header_items(conn, y)
    equal, different = [], []
    for name in HARDWARE:
        a, b = {_norm(v) for v in ix.get(name, ()) if _norm(v)}, {_norm(v) for v in iy.get(name, ()) if _norm(v)}
        if a and b:
            (equal if a & b else different).append(name)
    ox, ax = _markers(conn, x)
    oy, ay = _markers(conn, y)
    jac = len(ax & ay) / len(ax | ay) if ax | ay else None
    owners_equal = bool(ox) and ox == oy
    contradiction = bool(equal and different)
    if contradiction:
        verdict = "undetermined"
    elif equal:
        verdict = "same_device_established"
    elif different:
        verdict = "different_device"
    elif owners_equal and jac is not None and jac >= params["app_jaccard"]:
        verdict = "same_device_indicated"
    else:
        verdict = "undetermined"
    return {"verdict": verdict, "equal": equal, "different": different, "owners_equal": owners_equal,
            "app_jaccard": round(jac, 3) if jac is not None else None, "contradiction": contradiction,
            "items": (ix, iy)}


def _keys(conn, ext):
    """{key: [(instant, record_uid, model_type, deleted_state, status)]} of one extraction's top-level records."""
    out = defaultdict(list)
    seen = set()
    for r in conn.execute(text(
            "SELECT DISTINCT ON (e.record_uid) e.record_uid::text AS uid, e.kind, e.app, e.direction, e.sort_instant, "
            "e.body, e.call_duration_s, e.status, e.deleted_state, e.model_type, (SELECT string_agg(coalesce("
            "p.identity_key, ''), ',' ORDER BY p.identity_key) FROM pv_comm_party p WHERE p.event_uid = e.event_uid AND "
            "NOT coalesce(p.is_phone_owner, false)) AS others, (SELECT min(p.identity_key) FROM pv_comm_party p WHERE "
            "p.event_uid = e.event_uid AND (p.role IN ('sender', 'caller', 'From') OR p.implied_role = 'sender')) AS "
            "sender FROM pv_comm_event e WHERE e.extraction_id = :e ORDER BY e.record_uid, e.event_uid"),
            {"e": ext}).mappings():
        seen.add(r["uid"])
        at = r["sort_instant"].isoformat() if r["sort_instant"] else ""
        if r["kind"] == "call":
            key = ("call", r["others"] or "", at, r["direction"] or "", str(r["call_duration_s"] or ""))
        else:
            key = (r["kind"], r["app"] or "", r["sender"] or r["others"] or "", at,
                   hashlib.sha256((r["body"] or "").encode()).hexdigest()[:16])
        out[key].append((r["sort_instant"], r["uid"], r["model_type"], r["deleted_state"], r["status"]))
    fields = defaultdict(list)
    for r in conn.execute(text(
            "SELECT t.record_uid::text, t.field_path, t.value FROM pv_text t JOIN pv_record p ON p.record_uid = "
            "t.record_uid WHERE t.extraction_id = :e AND p.parent_record_uid IS NULL AND NOT coalesce(t.is_sensitive, "
            "false)"), {"e": ext}):
        if r[0] not in seen and r[1].split(".")[-1].split("[")[0] not in VOLATILE:
            fields[r[0]].append((r[1], r[2] or ""))
    for r in conn.execute(text(
            "SELECT record_uid::text, model_type, deleted_state, first_instant FROM pv_record WHERE extraction_id = :e "
            "AND parent_record_uid IS NULL"), {"e": ext}):
        if r[0] in seen:
            continue
        key = ("record", r[1], hashlib.sha256(repr(sorted(fields.get(r[0], ()))).encode()).hexdigest()[:24])
        out[key].append((r[3], r[0], r[1], r[2], None))
    for v in out.values():
        v.sort(key=lambda e: (e[0] is None, e[0] or datetime.min.replace(tzinfo=timezone.utc), e[1]))
    return out


def _deleted(state):
    return state in ("Deleted", "Trash")


def analyse(conn, case_id, params, ctx=None) -> tuple:
    from services.phone.coverage import selection
    counts = defaultdict(int)
    phones = FV.active_phones(conn, case_id)
    exts = list(phones)
    out = []
    for i, x in enumerate(exts):
        for y in exts[i + 1:]:
            if ctx is not None and ctx.cancelled():
                return out, dict(counts)
            idc = identity(conn, x, y, params)
            ix, iy = idc.pop("items")
            wx, wy = _when(ix, conn, x), _when(iy, conn, y)
            early, late = (x, y) if (wx, x) <= (wy, y) else (y, x)
            ie, il = (ix, iy) if early == x else (iy, ix)
            pair = [phones[early], phones[late]]
            counts["pairs"] += 1
            counts[idc["verdict"]] += 1
            supports, undercuts = [], []
            if idc["equal"]:
                supports.append(_d("hardware_equal", "Equal in both: %s." % ", ".join(idc["equal"])))
            if idc["different"]:
                undercuts.append(_d("hardware_differs", "Present in both and different: %s." %
                                    ", ".join(idc["different"])))
            if idc["contradiction"]:
                undercuts.append(_d("identifiers_contradict", "Some device identifiers are equal and others differ, "
                                    "so the comparison cannot say."))
            if idc["owners_equal"]:
                supports.append(_d("owner_equal", "The same owner numbers."))
            if idc["app_jaccard"] is not None and idc["app_jaccard"] >= params["app_jaccard"]:
                supports.append(_d("apps_similar", "Installed apps are %.0f percent the same." %
                                   (100 * idc["app_jaccard"])))
            anchor = "pair:%s|%s" % (early, late)
            out.append({"kind": "identity_check", "strength": idc["verdict"],
                        "measures": {"phones": pair, "earlier": early, "later": late, **idc},
                        "directions": {"supports": supports, "undercuts": undercuts},
                        "period_start": None, "period_end": None,
                        "records": [{"extraction_id": early, "record_uid": None, "field_path": anchor,
                                     "role": "earlier"},
                                    {"extraction_id": late, "record_uid": None, "field_path": anchor, "role": "later"}]})
            if idc["verdict"] not in ("same_device_established", "same_device_indicated"):
                continue
            ke, kl = _keys(conn, early), _keys(conn, late)
            types_e = {v[2] for vs in ke.values() for v in vs}
            types_l = {v[2] for vs in kl.values() for v in vs}
            sel_e, sel_l = selection(conn, early), selection(conn, late)
            pa_e = set(ie.get("UFED_PA_Version", ())) or None
            pa_l = set(il.get("UFED_PA_Version", ())) or None
            end_e = _end(ie) or wl_fallback(ke)
            summary = defaultdict(lambda: defaultdict(int))

            def reason(rec, other_types, other_sel, later_side):
                mt, at = rec[2], rec[0]
                if later_side and end_e and at and at > end_e:
                    return "created_after_first"
                if mt not in other_types and str(other_sel.get("IsSelectiveExtraction")).lower() == "true":
                    return "not_selected_in_other"
                if mt not in other_types and pa_e and pa_l and pa_e != pa_l:
                    return "decoder_differs"
                return "unexplained"
            for key in sorted(set(ke) | set(kl), key=repr):
                a, b = ke.get(key, []), kl.get(key, [])
                for j in range(max(len(a), len(b))):
                    ra = a[j] if j < len(a) else None
                    rb = b[j] if j < len(b) else None
                    mt = (ra or rb)[2]
                    if ra and rb:
                        summary[mt]["present_in_both"] += 1
                        if _deleted(ra[3]) != _deleted(rb[3]):
                            kind, words = "state_changed", "%s in the earlier extraction, %s in the later." % (
                                ra[3] or "Intact", rb[3] or "Intact")
                        elif (ra[4] or "") != (rb[4] or ""):
                            kind, words = "field_changed", "Status %s in the earlier, %s in the later." % (
                                ra[4] or "not recorded", rb[4] or "not recorded")
                        else:
                            continue
                        summary[mt][kind] += 1
                        counts[kind] += 1
                        out.append({"kind": kind, "strength": "recorded",
                                    "measures": {"phones": pair, "record_type": mt, "earlier_state": ra[3],
                                                 "later_state": rb[3], "earlier_status": ra[4],
                                                 "later_status": rb[4], "instant": ra[0] or rb[0]},
                                    "directions": {"supports": [_d(kind, words, [ra[1], rb[1]])],
                                                   "undercuts": [_d("method_differs", "Different extraction methods "
                                                                    "recover different data.")]},
                                    "period_start": ra[0] or rb[0], "period_end": ra[0] or rb[0],
                                    "records": [{"extraction_id": early, "record_uid": ra[1], "field_path": None,
                                                 "role": "earlier"},
                                                {"extraction_id": late, "record_uid": rb[1], "field_path": None,
                                                 "role": "later"}]})
                        continue
                    later_side = ra is None
                    rec = rb if later_side else ra
                    kind = "only_in_later" if later_side else "only_in_earlier"
                    why = reason(rec, types_e if later_side else types_l, sel_e if later_side else sel_l, later_side)
                    summary[mt][kind] += 1
                    counts[kind] += 1
                    counts[kind + ":" + why] += 1
                    words = {"created_after_first": "Newer than the earlier extraction's end: created after the first "
                                                    "extraction.",
                             "not_selected_in_other": "The other extraction was selective and holds no record of "
                                                      "this type.",
                             "decoder_differs": "The other report was produced by a different decoder version and "
                                                "holds no record of this type.",
                             "unexplained": "Neither extraction's selection, decoder or times account for it."}[why]
                    code = why if why != "created_after_first" else "created_after_first"
                    d = _d(code, words, [rec[1]])
                    out.append({"kind": kind, "strength": why,
                                "measures": {"phones": pair, "record_type": mt, "reason": why,
                                             "deleted_state": rec[3], "instant": rec[0]},
                                "directions": {"supports": [d] if why == "created_after_first" else [],
                                               "undercuts": [] if why == "created_after_first" else [d]},
                                "period_start": rec[0], "period_end": rec[0],
                                "records": [{"extraction_id": late if later_side else early, "record_uid": rec[1],
                                             "field_path": None, "role": kind}]})
            for mt, c in sorted(summary.items()):
                out.append({"kind": "type_summary", "strength": "counted",
                            "measures": {"phones": pair, "record_type": mt, **{k: c.get(k, 0) for k in (
                                "present_in_both", "only_in_earlier", "only_in_later", "state_changed",
                                "field_changed")}},
                            "directions": {"supports": [], "undercuts": []}, "period_start": None, "period_end": None,
                            "records": [{"extraction_id": early, "record_uid": None,
                                         "field_path": "%s|type:%s" % (anchor, mt), "role": "earlier"}]})
    return out, dict(counts)


def wl_fallback(keys):
    """The earlier extraction's last record time, when its header gives no end."""
    times = [v[0] for vs in keys.values() for v in vs if v[0]]
    return max(times) if times else None


def diff_counts(conn, case_id, x, y, params=None) -> dict:
    """The diff-kind counts for one pair (J-16 equality reads these): present_in_both, only_in_earlier,
    only_in_later, state_changed, field_changed."""
    params = params or {k: v["default"] for k, v in PARAMETERS.items()}
    res, _ = analyse(conn, case_id, params)
    out = defaultdict(int)
    for r in res:
        if r["kind"] == "type_summary" and set(r["measures"]["phones"]) == {FV.active_phones(conn, case_id)[x],
                                                                             FV.active_phones(conn, case_id)[y]}:
            for k in ("present_in_both", "only_in_earlier", "only_in_later", "state_changed", "field_changed"):
                out[k] += r["measures"][k]
    return dict(out)


def run(conn, case_id, params, ctx) -> list:
    results, counts = analyse(conn, case_id, params, ctx)
    _last["counts"] = counts
    return results


def last_counts() -> dict:
    return _last["counts"]
