"""Approach 7: what was typed, even if deleted (docs/cellebrite/05 section 10; unit 05-S10).

Per phone, the keyboard's learned words (DictionaryWord.Word) and autofill values (Autofill.Value) that match the
case vocabulary (``vocabulary.py``), and for each whether the same term occurs in the phone's own messages, emails,
notes, searches or calendar entries (10.3 step 3). Both fields are sensitive (05 section 3.8): the comparison runs
here, and a result carries only the kind of term matched, the masked value and the record locator. The value is
seen through the record's Reveal, which is logged. No value or matched term is stored in a result, sent to a model
or indexed (10.8 test 3).

Gate (10.6) passed: 37 vocabulary hits per phone on the C9 phones (M-7a, typed_words m7.2).

Decisions (05 section 19):

- 19.S10-a Matching: word tokens of 4 or more characters for names; a digit run equal to or ending with an account
  ending; a run of 7 or more digits for phone numbers (shorter runs matched any web address). Reverse if a
  measured sample shows 4 to 6 digit typed numbers that are real hits.
- 19.S10-b A hit is ``typed_not_in_extraction`` when no matched term occurs in the phone's own messages, emails,
  notes, searches or calendar; otherwise ``typed_and_present`` with up to 20 of those records linked and the full
  count stated. Absence can be selection rather than deletion, stated on every such result.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import text

from services.phone_analysis import fields as FV
from services.phone_analysis import vocabulary as V

CODE = "typed_words"
VERSION = "7.2"  # 7.2: the vocabulary takes investigator terms (case terms and keyword lists)
PARAMETERS: dict = {}
KINDS = ("typed_not_in_extraction", "typed_and_present")
SUPPORTS = ("vocabulary_match", "not_in_extraction", "present_elsewhere", "time_recorded")
UNDERCUTS = ("no_time_recorded", "learned_from_any_typing", "synced_dictionary", "frequency_not_period",
             "absence_may_be_selection", "vocabulary_partial", "deleted_or_carved")
DIRECTION_CODES = SUPPORTS + UNDERCUTS
SIGNALS = [
    {"code": "dictionary", "label": "Keyboard learned words"},
    {"code": "autofill", "label": "Autofill values"},
]
FIELD = {"DictionaryWord": "Word", "Autofill": "Value"}
LINK_LIMIT = 20
_last = {"counts": {}}


def _d(code, detail, locators=()):
    return {"code": code, "detail": detail, "locators": [str(x) for x in locators]}


def input_manifest(conn, case_id) -> dict:
    from services.phone_analysis.money_signals import ledger_revision
    return {"ledger": ledger_revision(conn, case_id), "investigator_terms": V.terms_revision(conn, case_id),
            "identities": conn.execute(text(
        "SELECT md5(coalesce(string_agg(x, ',' ORDER BY x), '')) FROM (SELECT DISTINCT name AS x FROM pv_identity_name "
        "WHERE case_id = :c UNION SELECT DISTINCT value_normalised FROM pv_identity WHERE case_id = :c) s"),
        {"c": str(case_id)}).scalar()}


def coverage(conn, case_id) -> dict:
    counts = defaultdict(dict)
    for r in conn.execute(text(
            "SELECT extraction_id, model_type, count(*) FROM pv_record WHERE case_id = :c AND model_type IN "
            "('DictionaryWord', 'Autofill') GROUP BY 1, 2"), {"c": str(case_id)}):
        counts[str(r[0])][r[1]] = int(r[2])
    phones = {}
    for ext, label in FV.active_phones(conn, case_id).items():
        d, a = counts[ext].get("DictionaryWord", 0), counts[ext].get("Autofill", 0)
        phones[ext] = {"label": label, "signals": {"dictionary": {"carries_signal": d > 0, "records": d},
                                                   "autofill": {"carries_signal": a > 0, "records": a}}}
    return {"phones": phones, "signals": SIGNALS}


def _typed(conn, ext):
    """``{record_uid: {"model_type", "values": [value...]}}`` of the phone's typed values (sensitive; never returned)."""
    out = {}
    for r in conn.execute(text(
            "SELECT record_uid, model_type, value FROM pv_text WHERE extraction_id = :e AND ((model_type = "
            "'DictionaryWord' AND field_path = 'Word') OR (model_type = 'Autofill' AND field_path = 'Value')) ORDER BY "
            "record_uid, value_index"), {"e": ext}):
        out.setdefault(str(r.record_uid), {"model_type": r.model_type, "values": []})["values"].append(r.value)
    return out


