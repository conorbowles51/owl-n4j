"""03 section 11 (S-1 to S-5, S-10): Loupe-wide search over synthetic phones and synthetic documents.

Invented data only: 555 numbers and made-up names and text.
"""
from __future__ import annotations

import hashlib
import uuid

import pytest
from sqlalchemy import text

from services.phone import streams
from services.phone.filters import StreamFilter
from services.search import document_folds
from services.search import search as S
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, ensure_identity, phone

pytestmark = needs_template
OWNER, ANA, BEN = "phone:+12025550100", "phone:+12025550143", "phone:+12025550188"
SCRIPT_NAME = "\U0001D4D9\U0001D4F8\U0001D4FC\U0001D4EE \U0001D4DB\U0001D4F8\U0001D4F9\U0001D4EE\U0001D503"  # 𝓙𝓸𝓼𝓮 𝓛𝓸𝓹𝓮𝔃


def msg(instant, sender, recips, body="hello", **kw):
    parties = [(sender, "sender", sender == OWNER, None, None)] + [(r, "recipient", r == OWNER, None, None)
                                                                    for r in recips]
    return dict(kind="message", instant=instant, body=body, parties=parties,
                direction="outgoing" if sender == OWNER else "incoming", **kw)


def _doc(c, case, name, content, locations=None):
    fid = uuid.uuid4()
    c.execute(text(
        "INSERT INTO evidence_files (id, case_id, original_filename, stored_path, size, sha256, status, created_at, "
        "updated_at) VALUES (:i, :c, :n, :p, 1, '00', 'processed', now(), now())"),
        {"i": fid, "c": case, "n": name, "p": "x/%s" % name})
    c.execute(text(
        "INSERT INTO evidence_document_texts (evidence_file_id, content, content_sha256, character_count, "
        "source_locations, processing_manifest, extracted_at) VALUES (:i, :b, :h, :n, CAST(:l AS jsonb), "
        "CAST('{}' AS jsonb), now())"),
        {"i": fid, "b": content, "h": hashlib.sha256(content.encode()).hexdigest(), "n": len(content),
         "l": __import__("json").dumps(locations or [])})
    return fid


@pytest.fixture
def world():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, other = make_case(c), make_case(c)
            ext, evs = phone(c, case, contacts={ANA: SCRIPT_NAME}, events=[
                msg(at(2023, 3, 14, 10), ANA, [OWNER], body="Meet %s at the dock" % SCRIPT_NAME, thread="t"),
                msg(at(2023, 3, 14, 11), OWNER, [ANA], body="ok jose, see you", thread="t"),
                msg(at(2023, 3, 15, 9), BEN, [OWNER], body="the code is a/b+c 2025550143", thread="u"),
                dict(kind="call", instant=at(2023, 3, 16), body=None, thread=None,
                     parties=[(OWNER, "caller", True, None, None), (BEN, "callee", False, None, None)])])
            c.execute(text("UPDATE phone_identities SET value_display = '+1 (202) 555-0143' WHERE case_id = :c AND "
                           "identity_key = :k"), {"c": case, "k": ANA})
            ensure_identity(c, case, "phone:+12025550199")
            doc = _doc(c, case, "synthetic-ledger.pdf",
                       "Page one.\nWire from ﬁrm to José Lopez, Straße 5.\nPage two: nothing.",
                       [{"page_number": 1, "start_char": 0, "end_char": 10},
                        {"page_number": 2, "start_char": 10, "end_char": 200}])
            _doc(c, other, "other-case.pdf", "Jose Lopez in another case")
        yield {"engine": engine, "case": case, "other": other, "ext": str(ext), "evs": evs, "doc": str(doc)}


def _search(w, q, **kw):
    with w["engine"].connect() as c:
        return {g["group"]: g for g in S.search(c, w["case"], q, **kw)["groups"]}


def test_s1_a_name_in_mathematical_script_is_found_by_plain_letters(world):
    g = _search(world, "jose lopez")
    assert g["messages"]["total"] == 1  # the message body written in script letters
    assert g["messages"]["items"][0]["snippet"]["match"] == SCRIPT_NAME
    people = [h for h in g["people"]["items"] if h.get("identity_key") == ANA]
    assert people and people[0]["title"] == SCRIPT_NAME  # the contact name on the phone
    assert g["documents"]["total"] == 0  # the document is not folded yet: it matches as typed only
    assert "still being prepared" in g["documents"]["note"]


def test_s2_exact_characters_turns_folding_off(world):
    assert _search(world, "jose lopez", exact=True)["messages"]["total"] == 0
    assert _search(world, "ok jose", exact=True)["messages"]["total"] == 1


def test_s3_digits_find_an_identity_stored_with_punctuation(world):
    g = _search(world, "2025550143")
    keys = [h["identity_key"] for h in g["people"]["items"] if h.get("identity_key")]
    assert keys == [ANA]
    assert g["messages"]["total"] == 1  # and the message that holds the digits


