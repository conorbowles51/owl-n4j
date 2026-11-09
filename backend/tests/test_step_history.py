"""The step history strip (lx-guide H-M): one person's steps through one case, kept server-side for 90 days.

Pure checks run anywhere; database round trips need a scratch PostgreSQL at the alembic head
(LOUPE_TEST_PHONE_PG_TEMPLATE_URL) and skip without one.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from services import guidance, step_history as H
from tests.phone_pg import fresh_engine, make_case, needs_template

PAY = {"tab": "transactions", "filters": {"account": "BBVA 0110280038", "month": "2022-11"}, "sort": "date",
       "selected": {"kind": "financial_transaction", "id": "tx-42"}, "anchor": "tx-40"}


@pytest.mark.parametrize("name,screen,path,state,item", [
    ("", "financial", "/cases/x/financial", {}, None),
    ("A step", "Financial!", "/cases/x/financial", {}, None),
    ("A step", "financial", "https://elsewhere.test/", {}, None),
    ("A step", "financial", "/cases/x/financial", {"big": "x" * 17_000}, None),
    ("A step", "financial", "/cases/x/financial", {}, {"kind": "financial_transaction"}),
])
def test_a_step_that_could_not_be_reopened_is_refused(name, screen, path, state, item):
    with pytest.raises(H.StepError):
        H._clean(name, screen, path, state, item)


def test_a_step_name_is_one_line_and_at_most_200_characters():
    name = H._clean("Transactions ·\n BBVA  " + "x" * 300, "financial", "/cases/x/financial", {}, None)[0]
    assert name.startswith("Transactions · BBVA x") and len(name) == 200


def _person(c, email):
    uid = uuid.uuid4()
    c.execute(text("INSERT INTO users (id, email, name, password_hash, global_role, is_active) VALUES "
                   "(:i, :e, 'Synthetic', 'x', 'guest', true)"), {"i": uid, "e": email})
    return uid


@needs_template
def test_a_payment_step_comes_back_with_its_filters_and_scroll_anchor_and_stays_private():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            me, them = _person(c, "a@synthetic.invalid"), _person(c, "b@synthetic.invalid")
            path = f"/cases/{case}/financial?tab=transactions"
            step = H.record(c, me, case, name="Transactions · BBVA 0110280038 · Nov 2022", screen="financial",
                            path=path, state=PAY, item={"kind": "financial_transaction", "id": "tx-42"})
        with engine.begin() as c:  # another session, another computer
            again = H.get(c, me, case, step["id"])
            assert (again["path"], again["state"], again["item"]["id"]) == (path, PAY, "tx-42")
            assert H.get(c, them, case, step["id"]) is None
            assert H.listing(c, them, case)["total"] == 0


@needs_template
def test_a_tiny_change_merges_into_the_last_step_and_never_rewrites_an_older_one():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            me = _person(c, "a@synthetic.invalid")
            base = f"/cases/{case}/financial"
            one = H.record(c, me, case, name="Transactions", screen="financial", path=base, state={"q": "a"})
            merged = H.record(c, me, case, name="Transactions", screen="financial", path=base, state={"q": "arr"},
                              replaces=one["id"])
            assert merged["merged"] and merged["id"] == one["id"]
            two = H.record(c, me, case, name="Graph · Jose", screen="graph", path=f"/cases/{case}/graph", state={})
            # a replaces that names an older step adds a new step instead
            three = H.record(c, me, case, name="Transactions", screen="financial", path=base, state={"q": "b"},
                             replaces=one["id"])
            assert not three["merged"] and three["id"] not in (one["id"], two["id"])
            # the same view again (a reload) is one step, not two
            assert H.record(c, me, case, name="Transactions", screen="financial", path=base,
                            state={"q": "b"})["id"] == three["id"]
            out = H.listing(c, me, case)
            assert [s["name"] for s in out["steps"]] == ["Transactions", "Graph · Jose", "Transactions"]
            assert out["steps"][2]["state"] == {"q": "arr"} and out["total"] == 3
            assert H.listing(c, me, case, q="graph")["total"] == 1


@needs_template
def test_steps_older_than_90_days_go_and_clear_removes_only_mine():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            me, them = _person(c, "a@synthetic.invalid"), _person(c, "b@synthetic.invalid")
            old = H.record(c, me, case, name="Old", screen="graph", path=f"/cases/{case}/graph")
            c.execute(text("UPDATE case_steps SET at = :t WHERE id = :i"),
                      {"t": datetime.now(timezone.utc) - timedelta(days=91), "i": old["id"]})
            H.record(c, me, case, name="New", screen="map", path=f"/cases/{case}/map")
            H.record(c, them, case, name="Theirs", screen="map", path=f"/cases/{case}/map")
            assert [s["name"] for s in H.listing(c, me, case)["steps"]] == ["New"]
            assert H.clear(c, me, case) == 1
            assert H.listing(c, them, case)["total"] == 1


@needs_template
def test_the_folded_strip_is_kept_for_the_person_across_sessions():
    with fresh_engine() as engine:
        with engine.begin() as c:
            me = _person(c, "a@synthetic.invalid")
            assert guidance.set_history_collapsed(c, me, True)["history_collapsed"] is True
        with engine.begin() as c:  # signed out and in again: a new session reads the same marks
            assert guidance.read(c, me)["history_collapsed"] is True
            assert guidance.set_history_collapsed(c, me, False)["history_collapsed"] is False


@needs_template
def test_a_run_of_steps_is_added_to_a_theory_as_one_trail_with_each_step_reopenable():
    from sqlalchemy.orm import Session
    from postgres.models.user import User
    from services import theory_additions as T
    from services.workspace_entry_service import create_entry
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            me = _person(c, "a@synthetic.invalid")
            other = make_case(c)
            steps = [H.record(c, me, case, name=f"Step {n}", screen="graph", path=f"/cases/{case}/graph?n={n}",
                              state={"n": n}) for n in range(1, 6)]
            foreign = H.record(c, me, other, name="Elsewhere", screen="graph", path=f"/cases/{other}/graph")
        with Session(engine) as db:
            user = db.get(User, me)
            theory = create_entry(db, case_id=case, current_user=user, entry_type="theory", title="The route",
                                  body="How the money moved")
            run = steps[1:4]
            members = [{"type": "history_step", "id": s["id"], "label": s["name"]} for s in run]
            members.append({"type": "history_step", "id": foreign["id"], "label": foreign["name"]})
            how = {"steps": [{k: s[k] for k in ("id", "name", "screen", "path", "state", "at")} for s in run]}
            out = T.add(db, case_id=case, entry_id=theory["id"], user=user, surface="history",
                        why="the trail to the transfer", narrative="From the account to the person who received it",
                        group={"group_type": "step_trail", "members": members, "how": how,
                               "words": "steps 2 to 4"})
            db.commit()
            assert (out["group"]["member_count"], out["group"]["left_out"]) == (3, 1)
            assert "from your step history" in out["group"]["label"]
            added = {a["link_id"]: a for a in T.reading(db, case_id=case, entry_id=theory["id"])["additions"]}
            trail = added[out["added_link_ids"][0]]
            assert [s["path"] for s in trail["how"]["steps"]] == [s["path"] for s in run]
        with engine.begin() as c:  # the trail keeps its steps after the history is cleared
            H.clear(c, me, case)
        with Session(engine) as db:
            added = {a["link_id"]: a for a in T.reading(db, case_id=case, entry_id=theory["id"])["additions"]}
            assert [s["name"] for s in added[out["added_link_ids"][0]]["how"]["steps"]] == ["Step 2", "Step 3", "Step 4"]