def analyse(conn, case_id, params, ctx=None) -> tuple:
    counts = defaultdict(int)
    vocab = V.build(conn, case_id)
    counts["vocabulary_names"] = len(vocab["names"])
    counts["vocabulary_numbers"] = len(vocab["numbers"])
    counts["vocabulary_endings"] = len(vocab["endings"])
    counts["vocabulary_terms"] = len(vocab["terms"])
    phones = FV.active_phones(conn, case_id)
    out = []
    for i, (ext, label) in enumerate(phones.items()):
        if ctx is not None:
            ctx.progress(i, len(phones), label)
            if ctx.cancelled():
                break
        typed = _typed(conn, ext)
        counts["typed_records"] += len(typed)
        hits = {}
        for uid, t in typed.items():
            m = sorted({x for v in t["values"] for x in V.matches(v, vocab)})
            if m:
                hits[uid] = (t["model_type"], m)
        if not hits:
            continue
        meta = FV.field_values(conn, ext, ("DictionaryWord", "Autofill"), ("Frequency", "Key", "Source"))
        times = FV.times_for(conn, ext, [u for u, (mt, _) in hits.items() if mt == "Autofill"],
                             ("TimeStamp", "LastUsedDate"))
        deleted = {str(r[0]): r[1] for r in conn.execute(text(
            "SELECT record_uid, deleted_state FROM pv_record WHERE extraction_id = :e AND record_uid = ANY(CAST(:u AS "
            "uuid[]))"), {"e": ext, "u": list(hits)})}
        seen = {}
        for uid in sorted(hits):
            mt, m = hits[uid]
            kinds = sorted({k for k, _ in m})
            n_else, links = 0, []
            for tok in sorted({t for _, t in m}):
                if tok not in seen:
                    seen[tok] = V.elsewhere(conn, ext, tok, LINK_LIMIT)
                n, u = seen[tok]
                n_else += n
                links += [x for x in u if x not in links]
            links = links[:LINK_LIMIT]
            present = n_else > 0
            vals = meta.get(uid, {}).get("values", {})
            t = times.get(uid, {})
            first = min([x for x in t.values() if x], default=None)
            last = max([x for x in t.values() if x], default=None)
            kind = "typed_and_present" if present else "typed_not_in_extraction"
            counts[kind] += 1
            for k in kinds:
                counts["hits_" + k] += 1
            words = ", ".join(V.KIND_WORDS[k] for k in kinds)
            supports = [_d("vocabulary_match", "The value matches %s." % words, [uid])]
            undercuts = [_d("learned_from_any_typing", "A keyboard learns from any typing on the device, in any app, "
                            "by anyone using it."),
                         _d("vocabulary_partial", "The comparison does not yet include: %s." %
                            ", ".join(V.NOT_INCLUDED))]
            if present:
                supports.append(_d("present_elsewhere", "The same term occurs in %d message, email, note, search or "
                                   "calendar records on this phone%s." % (n_else, "" if n_else <= len(links) else
                                                                          "; %d of them are linked" % len(links)),
                                   links))
            else:
                supports.append(_d("not_in_extraction", "The term does not occur in any message, email, note, search "
                                   "or calendar record this extraction holds."))
                undercuts.append(_d("absence_may_be_selection", "Absence can mean the extraction did not hold those "
                                    "records, not that they were deleted."))
            if mt == "DictionaryWord":
                undercuts.append(_d("no_time_recorded", "A learned word carries no time."))
                undercuts.append(_d("synced_dictionary", "A learned word may come from a dictionary synced from "
                                    "another device."))
                if vals.get("Frequency"):
                    undercuts.append(_d("frequency_not_period", "The frequency is the keyboard's own count, not a "
                                        "count of uses in a known period."))
            elif first:
                supports.append(_d("time_recorded", "The autofill entry records when it was used.", [uid]))
            else:
                undercuts.append(_d("no_time_recorded", "This autofill entry carries no time."))
            if deleted.get(uid) in ("Deleted", "Trash"):
                undercuts.append(_d("deleted_or_carved", "The record is a deleted one the phone still held."))
            recs = [{"extraction_id": ext, "record_uid": uid, "field_path": FIELD[mt], "role": "typed"}]
            recs += [{"extraction_id": ext, "record_uid": x, "field_path": None, "role": "elsewhere"} for x in links]
            out.append({
                "kind": kind, "strength": "not_elsewhere" if not present else "elsewhere", "sensitive": True,
                "measures": {"phone_label": label, "extraction_id": ext, "record_type": mt,
                             "value_masked": "••••", "term_kinds": kinds, "terms_matched": len({t for _, t in m}),
                             "frequency": (vals.get("Frequency") or [None])[0],
                             "autofill_key": (vals.get("Key") or [None])[0] if mt == "Autofill" else None,
                             "first_time": first, "last_time": last, "elsewhere_records": n_else,
                             "elsewhere_linked": len(links)},
                "directions": {"supports": supports, "undercuts": undercuts},
                "period_start": first, "period_end": last, "records": recs})
    if ctx is not None:
        ctx.progress(len(phones), len(phones))
    return out, dict(counts)


def run(conn, case_id, params, ctx) -> list:
    results, counts = analyse(conn, case_id, params, ctx)
    _last["counts"] = counts
    return results


def last_counts() -> dict:
    return _last["counts"]
