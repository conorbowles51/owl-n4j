"""05 section 11 (approach 8, exact tier; unit 05-S13): media spread across phones, acceptance tests 1 to 3 of 11.8,
the common-file flag of 11.5, SHA-256 disagreement, case isolation and the routes. Invented values only: the
hashes are made-up hex strings, the paths and numbers are synthetic. Needs the PostgreSQL template."""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

pytestmark = needs_template

OWNER, ANA = "phone:+12025550100", "phone:+12025550143"
SENT = "a" * 32         # sent by X, received by Y (11.8 test 1)
SYSTEM = "b" * 32       # a system file on every phone (11.8 test 2)
CAMERA = "c" * 32       # camera original on X, later received on Y (11.8 test 3)
WALL_EARLY = "d" * 32   # capture time with no offset, two days before the message
WALL_CLOSE = "e" * 32   # capture time with no offset, two hours before the message
STICKER = "f" * 32      # on three of the four phones: common file
SHA = "0123456789abcdef" * 2  # equal MD5, different SHA-256


def msg(instant, outgoing):
    parties = [(OWNER, "sender", True, None, None), (ANA, "recipient", False, None, None)] if outgoing else \
        [(ANA, "sender", False, None, None), (OWNER, "recipient", True, None, None)]
    return dict(kind="message", instant=instant, body="synthetic", parties=parties,
                direction="outgoing" if outgoing else "incoming")


def body(path, items=()):
    return ["file", {"path": path, "id": str(uuid.uuid4())}, None,
            [["metadata", {"section": "MetaData"}, None, [["item", {"name": k}, v, None] for k, v in items]]]
            if items else None]


def add_file(c, ext, ordinal, md5, path, *, record=None, items=(), sha256=None, stamps=()):
    uid = uuid.uuid4()
    c.execute(text(
        "INSERT INTO phone_files (extraction_id, document_index, ordinal, file_uid, local_path, declared_md5, "
        "declared_sha256, tags, outcome, body) VALUES (:e, 0, :o, :f, :lp, :m, :s, 'Image', 'no_hash', "
        "CAST(:b AS jsonb))"),
        {"e": ext, "o": ordinal, "f": uid, "lp": "files/Image/%s" % path.rsplit("/", 1)[-1], "m": md5, "s": sha256,
         "b": json.dumps(body(path, items))})
    if record is not None:
        c.execute(text(
            "INSERT INTO phone_file_references (extraction_id, document_index, record_ordinal, body_path, mechanism, "
            "reference_text, file_document_index, file_ordinal, resolution, ambiguous) VALUES (:e, 0, :r, :bp, "
            "'extracted_path_value', :p, 0, :o, 'container_entry', false)"), {"e": ext, "r": record, "p": path,
                                                                             "bp": "f%d" % ordinal, "o": ordinal})
    for field, instant, wall, original in stamps:
        c.execute(text(
            "INSERT INTO phone_timestamps (extraction_id, document_index, owner_kind, owner_ordinal, body_path, "
            "field_name, value_type, original_text, instant, local_wall_time, offset_state, parse_rule) VALUES "
            "(:e, 0, 'file', :o, :bp, :fn, 'metadata_item', :ot, :i, :w, :os, 'synthetic')"),
            {"e": ext, "o": ordinal, "bp": "3.0.%d" % len(field), "fn": field, "ot": original, "i": instant,
             "w": wall, "os": "explicit" if instant else "absent"})
    return str(uid)


CAM_ITEMS = (("EXIFCameraMaker", "SyntheticMaker"), ("EXIFCameraModel", "Model 0"),
             ("MetaDataLatitudeAndLongitude", "10.5, -20.25"))


