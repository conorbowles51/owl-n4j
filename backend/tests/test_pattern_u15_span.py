"""04 decisions 37 and 38 (cb-pol Gate F): a phone's usual span, and the per-family counts kept at build time.

Synthetic phones only. Opt-in PostgreSQL through ``LOUPE_TEST_PHONE_PG_TEMPLATE_URL``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from services.pattern_of_life import activity, subjects
from services.phone import registry
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.test_pattern_u4_availability import DAY, Phone, build, setup
from tests.test_phone_mappings import hooks  # noqa: F401 (fixture)


@needs_template
def test_stray_far_dates_are_set_apart_and_counted_and_families_are_kept_at_build(hooks):
    from tests.pattern_pg import api_client
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            p = Phone()
            for d in range(30):  # a month of use, then two stray dates decades on (a reminder, a clock reset)
                p.every(DAY + timedelta(days=d, hours=9), DAY + timedelta(days=d, hours=10), 20, p.device_event,
                        "DisplayOnOff")
            stray = [datetime(2057, 8, 30, 10, tzinfo=timezone.utc), datetime(2057, 8, 30, 11, tzinfo=timezone.utc)]
            for t in stray:
                p.device_event(t, "DisplayOnOff")
            ext = p.make(c, case)
        build(engine, ext)
        with engine.connect() as c:
            span = subjects.usual_span(c, ext)
            assert (span["first"], span["last"]) == (DAY.date(), (DAY + timedelta(days=29)).date())
            assert span["set_apart"] == 2 and (span["set_apart_first"], span["set_apart_last"]) == tuple(stray)
            kept = c.execute(text("SELECT families FROM pol_projection_state WHERE extraction_id = :e"),
                             {"e": ext}).scalar()
            assert kept == activity.families(c, ext) and kept[0]["events"] == 30 * 3 + 2
            # a projection built before the families were kept reads them from the events, the same
            c.execute(text("UPDATE pol_projection_state SET families = NULL WHERE extraction_id = :e"), {"e": ext})
            computed = subjects.extractions(c, case)
            c.rollback()
            assert subjects.extractions(c, case) == computed
        with api_client(engine, case) as client:
            got = client.get("/api/pattern/%s/subjects" % case).json()["extractions"][0]
            assert got["last"].startswith("2057-08-30")  # the last event, as recorded
            assert got["usual_span"]["last"] == (DAY + timedelta(days=29)).date().isoformat()
            assert got["usual_span"]["set_apart"] == 2


@needs_template
def test_a_phone_with_no_far_dates_keeps_its_whole_span(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            p = Phone()
            for d in (0, 60, 120):  # gaps under 90 days: one run
                p.device_event(DAY + timedelta(days=d, hours=9), "DisplayOnOff")
            ext = p.make(c, case)
        build(engine, ext)
        with engine.connect() as c:
            span = subjects.usual_span(c, ext)
        assert (span["first"], span["last"], span["set_apart"]) == (DAY.date(), (DAY + timedelta(days=120)).date(), 0)


def test_a_grid_pauses_collection_only_while_it_builds_and_restores_it():
    import gc
    import threading

    from services.pattern_of_life import grid
    was = gc.isenabled()
    try:
        gc.enable()
        first_in, second_done, release = threading.Event(), threading.Event(), threading.Event()
        seen = {}

        def one():
            with grid._collection_paused():
                first_in.set()
                release.wait(5)
                seen["first_end"] = gc.isenabled()

        def two():
            first_in.wait(5)
            with grid._collection_paused():
                seen["inside"] = gc.isenabled()
            seen["after_second"] = gc.isenabled()  # the first grid is still building
            second_done.set()

        a, b = threading.Thread(target=one), threading.Thread(target=two)
        a.start(); b.start()
        second_done.wait(5)
        release.set()
        a.join(5); b.join(5)
        assert seen == {"inside": False, "after_second": False, "first_end": False}
        assert gc.isenabled() is True  # resumed when the last grid ended
        gc.disable()
        with grid._collection_paused():
            pass
        assert gc.isenabled() is False  # left off when it was off before
        gc.enable()
        try:
            with grid._collection_paused():
                raise ValueError("synthetic")
        except ValueError:
            pass
        assert gc.isenabled() is True
    finally:
        (gc.enable if was else gc.disable)()
