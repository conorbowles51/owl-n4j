"""The lead finder (lx-leads D): Loupe looks across the whole case for patterns that may show people acting together,
and saves each as a lead "Found by Loupe".

How it works, in order:

1. Read every record of the case once, through Corroborate's own reader (``CaseStore.records``): messages, calls,
   e-mails, positions, payments, payment alerts and document rows. Photo places are never positions: a place read
   from a photo (EXIF, or a photo app's location record) shows where the photo was taken, not where the phone was,
   so it is read as a media place and places no one (``PHOTO_APPS``; until the mapping fix lands, this is the
   finder's own guard, and the run counts how many it set aside).
2. Detectors propose candidates, each a set of records and a Corroborate question:
   contact through a third number (relay chains), same place the same night, the same words every time, payments
   after the key nights, splitting cash under the $10,000 threshold, silences on the key nights, a message deleted on
   one phone and kept on another, and documents naming people together. "Key nights" are the nights of the
   strongest repeated pattern (a relay or a place on three nights or more) and any incident date the case's
   theories state.
3. Each candidate is weighed by the Corroborate engine (``services.corroborate.engine.run``) against the case's
   ordinary days. The engine's rules alone give the level (``services.corroborate.levels``); nothing here grades.
   Every candidate is saved, whatever its level: "Show every match, graded", no cutoff hides one.
4. What is weighed down is listed too ("set aside", with the rule that set it aside): words on most phones (stock
   phrases), files byte-identical on most phones, a payment a document explains, a saved name that shares a name
   with a person but is another number.
5. People who appear in no lead at Possible or above are asked "Is this person connected at all?" over the key
   nights, so "No link found" is shown with what was searched.

Nothing here calls a model. A run re-checks on new material: leads keep their identity (``finder_key``), state and
corrections; a level change is recorded with its reason. Runs start from the Leads page's button, never on their own:
measured 18 Nov on the loaded box, the demo case took 31-70 s and Phone reference 1 more than 10 minutes, so by the
brief's rule (over 10 minutes) automatic runs stay off; the page says when new material arrived since the last run.

Together rule: only the Corroborate engine's (``model.TOGETHER_GAP`` 15 minutes, accuracy radii plus
``TOGETHER_SLACK_M``) for "at the same time"; "same place the same night" uses the same distance rule over a
night. The relations/together.py and colocation.py rules are not used.
"""
from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from bisect import bisect_left, bisect_right
from itertools import combinations
from typing import Any, Callable

from sqlalchemy import select, text

from services.corroborate import model as M
from services.corroborate.store import CaseStore, text_key

log = logging.getLogger(__name__)

PHOTO_APPS = re.compile(r"photo|media|gallery|camera|picture|image", re.I)
NIGHT_SHIFT = timedelta(hours=12)      # a record belongs to the evening of (local time - 12 h): 03:00 is the night before
MIN_REPEAT = 3                         # a pattern repeats when it is on at least this many nights
LONG_TEXT = 30                         # identical words this long are distinctive enough to compare across phones
STOCK_SHARE = 0.75                     # words or files on at least this share of the case's phones are stock
RARE_COPIES = 3                        # a deleted message's words held at most this many times in the case
SILENCE_FROM, SILENCE_TO = 18, 9       # a night, for silences: 18:00 to 09:00 local
NAMES = {"relay": 10, "place": 20, "money": 30, "silence": 40, "words": 50, "cash": 60, "deleted": 70,
         "documents": 80, "once": 90, "missing": 95}


class FinderStore(CaseStore):
    """Corroborate's store, with photo places read as media places (where the photo was taken), never positions."""

    def __init__(self, db, case_id):
        super().__init__(db, case_id)
        self.photo_refs: set[str] = set()
        for uid, app, src in self.q("SELECT record_uid, source_app, source_kind FROM pol_place_observation WHERE "
                                    "case_id = :c AND kind = 'presence' AND record_uid IS NOT NULL"):
            if src == "media_exif" or (app and PHOTO_APPS.search(app)):
                self.photo_refs.add(f"phone_record:{uid}")

        self._held: dict | None = None
        self._phrase_n: dict[str, int] = {}
        self._number_hist: dict[tuple, list[dict]] = {}
        self._activity: dict[str, list[datetime]] | None = None
        self._contact: dict[tuple, int] = {}
        self._cov: dict[tuple, dict] = {}

    def contact_ever(self, a: dict, b: dict) -> int:
        """Asked of the database once per pair in a finder run (Phone reference 1, 18 Nov: every weighing asked its
        pairs again, 11% of a weighing). The pair is told by each side's phones and identifiers, what the count reads."""
        def side(p):
            return (tuple(p["phones"]), tuple(sorted(p.get("numbers") or ())), tuple(sorted(p.get("handles") or ())),
                    tuple(sorted(p.get("emails") or ())))
        key = (side(a), side(b))
        if key not in self._contact:
            self._contact[key] = super().contact_ever(a, b)
        return self._contact[key]

    def coverage(self, people: list[dict], doc_ids: list[str]) -> dict:
        """A person's coverage asked of the database once per finder run (Phone reference 1, 18 Nov: 8% of a weighing);
        documents as before. Callers get copies."""
        if len({p["key"] for p in people}) != len(people):
            return super().coverage(people, doc_ids)
        out: dict[str, dict] = {}
        for p in people:
            key = (p["key"], tuple(p["phones"]), tuple(p["accounts"]))
            if key not in self._cov:
                self._cov[key] = super().coverage([p], [])[p["key"]]
            out[p["key"]] = {n: list(v) for n, v in self._cov[key].items()}
        if doc_ids:
            out.update(super().coverage([], doc_ids))
        return out

    def activity(self, people: list[dict], windows) -> dict[str, list[datetime]]:
        """CaseStore.activity answered from the case's activity instants, read once per finder run (Phone reference 1,
        18 Nov: one query per person per weighing, 25% of a weighing). Same rule: every instant of a person's phones
        from a day before a window to a day after it, each instant once, in order."""
        if not windows or any(lo.tzinfo is None or hi.tzinfo is None or lo - DAY < EARLIEST or hi + DAY > LATEST
                              for lo, hi in windows):
            return super().activity(people, windows)
        if self._activity is None:
            held: dict[str, set] = defaultdict(set)
            rows = self.db.execute(text("SELECT extraction_id, instant_utc FROM pol_activity_event WHERE case_id = :c"),
                                   self.c, execution_options={"stream_results": True, "yield_per": 20000})
            for e, t in rows:
                held[str(e)].add(M.as_utc(t))
            self._activity = {e: sorted(v) for e, v in held.items()}
        out: dict[str, list[datetime]] = {}
        for p in people:
            if not p["phones"]:
                continue
            got: set = set()
            for e in p["phones"]:
                ts = self._activity.get(str(e), [])
                for lo, hi in windows:
                    got.update(ts[bisect_left(ts, lo - DAY):bisect_right(ts, hi + DAY)])
            out[p["key"]] = sorted(got)
        return out

    def number_history(self, value: str, before: datetime) -> list[dict]:
        """Asked of the database once per number and date in a finder run: every weighing asks it again for each
        person's numbers, with the same date (Phone reference 1, 18 Nov: 34% of a weighing)."""
        key = (value, before)
        if key not in self._number_hist:
            self._number_hist[key] = super().number_history(value, before)
        return [dict(r) for r in self._number_hist[key]]

    def phrase_counts(self, phrases: list[str]) -> dict[str, int]:
        """The case-wide count of each phrase, asked of the database once per finder run: on Phone reference 1 one
        count reads 847 MB of text (5.4 s, 18 Nov) and the weighings of one run ask many of the same phrases."""
        want = phrases[:200]
        new = [ph for ph in want if ph not in self._phrase_n]
        if len(new) >= STREAM_PHRASES_FROM:
            self._phrase_n.update(self._streamed_counts(new))
        elif new:
            self._phrase_n.update(super().phrase_counts(new))
        return {ph: self._phrase_n[ph] for ph in want}

    def _streamed_counts(self, phrases: list[str]) -> dict[str, int]:
        """CaseStore's phrase count (ILIKE with the phrase between wildcards) for many phrases in one read. The
        database lower-cases each text once (ILIKE is ``lower(body) LIKE lower(pattern)``) and the matching is done
        here: on Phone reference 1 the database took 4.7-5.4 s per phrase (18 Nov), most of it matching long e-mails;
        here it is about 0.5 s per phrase."""
        lows = [str(x) for (x,) in self.q("SELECT lower(p) FROM unnest(CAST(:ps AS text[])) WITH ORDINALITY AS u(p, i) "
                                         "ORDER BY i", ps=list(phrases))]
        tests = [_like_test(lo) for lo in lows]
        n = [0] * len(phrases)
        rows = self.db.execute(text("SELECT lower(body) FROM phone_comm_events WHERE case_id = :c AND body IS NOT NULL"),
                               self.c, execution_options={"stream_results": True, "yield_per": 2000})
        for (body,) in rows:
            for i, hit in enumerate(tests):
                if hit(body):
                    n[i] += 1
        return dict(zip(phrases, n))

    def records(self, people, windows, everyone):
        return photo_places_as_media(super().records(people, windows, everyone), self.photo_refs)

    def hold(self, recs: list[dict], lo: datetime, hi: datetime, everyone: list[dict]) -> None:
        """Keep the phone records the finder has read for the whole case (``lo`` to ``hi``, everyone's phones), so each
        weighing reads its windows from them instead of the database. On Phone reference 1 one weighing re-read
        251,780 records in 339 s (18 Nov); a finder run weighs dozens of leads."""
        phone = sorted((r for r in recs if r["ref"].startswith("phone_record:")), key=lambda r: r["at"])
        self._held = {"lo": lo, "hi": hi, "sig": _people_sig(everyone), "recs": phone, "at": [r["at"] for r in phone],
                      "phones": {e for p in everyone for e in p["phones"]}}

    def phone_records(self, people, windows, everyone):
        """The held records in the windows, chosen by the same rules as the database read (a payment alert up to three
        days after a window's end). Anything the held read does not cover goes to the database."""
        h = self._held
        phones = {e for p in people for e in p["phones"]}
        if (h is None or _people_sig(everyone) != h["sig"] or not phones <= h["phones"]
                or any(lo.tzinfo is None or hi.tzinfo is None or lo < h["lo"] or hi > h["hi"] for lo, hi in windows)):
            return super().phone_records(people, windows, everyone)
        pick: set[int] = set()
        recs, at = h["recs"], h["at"]
        for lo, hi in windows:
            for k in range(bisect_left(at, lo), bisect_right(at, hi + ALERT_AFTER)):
                r = recs[k]
                if r["phone"] in phones and (r["at"] <= hi or r["kind"] == "payment_alert"):
                    pick.add(k)
        # the held records themselves, not copies: every reader of records() only reads them or copies them (dedupe)
        return [recs[k] for k in sorted(pick)]