@pytest.fixture
def world():
    from datetime import datetime
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, other = make_case(c), make_case(c)
            x, _ = phone(c, case, label="C1", events=[msg(at(2023, 3, 14, 12), True), msg(at(2023, 3, 20, 9), True),
                                                      msg(at(2023, 3, 21, 9), True)])
            y, _ = phone(c, case, label="C2", events=[msg(at(2023, 3, 14, 12, 5), False),
                                                      msg(at(2023, 3, 16, 8), False), msg(at(2023, 3, 20, 9, 1), False),
                                                      msg(at(2023, 3, 21, 9, 1), False), msg(at(2023, 3, 22), False)])
            z, _ = phone(c, case, label="C3", events=[msg(at(2023, 3, 22, 1), False)])
            w, _ = phone(c, case, label="C4", events=[])
            ids = {}
            ids["sent_x"] = add_file(c, x, 9000, SENT, "/data/media/synthetic-sent.jpg", record=0)
            ids["sent_y"] = add_file(c, y, 9000, SENT.upper(), "/data/media/synthetic-sent.jpg", record=0)
            for ext in (x, y, z, w):
                add_file(c, ext, 9001, SYSTEM, "/system/fonts/synthetic.ttf")
            ids["cam_x"] = add_file(c, x, 9002, CAMERA, "/sdcard/DCIM/Camera/synthetic-cam.jpg", items=CAM_ITEMS,
                                    stamps=[("EXIFCaptureTime", at(2023, 3, 15, 10), None, "synthetic"),
                                            ("ModifyTime", at(2023, 3, 15, 10, 1), None, "synthetic")])
            ids["cam_y"] = add_file(c, y, 9002, CAMERA, "/data/media/synthetic-cam.jpg", record=1)
            add_file(c, x, 9003, WALL_EARLY, "/sdcard/DCIM/Camera/synthetic-early.jpg", items=CAM_ITEMS,
                     stamps=[("EXIFCaptureTime", None, datetime(2023, 3, 18, 9), "2023:03:18 09:00:00")])
            add_file(c, y, 9003, WALL_EARLY, "/data/media/synthetic-early.jpg", record=2)
            add_file(c, x, 9004, WALL_CLOSE, "/sdcard/DCIM/Camera/synthetic-close.jpg", items=CAM_ITEMS,
                     stamps=[("EXIFCaptureTime", None, datetime(2023, 3, 21, 7), "2023:03:21 07:00:00")])
            add_file(c, y, 9004, WALL_CLOSE, "/data/media/synthetic-close.jpg", record=3)
            add_file(c, x, 9005, STICKER, "/data/WhatsApp/Media/synthetic-sticker.webp", record=0)
            add_file(c, y, 9005, STICKER, "/data/WhatsApp/Media/synthetic-sticker.webp", record=4)
            add_file(c, z, 9005, STICKER, "/data/WhatsApp/Media/synthetic-sticker.webp", record=0)
            add_file(c, x, 9006, SHA, "/sdcard/DCIM/synthetic-sha.jpg", sha256="1" * 64)
            add_file(c, y, 9006, SHA, "/sdcard/DCIM/synthetic-sha.jpg", sha256="2" * 64)
            # another case holding a copy of the sent file: never seen from the first case, and alone in its own
            o, _ = phone(c, other, label="C9", events=[msg(at(2023, 3, 14, 13), False)])
            add_file(c, o, 9000, SENT, "/data/media/synthetic-sent.jpg", record=0)
        yield {"engine": engine, "case": case, "other": other, "x": str(x), "y": str(y), "z": str(z),
               "w": str(w), "ids": ids}


def _all(world, case=None, **f):
    from services.phone import media_spread
    with world["engine"].connect() as c:
        return media_spread.window(c, case or world["case"], f, 0, 100)


def _group(win, md5):
    return next((g for g in win["items"] if g["md5"] == md5), None)


def test_11_8_1_sent_on_one_phone_received_on_the_other_is_a_spread_item_in_order(world):
    win = _all(world)
    g = _group(win, SENT)
    assert g is not None and g["phone_count"] == 2 and g["copy_count"] == 2 and not g["common_file"]
    first, second = g["phones"]
    assert (first["extraction_id"], first["position"], first["roles"]) == (world["x"], 1, ["sent"])
    assert (second["extraction_id"], second["position"], second["roles"]) == (world["y"], 2, ["received"])
    assert first["earliest"]["source"] == "message_time" and first["earliest"]["instant"] == "2023-03-14T12:00:00Z"
    assert second["earliest"]["instant"] == "2023-03-14T12:05:00Z"
    copy = first["copies"][0]
    assert copy["file_uid"] == world["ids"]["sent_x"] and copy["messages"][0]["role"] == "sent"
    assert "+1 202-555-0143" in (copy["messages"][0]["line"] or "")
    assert g["clock_offset_unknown"] is True and g["clock_words"]


def test_11_8_2_a_system_file_on_every_phone_is_not_in_the_population(world):
    from services.phone import media_spread
    win = _all(world)
    assert _group(win, SYSTEM) is None
    with world["engine"].connect() as c:
        idx = media_spread.index(c, world["case"])
    assert idx["total_groups"] == win["total"] == len(win["items"]) == 6
    assert idx["case_phone_count"] == 4


