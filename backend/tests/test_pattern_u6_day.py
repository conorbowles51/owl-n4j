"""04-U6 (cb-pol item D): the Day view and the lanes window.

Synthetic phones only. Opt-in PostgreSQL through ``LOUPE_TEST_PHONE_PG_TEMPLATE_URL``.
"""
from __future__ import annotations

import json
from datetime import timedelta

from services.pattern_of_life import day
from services.phone import registry
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.test_pattern_u4_availability import DAY, setup
from tests.test_pattern_u5_places import PlacePhone, build
from tests.test_phone_mappings import hooks  # noqa: F401 (fixture)


def _phone():
    p = PlacePhone()
    p.device_event(DAY + timedelta(hours=9), "DeviceLockStatus", "Unlocked")
    p.every(DAY + timedelta(hours=1), DAY + timedelta(hours=5), 20, p.device_event, "DisplayOnOff")
    p.incoming_message(DAY + timedelta(hours=10))
    p.location(DAY + timedelta(hours=11), accuracy=10)
    return p


@needs_template
def test_the_day_view_puts_every_item_in_its_lane_and_states_availability(hooks):
    from tests.pattern_pg import api_client
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = _phone().make(c, case)
        build(engine, ext)
        subj = json.dumps({"kind": "extraction", "extraction_id": str(ext)})
        with api_client(engine, case) as client:
            r = client.get("/api/pattern/%s/day" % case, params={"subject": subj, "date": DAY.date().isoformat(),
                                                                  "zone": "UTC"})
            assert r.status_code == 200, r.text
            out = r.json()
            t = out["totals"]
            assert t["interaction"] == 1 and t["device_state"] == 12 and t["communications"] == 1
            assert t["places"] == 1 and t["money"] == 0
            assert out["truncated"] is False and out["passive_as_hourly_counts"] is False
            assert len(out["availability"][0]["hours"]) == 24
            words = {h["words"] for h in out["availability"][0]["hours"]}
            assert "No data" in words
            it = out["lanes"]["interaction"][0]
            assert it["record_uid"] and it["field"] == "StartTime" and it["phone"]
            msg = out["lanes"]["communications"][0]
            assert msg["parties"] and msg["parties"][0]["identifier"]
            w = client.get("/api/pattern/%s/window" % case, params={"at": (DAY + timedelta(hours=9)).isoformat(),
                                                                     "span": "1h", "zone": "UTC"}).json()
            assert w["phones_total"] == 1 and w["phones"][0]["totals"]["interaction"] == 1
            assert w["phones"][0]["totals"]["communications"] == 0  # 10:00 is outside 08:00 to 10:00
            ev = client.get("/api/pattern/%s/events" % case, params={
                "subject": subj, "start": DAY.isoformat(), "end": (DAY + timedelta(days=1)).isoformat()}).json()
            assert ev["total"] == ev["returned"] == sum(t[k] for k in ("interaction", "device_state", "passive",
                                                                        "others"))


@needs_template
def test_a_crowded_window_returns_passive_items_as_hourly_counts_and_says_so(hooks, monkeypatch):
    setup(hooks)
    monkeypatch.setattr(day, "PASSIVE_LIMIT", 3)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = _phone().make(c, case)
        build(engine, ext)
        with engine.connect() as c:
            out = day.window(c, [ext], {}, DAY, DAY + timedelta(days=1))
        assert out["passive_as_hourly_counts"] is True and "Show all" in out["limit_words"]
        assert out["totals"]["passive"] == sum(h["count"] for h in out["passive_hours"])
        assert out["totals"]["interaction"] == 1  # other lanes keep every item


@needs_template
def test_the_window_over_every_phone_uses_the_case_zone_and_says_on_what_basis(hooks):
    """The window covers several phones, so it is drawn in the case zone of 03 section 4.6, not the first phone's."""
    from sqlalchemy import text
    from tests.pattern_pg import api_client
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            _phone().make(c, case)
        at = (DAY + timedelta(hours=9)).isoformat()
        with api_client(engine, case) as client:
            unset = client.get("/api/pattern/%s/window" % case, params={"at": at, "span": "1h"}).json()
            assert unset["zone"] == "UTC" and unset["zone_basis"] == "utc_default"
            with engine.begin() as c:
                c.execute(text("INSERT INTO case_display_settings (case_id, time_zone, updated_by) SELECT id, "
                               "'America/New_York', owner_user_id FROM cases WHERE id = :c"), {"c": case})
            out = client.get("/api/pattern/%s/window" % case, params={"at": at, "span": "1h"}).json()
            assert out["zone"] == "America/New_York" and out["zone_basis"] == "case_setting"
            chosen = client.get("/api/pattern/%s/window" % case, params={"at": at, "span": "1h", "zone": "UTC"}).json()
            assert chosen["zone"] == "UTC" and chosen["zone_basis"] == "chosen"
