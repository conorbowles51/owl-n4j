"""Group a selection by person, day, place, amount, app (lx-corrorest C)."""
from __future__ import annotations

import pytest

from services.corroborate import grouping

NAMES = {"person:a": "Kell", "person:b": "Marsh"}


def pt(i, people=(), at=None, place=None, amount=None, app=None):
    return {"ref": f"phone_record:{i}", "type": "phone_record", "label": f"r{i}", "people": list(people), "at": at,
            **({"place": place} if place else {}), **({"amount_minor": amount} if amount is not None else {}),
            **({"app": app} if app else {})}


def test_person_groups_count_each_person_and_say_how_many_items_are_in_several():
    out = grouping.group_points([pt(1, ["person:a"]), pt(2, ["person:a", "person:b"]), pt(3)], "person", "UTC", NAMES)
    assert {g["label"]: g["count"] for g in out["groups"]} == {"Kell": 2, "Marsh": 1}
    assert out["in_several_groups"] == 1
    assert out["left_out_total"] == 1 and "no person" in out["left_out"][0]["why"]


def test_day_groups_use_the_zone_and_count_undated_items_as_left_out():
    pts = [pt(1, at="2026-05-03T23:30:00+00:00"), pt(2, at="2026-05-03T01:00:00+00:00"), pt(3)]
    utc = grouping.group_points(pts, "day", "UTC", {})
    assert [(g["key"], g["count"]) for g in utc["groups"]] == [("2026-05-03", 2)]
    plus = grouping.group_points(pts, "day", "Europe/Dublin", {})
    assert sorted(g["key"] for g in plus["groups"]) == ["2026-05-03", "2026-05-04"]
    assert utc["left_out"] == [{"count": 1, "why": "has no date"}]


def test_place_amount_and_app_groups_name_what_they_group_on():
    p = grouping.group_points([pt(1, place={"lat": 53.3441, "lon": -6.2675}), pt(2, place={"lat": 53.3449, "lon": -6.2671})], "place", "UTC", {})
    assert p["groups"][0]["count"] == 2 and "about 1 km" in p["groups"][0]["label"]
    a = grouping.group_points([pt(1, amount=-9_999), pt(2, amount=15_000), pt(3)], "amount", "UTC", {})
    assert {g["label"] for g in a["groups"]} == {"payments of under 100", "payments of 100 to 999"}
    w = grouping.group_points([pt(1, app="WhatsApp"), pt(2, app="whatsapp"), pt(3, app="Signal")], "app", "UTC", {})
    assert [g["count"] for g in w["groups"]] == [2, 1]


def test_an_unknown_grouping_is_refused():
    with pytest.raises(grouping.GroupError):
        grouping.group_points([], "colour", "UTC", {})