def test_11_8_3_a_camera_copy_taken_before_every_message_is_the_camera_original_candidate(world):
    g = _group(_all(world), CAMERA)
    by_phone = {p["extraction_id"]: p for p in g["phones"]}
    cam = by_phone[world["x"]]["copies"][0]
    assert cam["file_uid"] == world["ids"]["cam_x"]
    assert cam["camera_original_candidate"] is True and cam["camera"] == {"make": "SyntheticMaker",
                                                                          "model": "Model 0"}
    assert cam["earliest"]["source"] == "exif_capture" and cam["earliest"]["field"] == "EXIFCaptureTime"
    assert cam["place"]["source"] == "photo EXIF" and "10.5, -20.25" in cam["place"]["words"]
    assert "in a camera or screenshot folder" in cam["included_because"]
    assert by_phone[world["y"]]["copies"][0]["camera_original_candidate"] is False
    assert g["phones"][0]["extraction_id"] == world["x"] and g["camera_original_candidates"] == 1


def test_a_capture_time_without_offset_decides_only_when_every_zone_agrees(world):
    win = _all(world)
    early = _group(win, WALL_EARLY)["phones"]
    close = _group(win, WALL_CLOSE)["phones"]
    e = next(p for p in early if p["extraction_id"] == world["x"])["copies"][0]
    k = next(p for p in close if p["extraction_id"] == world["x"])["copies"][0]
    assert e["camera_original_candidate"] is True and "any time zone" in e["camera_original_words"]
    assert k["camera_original_candidate"] is None and k["camera_original_words"].startswith("Cannot tell")
    # a time with no offset is shown as written and never placed: the phone has no order position from it
    x_close = next(p for p in close if p["extraction_id"] == world["x"])
    assert x_close["earliest"] is None and x_close["position"] is None
    assert k["times"][0]["full"].endswith("no offset in report")


def test_the_common_file_flag_is_set_when_the_hash_is_on_more_than_half_the_phones(world):
    win = _all(world)
    sticker = _group(win, STICKER)
    assert sticker["common_file"] and sticker["phones_with_hash"] == 3 and "3 of the case's 4" in sticker["common_words"]
    assert not _group(win, SENT)["common_file"]  # 2 of 4 is not more than half
    hidden = _all(world, common="hide")
    assert _group(hidden, STICKER) is None and hidden["total"] == 5
    assert [g["md5"] for g in _all(world, common="only")["items"]] == [STICKER]


def test_equal_md5_with_different_sha256_is_flagged(world):
    g = _group(_all(world), SHA)
    assert g["sha256_disagrees"] and g["sha256_words"]
    assert not _group(_all(world), SENT)["sha256_disagrees"]


def test_case_isolation_and_the_pair_and_phone_counts(world):
    from services.phone import media_spread
    g = _group(_all(world), SENT)
    assert {p["extraction_id"] for p in g["phones"]} == {world["x"], world["y"]}
    with world["engine"].connect() as c:
        other = media_spread.index(c, world["other"])
        idx = media_spread.index(c, world["case"])
    assert other["total_groups"] == 0 and other["by_pair"] == []
    assert _all(world, case=world["other"])["items"] == []
    pairs = {frozenset((p["a"]["extraction_id"], p["b"]["extraction_id"])): p["groups"] for p in idx["by_pair"]}
    assert pairs == {frozenset((world["x"], world["y"])): 6, frozenset((world["x"], world["z"])): 1,
                     frozenset((world["y"], world["z"])): 1}
    assert {p["extraction_id"]: p["groups"] for p in idx["by_phone"]} == {world["x"]: 6, world["y"]: 6,
                                                                          world["z"]: 1}
    only_z = _all(world, phones=[world["z"]])
    assert only_z["total"] == 1 and only_z["items"][0]["md5"] == STICKER


def test_paging_states_the_total(world):
    from services.phone import media_spread
    with world["engine"].connect() as c:
        page = media_spread.window(c, world["case"], {}, 4, 4)
    assert page["total"] == 6 and len(page["items"]) == 2 and page["offset"] == 4


def test_the_routes_need_view_permission_and_answer(world):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from postgres.models.enums import GlobalRole
    from postgres.models.user import User
    from postgres.session import get_db
    from routers.phones import router
    from routers.users import get_current_db_user
    engine = world["engine"]
    with engine.connect() as c:
        owner = c.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": world["case"]}).scalar()
        email = c.execute(text("SELECT email FROM users WHERE id = :u"), {"u": owner}).scalar()
    Session = sessionmaker(bind=engine)
    app = FastAPI()
    app.include_router(router)

    def db():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_current_db_user] = lambda: User(id=owner, email=email, name="synthetic",
                                                                 global_role=GlobalRole.user)
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get("/api/phones/media-spread/index", params={"case_id": str(world["case"])})
        assert r.status_code == 200, r.text
        assert r.json()["total_groups"] == 6
        r = client.get("/api/phones/media-spread/window", params={"case_id": str(world["case"]), "common": "hide",
                                                                  "phones": [world["z"]]})
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 0
        # the other case's owner is not this user: no access
        r = client.get("/api/phones/media-spread/index", params={"case_id": str(world["other"])})
        assert r.status_code in (403, 404), r.text


