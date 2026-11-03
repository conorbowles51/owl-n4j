"""03 section 9.7 (T-1, T-6, T-7 and the window behind T-2, T-3): the Case Timeline phone lens.

Invented data only: 555 numbers and made-up text. Needs the PostgreSQL phone template.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from services.phone import ids
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import GEN, at, phone

pytestmark = needs_template
OWNER, ANA, BEN = "phone:+12025550100", "phone:+12025550143", "phone:+12025550188"


def _msg(instant, sender, recips, body="synthetic", thread="t"):
    parties = [(sender, "sender", sender == OWNER, None, None)] + [(r, "recipient", r == OWNER, None, None)
                                                                    for r in recips]
    return dict(kind="message", instant=instant, body=body, thread=thread, parties=parties,
                direction="outgoing" if sender == OWNER else "incoming")


def _entry(c, case, ext, ordinal, model_type, instant, event=True, keys=()):
    """A non-communication record's time value (phone_time_values) and its summary title."""
    rec = ids.record_uid(ext, 0, ordinal)
    c.execute(text(
        "INSERT INTO phone_time_values (case_id, extraction_id, document_index, ordinal, record_uid, root_record_uid, "
        "locator, model_type, generation, time_uid, body_path, field_name, field_path, value_index, instant, "
        "original_text, offset_state, offset_present, effective_instant, is_event_time) VALUES (:c, :e, 0, :o, :r, :r, "
        "'x', :m, :g, :u, 'f', 'TimeStamp', 'TimeStamp', 0, :i, 'synthetic', 'present', true, :i, :ev)"),
        {"c": case, "e": ext, "o": ordinal, "r": rec, "m": model_type, "g": GEN, "u": uuid.uuid4(), "i": instant,
         "ev": event})
    for k in keys:
        c.execute(text(
            "INSERT INTO phone_participations (case_id, extraction_id, document_index, ordinal, record_uid, "
            "root_record_uid, locator, model_type, generation, participation_uid, role, role_basis, is_phone_owner, "
            "identity_key) VALUES (:c, :e, 0, :o, :r, :r, 'x', :m, :g, :u, 'other', 'container', false, :k)"),
            {"u": uuid.uuid4(), "c": case, "e": ext, "o": ordinal, "r": rec, "m": model_type, "g": GEN, "k": k})
    return rec


@pytest.fixture
def world():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            ext, evs = phone(c, case, device_zone="America/New_York", events=[
                _msg(at(2023, 3, 14, 12), ANA, [OWNER]),
                _msg(at(2023, 3, 14, 13), OWNER, [ANA]),
                _msg(at(2023, 3, 15, 9), BEN, [OWNER], thread="u"),
                _msg(None, ANA, [OWNER])])
            _entry(c, case, ext, 100, "Location", at(2023, 3, 14, 12, 30), keys=[ANA])
            _entry(c, case, ext, 101, "DeviceEvent", at(2023, 3, 14, 14))
            _entry(c, case, ext, 102, "NetworkUsage", at(2023, 3, 14, 15))
            _entry(c, case, ext, 103, "VisitedPage", at(2023, 3, 14, 16))
            _entry(c, case, ext, 104, "Location", at(2023, 3, 14, 17), event=False)  # not an event time
        yield {"engine": engine, "case": str(case), "ext": str(ext), "evs": evs}


def _f(w, **kw):
    from services.phone.timeline_lens import TimelineLensFilter
    return TimelineLensFilter.model_validate({"case_id": w["case"], **kw})


def test_t1_with_two_participants_the_lens_total_equals_the_conversations_total(world):
    from services.phone import streams, timeline_lens
    from services.phone.filters import StreamFilter
    body = {"participants": [ANA, OWNER], "participant_mode": "all"}
    with world["engine"].connect() as c:
        conv = streams.index_comm_events(c, StreamFilter.model_validate({"case_id": world["case"], **body}))
        lens = timeline_lens.index(c, _f(world, lens_kinds=["messages", "calls", "emails"], **body))
    assert lens["total"] == conv["counts"]["events"] == 3
    assert lens["no_time_count"] == conv["no_time_count"] == 1


def test_t7_default_kinds_hide_device_events_and_state_their_number(world):
    from services.phone import timeline_lens
    with world["engine"].connect() as c:
        out = timeline_lens.index(c, _f(world))
        shown = timeline_lens.index(c, _f(world, lens_kinds=list(timeline_lens.KIND_WORDS)))
    assert timeline_lens.DEFAULT_KINDS == ["messages", "calls", "emails", "media", "locations"]
    # 4 messages and 1 location (the other location value is not an event time); device and web are off
    assert out["total"] == 5 and out["counts"]["communications"] == 4
    assert out["hidden"]["count"] == 2 and out["hidden"]["words"] == "2 device events and sensor readings hidden."
    assert {k["key"] for k in out["kinds"] if k["on"]} == set(timeline_lens.DEFAULT_KINDS)
    assert shown["total"] == 8 and shown["hidden"]["count"] == 0


