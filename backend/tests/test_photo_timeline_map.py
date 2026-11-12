"""Photos reach the Timeline and the map from their own data; any file can be added by a person, caption optional."""
import hashlib
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.timeline_entry import TimelineEntry
from postgres.models.timeline_event_file import TimelineEventFile
from postgres.models.user import User
from services import photo_data as pd
from services.timeline_entries import TimelineAddition, list_entries, preview_addition, save_addition

DATED = {"width": 4, "height": 3, "source": "photo_data", "confirmed_by": None,
         "date_taken": {"local": "2024-05-01T12:30:15", "offset": None, "field": "DateTimeOriginal"},
         "gps": {"latitude": 51.5, "longitude": -0.125, "altitude_m": 12.0}, "camera": {"make": "Apple"}}
DATE_ONLY = {"width": 4, "height": 3, "date_taken": {"local": "2024-05-02T09:00:00", "offset": "+01:00"}}
NEITHER = {"width": 4, "height": 3}


@pytest.fixture
def world():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[User.__table__, Case.__table__, EvidenceFolder.__table__,
                                             EvidenceFile.__table__, TimelineEntry.__table__, TimelineEventFile.__table__])
    with Session(engine, expire_on_commit=False) as db:
        user = User(id=uuid.uuid4(), email="a@example.com", name="A", password_hash="x", global_role="user")
        case = Case(id=uuid.uuid4(), title="Case", created_by_user_id=user.id, owner_user_id=user.id)
        db.add_all([user, case])
        db.commit()
        yield db, case.id
    engine.dispose()


def _file(db, case_id, name, photo=None, **extra):
    meta = dict(extra)
    if photo is not None:
        meta["photo_data"] = photo
    row = EvidenceFile(id=uuid.uuid4(), case_id=case_id, original_filename=name, stored_path="/x/" + name, size=1,
                       sha256=hashlib.sha256(name.encode()).hexdigest(), status="processed", metadata_=meta)
    db.add(row)
    db.commit()
    return row


def test_dated_photos_are_on_the_timeline_labelled_and_undated_ones_are_not(world):
    db, case = world
    dated, date_only, neither = (_file(db, case, "a.jpg", DATED), _file(db, case, "b.jpg", DATE_ONLY),
                                 _file(db, case, "c.jpg", NEITHER))
    _file(db, case, "d.pdf")
    events = {e["evidence_file_id"]: e for e in pd.photo_events(db, case)}
    assert set(events) == {str(dated.id), str(date_only.id)}
    first = events[str(dated.id)]
    assert (first["name"], first["date"], first["time"]) == ("Photo taken", "2024-05-01", "12:30")
    assert "not checked by a person" in first["source"]["date_basis"] and "Time zone not recorded" in first["source"]["date_basis"]
    assert first["thumbnail_url"].startswith(f"/api/photos/{dated.id}/thumbnail")
    assert "UTC offset +01:00" in events[str(date_only.id)]["source"]["date_basis"]


def test_only_gps_photos_are_map_pins_linked_to_the_file(world):
    db, case = world
    dated, _ = _file(db, case, "a.jpg", DATED), _file(db, case, "b.jpg", DATE_ONLY)
    pins = pd.photo_places(db, case)
    assert [p["evidence_file_id"] for p in pins] == [str(dated.id)]
    assert (pins[0]["latitude"], pins[0]["longitude"]) == (51.5, -0.125)
    assert "not checked by a person" in pins[0]["location_formatted"]


def test_detail_says_which_values_were_absent(world):
    db, case = world
    detail = pd.photo_detail(_file(db, case, "b.jpg", DATE_ONLY))
    assert detail["absent"] == ["place", "camera"] and detail["read"] is True
    unread = pd.photo_detail(_file(db, case, "z.jpg"))
    assert unread["read"] is False and unread["absent"] == []