def test_s4_a_group_total_equals_its_pages_and_the_conversations_total(world):
    with world["engine"].connect() as c:
        first = S.search(c, world["case"], "o")  # short: identifiers only
        assert first["short"] == S.SHORT and all(g["total"] == 0 for g in first["groups"] if g["group"] != "people")
        full = {g["group"]: g for g in S.search(c, world["case"], "see")["groups"]}
        conv = streams.shown_count(c, StreamFilter.model_validate(
            {"case_id": str(world["case"]), "kinds": S.COMM_KINDS["messages"], "text": {"query": "see"}}))
        assert full["messages"]["total"] == conv == 1
        seen, cursor = [], None
        while True:
            page = S.group_page(c, world["case"], "e", "people", cursor=cursor, limit=1)
            seen += page["items"]
            cursor = page["next_cursor"]
            if cursor is None:
                break
        total = S.group_page(c, world["case"], "e", "people", limit=200)["total"]
        assert len(seen) == total


def test_s5_document_highlights_fall_on_the_original_characters_after_folding(world):
    out = document_folds.backfill(world["engine"])
    assert out["folded"] == 2 and out["remaining"] == 0
    assert set(out["by_case"]) == {str(world["case"]), str(world["other"])}
    g = _search(world, "firm to jose lopez strasse")
    assert g["documents"]["total"] == 1 and "note" not in g["documents"]
    hit = g["documents"]["items"][0]
    assert hit["snippet"]["match"] == "ﬁrm to José Lopez, Straße"
    assert hit["page"] == 2 and hit["evidence_file_id"] == world["doc"]
    assert document_folds.backfill(world["engine"])["folded"] == 0  # resumable: nothing left to do
    with world["engine"].begin() as c:  # a changed text is folded again
        c.execute(text("UPDATE evidence_document_texts SET content = 'renamed firm', content_sha256 = 'changed' "
                       "WHERE evidence_file_id = :i"), {"i": world["doc"]})
    assert document_folds.backfill(world["engine"])["folded"] == 1
    assert _search(world, "renamed firm")["documents"]["total"] == 1


def test_s10_slashes_and_plus_signs_are_searched_as_typed(world):
    g = _search(world, "a/b+c")
    assert g["messages"]["total"] == 1
    assert g["messages"]["items"][0]["snippet"]["match"] == "a/b+c"


def test_another_case_is_never_searched(world):
    document_folds.backfill(world["engine"])
    with world["engine"].connect() as c:
        g = {x["group"]: x for x in S.search(c, world["other"], "jose lopez")["groups"]}
    assert g["documents"]["total"] == 1 and g["messages"]["total"] == 0 and g["people"]["total"] == 0
    assert _search(world, "another case")["documents"]["total"] == 0


def test_media_is_said_not_to_be_searched(world):
    with world["engine"].connect() as c:
        out = S.search(c, world["case"], "dock")
    assert [n["group"] for n in out["not_searched"]] == ["media"]


STYLES = [c for c in __import__("json").load(open(__import__("os").path.join(
    __import__("os").path.dirname(__file__), "fixtures", "fold_cases.json"), encoding="utf-8"))["cases"]
    if c["name"] in ("mathematical bold script", "fullwidth", "circled", "negative squared", "small capitals")]


@pytest.mark.parametrize("case", STYLES, ids=[c["name"] for c in STYLES])
def test_a8_each_decorative_style_is_found_by_plain_typing_in_messages_and_names(case):
    """A8: a display name in each style is found by typing its plain letters, in a message and in the contact name
    that names the identity; Exact characters does not fold it."""
    with fresh_engine() as engine:
        with engine.begin() as c:
            case_id = make_case(c)
            phone(c, case_id, contacts={ANA: case["input"]},
                  events=[msg(at(2023, 3, 14, 10), ANA, [OWNER], body="from %s today" % case["input"], thread="t")])
        with engine.connect() as c:
            g = {x["group"]: x for x in S.search(c, case_id, case["fold"])["groups"]}
            assert g["messages"]["total"] == 1
            assert g["messages"]["items"][0]["snippet"]["match"] == case["input"]
            assert [h["identity_key"] for h in g["people"]["items"] if h.get("identity_key")] == [ANA]
            exact = {x["group"]: x for x in S.search(c, case_id, case["fold"], exact=True)["groups"]}
            assert exact["messages"]["total"] == 0


def test_search_is_not_presented_as_whole_while_a_phone_is_still_being_read(world):
    """Review of item E: a phone still being read makes every search total incomplete, in the same words as
    Conversations; files with no text read are said not to be searched, with their count."""
    with world["engine"].begin() as c:
        phone(c, world["case"], label="C9", interpreted=False, events=[msg(at(2023, 4, 1), ANA, [OWNER], body="see")])
        c.execute(text(
            "INSERT INTO evidence_files (id, case_id, original_filename, stored_path, size, sha256, status, created_at, "
            "updated_at) VALUES (:i, :c, 'waiting.pdf', 'x/waiting.pdf', 1, '01', 'unprocessed', now(), now())"),
            {"i": uuid.uuid4(), "c": world["case"]})
    with world["engine"].connect() as c:
        out = S.search(c, world["case"], "see")
        page = S.group_page(c, world["case"], "see", "messages")
        other = S.search(c, world["other"], "jose lopez")
    assert out["complete"] is False and out["limits"][0]["kind"] == "phone_incomplete"
    assert "still being read" in out["limits"][0]["message"]
    assert page["complete"] is False and page["limits"] == out["limits"]
    unread = [n for n in out["not_searched"] if n["group"] == "unread_files"]
    assert unread == [{"group": "unread_files", "reason": "1 file has no text read yet (still waiting, failed, or not "
                                                          "a document) and is not searched."}]
    assert other["complete"] is True and other["limits"] == []  # another case's phone does not count