STREAM_PHRASES_FROM = 4          # this many new phrases in one weighing are counted in one read of the case's texts


def _like_test(low: str) -> Callable[[str], bool]:
    """LIKE with ``low`` between wildcards, as a test on a lower-cased text: ``_`` matches any one character, ``%`` any run, ``\\`` escapes."""
    if not any(ch in low for ch in "_%\\"):
        return lambda body: low in body
    out, i = [], 0
    while i < len(low):
        ch = low[i]
        if ch == "\\" and i + 1 < len(low):
            out.append(re.escape(low[i + 1]))
            i += 2
            continue
        out.append("." if ch == "_" else ".*" if ch == "%" else re.escape(ch))
        i += 1
    rx = re.compile("".join(out), re.DOTALL)
    return lambda body: rx.search(body) is not None


EARLIEST = datetime(1, 1, 3, tzinfo=timezone.utc)   # windows this near the calendar's ends go to the database
LATEST = datetime(9999, 12, 29, tzinfo=timezone.utc)
DAY = timedelta(hours=24)        # activity is read from a day before a window to a day after it (CaseStore.activity)
ALERT_AFTER = timedelta(days=3)   # a payment alert is read up to this long after a window's end (CaseStore.phone_records)


def _people_sig(everyone: list[dict]) -> tuple:
    return tuple((p["key"], tuple(p["phones"]), tuple(sorted(p.get("numbers") or ())), tuple(sorted(p.get("handles") or ())),
                  tuple(sorted(p.get("emails") or ())), tuple(p.get("names") or ())) for p in everyone)


def photo_places_as_media(recs: list[dict], photo_refs: set[str]) -> list[dict]:
    """A position read from a photo is a media place: it shows where the photo was taken, and places no one."""
    for r in recs:
        if r["kind"] == "position" and r["ref"] in photo_refs:
            r["kind"] = "media_position"
            r["photo_place"] = True
    return recs


# ---- the case, read once -------------------------------------------------------------------------------------------

class Case:
    def __init__(self, store: FinderStore):
        self.store = store
        self.zone = M.tz(store.zone())
        self.people = {p["key"]: p for p in store.people()}
        period = store.period(list(self.people.values()))
        self.period = period
        if period:
            lo = datetime.combine(period[0], datetime.min.time(), timezone.utc) - timedelta(days=1)
            hi = datetime.combine(period[1], datetime.min.time(), timezone.utc) + timedelta(days=2)
            raw = store.records(list(self.people.values()), [(lo, hi)], list(self.people.values()))
            if hasattr(store, "hold"):
                store.hold(raw, lo, hi, list(self.people.values()))
        else:
            raw = []
        self.recs = [r for r in raw if r.get("at")]
        self.stock: set[str] = set()
        self.photo_places = sum(1 for r in self.recs if r.get("photo_place"))
        phones = {r["phone"] for r in self.recs if r.get("phone")}
        self.phones = sorted(phones)
        self.body_phones: dict[str, set] = defaultdict(set)
        self.body_copies: Counter = Counter()
        self._bkey: dict[int, str] = {}  # id(record) -> its body's key, made once (the detectors asked it again)
        for r in self.recs:
            if r["kind"] in M.CONTACT_KINDS and r.get("body"):
                b = _body_key(r["body"])
                self._bkey[id(r)] = b
                self.body_phones[b].add(r["phone"])
                self.body_copies[b] += 1

    def body_key(self, r: dict) -> str:
        """``_body_key(r["body"])``, made once per record while the case is read."""
        k = getattr(self, "_bkey", {}).get(id(r))
        return k if k is not None else _body_key(r["body"])

    def label(self, key) -> str:
        return (self.people.get(key) or {}).get("label") or "someone"

    def local(self, at: datetime) -> datetime:
        return at.astimezone(self.zone)

    def night(self, at: datetime) -> date:
        return (self.local(at) - NIGHT_SHIFT).date()


