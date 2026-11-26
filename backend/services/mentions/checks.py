"""Testing one mention against the case, by rules only.

Each source (places, device, photos, other phones, financial, messages, documents) gives a verdict with the reason in
plain words and the records it read. The outcome is computed from those verdicts (``outcome``); no model takes part.

Strength follows what the record can say. A position's own radius decides "at" against "near": a fix of 100 m or less
can place a phone at a place; a wider one only near it ("cell towers only, so near, not at"). Absence is weaker than
presence: a payment not found, a phone with no positions, a message not found is never a contradiction, it says what
was searched. A photo's place says where the camera was; it is never counted as the phone's position.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from services.corroborate import model as M
from services.mentions.kinds import OUTCOME_LABELS, SOURCES, VERDICT_LABELS

AT_M = 100.0             # a position this precise can say "at"
OUTSIDE_MARGIN_M = 100.0  # past the place's edge by this much is clearly elsewhere (as claim_weigh)
AWAY_KM = 20.0           # this far from the usual night-time place is away from home
STAYED_M = 2000.0        # all positions within this of home: stayed home
MOVED_M = 1000.0         # moved at least this far in the window
TOGETHER_M = 300.0
TOGETHER_MIN = 15
OFF_EVENTS = 3           # this many phone events in a window the message says the phone was off
QUIET_EXPECTED = 3.0   # silence is a weak fit only when the phone's own rate expects this many records
OWN_SEND_S = 120   # a phone-off message's own sending and the typing before it: left out of the phone's use
MAX_REFS = 6
_DAY = timedelta(days=1)
_TRAVEL_SPEND = re.compile(r"\b(fuel|gas|shell|exxon|bp|toll|uber|lyft|taxi|airline|airways|air|hotel|motel|inn|"
                           r"cabins?|lodge|parking|rail|amtrak)\b", re.I)


def _dt(v):
    return M.as_utc(datetime.fromisoformat(str(v).replace("Z", "+00:00")))


def _local(t, zone, fmt="%a %d %b, %H:%M"):
    return t.astimezone(M.tz(zone)).strftime(fmt).replace(" 0", " ")


def _km(m):
    return f"{m / 1000:.1f} km" if m >= 1000 else f"{int(round(m))} m"


def _money(minor):
    return f"${minor / 100:,.2f}"


def _chk(source, verdict, text, note="", refs=(), strong=False):
    refs = list(refs)
    return {"source": source, "source_label": SOURCES[source], "verdict": verdict, "verdict_label": VERDICT_LABELS[verdict],
            "text": text, "note": note, "refs": refs[:MAX_REFS], "refs_total": len(refs), "strong": bool(strong)}


def _ref(r, label):
    return {"ref": r["ref"], "label": label}


def _precision(pos):
    rad = float((pos.get("place") or {}).get("radius_m") or 0)
    return rad


def _precision_note(positions):
    rads = [_precision(p) for p in positions]
    if not rads:
        return ""
    worst = max(rads)
    if worst > 1000:
        return f"Some positions come from cell towers, about {_km(worst)} across, so “near”, not “at”."
    if worst > AT_M:
        return f"Positions are up to {_km(worst)} across, so “near” rather than “at”."
    return f"Positions are within {_km(worst)}."


class Ctx:
    """One mention with what the checks need: the people, the window and the records in it."""

    def __init__(self, data, mention: dict, context: dict):
        self.data, self.m, self.c = data, mention, context
        self.zone = data.zone()
        self.everyone = {p["key"]: p for p in data.people()}
        self.who = [self.everyone[k] for k in mention.get("who") or [] if k in self.everyone]
        self.others = [self.everyone[k] for k in mention.get("with") or [] if k in self.everyone]
        w = mention.get("when") or {}
        self.lo, self.hi = _dt(w["start"]), _dt(w["end"])
        self.at = _dt(context["at"])
        people = self.who + [o for o in self.others if o not in self.who]
        self.recs = data.phone_records(people, self.lo - timedelta(minutes=5), self.hi + timedelta(minutes=5)) if people else []

    def label(self, p):
        return p["label"]

    def positions(self, person, media=False):
        kind = "media_position" if media else "position"
        return sorted((r for r in self.recs if r["kind"] == kind and r.get("owner") == person["key"] and r.get("place")
                       and self.lo - timedelta(minutes=5) <= r["at"] <= self.hi + timedelta(minutes=5)), key=lambda r: r["at"])

    def window_words(self):
        return f"{_local(self.lo, self.zone)} to {_local(self.hi, self.zone)}"


def _dist(a, b):
    return M.haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])


def _inside(pos, where):
    d = _dist(where, pos["place"])
    edge = float(where.get("radius_m") or 150.0) + float(pos["place"].get("radius_m") or 0)
    return d <= edge, d - edge


# ---- places ----------------------------------------------------------------------------------------------------

def place_check(ctx, person, where, name, expect=True):
    """The person's positions in the window against a located place. ``expect`` False: the mention says they were
    not there."""
    pos = ctx.positions(person)
    if not person["phones"]:
        return _chk("places", "nothing", f"{person['label']} has no phone in the case.")
    if not pos:
        return _chk("places", "nothing", f"{person['label']}'s phone has no positions from {ctx.window_words()}.",
                    "No positions is not evidence either way.")
    ins = [(r, o) for r in pos for ok, o in [_inside(r, where)] if ok]
    far = [(r, o) for r in pos for ok, o in [_inside(r, where)] if not ok and o > OUTSIDE_MARGIN_M]
    refs = [_ref(r, f"{person['label']} · {_local(r['at'], ctx.zone)}") for r in pos]
    note = _precision_note(pos)
    if ins and not far:
        precise = all(_precision(r) <= AT_M for r, _ in ins)
        v = "fits" if precise else "fits_weakly"
        text = (f"{person['label']}'s phone is {'at' if precise else 'near'} {name} at {len(ins)} of {len(pos)} positions "
                f"from {ctx.window_words()}.")
    elif far and not ins:
        nearest = min(o for _, o in far) + float(where.get("radius_m") or 150.0)
        precise = all(_precision(r) <= 1000 for r, _ in far)
        v = "contradicts" if precise else "contradicts_weakly"
        first = far[0][0]
        text = (f"{person['label']}'s phone is elsewhere at all {len(pos)} positions from {ctx.window_words()}, the nearest "
                f"{_km(nearest)} from {name}; at {_local(first['at'], ctx.zone)} it was {_km(_dist(where, first['place']))} away.")
    elif ins and far:
        v = "context"
        text = (f"{person['label']}'s phone is at {name} at {len(ins)} positions and clearly elsewhere at {len(far)} from "
                f"{ctx.window_words()}: it came or went in the window.")
    else:
        v = "context"
        text = f"{person['label']}'s {len(pos)} positions are just outside {name}, within {int(OUTSIDE_MARGIN_M)} m of its edge."
    if not expect and v in ("fits", "fits_weakly", "contradicts", "contradicts_weakly"):
        v = {"fits": "contradicts", "fits_weakly": "contradicts_weakly", "contradicts": "fits",
             "contradicts_weakly": "fits_weakly"}[v]
    return _chk("places", v, text, note, refs, strong=v in ("fits", "contradicts"))


def home_check(ctx, person, expect_home=True, words="home"):
    home = ctx.data.home(person["key"])
    if not home:
        return _chk("places", "nothing", f"Loupe cannot tell where {person['label']}'s phone usually spends the night: too "
                    "few night-time positions.", "A home address with a position on the person's page would test it.")
    where = {"lat": home["lat"], "lon": home["lon"], "radius_m": home["radius_m"]}
    out = place_check(ctx, person, where, "its usual night-time place", expect=expect_home)
    out["note"] = (out["note"] + " " if out["note"] else "") + f"“{words}” is read as that place ({home['how']})."
    return out


def away_check(ctx, person, dest_name):
    """Travel to a place not on the map: how far the phone was from its usual night-time place."""
    pos = ctx.positions(person)
    home = ctx.data.home(person["key"])
    if not pos:
        return _chk("places", "nothing", f"{person['label']}'s phone has no positions from {ctx.window_words()}.",
                    "No positions is not evidence either way.")
    refs = [_ref(r, f"{person['label']} · {_local(r['at'], ctx.zone)}") for r in pos]
    if home:
        ds = [_dist(home, r["place"]) for r in pos]
        far = max(ds)
        if far >= AWAY_KM * 1000:
            return _chk("places", "fits_weakly", f"{person['label']}'s phone is {_km(far)} from its usual night-time place "
                        f"from {ctx.window_words()}.", f"{dest_name} is not on the map, so this shows the trip, not the "
                        "place.", refs)
        if far <= STAYED_M:
            return _chk("places", "contradicts_weakly", f"{person['label']}'s phone stays within {_km(far)} of its usual "
                        f"night-time place at all {len(pos)} positions from {ctx.window_words()}.",
                        _precision_note(pos), refs)
        return _chk("places", "context", f"{person['label']}'s phone is up to {_km(far)} from its usual night-time place "
                    f"from {ctx.window_words()}.", f"{dest_name} is not on the map.", refs)
    return moved_check(ctx, person)


def moved_check(ctx, person):
    pos = ctx.positions(person)
    start = ctx.data.last_position_before(person, ctx.at) if person["phones"] else None
    pts = ([start] if start else []) + pos
    if len(pts) < 2:
        return _chk("places", "nothing", f"{person['label']}'s phone has too few positions around {_local(ctx.at, ctx.zone)} "
                    "to show movement.")
    span = max(_dist(pts[0]["place"], p["place"]) for p in pts[1:])
    refs = [_ref(r, f"{person['label']} · {_local(r['at'], ctx.zone)}") for r in pts]
    if span >= MOVED_M:
        return _chk("places", "fits_weakly", f"{person['label']}'s phone moves {_km(span)} between "
                    f"{_local(pts[0]['at'], ctx.zone)} and {_local(pts[-1]['at'], ctx.zone)}.", _precision_note(pts), refs)
    if len(pos) < 2:
        return _chk("places", "nothing", f"{person['label']}'s phone has {len(pos)} position{'' if len(pos) == 1 else 's'} from "
                    f"{ctx.window_words()}, too few to show whether it moved.")
    return _chk("places", "contradicts_weakly", f"{person['label']}'s phone stays within {_km(span)} between "
                f"{_local(pts[0]['at'], ctx.zone)} and {_local(pts[-1]['at'], ctx.zone)}.", _precision_note(pts), refs)


def together_check(ctx, a, b):
    pa, pb = ctx.positions(a), ctx.positions(b)
    if not a["phones"] or not b["phones"]:
        lacking = [p["label"] for p in (a, b) if not p["phones"]]
        return _chk("other_phones", "nothing", f"{' and '.join(lacking)} {'has' if len(lacking) == 1 else 'have'} no phone in "
                    "the case, so whether they met cannot be tested from phones.")
    if not pa or not pb:
        lacking = [p["label"] for p, ps in ((a, pa), (b, pb)) if not ps]
        return _chk("other_phones", "nothing", f"No positions of {' or '.join(lacking)}'s phone from {ctx.window_words()}.")
    pairs = [(x, y) for x in pa for y in pb if abs((x["at"] - y["at"]).total_seconds()) <= TOGETHER_MIN * 60 and
             _dist(x["place"], y["place"]) <= TOGETHER_M + _precision(x) + _precision(y)]
    refs = [_ref(x, f"{a['label']} · {_local(x['at'], ctx.zone)}") for x, _ in pairs[:3]] + \
           [_ref(y, f"{b['label']} · {_local(y['at'], ctx.zone)}") for _, y in pairs[:3]]
    if pairs:
        x, y = pairs[0]
        return _chk("other_phones", "fits", f"{a['label']}'s and {b['label']}'s phones are within {_km(_dist(x['place'], y['place']))} "
                    f"of each other at {_local(x['at'], ctx.zone)}.", _precision_note([x, y]), refs, strong=True)
    closest = min(((abs((x["at"] - y["at"]).total_seconds()), _dist(x["place"], y["place"]), x) for x in pa for y in pb),
                  key=lambda t: (t[0] > TOGETHER_MIN * 60, t[1]))
    refs = [_ref(x, f"{a['label']} · {_local(x['at'], ctx.zone)}") for x in pa[:3]] + \
           [_ref(y, f"{b['label']} · {_local(y['at'], ctx.zone)}") for y in pb[:3]]
    if len(pa) < 2 or len(pb) < 2:
        return _chk("other_phones", "context", f"{a['label']}'s phone has {len(pa)} position{'s' if len(pa) != 1 else ''} and "
                    f"{b['label']}'s {len(pb)} from {ctx.window_words()}, never within {int(TOGETHER_M)} m of each other inside "
                    f"{TOGETHER_MIN} minutes; too few to say they were apart.", _precision_note(pa + pb), refs)
    v = "contradicts" if len(pa) >= 3 and len(pb) >= 3 else "contradicts_weakly"
    return _chk("other_phones", v, f"{a['label']}'s {len(pa)} positions and {b['label']}'s {len(pb)} are never within "
                f"{int(TOGETHER_M)} m of each other inside {TOGETHER_MIN} minutes from {ctx.window_words()}; the closest "
                f"pair is {_km(closest[1])} apart.", _precision_note(pa + pb), refs, strong=v == "contradicts")


def contact_check(ctx, a, b):
    hits = [r for r in ctx.recs if r["kind"] in ("message", "call", "email") and r.get("ref") != f"phone_record:{ctx.c.get('record_uid')}"
            and ((r.get("owner") == a["key"] and b["key"] in (r.get("parties") or ())) or
                 (r.get("owner") == b["key"] and a["key"] in (r.get("parties") or ())))]
    if not hits:
        return None
    return _chk("messages", "context", f"{len(hits)} call{'s' if len(hits) != 1 else ''} or message{'s' if len(hits) != 1 else ''} "
                f"between {a['label']} and {b['label']} from {ctx.window_words()}, the first at {_local(hits[0]['at'], ctx.zone)}.",
                "Contact around the time fits a meeting being arranged; it does not show they met.",
                [_ref(r, f"{r['kind']} · {_local(r['at'], ctx.zone)}") for r in hits])


def photos_check(ctx, person, where=None, name=None):
    media = ctx.positions(person, media=True)
    if not media:
        return None
    refs = [_ref(r, f"photo · {_local(r['at'], ctx.zone)}") for r in media]
    note = "A photo's place says where the camera was, not where the phone's owner was."
    if where:
        ins = [r for r in media if _inside(r, where)[0]]
        if ins:
            return _chk("photos", "fits_weakly", f"{len(ins)} of {len(media)} photos on {person['label']}'s phone from "
                        f"{ctx.window_words()} carry a place at {name}.", note, refs)
    home = ctx.data.home(person["key"])
    if home:
        far = [r for r in media if _dist(home, r["place"]) >= AWAY_KM * 1000]
        if far:
            return _chk("photos", "fits_weakly", f"{len(far)} of {len(media)} photos on {person['label']}'s phone from "
                        f"{ctx.window_words()} carry a place more than {int(AWAY_KM)} km from its usual night-time place.",
                        note, refs)
    return _chk("photos", "context", f"{len(media)} photos on {person['label']}'s phone from {ctx.window_words()} carry a place.",
                note, refs)


# ---- device ----------------------------------------------------------------------------------------------------

def device_off_check(ctx, person, words):
    if not person["phones"]:
        return _chk("device", "nothing", f"{person['label']} has no phone in the case.")
    # The message saying so was sent from the phone: its own sending (and the typing just before it) is left out.
    cut = ctx.at - timedelta(seconds=OWN_SEND_S)
    ev = [e for e in ctx.data.use_events(person, ctx.lo, ctx.hi) if e[0] < cut]
    own = "The sending of this message is left out."
    used = [t for t, c, _ in ev if c == "interaction"]
    on = [t for t, c, _ in ev if c != "interaction"]
    span = ctx.window_words()
    if len(used) >= 2 or len(used) + len(on) >= OFF_EVENTS:
        last = max(used + on)
        return _chk("device", "contradicts", f"{person['label']}'s phone records {len(used)} use{'s' if len(used) != 1 else ''} by its "
                    f"owner (messages sent, calls, apps) and {len(on)} other record{'s' if len(on) != 1 else ''} of being on from "
                    f"{span}, the last at {_local(last, ctx.zone)}.", f"The message says “{words}”. {own}", strong=len(used) >= 2)
    if not ev:
        hours = max((cut - ctx.lo).total_seconds() / 3600, 0)
        expected = ctx.data.use_rate(person) * hours
        if expected < QUIET_EXPECTED:
            return _chk("device", "context", f"{person['label']}'s phone records nothing of its own from {span}, and that is "
                        f"usual for it: it keeps about {_rate_words(expected)} records in a span that long.",
                        f"So a quiet phone says nothing here either way. {own}")
        return _chk("device", "fits_weakly", f"{person['label']}'s phone records nothing of its own from {span}, where it "
                    f"usually keeps about {expected:.0f}.", f"Absence is weaker evidence than presence. {own}")
    return _chk("device", "context", f"{person['label']}'s phone records {len(ev)} record{'s' if len(ev) != 1 else ''} of its own "
                f"from {span}.", f"Too few to say it was on. {own}")


def _rate_words(expected):
    return "none" if expected < 0.5 else "one" if expected < 1.5 else f"{expected:.0f}"


def device_use_check(ctx, person):
    acts = ctx.data.activity(person, ctx.lo, ctx.hi)
    if not person["phones"] or not acts:
        return None
    return _chk("device", "context", f"{person['label']}'s phone records {len(acts)} events of its own use from "
                f"{ctx.window_words()}.", "Using a phone says nothing about where its owner was.")


# ---- money and records -----------------------------------------------------------------------------------------

def _word_hit(words, body):
    low = body.lower()
    return [w for w in words if len(w) >= 4 and re.search(rf"\b{re.escape(w.lower())}\b", low)]


def payment_check(ctx, words, amounts, checks_no, before_days=2, after_days=14):
    lo_d = ctx.lo.astimezone(M.tz(ctx.zone)).date() - timedelta(days=before_days)
    hi_d = ctx.hi.astimezone(M.tz(ctx.zone)).date() + timedelta(days=after_days)
    pays = ctx.data.payments(lo_d, hi_d)
    hits, why = [], []
    for p in pays:
        reasons = []
        hw = _word_hit(words, p["words"])
        if hw:
            reasons.append("names " + ", ".join(f"“{w}”" for w in hw))
        if amounts and p["amount_minor"] in amounts:
            reasons.append(f"is {_money(p['amount_minor'])}")
        for n in checks_no:
            if re.search(rf"\b(?:CHECK|CHK|CHEQUE)\s*#?\s*{re.escape(n)}\b", p["words"], re.I):
                reasons.append(f"is check {n}")
        if reasons:
            hits.append(p)
            why.append(reasons)
    span = f"{lo_d:%d %b} to {hi_d:%d %b %Y}".lstrip("0")
    if not hits:
        sought = [f"“{w}”" for w in words if len(w) >= 4] + [_money(a) for a in amounts] + [f"check {n}" for n in checks_no]
        if not sought:
            return None
        cover = ctx.data.ledger_span()
        covered = f" The ledger runs {cover[0]:%d %b %Y} to {cover[1]:%d %b %Y}." if cover else " The case has no ledger."
        return _chk("financial", "nothing", f"No payment from {span} names or matches {', '.join(sought)}.",
                    "A payment not found is not evidence either way." + covered)
    p, r = hits[0], why[0]
    strong = len(r) >= 2 or any(x.startswith("is check") for x in r) or (bool(amounts) and any(x.startswith("is $") for x in r))
    lines = [f"{h['words']}, {_money(h['amount_minor'])}, on {h['day']:%a %d %b}, account held by {h['holder'] or 'an unnamed holder'}"
             for h in hits[:3]]
    text = "; ".join(lines) + (f"; and {len(hits) - 3} more" if len(hits) > 3 else "") + "."
    return _chk("financial", "fits", text, f"It {' and '.join(r)}.", [_ref(h, f"{h['words']} · {h['day']:%d %b}") for h in hits],
                strong=strong)


def travel_spend_check(ctx):
    lo_d = ctx.lo.astimezone(M.tz(ctx.zone)).date()
    hi_d = ctx.hi.astimezone(M.tz(ctx.zone)).date() + timedelta(days=3)
    who = {p["label"].lower() for p in ctx.who}
    hits = [p for p in ctx.data.payments(lo_d, hi_d) if _TRAVEL_SPEND.search(p["words"])]
    if not hits:
        return None
    return _chk("financial", "context", f"{len(hits)} travel payment{'s' if len(hits) != 1 else ''} in the window: "
                + "; ".join(f"{h['words']}, {_money(h['amount_minor'])}, {h['day']:%d %b}" for h in hits[:3]) + ".",
                "These do not name the place." if not who else "", [_ref(h, h["words"]) for h in hits])


def messages_check(ctx, words, days=3):
    ws = [w for w in words if len(w) >= 4]
    if not ws:
        return None
    hits = ctx.data.comm_with_words(ws, ctx.lo - timedelta(days=days), ctx.hi + timedelta(days=days),
                                    exclude_uid=ctx.c.get("record_uid"))
    if not hits:
        return _chk("messages", "nothing", f"No other message or e-mail within {days} days names {', '.join(f'“{w}”' for w in ws)}.")
    em = [h for h in hits if h["kind"] == "email"]
    return _chk("messages", "fits_weakly" if em else "context",
                f"{len(hits)} other message{'s' if len(hits) != 1 else ''} or e-mail{'s' if len(hits) != 1 else ''} within {days} days "
                f"name {', '.join(f'“{w}”' for w in ws)}" + (f", {len(em)} of them e-mails" if em else "") + ".",
                "Naming the same thing is not the same as being the thing sent.",
                [_ref(h, f"{h['kind']} · {_local(h['at'], ctx.zone)}") for h in hits])


def deleted_check(ctx, words):
    ws = [w for w in words if len(w) >= 4]
    if not ws:
        return None
    hits = ctx.data.comm_with_words(ws, ctx.at - timedelta(days=365), ctx.at + timedelta(days=365),
                                    exclude_uid=ctx.c.get("record_uid"))
    if not hits:
        return _chk("messages", "nothing", f"No message or e-mail on any phone in the case names {', '.join(f'“{w}”' for w in ws)}.",
                    "Nothing left fits a deletion, and fits nothing having existed.")
    gone = [h for h in hits if h["deleted"]]
    kept = [h for h in hits if not h["deleted"]]
    refs = [_ref(h, f"{h['kind']} · {_local(h['at'], ctx.zone)}{' · deleted' if h['deleted'] else ''}") for h in gone + kept]
    if gone:
        return _chk("messages", "fits", f"{len(gone)} message{'s' if len(gone) != 1 else ''} or e-mail{'s' if len(gone) != 1 else ''} "
                    f"naming {', '.join(f'“{w}”' for w in ws)} {'are' if len(gone) != 1 else 'is'} marked deleted on a phone"
                    + (f"; {len(kept)} {'are' if len(kept) != 1 else 'is'} still there." if kept else "."), "", refs, strong=True)
    after = [h for h in kept if h["at"] > ctx.at]
    return _chk("messages", "context", f"{len(kept)} message{'s' if len(kept) != 1 else ''} or e-mail{'s' if len(kept) != 1 else ''} "
                f"naming {', '.join(f'“{w}”' for w in ws)} are still on the phones" + (f", {len(after)} dated after this message" if after else "")
                + ".", "A phone keeps a copy the sender's deletion does not reach.", refs)


def documents_check(ctx, words):
    ws = [w for w in words if len(w) >= 4]
    if not ws:
        return None
    docs = ctx.data.documents_with_words(ws)
    if not docs:
        return None
    seen, uniq = set(), []
    for d in docs:
        if d["name"] not in seen:
            seen.add(d["name"])
            uniq.append(d)
    return _chk("documents", "context", f"{len(uniq)} document{'s' if len(uniq) != 1 else ''} name "
                f"{', '.join(f'“{w}”' for w in ws)}: " + ", ".join(d["name"] for d in uniq[:4]) + ("…" if len(uniq) > 4 else "") + ".",
                "Read them for dates and names; Loupe does not decide what a document says.",
                [_ref(d, d["name"]) for d in uniq])


# ---- per kind --------------------------------------------------------------------------------------------------

_OFF = re.compile(r"\b(phone was off|phone off|no signal|battery died)\b", re.I)
_BED = re.compile(r"\b(in bed|asleep|sleeping|off sick|home)\b", re.I)
_NOT_IN = re.compile(r"\b(not coming in|off sick|off work)\b", re.I)
_EN_ROUTE = re.compile(r"\b(on my way|on the way|minutes behind|running late)\b", re.I)
_BACK = re.compile(r"\bback (on|home|by)\b", re.I)
_NOT_HOME = re.compile(r"\bnot (at )?home\b", re.I)


def _where_of(ctx, person):
    w = ctx.m.get("where") or {}
    if w.get("located"):
        return {"lat": w["lat"], "lon": w["lon"], "radius_m": w.get("radius_m") or 150.0}, w["name"]
    if w.get("routine") == "work" and person:
        r = ctx.data.work(person["key"])
        if r:
            return {"lat": r["lat"], "lon": r["lon"], "radius_m": r["radius_m"]}, "its usual weekday place"
    return None, w.get("name")


def _would_test(kind, ctx):
    w = (ctx.m.get("where") or {})
    out = []
    if w and not w.get("located") and w.get("name") and not w.get("routine"):
        out.append(f"{w['name']} placed on the map (a labelled place or a dossier address), so positions can be tested against it")
    if kind in ("travel", "at_place", "home_away"):
        out.append("positions of the phone in the window")
        if kind == "travel":
            out.append("a booking e-mail, a boarding pass or a card statement for the trip")
    if kind in ("meeting", "plan"):
        out.append("both people's phones with positions at the time" if ctx.others else "who they were meeting, named or with a phone in the case")
    if kind == "money":
        if ctx.who and not any(p.get("accounts") for p in ctx.who):
            out.append(f"{ctx.who[0]['label']} joined to a bank account in the case (a person page with the account "
                       "holder's name and the phone's number), so the account's own deposits and transfers can be read")
        out.append("the statement for the account the money moved through")
    if kind == "sent":
        out.append("the thing sent itself: the e-mail, file or payment, on a phone or in the evidence")
    if kind == "deleted":
        out.append("a second extraction of the phone, or another phone that received the item")
    return out


def run_checks(ctx) -> list[dict]:
    m, kind = ctx.m, ctx.m["kind"]
    phrase = m.get("phrase") or ""
    person = ctx.who[0] if ctx.who else None
    words = list(m.get("words") or [])
    where, name = _where_of(ctx, person)
    out = []

    def add(x):
        if x:
            out.append(x)

    if kind == "travel":
        if person:
            if _BACK.search(phrase):
                add(home_check(ctx, person, True, "back"))
            elif where:
                add(place_check(ctx, person, where, name))
            elif _EN_ROUTE.search(phrase):
                add(moved_check(ctx, person))
            else:
                add(away_check(ctx, person, name or "The place"))
            add(photos_check(ctx, person, where, name))
        dest = [w for w in words if len(w) >= 4] or ([name] if name and not name.startswith("the ") else [])
        add(payment_check(ctx, dest, [], []))
        if not any(c["source"] == "financial" and c["verdict"] == "fits" for c in out):
            add(travel_spend_check(ctx))
        add(documents_check(ctx, dest))
    elif kind == "at_place":
        w = m.get("where") or {}
        if person and w.get("near_counterpart") and ctx.others:
            add(together_check(ctx, person, ctx.others[0]))
        elif person and w.get("near_counterpart"):
            add(_chk("other_phones", "nothing", "“Outside” means near the person it was written to, and they have no phone "
                     "in the case."))
        elif person and w.get("routine") == "home":
            add(home_check(ctx, person))
        elif person and where:
            add(place_check(ctx, person, where, name))
        elif person:
            add(_chk("places", "nothing", f"{name or 'The place'} is not on the map, so the phone's positions cannot be tested "
                     "against it."))
        add(payment_check(ctx, words or ([name] if name else []), [], [], before_days=0, after_days=3))
        if person:
            add(photos_check(ctx, person, where, name))
    elif kind == "home_away":
        if person:
            if _OFF.search(phrase):
                add(device_off_check(ctx, person, _OFF.search(phrase).group(0)))
            elif _NOT_IN.search(phrase):
                add(home_check(ctx, person, True, _NOT_IN.search(phrase).group(0)))
                work = ctx.data.work(person["key"])
                if work:
                    add(place_check(ctx, person, {"lat": work["lat"], "lon": work["lon"], "radius_m": work["radius_m"]},
                                    "its usual weekday place", expect=False))
            else:
                add(home_check(ctx, person, not _NOT_HOME.search(phrase), (_BED.search(phrase) or re.search("home", phrase) or [None])[0] or "home"))
                add(device_use_check(ctx, person))
    elif kind in ("meeting", "plan"):
        if person and ctx.others:
            add(together_check(ctx, person, ctx.others[0]))
            add(contact_check(ctx, person, ctx.others[0]))
        if person and where:
            add(place_check(ctx, person, where, name))
        if person and _EN_ROUTE.search(phrase):
            add(moved_check(ctx, person))
        if kind == "plan":
            add(payment_check(ctx, words, m.get("amounts_minor") or [], m.get("check_numbers") or [], 1, 3))
    elif kind == "money":
        timed = bool((m.get("when") or {}).get("words"))
        add(payment_check(ctx, words, m.get("amounts_minor") or [], m.get("check_numbers") or [], 1 if timed else 7,
                          3 if timed else 14))
        add(documents_check(ctx, words))
    elif kind == "sent":
        add(messages_check(ctx, words))
        add(payment_check(ctx, words, m.get("amounts_minor") or [], m.get("check_numbers") or [], 1, 7))
        add(documents_check(ctx, words))
    elif kind == "deleted":
        add(deleted_check(ctx, words))
        add(documents_check(ctx, words))
    return out


def outcome(checks: list[dict]) -> tuple[str, str]:
    """The mention's outcome from its checks' verdicts, and the basis in words. Rules only."""
    v = [c["verdict"] for c in checks]
    fits = [c for c in checks if c["verdict"] == "fits"]
    weak = [c for c in checks if c["verdict"] == "fits_weakly"]
    against = [c for c in checks if c["verdict"] == "contradicts"]
    against_w = [c for c in checks if c["verdict"] == "contradicts_weakly"]
    if against:
        return "contradicts", (f"{SOURCES[against[0]['source']]} contradict{'s' if not SOURCES[against[0]['source']].endswith('s') else ''} it"
                               + (f"; {len(fits) + len(weak)} other source{'s' if len(fits) + len(weak) != 1 else ''} fit" if fits or weak else ""))
    sources_fit = {c["source"] for c in fits + weak}
    if against_w and not (fits or weak):
        return "contradicts_weakly", f"{SOURCES[against_w[0]['source']]} weakly against it, nothing for it"
    if against_w:
        return "cant_tell", "the sources disagree"
    if fits and len(sources_fit) >= 2:
        return "fits_strongly", f"{len(sources_fit)} independent sources agree"
    if len(fits) == 1 and fits[0]["strong"]:
        return "fits_strongly", f"one {SOURCES[fits[0]['source']].lower()} record matches it closely"
    if fits or weak:
        return "fits_weakly", ("one source fits" if len(sources_fit) == 1 else f"{len(sources_fit)} sources fit, each weakly")
    return "cant_tell", "nothing in the case tests it yet"


def check(data, mention: dict, context: dict) -> dict:
    ctx = Ctx(data, mention, context)
    checks = run_checks(ctx)
    order = {"contradicts": 0, "contradicts_weakly": 1, "fits": 2, "fits_weakly": 3, "context": 4, "nothing": 5}
    checks.sort(key=lambda c: order[c["verdict"]])
    out, basis = outcome(checks)
    deciding = [c for c in checks if c["verdict"] not in ("context", "nothing")]
    why = deciding[0]["text"] if deciding else (checks[0]["text"] if checks else "Nothing in the case could be read for it.")
    return {"outcome": out, "label": OUTCOME_LABELS[out], "basis": basis, "why": why, "checks": checks,
            "would_test": _would_test(mention["kind"], ctx) if out == "cant_tell" else [],
            "window": {"start": ctx.lo.isoformat(), "end": ctx.hi.isoformat(), "label": (mention.get("when") or {}).get("label")},
            "people": [p["label"] for p in ctx.who], "with": [p["label"] for p in ctx.others]}
