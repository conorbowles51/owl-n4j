"""Guidance settings (lx-guide): a person's choice follows them; the case default applies until they choose."""
from __future__ import annotations

import uuid

import pytest

from services import guidance


def test_guidance_is_on_with_no_choice_and_no_case_default():
    out = guidance.resolve([], None)
    assert out == {"guidance": "on", "source": "default", "case_default": None, "tips_off": [], "tours": {},
                   "history_collapsed": False}


def test_a_case_default_of_off_applies_until_the_person_chooses():
    assert guidance.resolve([], "off")["guidance"] == "off"
    assert guidance.resolve([], "off")["source"] == "case"
    own = guidance.resolve(["guide:on"], "off")
    assert (own["guidance"], own["source"]) == ("on", "user")
    assert guidance.resolve(["guide:off"], None)["guidance"] == "off"


def test_tours_and_hidden_tips_are_read_from_marks():
    out = guidance.resolve(["guide:tip_off:after-upload", "guide:tour:graph:skipped", "guide:tour:graph:step:2",
                            "guide:tour:map:done", "guide:tour:map:step:x"], None)
    assert out["tips_off"] == ["after-upload"]
    assert out["tours"] == {"graph": {"state": "skipped", "step": 2}, "map": {"state": "done"}}


@pytest.mark.parametrize("bad", ["", "Graph", "a:b", "x" * 41, "../x"])
def test_names_outside_the_pattern_are_refused(bad):
    with pytest.raises(guidance.GuidanceError):
        guidance._name(bad)


# Database round trips (a scratch PostgreSQL at the alembic head; skipped without one).
from tests.phone_pg import fresh_engine, make_case, needs_template  # noqa: E402
from sqlalchemy import text  # noqa: E402


def _person(c, email):
    uid = uuid.uuid4()
    c.execute(text("INSERT INTO users (id, email, name, password_hash, global_role, is_active) VALUES "
                   "(:i, :e, 'Synthetic', 'x', 'guest', true)"), {"i": uid, "e": email})
    return uid


@needs_template
def test_turning_guidance_off_is_kept_for_that_person_only_and_phone_marks_are_unchanged():
    from services.phone import job_list
    with fresh_engine() as engine:
        with engine.begin() as c:
            me, them = _person(c, "a@synthetic.invalid"), _person(c, "b@synthetic.invalid")
            job_list.set_mark(c, me, "first_phone_card_seen")
            guidance.set_guidance(c, me, "off")
        with engine.begin() as c:  # a new session: the choice is still there
            assert guidance.read(c, me)["guidance"] == "off"
            assert guidance.read(c, them)["guidance"] == "on"
            assert list(job_list.marks(c, me)) == ["first_phone_card_seen"]
            assert guidance.set_guidance(c, me, "on")["guidance"] == "on"
            assert guidance.read(c, me)["source"] == "user"


@needs_template
def test_a_tour_resumes_at_its_step_and_show_again_brings_it_back():
    with fresh_engine() as engine:
        with engine.begin() as c:
            me = _person(c, "a@synthetic.invalid")
            guidance.set_tour(c, me, "graph", step=1)
            out = guidance.set_tour(c, me, "graph", step=2, state="skipped")
            assert out["tours"]["graph"] == {"state": "skipped", "step": 2}
            assert guidance.set_tour(c, me, "graph", state="done")["tours"]["graph"]["state"] == "done"
            guidance.hide_tip(c, me, "after-merge")
            out = guidance.show_tips_again(c, me)
            assert out["tours"] == {} and out["tips_off"] == []


@needs_template
def test_the_case_default_reaches_everyone_who_has_not_chosen():
    with fresh_engine() as engine:
        with engine.begin() as c:
            admin, member = _person(c, "a@synthetic.invalid"), _person(c, "b@synthetic.invalid")
            case = make_case(c)
            guidance.set_case_default(c, case, "off", admin)
            assert guidance.read(c, member, case)["guidance"] == "off"
            guidance.set_guidance(c, member, "on")
            assert guidance.read(c, member, case)["guidance"] == "on"
            guidance.set_case_default(c, case, None, admin)
            assert guidance.read(c, admin, case)["case_default"] is None
