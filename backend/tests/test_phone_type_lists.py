"""03 section 7.5 and test P-8: the list for each record type, through the real interpretation path and the route.
Keyset windows, the exact total, sort, filters, sensitive masking, corrections and copies from another source
(02 decision 39). Synthetic data only."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from services.phone import sweep, type_lists
from tests.phone_pg import fld, fresh_engine, make_case, make_extraction, model, needs_template, refs

pytestmark = needs_template


def stamp(ordinal, body_path, field, mt, instant):
    return {"o": ordinal, "bp": body_path, "mt": mt, "fn": field, "ot": instant.isoformat(), "i": instant,
            "os": "explicit"}


def day(d, h=12):
    return datetime(2023, 3, d, h, 0, tzinfo=timezone.utc)


def records():
    """Five web visits (two dated, one deleted), a saved password, a contact with a nested number and a copy of the
    visit from another source held under RelatedModels."""
    out, stamps = [], []

    def visit(o, url, when=None, parent=None, top=None, **attrs):
        fields = [fld("Url", ("String", url))]
        if when:
            fields.append(fld("LastVisited", ("TimeStamp", when.isoformat())))
            stamps.append(stamp(o, "1.0", "LastVisited", "VisitedPage", when))
        return (o, parent, o if top is None else top, model("VisitedPage", fields, **attrs))

    out.append(visit(0, "b.example", day(2)))
    out.append(visit(1, "a.example", day(4), deleted_state="Deleted"))
    out.append(visit(2, "c.example"))
    out.append(visit(3, "e.example", day(3)))
    owner = model("VisitedPage", [fld("Url", ("String", "d.example")), ["RelatedModels", None, None, [["@", 5]]]])
    out.append((4, None, 4, owner))
    out.append(visit(5, "d.example", parent=4, top=4, isrelated="True", source_index="2"))
    out.append((6, None, 6, model("Password", [fld("Service", ("String", "mail")), fld("Data", ("String", "hunter2"))])))
    out.append((7, None, 7, model("Contact", [fld("Name", ("String", "Ana")),
                                              refs("Entries", 8)])))
    out.append((8, 7, 7, model("PhoneNumber", [fld("Value", ("String", "+12025550143"))])))
    return out, stamps


@pytest.fixture
def world():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            other = make_case(c)
            rows, stamps = records()
            ext = make_extraction(c, case, rows, timestamps=stamps)
            far = make_extraction(c, other, rows, timestamps=stamps, label="C9")
        sweep.interpret_one(engine, ext)
        sweep.interpret_one(engine, far)
        yield {"engine": engine, "case": str(case), "ext": str(ext), "other": str(other), "far": str(far)}


def listed(w, mt, **kw):
    with w["engine"].connect() as c:
        return type_lists.page(c, w["case"], mt, extraction_ids=[w["ext"]], **kw)


def test_total_and_windows_walk_every_record_once_in_each_sort(world):
    for sort in type_lists.SORTS:
        for direction in ("asc", "desc"):
            seen, cursor, windows = [], None, 0
            while True:
                p = listed(world, "VisitedPage", sort=sort, direction=direction, limit=2, cursor=cursor)
                assert p["total"] == 6
                seen += [i["record_uid"] for i in p["items"]]
                windows += 1
                cursor = p["next"]
                if not cursor:
                    break
            assert windows == 3 and len(seen) == 6 and len(set(seen)) == 6, (sort, direction)


def test_time_order_puts_records_with_no_time_last_either_way(world):
    up = [i["title"] for i in listed(world, "VisitedPage", sort="time")["items"]]
    assert up[:3] == ["b.example", "e.example", "a.example"]
    down = [i["title"] for i in listed(world, "VisitedPage", sort="time", direction="desc")["items"]]
    assert down[:3] == ["a.example", "e.example", "b.example"]
    assert set(up[3:]) == set(down[3:]) == {"c.example", "d.example"}


def test_title_order_is_the_value_not_the_type_word(world):
    assert [i["title"] for i in listed(world, "VisitedPage", sort="title", placement="top")["items"]] == \
        ["a.example", "b.example", "c.example", "d.example", "e.example"]


def test_filters_count_exactly_and_a_date_filter_says_what_it_left_out(world):
    assert listed(world, "VisitedPage", placement="top")["total"] == 5
    assert listed(world, "VisitedPage", placement="nested")["total"] == 1
    assert listed(world, "VisitedPage", deleted="only")["total"] == 1
    assert listed(world, "VisitedPage", deleted="hide")["total"] == 5
    p = listed(world, "VisitedPage", day_from="2023-03-03", day_to="2023-03-04")
    assert p["total"] == 2 and p["no_time"] == 3
    assert listed(world, "VisitedPage")["no_time"] == 0  # no date filter: nothing is left out


def test_a_related_copy_is_marked_and_sits_under_its_owner(world):
    p = listed(world, "VisitedPage", copies="only")
    assert p["total"] == 1
    copy = p["items"][0]
    assert copy["copy"] is True and copy["nested"] is True and copy["source_index"] == "2"
    assert copy["owner"]["title"] == "d.example"
    assert listed(world, "VisitedPage", copies="hide")["total"] == 5
    assert not any(i["copy"] for i in listed(world, "VisitedPage", copies="hide")["items"])


def test_the_copy_flag_reaches_what_a_copy_derives_and_not_its_owner(world):
    with world["engine"].connect() as c:
        n = c.execute(text("SELECT count(*) FROM phone_texts WHERE extraction_id = :e AND 'related_copy' = ANY(flags)"),
                      {"e": world["ext"]}).scalar()
        total = c.execute(text("SELECT count(*) FROM phone_record_summaries WHERE extraction_id = :e AND "
                               "'related_copy' = ANY(flags)"), {"e": world["ext"]}).scalar()
    assert n == 1 and total == 1


def test_columns_come_from_the_field_names_and_cells_from_the_record(world):
    p = listed(world, "VisitedPage", sort="title", placement="top")
    assert {c["id"] for c in p["columns"]} >= {"Url", "LastVisited"}
    first = p["items"][0]
    assert first["cells"]["Url"]["text"] == "a.example"
    assert first["cells"]["LastVisited"]["text"] == "Sat, Mar 4, 2023, 12:00:00 PM UTC"
    assert first["deleted_state"] == "Deleted"


def test_a_nested_record_shows_in_its_owners_cell(world):
    p = listed(world, "Contact")
    assert p["items"][0]["cells"]["Entries"]["text"] == "+12025550143"


def test_sensitive_values_stay_masked_in_the_list(world):
    p = listed(world, "Password")
    cell = p["items"][0]["cells"]["Data"]
    assert cell == {"text": "••••", "more": 0, "masked": True}
    assert "hunter2" not in str(p)
    assert next(c for c in p["columns"] if c["id"] == "Data")["sensitive"] is True


def test_a_corrected_value_shows_with_its_original_beside_it(world):
    with world["engine"].connect() as c:
        uid = type_lists.page(c, world["case"], "Contact", extraction_ids=[world["ext"]])["items"][0]["record_uid"]
    with world["engine"].begin() as c:
        c.execute(text("SET LOCAL session_replication_role = replica"))  # only the reading side is under test here
        c.execute(text(
            "INSERT INTO phone_value_corrections (id, case_id, extraction_id, record_uid, field_path, value_index, "
            "value_type, machine_text, corrected_text, decision_id) VALUES (:i, :c, :e, :u, 'Name', 0, 'String', "
            "'Ana', 'Anna', :d)"), {"i": uuid.uuid4(), "c": world["case"], "e": world["ext"], "u": uid, "d": uuid.uuid4()})
    cell = listed(world, "Contact")["items"][0]["cells"]["Name"]
    assert cell["text"] == "Anna" and cell["original"] == "Ana"


def test_a_message_opens_in_conversations_and_anything_else_in_the_panel(world):
    assert {i["open_in"] for i in listed(world, "VisitedPage")["items"]} == {"panel"}
    from tests.phone_streams_fixture import at, phone
    with world["engine"].begin() as c:
        ext, _ = phone(c, world["case"], events=[dict(
            kind="message", instant=at(2023, 3, 14), body="hello", direction="incoming", thread="t",
            parties=[("phone:+12025550143", "sender", False, None, None), ("phone:+12025550100", "recipient", True, None, None)])])
        mt = c.execute(text("SELECT DISTINCT model_type FROM phone_record_summaries WHERE extraction_id = :e"),
                       {"e": ext}).scalar()
        got = type_lists.page(c, world["case"], mt, extraction_ids=[ext])
    assert got["total"] == 1 and got["items"][0]["open_in"] == "conversations"


def test_a_phone_of_another_case_is_not_found(world):
    with world["engine"].connect() as c:
        with pytest.raises(type_lists.NotFound):
            type_lists.page(c, world["case"], "VisitedPage", extraction_ids=[world["far"]])


def test_a_window_from_before_a_new_reading_is_refused_not_mixed(world):
    p = listed(world, "VisitedPage", limit=2)
    with world["engine"].begin() as c:
        c.execute(text("UPDATE phone_interpretation_state SET generation = generation + 1 WHERE extraction_id = :e"),
                  {"e": world["ext"]})
    with pytest.raises(type_lists.StaleWindow):
        listed(world, "VisitedPage", limit=2, cursor=p["next"])


def test_a_cursor_cannot_be_used_for_another_list(world):
    p = listed(world, "VisitedPage", limit=2)
    with pytest.raises(type_lists.StaleWindow):
        listed(world, "VisitedPage", limit=2, cursor=p["next"], sort="title")
    with pytest.raises(type_lists.BadCursor):
        listed(world, "VisitedPage", cursor="not-a-cursor")


def test_p8_every_summary_figure_equals_the_list_it_opens(world):
    from services.phone import profile
    with world["engine"].connect() as c:
        p = profile.profile(c, world["case"], world["ext"])
    rows = {t["model_type"]: t for t in p["coverage"]}
    assert {"VisitedPage", "Password", "Contact", "PhoneNumber"} <= set(rows)
    assert rows["PhoneNumber"]["records"] == 0 and rows["PhoneNumber"]["nested"] == 1
    for t in p["coverage"]:
        assert listed(world, t["model_type"], placement="top")["total"] == t["records"]
        assert listed(world, t["model_type"], placement="nested")["total"] == t["nested"]
        assert listed(world, t["model_type"], copies="only")["total"] == t["copies"]
    for d in p["deleted"]["by_type"]:
        assert listed(world, d["model_type"], placement="top", deleted="only")["total"] == d["deleted"] + d["trash"]


def test_the_record_panel_marks_a_copy_and_lists_it_under_its_owner(world):
    from services.phone import records
    copy = listed(world, "VisitedPage", copies="only")["items"][0]
    with world["engine"].connect() as c:
        got = records.record_detail(c, world["case"], copy["record_uid"])
        owner = records.record_detail(c, world["case"], copy["owner"]["record_uid"])
    assert got["is_copy"] is True and got["copy_of"]["record_uid"] == copy["owner"]["record_uid"]
    assert owner["is_copy"] is False
    assert [r["record_uid"] for r in owner["related_copies"]] == [copy["record_uid"]]


def test_the_route_answers_for_a_member_and_hides_a_phone_of_another_case(world):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from postgres.models.enums import GlobalRole
    from postgres.models.user import User
    from postgres.session import get_db
    from routers.phones import router
    from routers.users import get_current_db_user

    Session = sessionmaker(bind=world["engine"])
    with world["engine"].connect() as c:
        owner = c.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": world["case"]}).scalar()
        email = c.execute(text("SELECT email FROM users WHERE id = :u"), {"u": owner}).scalar()
    app = FastAPI()
    app.include_router(router)

    def db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_current_db_user] = lambda: User(
        id=owner, email=email, name="Owner", password_hash="x", global_role=GlobalRole.user, is_active=True)
    api = TestClient(app)
    base = {"case_id": world["case"], "phones": world["ext"]}
    r = api.get("/api/phones/record-lists/VisitedPage", params={**base, "placement": "top", "limit": 2})
    assert r.status_code == 200 and r.json()["total"] == 5 and r.json()["next"]
    r2 = api.get("/api/phones/record-lists/VisitedPage", params={**base, "placement": "top", "limit": 2, "cursor": r.json()["next"]})
    assert r2.status_code == 200 and r2.json()["items"][0]["record_uid"] != r.json()["items"][0]["record_uid"]
    assert api.get("/api/phones/record-lists/VisitedPage", params={"case_id": world["case"], "phones": world["far"]}).status_code == 404
    assert api.get("/api/phones/record-lists/VisitedPage", params={**base, "from": "2023-03-05", "to": "2023-03-01"}).status_code == 422
    assert api.get("/api/phones/record-lists/VisitedPage", params={**base, "cursor": "nonsense"}).status_code == 422
    stale = api.get("/api/phones/record-lists/VisitedPage", params={**base, "sort": "title", "cursor": r.json()["next"]})
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "stale_snapshot"


def _copy_case(c, case):
    """A search and its copy from another source: same words and time; a second copy saying something else."""
    when = day(9)
    rows = [
        (0, None, 0, model("SearchedItem", [fld("Value", ("String", "invented words")),
                                            fld("TimeStamp", ("TimeStamp", when.isoformat())),
                                            ["RelatedModels", None, None, [["@", 1], ["@", 2]]]])),
        (1, 0, 0, model("SearchedItem", [fld("Value", ("String", "invented words")),
                                         fld("TimeStamp", ("TimeStamp", when.isoformat()))], isrelated="True", source_index="1")),
        (2, 0, 0, model("SearchedItem", [fld("Value", ("String", "other words")),
                                         fld("TimeStamp", ("TimeStamp", day(10).isoformat()))], isrelated="True", source_index="2")),
    ]
    stamps = [stamp(0, "1.0", "TimeStamp", "SearchedItem", when), stamp(1, "1.0", "TimeStamp", "SearchedItem", when),
              stamp(2, "1.0", "TimeStamp", "SearchedItem", day(10))]
    return make_extraction(c, case, rows, timestamps=stamps)


def test_a_copy_repeating_its_owner_is_one_fact_and_a_copy_saying_more_is_kept():
    from services.phone_analysis import fields as FV
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            ext = _copy_case(c, case)
        sweep.interpret_one(engine, ext)
        with engine.connect() as c:
            # every record stays readable and listed
            assert c.execute(text("SELECT count(*) FROM pv_record WHERE extraction_id = :e"), {"e": ext}).scalar() == 3
            assert c.execute(text("SELECT count(*) FROM pv_time WHERE extraction_id = :e"), {"e": ext}).scalar() == 3
            # the timeline shows the repeated time once, the different one too
            got = sorted(r[0].day for r in c.execute(text(
                "SELECT instant FROM pv_timeline_entry WHERE extraction_id = :e"), {"e": ext}))
            assert got == [9, 10]
            # search still finds the copy's text; a reader of evidence sees each fact once
            texts = c.execute(text("SELECT value, 'same_as_owner' = ANY(flags) FROM pv_text WHERE extraction_id = :e "
                                   "AND field_path = 'Value' ORDER BY value, 2"), {"e": ext}).fetchall()
            assert [tuple(t) for t in texts] == [("invented words", False), ("invented words", True), ("other words", False)]
            vals = FV.field_values(c, ext, ("SearchedItem",), ("Value",))
            assert sorted(v["values"]["Value"][0] for v in vals.values()) == ["invented words", "other words"]
            assert FV.type_counts(c, ext, ("SearchedItem",)) == {"SearchedItem": 1}