def _norm(body: str) -> str:
    return " ".join(str(body or "").split()).casefold()


def _body_key(body: str) -> str:
    """``_norm(body)`` as a fixed-size key: the case-wide counts keep no third copy of every body."""
    return text_key(_norm(body))


def _member(ref: str) -> dict:
    t, _, i = ref.partition(":")
    return {"type": t, "id": i}


def _people_words(case: Case, keys) -> str:
    names = [case.label(k) for k in keys]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _days_words(days) -> str:
    days = sorted(days)
    return ", ".join(f"{d:%-d %b}" for d in days)


def _cand(key, family, title, refs, question, *, kinds, people, detail=None, anchors=()) -> dict:
    return {"key": key, "family": family, "title": title, "refs": list(dict.fromkeys(list(anchors) + list(refs))),
            "question": question, "kinds": kinds, "people": list(people), "detail": detail or {},
            "order": NAMES.get(family, 99)}


def _quote(body: str) -> str:
    return f"“{' '.join(str(body).split())}”"


# ---- detectors -----------------------------------------------------------------------------------------------------

def relays(case: Case) -> list[dict]:
    """Contact through a third number: A and B are each in contact with H within RELAY_WINDOW of each other, on
    MIN_REPEAT nights or more."""
    edges = defaultdict(list)  # hub -> [(at, spoke, ref)]
    for r in case.recs:
        if r["kind"] not in M.CONTACT_KINDS or not r.get("owner"):
            continue
        for p in r.get("parties") or []:
            if p and p != r["owner"]:
                edges[r["owner"]].append((r["at"], p, r["ref"]))
                edges[p].append((r["at"], r["owner"], r["ref"]))
    out = []
    for hub, es in edges.items():
        es.sort()
        by_pair: dict[tuple, dict] = defaultdict(lambda: {"nights": set(), "refs": [], "gaps": []})
        for i, (t1, a, ref1) in enumerate(es):
            for t2, b, ref2 in es[i + 1:]:
                if t2 - t1 > M.RELAY_WINDOW:
                    break
                if a == b or hub in (a, b):
                    continue
                pair = tuple(sorted((a, b)))
                hit = by_pair[pair]
                hit["nights"].add(case.night(t1))
                hit["refs"] += [ref1, ref2]
                hit["gaps"].append((t2 - t1).total_seconds() / 60)
        for (a, b), hit in by_pair.items():
            if len(hit["nights"]) < MIN_REPEAT:
                continue
            gap = round(max(hit["gaps"]))
            title = (f"{case.label(a)} and {case.label(b)} are each in contact with {case.label(hub)}, within "
                     f"{gap} minute{'' if gap == 1 else 's'} of each other, on {len(hit['nights'])} nights")
            out.append(_cand(f"relay:{hub}:{a}:{b}", "relay", title, hit["refs"], {"kind": "every_time"},
                             kinds=["contact", "sequence"], people=[hub, a, b],
                             detail={"nights": sorted(d.isoformat() for d in hit["nights"]), "hub": hub}))
    return out


def _true_positions(case: Case) -> list[dict]:
    return [r for r in case.recs if r["kind"] == "position" and r.get("owner") and r.get("place")
            and (r["place"].get("radius_m") or 0) <= M.TOGETHER_MAX_RADIUS_M]


def _near(x, y) -> bool:
    d = M.haversine_m(x["place"]["lat"], x["place"]["lon"], y["place"]["lat"], y["place"]["lon"])
    return d <= (x["place"].get("radius_m") or 0) + (y["place"].get("radius_m") or 0) + M.TOGETHER_SLACK_M


NEAR_TIERS = (100.0, 500.0, M.TOGETHER_MAX_RADIUS_M)   # radius bands for pairing positions (``_near_pairs``)


