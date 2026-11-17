"""The five levels of Corroborate and the rules that give them (lx-corroengine E). Every rule is here and nowhere else.

A level is a statement of likelihood, never a yes or no, and it comes only from these rules, never from a model. Each
level is returned with the rule that gave it, the comparison it was judged against with the counts on both sides,
and a sentence written from its reasons.

The rules read a *grid*: one row per signal (a kind of link between the people, e.g. "Doe and Roe in contact"),
one cell per instance (an incident night, or an ordinary night it is compared with). A cell is ``present``,
``absent`` (checked and not there) or ``no_data`` (the records that would show it do not cover that instance; it
counts neither way). A row carries a ``weight``: ``full``, or ``low`` when an explained-away check accounts for it
(the person works there, the phrase is used all over the case, the place is busy). A row that was used to pick the
incident instances (``picked_by``) never counts as evidence for them.

*Reverse if* investigators read a level differently from its sentence: the thresholds below are the only place to
change it, and ``tests/test_corroborate_levels.py`` holds each boundary.
"""
from __future__ import annotations

from typing import Any

LEVELS = {
    "strong": "Strong link",
    "probable": "Probable link",
    "possible": "Possible link",
    "coincidence": "Coincidence likely",
    "cant_tell": "Can't tell",
}
# Not a sixth likelihood: the outcome of a search that had the data it needed and found nothing between the people.
NO_LINK = {"key": "no_link_found", "name": "No link found"}

# A signal row *separates* the incidents from ordinary instances when it is in most incidents and rare otherwise.
SEPARATES_INCIDENT_SHARE = 0.6     # present in at least this share of incidents that have data
SEPARATES_ORDINARY_SHARE = 0.2     # and in at most this share of ordinary instances that have data
SEPARATES_GAP = 0.5                # and the two shares differ by at least this much
# A signal is *as often on ordinary days* when its ordinary share is at least this share of its incident share.
ORDINARY_AS_OFTEN = 0.5
REPEATED_MIN = 3                   # a pattern "repeats" when it is in at least this many incidents
STRONG_KINDS = 3                   # independent link kinds that must separate, at full weight, for Strong
PROBABLE_KINDS = 2
MIN_ORDINARY = 2                   # fewer ordinary instances with data than this: the comparison cannot be made

# Link kinds. Two rows of one kind are not independent of each other (two contact rows are one kind of evidence).
LINK_KINDS = {
    "same_person": "Same person", "contact": "Contact", "together": "Together", "sequence": "Sequence",
    "money": "Money", "shared_content": "Shared content", "access": "Access and documents",
    "absence": "Absence", "statement": "Against a statement", "activity": "Active at the same time",
}


def share(counts: dict) -> float | None:
    of = counts.get("of") or 0
    return None if not of else counts.get("present", 0) / of


def row_counts(row: dict, instances: list[dict]) -> dict:
    """{incident: {present, absent, no_data, of}, ordinary: {...}} for one grid row."""
    out = {}
    for side in ("incident", "ordinary"):
        cells = [row["cells"].get(i["id"], "no_data") for i in instances if i["side"] == side]
        present = sum(1 for c in cells if c == "present")
        absent = sum(1 for c in cells if c == "absent")
        out[side] = {"present": present, "absent": absent, "no_data": len(cells) - present - absent,
                     "of": present + absent}
    return out


def separates(row: dict) -> bool:
    inc, ordi = share(row["incident"]), share(row["ordinary"])
    if inc is None or row.get("picked_by"):
        return False
    single = row["incident"]["of"] == 1
    if ordi is None or row["ordinary"]["of"] < MIN_ORDINARY:
        return False
    if single:
        return inc == 1 and ordi <= SEPARATES_ORDINARY_SHARE / 2
    return inc >= SEPARATES_INCIDENT_SHARE and ordi <= SEPARATES_ORDINARY_SHARE and inc - ordi >= SEPARATES_GAP


def as_often_ordinary(row: dict) -> bool:
    inc, ordi = share(row["incident"]), share(row["ordinary"])
    return bool(inc) and ordi is not None and row["ordinary"]["of"] >= MIN_ORDINARY and ordi >= ORDINARY_AS_OFTEN * inc


def _n(x: int) -> str:
    return format(x, ",")


