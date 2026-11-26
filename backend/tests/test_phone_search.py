"""Search every phone (Phones screen 2; lx-phonesearch A to D): counts by kind and phone, grouped hits, hidden fields,
deleted items, files, the period, the person saved differently on each phone and the next steps.

Invented data only: 555 numbers and made-up names and text.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from services.phone import fold as F
from services.phone import ids
from services.search import phone_search as P
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import GEN, at, phone

pytestmark = needs_template
OWNER1, OWNER2, PELL, NELL = ("phone:+12025550100", "phone:+12025550101", "phone:+12025550177",
                              "phone:+12025550188")


def record(c, case, ext, ordinal, model_type, fields, *, instant=None, deleted=None):
    """A top-level record that is not a message (a contact, a typed word, a page) with its texts.
    ``fields``: [(field, value, sensitive)]."""
    uid = ids.record_uid(ext, 0, ordinal)
    c.execute(text(
        "INSERT INTO phone_record_summaries (case_id, extraction_id, document_index, ordinal, record_uid, "
        "root_record_uid, locator, model_type, generation, is_top_level, title, first_instant, has_time, has_point, "
        "deleted_state) VALUES (:c, :e, 0, :o, :u, :u, :loc, :mt, :g, true, 'synthetic', :i, :ht, false, :ds)"),
        {"c": case, "e": ext, "o": ordinal, "u": uid, "loc": "%s/0/r%d" % (ext, ordinal), "mt": model_type, "g": GEN,
         "i": instant, "ht": instant is not None, "ds": deleted})
    for k, (field, value, sensitive) in enumerate(fields):
        c.execute(text(
            "INSERT INTO phone_texts (case_id, extraction_id, document_index, ordinal, record_uid, root_record_uid, "
            "locator, model_type, generation, text_uid, body_path, field_name, field_path, value_index, value, "
            "value_folded, effective_value, is_sensitive) VALUES (:c, :e, 0, :o, :u, :u, :loc, :mt, :g, :tu, '0', :f, "
            ":fp, 0, :v, :vf, :v, :s)"),
            {"c": case, "e": ext, "o": ordinal, "u": uid, "loc": "%s/0/r%d" % (ext, ordinal), "mt": model_type,
             "g": GEN, "tu": uuid.uuid5(uid, field + str(k)), "f": field, "fp": field, "v": value, "vf": F.fold(value),
             "s": sensitive})
    return str(uid)


def a_file(c, ext, ordinal, path, deleted=None):
    fid = uuid.uuid4()
    c.execute(text(
        "INSERT INTO phone_files (extraction_id, document_index, ordinal, file_uid, local_path, body) VALUES (:e, 0, :o, "
        ":u, :p, CAST(:b AS jsonb))"),
        {"e": ext, "o": ordinal, "u": fid, "p": path, "b": '[null, {"deleted": "%s"}]' % deleted if deleted else "[]"})
    return str(fid)


def msg(instant, sender, recips, body, owner, thread="t", **kw):
    parties = [(sender, "sender", sender == owner, None, None)] + [(r, "recipient", r == owner, None, None)
                                                                   for r in recips]
    return dict(kind="message", instant=instant, body=body, parties=parties, thread=thread,
                direction="outgoing" if sender == owner else "incoming", **kw)


@pytest.fixture
def world():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            p1, ev1 = phone(c, case, label="C1", owner=OWNER1, contacts={PELL: "Dorian (office)"}, events=[
                msg(at(2024, 3, 11, 18), NELL, [OWNER1], "is Pell in tomorrow?", OWNER1),
                msg(at(2024, 3, 12, 10), OWNER1, [NELL], "Tell Pell the checks are in the drawer", OWNER1,
                    deleted_state="Deleted"),
                msg(at(2024, 6, 1, 9), NELL, [OWNER1], "pell again in June", OWNER1)])
            p2, ev2 = phone(c, case, label="C2", owner=OWNER2, contacts={PELL: "D Pell"}, events=[
                msg(at(2024, 3, 13, 9), PELL, [OWNER2], "see you at the office", OWNER2)])
            p3, _ = phone(c, case, label="C3", owner=PELL, events=[
                msg(at(2024, 3, 14, 9), PELL, [NELL], "nothing to see", PELL)])
            recs = {
                "contact": record(c, case, p1, 1000, "Contact", [("Name", "Dorian Pell", False),
                                                                  ("Value", "(202) 555-0177", False)]),
                "word": record(c, case, p1, 1001, "DictionaryWord", [("Word", "Pell", True), ("Source", "keyboard",
                                                                                          False)]),
                "almost": record(c, case, p2, 1002, "DictionaryWord", [("Word", "Pellucid", True)]),
                "page": record(c, case, p1, 1003, "VisitedPage", [("Title", "dorian pell corwen street dental", False)],
                               instant=at(2024, 3, 9, 23)),
                "late_page": record(c, case, p2, 1004, "SearchedItem", [("Value", "pell hours", False)],
                                    instant=at(2024, 7, 1, 9)),
            }
            files = {"invoice": a_file(c, p2, 1, "/private/var/mobile/Media/DCIM/Pell_invoice-2024.pdf"),
                     "folder_only": a_file(c, p2, 2, "/private/var/Pell/photo.jpg")}
        yield {"engine": engine, "case": case, "p": [str(p1), str(p2), str(p3)], "ev1": ev1, "recs": recs,
               "files": files}


def _search(w, q, **kw):
    with w["engine"].connect() as c:
        return P.phone_search(c, w["case"], q, **kw)


def _kinds(out):
    return {k["kind"]: k for k in out["kinds"]}


def test_counts_by_kind_and_phone_are_exact_and_add_up(world):
    out = _search(world, "pell")
    k = _kinds(out)
    p1, p2, p3 = world["p"]
    assert k["messages"]["by_phone"] == {p1: 3, p2: 0, p3: 0}
    assert k["contacts"]["by_phone"] == {p1: 1, p2: 0, p3: 0}  # found by its name: one contact
    assert k["web"]["by_phone"] == {p1: 1, p2: 1, p3: 0}
    assert k["typed_words"]["by_phone"] == {p1: 1, p2: 0, p3: 0}  # "Pellucid" is hidden: only its whole value counts
    assert k["files"]["by_phone"] == {p1: 0, p2: 1, p3: 0}  # by file name, never by folder
    assert out["total"] == sum(x["total"] for x in out["kinds"]) == 8
    for g in out["groups"]:
        assert g["total"] == k[g["kind"]]["total"]
    assert sorted(p["label"] for p in out["phones"]) == ["C1", "C2", "C3"]  # in capture order (one instant here)


def test_every_kind_pages_to_its_total(world):
    out = _search(world, "pell")
    with world["engine"].connect() as c:
        for g in out["groups"]:
            seen, cursor = [], None
            while True:
                page = P.kind_page(c, world["case"], "pell", g["kind"], cursor=cursor, limit=1)
                assert page["total"] == g["total"]
                seen += page["items"]
                cursor = page["next_cursor"]
                if not cursor:
                    break
            assert len(seen) == g["total"]


def test_a_hidden_typed_word_is_found_on_its_whole_value_and_shown_masked(world):
    g = {x["kind"]: x for x in _search(world, "pell")["groups"]}
    hit = g["typed_words"]["items"][0]
    assert hit["masked"] is True and hit["snippet"]["match"] == "••••"
    assert "Pell" not in str(hit["snippet"])
    assert hit["field_path"] == "Word" and hit["record_uid"] == world["recs"]["word"]
    assert _kinds(_search(world, "pellucid"))["typed_words"]["total"] == 1
    assert _kinds(_search(world, "pellu"))["typed_words"]["total"] == 0  # never a part of a hidden value


def test_deleted_items_are_searched_and_marked(world):
    out = _search(world, "checks are in the drawer")
    hit = {x["kind"]: x for x in out["groups"]}["messages"]["items"][0]
    assert hit["deleted"] is True and hit["thread_key"]
    assert _kinds(out)["messages"]["deleted"] == 1
    assert out["next_steps"][0]["id"] == "deleted"


def test_a_number_finds_the_contact_saved_with_punctuation(world):
    out = _search(world, "+1 202 555 0177")
    assert _kinds(out)["contacts"]["total"] == 1
    hit = {x["kind"]: x for x in out["groups"]}["contacts"]["items"][0]
    assert hit["snippet"]["match"] == "202) 555-0177"


def test_the_period_limits_dated_records_and_messages_and_keeps_undated_ones(world):
    k = _kinds(_search(world, "pell", start="2024-03-01", end="2024-03-31"))
    p1 = world["p"][0]
    assert k["messages"]["by_phone"][p1] == 2  # June's message is outside
    assert k["web"]["total"] == 1  # the July search is outside; the March page inside
    assert k["contacts"]["total"] == 1  # a contact has no time: kept, as Conversations keeps undated messages


def test_the_phone_scope_limits_every_kind(world):
    p1, p2, _ = world["p"]
    out = _search(world, "pell", phones=[p2])
    assert [p["extraction_id"] for p in out["phones"]] == [p2]
    assert out["total"] == 2 and all(set(k["by_phone"]) == {p2} for k in out["kinds"])
    with pytest.raises(P.PhoneSearchError):
        _search(world, "pell", phones=[str(uuid.uuid4())])


def test_the_person_saved_differently_on_each_phone_is_noted_with_their_own_phone(world):
    out = _search(world, "pell")
    s = out["saved_differently"]
    assert len(s) == 1
    order = [p["label"] for p in out["phones"]]  # the case's phone order (capture time, then id)
    saved = {"C1": "Dorian (office)", "C2": "D Pell"}
    assert [(n["phone"], n["names"]) for n in s[0]["names"]] == [(p, [saved[p]]) for p in order if p in saved]
    assert [o["phone"] for o in s[0]["own_phones"]] == ["C3"]
    assert s[0]["sentence"] == ". ".join("%s: \u201c%s\u201d" % (p, saved[p]) for p in order if p in saved) + \
        ". C3 is this person's own phone."
    step = out["next_steps"][0]
    assert step["id"] == "person" and step["open"]["params"]["people"] == PELL
    assert step["title"] == "Open D Pell across every phone"


def test_next_steps_are_ranked_and_built_from_the_result(world):
    out = _search(world, "pell")
    ids_ = [s["id"] for s in out["next_steps"]]
    assert ids_[:2] == ["person", "deleted"]
    assert [s["rank"] for s in out["next_steps"]] == list(range(1, len(ids_) + 1))
    empty = next(s for s in out["next_steps"] if s["id"] == "empty_phones")
    assert empty["open"]["params"] == {"phones": world["p"][2], "from": "2024-03-11", "to": "2024-06-01"}
    assert "11 Mar 2024 to 1 Jun 2024" in empty["why"]
    nothing = _search(world, "no such words anywhere")
    assert nothing["total"] == 0 and [s["id"] for s in nothing["next_steps"]] == []


def test_a_message_hit_opens_in_its_thread_with_the_hit_marked(world):
    ev = world["ev1"][1]
    with world["engine"].connect() as c:
        ctx = P.hit_context(c, world["case"], ev["event_uid"])
    assert ctx["deleted"] is True and ctx["thread_key"] == ev["thread_key"]
    assert [i["event_uid"] for i in ctx["items"]][:1] == [world["ev1"][0]["event_uid"]]
    assert ev["event_uid"] in [i["event_uid"] for i in ctx["items"]]
    with world["engine"].connect() as c, pytest.raises(LookupError):
        P.hit_context(c, world["case"], str(uuid.uuid4()))


def test_the_hits_day_is_its_day_in_the_zone_the_times_are_shown_in(world):
    """"That day, all phones" opens the hit's day as the screen shows it, not the UTC date of the instant."""
    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo
    ev = world["ev1"][1]  # 12 Mar 2024, 10:00
    with world["engine"].connect() as c:
        ctx = P.hit_context(c, world["case"], ev["event_uid"])
    day = ctx["day"]
    hit = next(i for i in ctx["items"] if i["event_uid"] == ev["event_uid"])["time"]["instant"]
    at = datetime.fromisoformat(hit.replace("Z", "+00:00"))
    assert day["date"] == at.astimezone(ZoneInfo(day["zone"])).date().isoformat()
    start = datetime.fromisoformat(day["from"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(day["to"].replace("Z", "+00:00"))
    assert start <= at <= end and timedelta(hours=22) < end - start < timedelta(hours=26)
    assert start.astimezone(ZoneInfo(day["zone"])).time().isoformat() == "00:00:00"
    assert start.tzinfo == timezone.utc