# ---- approach 2's clock offsets in the order (11.3 step 4) -----------------------------------------------------------

def _offsets(monkeypatch, items, current=True):
    from services.phone_analysis import across_badges as B
    run = {"id": "r", "finished_at": None, "current": current}
    monkeypatch.setattr(B, "clock_offsets", lambda conn, case_id: {"run": run, "items": items})


def _reading(offset_s, *, cls="device_stamped", pairs=12, family="whatsapp", too_few=False, phones=("C1", "C2")):
    return {"phones": list(phones), "family": family, "timestamp_class": cls, "offset_s": offset_s, "pairs": pairs,
            "spread_s": 4.0, "too_few": too_few, "words": "C2's clock reads %.0f seconds ahead of C1's (spread 4 s, "
                                                           "%d pairs)." % (offset_s, pairs)}


def test_no_run_says_so_and_stays_on_each_phones_own_clock(world):
    from services.phone import media_spread
    win = _all(world)
    assert win["clock_words"] == media_spread.CLOCK_NOT_RUN and "not been run" in win["clock_words"]
    g = _group(win, SENT)
    assert g["clock_offset_unknown"] is True and g["clock_offsets"] == [] and "C1 and C2" in g["clock_words"]


def test_an_established_offset_orders_the_phones_and_moves_no_time(world, monkeypatch):
    # C1 holds it 12:00, C2 12:05 by their own clocks; C2's clock is ten minutes ahead, so C2 held it first
    _offsets(monkeypatch, [_reading(600.0)])
    g = _group(_all(world), SENT)
    assert [p["phone_label"] for p in g["phones"]] == ["C2", "C1"] and [p["position"] for p in g["phones"]] == [1, 2]
    by = {p["phone_label"]: p for p in g["phones"]}
    assert by["C1"]["earliest"]["instant"] == "2023-03-14T12:00:00Z"      # the times shown are the phones' own
    assert by["C2"]["earliest"]["instant"] == "2023-03-14T12:05:00Z"
    assert g["clock_offset_unknown"] is False
    used = g["clock_offsets"]
    assert len(used) == 1 and used[0]["offset_s"] == 600.0 and used[0]["pairs"] == 12 and used[0]["spread_s"] == 4.0
    assert "600 seconds ahead of C1's (spread 4 s, 12 pairs)" in g["clock_words"]


def test_the_offset_applies_the_other_way_round(world, monkeypatch):
    _offsets(monkeypatch, [_reading(-60.0)])   # C2 a minute behind: it held the file later still
    g = _group(_all(world), SENT)
    assert [p["phone_label"] for p in g["phones"]] == ["C1", "C2"]
    assert {p["phone_label"]: p["clock_shift_s"] for p in g["phones"]} in ({"C1": None, "C2": 60.0},
                                                                          {"C1": -60.0, "C2": None})


@pytest.mark.parametrize("reading", [_reading(0.0, cls="server_stamped"), _reading(600.0, too_few=True, pairs=3)])
def test_a_service_time_or_too_few_pairs_establishes_no_offset(world, monkeypatch, reading):
    _offsets(monkeypatch, [reading])
    win = _all(world)
    g = _group(win, SENT)
    assert g["clock_offset_unknown"] is True and g["clock_offsets"] == []
    assert [p["phone_label"] for p in g["phones"]] == ["C1", "C2"]
    assert reading["words"] in g["clock_words"] and "no clock difference" in win["clock_words"]


def test_a_group_with_a_pair_without_an_offset_keeps_own_clocks_and_names_the_pair(world, monkeypatch):
    _offsets(monkeypatch, [_reading(600.0)])
    g = _group(_all(world), STICKER)   # on C1, C2 and C3: only C1 and C2 have a reading
    assert g["clock_offset_unknown"] is True and g["clock_offsets"] == []
    assert "C3" in g["clock_words"] and all(p["clock_shift_s"] is None for p in g["phones"])