def _counts_words(row: dict, comparison: dict) -> str:
    inc, ordi = row["incident"], row["ordinary"]
    inc_w = f"{_n(inc['present'])} of {_n(inc['of'])} {comparison['incident_noun']}"
    if ordi["of"]:
        ord_w = (f"none of the {_n(ordi['of'])} {comparison['ordinary_noun']}" if ordi["present"] == 0 else
                 f"{_n(ordi['present'])} of {_n(ordi['of'])} {comparison['ordinary_noun']}")
    else:
        ord_w = f"no {comparison['ordinary_noun']} with data to compare"
    return f"{inc_w}, {ord_w}"


def decide(grid: list[dict], instances: list[dict], comparison: dict, checks: list[dict], *,
           question_kind: str, missing: list[dict]) -> dict[str, Any]:
    """The level, its rule, its reasons and its sentence. ``grid`` rows already carry their counts (``row_counts``)."""
    incidents = [i for i in instances if i["side"] == "incident"]
    evidence_rows = [r for r in grid if not r.get("picked_by") and not r.get("context")]
    present_rows = [r for r in evidence_rows if r["incident"]["present"]]
    with_data = [r for r in evidence_rows if r["incident"]["of"]]
    full_sep = [r for r in present_rows if separates(r) and r.get("weight") == "full"]
    low_sep = [r for r in present_rows if separates(r) and r.get("weight") != "full"]
    sep_kinds = sorted({r["link_kind"] for r in full_sep})
    sep_kinds_low = sorted({r["link_kind"] for r in low_sep} - set(sep_kinds))
    repeated = len(incidents) >= REPEATED_MIN and any(r["incident"]["present"] >= REPEATED_MIN for r in full_sep)
    open_checks = [c for c in checks if c.get("open")]
    reasons_up = [f"{r['label']}: {_counts_words(r, comparison)}." for r in full_sep]
    reasons_low = [f"{r['label']}: {_counts_words(r, comparison)}, weighed low ({r.get('why_low') or 'explained'})."
                   for r in present_rows if r.get("weight") != "full"]
    reasons_ordinary = [f"{r['label']}: {_counts_words(r, comparison)}, as often on ordinary days." for r in
                        present_rows if as_often_ordinary(r) and r.get("weight") == "full"]
    ord_with_data = max((r["ordinary"]["of"] for r in evidence_rows), default=0)

    def out(key, rule, reasons):
        level = {"key": key, "name": LEVELS[key] if key in LEVELS else NO_LINK["name"], "rule": rule,
                 "reasons": reasons, "comparison": comparison["words"],
                 "separating_kinds": sep_kinds, "repeated": repeated}
        level["sentence"] = sentence(level, full_sep, present_rows, comparison, incidents, missing, open_checks)
        return level

    if not incidents or not with_data:
        return out("cant_tell", "no_data", [m["words"] for m in missing] or ["No records cover the instances asked about."])
    seed_rows = [r for r in grid if (r.get("picked_by") or r.get("context")) and r["incident"]["present"]]
    distinctive = [r for r in present_rows if r.get("weight") == "full" and not as_often_ordinary(r)]
    if not distinctive and seed_rows:
        return out("coincidence", "overlap_only", [
            f"{r['label']}: {_counts_words(r, comparison)}; this describes what was picked, not a link."
            for r in seed_rows] + reasons_ordinary + reasons_low +
            [f"{r['label']}: checked, not found." for r in with_data if not r["incident"]["present"]][:6])
    if len(incidents) == 1 and distinctive and _only_together_once(distinctive, evidence_rows):
        return out("coincidence", "together_once_no_contact", [f"{r['label']}: {_counts_words(r, comparison)}."
                                                               for r in distinctive] +
                   ["No contact, money or document links the people at any time in the records read."] +
                   reasons_ordinary + reasons_low)
    if not present_rows:
        if len(with_data) >= 2:
            return out("no_link_found", "nothing_present",
                       [f"{r['label']}: checked on {_n(r['incident']['of'])} {comparison['incident_noun']}, not found."
                        for r in with_data])
        return out("cant_tell", "too_little_data", [m["words"] for m in missing] or
                   ["Only one kind of record could be checked."])
    if ord_with_data < MIN_ORDINARY and not full_sep:
        return out("cant_tell", "no_comparison",
                   [f"Fewer than {MIN_ORDINARY} {comparison['ordinary_noun']} hold records to compare with."] +
                   [m["words"] for m in missing])
    if len(sep_kinds) >= STRONG_KINDS and repeated and not open_checks:
        return out("strong", "kinds_repeat_rare", reasons_up + reasons_low)
    if len(sep_kinds) >= STRONG_KINDS and repeated:
        return out("probable", "one_explanation_open", reasons_up + [c["words"] for c in open_checks])
    if len(sep_kinds) >= PROBABLE_KINDS:
        return out("probable", "kinds_agree", reasons_up + reasons_low + [c["words"] for c in open_checks])
    if len(sep_kinds) == 1:
        return out("possible", "one_kind", reasons_up + reasons_low)
    if len(sep_kinds_low) >= 2:
        return out("possible", "weak_kinds", reasons_low)
    return out("coincidence", "as_often_or_explained", reasons_ordinary + reasons_low or
               [f"{r['label']}: {_counts_words(r, comparison)}." for r in present_rows])


