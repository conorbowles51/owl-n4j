"""Explained-away checks (lx-corroengine C). Every check is run and returned, whatever it finds.

Each check is ``{check, label, outcome, words, records, rows}``: ``outcome`` is ``checked`` (looked at, nothing to
weigh), ``ruled_out`` (the innocent explanation was tested and does not fit), ``weighed_low`` (it fits, so the rows
it explains count for less: their ``weight`` becomes ``low`` with the reason) or ``no_data`` (the records that would
test it are missing). ``open`` marks an innocent explanation that is neither ruled out nor accounted for; a level is
never Strong while one is open.

A case fact a person recorded (``facts``: "live together", "work group", "routine phrase") is used here and named
with who recorded it and when.
"""
from __future__ import annotations

from datetime import timedelta

from services.corroborate import levels as L
from services.corroborate import model as M

LABELS = {
    "routine": "Routine contact", "household": "Same household", "workplace": "Workplace",
    "stock_phrase": "Stock phrase", "busy_place": "Busy place", "clock_zone": "Clock or zone",
    "recycled_number": "Recycled number", "same_name": "Another person of the same name",
    "shared_device": "Shared device", "duplicate_copy": "Copies counted once", "received_media": "Received photos",
}
HOUSEHOLD_SHARE = 0.5     # together on at least this share of ordinary instances: they may share a home
BUSY_PHONES = 3           # a place this many of the case's phones were seen at ...
BUSY_SHARE = 0.3          # ... being at least this share of the phones, is a busy place
SHARED_DEVICE_SHARE = 0.6 # a phone with no known user, with one person's phone this often: maybe one person


def _check(kind, outcome, words, records=(), rows=(), open_=False) -> dict:
    return {"check": kind, "label": LABELS[kind], "outcome": outcome, "words": words, "records": list(records)[:25],
            "rows": list(rows), "open": open_}


def _low(row, why):
    row["weight"], row["why_low"] = "low", why


def _fact_for(facts, kind, people) -> dict | None:
    for f in facts:
        if f["kind"] == kind and set(f.get("people") or ()) >= set(people) and f.get("state", "active") == "active":
            return f
    return None


def _fact_words(f) -> str:
    return f"case fact recorded by {f.get('by_name') or 'a person'} on {str(f.get('at') or '')[:10]}: “{f['text']}”"


