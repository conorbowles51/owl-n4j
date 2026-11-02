"""Frozen pattern results as phone_analysis links, and one statement check or result added to an interview
(07 section 6.4 items 5 and 13; J-9 "linked to the interview").

Synthetic phones only. Opt-in PostgreSQL through ``LOUPE_TEST_PHONE_PG_TEMPLATE_URL``.
"""
from __future__ import annotations

import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from postgres import link_types
from services.pattern_of_life import snapshots
from services.phone import registry
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.test_pattern_u4_availability import DAY, setup
from tests.test_pattern_u5_places import build
from tests.test_pattern_u6_day import _phone
from tests.test_phone_mappings import hooks  # noqa: F401 (fixture)


def _case(engine):
    with engine.begin() as c:
        registry.apply_seed(c)
        case = make_case(c)
        ext = _phone().make(c, case)
    build(engine, ext)
    return case, ext


@needs_template
def test_a_frozen_day_is_recomputed_by_the_server_linkable_and_stale_after_the_readings_move(hooks):
    from tests.pattern_pg import api_client
    setup(hooks)
    saved = dict(link_types._RESOLVERS)
    snapshots.register()
    try:
        with fresh_engine() as engine:
            case, ext = _case(engine)
            subj = json.dumps({"kind": "extraction", "extraction_id": str(ext)})
            body = {"kind": "day", "subject": subj, "date": DAY.date().isoformat(), "zone": "UTC"}
            with api_client(engine, case) as client:
                r = client.post("/api/pattern/%s/snapshots" % case, json=body)
                assert r.status_code == 200, r.text
                one = r.json()
                assert one["id"].startswith("pa_") and one["stale"] is False
                counts = one["snapshot"]["summary_counts"]
                assert counts["interaction"] == 1 and counts["communications"] == 1 and counts["places"] == 1
                assert one["record_count"] == len(one["snapshot"]["record_ids"]) > 0
                assert one["snapshot"]["window"]["zone"] == "UTC"
                # the browser cannot supply the counts: unknown fields are refused
                bad = client.post("/api/pattern/%s/snapshots" % case, json=dict(body, summary_counts={"x": 1}))
                assert bad.status_code == 422
                again = client.post("/api/pattern/%s/snapshots" % case, json=body).json()
                assert again["id"] == one["id"]  # same inputs, same result, same id
                with engine.connect() as c:
                    assert c.execute(text("SELECT count(*) FROM pol_analysis_snapshot")).scalar() == 1
                # the registry accepts it: the stored snapshot hashes back to its id
                with sessionmaker(bind=engine)() as s:
                    target = link_types.resolve_phone_target(s, case, "phone_analysis", one["id"])
                    assert target.label.startswith("Day view") and target.snapshot["record_ids"] == \
                        one["snapshot"]["record_ids"]
                    other = uuid.uuid4()
                    try:
                        link_types.resolve_phone_target(s, other, "phone_analysis", one["id"])
                        raise AssertionError("a snapshot of another case resolved")
                    except link_types.LinkTargetError:
                        pass
                with engine.begin() as c:
                    c.execute(text("UPDATE pol_projection_state SET signature = 'changed' WHERE extraction_id = :e"),
                              {"e": ext})
                kept = client.get("/api/pattern/%s/snapshots/%s" % (case, one["id"])).json()
                assert kept["stale"] is True and "kept as it was" in kept["stale_words"]
                assert kept["snapshot"] == one["snapshot"]  # never rewritten
                fresh = client.post("/api/pattern/%s/snapshots" % case, json=body).json()
                assert fresh["id"] != one["id"]
                d = DAY.date().isoformat()
                grid = client.post("/api/pattern/%s/snapshots" % case, json={
                    "kind": "grid", "subject": subj, "start_date": d, "end_date": d, "zone": "UTC"}).json()
                assert grid["snapshot"]["summary_counts"]["days"] == 1
                assert sum(v for k, v in grid["snapshot"]["summary_counts"].items() if k.startswith("hours_")) == 24
                # a grid in a zone west of UTC covers the same local days the screen shows, local midnight to
                # local midnight (the review found UTC-midnight bounds gave an extra day)
                ny = client.post("/api/pattern/%s/snapshots" % case, json={
                    "kind": "grid", "subject": subj, "start_date": d, "end_date": d,
                    "zone": "America/New_York"}).json()
                assert ny["snapshot"]["summary_counts"]["days"] == 1, ny["snapshot"]["summary_counts"]
                shown = client.get("/api/pattern/%s/grid" % case, params={
                    "subject": subj, "start_date": d, "end_date": d, "zone": "America/New_York"}).json()
                assert len(shown["days"]) == 1
                assert ny["snapshot"]["window"]["start"][11:16] in ("04:00", "05:00")
                # the record list follows the grid's own rule: device state chosen adds the device records
                both = client.post("/api/pattern/%s/snapshots" % case, json={
                    "kind": "grid", "subject": subj, "start_date": d, "end_date": d, "zone": "UTC",
                    "parameters": {"min_strength": "strong", "classes": ["interaction", "device_state"],
                                   "include_physical": False}}).json()
                with engine.connect() as c:
                    expect = c.execute(text(
                        "SELECT count(DISTINCT record_uid) FROM pol_activity_event_v WHERE extraction_id = :e AND "
                        "((activity_class = 'interaction' AND counts_for = 'owner' AND strength = 'strong') OR "
                        "(activity_class = 'device_state' AND counts_for = 'owner')) AND record_uid IS NOT NULL"),
                        {"e": ext}).scalar()
                assert both["record_count"] == expect > grid["record_count"]
    finally:
        link_types._RESOLVERS.clear()
        link_types._RESOLVERS.update(saved)