def test_the_window_merges_both_sources_by_time_with_day_header_and_12_hour_time(world):
    from services.phone import timeline_lens
    with world["engine"].connect() as c:
        f = _f(world)
        idx = timeline_lens.index(c, f)
        assert [d["day"] for d in idx["items"]] == ["2023-03-14", "2023-03-15"]
        assert idx["items"][0]["header"] == "Tuesday, March 14, 2023"
        day = timeline_lens.window(c, f, snapshot_token=idx["snapshot"], day="2023-03-14", limit=1000)["items"]
        undated = timeline_lens.window(c, f, snapshot_token=idx["snapshot"], day=None)["items"]
    assert [x["source"] for x in day] == ["comm", "other", "comm"]
    assert day[0]["body"] == "synthetic" and day[0]["kind"] == "message" and day[1]["model_type"] == "Location"
    assert day[1]["kind"] == "record" and day[1]["subject"] == "Locations: Location" and day[1]["to"] == []
    assert day[0]["time"]["row"] == "8:00 AM"  # 12:00 UTC in New York, 12-hour (T-3)
    assert [d["count"] for d in idx["items"]] == [3, 1] and len(undated) == idx["no_time_count"] == 1
    assert {x["lane_key"] for x in day} == {world["ext"]} and day[0]["lane_label"]


def test_t2_windows_sum_to_the_total_without_gaps(world):
    from services.phone import timeline_lens
    with world["engine"].connect() as c:
        f = _f(world, lens_kinds=list(timeline_lens.KIND_WORDS))
        idx = timeline_lens.index(c, f)
        seen = []
        for d in [x["day"] for x in idx["items"]] + [None]:
            off = 0
            while True:
                page = timeline_lens.window(c, f, snapshot_token=idx["snapshot"], day=d, offset=off, limit=2)["items"]
                seen += [x["entry_uid"] for x in page]
                if len(page) < 2:
                    break
                off += 2
    assert len(seen) == len(set(seen)) == idx["total"] == 8


def test_lanes_by_person_kind_and_a_filter_only_conversations_have(world):
    from services.phone import timeline_lens
    with world["engine"].connect() as c:
        people = timeline_lens.index(c, _f(world, participants=[ANA, BEN], lane_by="person"))
        kinds = timeline_lens.index(c, _f(world, lane_by="kind"))
        between = timeline_lens.index(c, _f(world, participants=[ANA, OWNER], participant_mode="between"))
    assert {l["key"]: l["count"] for l in people["lanes"]} == {ANA: 4, BEN: 1}  # 3 messages and the location
    assert {l["key"]: l["count"] for l in kinds["lanes"]} == {"messages": 4, "locations": 1}
    assert between["counts"]["other"] == 0 and not between["other_filter_applies"]


def test_t6_a_phone_with_no_data_in_a_period_shows_no_data_distinct_from_zero(world, monkeypatch):
    from services.phone import timeline_lens
    gap = {datetime(2023, 3, 16, h, tzinfo=timezone.utc) for h in range(24)}
    monkeypatch.setattr(timeline_lens, "_no_data_hours", lambda conn, ext, a, b: gap)
    with world["engine"].connect() as c:
        f = _f(world)
        idx = timeline_lens.index(c, f)
        out = timeline_lens.buckets(c, f, snapshot_token=idx["snapshot"], start=datetime(2023, 3, 14, 4, tzinfo=timezone.utc),
                                    end=datetime(2023, 3, 18, 4, tzinfo=timezone.utc), bucket="day")
    [lane] = out["lanes"]
    by_day = {b["wall"][:10]: b for b in lane["buckets"]}
    assert by_day["2023-03-14"]["count"] == 3 and not by_day["2023-03-14"]["no_data"]
    assert by_day["2023-03-16"]["count"] == 0 and not by_day["2023-03-16"]["no_data"]  # New York day spans 2 UTC days
    assert by_day["2023-03-17"]["count"] == 0 and not by_day["2023-03-17"]["no_data"]
    assert out["no_data_words"] == "No data" and out["empty_words"] == "No matching entries"
    # a whole display day inside the gap reads No data
    gap |= {datetime(2023, 3, 17, h, tzinfo=timezone.utc) for h in range(24)}
    with world["engine"].connect() as c:
        out = timeline_lens.buckets(c, f, snapshot_token=idx["snapshot"], start=datetime(2023, 3, 14, 4, tzinfo=timezone.utc),
                                    end=datetime(2023, 3, 18, 4, tzinfo=timezone.utc), bucket="day")
    assert {b["wall"][:10]: b["no_data"] for b in out["lanes"][0]["buckets"]}["2023-03-16"] is True
    with world["engine"].connect() as c, pytest.raises(ValueError, match="at most 7 days"):
        timeline_lens.buckets(c, f, snapshot_token=idx["snapshot"], start=datetime(2023, 3, 1, tzinfo=timezone.utc),
                              end=datetime(2023, 3, 9, tzinfo=timezone.utc), bucket="hour")


