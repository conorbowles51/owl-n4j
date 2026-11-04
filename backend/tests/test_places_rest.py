"""cb-places-rest: named places (D), photos taken on the phone as presence (E), Together on the map (C), the place
label (G).

Synthetic phones only (invented coordinates, paths and camera names). Opt-in PostgreSQL through
``LOUPE_TEST_PHONE_PG_TEMPLATE_URL``. Each test fails on the code before this job: the naming route, the
media rule, the positions on Together items and the label did not exist.
"""
from __future__ import annotations

import json
import uuid
from datetime import timedelta

from sqlalchemy import text

from services.pattern_of_life import activity, places, routine
from services.phone import registry
from tests.phone_pg import fld, fresh_engine, make_case, make_extraction, model, needs_template, refs
from tests.test_pattern_u4_availability import DAY, _stamp, setup
from tests.test_pattern_u5_places import LAT, LON, PlacePhone, build, obs
from tests.test_pattern_u8_routine import HOME, routine_phone
from tests.test_phone_mappings import hooks  # noqa: F401 (fixture)


def _subject(ext):
    return json.dumps({"kind": "extraction", "extraction_id": str(ext)})


@needs_template
def test_d_a_named_place_keeps_its_name_through_a_recompute_and_the_deviation_uses_it(hooks):
    from tests.pattern_pg import api_client
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = routine_phone(away_tuesday_week=3).make(c, case)
        build(engine, ext)
        with api_client(engine, case) as cl:
            r = cl.get("/api/pattern/%s/routine" % case, params={"subject": _subject(ext), "zone": "UTC"})
            assert r.status_code == 200
            body = r.json()
            assert body["label"] == "Investigative location, not cell-site opinion"
            home = min((p for p in body["places"] if p["routine"]), key=lambda p: abs(p["lat"] - HOME[0]))
            assert home["place_id"] is None and home["label"] is None  # unnamed until a person names it
            r = cl.post("/api/pattern/%s/routine/places/name" % case, json={
                "subject": _subject(ext), "cluster_id": home["cluster_id"], "zone": "UTC", "label": "Home (synthetic)",
                "reason": "Overnight stays every night"})
            assert r.status_code == 200, r.text
            named = r.json()
            assert named["label"] == "Home (synthetic)" and named["previous_label"] is None
            again = cl.get("/api/pattern/%s/routine" % case, params={"subject": _subject(ext), "zone": "UTC"}).json()
            h2 = next(p for p in again["places"] if p["cluster_id"] == home["cluster_id"])
            assert (h2["place_id"], h2["label"], h2["label_by"]) == (named["place_id"], "Home (synthetic)", "synthetic")
            dev = cl.get("/api/pattern/%s/routine/deviations" % case, params={"subject": _subject(ext),
                                                                             "zone": "UTC"}).json()
            assert len(dev["flagged"]) == 1
            assert dev["flagged"][0]["expectation"] == "Usually at Home (synthetic) on Tuesdays 21:00 to 00:00."
            # a rename is a second decision; the first name stays in its before
            r = cl.post("/api/pattern/%s/routine/places/name" % case, json={
                "subject": _subject(ext), "cluster_id": home["cluster_id"], "zone": "UTC", "label": "Flat (synthetic)",
                "reason": "Renamed"})
            assert r.status_code == 200 and r.json()["previous_label"] == "Home (synthetic)"
            assert r.json()["place_id"] == named["place_id"]
            same = cl.post("/api/pattern/%s/routine/places/name" % case, json={
                "subject": _subject(ext), "cluster_id": home["cluster_id"], "zone": "UTC", "label": "Flat (synthetic)",
                "reason": "again"})
            assert same.status_code == 409
            missing = cl.post("/api/pattern/%s/routine/places/name" % case, json={
                "subject": _subject(ext), "cluster_id": 99, "zone": "UTC", "label": "x", "reason": "x"})
            assert missing.status_code == 404
            # the page's centre no longer the place's: the number now names another place, so nothing is saved
            moved = cl.post("/api/pattern/%s/routine/places/name" % case, json={
                "subject": _subject(ext), "cluster_id": home["cluster_id"], "zone": "UTC", "label": "Elsewhere",
                "reason": "x", "lat": HOME[0] + 0.01, "lon": HOME[1]})
            assert moved.status_code == 409 and "Reload" in moved.json()["detail"]
            seen = cl.post("/api/pattern/%s/routine/places/name" % case, json={
                "subject": _subject(ext), "cluster_id": home["cluster_id"], "zone": "UTC", "label": "Flat (synthetic)",
                "reason": "again", "lat": home["lat"], "lon": home["lon"]})
            assert seen.status_code == 409  # the centre matched; refused only as the same name
        with engine.connect() as c:
            evs = c.execute(text("SELECT decision, before, after, actor_name FROM adjudications WHERE subject_type = "
                                 "'place_cluster' ORDER BY subject_sequence")).fetchall()
            assert [e.decision for e in evs] == ["label_place", "label_place"]
            assert (evs[0].before["label"], evs[0].after["label"]) == (None, "Home (synthetic)")
            assert (evs[1].before["label"], evs[1].after["label"]) == ("Home (synthetic)", "Flat (synthetic)")
            assert c.execute(text("SELECT count(*) FROM manual_changes WHERE kind = 'pattern_place_name'"
                                  )).scalar() == 2
        # another phone with stays at the same spot: a place is its subject's own, so the name never crosses over
        with engine.begin() as c:
            p2 = routine_phone()
            for d in range(7):
                p2.location(DAY + timedelta(days=60 + d, hours=2), HOME[0] + 0.0003, HOME[1], accuracy=10)
            ext2 = p2.make(c, case)
        build(engine, ext2)
        from zoneinfo import ZoneInfo
        with engine.connect() as c:
            res = routine.compute(c, [str(ext2)], ZoneInfo("UTC"), case_id=case,
                                  subject="extraction:%s" % ext2)
            mine = routine.compute(c, [str(ext)], ZoneInfo("UTC"), case_id=case, subject="extraction:%s" % ext)
        assert res["places"] and not any(p["label"] or p["place_id"] for p in res["places"])
        h3 = min((p for p in mine["places"] if p["routine"]), key=lambda p: abs(p["lat"] - HOME[0]))
        assert (h3["place_id"], h3["label"]) == (named["place_id"], "Flat (synthetic)")
        assert sum(1 for p in mine["places"] if p["label"]) == 1  # one name, one place
        assert res["parameters"]["places_version"] == routine.PLACES_VERSION


