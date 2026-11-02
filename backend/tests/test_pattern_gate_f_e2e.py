"""Gate F (06 row 52): the statement check end to end on a synthetic two-phone case, through HTTP only.

Two synthetic phones in one case: A is recording through a night with one unlock at 01:00 and a run of GPS fixes; B
has fixes 15 m away at the same times. Every step below is an HTTP call a screen makes. Opt-in PostgreSQL.
"""
from __future__ import annotations

import json
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.phone import registry
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.test_pattern_u4_availability import DAY, setup
from tests.test_pattern_u5_places import LAT, PlacePhone, build
from tests.test_phone_mappings import hooks  # noqa: F401 (fixture)

M_PER_DEG_LAT = 111195.0
NIGHT = DAY + timedelta(hours=23)


@pytest.fixture(autouse=True)
def _feed_inbox(monkeypatch, tmp_path):
    from services import manual_changes
    monkeypatch.setattr(manual_changes, "INBOX", tmp_path / "inbox.jsonl")  # never the real feed inbox


def _two_phones(c, case):
    a, b = PlacePhone(), PlacePhone()
    a.every(NIGHT, NIGHT + timedelta(hours=8), 20, a.device_event, "DisplayOnOff")
    a.device_event(NIGHT + timedelta(hours=2), "DeviceLockStatus", "Unlocked")
    for i in range(12):
        t = NIGHT + timedelta(minutes=10 * i)
        a.location(t, accuracy=5)
        b.location(t, lat=LAT + 15 / M_PER_DEG_LAT, accuracy=5)
    return a.make(c, case), b.make(c, case)


