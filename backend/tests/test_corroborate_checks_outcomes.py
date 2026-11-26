"""Explained-away checks say "ruled out" only when the explanation was tested and does not fit (followups 26 Nov:
a phone with no known user together on 71 of 113 days read as a shared home ruled out; a busy place was ruled out
on 0 of 0 other phones)."""
from datetime import datetime, timezone

from services.corroborate import checks

COMP = {"ordinary_noun": "ordinary days"}
INST = [{"id": "i1", "side": "incident", "start": datetime(2024, 3, 1, 12, tzinfo=timezone.utc)}]


class Store:
    def __init__(self, total):
        self.total = total

    def place_stats(self, lat, lon, radius, exclude=()):
        return {"phones_near": 0, "phones_total": self.total, "radius_m": radius, "days": 0}

    def merchant_payments(self, people, day):
        return []

    def offsets(self, phones, windows):
        return {}

    def number_history(self, num, before):
        return []

    def identities_named(self, nums):
        return []


def _row(present, of, people=("a", "b")):
    return {"id": "t1", "label": "A and B together", "link_kind": "together", "people": list(people),
            "incident": {"present": 1, "absent": 0, "no_data": 0, "of": 1},
            "ordinary": {"present": present, "absent": of - present, "no_data": 0, "of": of},
            "cells": {"i1": "present"}, "records": {"i1": ["pos1"]}}


def _people(known=True):
    return {k: {"label": k.upper(), "dossier_id": "d" + k if known else None, "phones": ["p" + k], "numbers": [],
                "names": []} for k in ("a", "b")}


def _run(rows, people, total=5):
    recs = [{"ref": "pos1", "kind": "position", "place": {"lat": 1.0, "lon": 2.0, "radius_m": 50}}]
    ctx = {"comparison": COMP, "phones": [], "zone": "UTC", "windows": []}
    return {c["check"]: c for c in checks.run(rows, INST, people, recs, ctx, Store(total))}


def test_unknown_phone_together_most_days_is_not_a_shared_home_ruled_out():
    got = _run([_row(71, 113)], _people(known=False))["household"]
    assert got["outcome"] == "checked", got
    assert "Shared device" in got["words"] and "not together every day" not in got["words"]


def test_known_people_together_under_half_the_days_is_ruled_out_with_the_threshold():
    got = _run([_row(20, 113)], _people())["household"]
    assert got["outcome"] == "ruled_out" and "under half" in got["words"]


def test_known_people_together_most_days_is_weighed_low():
    assert _run([_row(71, 113)], _people())["household"]["outcome"] == "weighed_low"


def test_too_few_ordinary_days_is_not_known():
    assert _run([_row(1, 1)], _people())["household"]["outcome"] == "no_data"


def test_busy_place_with_no_other_phones_is_not_known():
    got = _run([_row(20, 113)], _people(), total=0)["busy_place"]
    assert got["outcome"] == "no_data", got
    assert "0 of the case's 0" not in got["words"]


def test_busy_place_with_other_phones_far_away_is_ruled_out():
    assert _run([_row(20, 113)], _people(), total=4)["busy_place"]["outcome"] == "ruled_out"