class MediaPhone(PlacePhone):
    def photo(self, when, lat=LAT, lon=LON):
        top = self.o
        f = [fld("TimeStamp", ("TimeStamp", when.isoformat())), refs("Position", top + 1, kind="modelField"),
             fld("Category", ("String", "Media Locations"))]
        cf = [fld("Latitude", ("Double", str(lat))), fld("Longitude", ("Double", str(lon)))]
        self.records += [(top, None, top, model("Location", f)), (top + 1, top, top, model("Coordinate", cf))]
        self.stamps.append(_stamp(top, "TimeStamp", "Location", when))
        self.o += 2
        return top


def _file(c, ext, record_ordinal, file_ordinal, path, maker=None, cam_model=None):
    items = [["item", {"name": k}, v, None] for k, v in (("EXIFCameraMaker", maker), ("EXIFCameraModel", cam_model))
             if v]
    body = ["file", {"path": path}, None, [["metadata", {"section": "MetaData"}, None, items]]]
    c.execute(text("INSERT INTO phone_files (extraction_id, document_index, ordinal, file_uid, local_path, body) "
                   "VALUES (:e, 0, :o, :u, :p, CAST(:b AS jsonb))"),
              {"e": ext, "o": file_ordinal, "u": uuid.uuid4(), "p": "files/%d.jpg" % file_ordinal,
               "b": json.dumps(body)})
    c.execute(text("INSERT INTO phone_file_references (extraction_id, document_index, record_ordinal, body_path, "
                   "mechanism, reference_text, file_document_index, file_ordinal, resolution) VALUES (:e, 0, :r, "
                   "'0', 'jumptarget', 'x', 0, :o, 'tagged_file')"), {"e": ext, "r": record_ordinal, "o": file_ordinal})


