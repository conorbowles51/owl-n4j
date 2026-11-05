"""04-U11 (cb-pol item J): statement claims and their evaluation.

Synthetic phones only. Opt-in PostgreSQL through ``LOUPE_TEST_PHONE_PG_TEMPLATE_URL``.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.financial.decisions import Actor
from services.pattern_of_life import claims, evaluation
from services.phone import registry
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.test_pattern_u4_availability import DAY, Phone, setup
from tests.test_pattern_u5_places import LAT, LON, PlacePhone, build
from tests.test_phone_mappings import hooks  # noqa: F401 (fixture)

M_PER_DEG_LAT = 111195.0


def person(conn, case):
    uid = conn.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": case}).scalar_one()
    return Actor(name="Test Person", email="t@x.test", user_id=uid)


def night_phone(unlock_at=None):
    p = Phone()
    night = DAY + timedelta(hours=23)
    p.every(night, night + timedelta(hours=8), 20, p.device_event, "DisplayOnOff")
    if unlock_at is not None:
        p.device_event(unlock_at, "DeviceLockStatus", "Unlocked")
    return p


def confirmed(conn, case, actor, kind, subject, a, b, **extra):
    c = claims.create(conn, case, dict(kind=kind, subject=subject, window_start=a.isoformat(),
                                       window_end=b.isoformat(), window_zone="UTC", window_text="synthetic", **extra),
                      actor)
    return claims.confirm(conn, case, c["id"], c["version"], actor)



@pytest.fixture(autouse=True)
def _feed_inbox(monkeypatch, tmp_path):
    from services import manual_changes
    monkeypatch.setattr(manual_changes, "INBOX", tmp_path / "inbox.jsonl")  # never the real feed inbox

@needs_template
def test_inactive_is_consistent_over_a_recording_night_and_contradicted_by_an_unlock(hooks):
    setup(hooks)
    night = DAY + timedelta(hours=23)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            quiet = night_phone().make(c, case)
            woke = night_phone(unlock_at=night + timedelta(hours=3, minutes=10)).make(c, case)
        build(engine, quiet)
        build(engine, woke)
        with engine.begin() as c:
            me = person(c, case)
            q = confirmed(c, case, me, "inactive", {"kind": "extraction", "extraction_id": str(quiet)}, night,
                          night + timedelta(hours=6))
            ev = evaluation.evaluate(c, case, q["id"], me.name)
            assert ev["outcome"] == "consistent", ev["outcome_basis"]
            assert ev["outcome_words"].startswith("Nothing on the phone needed a person")
            assert "asleep" not in ev["outcome_words"]
            assert ev["counts"]["contradicting"] == {"strong": 0, "moderate": 0, "weak": 0}
            assert ev["counts"]["context"] == ev["total_items"] - ev["counts"]["supporting"]["moderate"] - \
                ev["counts"]["supporting"]["weak"] - ev["counts"]["gap"]
            w = confirmed(c, case, me, "inactive", {"kind": "extraction", "extraction_id": str(woke)}, night,
                          night + timedelta(hours=6))
            ev2 = evaluation.evaluate(c, case, w["id"], me.name)
            con = [i for i in ev2["items"] if i["role"] == "contradicting"]
            assert len(con) == 1 and con[0]["reason_code"] == "owner_interaction" and con[0]["record_uid"]
            assert ev2["outcome"] == ("contradicted" if con[0]["strength"] == "strong" else "contradicted_weakly")
            # a tolerance at the window's edge does not reach 03:10
            t = claims.edit(c, case, w["id"], {"activity": {"tolerance_minutes": 30}}, w["version"], me)
            t = claims.confirm(c, case, t["id"], t["version"], me)
            assert evaluation.evaluate(c, case, t["id"], me.name)["outcome"] == ev2["outcome"]


@needs_template
def test_an_evaluation_is_reproducible_from_its_fingerprint_and_stale_after_a_mapping_change(hooks):
    setup(hooks)
    night = DAY + timedelta(hours=23)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = night_phone(unlock_at=night + timedelta(hours=1)).make(c, case)
        build(engine, ext)
        with engine.begin() as c:
            me = person(c, case)
            cl = confirmed(c, case, me, "inactive", {"kind": "extraction", "extraction_id": str(ext)}, night,
                           night + timedelta(hours=6))
            one = evaluation.evaluate(c, case, cl["id"], me.name)
            two = evaluation.evaluate(c, case, cl["id"], me.name)
            strip = lambda ev: [{k: v for k, v in i.items() if k != "disputed"} for i in ev["items"]]  # noqa: E731
            assert one["inputs_fingerprint"] == two["inputs_fingerprint"] and strip(one) == strip(two)
            assert one["outcome"] == two["outcome"] and not one["stale"]
            # a mapping change re-projects the phone with a new signature (activity.project_stale); the check is stale
            c.execute(text("UPDATE pol_projection_state SET signature = 'changed' WHERE extraction_id = :e"), {"e": ext})
            again = evaluation.read(c, case, one["evaluation_id"])
            assert again["stale"] is True and again["outcome"] == one["outcome"]  # shown, never deleted
            hist = evaluation.list_evaluations(c, case, cl["id"])
            assert hist["total"] == 2 and all(h["stale"] for h in hist["items"])
            three = evaluation.evaluate(c, case, cl["id"], me.name)  # Check again
            assert not three["stale"] and evaluation.list_evaluations(c, case, cl["id"])["total"] == 3
            # editing the statement makes its checks stale too (claim version is an input)
            claims.edit(c, case, cl["id"], {"window_text": "about eleven"}, cl["version"], me)
            assert evaluation.read(c, case, three["evaluation_id"])["stale"] is True


@needs_template
def test_only_a_named_person_confirms_and_a_draft_never_carries_a_model_time(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = night_phone().make(c, case)
        with engine.begin() as c:
            me = person(c, case)
            subj = {"kind": "extraction", "extraction_id": str(ext)}
            d = claims.create(c, case, {"kind": "at_place", "subject": subj, "window_text": "at home all evening",
                                        "place": {"text": "home"}}, me)
            assert d["status"] == "draft" and d["missing_for_confirm"] == ["window_start", "window_end", "window_zone",
                                                                            "place"]
            with pytest.raises(claims.ClaimError) as exc:
                claims.confirm(c, case, d["id"], d["version"], me)
            assert exc.value.status == 422 and "place" in exc.value.fields
            with pytest.raises(claims.ClaimError) as exc:
                claims.confirm(c, case, d["id"], d["version"], Actor(name="Nobody", email="n@x.test"))
            assert exc.value.status == 403
            model = Actor(name="Test Person", email="t@x.test", user_id=me.user_id, origin={"kind": "model", "model": "synthetic"})
            with pytest.raises(claims.ClaimError) as exc:
                claims.confirm(c, case, d["id"], d["version"], model)
            assert exc.value.status == 403  # a model's work is never confirmed under a person's name
            with pytest.raises(claims.ClaimError) as exc:
                claims.edit(c, case, d["id"], {"window_text": "x"}, d["version"] + 5, me)
            assert exc.value.status == 409
            with pytest.raises(claims.ClaimError):
                evaluation.evaluate(c, case, d["id"], me.name)  # only a confirmed claim is checked
            aid = uuid.uuid4()
            with pytest.raises(claims.ClaimError):
                claims.create(c, case, {"kind": "inactive", "subject": subj, "window_start": DAY.isoformat(),
                                        "window_end": (DAY + timedelta(hours=1)).isoformat()}, me,
                              origin="ai_draft", ai_output_id=aid, ai_model="deepseek-chat")
            dr = claims.create(c, case, {"kind": "inactive", "subject": subj, "window_text": "asleep by eleven"}, me,
                               origin="ai_draft", ai_output_id=aid, ai_model="deepseek-chat")
            assert dr["status_words"] == "Drafted by deepseek-chat, not confirmed"
            assert dr["window_start"] is None
            assert claims.revisions(c, case, d["id"])["total"] == 1


@needs_template
def test_at_place_supported_near_and_contradicted_far(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            p = PlacePhone()
            for m in range(0, 120, 10):
                p.location(DAY + timedelta(hours=20, minutes=m), accuracy=10)
            ext = p.make(c, case)
        build(engine, ext)
        with engine.begin() as c:
            me = person(c, case)
            subj = {"kind": "extraction", "extraction_id": str(ext)}
            a, b = DAY + timedelta(hours=20), DAY + timedelta(hours=22)
            home = confirmed(c, case, me, "at_place", subj, a, b, place={"lat": LAT, "lon": LON, "radius_m": 50})
            ev = evaluation.evaluate(c, case, home["id"], me.name)
            assert ev["outcome"] == "supported" and ev["counts"]["supporting"]["strong"] == 12
            far = confirmed(c, case, me, "at_place", subj, a, b,
                            place={"lat": LAT + 5000 / M_PER_DEG_LAT, "lon": LON, "radius_m": 50})
            ev = evaluation.evaluate(c, case, far["id"], me.name)
            assert ev["outcome"] == "contradicted" and ev["counts"]["contradicting"]["strong"] == 12
            nat = confirmed(c, case, me, "not_at_place", subj, a, b, place={"lat": LAT, "lon": LON, "radius_m": 50})
            assert evaluation.evaluate(c, case, nat["id"], me.name)["outcome"] == "contradicted"
            empty = confirmed(c, case, me, "at_place", subj, a + timedelta(days=3), b + timedelta(days=3),
                              place={"lat": LAT, "lon": LON, "radius_m": 50})
            ev = evaluation.evaluate(c, case, empty["id"], me.name)
            # three days after every record on the phone: no record, outside the extraction's coverage (agent-phones)
            assert ev["outcome"] == "no_record" and ev["summary"]["no_record_reason"] == "outside_coverage"
            assert any(i["reason_code"] == "no_location" for i in ev["items"] if i["role"] == "gap")


@needs_template
def test_no_contact_is_undercut_by_a_message_from_the_other_side_and_the_item_can_be_disputed(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            p = Phone()
            p.incoming_message(DAY + timedelta(hours=10))
            ext = p.make(c, case)
        build(engine, ext)
        with Session(engine) as s:
            c = s.connection()
            me = person(c, case)
            ident = c.execute(text("SELECT id FROM phone_identities WHERE case_id = :c AND value_normalised LIKE "
                                   "'%2025550143%'"), {"c": case}).scalar_one()
            cl = confirmed(c, case, me, "no_contact", {"kind": "extraction", "extraction_id": str(ext)},
                           DAY + timedelta(hours=9), DAY + timedelta(hours=12),
                           counterpart={"identity_ids": [str(ident)]})
            ev = evaluation.evaluate(c, case, cl["id"], me.name)
            con = [i for i in ev["items"] if i["role"] == "contradicting"]
            assert len(con) == 1 and con[0]["strength"] == "weak" and con[0]["ref_kind"] == "comm_event"
            assert ev["outcome"] == "contradicted_weakly"
            d = evaluation.dispute(s, case, ev["evaluation_id"], con[0]["ordinal"], "not the same person", me)
            s.commit()
            assert d["decision_id"]  # recorded on the record it names
            again = evaluation.read(s.connection(), case, ev["evaluation_id"])
            item = [i for i in again["items"] if i["ordinal"] == con[0]["ordinal"]][0]
            assert item["disputed"]["reason"] == "not the same person"
            assert again["outcome"] == "contradicted_weakly"  # the computed outcome is never set by hand
            assert s.execute(text("SELECT decision FROM adjudications WHERE id = :d"),
                             {"d": d["decision_id"]}).scalar() == "dispute_check_item"
            with pytest.raises(claims.ClaimError):
                evaluation.dispute(s, case, ev["evaluation_id"], con[0]["ordinal"], "again", me)
            evaluation.withdraw_dispute(s, case, ev["evaluation_id"], con[0]["ordinal"], "it was them", me)
            s.commit()
            assert evaluation.read(s.connection(), case, ev["evaluation_id"])["disputed_items"] == 0


@needs_template
def test_claims_over_http_and_attaching_items_to_a_finding(hooks):
    from postgres.models.enums import GlobalRole
    from postgres.models.user import User
    from services.workspace_entry_service import create_entry
    from tests.pattern_pg import api_client
    from services.phone import resolvers
    resolvers.register()  # as main.py does at start-up
    evaluation.register()
    setup(hooks)
    night = DAY + timedelta(hours=23)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = night_phone(unlock_at=night + timedelta(hours=2)).make(c, case)
        build(engine, ext)
        with Session(engine) as s:
            uid, email = s.execute(text("SELECT u.id, u.email FROM cases k JOIN users u ON u.id = k.owner_user_id "
                                        "WHERE k.id = :c"), {"c": case}).one()
            user = User(id=uid, email=email, name="synthetic", global_role=GlobalRole.user)
            entry = create_entry(s, case_id=case, current_user=user, entry_type="finding", title="Synthetic finding",
                                 body="synthetic finding")
            s.commit()
        subj = {"kind": "extraction", "extraction_id": str(ext)}
        with api_client(engine, case) as client:
            base = "/api/pattern/%s/claims" % case
            r = client.post(base, json={"kind": "inactive", "subject": subj, "window_start": night.isoformat(),
                                        "window_end": (night + timedelta(hours=6)).isoformat(), "window_zone": "UTC",
                                        "window_text": "asleep from eleven"})
            assert r.status_code == 200, r.text
            cl = r.json()
            assert client.post("%s/%s/evaluate" % (base, cl["id"])).status_code == 422  # not confirmed
            r = client.post("%s/%s/confirm" % (base, cl["id"]), json={"expected_version": cl["version"]})
            assert r.status_code == 200 and r.json()["status"] == "confirmed"
            ev = client.post("%s/%s/evaluate" % (base, cl["id"])).json()
            assert ev["total_items"] == len(ev["items"]) and ev["outcome"] in ("contradicted", "contradicted_weakly")
            con = [i for i in ev["items"] if i["role"] == "contradicting"][0]
            r = client.post("%s/%s/evaluations/%s/attach" % (base, cl["id"], ev["evaluation_id"]),
                            json={"entry_id": entry["id"], "expected_version": entry["version"],
                                  "item_ordinals": [con["ordinal"]], "include_check_link": True})
            assert r.status_code == 200, r.text
            assert len(r.json()["result"]["added_link_ids"]) == 2
            with engine.connect() as c:
                links = dict(c.execute(text("SELECT target_type, relationship FROM workspace_entry_links WHERE "
                                            "entry_id = :e"), {"e": entry["id"]}).fetchall())
            assert links == {"phone_record": "contradicts", "statement_check": "contradicts"}
            lst = client.get("%s/%s/evaluations" % (base, cl["id"])).json()
            assert lst["total"] == 1 and lst["items"][0]["stale"] is False
            assert client.get(base).json()["total"] == 1
            # a saved statement_check link holds only the check's id: it opens that check with its statement's subject
            got = client.get("/api/pattern/%s/checks/%s" % (case, ev["evaluation_id"]))
            assert got.status_code == 200, got.text
            got = got.json()
            assert got["evaluation_id"] == ev["evaluation_id"] and got["claim_id"] == cl["id"]
            assert got["subject"] == subj and got["claim"]["window_text"] == "asleep from eleven"
            assert got["total_items"] == ev["total_items"]
            assert client.get("/api/pattern/%s/checks/%s" % (case, uuid.uuid4())).status_code == 404


@needs_template
def test_context_events_are_one_item_per_phone_hour_and_reason_and_each_is_listed(hooks):
    """04 decision 37: recorded-without-use events say so (never "what this time means is not established", which
    is for a time of unknown meaning), are kept as one counted item per phone, hour and reason, and every event of a
    group is listed with the count the check stored."""
    from tests.pattern_pg import api_client
    setup(hooks)
    night = DAY + timedelta(hours=23)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            p = night_phone()
            p.every(night + timedelta(minutes=5), night + timedelta(hours=2), 10, p.device_event, "MotionState",
                    "Stationary")
            ext = p.make(c, case)
        build(engine, ext)
        with engine.begin() as c:
            me = person(c, case)
            cl = confirmed(c, case, me, "inactive", {"kind": "extraction", "extraction_id": str(ext)}, night,
                           night + timedelta(hours=6))
            ev = evaluation.evaluate(c, case, cl["id"], me.name)
        ctx = [i for i in ev["items"] if i["role"] == "context"]
        assert not [i for i in ctx if i["ref_kind"] == "activity_event" and i["reason_code"] != "near_window"]
        passive = [i for i in ctx if i["ref_kind"] == "event_group" and i["reason_code"] == "passive"]
        assert [i["display"]["count"] for i in passive] == [6, 6]  # 23:05 to 00:55, every 10 minutes
        assert passive[0]["explanation"] == "6 events in this hour. Recorded by the phone without anyone using it."
        assert not [i for i in ctx if i["reason_code"] == "time_meaning_unknown"]
        assert [i["display"]["count"] for i in ctx if i["reason_code"] == "device_state"] == [3] * 6  # every 20 min
        assert ev["outcome"] == "consistent"
        with api_client(engine, case) as client:
            url = "/api/pattern/%s/claims/%s/evaluations/%s/items/%d/events" % (case, cl["id"], ev["evaluation_id"],
                                                                                passive[1]["ordinal"])
            r = client.get(url)
            assert r.status_code == 200, r.text
            got = r.json()
            assert (got["total"], got["stored_count"], got["returned"], got["changed_since_check"]) == (6, 6, 6, False)
            assert got["next_cursor"] is None and all(i["record_uid"] for i in got["items"])
            assert all(i["at_utc"].startswith((night + timedelta(hours=1)).date().isoformat()) for i in got["items"])
            near = [i for i in ev["items"] if i["ref_kind"] != "event_group"][0]
            assert client.get(url.rsplit("/items/", 1)[0] + "/items/%d/events" % near["ordinal"]).status_code == 404
            other = "/api/pattern/%s/claims/%s/evaluations/%s/items/%d/events" % (case, uuid.uuid4(),
                                                                                  ev["evaluation_id"], 0)
            assert client.get(other).status_code == 404
        # the statement edited after the check (a later window, the other kind): the old check's group still lists
        # the events it counted, from the window and kind it ran with
        with engine.begin() as c:
            claims.edit(c, case, cl["id"], {"kind": "active", "window_start": (night + timedelta(hours=5)).isoformat(),
                                            "window_end": (night + timedelta(hours=7)).isoformat()},
                        cl["version"], me)
        with api_client(engine, case) as client:
            got = client.get(url).json()
            assert (got["total"], got["stored_count"], got["changed_since_check"]) == (6, 6, False)


@needs_template
def test_no_contact_runs_when_an_owner_party_has_no_identity(hooks):
    """A phone holds owner parties with and without an identity key (P14 does); the check runs on both."""
    from tests.phone_pg import fld, model, refs
    from tests.test_pattern_u4_availability import _stamp
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            p = Phone()
            p.incoming_message(DAY + timedelta(hours=10))
            for n, ident in enumerate(("+12025550100", None)):  # outgoing: the owner named by number, then unnamed
                top, when = p.o, DAY + timedelta(hours=11, minutes=n)
                owner = [fld("Role", ("PartyRole", "From")), fld("IsPhoneOwner", ("Boolean", "True"))]
                if ident:
                    owner.insert(0, fld("Identifier", ("String", ident)))
                p.records += [(top, None, top, model("InstantMessage", [
                                  fld("TimeStamp", ("TimeStamp", when.isoformat())),
                                  refs("From", top + 1, kind="modelField"), refs("To", top + 2)])),
                              (top + 1, top, top, model("Party", owner)),
                              (top + 2, top, top, model("Party", [fld("Identifier", ("String", "+12025550143")),
                                                                  fld("Role", ("PartyRole", "To")),
                                                                  fld("IsPhoneOwner", ("Boolean", "False"))]))]
                p.stamps.append(_stamp(top, "TimeStamp", "InstantMessage", when))
                p.o += 3
            ext = p.make(c, case)
        build(engine, ext)
        with engine.begin() as c:
            assert c.execute(text("SELECT count(*) FILTER (WHERE identity_key IS NULL), count(*) FILTER (WHERE "
                                  "identity_key IS NOT NULL) FROM pv_comm_party WHERE extraction_id = :e AND "
                                  "is_phone_owner"), {"e": ext}).one() == (1, 1)
            me = person(c, case)
            ident = c.execute(text("SELECT id FROM phone_identities WHERE case_id = :c AND value_normalised LIKE "
                                   "'%2025550143%'"), {"c": case}).scalar_one()
            cl = confirmed(c, case, me, "no_contact", {"kind": "extraction", "extraction_id": str(ext)},
                           DAY + timedelta(hours=9), DAY + timedelta(hours=12),
                           counterpart={"identity_ids": [str(ident)]})
            ev = evaluation.evaluate(c, case, cl["id"], me.name)
        assert ev["outcome"] in ("contradicted", "contradicted_weakly")
        assert len([i for i in ev["items"] if i["role"] == "contradicting"]) == 3


@needs_template
def test_every_kind_settled_from_a_draft_reaches_confirm_and_the_model_words_stay(hooks):
    """cb-statements-rest C: each kind goes draft to confirmed through PATCH's fields, the way the form sends them."""
    setup(hooks)
    night = DAY + timedelta(hours=23)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext, other = night_phone().make(c, case), night_phone().make(c, case)
            identity = uuid.uuid4()
            c.execute(text("INSERT INTO phone_identities (id, case_id, identity_key, kind, value_normalised, "
                           "value_display) VALUES (:i, :c, 'phone:+15550100', 'phone', '+15550100', '+1 555 0100')"),
                      {"i": identity, "c": case})
        with engine.begin() as c:
            me = person(c, case)
            subj = {"kind": "extraction", "extraction_id": str(ext)}
            second = {"kind": "extraction", "extraction_id": str(other)}
            routine_place = {"lat": LAT, "lon": LON, "radius_m": 80, "cluster_id": 3, "label": "Home", "text": "the flat"}
            settle = {"inactive": {"activity": {"tolerance_minutes": 10}}, "active": {},
                      "at_place": {"place": routine_place}, "not_at_place": {"place": routine_place},
                      "with_subject": {"counterpart": second}, "apart_from_subject": {"counterpart": second},
                      "no_contact": {"counterpart": {"identity_ids": [str(identity)], "label": "the other number"}},
                      "contact": {"counterpart": {"identity_ids": [str(identity)], "label": "the other number"}}}
            assert set(settle) == set(claims.KINDS)
            aid = uuid.uuid4()
            for kind, fields in settle.items():
                d = claims.create(c, case, {"kind": kind, "subject": subj, "window_text": "that night",
                                            "place": {"text": "the flat"} if kind in claims.PLACE_KINDS else None,
                                            "source_anchor": {"quote": "I was asleep that night",
                                                              "counterpart_text": "my brother"}},
                                  me, origin="ai_draft", ai_output_id=aid, ai_model="deepseek-chat")
                assert "window_start" in d["missing_for_confirm"]
                e = claims.edit(c, case, d["id"], dict(fields, window_start=night.isoformat(), window_text="my words",
                                                       window_end=(night + timedelta(hours=8)).isoformat(),
                                                       window_zone="UTC"), d["version"], me)
                assert e["missing_for_confirm"] == [] and e["status_words"] == "Drafted by deepseek-chat, not confirmed"
                got = claims.confirm(c, case, e["id"], e["version"], me)
                assert got["status"] == "confirmed" and got["confirmed_by_name"] == me.name
                drafted = claims.get(c, case, got["id"])["as_drafted"]
                assert drafted == {"kind": kind, "window_text": "that night", "quote": "I was asleep that night",
                                   "place_text": "the flat" if kind in claims.PLACE_KINDS else None,
                                   "counterpart_text": "my brother"}
            listed = claims.list_claims(c, case)["items"]
            assert len(listed) == 8 and all(x["as_drafted"]["window_text"] == "that night" for x in listed)
            typed = claims.create(c, case, {"kind": "active", "subject": subj}, me)
            assert "as_drafted" not in typed