@needs_template
def test_one_item_added_to_an_interview_keeps_the_others_and_is_never_added_twice(hooks):
    from postgres.models.user import User
    from services import dossier_service
    from tests.pattern_pg import api_client
    setup(hooks)
    saved = dict(link_types._RESOLVERS)
    snapshots.register()
    try:
        with fresh_engine() as engine:
            case, ext = _case(engine)
            subj = json.dumps({"kind": "extraction", "extraction_id": str(ext)})
            with api_client(engine, case) as client:
                day = client.post("/api/pattern/%s/snapshots" % case, json={
                    "kind": "day", "subject": subj, "date": DAY.date().isoformat(), "zone": "UTC"}).json()
                places = client.post("/api/pattern/%s/snapshots" % case, json={
                    "kind": "places", "subject": subj, "start": DAY.isoformat(),
                    "end": (DAY + timedelta(days=1)).isoformat(), "zone": "UTC"}).json()
            assert places["snapshot"]["summary_counts"]["observations"] == 1
            with engine.connect() as c:
                uid = c.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": case}).scalar()
            with patch.object(dossier_service, "check_case_access", return_value=(None, None)), \
                    patch.object(dossier_service, "get_case_if_allowed", return_value=None), \
                    patch.object(dossier_service, "_case_member_ids", return_value=set()), \
                    sessionmaker(bind=engine)() as s:
                user = s.get(User, uid)
                dossier = dossier_service.create_dossier(s, case_id=case, user=user, data={"display_name": "Witness"})
                did = uuid.UUID(dossier["id"])
                iv = dossier_service.create_interview(s, dossier_id=did, user=user, data={
                    "status": "completed",
                    "evidence_links": [{"target_type": "phone_analysis", "target_id": day["id"]}]})
                iid = uuid.UUID(iv["id"])
                out = dossier_service.add_interview_evidence(s, dossier_id=did, interview_id=iid, user=user, item={
                    "target_type": "phone_analysis", "target_id": places["id"], "source_anchor": {}})
                assert out["added"] == 1 and out["already_there"] == 0
                listed = [(e["target_type"], e["target_id"]) for e in out["interview"]["evidence_links"]]
                assert listed == [("phone_analysis", day["id"]), ("phone_analysis", places["id"])]
                again = dossier_service.add_interview_evidence(s, dossier_id=did, interview_id=iid, user=user, item={
                    "target_type": "phone_analysis", "target_id": places["id"], "source_anchor": {}})
                assert again["added"] == 0 and again["already_there"] == 1
                assert len(again["interview"]["evidence_links"]) == 2
                anchor = again["interview"]["evidence_links"][1]["source_anchor"]
                assert anchor["snapshot"]["record_ids"] == places["snapshot"]["record_ids"]
    finally:
        link_types._RESOLVERS.clear()
        link_types._RESOLVERS.update(saved)
