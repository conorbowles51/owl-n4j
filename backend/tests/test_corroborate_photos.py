"""Corroborate on a photo (Media page tile): the file becomes the phone records it belongs to, the place in its
metadata and the messages that carried it, each labelled with the file's name; a file with neither is refused by
name, never dropped."""
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services import case_selections
from services.corroborate import photos
from services.phone import ids
from services.relations import runs

CASE = "11111111-2222-3333-4444-555555555555"
EXT = "22222222-3333-4444-5555-666666666666"
PHOTO = "33333333-4444-5555-6666-777777777777"
BARE = "44444444-5555-6666-7777-888888888888"
UNDATED = "66666666-7777-8888-9999-aaaaaaaaaaaa"
MESSAGE = "55555555-6666-7777-8888-999999999999"
PLACE = str(ids.record_uid(EXT, 0, 41))


class _Db:
    """Answers each of the four reads by its table, for the files of the case."""

    def __init__(self, placed=True):
        self.placed = placed

    def execute(self, statement, params=None):
        sql = str(statement)
        if "phone_file_references" in sql:
            return iter([(uuid.UUID(PHOTO), uuid.UUID(EXT), 0, 41)] if PHOTO in params["u"] else [])
        if "pol_place_observation" in sql:
            return iter([(uuid.UUID(PLACE),)] if self.placed and PLACE in params["r"] else [])
        if "pv_attachment_link" in sql:
            at = datetime(2024, 3, 16, 14, 50, tzinfo=timezone.utc)
            rows = [(uuid.UUID(PHOTO), uuid.UUID(MESSAGE), at), (uuid.UUID(PHOTO), uuid.UUID(MESSAGE), at),
                    (uuid.UUID(UNDATED), None, None)]  # two links under one message: it is read once
            return iter([r for r in rows if str(r[0]) in params["u"]])
        if "FROM pv_file" in sql:
            files = {PHOTO: "DCIM/Camera/IMG_0412.jpg", BARE: "Pictures\\saved.png", UNDATED: "chats/voice.ogg"}
            return iter([(uuid.UUID(u), files[u]) for u in params["u"] if u in files])
        raise AssertionError(sql)


def test_a_photo_becomes_its_metadata_place_and_the_messages_that_carried_it():
    other = {"type": "financial_transaction", "id": "t1"}
    out = photos.expand(_Db(), CASE, [other, {"type": "media_file", "id": PHOTO}])
    assert out == [other,
                   {"type": "phone_record", "id": PLACE, "label": "IMG_0412.jpg: place in its metadata"},
                   {"type": "phone_record", "id": MESSAGE, "label": "IMG_0412.jpg: message that carried it"}]


def test_a_tagged_place_not_on_the_map_is_not_offered_and_the_message_still_is():
    out = photos.expand(_Db(placed=False), CASE, [{"type": "media_file", "id": PHOTO, "label": "IMG_0412.jpg"}])
    assert [m["id"] for m in out] == [MESSAGE]


def test_a_file_with_no_place_and_no_message_is_refused_by_name():
    with pytest.raises(case_selections.SelectionError, match="saved.png names no place"):
        photos.expand(_Db(), CASE, [{"type": "media_file", "id": BARE}])


def test_a_file_only_undated_records_refer_to_is_refused_saying_so():
    with pytest.raises(case_selections.SelectionError, match="voice.ogg names no place .* the records that refer to it have no time"):
        photos.expand(_Db(), CASE, [{"type": "media_file", "id": UNDATED}])


def test_a_file_not_in_the_case_is_refused():
    with pytest.raises(case_selections.SelectionError, match="not on a phone in this case"):
        photos.expand(_Db(), CASE, [{"type": "media_file", "id": str(uuid.uuid4()), "label": "elsewhere.jpg"}])


def test_the_run_and_the_preview_read_a_photo_through_normalise():
    out = runs.normalise(_Db(), CASE, [{"type": "media_file", "id": PHOTO}])
    assert {m["type"] for m in out} == {"phone_record"} and len(out) == 2
    # the members the group keeps are all of a type a relation query holds
    assert case_selections.clean_members("relation_query", out)


def test_group_by_reads_a_photo_as_its_records(monkeypatch):
    from routers import corroborate
    from routers.case_access import require_case_view
    from services.corroborate import store
    seen = []

    class Store:
        def __init__(self, db, case_id):
            pass

        def selection_points(self, members):
            seen.extend(members)
            return [], []

        def people(self):
            return []

        def zone(self):
            return "UTC"

    monkeypatch.setattr(store, "CaseStore", Store)
    app = FastAPI()
    app.include_router(corroborate.router)
    app.dependency_overrides[require_case_view] = lambda: None
    app.dependency_overrides[corroborate.get_db] = lambda: _Db()
    TestClient(app).post(f"/api/cases/{CASE}/corroborate/group",
                         json={"members": [{"type": "media_file", "id": PHOTO}], "by": "day"})
    assert [m["type"] for m in seen] == ["phone_record", "phone_record"]
