"""An invented case for the Corroborate tests: three people, a prepaid phone and an outsider, over ten Fridays.

On three Fridays (the incidents) the prepaid phone texts Ann at 22:00 and Bob at 22:05, Ann's badge opens a gate at
23:00, Bob and the prepaid phone are together at a yard at 23:30, Ann's phone is silent from 23:00 to 04:00, and Ann
pays Bob $400 the next day (a ledger row and an alert on Bob's phone: one payment). Every day Ann and Bob message at
noon (routine). Dan, the outsider, messages no one in the pattern; once he is at a shop at the same time as Bob.
All names, numbers and places are invented here and appear nowhere in the rules.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone

UTC = timezone.utc
FRIDAYS = [date(2025, 1, 3) + timedelta(days=7 * n) for n in range(10)]
INCIDENTS = [FRIDAYS[2], FRIDAYS[5], FRIDAYS[8]]
YARD = (51.5000, -0.1000)
SHOP = (51.6000, -0.2000)


def at(day: date, h: int, m: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, h, m, tzinfo=UTC)


def person(key, label, numbers, phones, accounts=(), dossier=True):
    return {"key": key, "label": label, "dossier_id": key if dossier else None, "numbers": set(numbers),
            "handles": set(), "emails": set(), "accounts": list(accounts), "phones": list(phones),
            "names": [label] if dossier else [], "links": [{"identifier": "+" + n, "how": "recorded", "basis": "test"}
                                                           for n in numbers], "phone_labels": {p: p for p in phones}}


PEOPLE = [person("ann", "Ann Arden", ["15550001"], ["phA"], ["accA"]),
          person("bob", "Bob Brook", ["15550002"], ["phB"]),
          person("pre", "the user of Phone C", ["15550003"], ["phC"], dossier=False),
          person("dan", "Dan Dale", ["15550004"], ["phD"])]


def _msg(ref, owner, other, when, body, sender=None):
    num = {"ann": "15550001", "bob": "15550002", "pre": "15550003", "dan": "15550004"}[other]
    return {"ref": ref, "kind": "message", "at": when, "phone": "ph" + owner[0].upper(), "owner": owner,
            "parties": [other], "counterpart_values": [num], "body": body, "sender": sender or owner,
            "dup_key": ("msg", when.replace(second=0), body, frozenset([owner, other]))}


def build_records(burst_only=False):
    recs = []
    days = [FRIDAYS[0] + timedelta(days=n) for n in range(70)]
    for d in days:  # routine noon messages, every day
        recs.append(_msg(f"r:{d}", "ann", "bob", at(d, 12), f"lunch {d.day}?"))
        for p in ("ann", "bob", "pre", "dan"):  # every phone ticks every hour except in its gaps
            for h in range(24):
                if p == "ann" and d in INCIDENTS and h >= 23:
                    continue
                if p == "ann" and d - timedelta(days=1) in INCIDENTS and h < 4:
                    continue
                recs.append({"ref": f"t:{p}:{d}:{h}", "kind": "activity", "at": at(d, h, 30), "owner": p})
    for d in INCIDENTS:
        nxt = d + timedelta(days=1)
        recs += [_msg(f"m1:{d}", "pre", "ann", at(d, 22), "the gate code is 4471"),
                 _msg(f"m1c:{d}", "ann", "pre", at(d, 22), "the gate code is 4471", sender="pre"),
                 _msg(f"m2:{d}", "pre", "bob", at(d, 22, 5), "yard at half eleven"),
                 {"ref": f"doc:{d}", "kind": "doc_row", "at": at(d, 23), "parties": ["ann"], "body": "ARDEN, ANN gate",
                  "source": "log1", "source_label": "gate-log.csv"},
                 {"ref": f"pB:{d}", "kind": "position", "at": at(d, 23, 30), "phone": "phB", "owner": "bob",
                  "place": {"lat": YARD[0], "lon": YARD[1], "radius_m": 10}},
                 {"ref": f"pC:{d}", "kind": "position", "at": at(d, 23, 35), "phone": "phC", "owner": "pre",
                  "place": {"lat": YARD[0], "lon": YARD[1] + 0.0001, "radius_m": 10}},
                 {"ref": f"pay:{d}", "kind": "payment", "at": at(nxt, 12), "day_only": True, "owner": "ann",
                  "parties": ["bob"], "amount_minor": 40000, "body": "TRANSFER TO BOB BROOK",
                  "dup_key": ("pay", "ann", ("bob",), 40000, nxt)},
                 {"ref": f"alert:{d}", "kind": "payment_alert", "at": at(nxt, 13), "phone": "phB", "owner": "ann",
                  "parties": ["bob"], "amount_minor": 40000, "body": "You received $400.00 from Ann Arden",
                  "dup_key": ("pay", "ann", ("bob",), 40000, nxt)},
                 {"ref": f"media:{d}", "kind": "media_position", "at": at(d, 23, 40), "phone": "phD", "owner": "dan",
                  "place": {"lat": YARD[0], "lon": YARD[1], "radius_m": 5}}]
    # Dan and Bob at a shop once, on an ordinary Friday, and never in contact
    shop_day = FRIDAYS[3]
    recs += [{"ref": "shopB", "kind": "position", "at": at(shop_day, 14), "phone": "phB", "owner": "bob",
              "place": {"lat": SHOP[0], "lon": SHOP[1], "radius_m": 8}},
             {"ref": "shopD", "kind": "position", "at": at(shop_day, 14, 5), "phone": "phD", "owner": "dan",
              "place": {"lat": SHOP[0], "lon": SHOP[1], "radius_m": 8}},
             {"ref": "dan_note", "kind": "message", "at": at(shop_day, 14, 1), "phone": "phD", "owner": "dan",
              "parties": [], "counterpart_values": ["19990000"], "body": "at the shop", "sender": "dan"}]
    return recs


class FakeStore:
    def __init__(self, recs=None, facts=None, zone="UTC"):
        self.recs = build_records() if recs is None else recs
        self._facts = facts or []
        self._zone = zone
        self.by_ref = {r["ref"]: r for r in self.recs}

    def zone(self):
        return self._zone

    def phone_zones(self):
        return {"phA": "UTC", "phB": "UTC", "phC": "America/Chicago", "phD": "UTC"}

    def people(self):
        return PEOPLE

    def selection_points(self, members):
        points, unread = [], []
        owner = {e: p["key"] for p in PEOPLE for e in p["phones"]}
        for m in members:
            ref = f"{m['type']}:{m['id']}"
            if m["type"] == "record" and m["id"] in self.by_ref:
                r = self.by_ref[m["id"]]
                people = [r.get("owner")] + list(r.get("parties") or [])
                points.append({"ref": ref, "type": "phone_record" if r["kind"] != "payment" else "financial_transaction",
                               "at": r["at"], "kind": r["kind"], "day_only": r.get("day_only"),
                               "people": [p for p in people if p], "place": r.get("place"),
                               "phone": r.get("phone")})
            elif m["type"] == "person":
                points.append({"ref": ref, "type": "person", "kind": "person", "people": [m["id"]]})
            elif m["type"] == "phone":
                points.append({"ref": ref, "type": "phone", "kind": "phone", "people": [owner[m["id"]]],
                               "phone": m["id"]})
            elif m["type"] == "place":
                lat, lon, rad = (float(x) for x in m["id"].split(","))
                points.append({"ref": ref, "type": "place", "kind": "place", "people": [],
                               "place": {"lat": lat, "lon": lon, "radius_m": rad}})
            else:
                unread.append({"ref": ref, "why": "unknown"})
        del owner
        return points, unread

    def place_points(self, place, phones):
        return []

    def records(self, people, windows, everyone):
        keys = {p["key"] for p in people}
        lo, hi = min(w[0] for w in windows), max(w[1] for w in windows)
        return [dict(r) for r in self.recs if r["kind"] != "activity" and lo - timedelta(days=1) <= r["at"] <= hi
                and (r.get("owner") in keys or keys & set(r.get("parties") or ()))]

    def activity(self, people, windows):
        keys = {p["key"] for p in people}
        out = {}
        for r in self.recs:
            if r["kind"] == "activity" and r["owner"] in keys:
                out.setdefault(r["owner"], []).append(r["at"])
        return {k: sorted(v) for k, v in out.items()}

    def coverage(self, people, doc_ids):
        span = (at(FRIDAYS[0], 0), at(FRIDAYS[-1] + timedelta(days=6), 23))
        cov = {p["key"]: {"phone": [span] if p["phones"] else [], "ledger": [span] if p["accounts"] else [],
                          "alerts": [span] if p["key"] == "bob" else []} for p in people}
        for d in doc_ids:
            cov[f"doc:{d}"] = {"doc": [span]}
        return cov

    def ledger_months(self, people):
        return {a: ["2025-01", "2025-02", "2025-03"] for p in people for a in p["accounts"]}

    def statement_files_outside_ledger(self):
        return ["acc-2025-02.pdf (not in the ledger; the same period is read from exhibit-2-acc-february-2025.pdf)"]

    def period(self, people):
        return FRIDAYS[0], FRIDAYS[-1] + timedelta(days=6)

    def phone_starts(self, people):
        return {p["key"]: at(FRIDAYS[0], 0) for p in people if p["phones"]}

    def phrase_counts(self, phrases):
        c = Counter()
        for r in self.recs:
            for ph in phrases:
                if ph in (r.get("body") or "").casefold():
                    c[ph] += 1
        return {ph: c[ph] for ph in phrases}

    def place_stats(self, lat, lon, radius_m, exclude=None):
        return {"phones_near": 0, "phones_total": 2, "days": 0, "radius_m": radius_m}

    def contact_ever(self, a, b):
        return sum(1 for r in self.recs if r["kind"] == "message" and {a["key"], b["key"]} <= (
            {r.get("owner")} | set(r.get("parties") or ())))

    def identities_named(self, values):
        return [{"value": "15550003", "name": "Old Owner", "phone": "phB", "first": at(date(2022, 1, 1), 9),
                 "last": at(date(2022, 2, 1), 9)}] if "15550003" in values else []

    def number_history(self, value, before):
        return [{"ref": "old1", "at": at(date(2022, 1, 1), 9), "phone": "phB"}] if value == "15550003" else []

    def offsets(self, phones, windows):
        return Counter({"explicit": 100})

    def merchant_payments(self, people, day):
        return []

    def facts(self):
        return self._facts

    def lookalike_names(self, person):
        if person["key"] == "ann":
            return [{"name": "Ann Other", "value": "+15559999", "phone": "phD", "where": "saved on a phone"}]
        return []