@needs_template
def test_gate_f_statement_check_end_to_end_over_http_on_two_synthetic_phones(hooks):
    from postgres.models.enums import GlobalRole
    from postgres.models.user import User
    from services.pattern_of_life import evaluation, snapshots
    from services.phone import resolvers
    from services.workspace_entry_service import create_entry
    from tests.pattern_pg import api_client
    from postgres import link_types
    saved = dict(link_types._RESOLVERS)
    resolvers.register(); evaluation.register(); snapshots.register()  # as main.py does at start-up
    setup(hooks)
    try:
        with fresh_engine() as engine:
            with engine.begin() as c:
                registry.apply_seed(c)
                case = make_case(c)
                ea, eb = _two_phones(c, case)
            build(engine, ea)
            build(engine, eb)
            with Session(engine) as s:
                uid, email = s.execute(text("SELECT u.id, u.email FROM cases k JOIN users u ON u.id = "
                                            "k.owner_user_id WHERE k.id = :c"), {"c": case}).one()
                entry = create_entry(s, case_id=case, current_user=User(id=uid, email=email, name="synthetic",
                                                                         global_role=GlobalRole.user),
                                     entry_type="finding", title="Synthetic finding", body="synthetic")
                s.commit()
            A = {"kind": "extraction", "extraction_id": str(ea)}
            B = {"kind": "extraction", "extraction_id": str(eb)}
            with api_client(engine, case) as client:
                P = "/api/pattern/%s" % case
                # the subjects and the views a person opens first
                subj = client.get(P + "/subjects").json()
                assert subj["total_extractions"] == 2
                after_midnight = (NIGHT + timedelta(hours=2)).date().isoformat()  # the unlock's own day
                day = client.get(P + "/day", params={"subject": json.dumps(A), "date": after_midnight,
                                                     "zone": "UTC"}).json()
                assert day["totals"]["interaction"] == 1 and day["totals"]["places"] >= 1
                unlock = NIGHT + timedelta(hours=2)
                win = client.get(P + "/window", params={"at": unlock.isoformat(), "span": "1h"}).json()
                assert win["phones_total"] == 2 and win["zone_basis"] == "utc_default"
                # the moment saved as a key date, offered back
                kd = client.post(P + "/key-dates", json={"kind": "date", "label": "Synthetic unlock",
                                                         "instant": unlock.isoformat(), "zone": "UTC"})
                assert kd.status_code == 200, kd.text
                assert client.get(P + "/key-dates").json()["total"] == 1
                # were the two together
                tg = client.post(P + "/together", json={"subjects": [A, B], "start": NIGHT.isoformat(),
                                                        "end": (NIGHT + timedelta(hours=3)).isoformat()})
                assert tg.status_code == 200, tg.text
                assert tg.json()["counts"]["compatible"] == 12 and tg.json()["counts"].get("separated", 0) == 0
                # "I was asleep": entered, confirmed, checked
                C = P + "/claims"
                cl = client.post(C, json={"kind": "inactive", "subject": A, "window_start": NIGHT.isoformat(),
                                          "window_end": (NIGHT + timedelta(hours=6)).isoformat(),
                                          "window_zone": "UTC", "window_text": "asleep from eleven"}).json()
                assert cl["status"] == "draft"
                cl = client.post("%s/%s/confirm" % (C, cl["id"]), json={"expected_version": cl["version"]}).json()
                ev = client.post("%s/%s/evaluate" % (C, cl["id"])).json()
                assert ev["outcome"] in ("contradicted", "contradicted_weakly")
                assert ev["total_items"] == len(ev["items"])
                con = [i for i in ev["items"] if i["role"] == "contradicting"]
                assert con and con[0]["record_uid"]
                again = client.post("%s/%s/evaluate" % (C, cl["id"])).json()
                assert again["outcome"] == ev["outcome"] and again["total_items"] == ev["total_items"]
                # "I was with B": checked against the same pair rule Together uses
                w = client.post(C, json={"kind": "with_subject", "subject": A, "counterpart": B,
                                         "window_start": NIGHT.isoformat(),
                                         "window_end": (NIGHT + timedelta(hours=2)).isoformat(),
                                         "window_zone": "UTC", "window_text": "with B all evening"})
                assert w.status_code == 200, w.text
                w = client.post("%s/%s/confirm" % (C, w.json()["id"]), json={"expected_version": w.json()["version"]}).json()
                wev = client.post("%s/%s/evaluate" % (C, w["id"])).json()
                assert wev["outcome"] not in ("contradicted", "contradicted_weakly"), wev["outcome_words"]
                assert any(i["role"] == "supporting" for i in wev["items"])
                # "This item is wrong": recorded, the outcome unchanged
                d = client.post("%s/%s/evaluations/%s/items/%d/dispute" % (C, cl["id"], ev["evaluation_id"],
                                                                         con[0]["ordinal"]),
                                json={"reason": "synthetic: the unlock was the alarm"})
                assert d.status_code == 200, d.text
                read = client.get("%s/%s/evaluations/%s" % (C, cl["id"], ev["evaluation_id"])).json()
                assert read["disputed_items"] == 1 and read["outcome"] == ev["outcome"]
                # the readings move: the old check says stale, Check again makes a fresh one
                with engine.begin() as c:
                    c.execute(text("UPDATE pol_projection_state SET signature = 'moved' WHERE extraction_id = :e"),
                              {"e": ea})
                lst = client.get("%s/%s/evaluations" % (C, cl["id"])).json()
                assert all(i["stale"] for i in lst["items"])
                fresh = client.post("%s/%s/evaluate" % (C, cl["id"])).json()
                assert fresh["stale"] is False and fresh["evaluation_id"] != ev["evaluation_id"]
                # kept: attached to a finding, and the Day view frozen as a result
                at = client.post("%s/%s/evaluations/%s/attach" % (C, cl["id"], fresh["evaluation_id"]),
                                 json={"entry_id": entry["id"], "expected_version": entry["version"],
                                       "item_ordinals": [i["ordinal"] for i in fresh["items"]
                                                         if i["role"] == "contradicting"],
                                       "include_check_link": True})
                assert at.status_code == 200, at.text
                snap = client.post(P + "/snapshots", json={"kind": "day", "subject": json.dumps(A),
                                                           "date": after_midnight, "zone": "UTC"})
                assert snap.status_code == 200 and snap.json()["record_count"] > 0
            with engine.connect() as c:
                kinds = sorted(r[0] for r in c.execute(text("SELECT DISTINCT target_type FROM workspace_entry_links "
                                                            "WHERE entry_id = :e"), {"e": entry["id"]}))
            assert kinds == ["phone_record", "statement_check"]
    finally:
        link_types._RESOLVERS.clear()
        link_types._RESOLVERS.update(saved)