def test_a_group_with_one_timed_phone_never_reads_as_a_known_offset():
    from services.phone import media_spread
    out = media_spread._clock(["C1"], {"pairs": {}})
    assert out["unknown"] is True and out["used"] == [] and out["words"] == media_spread.CLOCK_OWN


def test_phones_changed_since_the_run_is_said(world, monkeypatch):
    _offsets(monkeypatch, [_reading(600.0)], current=False)
    win = _all(world)
    assert "changed since that run" in win["clock_words"] and "changed since" in _group(win, SENT)["clock_words"]


# ---- 04's place model (11.3 step 6, 04 decision 48) ---------------------------------------------------------------

def _point(world, ext, record_ordinal, file_ordinal, *, kind, basis, flags):
    """A ``Media Locations`` point of the place model for one file."""
    record_uid, coordinate = uuid.uuid4(), uuid.uuid4()
    with world["engine"].begin() as c:
        c.execute(text(
            "INSERT INTO phone_file_references (extraction_id, document_index, record_ordinal, body_path, mechanism, "
            "reference_text, file_document_index, file_ordinal, resolution, ambiguous) VALUES (:e, 0, :r, 'p', "
            "'extracted_path_value', 'p', 0, :o, 'tagged_file', false)"), {"e": ext, "r": record_ordinal,
                                                                           "o": file_ordinal})
        gen = c.execute(text("SELECT generation FROM phone_interpretation_state WHERE extraction_id = :e"),
                        {"e": ext}).scalar()
        c.execute(text(
            "INSERT INTO phone_location_points (case_id, extraction_id, document_index, ordinal, record_uid, "
            "root_record_uid, locator, model_type, generation, point_uid, coordinate_record_uid, lat, lon, "
            "accuracy_basis, source_kind) VALUES (:c, :e, 0, :r, :u, :u, 'l', 'Location', :g, :p, :cu, 1.5, 2.5, "
            "'none', 'device_location')"), {"c": world["case"], "e": ext, "r": record_ordinal, "u": record_uid,
                                            "g": gen, "p": uuid.uuid4(), "cu": coordinate})
        c.execute(text(
            "INSERT INTO pol_place_observation (case_id, extraction_id, record_uid, record_type, kind, source_kind, "
            "lat, lon, radius_basis, start_utc, end_utc, offset_status, time_semantics, presence_basis, "
            "attribution_flags) VALUES (:c, :e, :u, 'Location', :k, 'media_exif', 1.5, 2.5, 'unknown', now(), now(), "
            "'explicit', 'instant', :b, :f)"), {"c": world["case"], "e": ext, "u": record_uid, "k": kind, "b": basis,
                                                "f": flags})


def _copy(g, label):
    return next(c for p in g["phones"] if p["phone_label"] == label for c in p["copies"])


def test_a_photo_the_model_counts_as_taken_here_says_the_phone_was_there(world):
    _point(world, world["x"], 0, 9002, kind="presence", basis="camera_matches_device", flags=["media_taken_on_device"])
    place = _copy(_group(_all(world), CAMERA), "C1")["place"]
    assert place["taken_on_this_phone"] is True and place["source"] == "photo EXIF"
    assert place["model"]["presence_basis"] == "camera_matches_device" and "10.5, -20.25" in place["words"]
    assert "the phone was there" in place["words"]


def test_received_media_in_the_model_is_never_where_the_phone_was(world):
    _point(world, world["x"], 0, 9002, kind="media", basis=None, flags=["received_media"])
    place = _copy(_group(_all(world), CAMERA), "C1")["place"]
    assert place["taken_on_this_phone"] is False and place["model"]["flags"] == ["received_media"]
    assert "nothing shows the phone was there" in place["words"]


def test_a_copy_received_in_a_message_is_not_presence_whatever_the_model_says(world):
    # the join may not raise a reading: this copy on C2 arrived in a message
    _point(world, world["y"], 1, 9002, kind="presence", basis="camera_folder", flags=["media_taken_on_device"])
    g = _group(_all(world), CAMERA)
    place = _copy(g, "C2")["place"]
    assert place["taken_on_this_phone"] is False and "not where the phone was" in place["words"]
    assert place["model"]["kind"] == "presence"      # what the model holds stays visible


def test_exif_with_no_point_in_the_model_keeps_the_written_place_and_claims_nothing(world):
    place = _copy(_group(_all(world), CAMERA), "C1")["place"]
    assert place["model"] is None and place["taken_on_this_phone"] is False
    assert "as written: 10.5, -20.25" in place["words"] and "nothing shows the phone was there" in place["words"]