def test_lane_buckets_are_whole_days_in_the_display_zone_and_equal_the_days_list():
    """Review of 03-6: a span given in UTC is widened to whole days in the phone's zone, so the first and last
    days' marks count the whole day, as the list it opens does."""
    from services.phone import timeline_lens
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            phone(c, case, device_zone="America/New_York", events=[
                _msg(at(2023, 3, 13, 22), ANA, [OWNER]),     # 6 PM on March 13 in New York, before the UTC span
                _msg(at(2023, 3, 14, 12), ANA, [OWNER]),
                _msg(at(2023, 3, 21, 1), ANA, [OWNER])])     # 9 PM on March 20 in New York, after the UTC span
        with engine.connect() as c:
            f = timeline_lens.TimelineLensFilter.model_validate({"case_id": str(case)})
            idx = timeline_lens.index(c, f)
            out = timeline_lens.buckets(c, f, snapshot_token=idx["snapshot"],
                                        start=datetime(2023, 3, 14, tzinfo=timezone.utc),
                                        end=datetime(2023, 3, 21, tzinfo=timezone.utc), bucket="day")
        days = {b["wall"][:10]: b["count"] for b in out["lanes"][0]["buckets"]}
        per_day = {d["day"]: d["count"] for d in idx["items"]}
        assert days["2023-03-13"] == per_day["2023-03-13"] == 1
        assert days["2023-03-20"] == per_day["2023-03-20"] == 1
        assert sum(days.values()) == 3
        # no hourly rollup built for this phone: no day is claimed to have no data
        assert not any(b["no_data"] for b in out["lanes"][0]["buckets"])


def test_an_all_span_over_ten_years_is_drawn_in_weeks_not_refused():
    """A phone whose entries run from 2017 to a calendar entry in 2036 (a live case has one) gives an "All" span of
    about 7,000 days. Daily lanes stop at ten years, so the screen asks for weeks; weekly lanes start on Monday in the
    display zone and count every entry once."""
    from services.phone import timeline_lens
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            ext, _ = phone(c, case, device_zone="America/New_York", events=[
                _msg(at(2017, 8, 30, 18), ANA, [OWNER]),
                _msg(at(2017, 8, 31, 18), OWNER, [ANA]),
                _msg(at(2022, 12, 5, 1), BEN, [OWNER], thread="u")])   # 8 PM on Sunday 4 December in New York
            _entry(c, case, ext, 100, "CalendarEntry", at(2036, 11, 30, 23))
        with engine.connect() as c:
            f = timeline_lens.TimelineLensFilter.model_validate({"case_id": str(case),
                                                                 "lens_kinds": list(timeline_lens.KIND_WORDS)})
            idx = timeline_lens.index(c, f)
            start, end = datetime(2017, 8, 29, tzinfo=timezone.utc), datetime(2036, 12, 2, tzinfo=timezone.utc)
            with pytest.raises(ValueError, match="at most ten years"):
                timeline_lens.buckets(c, f, snapshot_token=idx["snapshot"], start=start, end=end, bucket="day")
            out = timeline_lens.buckets(c, f, snapshot_token=idx["snapshot"], start=start, end=end, bucket="week")
            with pytest.raises(ValueError, match="at most a hundred years"):
                timeline_lens.buckets(c, f, snapshot_token=idx["snapshot"], start=start,
                                      end=start + timedelta(days=36601), bucket="week")
    assert out["bucket"] == "week"
    [lane] = out["lanes"]
    walls = [b["wall"] for b in lane["buckets"]]
    assert all(datetime.fromisoformat(w).weekday() == 0 and w.endswith("T00:00:00") for w in walls)
    assert walls == sorted(walls) and len(walls) == len(set(walls))
    counts = {b["wall"][:10]: b["count"] for b in lane["buckets"] if b["count"]}
    assert counts == {"2017-08-28": 2, "2022-11-28": 1, "2036-11-24": 1}
    assert sum(counts.values()) == idx["total"] == 4


def test_the_week_bucket_is_accepted_by_the_lanes_route():
    from routers.phones import LensBucketsBody
    body = LensBucketsBody.model_validate({"filter": {}, "snapshot": "s", "start": "2017-08-29T00:00:00Z",
                                           "end": "2036-12-02T00:00:00Z", "bucket": "week"})
    assert body.bucket == "week"
