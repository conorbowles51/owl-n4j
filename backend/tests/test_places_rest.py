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
        with engine.connect() as c:
            evs = c.execute(text("SELECT decision, before, after, actor_name FROM adjudications WHERE subject_type = "
                                 "'place_cluster' ORDER BY subject_sequence")).fetchall()
            assert [e.decision for e in evs] == ["label_place", "label_place"]
            assert (evs[0].before["label"], evs[0].after["label"]) == (None, "Home (synthetic)")
            assert (evs[1].before["label"], evs[1].after["label"]) == ("Home (synthetic)", "Flat (synthetic)")
            assert c.execute(text("SELECT count(*) FROM manual_changes WHERE kind = 'pattern_place_name'"
                                  )).scalar() == 2
        # new data a few metres off moves the centre; the place keeps its name and identity
        with engine.begin() as c:
            p2 = routine_phone()
            for d in range(7):
                p2.location(DAY + timedelta(days=60 + d, hours=2), HOME[0] + 0.0003, HOME[1], accuracy=10)
            ext2 = p2.make(c, case)
        build(engine, ext2)
        from zoneinfo import ZoneInfo
        with engine.connect() as c:
            res = routine.compute(c, [str(ext2)], ZoneInfo("UTC"), case_id=case)
        h3 = min((p for p in res["places"] if p["routine"]), key=lambda p: abs(p["lat"] - HOME[0]))
        assert (h3["place_id"], h3["label"]) == (named["place_id"], "Flat (synthetic)")
        assert sum(1 for p in res["places"] if p["label"]) == 1  # one name, one place
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
            ext = make_extraction(c, case, p.records, timestamps=p.stamps, metadata={
                "DeviceInfoSelectedManufacturer": "Acme", "DeviceInfoSelectedDeviceName": "Phone X1"})
            _file(c, ext, cam, 1, "/storage/emulated/0/DCIM/Camera/IMG_1.jpg")
            _file(c, ext, exif, 2, "/storage/emulated/0/Pictures/Edited/IMG_2.jpg", "ACME", "phone x1")
            _file(c, ext, other, 3, "/storage/emulated/0/WhatsApp/Media/WhatsApp Images/IMG_3.jpg", "Other",
                  "Model 9")
            _file(c, ext, shot, 4, "/storage/emulated/0/Pictures/Screenshots/S_4.png")
        stats = build(engine, ext)
        got = [(o["kind"], o["presence_basis"], [f for f in o["attribution_flags"] if "media" in f])
               for o in obs(engine, ext)]
        assert got == [("presence", "camera_folder", ["media_taken_on_device"]),
                       ("presence", "camera_matches_device", ["media_taken_on_device"]),
                       ("media", None, ["received_media"]),
                       ("media", None, ["received_media"]),
                       ("media", None, ["received_media"])]
        assert bare not in (cam, exif)
        assert stats["media:camera_folder"] == 1 and stats["media:received_media"] == 3
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