def run(rows, instances, people, recs, ctx, store) -> list[dict]:
    """``ctx``: {comparison, folded, facts, phones, zone, windows, period_start}."""
    facts = ctx.get("facts") or []
    comp = ctx["comparison"]
    out = []
    for r in rows:
        r.setdefault("incident", L.row_counts(r, instances)["incident"])
        r.setdefault("ordinary", L.row_counts(r, instances)["ordinary"])
    present = [r for r in rows if r["incident"]["present"]]

    # routine contact
    contact = [r for r in present if r["link_kind"] == "contact"]
    if not contact:
        out.append(_check("routine", "no_data" if not any(r["link_kind"] == "contact" for r in rows) else "checked",
                          "No contact between the people on the instances asked about, so there is no routine to test."))
    else:
        routine = [r for r in contact if L.as_often_ordinary(r)]
        for r in routine:
            _low(r, f"routine: also on {r['ordinary']['present']} of {r['ordinary']['of']} {comp['ordinary_noun']}")
        if routine:
            out.append(_check("routine", "weighed_low", "; ".join(f"{r['label']} on {r['ordinary']['present']} of "
                              f"{r['ordinary']['of']} {comp['ordinary_noun']}" for r in routine) + ".",
                              rows=[r["id"] for r in routine]))
        else:
            out.append(_check("routine", "ruled_out", "; ".join(
                f"{r['label']}: {r['ordinary']['present']} of {r['ordinary']['of']} {comp['ordinary_noun']}"
                for r in contact) + ". Not their everyday contact.", rows=[r["id"] for r in contact]))

    # household
    together = [r for r in present if r["link_kind"] == "together"]
    if not together:
        out.append(_check("household", "checked", "No two of them were placed together, so no shared home to test."))
    else:
        hits, tested, short, device = [], [], [], []
        for r in together:
            f = _fact_for(facts, "live_together", r["people"])
            share = L.share(r["ordinary"])
            if any(not people[k].get("dossier_id") for k in r["people"]) and not f:
                device.append(r)  # a phone with no known user that travels with someone is the shared-device check
                continue
            if f:
                _low(r, _fact_words(f))
                hits.append(f"{r['label']}: {_fact_words(f)}")
            elif share is None or r["ordinary"]["of"] < L.MIN_ORDINARY:
                short.append(r)
            elif share >= HOUSEHOLD_SHARE:
                _low(r, f"together on {r['ordinary']['present']} of {r['ordinary']['of']} {comp['ordinary_noun']} too")
                hits.append(f"{r['label']} on {r['ordinary']['present']} of {r['ordinary']['of']} {comp['ordinary_noun']}")
            else:
                tested.append(r)
        counts = lambda rs: "; ".join(f"{r['label']}: {r['ordinary']['present']} of {r['ordinary']['of']} "
                                      f"{comp['ordinary_noun']}" for r in rs)
        device_words = (" " + counts(device) + ": a phone with no known user, so whether it is the other person's "
                        "second phone is the Shared device check.") if device else ""
        if hits:
            outcome, words = "weighed_low", "; ".join(hits) + "." + device_words
        elif tested:
            outcome, words = "ruled_out", (counts(tested) + f". Together on under half of the {comp['ordinary_noun']}, "
                                           "so not the pattern of a shared home." + device_words)
        elif short:
            outcome, words = "no_data", (f"Fewer than {L.MIN_ORDINARY} {comp['ordinary_noun']} hold records to "
                                         "compare with, so a shared home cannot be tested." + device_words)
        else:
            outcome, words = "checked", device_words.strip()
        out.append(_check("household", outcome, words, rows=[r["id"] for r in together]))

    # workplace
    access = [r for r in present if r["link_kind"] in ("access", "together")]
    work = []
    for r in access:
        f = _fact_for(facts, "work_group", r["people"])
        if f:
            _low(r, _fact_words(f))
            work.append(f"{r['label']}: {_fact_words(f)}")
        elif r["link_kind"] == "access" and r["ordinary"]["of"] >= L.MIN_ORDINARY and \
                (L.share(r["ordinary"]) or 0) >= HOUSEHOLD_SHARE:
            _low(r, f"named on {r['ordinary']['present']} of {r['ordinary']['of']} {comp['ordinary_noun']} too: a work routine")
            work.append(f"{r['label']} on {r['ordinary']['present']} of {r['ordinary']['of']} {comp['ordinary_noun']}")
    access_rows = [r for r in access if r["link_kind"] == "access"]
    out.append(_check("workplace", "weighed_low" if work else ("ruled_out" if access_rows else "checked"),
                      "; ".join(work) + "." if work else ("; ".join(
                          f"{r['label']}: {r['ordinary']['present']} of {r['ordinary']['of']} {comp['ordinary_noun']}"
                          for r in access_rows) + ". Not a shift they keep on ordinary days." if access_rows else
                          "No access log or work record names them on the instances asked about."),
                      rows=[r["id"] for r in access]))

    # stock phrase
    content = [r for r in present if r["link_kind"] == "shared_content"]
    for r in content:
        f = next((f for f in facts if f["kind"] == "routine_phrase" and f.get("phrase", "").casefold() in r["phrase"]), None)
        if f:
            _low(r, _fact_words(f))
    low = [r for r in content if r.get("weight") == "low"]
    out.append(_check("stock_phrase", "weighed_low" if low else ("ruled_out" if content else "checked"),
                      ("; ".join(f"“{r['phrase']}”: {r.get('why_low')}" for r in low) + ".") if low else
                      ("; ".join(f"“{r['phrase']}” is in {r['case_count']:,} records of the case" for r in content) +
                       ". Rare in the case, so it is not a stock phrase.") if content else
                      "No words are shared between their records on the instances asked about.",
                      rows=[r["id"] for r in content]))

    # busy place
    if not together:
        out.append(_check("busy_place", "checked", "No meeting place to test."))
    else:
        notes, busy_rows, recs_used, tested = [], [], [], []
        by_ref = {x["ref"]: x for x in recs}
        for r in together:
            first_inst = next((i for i in instances if r["cells"].get(i["id"]) == "present"), None)
            ref = (r["records"].get(first_inst["id"]) or [None])[0] if first_inst else None
            pos = by_ref.get(ref)
            if not pos:
                continue
            st = store.place_stats(pos["place"]["lat"], pos["place"]["lon"], max(pos["place"].get("radius_m") or 0, 100),
                                   exclude=ctx["phones"])
            busy = st["phones_near"] >= BUSY_PHONES and st["phones_total"] and \
                st["phones_near"] / st["phones_total"] >= BUSY_SHARE
            if st["phones_total"]:
                tested.append(r["id"])
                words = (f"{st['phones_near']} of the case's {st['phones_total']} other phones were ever within "
                         f"{int(st['radius_m'])} m of it" + (f", on {st['days']} days" if st['phones_near'] else ""))
            else:  # nothing to compare with: not tested, so not ruled out
                words = "the case holds no other phone to compare the place with"
            day = first_inst["start"].astimezone(M.tz(ctx["zone"])).date() if first_inst else None
            shops = store.merchant_payments([people[k] for k in r["people"]], day) if day else []
            if shops:
                words += "; a card payment that day: " + ", ".join(
                    f"{s['words'].strip()} {M.fmt_money(s['amount_minor'])}" for s in shops[:3]) + \
                    " (the records do not say whether it was paid at this place)"
                recs_used += [s["ref"] for s in shops[:3]]
            if busy:
                _low(r, "a busy place: " + words)
                busy_rows.append(r["id"])
            notes.append(f"{r['label']}: {words}")
        out.append(_check("busy_place", "weighed_low" if busy_rows else ("ruled_out" if tested else (
                              "no_data" if notes else "checked")),
                          "; ".join(notes) + "." if notes else "No position record to place the meeting.",
                          records=recs_used, rows=busy_rows or [r["id"] for r in together]))

    # clock or zone
    zones = {e: z for e, z in (ctx.get("phone_zones") or {}).items() if e in ctx["phones"]}
    offsets = store.offsets(ctx["phones"], ctx["windows"]) if ctx["phones"] else {}
    total = sum(offsets.values())
    explicit = offsets.get("explicit", 0)
    other_zones = sorted({z for z in zones.values() if z and z != ctx["zone"]})
    if not total:
        out.append(_check("clock_zone", "no_data", "No phone records to test for clock or zone differences."))
    elif explicit == total:
        out.append(_check("clock_zone", "ruled_out",
                          f"Every record's time states its offset ({explicit:,} of {total:,}), so each is read as the "
                          f"instant it is and shown in {ctx['zone']}." + (
                              f" A phone examined in {', '.join(other_zones)} is read the same way: nothing is placed "
                              "in that zone and nothing moves by an hour." if other_zones else "")))
    else:
        out.append(_check("clock_zone", "weighed_low",
                          f"{total - explicit:,} of {total:,} record times carry no offset and are read in the phone's "
                          f"zone; a link resting on them could be an hour out.", open_=False))

    # recycled number: records carrying a person's number from before their own phone's first outgoing record
    starts = ctx.get("phone_starts") or {}
    rec_notes, rec_refs = [], []
    for k in sorted(people):
        p = people[k]
        start = starts.get(k)
        if not start:
            continue
        for num in sorted(p["numbers"]):
            early = store.number_history(num, start - timedelta(days=90))
            if not early:
                continue
            names = sorted({n["name"] for n in store.identities_named([num]) if n["name"] and
                            not any(M.names_match(x, n["name"]) for x in p["names"] if x)})
            saved = f", saved as {', '.join('“' + n + '”' for n in names[:3])}" if names else ""
            rec_notes.append(f"+{num} ({p['label']}) carries {len(early)} records from {early[0]['at']:%Y}{saved}, before "
                             f"this phone's own records begin ({start:%b %Y}): the number was someone else's then. Those "
                             f"records are not read as {p['label']}'s" + (", and the older name is not joined to this "
                                                                          "pattern." if names else "."))
            rec_refs += [e["ref"] for e in early[:5]]
    out.append(_check("recycled_number", "ruled_out" if rec_notes else "checked",
                      " ".join(rec_notes) or "None of their numbers was in use by someone else before their phones' "
                      "records begin.", records=rec_refs))

    # another person of the same name
    same = []
    everyone = ctx.get("everyone") or []
    for k in sorted(people):
        p = people[k]
        for n in p["names"]:
            words = M.name_words(n)
            if len(words) < 2:
                continue
            for o in everyone:
                if o["key"] == k:
                    continue
                for on in o["names"]:
                    ow = M.name_words(on)
                    if ow and ow != words and (ow[0] == words[0] or ow[-1] == words[-1]):
                        same.append(f"{on} is another person of the case, not {n}")
        saved = ctx.get("saved_names", {}).get(k, [])
        for s in saved:
            same.append(s)
    out.append(_check("same_name", "ruled_out" if same else "checked",
                      "; ".join(dict.fromkeys(same)) + "." if same else "No one else in the case shares their names."))

    # shared device
    unknown = [k for k in people if not people[k].get("dossier_id") and people[k]["phones"]]
    dev_notes, dev_rows = [], []
    for u in unknown:
        # a "together" row of one person (inside the area chosen) says where, not with whom
        for r in [r for r in rows if r["link_kind"] == "together" and u in r["people"] and len(set(r["people"])) > 1]:
            share = L.share(r["ordinary"])
            if share is not None and r["ordinary"]["of"] >= L.MIN_ORDINARY and share >= SHARED_DEVICE_SHARE:
                other = next(x for x in r["people"] if x != u)
                dev_notes.append(f"{people[u]['label']} was with {people[other]['label']}'s phone on "
                                 f"{r['ordinary']['present']} of {r['ordinary']['of']} {comp['ordinary_noun']}: it may be "
                                 f"{people[other]['label']}'s second phone, so contact between the two is not counted")
                for c in rows:
                    if c["link_kind"] == "contact" and set(c["people"]) == {u, other}:
                        _low(c, "the two phones may be one person's")
                        dev_rows.append(c["id"])
    out.append(_check("shared_device", "weighed_low" if dev_notes else "checked",
                      "; ".join(dev_notes) + "." if dev_notes else
                      "No phone in the pattern travels with another person's phone often enough to be theirs.",
                      rows=dev_rows))

    # copies counted once
    outside = sorted(ctx.get("statements_outside") or [], key=lambda x: ("counted once" in x, x))
    copies = sum(1 for x in outside if "counted once" in x)
    outside = [x for x in outside if "counted once" not in x] + ([f"{copies} more file{'s' if copies != 1 else ''} "
                                                                   "held twice, each counted once"] if copies else [])
    out.append(_check("duplicate_copy", "ruled_out",
                      f"{ctx.get('folded', 0):,} copies (the same message on two phones, a payment seen as a ledger row "
                      "and as phone alerts) are counted once." + (
                          f" Statement files not in the ledger, so none of their payments is counted: "
                          f"{', '.join(outside[:6])}." if outside else "")))

    # received photos
    media = [x for x in recs if x["kind"] == "media_position"]
    out.append(_check("received_media", "ruled_out" if media else "checked",
                      f"{len(media)} position{'s' if len(media) != 1 else ''} come from photos received on a phone; "
                      "they show where the photo was taken, not where the phone was, and place no one." if media else
                      "No received photo carries a position here.", records=[x["ref"] for x in media]))
    return out