def test_person_adds_photos_with_no_description_and_a_changed_date_keeps_the_original(world):
    db, case = world
    a, b, c = _file(db, case, "a.jpg", DATED), _file(db, case, "b.jpg", DATE_ONLY), _file(db, case, "c.jpg", NEITHER)
    request = TimelineAddition(source_kind="evidence_file", source_ids=[a.id, b.id, c.id])
    preview = preview_addition(db, case_id=case, request=request)
    assert (preview["ready"], preview["undated"]) == (2, 1)  # the photo with no date is told, not invented
    request.expected_revision = preview["revision"]
    assert save_addition(db, case_id=case, request=request, actor="a@example.com")["added"] == 2
    # a virtual entry no longer repeats a photo that was added by hand
    assert pd.photo_events(db, case) == []
    # changing the date of one photo keeps the photo's own value visible
    change = TimelineAddition(source_kind="evidence_file", source_ids=[c.id], event_date="2024-06-01", event_time="08:15",
                              place="Pier")
    change.expected_revision = preview_addition(db, case_id=case, request=change)["revision"]
    save_addition(db, case_id=case, request=change, actor="a@example.com")
    events = {e["source"]["id"]: e for e in list_entries(db, case_id=case)}
    moved = events[str(c.id)]
    assert (moved["date"], moved["time"]) == ("2024-06-01", "08:15") and "Place: Pier" in moved["summary"]
    assert "holds no date taken" in moved["source"]["date_basis"]
    again = TimelineAddition(source_kind="evidence_file", source_ids=[a.id], event_date="2024-05-09")
    again.expected_revision = preview_addition(db, case_id=case, request=again)["revision"]
    save_addition(db, case_id=case, request=again, actor="a@example.com")  # already added: nothing changes
    kept = {e["source"]["id"]: e for e in list_entries(db, case_id=case)}[str(a.id)]
    assert kept["date"] == "2024-05-01"
    assert kept["photo_original"]["date_taken"]["local"] == "2024-05-01T12:30:15"


def test_changed_date_shows_the_original_alongside(world):
    db, case = world
    a = _file(db, case, "a.jpg", DATED)
    event = pd.photo_event(a, event_date="2024-07-07")
    assert event["date"] == "2024-07-07" and "2024-05-01 12:30" in event["source"]["date_basis"]
    assert event["photo_original"]["date_taken"]["local"] == "2024-05-01T12:30:15"


def test_caption_is_optional_one_line_and_removable(world):
    db, case = world
    a = _file(db, case, "a.jpg", DATED)
    assert pd.set_caption(a, "  The  pier\nat dawn ") == "The pier at dawn"
    assert pd.photo_detail(a)["caption"] == "The pier at dawn"
    assert pd.set_caption(a, "") is None and pd.photo_detail(a)["caption"] is None
    with pytest.raises(ValueError):
        pd.set_caption(a, "x" * 201)


def test_deleted_file_is_not_a_timeline_event_or_pin(world):
    db, case = world
    from datetime import datetime, timezone
    a = _file(db, case, "a.jpg", DATED)
    a.deleted_at = datetime.now(timezone.utc)
    db.commit()
    assert pd.photo_events(db, case) == [] and pd.photo_places(db, case) == []


def test_backfill_stores_photo_data_only_and_is_a_dry_run_by_default(world, tmp_path):
    from PIL import Image

    from scripts.backfill_photo_data import backfill

    db, case = world
    exif = Image.Exif()
    exif.get_ifd(0x8769)[0x9003] = "2024:05:01 12:30:15"
    path = tmp_path / "a.jpg"
    Image.new("RGB", (5, 5)).save(path, format="JPEG", exif=exif)
    file = _file(db, case, "a.jpg", None, ocr="kept")
    file.stored_path = str(path)
    db.commit()
    resolve = lambda stored: tmp_path / stored.rsplit("/", 1)[-1]

    dry = backfill(db, apply=False, resolve_path=resolve)[str(case)]
    assert (dry["would_store"], dry["stored"], dry["before"]) == (1, 0, {})
    db.refresh(file)
    assert "photo_data" not in file.metadata_

    done = backfill(db, apply=True, resolve_path=resolve)[str(case)]
    assert done["stored"] == 1 and done["after"]["date_taken"] == 1
    db.refresh(file)
    assert file.metadata_["photo_data"]["read_by"] == "backfill" and file.metadata_["ocr"] == "kept"
    again = backfill(db, apply=True, resolve_path=resolve)[str(case)]
    assert again["stored"] == 0  # a file with a record is left alone
