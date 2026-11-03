"""03 section 17.1, A1 and A3, each in one test across the screens that show phone rows.

A1: one identity saved under a different name on each phone shows, in phone view, that phone's own name on that
phone's rows in Conversations, the Timeline lens and Search hits; event ids, order and counts are the same in both
name modes.
A3: for one filter ("Ana and the owner, between, March", with calls whose owner side is implicit and copies),
the Conversations total, the Timeline lens total (communications only) and the export's stated total are equal,
and the graph edge's count equals the Conversations list it opens (every copy).

Invented data only: 555 numbers and made-up names. Needs the PostgreSQL phone template.
"""
from __future__ import annotations

from datetime import datetime, timezone

from services.phone import streams as S
from services.phone.filters import StreamFilter
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

pytestmark = needs_template
OWNER, ANA, BEN = "phone:+12025550100", "phone:+12025550143", "phone:+12025550188"


def _m(instant, sender, recips, body="synthetic harbour", dup=None, app="WhatsApp"):
    parties = [(sender, "sender", sender == OWNER, None, None)] + [(r, "recipient", r == OWNER, None, None)
                                                                    for r in recips]
    return dict(kind="message", instant=instant, body=body, thread="t", parties=parties, dup=dup, app=app,
                direction="outgoing" if sender == OWNER else "incoming")


def _implicit_call(instant):
    # the report names only the other side; the owner's side is implied from the direction, as comms.py does (C-4)
    return dict(kind="call", instant=instant, thread=None, direction="incoming", call_duration_s=30,
                parties=[(ANA, "caller", False, None, None), (None, "owner_implicit", True, None, None, "callee")])


def test_a1_each_phone_shows_its_own_name_for_one_identity_on_every_screen():
    from services.phone import timeline_lens
    from services.search import search
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            c3, _ = phone(c, case, label="C3", contacts={ANA: "Xavier Synthetic"},
                          events=[_m(at(2023, 3, 14, 12), ANA, [OWNER])])
            c7, _ = phone(c, case, label="C7", contacts={ANA: "Yolanda Synthetic"},
                          events=[_m(at(2023, 3, 14, 13), ANA, [OWNER])])
        names = {str(c3): "Xavier Synthetic", str(c7): "Yolanda Synthetic"}
        with engine.connect() as c:
            out = {}
            for mode in ("phone", "case"):
                f = StreamFilter.model_validate({"case_id": str(case), "names": {"mode": mode}})
                idx = S.index_comm_events(c, f)
                rows = S.window_comm_events(c, f, snapshot_token=idx["snapshot"], day="2023-03-14")["items"]
                out[mode] = rows
            for r in out["phone"]:
                assert r["from"]["name"] == names[r["phone"]["extraction_id"]]
            # the same events in the same order whichever names are shown
            assert [r["event_uid"] for r in out["phone"]] == [r["event_uid"] for r in out["case"]]
            lf = timeline_lens.TimelineLensFilter.model_validate({"case_id": str(case), "names": {"mode": "phone"}})
            li = timeline_lens.index(c, lf)
            lens_rows = timeline_lens.window(c, lf, snapshot_token=li["snapshot"], day="2023-03-14")["items"]
            assert [r["event_uid"] for r in lens_rows] == [r["event_uid"] for r in out["phone"]]
            for r in lens_rows:
                assert r["from"]["name"] == names[r["phone"]["extraction_id"]]
            hits = {g["group"]: g for g in search.search(c, case, "harbour")["groups"]}["messages"]["items"]
            assert len(hits) == 2
            for h in hits:
                ext = [e for e, label in (("%s" % c3, "C3"), ("%s" % c7, "C7")) if label == h["phone_label"]][0]
                assert names[ext] in str(h["participants"])


def test_a3_one_filter_gives_the_same_total_on_every_screen():
    from services.phone import graph_projection, timeline_lens
    from services.phone.exports import jobs
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            phone(c, case, label="C1", device_zone="America/New_York", events=[
                _m(at(2023, 3, 2, 9), ANA, [OWNER], body="same", dup="g1", app="Native Messages"),
                _m(at(2023, 3, 2, 9), ANA, [OWNER], body="same", dup="g1", app="IMS Service"),
                _m(at(2023, 3, 3, 9), OWNER, [ANA]),
                _implicit_call(at(2023, 3, 4, 9)),
                _implicit_call(at(2023, 3, 5, 9)),
                _m(at(2023, 3, 6, 9), BEN, [OWNER]),            # someone else: not between
                _m(at(2023, 4, 2, 9), ANA, [OWNER])])            # April: outside the dates
        body = {"case_id": str(case), "participants": [ANA, S.PHONE_OWNER], "participant_mode": "between",
                "from_instant": "2023-03-01T00:00:00Z", "to_instant": "2023-03-31T23:59:59Z", "include_no_time": False}
        with engine.connect() as c:
            conv = S.index_comm_events(c, StreamFilter.model_validate(body))["counts"]["events"]
            lens = timeline_lens.index(c, timeline_lens.TimelineLensFilter.model_validate(
                {**body, "lens_kinds": ["messages", "calls", "emails"]}))["total"]
            export = jobs.describe(c, case, {k: v for k, v in body.items() if k != "case_id"})["total"]
            every = S.shown_count(c, StreamFilter.model_validate({**body, "collapse_copies": False}))
            edge = graph_projection.pair_counts(c, case, ANA, S.PHONE_OWNER,
                                                datetime(2023, 3, 1, tzinfo=timezone.utc),
                                                datetime(2023, 3, 31, 23, 59, 59, tzinfo=timezone.utc))["total"]
        assert conv == lens == export == 4  # the copy counted once, both implicit-owner calls counted
        assert edge == every == 5