def _only_together_once(full_sep: list[dict], rows: list[dict]) -> bool:
    """One instance, the only separating signal is being in one place (or active) at once, and no contact, money or
    document between the people anywhere in what was read: a meeting needs arranging, and nothing arranges this one."""
    if {r["link_kind"] for r in full_sep} - {"together", "activity"}:
        return False
    linking = [r for r in rows if r["link_kind"] in ("contact", "money", "access", "shared_content")]
    return all(not r.get("ever_present") for r in linking) and any(r.get("ever_checked") for r in linking)


def sentence(level: dict, full_sep, present_rows, comparison, incidents, missing, open_checks) -> str:
    """One plain sentence written from the level's reasons (never from a model)."""
    key = level["key"]
    n_inc = len(incidents)
    if key == "cant_tell":
        what = "; ".join(m["missing"] for m in missing[:3]) or "the records that would show it"
        return f"Can't tell: too little data. Missing: {what}."
    if key == "no_link_found":
        return (f"No link found: nothing links them on the {_n(n_inc)} {comparison['incident_noun']} checked. "
                "This is what was searched, not proof that no link exists.")
    kinds = [LINK_KINDS[k].lower() for k in level["separating_kinds"]]
    if key in ("strong", "probable") and full_sep:
        best = max(full_sep, key=lambda r: (r["incident"]["present"], -r["ordinary"]["present"]))
        lead = f"{LEVELS[key]}: {_join(kinds)} agree"
        tail = f" ({_counts_words(best, comparison)})."
        if key == "probable" and open_checks:
            tail = tail[:-1] + f"; not yet ruled out: {open_checks[0]['label'].lower()}."
        return lead + tail
    if key == "possible":
        if full_sep:
            return f"Possible link: one kind of signal ({_join(kinds)}) and nothing else agrees yet."
        return "Possible link: several weak signals; innocent explanations remain."
    if level["rule"] == "overlap_only":
        return ("Coincidence likely: the records overlap in time, and nothing links the people: no contact, place, "
                "money or document between them then.")
    if level["rule"] == "together_once_no_contact":
        return ("Coincidence likely: they were in the same place once, and nothing else links them: no contact, money "
                "or document in the records read.")
    return f"Coincidence likely: what they share happens as often on {comparison['ordinary_noun']}, or is explained."


def _join(words: list[str]) -> str:
    words = list(dict.fromkeys(words))
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


# Who used this phone: the phone with one person's phone on this share of the days both have positions, over at least
# this many days, and never in contact with it.
WHO_USED_STRONG = (0.8, 10)
WHO_USED_PROBABLE = (0.6, 5)


def who_used(days: dict, contact_between: int) -> dict:
    """The level that the phone was used by the person whose phone it travels with (``days``: present/of counts)."""
    s, n = share(days), days.get("of") or 0
    together = f"together on {days.get('present', 0)} of {n} days with positions"
    if not n:
        return {"key": "cant_tell", "name": LEVELS["cant_tell"], "rule": "who_used_no_positions",
                "sentence": "Can't tell: the two phones never have positions on the same day."}
    if contact_between:
        key = "coincidence" if (s or 0) < WHO_USED_PROBABLE[0] else "possible"
        return {"key": key, "name": LEVELS[key], "rule": "who_used_in_contact",
                "sentence": f"{LEVELS[key]}: {together}, but the phones contact each other ({contact_between} times), "
                            "so they are more likely two people."}
    for key, (cut, minimum) in (("strong", WHO_USED_STRONG), ("probable", WHO_USED_PROBABLE)):
        if (s or 0) >= cut and n >= minimum:
            return {"key": key, "name": LEVELS[key], "rule": f"who_used_{key}",
                    "sentence": f"{LEVELS[key]}: {together}, and the phones never contact each other."}
    key = "possible" if (s or 0) >= 0.3 else "coincidence"
    return {"key": key, "name": LEVELS[key], "rule": "who_used_weak", "sentence": f"{LEVELS[key]}: {together}."}