def test_a_period_is_its_span_in_a_check():
    """cb-statements-rest review: a usage summary ending as the window starts is outside it, and its whole span is use.
    Fails on the old code: an end equal to the window start counted as inside, and a period cut only at its start."""
    a, b = DAY, DAY + timedelta(hours=4)
    hour = timedelta(hours=1)
    assert evaluation._in_window(a - hour, a, a, b) is False
    assert evaluation._in_window(a - hour, a + timedelta(minutes=1), a, b) is True
    assert evaluation._in_window(a, None, a, b) is True
    assert evaluation._in_window(a - hour, None, a, b) is False
    assert evaluation._in_window(b, None, a, b) is False
    piece = {"state": "observed", "start": a, "end": b}
    free = evaluation._interaction_free_pieces({"e": [piece]}, [("e", a + hour, a + 2 * hour), ("e", a + 3 * hour, None)])
    assert [(s, t) for _, s, t, _p in free] == [(a, a + hour), (a + 2 * hour, a + 3 * hour), (a + 3 * hour, b)]
    free = evaluation._interaction_free_pieces({"e": [piece]}, [("e", a - hour, a + 30 * timedelta(minutes=1))])
    assert [(s, t) for _, s, t, _p in free] == [(a + timedelta(minutes=30), b)]
    free = evaluation._interaction_free_pieces({"e": [piece]}, [("e", a - hour, a), ("e", b, b + hour)])
    assert [(s, t) for _, s, t, _p in free] == [(a, b)]
