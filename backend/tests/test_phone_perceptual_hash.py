"""05 section 11.8 test 4 and the perceptual tier (cb-gated-spread D, G): a recompressed copy (a fixture JPEG
re-encoded at quality 70) is not in an exact group and is a near-identical pair; identical files stay in the exact
tier only; the exact tier's output is the same before and after hashing; hashing is resumable and skips one-phone
cases. Pictures are drawn here (synthetic); no case material."""
from __future__ import annotations

import hashlib
import io
import json
import uuid

import pytest
from sqlalchemy import text

from services.phone_analysis import perceptual_hash as PH
from tests.phone_pg import TEMPLATE_REASON, TEMPLATE_URL, fresh_engine, make_case
from tests.phone_streams_fixture import at, phone

OWNER, ANA = "phone:+12025550100", "phone:+12025550143"


def picture(seed=0, quality=95, size=(320, 240)):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", size, (30 + seed * 40 % 200, 90, 160))
    d = ImageDraw.Draw(img)
    for k in range(6):
        x = (37 * (k + 1) * (seed + 3)) % size[0]
        y = (53 * (k + 2) * (seed + 1)) % size[1]
        d.ellipse([x, y, x + 60 + 10 * k, y + 40 + 7 * k], fill=((k * 50 + seed * 30) % 255, 200 - k * 25, 40 + k * 30))
    d.rectangle([10, 10, 120 + seed * 15, 60], fill=(250, 250, 240))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def reencode(data, quality=70):
    from PIL import Image
    buf = io.BytesIO()
    Image.open(io.BytesIO(data)).save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def test_a_recompressed_copy_hashes_near_and_another_picture_far():
    a, b = picture(1), picture(2)
    a70 = reencode(a, 70)
    assert hashlib.md5(a).hexdigest() != hashlib.md5(a70).hexdigest()
    (pa, da), (pa70, da70), (pb, db) = PH.hashes(a), PH.hashes(a70), PH.hashes(b)
    assert PH.distance(pa, pa70) <= 6 and PH.distance(da, da70) <= 6
    assert max(PH.distance(pa, pb), PH.distance(da, db)) > 10
    assert PH.to_unsigned(PH.to_signed(pa)) == pa
    with pytest.raises(ValueError, match="cannot_open"):
        PH.hashes(b"%PDF-1.4 synthetic")
    with pytest.raises(ValueError, match="empty"):
        PH.hashes(b"")


def msg(instant, outgoing):
    parties = [(OWNER, "sender", True, None, None), (ANA, "recipient", False, None, None)] if outgoing else \
        [(ANA, "sender", False, None, None), (OWNER, "recipient", True, None, None)]
    return dict(kind="message", instant=instant, body="synthetic", parties=parties, thread="t",
                direction="outgoing" if outgoing else "incoming")


class World:
    def __init__(self, engine, root):
        self.engine, self.root, self.ordinal = engine, root, 9000

    def add(self, ext, name, data, *, path, record=None):
        self.ordinal += 1
        uid = str(uuid.uuid4())
        rel = "files/%s" % name
        dest = self.root / "up" / str(ext) / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        body = ["file", {"path": path, "id": uid}, None, None]
        with self.engine.begin() as c:
            c.execute(text(
                "INSERT INTO phone_files (extraction_id, document_index, ordinal, file_uid, local_path, disk_relpath, "
                "disk_size, declared_md5, tags, outcome, body) VALUES (:e, 0, :o, :f, :lp, :d, :s, :m, 'Image', "
                "'no_hash', CAST(:b AS jsonb))"),
                {"e": ext, "o": self.ordinal, "f": uid, "lp": rel, "d": rel, "s": len(data),
                 "m": hashlib.md5(data).hexdigest(), "b": json.dumps(body)})
            if record is not None:
                c.execute(text(
                    "INSERT INTO phone_file_references (extraction_id, document_index, record_ordinal, body_path, "
                    "mechanism, reference_text, file_document_index, file_ordinal, resolution, ambiguous) VALUES "
                    "(:e, 0, :r, :bp, 'extracted_path_value', :p, 0, :o, 'container_entry', false)"),
                    {"e": ext, "r": record, "p": path, "bp": "f%d" % self.ordinal, "o": self.ordinal})
        return uid


