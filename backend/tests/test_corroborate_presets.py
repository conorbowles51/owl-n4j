"""Preset windows round an incident (lx-corrorest E): dates read from a theory's own words, and the exact window."""
from __future__ import annotations

from zoneinfo import ZoneInfo

from services.corroborate import incidents, scope


def test_dates_are_read_with_their_words_and_optional_time():
    hits = incidents.dates_in_text("It happened on 2026-05-03 21:30. Earlier, 3 May 2026 was quiet; May 4th, 2026 at 09:15 too. 2026-13-40 is not a date.")
    assert [(h["date"], h["time"]) for h in hits] == [("2026-05-03", "21:30"), ("2026-05-03", None), ("2026-05-04", "09:15")]
    assert hits[0]["words"].startswith("2026-05-03")


def test_text_with_no_date_gives_none():
    assert incidents.dates_in_text("He said he was home all evening.") == []


def item(at, precision=None):
    return {"ref": "x", "type": "phone_record", "id": at, "label": "", "at": at, **({"precision": precision} if precision else {})}


def test_window_keeps_instants_inside_and_counts_day_only_items_as_no_time():
    win = {"from_at": "2026-05-03T20:30:00+00:00", "to_at": "2026-05-03T22:30:00+00:00", "label": "the incident, 1 h"}
    items = [item("2026-05-03T21:00:00+00:00"), item("2026-05-03T23:00:00+00:00"), item("2026-05-03", "day")]
    out = scope.apply(items, {"window": win})
    assert [i["at"] for i in out["kept"]] == ["2026-05-03T21:00:00+00:00", "2026-05-03"]
    assert out["outside_total"] == 1 and out["no_time"] == 1
    assert out["words"] and "the incident, 1 h" in out["words"][0]