def _near_pairs(rs: list[dict]):
    """The pairs of ``combinations(rs, 2)``, in its order, that can be near (``_near``) and belong to two owners. Each
    position is in a radius band; two positions are compared only when they lie in the same or a neighbouring cell of
    a grid sized for their two bands (the farthest two positions of those bands can be apart and still be near), so no
    near pair is left out. On Phone reference 1 every pair of a night's positions took 171 s (18 Nov)."""
    from math import cos, pi, radians
    if len(rs) < 2:
        return
    c = min(cos(radians(r["place"]["lat"])) for r in rs)
    if c < 0.05 or any(abs(r["place"]["lon"]) > 179 for r in rs):
        yield from combinations(rs, 2)  # near a pole or the date line: every pair, as before
        return
    earth = 6_371_000
    tier = [next(t for t, top in enumerate(NEAR_TIERS) if (r["place"].get("radius_m") or 0) <= top) for r in rs]
    # haversine: d >= R |dlat| and d >= (2/pi) R c |dlon| (c the smallest cos(lat)), so with cells this size two
    # positions within ``reach`` are in the same or the next cell
    size = {}
    for a in range(len(NEAR_TIERS)):
        for b in range(len(NEAR_TIERS)):
            reach = NEAR_TIERS[a] + NEAR_TIERS[b] + M.TOGETHER_SLACK_M
            size[a, b] = (reach / earth * 180 / pi, reach / ((2 / pi) * earth * c) * 180 / pi)
    grids: dict[tuple, dict[tuple[int, int], list[int]]] = {}
    for j, r in enumerate(rs):
        for a in range(len(NEAR_TIERS)):
            dlat, dlon = size[a, tier[j]]
            k = (int(r["place"]["lat"] // dlat), int(r["place"]["lon"] // dlon))
            grids.setdefault((a, tier[j]), defaultdict(list))[k].append(j)
    for i, r in enumerate(rs):
        own, a = r["owner"], tier[i]
        js = []
        for b in range(len(NEAR_TIERS)):
            grid = grids.get((a, b))
            if not grid:
                continue
            dlat, dlon = size[a, b]
            ci, cj = int(r["place"]["lat"] // dlat), int(r["place"]["lon"] // dlon)
            js += [j for da in (-1, 0, 1) for db in (-1, 0, 1) for j in grid.get((ci + da, cj + db), ())
                   if j > i and rs[j]["owner"] != own]
        for j in sorted(js):
            yield r, rs[j]


def places(case: Case) -> list[dict]:
    """Phones of different people in the same place (the engine's distance rule) on the same night. Repeated on
    MIN_REPEAT nights: one lead per place with everyone there. Once, with the two within TOGETHER_GAP: one lead per
    pair and place, which the engine weighs (it says "Coincidence likely" when nothing else links them)."""
    pos = _true_positions(case)
    by_night = defaultdict(list)
    for r in pos:
        by_night[case.night(r["at"])].append(r)
    # anchor places: one representative point per ~200 m cell
    groups: dict[tuple, dict] = {}
    for night, rs in by_night.items():
        for x, y in _near_pairs(rs):
            if x["owner"] == y["owner"] or not _near(x, y):
                continue
            cell = (round(x["place"]["lat"] / 0.002), round(x["place"]["lon"] / 0.002))
            g = groups.setdefault(cell, {"nights": defaultdict(set), "refs": defaultdict(set), "close": defaultdict(set),
                                         "lat": x["place"]["lat"], "lon": x["place"]["lon"]})
            g["nights"][night] |= {x["owner"], y["owner"]}
            g["refs"][night] |= {x["ref"], y["ref"]}
            if abs(x["at"] - y["at"]) <= M.TOGETHER_GAP:
                g["close"][night].add(tuple(sorted((x["owner"], y["owner"]))))
    out = []
    for cell, g in groups.items():
        repeated = {n: who for n, who in g["nights"].items() if len(who) >= 2}
        if len(repeated) >= MIN_REPEAT:
            who = Counter(p for ws in repeated.values() for p in ws)
            keys = sorted(p for p, n in who.items() if n >= MIN_REPEAT)
            if len(keys) >= 2:
                refs = [ref for n in repeated for ref in g["refs"][n]
                        if any(r["ref"] == ref and r["owner"] in keys for r in pos)]
                title = (f"{_people_words(case, keys)}: phones in the same place on {len(repeated)} nights "
                         f"({_days_words(repeated)})")
                out.append(_cand(f"place:{cell[0]}:{cell[1]}:{':'.join(keys)}", "place", title, refs,
                                 {"kind": "every_time"}, kinds=["together"], people=keys,
                                 detail={"place": {"lat": g["lat"], "lon": g["lon"]},
                                         "nights": sorted(d.isoformat() for d in repeated)}))
                continue
        for night, pairs in g["close"].items():
            if len(g["nights"]) >= MIN_REPEAT:
                continue
            for a, b in pairs:
                refs = [ref for ref in g["refs"][night] if any(r["ref"] == ref and r["owner"] in (a, b) for r in pos)]
                at = min(r["at"] for r in pos if r["ref"] in refs)
                title = (f"{case.label(a)} and {case.label(b)} in the same place on {case.local(at):%a %-d %b %Y, %H:%M}, "
                         "once")
                out.append(_cand(f"once:{cell[0]}:{cell[1]}:{night.isoformat()}:{a}:{b}", "once", title, refs,
                                 {"kind": "together"}, kinds=["together"], people=[a, b],
                                 detail={"place": {"lat": g["lat"], "lon": g["lon"]}, "night": night.isoformat()}))
    return out


def key_nights(case: Case, weighed: list[tuple[dict, dict]], stated: list[date]) -> dict[date, str]:
    """The key nights: the nights of the strongest contact through a third number (the relay leads at the best level
    the engine gave any of them, Strong or Probable); with none, the nights of the strongest repeated place; and the
    incident dates the case's theories state. Each with its first record, to anchor a question to that night.
    *Reverse if* a case's planning signal is not contact through a third number: then the place leads lead."""
    nights: set[date] = set(stated)
    for family in ("relay", "place"):
        best = None
        for c, result in weighed:
            if c["family"] != family:
                continue
            key = (result.get("level") or {}).get("key")
            if key in ("strong", "probable"):
                rank = ("strong", "probable").index(key)
                best = rank if best is None else min(best, rank)
        if best is None:
            continue
        top = ("strong", "probable")[best]
        for c, result in weighed:
            if c["family"] == family and (result.get("level") or {}).get("key") == top:
                nights |= {date.fromisoformat(d) for d in c["detail"].get("nights", [])}
        break
    anchors = {}
    refs = {r for c, _ in weighed if c["family"] in ("relay", "place") for r in c["refs"]}
    for n in sorted(nights):
        first = [r for r in case.recs if r["ref"] in refs and case.night(r["at"]) == n and r["kind"] in M.CONTACT_KINDS]
        first = first or [r for r in case.recs if case.night(r["at"]) == n and r["kind"] in M.CONTACT_KINDS]
        if first:
            anchors[n] = min(first, key=lambda r: r["at"])["ref"]
    return anchors


def payments_after(case: Case, keys: dict[date, str]) -> list[dict]:
    """The same amount from one person to another within MONEY_SPREAD after the key nights, on MIN_REPEAT of them."""
    if len(keys) < MIN_REPEAT:
        return []
    money = [r for r in case.recs if r["kind"] in M.MONEY_KINDS and r.get("owner") and r.get("parties")]
    by = defaultdict(lambda: {"nights": set(), "refs": []})
    for r in money:
        for n in keys:
            start = datetime.combine(n, datetime.min.time(), case.zone) + NIGHT_SHIFT
            if timedelta(0) <= r["at"] - start <= M.MONEY_SPREAD + timedelta(hours=12):
                for p in r["parties"]:
                    g = by[(r["owner"], p, abs(r.get("amount_minor") or 0))]
                    g["nights"].add(n)
                    g["refs"].append(r["ref"])
    groups = {k: v for k, v in by.items() if len(v["nights"]) >= MIN_REPEAT}
    out = []
    by_payer = defaultdict(list)
    for (payer, payee, amount), g in groups.items():
        by_payer[payer].append((payee, amount, g))
    for payer, items in by_payer.items():
        items.sort(key=lambda x: x[1])
        words = "; ".join(f"{M.fmt_money(a)} to {case.label(p)} after {len(g['nights'])} of the {len(keys)} key nights"
                          for p, a, g in items)
        refs = [ref for _, _, g in items for ref in g["refs"]]
        nights = set().union(*(g["nights"] for _, _, g in items))
        people = [payer] + list(dict.fromkeys(p for p, _, _ in items))
        anchors = [keys[n] for n in sorted(nights) if n in keys]
        out.append(_cand(f"money:{payer}:{':'.join(sorted(set(p for p, _, _ in items)))}", "money",
                         f"{case.label(payer)} pays the same amounts after the key nights: {words}", refs,
                         {"kind": "payment", "chips": {"people": people}}, kinds=["money"], people=people,
                         anchors=anchors, detail={"nights": sorted(n.isoformat() for n in nights)}))
    return out


CASH_AFTER_DAYS = 4  # a deposit on the Monday after a Friday key night is 3 days on


def cash_splits(case: Case, keys: dict[date, str]) -> list[dict]:
    """Cash deposits just under the $10,000 reporting threshold (model.STRUCTURING_*), two or more by one person."""
    by = defaultdict(list)
    for r in case.recs:
        amt = abs(r.get("amount_minor") or 0)
        if not (M.STRUCTURING_FROM_MINOR <= amt < M.STRUCTURING_BELOW_MINOR):
            continue
        if r.get("cash_deposit") or (r["kind"] == "payment_alert" and "deposit" in (r.get("body") or "").casefold()):
            by[r.get("owner") or (r.get("parties") or [None])[0]].append(r)
    out = []
    for who, rs in by.items():
        if not who or len({case.night(r["at"]) for r in rs}) < 2:
            continue
        days = sorted({r["at"].date() for r in rs})
        # the key nights each followed by one of these deposits within CASH_AFTER_DAYS, so the engine weighs the
        # deposits against those nights (as payments_after does) and not on their own
        after = sorted(n for n in keys if any(0 <= (d - n).days <= CASH_AFTER_DAYS for d in days))
        title = (f"{len(days)} cash deposits just under $10,000 by {case.label(who)} ({_days_words(days)})"
                 + (f", each within {CASH_AFTER_DAYS} days after a key night" if len(after) >= len(days) else ""))
        out.append(_cand(f"cash:{who}", "cash", title, [r["ref"] for r in rs], {"kind": "every_time",
                                                                                 "chips": {"people": [who]}},
                         kinds=["money"], people=[who], anchors=[keys[n] for n in after] if len(after) >= MIN_REPEAT else [],
                         detail={"days": [d.isoformat() for d in days], "after_key_nights": [n.isoformat() for n in after]}))
    return out


def silences(case: Case, keys: dict[date, str]) -> list[dict]:
    """A phone with nothing at all for M.SILENCE_MIN or more inside the night, on MIN_REPEAT of the key nights."""
    if len(keys) < MIN_REPEAT:
        return []
    out = []
    windows = []
    for n in keys:
        lo = datetime.combine(n, datetime.min.time(), case.zone).replace(hour=SILENCE_FROM)
        windows.append((n, lo, lo + timedelta(hours=24 - SILENCE_FROM + SILENCE_TO)))
    act = case.store.activity(list(case.people.values()), [(lo, hi) for _, lo, hi in windows])
    for key, times in act.items():
        if not times:
            continue
        quiet, refs = [], []
        for n, lo, hi in windows:
            inside = [t for t in times if lo <= t <= hi]
            if not inside:
                continue
            edges = [lo] + inside + [hi]
            longest = max(b - a for a, b in zip(edges, edges[1:]))
            if longest >= M.SILENCE_MIN:
                quiet.append(n)
        if len(quiet) < MIN_REPEAT:
            continue
        last = [max((r for r in case.recs if r.get("owner") == key and case.night(r["at"]) == n and
                     r["kind"] in M.CONTACT_KINDS), key=lambda r: r["at"],
                    default=None) for n in quiet]
        refs = [r["ref"] for r in last if r]
        title = f"{case.label(key)}'s phone goes silent overnight on {len(quiet)} of the {len(keys)} key nights"
        out.append(_cand(f"silence:{key}", "silence", title, refs, {"kind": "every_time", "chips": {"people": [key]}},
                         kinds=["absence"], people=[key], anchors=[keys[n] for n in quiet],
                         detail={"nights": [n.isoformat() for n in quiet]}))
    return out


def stock_phrases(case: Case) -> list[dict]:
    """Words at least LONG_TEXT long on most of the case's phones (the whole case, every date): a stock phrase, set
    aside, never shared wording."""
    n_phones = max(len(case.phones), 1)
    rows = case.store.q(
        "SELECT lower(regexp_replace(btrim(body), '\\s+', ' ', 'g')) AS b, count(DISTINCT extraction_id), count(*) "
        "FROM phone_comm_events WHERE case_id = :c AND length(btrim(body)) >= :n GROUP BY 1 HAVING "
        "count(DISTINCT extraction_id) >= 3", n=LONG_TEXT).all()
    kept = [(body, phones, copies) for body, phones, copies in sorted(rows, key=lambda r: -r[2])
            if phones / n_phones >= STOCK_SHARE]
    # one pass over the records for every stock phrase (was one pass per phrase: phrases x records on a large case)
    refs: dict[str, list] = {body: [] for body, _, _ in kept}
    by_key = {text_key(body): refs[body] for body in refs}
    if refs:
        for r in case.recs:
            if r.get("body"):
                hit = by_key.get(case.body_key(r))
                if hit is not None and len(hit) < 200:
                    hit.append(r["ref"])
    out = []
    for body, phones, copies in kept:
        case.stock.add(body)
        out.append({"key": f"stock:{body[:150]}", "title": _quote(body),
                    "summary": f"{_quote(body)} is on {phones} of the {n_phones} phones, {copies} times: a stock "
                               "phrase, not shared wording.", "kinds": ["shared_content"],
                    "refs": refs[body]})
    return out


def words(case: Case, keys: dict[date, str], taken: set[str]) -> list[dict]:
    """The same words from one sender on MIN_REPEAT key nights or more, rare on other nights, not a stock phrase.
    Words exchanged between the same people on the same nights make one lead (a message and its answer)."""
    by = defaultdict(list)
    for r in case.recs:
        if r["kind"] in M.CONTACT_KINDS and r.get("body") and r.get("sender") and r["ref"] not in taken:
            by[(r["sender"], _norm(r["body"]))].append(r)
    groups: dict[tuple, list] = defaultdict(list)
    for (sender, body), rs in by.items():
        nights = {case.night(r["at"]) for r in rs}
        on_key = nights & set(keys)
        if len(on_key) < MIN_REPEAT or len(nights - set(keys)) > len(on_key) // 2 or body in case.stock:
            continue
        who = frozenset([sender] + [p for r in rs for p in (r.get("parties") or []) if p])
        groups[(who, frozenset(on_key))].append(sorted(rs, key=lambda r: r["at"]))
    out = []
    for (who, on_key), seqs in groups.items():
        seqs.sort(key=lambda rs: rs[0]["at"])
        first = seqs[0][0]
        others = sorted(p for p in who if p != first["sender"])
        local = case.local(first["at"])
        title = (f"{case.label(first['sender'])} writes {_quote(first['body'])}"
                 + (f" to {_people_words(case, others)}" if others else "")
                 + f" at {local:%H:%M} on {len(on_key)} of the {len(keys)} key nights")
        if len(seqs) > 1:
            title += "; " + "; ".join(f"{case.label(rs[0]['sender'])}: {_quote(rs[0]['body'])}" for rs in seqs[1:3])
            if len(seqs) > 3:
                title += f" and {len(seqs) - 3} more"
        refs = [r["ref"] for rs in seqs for r in rs]
        out.append(_cand(f"words:{':'.join(sorted(who))}:{min(on_key).isoformat()}:{len(on_key)}", "words", title,
                         refs, {"kind": "every_time"}, kinds=["shared_content"], people=sorted(who),
                         detail={"nights": sorted(n.isoformat() for n in on_key),
                                 "threads": sorted({r.get("thread") for rs in seqs for r in rs if r.get("thread")})}))
    return out


def deletions(case: Case) -> list[dict]:
    """A message deleted on one phone whose copy is kept on another (same words, same minute), when its words are
    rare in the case (held at most RARE_COPIES times)."""
    out = []
    kept = defaultdict(list)
    for r in case.recs:
        if r["kind"] in M.CONTACT_KINDS and r.get("body") and not r.get("deleted"):
            kept[(case.body_key(r), r["at"].replace(second=0, microsecond=0))].append(r)
    for r in case.recs:
        if r["kind"] not in M.CONTACT_KINDS or not r.get("deleted") or not r.get("body"):
            continue
        b = case.body_key(r)
        if case.body_copies[b] > RARE_COPIES:
            continue
        copies = [x for x in kept.get((b, r["at"].replace(second=0, microsecond=0)), []) if x["phone"] != r["phone"]]
        if not copies:
            continue
        who = case.label(r.get("owner"))
        there = _people_words(case, sorted({x.get("owner") for x in copies if x.get("owner")}))
        title = f"{_quote(r['body'])}: deleted on {who}'s phone, still on {there}'s"
        people = [k for k in dict.fromkeys([r.get("owner")] + [x.get("owner") for x in copies]) if k]
        out.append(_cand(f"deleted:{r['ref']}", "deleted", title, [r["ref"]] + [x["ref"] for x in copies], {},
                         kinds=["absence", "shared_content"], people=people,
                         detail={"at": r["at"].isoformat()}))
    return out


GAP_MATCH_DAYS = 3  # a bank row within this many days of an alert, same payer and amount, is the same payment


def statement_gaps(case: Case, ledger_months: dict[str, set[str]] | None = None) -> list[dict]:
    """Payments the phones' alerts show and the payer's bank rows do not, for an amount the payer's bank rows do
    confirm in other months: part of a statement (the month holds other rows) or all of it is missing. Nothing is
    weighed on such a payment until the rows arrive, so the lead is Can't tell. ``ledger_months`` is
    ``{person key: {"YYYY-MM", ...}}``, the months each payer's accounts hold any row (read from the store)."""
    alerts, rows = {}, defaultdict(list)
    for r in case.recs:
        if r["kind"] == "payment_alert" and r.get("owner") and r.get("amount_minor"):
            alerts.setdefault(r.get("dup_key") or r["ref"], []).append(r)
        elif r["kind"] == "payment" and r.get("owner"):
            rows[r["owner"]].append(r)
    found, matched = defaultdict(list), set()
    for copies in alerts.values():
        a = copies[0]
        payer, amt = a["owner"], abs(a["amount_minor"])
        day = case.local(a["at"]).date()
        hit = any(abs(x.get("amount_minor") or 0) == amt and abs((x["at"].date() - day).days) <= GAP_MATCH_DAYS
                  for x in rows[payer])
        if hit:
            matched.add((payer, amt, f"{day:%Y-%m}"))
        elif (case.people.get(payer) or {}).get("accounts"):
            found[(payer, f"{day:%Y-%m}")].append(copies)
    if ledger_months is None:
        ledger_months = {}
        for payer in {p for p, _ in found}:
            got = case.store.ledger_months([case.people[payer]]) if case.store is not None else {}
            ledger_months[payer] = {m for ms in got.values() for m in ms}
    out = []
    for (payer, month), groups in found.items():
        # only amounts the payer's bank rows confirm in another month: those rows are known to reach the ledger
        groups = [g for g in groups if any(p == payer and a == abs(g[0]["amount_minor"]) and m != month
                                           for p, a, m in matched)]
        if not groups:
            continue
        amounts = {abs(g[0]["amount_minor"]) for g in groups}
        days = sorted({case.local(g[0]["at"]).date() for g in groups})
        holders = sorted({c.get("phone_owner") or c.get("owner") for g in groups for c in g} - {None})
        mon = datetime.strptime(month, "%Y-%m").strftime("%B")
        amount_words = " and ".join(M.fmt_money(a) for a in sorted(amounts))
        title = (f"{mon} payments: the alerts show {amount_words} from {case.label(payer)} on "
                 f"{_days_words(days)}, but the bank rows are missing")
        part = month in ledger_months.get(payer, set())
        missing = [{"missing": f"{case.label(payer)}'s bank rows for {_days_words(days)}",
                    "words": (f"{case.label(payer)}'s {mon} statement holds other rows, but none for these "
                              if part else f"{case.label(payer)}'s {mon} statement is not in the case, so nothing "
                              "confirms these ") +
                             f"{len(groups)} payments, which the alerts show and the bank rows confirm in other "
                             "months. " + ("Part of the statement is missing" if part else "Ask for the statement") +
                             ": it would settle these payments."}]
        out.append({"key": f"gap:{payer}:{month}", "title": title, "summary": missing[0]["words"],
                    "refs": [c["ref"] for g in groups for c in g], "kinds": ["money"], "people": [payer],
                    "missing": missing, "days": [d.isoformat() for d in days]})
    return out


def set_aside_names(case: Case) -> list[dict]:
    """A name saved on a phone, or in the ledger, that shares a name with a person but is another number."""
    out = []
    for key, p in case.people.items():
        if not key.startswith("person:"):
            continue
        for x in case.store.lookalike_names(p):
            if x.get("where") != "saved on a phone":
                continue
            out.append({"key": f"name:{key}:{x['value']}", "title": f"“{x['name']}”",
                        "summary": f"“{x['name']}” saved on a phone is {x['value']}, another number: not "
                                   f"{p['label']}.", "kinds": ["contact"], "refs": []})
    return out


MEDIA_FILE = r"\.(jpe?g|png|heic|gif|webp|mp4|mov|3gp|m4a|opus|amr|aac|pdf)$"


def common_files(case: Case) -> list[dict]:
    """Photos, videos, voice notes and documents byte-identical on most of the case's phones: common files, counted
    for nothing. One entry names them all (the first 10 by name, with the whole count)."""
    n_phones = max(len(case.phones), 1)
    rows = case.store.q(
        "SELECT e.sha256, min(regexp_replace(e.relpath, '^.*[\\\\/]', '')), count(DISTINCT e.extraction_id) FROM "
        "phone_container_entries e JOIN phone_extractions x ON x.id = e.extraction_id WHERE x.case_id = :c AND "
        "x.standing = 'active' AND e.sha256 IS NOT NULL AND e.relpath ~* :rx GROUP BY e.sha256 HAVING "
        "count(DISTINCT e.extraction_id) >= 3", rx=MEDIA_FILE).all()
    common = sorted((str(name), n) for _, name, n in rows if n / n_phones >= STOCK_SHARE)
    if not common:
        return []
    names = [name for name, _ in common]
    shown = " and ".join(names[:2]) if len(names) <= 2 else ", ".join(names[:10]) + (
        f" and {len(names) - 10} more" if len(names) > 10 else "")
    most = max(n for _, n in common)
    return [{"key": "files:common", "title": shown,
             "summary": f"{'Files' if len(names) > 1 else 'The file'} {shown} {'are' if len(names) > 1 else 'is'} "
                        f"byte-identical on {most} of the {n_phones} phones: common files, counted for nothing.",
             "kinds": ["shared_content"], "refs": []}]


def explained_payments(case: Case, keys: dict[date, str]) -> list[dict]:
    """A payment of the same amount to the same payee every month, from an account of a case person, that started
    before the first key night and whose amount and payee a document names (a lease, an invoice): a regular payment
    the document explains, set aside with the document named. Read over the whole ledger, every date."""
    if not keys:
        return []
    first = min(keys)
    holders = {a: k for k, p in case.people.items() for a in p["accounts"]}
    if not holders:
        return []
    rows = case.store.q(
        "SELECT account_id, amount_minor, upper(regexp_replace(COALESCE(counterparty_raw, '') || ' ' || "
        "COALESCE(description, ''), '\\s+', ' ', 'g')), min(COALESCE(transaction_date, posted_date)), "
        "count(DISTINCT date_trunc('month', COALESCE(transaction_date, posted_date))), array_agg(id::text) FROM "
        "financial_transactions WHERE case_id = :c AND superseded_by_id IS NULL AND direction = 'debit' AND "
        "account_id = ANY(CAST(:a AS uuid[])) GROUP BY 1, 2, 3 HAVING count(DISTINCT date_trunc('month', "
        "COALESCE(transaction_date, posted_date))) >= :n", a=list(holders), n=MIN_REPEAT).all()
    out = []
    for acc, amount, words_, since, months, ids in rows:
        if not since or since >= first:
            continue
        payer = holders.get(str(acc))
        figure = f"{abs(amount) // 100:,}"
        hits = []
        for fid, name, content in case.store.q(
                "SELECT f.id, f.original_filename, t.content FROM evidence_document_texts t JOIN evidence_files f ON "
                "f.id = t.evidence_file_id WHERE f.case_id = :c AND f.deleted_at IS NULL AND t.content ~ :fig",
                fig=re.escape(figure)):
            if any(M.names_match(n, content or "") for n in case.people[payer]["names"] if n) and \
                    any(w in (content or "").upper() for w in words_.split() if len(w) >= 4 and not w.isdigit()):
                hits.append(str(name or fid))
        if not hits:
            continue
        payee = " ".join(w for w in words_.split() if not w.isdigit()).title()
        title = f"{M.fmt_money(abs(amount))} a month from {case.label(payer)}: {payee}"
        summary = (f"{case.label(payer)}'s {M.fmt_money(abs(amount))} a month ({payee}) is paid since {since:%-d %b %Y}, "
                   f"{months} months in the ledger, before the first key night ({first:%-d %b %Y}); "
                   f"{', '.join(hits[:3])} name{'s' if len(hits) == 1 else ''} the amount: a regular payment, not one "
                   "timed to the nights.")
        out.append({"key": f"regular:{acc}:{amount}", "title": title, "summary": summary, "kinds": ["money"],
                    "refs": [f"financial_transaction:{i}" for i in ids][:200], "documents": hits})
    return out


# ---- running -------------------------------------------------------------------------------------------------------

def _stated_dates(db, case_id) -> list[date]:
    """Incident dates the case's theories and findings state in their own words (``incidents.incident_dates``)."""
    from services.corroborate import incidents
    out = []
    for f in incidents.incident_dates(db, case_id):
        try:
            out.append(date.fromisoformat(str(f.get("date"))[:10]))
        except (TypeError, ValueError):
            continue
    return out


def find(db, case_id, *, user=None, progress: Callable[[str], None] | None = None,
         runner: Callable | None = None) -> dict[str, Any]:
    """Run every detector, weigh every candidate, save every lead. Returns counts and seconds."""
    from services import case_selections
    from services.corroborate import engine, levels
    from services.leads import store as leads
    step = progress or (lambda *_: None)
    started = time.time()
    st = FinderStore(db, case_id)
    step("Reading the case")
    case = Case(st)
    t_read = time.time() - started
    step("Looking for patterns")
    run = runner or (lambda members, question: engine.run(st, members, question))
    saved, by_level, keys_seen = [], Counter(), set()

    def weigh_and_save(cands, i0, total):
        out = []
        for i, c in enumerate(cands, i0):
            step(f"Weighing lead {i} of about {total}")
            members = [_member(r) for r in c["refs"]][:case_selections.MAX_MEMBERS]
            result = run(members, c["question"])
            out.append((c, result))
            sel = _selection(db, case_id, members, c, user)
            if sel is None:
                by_level["not_saved"] += 1
                continue
            lead = leads.save(db, case_id, origin="found_by_loupe", selection_id=sel, result=result, members=members,
                              title=c["title"], summary=(result.get("level") or {}).get("sentence") or "",
                              finder_key=c["key"], kinds=c["kinds"], question=c["question"], user=user,
                              detail={**c["detail"], "family": c["family"], "order": c["order"],
                                      "photo_places_not_counted": case.photo_places})
            saved.append(lead)
            keys_seen.add(c["key"])
            by_level[lead["level"]["key"]] += 1
        return out

    first = relays(case) + places(case)
    weighed = weigh_and_save(first, 1, len(first))
    stated = _stated_dates(db, case_id)
    keys = key_nights(case, weighed, stated)
    pattern = key_nights(case, weighed, [])  # the pattern's own nights, without dates the theories state
    aside = stock_phrases(case)
    taken = {r for c in first if c["family"] == "relay" for r in c["refs"]}
    second = payments_after(case, keys) + cash_splits(case, keys) + silences(case, keys) + \
        words(case, keys, taken) + deletions(case)
    weigh_and_save(second, len(first) + 1, len(first) + len(second))
    cands = first + second
    aside += common_files(case) + set_aside_names(case) + explained_payments(case, keys)
    # people in no lead at Possible or above: is this person connected at all, over the key nights?
    linked = {p["key"] for x in saved if x["level"]["key"] in ("strong", "probable", "possible") for p in x["people"]}
    # asked over the pattern's own nights: a date a theory states is a claim to test, not a night of the pattern
    anchors = [pattern[n] for n in sorted(pattern)]
    for key, p in case.people.items():
        if key in linked or not key.startswith("person:") or not anchors:
            continue
        step(f"Checking {p['label']}")
        members = [_member(r) for r in anchors]
        q = {"kind": "connected", "chips": {"person": key, "people": [key] + sorted(linked)}}
        result = run(members, q)
        lv = (result.get("level") or {}).get("key")
        c = {"key": f"nolink:{key}", "family": "nolink", "order": 100, "detail": {}}
        sel = _selection(db, case_id, members, c, user)
        if sel is None:
            by_level["not_saved"] += 1
            continue
        title = (f"{p['label']}: no link found" if lv == "no_link_found" else
                 f"Is {p['label']} connected to the others on the key nights?")
        lead = leads.save(db, case_id, origin="found_by_loupe", selection_id=sel, result=result, members=members,
                          title=title, summary=(result.get("level") or {}).get("sentence") or "",
                          finder_key=c["key"], question=q, user=user,
                          detail={"family": "nolink", "order": 100, "person": key})
        saved.append(lead)
        keys_seen.add(c["key"])
        by_level[lv] += 1
    for a in aside:
        members = [_member(r) for r in a["refs"]][:case_selections.MAX_MEMBERS]
        sel = _selection(db, case_id, members or [{"type": "person", "id": k.split(":", 1)[1]} for k in case.people
                                                  if k.startswith("person:")][:1], {"key": a["key"]}, user)
        if sel is None:
            by_level["not_saved"] += 1
            continue
        lead = leads.save(db, case_id, origin="found_by_loupe", selection_id=sel, result={}, members=members,
                          title=a["title"], summary=a["summary"], finder_key=a["key"], kinds=a["kinds"],
                          level={**leads.SET_ASIDE, "sentence": a["summary"], "rule": a["key"].split(":")[0]},
                          raises=[], lowers=[a["summary"]], user=user,
                          detail={"family": "set_aside", "order": 200, **({"documents": a["documents"]}
                                                                        if a.get("documents") else {})})
        saved.append(lead)
        keys_seen.add(a["key"])
        by_level["set_aside"] += 1
    for g in statement_gaps(case):
        members = [_member(r) for r in g["refs"]][:case_selections.MAX_MEMBERS]
        sel = _selection(db, case_id, members, {"key": g["key"]}, user)
        if sel is None:
            by_level["not_saved"] += 1
            continue
        level = levels.records_missing(g["missing"])
        # nothing is weighed: the result only names who and when, for the lists that filter by them
        shape = {"people": [{"key": k, "label": case.label(k)} for k in g["people"]],
                 "comparison": {"incident": [{"id": d, "start": d, "end": d} for d in g["days"]]}}
        lead = leads.save(db, case_id, origin="found_by_loupe", selection_id=sel, result=shape, members=members,
                          title=g["title"], summary=g["summary"], finder_key=g["key"], kinds=g["kinds"], level=level,
                          raises=[], lowers=[m["words"] for m in g["missing"]], user=user,
                          detail={"family": "gap", "order": 90, "days": g["days"], "people": g["people"]})
        saved.append(lead)
        keys_seen.add(g["key"])
        by_level["cant_tell"] += 1
    gone = _withdraw_stale(db, case_id, keys_seen)
    return {"candidates": len(cands), "saved": len(saved), "by_level": dict(by_level), "key_nights": len(keys), "key_night_dates": [n.isoformat() for n in sorted(keys)],
            "stated_dates": sorted({d.isoformat() for d in stated}),
            "photo_places_not_counted": case.photo_places, "records_read": len(case.recs),
            "no_longer_found": gone, "seconds": round(time.time() - started, 1), "read_seconds": round(t_read, 1)}


def _selection(db, case_id, members, cand, user) -> str | None:
    """The lead's records, kept as one group (``case_selections``) so the lead can be re-asked and shown."""
    from services import case_selections
    if not members:
        return None
    try:
        return case_selections.freeze(db, case_id=case_id, group_type="relation_query", members=members,
                                      how={"surface": "relation", "lead_finder": cand["key"]},
                                      words="Found by Loupe's lead finder", user=user, commit=False)["id"]
    except case_selections.SelectionError:
        db.rollback()
        return None


def _withdraw_stale(db, case_id, keys_seen: set[str]) -> int:
    """A finder lead not found on this run stays, with its state and history; it is marked no longer watched and
    the history says it was not found again. Never deleted."""
    from postgres.models.corroborate import CorroborateWatch
    n = 0
    now = datetime.now(timezone.utc).isoformat()
    for w in db.scalars(select(CorroborateWatch).where(CorroborateWatch.case_id == uuid.UUID(str(case_id)),
                                                      CorroborateWatch.origin == "found_by_loupe",
                                                      CorroborateWatch.finder_key.is_not(None))):
        if w.finder_key in keys_seen or not w.active:
            continue
        w.active = False
        w.history = list(w.history or []) + [{"at": now, "from": w.level, "to": w.level,
                                              "reason": "Not found again on new material."}]
        n += 1
    db.commit()
    return n


# ---- run bookkeeping -----------------------------------------------------------------------------------------------

def last_run(db, case_id) -> dict[str, Any]:
    from postgres.models.corroborate import LeadFinderRun
    r = db.scalars(select(LeadFinderRun).where(LeadFinderRun.case_id == uuid.UUID(str(case_id)))
                   .order_by(LeadFinderRun.started_at.desc())).first()
    if r is None:
        return {"status": "never", "words": "Loupe has not looked for leads in this case yet."}
    from services.corroborate import facts
    status, error = r.status, r.error
    if _stale(r):
        status, error = "failed", STALE_WORDS
    changed = status in ("done", "failed") and (r.material or {}) != facts.material(db, case_id)
    return {"id": str(r.id), "status": status, "step": r.step, "trigger": r.trigger, "counts": r.counts or {},
            "error": error, "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None, "new_material": changed}


def start(db, case_id, *, user=None, trigger: str = "button", session_factory=None, inline: bool = False) -> dict:
    """Record a run and do it in the background (or inline, for tests and scripts). One run per case at a time."""
    from postgres.models.corroborate import LeadFinderRun
    from services.corroborate import facts
    busy = db.scalars(select(LeadFinderRun).where(LeadFinderRun.case_id == uuid.UUID(str(case_id)),
                                                  LeadFinderRun.status.in_(("queued", "running")))).first()
    if busy is not None and not _stale(busy):
        return last_run(db, case_id)
    if busy is not None:
        _fail(db, busy, STALE_WORDS)
    row = LeadFinderRun(id=uuid.uuid4(), case_id=uuid.UUID(str(case_id)), status="queued", step="Waiting to start",
                        trigger=trigger, requested_by=getattr(user, "id", None), material=facts.material(db, case_id))
    db.add(row)
    db.commit()
    if inline:
        _work(str(row.id), str(case_id), lambda: db, own=False)
    else:
        try:
            if session_factory is None:
                from postgres.session import _get_background_session_local
                session_factory = _get_background_session_local()
            threading.Thread(target=_work, args=(str(row.id), str(case_id), session_factory), daemon=True,
                             name=f"lead-finder-{row.id}").start()
        except Exception as exc:  # noqa: BLE001 - a run that cannot start says so, and never blocks the next one
            log.exception("lead finder run %s could not start", row.id)
            _fail(db, row, f"Could not start: {type(exc).__name__}: {exc}"[:2000])
    return last_run(db, case_id)


STALE_WORDS = "Stopped before it finished (the server restarted, or the run could not start). Look again."
QUEUED_STALE = timedelta(minutes=10)   # a run starts at once, so one still queued after this never started
RUNNING_STALE = timedelta(hours=3)     # a running row with no beat at all (written before the heartbeat existed)
BEAT_EVERY = 60                        # seconds between beats while the run's thread is alive
BEAT_STALE = timedelta(minutes=15)     # no beat for this long: the thread ended with its server (a release restart)


def _utc(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _stale(row) -> bool:
    if row.status not in ("queued", "running") or row.started_at is None:
        return False
    now = datetime.now(timezone.utc)
    if row.status == "queued":
        return now - _utc(row.started_at) > QUEUED_STALE
    beat = getattr(row, "beat_at", None)
    if beat is not None:
        return now - _utc(beat) > BEAT_STALE
    return now - _utc(row.started_at) > RUNNING_STALE


def _beat(run_id: str, session_factory, stop: threading.Event, every: float = BEAT_EVERY) -> None:
    """Stamp the run's beat until it stops. Its own session, so a long step never delays it; it ends with the process,
    which is the point: a restart leaves an old beat behind, and the next press starts a new run."""
    from postgres.models.corroborate import LeadFinderRun
    while not stop.wait(every):
        session = session_factory()
        try:
            row = session.get(LeadFinderRun, uuid.UUID(run_id))
            if row is None or row.status != "running":
                return
            row.beat_at = datetime.now(timezone.utc)
            session.commit()
        except Exception:  # noqa: BLE001 - a missed beat is retried next minute; 15 missed ones end the run's claim
            log.warning("lead finder run %s: beat failed", run_id, exc_info=True)
            session.rollback()
        finally:
            session.close()


def _fail(db, row, words: str) -> None:
    row.status, row.error, row.step = "failed", words, "Stopped"
    row.finished_at = datetime.now(timezone.utc)
    db.commit()


def _work(run_id: str, case_id: str, session_factory, own: bool = True) -> None:
    from types import SimpleNamespace
    from postgres.models.corroborate import LeadFinderRun
    session = session_factory()
    stop = threading.Event()
    try:
        row = session.get(LeadFinderRun, uuid.UUID(run_id))
        row.status, row.step, row.beat_at = "running", "Reading the case", datetime.now(timezone.utc)
        session.commit()
        if own:  # a background run beats on its own thread; an inline run (tests, scripts) beats with each step
            threading.Thread(target=_beat, args=(run_id, session_factory, stop), daemon=True,
                             name=f"lead-finder-beat-{run_id}").start()

        def progress(words):
            row.step, row.beat_at = words, datetime.now(timezone.utc)
            session.commit()
        counts = find(session, case_id, user=SimpleNamespace(id=row.requested_by), progress=progress)
        row = session.get(LeadFinderRun, uuid.UUID(run_id))
        row.status, row.step, row.counts = "done", "Done", counts
        row.finished_at = datetime.now(timezone.utc)
        session.commit()
    except Exception as exc:  # noqa: BLE001 - the run fails visibly, with the reason
        log.exception("lead finder run %s failed", run_id)
        session.rollback()
        row = session.get(LeadFinderRun, uuid.UUID(run_id))
        if row is not None:
            row.status, row.error, row.step = "failed", f"{type(exc).__name__}: {exc}"[:2000], "Stopped"
            row.finished_at = datetime.now(timezone.utc)
            session.commit()
    finally:
        stop.set()
        if own:
            session.close()