def _link(c, ext):
    cid = c.execute(text("SELECT first_container_id FROM phone_extractions WHERE id = :e"), {"e": ext}).scalar()
    c.execute(text("UPDATE phone_extraction_containers SET stored_path = :p WHERE id = :i"),
              {"p": "up/%s" % ext, "i": cid})
    c.execute(text("INSERT INTO phone_extraction_container_links (extraction_id, container_id, root_path) VALUES "
                   "(:e, :i, '')"), {"e": ext, "i": cid})


@pytest.fixture
def world(tmp_path, monkeypatch):
    if not TEMPLATE_URL:
        pytest.skip(TEMPLATE_REASON)
    monkeypatch.setattr("config.EVIDENCE_DATA_ROOT", str(tmp_path / "data"))
    PH._idle_until.clear()
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, solo = make_case(c), make_case(c)
            x, _ = phone(c, case, label="C1", events=[msg(at(2023, 3, 14, 12), True)])
            y, _ = phone(c, case, label="C2", events=[msg(at(2023, 3, 14, 12, 5), False)])
            s, _ = phone(c, solo, label="C9", events=[])
            for ext in (x, y):
                _link(c, ext)
        w = World(engine, tmp_path / "data" / str(case))
        a = picture(1)
        w.a_x = w.add(x, "sent.jpg", a, path="WhatsApp/Media/sent.jpg", record=0)
        w.a_y = w.add(y, "sent-recompressed.jpg", reencode(a, 70), path="WhatsApp/Media/r.jpg", record=0)
        same = picture(3)
        w.add(x, "same.jpg", same, path="DCIM/Camera/same.jpg")
        w.add(y, "same.jpg", same, path="DCIM/Camera/same.jpg")
        w.add(y, "other.jpg", picture(2), path="DCIM/Camera/other.jpg")
        w.case, w.solo, w.x, w.y, w.s = case, solo, x, y, s
        yield w


def test_11_8_4_recompressed_copy_is_near_identical_not_exact(world):
    from services.phone import media_spread as S
    with world.engine.connect() as c:
        exact_before = S.window(c, world.case, {}, 0, 100)
        index_before = S.index(c, world.case)
        pending = PH.describe(c, world.case)
    assert pending["pictures"] == 5 and pending["hashed"] == 0 and pending["waiting"] == 5
    done = PH.run_pending(world.engine)
    assert sorted(d["state"] for d in done) == ["done"] * 5
    assert PH.run_pending(world.engine) == []  # resumable: nothing is read twice
    with world.engine.connect() as c:
        exact_after = S.window(c, world.case, {}, 0, 100)
        index_after = S.index(c, world.case)
        page = S.perceptual(c, world.case)
        solo = PH.describe(c, world.solo)
    # the exact tier is unchanged by hashing (G), and holds only the identical pair
    assert json.dumps(exact_before, sort_keys=True, default=str) == json.dumps(exact_after, sort_keys=True, default=str)
    assert index_before == index_after and exact_after["total"] == 1
    assert all(g["md5"] != hashlib.md5(picture(1)).hexdigest() for g in exact_after["items"])
    # the recompressed copy is a near-identical pair; the identical pair is not listed again
    assert page["total"] == 1 and page["total_all"] == 1
    (p,) = page["items"]
    assert {p["a"]["file_uid"], p["b"]["file_uid"]} == {world.a_x, world.a_y}
    assert p["distance"] <= 6 and p["level"] in ("strong", "moderate", "weak")
    assert sum(page["by_strength"].values()) == 1 and page["by_strength"][p["level"]] == 1
    assert p["label"] == "Lead for enquiry" and p["reasons"]["match"]
    roles = {p["a"]["phone_label"]: p["a"]["roles"], p["b"]["phone_label"]: p["b"]["roles"]}
    assert roles == {"C1": ["sent"], "C2": ["received"]}
    assert page["hashing"]["hashed"] == 5
    # a one-phone case is not hashed, and says why
    assert solo["case_phones"] == 1 and solo["waiting"] == 0 and solo["not_hashed_words"]


def test_grading_rule():
    from services.phone import media_spread as S
    assert [S._level_of(d, False) for d in (0, 2, 3, 4, 5, 6, 7, 10)] == [
        "strong", "strong", "moderate", "moderate", "weak", "weak", "faint", "faint"]
    assert S._level_of(0, True) == "moderate" and S._level_of(9, True) == "faint"