@needs_template
def test_e_a_photo_taken_on_the_phone_is_presence_and_a_received_one_never_is(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            p = MediaPhone()
            cam = p.photo(DAY)
            exif = p.photo(DAY + timedelta(hours=1))
            other = p.photo(DAY + timedelta(hours=2))
            shot = p.photo(DAY + timedelta(hours=3))
            bare = p.photo(DAY + timedelta(hours=4))
            saved = p.photo(DAY + timedelta(hours=5))
            pro = p.photo(DAY + timedelta(hours=6))
            coded = p.photo(DAY + timedelta(hours=7))
            ext = make_extraction(c, case, p.records, timestamps=p.stamps, metadata={
                "DeviceInfoSelectedManufacturer": "Acme", "DeviceInfoSelectedDeviceName": "Phone X1"})
            _file(c, ext, cam, 1, "/storage/emulated/0/DCIM/Camera/IMG_1.jpg")
            _file(c, ext, exif, 2, "/storage/emulated/0/Pictures/Edited/IMG_2.jpg", "ACME", "phone x1")
            _file(c, ext, other, 3, "/storage/emulated/0/WhatsApp/Media/WhatsApp Images/IMG_3.jpg", "Other",
                  "Model 9")
            _file(c, ext, shot, 4, "/storage/emulated/0/Pictures/Screenshots/S_4.png")
            # a received photo saved to the camera roll keeps the sender's camera: not presence
            _file(c, ext, saved, 5, "/private/var/mobile/Media/DCIM/100APPLE/IMG_5.jpg", "Other", "Model 9")
            # one model name inside the other is another phone
            _file(c, ext, pro, 6, "/storage/emulated/0/Pictures/IMG_6.jpg", "Acme", "Phone X1 Pro")
            # the make written before the model, and a bracketed code, are the same camera
            _file(c, ext, coded, 7, "/storage/emulated/0/Pictures/IMG_7.jpg", "Acme Inc.", "Acme Phone X1 (A123)")
        stats = build(engine, ext)
        got = [(o["kind"], o["presence_basis"], [f for f in o["attribution_flags"] if "media" in f])
               for o in obs(engine, ext)]
        assert got == [("presence", "camera_folder", ["media_taken_on_device"]),
                       ("presence", "camera_matches_device", ["media_taken_on_device"]),
                       ("media", None, ["received_media"]),
                       ("media", None, ["received_media"]),
                       ("media", None, ["received_media"]),
                       ("media", None, ["received_media"]),
                       ("media", None, ["received_media"]),
                       ("presence", "camera_matches_device", ["media_taken_on_device"])]
        assert bare not in (cam, exif)
        assert stats["media:camera_folder"] == 1 and stats["media:received_media"] == 5
        assert "media" not in places.ROUTINE_KINDS  # received media stays out of routine and together


@needs_template
def test_e_the_places_version_is_part_of_the_projection_signature(hooks, monkeypatch):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            p = PlacePhone()
            p.location(DAY)
            ext = p.make(c, case)
        build(engine, ext)
        with engine.connect() as c:
            assert activity.stale(c) == []
            now = activity.signature(c, ext)
            monkeypatch.setattr(routine, "PLACES_VERSION", 1)
            assert activity.signature(c, ext) != now  # a phone built under version 1 is rebuilt
            monkeypatch.setattr(routine, "PLACES_VERSION", 2)
            assert activity.signature(c, ext) == now


@needs_template
def test_c_together_items_carry_both_positions_and_the_label(hooks):
    from tests.pattern_pg import api_client
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            a, b = PlacePhone(), PlacePhone()
            for k in range(3):
                a.location(DAY + timedelta(minutes=10 * k), accuracy=10)
                b.location(DAY + timedelta(minutes=10 * k, seconds=30), LAT + 0.0002, LON, accuracy=10)
            ea, eb = a.make(c, case), b.make(c, case)
        build(engine, ea)
        build(engine, eb)
        with api_client(engine, case) as cl:
            r = cl.post("/api/pattern/%s/together" % case, json={
                "subjects": [{"kind": "extraction", "extraction_id": str(ea)},
                             {"kind": "extraction", "extraction_id": str(eb)}],
                "start": (DAY - timedelta(hours=1)).isoformat(), "end": (DAY + timedelta(hours=2)).isoformat()})
            assert r.status_code == 200, r.text
            out = r.json()
        assert out["label"] == "Investigative location, not cell-site opinion"
        assert out["total"] >= 3 and out["items"]
        it = out["items"][0]
        assert abs(it["a_lat"] - LAT) < 1e-9 and abs(it["b_lat"] - (LAT + 0.0002)) < 1e-9
        assert it["a_radius_m"] == 20.0 and it["b_radius_m"] == 20.0


def test_f_phones_seen_in_an_area_counts_every_position_inside_and_none_outside():
    """03 13.3 / 07 J-10: drawing an area lists the phones seen in it, each with its exact count there."""
    from services.phone import map as M
    from tests.phone_streams_fixture import phone
    from tests.test_phone_map import _points
    if not __import__("tests.phone_pg", fromlist=["TEMPLATE_URL"]).TEMPLATE_URL:
        import pytest
        pytest.skip("Requires LOUPE_TEST_PHONE_PG_TEMPLATE_URL")
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            a, _ = phone(c, case, label="C1", device_zone="UTC")
            b, _ = phone(c, case, label="C2", device_zone="UTC")
            far, _ = phone(c, case, label="C3", device_zone="UTC")
            _points(c, case, a, [(40.0 + k * 0.0001, -74.0) for k in range(3)])
            _points(c, case, b, [(40.0002, -74.0001)], start=2000)
            _points(c, case, b, [(40.5, -74.009)], start=2100)  # in the box around the area, outside the triangle
            _points(c, case, far, [(41.0, -73.0)], start=3000)
        triangle = [[-74.01, 39.99], [-73.99, 39.99], [-74.0, 40.6]]
        with engine.connect() as c:
            out = M.area(c, case, triangle, {})
            assert [(p["phone_label"], p["points"]) for p in out["phones"]] == [("C1", 3), ("C2", 1)]
            assert (out["phones_total"], out["points_total"]) == (2, 4)
            assert out["label"] == "Investigative location, not cell-site opinion"
            assert out["phones"][0]["first"] is not None
            import pytest
            with pytest.raises(ValueError):
                M.area(c, case, [[0, 0], [1, 1]], {})
    assert M._inside(0.5, 0.5, [(0, 0), (1, 0), (1, 1), (0, 1)]) and not M._inside(1.5, 0.5, [(0, 0), (1, 0), (1, 1), (0, 1)])


def test_g_an_export_that_prints_locations_carries_the_investigative_label():
    from services.phone.exports import jobs
    assert jobs.place_words(["messages", "locations"]) == (
        "Locations in this export: investigative location, not cell-site opinion. A position is what the phone "
        "recorded, read by an investigator.")
    assert jobs.place_words(["messages", "calls"]) is None


# ---- I: the media viewer's filters, Download originals and the case blur default (03 8.3) -------------------------

from tests.test_phone_media import LINKED, LOOSE, MISSING, world  # noqa: E402,F401 (fixture)


def _phones_client(engine, case):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from postgres.models.enums import GlobalRole
    from postgres.models.user import User
    from postgres.session import get_db
    from routers.phones import router
    from routers.users import get_current_db_user
    with engine.connect() as c:
        owner, email = c.execute(text("SELECT u.id, u.email FROM cases k JOIN users u ON u.id = k.owner_user_id "
                                      "WHERE k.id = :c"), {"c": case}).one()
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
    return TestClient(app, raise_server_exceptions=False)


def _carrier(c, case):
    """(app, identity_key) of the message carrying LINKED; the app is set when the synthetic call has none."""
    row = c.execute(text(
        "SELECT ev.record_uid, ev.app, ev.generation FROM pv_attachment_link l JOIN phone_record_summaries s ON "
        "s.record_uid = l.record_uid JOIN phone_comm_events ev ON ev.record_uid = coalesce(s.root_record_uid, "
        "l.record_uid) AND ev.generation = s.generation WHERE l.case_id = :c AND l.file_uid = :f"),
        {"c": case, "f": LINKED}).one()
    if not row.app:
        c.execute(text("UPDATE phone_comm_events SET app = 'SyntheticApp' WHERE record_uid = :r"), {"r": row.record_uid})
    key = c.execute(text("SELECT identity_key FROM phone_participations WHERE record_uid = :r AND generation = :g AND "
                         "identity_key IS NOT NULL AND NOT coalesce(is_phone_owner, false) LIMIT 1"), {"r": row.record_uid, "g": row.generation}).scalar()
    return row.app or "SyntheticApp", key


@needs_template
def test_i_the_app_participant_and_date_filters_keep_only_the_files_carried_that_way(world):
    from services.phone import media
    engine, case, _, ext = world
    with engine.begin() as c:
        app, key = _carrier(c, case)
    with engine.connect() as c:
        everything = media.index(c, case, {})["total"]
        assert everything == 3
        assert [i["file_uid"] for i in media.window(c, case, {"apps": [app]})["items"]] == [LINKED]
        assert media.index(c, case, {"apps": ["NoSuchApp"]})["total"] == 0
        assert key is not None
        assert [i["file_uid"] for i in media.window(c, case, {"participants": [key]})["items"]] == [LINKED]
        assert media.index(c, case, {"participants": ["nobody"]})["total"] == 0
        when = media.window(c, case, {})["items"][0]["taken_or_sent"]
        assert when["basis"] == "message_time"
        t = when["instant"] if "instant" in when else when.get("utc")
        assert t, when
        from datetime import datetime
        at = datetime.fromisoformat(t.replace("Z", "+00:00"))
        inside = media.index(c, case, {"from_instant": at - timedelta(minutes=1), "to_instant": at + timedelta(minutes=1)})
        assert inside["total"] == 1 and inside["outside_dates_no_time"] == 2  # the two untimed files are counted
        assert media.index(c, case, {"from_instant": at + timedelta(minutes=1)})["total"] == 0
        assert media.window(c, case, {})["items"][0]["hashes"] == {"md5": None, "sha256": None}
        fac = media.facets(c, case, {"phones": [ext]})
        assert fac["apps"] == [{"app": app, "files": 1}]
        assert [(x["key"], x["files"]) for x in fac["participants"]] == [(key, 1)]
        assert media.facets(c, case, {"categories": ["none"]}) == {"case_id": str(case), "apps": [], "participants": []}


def _on_disk(engine, case, ext, tmp_path, monkeypatch, data=b"synthetic bytes"):
    import hashlib
    monkeypatch.setattr("config.EVIDENCE_DATA_ROOT", str(tmp_path))
    (tmp_path / str(case) / "up" / "root" / "chats").mkdir(parents=True)
    (tmp_path / str(case) / "up" / "root" / "chats" / "synthetic-a.jpg").write_bytes(data)
    with engine.begin() as c:
        c.execute(text("UPDATE phone_files SET disk_relpath = 'chats/synthetic-a.jpg', disk_size = :n, disk_sha256 = :h "
                       "WHERE file_uid = :f"), {"f": LINKED, "n": len(data), "h": hashlib.sha256(data).hexdigest()})
        cid = c.execute(text("SELECT first_container_id FROM phone_extractions WHERE id = :e"), {"e": ext}).scalar()
        c.execute(text("UPDATE phone_extraction_containers SET container_kind = 'folder', stored_path = 'up' WHERE "
                       "id = :i"), {"i": cid})
        c.execute(text("DELETE FROM phone_extraction_container_links WHERE extraction_id = :e"), {"e": ext})
        c.execute(text("INSERT INTO phone_extraction_container_links (extraction_id, container_id, root_path) VALUES "
                       "(:e, :i, 'root')"), {"e": ext, "i": cid})
    return hashlib.sha256(data).hexdigest()


@needs_template
def test_i_download_originals_is_a_zip_of_the_files_with_a_manifest_whose_hashes_match(world, tmp_path, monkeypatch):
    import csv
    import io
    import zipfile
    engine, case, _, ext = world
    sha = _on_disk(engine, case, ext, tmp_path, monkeypatch)
    with _phones_client(engine, case) as cl:
        body = {"filter": {"case_id": str(case)}, "file_uids": [LINKED, MISSING]}
        r = cl.post("/api/phones/media/download", json=dict(body, check_only=True))
        assert r.status_code == 200, r.text
        facts = r.json()
        assert (facts["count"], facts["held"], facts["not_in_production"], facts["refusal"]) == (2, 1, 1, None)
        r = cl.post("/api/phones/media/download", json=body)
        assert r.status_code == 200, r.text
        assert r.headers["x-files"] == "2" and r.headers["x-files-not-in-production"] == "1"
        z = zipfile.ZipFile(io.BytesIO(r.content))
        assert z.testzip() is None
        names = z.namelist()
        assert names[-1] == "manifest.csv" and len(names) == 2
        assert z.read(names[0]) == b"synthetic bytes"
        rows = list(csv.reader(io.StringIO(z.read("manifest.csv").decode("utf-8"))))
        assert rows[0][0] == "file_in_zip" and len(rows) == 3
        held = next(x for x in rows[1:] if x[0] == names[0])
        assert (held[9], held[10]) == (sha, "yes")
        gone = next(x for x in rows[1:] if x is not held)
        assert gone[5] == "not in the production" and gone[9] == "" and gone[0] == ""  # nothing in the zip for it
        # a file that cannot be read refuses the whole download before any byte
        r = cl.post("/api/phones/media/download", json={"filter": {"case_id": str(case)}})
        assert r.status_code == 409 and "nothing was downloaded" in r.json()["detail"], r.text


@needs_template
def test_i_a_download_over_the_limit_is_refused_with_its_numbers_and_nothing_is_made(world, monkeypatch):
    from services.phone import media
    engine, case, _, _ext = world
    monkeypatch.setattr(media, "DOWNLOAD_MAX_FILES", 2)
    with _phones_client(engine, case) as cl:
        r = cl.post("/api/phones/media/download", json={"filter": {"case_id": str(case)}})
        assert r.status_code == 413, r.text
        words = r.json()["detail"]
        assert words.startswith("These 3 files are") and "at most 2 files" in words and "nothing was made" in words
        r = cl.post("/api/phones/media/download", json={"filter": {"case_id": str(case)}, "check_only": True})
        assert r.status_code == 200 and r.json()["refusal"] == words
        # a chosen file outside the filter is refused, never silently dropped
        r = cl.post("/api/phones/media/download", json={"filter": {"case_id": str(case), "categories": ["none"]},
                                                        "file_uids": [LINKED]})
        assert r.status_code == 422


@needs_template
def test_i_media_blur_is_on_by_default_in_a_criminal_case_and_a_case_setting_overrides_it(world):
    engine, case, other, _ext = world
    with _phones_client(engine, case) as cl:
        got = cl.get("/api/phones/settings", params={"case_id": str(case)}).json()["media_blur"]
        assert (got["default_on"], got["basis"]) == (False, "not_criminal")
        with engine.begin() as c:
            c.execute(text("INSERT INTO case_contexts (id, case_id, active_template_key, created_at, updated_at) "
                           "VALUES (gen_random_uuid(), :c, 'criminal_defense', now(), now())"), {"c": case})
        got = cl.get("/api/phones/settings", params={"case_id": str(case)}).json()["media_blur"]
        assert (got["default_on"], got["basis"], got["words"]) == (True, "criminal_case",
                                                                   "On by default in a criminal case.")
        r = cl.put("/api/phones/settings/media-blur", json={"case_id": str(case), "default_on": False})
        assert r.status_code == 200, r.text
        assert (r.json()["default_on"], r.json()["basis"], r.json()["set"]) == (False, "case_setting", False)
        r = cl.put("/api/phones/settings/media-blur", json={"case_id": str(case), "default_on": None})
        assert r.json()["basis"] == "criminal_case"  # cleared: follows the case kind again
        r = cl.put("/api/phones/settings/media-blur", json={"case_id": str(other), "default_on": True})
        assert r.status_code in (403, 404)
