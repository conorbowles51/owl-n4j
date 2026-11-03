"""05 section 17.6: image search by description over a case's phone images, on this server.

A person indexes the case's images (approach 8's population plus camera files): each distinct content is embedded
once by a local image-text model and stored per content hash; a file is linked to its content's vector. A text is
embedded by the same model and the images are ranked by similarity; a result shows the image, its phones and the
messages that carried it, labelled machine-ranked. Every count is a true count, every file left out has a reason.

The child process is replaced by a stand-in that answers like the real one (vectors chosen per image content),
except in the last test, which runs the real child against the pinned SigLIP 2 model when ``LOUPE_IMAGE_MODEL_DIR``
holds it. Every image is generated here (a red square, a blue circle, the word INVOICE); no case data. Needs the
PostgreSQL phone template for every test but the child tests.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import socket
import subprocess
import sys

import pytest
from sqlalchemy import text

from tests.phone_pg import TEMPLATE_REASON, TEMPLATE_URL, fresh_engine, make_case
from tests.phone_streams_fixture import at, phone

OWNER, ANA = "phone:+12025550100", "phone:+12025550143"


def _png(kind, fmt="PNG"):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (320, 320), "white")
    d = ImageDraw.Draw(im)
    if kind == "red":
        d.rectangle([60, 60, 260, 260], fill="red")
    elif kind == "blue":
        d.ellipse([60, 60, 260, 260], fill="blue")
    elif kind == "invoice":
        d.text((40, 140), "INVOICE", fill="black", font_size=56)
    out = io.BytesIO()
    im.save(out, fmt)
    return out.getvalue()


def _png_size(width, height):
    from PIL import Image
    out = io.BytesIO()
    Image.new("RGB", (width, height), "green").save(out, "PNG")
    return out.getvalue()


RED, BLUE, INVOICE = _png("red"), _png("blue", "JPEG"), _png("invoice")
HEIC = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + b"\x00" * 64
PDF = b"%PDF-1.4\n% synthetic\n" + b"0" * 64
DAMAGED = b"\xff\xd8\xff\xe0" + b"synthetic damaged jpeg" * 4
sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731

# the stand-in model: a 4-dimensional space where each synthetic picture and description has its own direction
VEC = {sha(RED): [1, 0, 0, 0], sha(BLUE): [0, 1, 0, 0], sha(INVOICE): [0, 0, 1, 0]}
TEXT = {"a red square": [0.9, 0.1, 0.05, 0], "an invoice": [0.05, 0, 1, 0.1]}


def _unit(v):
    n = math.sqrt(sum(x * x for x in v)) or 1
    return [x / n for x in v]


class FakeChild:
    """Answers like the child: a vector per image it can "open" (the synthetic pictures), "cannot_open" otherwise."""

    def __init__(self, monkeypatch, fail=False):
        from services.phone import image_search
        self.calls, self.fail = [], fail
        real = subprocess.run

        def run(argv, *a, **k):
            if argv[:2] == [sys.executable, "-I"]:
                req = json.loads(k["input"])
                self.calls.append({"argv": argv, "input": req, "env": k["env"]})
                if self.fail:
                    return subprocess.CompletedProcess(argv, 1, stdout="", stderr="Killed")
                return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(self.answer(req)), stderr="")
            return real(argv, *a, **k)
        monkeypatch.setattr(image_search.subprocess, "run", run)

    @staticmethod
    def answer(req):
        out = {"transformers_version": "5.3.0", "torch_version": "2.11.0"}
        if req["mode"] == "text":
            return dict(out, vector=_unit(TEXT.get(req["text"].lower(), [0.5, 0.5, 0.5, 0.5])), tokens=4,
                        truncated=False)
        res = []
        for p in req["images"]:
            v = VEC.get(sha(open(p, "rb").read()))
            res.append({"vector": _unit(v)} if v else {"reason": "cannot_open", "detail": "synthetic"})
        return dict(out, pillow_version="12.1.1", results=res)


@pytest.fixture
def model(tmp_path, monkeypatch):
    """A model folder with stand-in files (synthetic weights) and its manifest."""
    from services.phone import image_search_models as M
    d = tmp_path / "img" / M.MODEL["folder"]
    d.mkdir(parents=True)
    for f in M.FILES:
        (d / f).write_bytes(b"synthetic " + f.encode())
    (d / M.WEIGHTS).write_bytes(b"synthetic weights " * 2048)
    (d / M.MANIFEST).write_text(json.dumps({"repo": M.MODEL["repo"], "revision": M.MODEL["revision"]}))
    monkeypatch.setenv("LOUPE_IMAGE_MODEL_DIR", str(tmp_path / "img"))
    monkeypatch.setenv("LOUPE_IMAGE_QUERY_IDLE_SECONDS", "0")  # a child per description (the stand-in answers it)
    from services.phone import image_search
    image_search._QUERY_CACHE.clear()
    return d


def msg(instant, outgoing):
    parties = [(OWNER, "sender", True, None, None), (ANA, "recipient", False, None, None)] if outgoing else \
        [(ANA, "sender", False, None, None), (OWNER, "recipient", True, None, None)]
    return dict(kind="message", instant=instant, body="synthetic", parties=parties, thread="t",
                direction="outgoing" if outgoing else "incoming")


class World:
    def __init__(self, engine, root):
        self.engine, self.root, self.ordinal, self.files = engine, root, 9000, {}

    def add(self, ext, name, data, *, path, category="Image", outcome="no_hash", record=None, items=(),
            disk_sha=None):
        """One file on phone ``ext``: its bytes in the phone's folder container (None: not in the production)."""
        import uuid
        self.ordinal += 1
        uid = str(uuid.uuid4())
        rel = "files/%s" % name
        body = ["file", {"path": path, "id": uid}, None,
                [["metadata", {"section": "MetaData"}, None, [["item", {"name": k}, v, None] for k, v in items]]]
                if items else None]
        if data is not None:
            dest = self.root / "up" / str(ext) / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        with self.engine.begin() as c:
            c.execute(text(
                "INSERT INTO phone_files (extraction_id, document_index, ordinal, file_uid, local_path, disk_relpath, "
                "disk_size, disk_sha256, tags, outcome, body) VALUES (:e, 0, :o, :f, :lp, :d, :s, :ds, :t, :out, "
                "CAST(:b AS jsonb))"),
                {"e": ext, "o": self.ordinal, "f": uid, "lp": rel, "d": rel if data is not None else None,
                 "s": len(data) if data is not None else None, "ds": disk_sha, "t": category, "out": outcome,
                 "b": json.dumps(body)})
            if record is not None:
                c.execute(text(
                    "INSERT INTO phone_file_references (extraction_id, document_index, record_ordinal, body_path, "
                    "mechanism, reference_text, file_document_index, file_ordinal, resolution, ambiguous) VALUES "
                    "(:e, 0, :r, :bp, 'extracted_path_value', :p, 0, :o, 'container_entry', false)"),
                    {"e": ext, "r": record, "p": path, "bp": "f%d" % self.ordinal, "o": self.ordinal})
        self.files[name] = uid
        return uid


@pytest.fixture
def world(tmp_path, monkeypatch, model):
    if not TEMPLATE_URL:
        pytest.skip(TEMPLATE_REASON)
    monkeypatch.setattr("config.EVIDENCE_DATA_ROOT", str(tmp_path / "data"))
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, other = make_case(c), make_case(c)
            x, _ = phone(c, case, label="C1", events=[msg(at(2023, 3, 14, 12), True)])
            y, _ = phone(c, case, label="C2", events=[msg(at(2023, 3, 14, 12, 5), False)])
            for ext in (x, y):
                cid = c.execute(text("SELECT first_container_id FROM phone_extractions WHERE id = :e"),
                                {"e": ext}).scalar()
                c.execute(text("UPDATE phone_extraction_containers SET stored_path = :p WHERE id = :i"),
                          {"p": "up/%s" % ext, "i": cid})
                c.execute(text("INSERT INTO phone_extraction_container_links (extraction_id, container_id, root_path) "
                               "VALUES (:e, :i, '')"), {"e": ext, "i": cid})
            user = c.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": case}).scalar()
        w = World(engine, tmp_path / "data" / str(case))
        w.case, w.other, w.x, w.y, w.user = case, other, x, y, user
        # in the population: attached to a message, in a camera folder, EXIF camera, in a screenshot folder
        w.add(x, "red.png", RED, path="WhatsApp/Media/red.png", record=0)
        w.add(y, "red-copy.png", RED, path="DCIM/Camera/red-copy.png")
        w.add(x, "blue.jpg", BLUE, path="Pictures/blue.jpg", items=(("EXIFCameraMaker", "SyntheticMaker"),))
        w.add(y, "invoice.png", INVOICE, path="Pictures/Screenshots/invoice.png")
        w.add(x, "photo.heic", HEIC, path="DCIM/100APPLE/photo.heic")
        w.add(x, "not-a-picture.jpg", PDF, path="DCIM/Camera/not-a-picture.jpg")
        w.add(y, "damaged.jpg", DAMAGED, path="DCIM/Camera/damaged.jpg")
        w.add(y, "placeholder.jpg", b"", path="DCIM/Camera/placeholder.jpg", outcome="empty_placeholder")
        w.add(x, "gone.jpg", None, path="WhatsApp/Media/gone.jpg", outcome="missing", record=0)
        # not in the population: an app's picture no message carried, outside camera folders, no camera EXIF
        w.add(x, "icon.png", RED, path="data/app/synthetic/icon.png")
        w.add(y, "clip.mp4", b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32, path="DCIM/Camera/clip.mp4",
              category="Video")
        w.add(y, "unknown.bin", b"synthetic", path="DCIM/unknown.bin", category="")
        yield w


def _describe(w, case=None):
    from services.phone import image_search
    with w.engine.connect() as c:
        return image_search.describe(c, case or w.case)


def _create(w):
    from services.phone import image_search
    with w.engine.begin() as c:
        return image_search.create(c, case_id=w.case, user_id=w.user)


def _no_outbound(monkeypatch):
    """Any outbound connection from this process (other than to the local test database) is recorded."""
    seen = []
    real = socket.socket.connect

    def connect(self, addr, *a, **k):
        host = addr[0] if isinstance(addr, tuple) else str(addr)
        if host not in ("127.0.0.1", "::1", "localhost") and not str(host).startswith("/"):
            seen.append(addr)
        return real(self, addr, *a, **k)
    monkeypatch.setattr(socket.socket, "connect", connect)
    return seen


def _drain(w):
    from services.phone import image_search
    out = []
    while True:
        got = image_search.run_pending(w.engine)
        if not got:
            return out
        out += got


def test_the_counts_before_starting_are_true_and_every_image_left_out_has_its_reason(world):
    d = _describe(world)
    # 10 images: 7 readable in the population, 1 empty placeholder, 1 not in the production, 1 outside it
    assert d["images"] == 10 and d["eligible"] == 7
    assert d["left_out"] == {"not_in_population": 1, "not_in_production": 1, "empty_placeholder": 1,
                             "could_not_open": 0, "could_not_open_by_reason": {}}
    assert (d["indexed"], d["waiting"], d["uncategorised_files"]) == (0, 0, 1)
    assert d["model_installed"] and d["model"] == "siglip2-base-patch16-224" and d["revision_short"] == "75de2d5"
    assert _describe(world, world.other)["images"] == 0  # another case sees nothing


def test_indexing_embeds_each_content_once_links_every_copy_and_states_each_failure(world, monkeypatch):
    from services.phone import image_search
    from services.phone import image_search_models as M
    seen = _no_outbound(monkeypatch)
    child = FakeChild(monkeypatch)
    job = _create(world)
    assert (job["total"], job["queued"], job["state"]) == (7, 7, "running")
    _drain(world)
    # one draw: the heic and the PDF were refused from their first bytes and never went to the model; the red
    # square is embedded once although two phones hold it
    [call] = child.calls
    assert call["argv"][3].startswith(image_search.derive.GUARD)
    assert {k: call["env"][k] for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")} == {"HF_HUB_OFFLINE": "1",
                                                                                       "TRANSFORMERS_OFFLINE": "1"}
    assert call["input"]["mode"] == "image" and len(call["input"]["images"]) == 4  # red, blue, invoice, damaged
    assert call["input"]["model"] == str(M.model_dir())
    with world.engine.connect() as c:
        rows = {r.file_uid: r for r in c.execute(text(
            "SELECT file_uid::text, state, outcome, reason, error, content_sha256, weights_sha256, sniffed_container "
            "FROM phone_image_index_items WHERE case_id = :c"), {"c": world.case})}
        vectors = c.execute(text("SELECT content_sha256, dim, octet_length(vector) AS n, model_id, weights_sha256, "
                                 "parameters FROM phone_image_vectors WHERE case_id = :c ORDER BY 1"),
                            {"c": world.case}).fetchall()
    f = world.files
    weights = hashlib.sha256((M.model_dir() / M.WEIGHTS).read_bytes()).hexdigest()
    assert sorted(v.content_sha256 for v in vectors) == sorted({sha(RED), sha(BLUE), sha(INVOICE)})
    assert all(v.dim == 4 and v.n == 16 and v.weights_sha256 == weights for v in vectors)
    assert vectors[0].model_id == "google/siglip2-base-patch16-224@" + M.MODEL["revision"]
    assert vectors[0].parameters["text_max_tokens"] == 64 and vectors[0].parameters["transformers_version"] == "5.3.0"
    outcomes = sorted(rows[f[n]].outcome for n in ("red.png", "red-copy.png"))
    assert outcomes == ["embedded", "reused"]
    assert rows[f["red.png"]].content_sha256 == rows[f["red-copy.png"]].content_sha256 == sha(RED)
    assert rows[f["blue.jpg"]].outcome == "embedded" and rows[f["blue.jpg"]].sniffed_container == "jpeg"
    assert (rows[f["photo.heic"]].state, rows[f["photo.heic"]].reason) == ("failed", "heic")
    assert rows[f["photo.heic"]].error == "Stored as HEIC, which the image library on this server cannot open."
    assert rows[f["not-a-picture.jpg"]].reason == "not_image" and "a PDF file" in rows[f["not-a-picture.jpg"]].error
    assert rows[f["damaged.jpg"]].reason == "cannot_open"
    with world.engine.connect() as c:
        [s] = image_search.status(c, world.case)
    assert (s["total"], s["done"], s["embedded"], s["reused"], s["failed"], s["state"]) == (7, 4, 3, 1, 3, "done")
    assert s["failed_by_reason"] == {"heic": 1, "not_image": 1, "cannot_open": 1}
    assert s["first_started_at"] and s["last_finished_at"]
    # after: nothing left to index; the three that could not be opened are counted by reason and not retried
    d = _describe(world)
    assert (d["eligible"], d["indexed"], d["indexed_contents"]) == (0, 4, 3)
    assert d["left_out"]["could_not_open"] == 3
    assert d["left_out"]["could_not_open_by_reason"] == {"heic": 1, "not_image": 1, "cannot_open": 1}
    with world.engine.begin() as c, pytest.raises(image_search.ImageSearchError, match="nothing was queued"):
        image_search.create(c, case_id=world.case, user_id=None)
    assert seen == []


def test_a_description_ranks_the_case_images_and_each_result_shows_its_phones_and_messages(world, monkeypatch):
    from services.phone import image_search
    from services.phone.readings import phone_labels
    child = FakeChild(monkeypatch)
    _create(world)
    _drain(world)
    with world.engine.connect() as c:
        got = image_search.search(c, world.case, "a red square")
        labels = phone_labels(c, world.case)
        again = image_search.search(c, world.case, "A red square ", limit=1)
        other = image_search.search(c, world.other, "a red square")
    assert got["scored"] == 3 and got["shown"] == 3 and got["scored_files"] == 4
    assert [r["content_sha256"] for r in got["results"]] == [sha(RED), sha(BLUE), sha(INVOICE)]
    assert [r["rank"] for r in got["results"]] == [1, 2, 3] and "score" not in got["results"][0]
    top = got["results"][0]
    assert top["copy_count"] == 2 and top["phones"] == sorted({labels[str(world.x)], labels[str(world.y)]})
    # the copy a message carried comes first, with its message count; the detail screen opens to the message
    assert [(c_["filename"], c_["message_count"]) for c_ in top["copies"]] == [("red.png", 1), ("red-copy.png", 0)]
    assert got["label"] == ("Machine-ranked by siglip2-base-patch16-224 75de2d5; a result points to an image, it does "
                            "not describe it.")
    assert got["provider_words"].startswith("Made on this server.")
    assert got["coverage"]["indexed"] == 4 and got["coverage"]["left_out"]["could_not_open"] == 3
    # the same description again is answered without running the model again; the limit is honoured and stated
    assert len(child.calls) == 2 and again["shown"] == 1 and again["scored"] == 3
    assert other["scored"] == 0 and other["results"] == []
    text_call = child.calls[1]
    assert text_call["input"] == {"mode": "text", "text": "a red square", "max_tokens": 64,
                                  "model": text_call["input"]["model"]}
    assert "a red square" not in " ".join(text_call["argv"])  # on standard input, not the command line
    with world.engine.connect() as c:
        inv = image_search.search(c, world.case, "an invoice")
    assert inv["results"][0]["content_sha256"] == sha(INVOICE)


def test_a_superseded_phone_drops_out_of_the_results(world, monkeypatch):
    from services.phone import image_search
    FakeChild(monkeypatch)
    _create(world)
    _drain(world)
    with world.engine.begin() as c:
        c.execute(text("UPDATE phone_extractions SET standing = 'superseded' WHERE id = :e"), {"e": world.x})
    with world.engine.connect() as c:
        got = image_search.search(c, world.case, "a red square")
    # the blue photo was only on the superseded phone; the red square stays through its copy on the other phone
    assert got["scored"] == 2 and [r["copy_count"] for r in got["results"]][0] == 1
    assert sha(BLUE) not in [r["content_sha256"] for r in got["results"]]
    # the ranking and the coverage count the same things: distinct pictures, and the files holding them
    assert got["scored_files"] == 2 == got["coverage"]["indexed"]
    assert got["coverage"]["indexed_contents"] == got["scored"] == 2


def test_a_file_whose_verified_hash_is_already_embedded_is_linked_without_reading_it(world, monkeypatch):
    from services.phone import image_search
    FakeChild(monkeypatch)
    _create(world)
    _drain(world)
    # a third copy whose bytes are not even on disk: its verified hash names content already embedded
    uid = world.add(world.y, "red-third.png", None, path="DCIM/Camera/red-third.png", disk_sha=sha(RED),
                    outcome="match")
    with world.engine.begin() as c:
        c.execute(text("UPDATE phone_files SET disk_relpath = 'files/red-third.png' WHERE file_uid = :f"), {"f": uid})
    assert _describe(world)["eligible"] == 1
    _create(world)
    assert _drain(world) == [{"id": _drain_id(world, uid), "state": "done", "outcome": "reused"}]
    with world.engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM phone_image_vectors WHERE case_id = :c"),
                         {"c": world.case}).scalar() == 3
        assert image_search.search(c, world.case, "a red square")["results"][0]["copy_count"] == 3


def _drain_id(w, uid):
    with w.engine.connect() as c:
        return str(c.execute(text("SELECT id FROM phone_image_index_items WHERE file_uid = :f"), {"f": uid}).scalar())


def test_a_missing_model_is_refused_in_words_and_nothing_is_queued_or_sent(world, monkeypatch, tmp_path):
    from services.phone import image_search
    child = FakeChild(monkeypatch)
    monkeypatch.setenv("LOUPE_IMAGE_MODEL_DIR", str(tmp_path / "nothing-here"))
    d = _describe(world)
    assert not d["model_installed"] and d["model_words"] == image_search.NO_MODEL == (
        "The image search model is not installed on this server. Nothing was sent anywhere.")
    with world.engine.begin() as c, pytest.raises(image_search.ImageSearchError, match="^The image search model is"):
        image_search.create(c, case_id=world.case, user_id=None)
    with world.engine.connect() as c:
        with pytest.raises(image_search.ImageSearchError, match="not installed"):
            image_search.search(c, world.case, "a red square")
        assert c.execute(text("SELECT count(*) FROM phone_image_index_items")).scalar() == 0
    assert child.calls == []


def test_the_model_removed_while_a_job_waits_fails_its_files_with_the_words(world, monkeypatch, tmp_path, model):
    from services.phone import image_search
    child = FakeChild(monkeypatch)
    _create(world)
    monkeypatch.setenv("LOUPE_IMAGE_MODEL_DIR", str(tmp_path / "nothing-here"))
    got = image_search.run_pending(world.engine)
    assert len(got) == 7 and {g["reason"] for g in got} == {"no_model"} and child.calls == []
    with world.engine.connect() as c:
        assert set(c.execute(text("SELECT error FROM phone_image_index_items")).scalars()) == {image_search.NO_MODEL}
    # not a fault of the files: once the model is back they are offered again
    monkeypatch.setenv("LOUPE_IMAGE_MODEL_DIR", str(model.parent))
    assert _describe(world)["eligible"] == 7


def test_cancel_removes_files_not_started_and_keeps_every_indexed_one(world, monkeypatch):
    from services.phone import image_search
    FakeChild(monkeypatch)
    job = _create(world)
    image_search.run_pending(world.engine, limit=2)
    with world.engine.begin() as c:
        out = image_search.cancel(c, world.case, job["id"])
    assert out["state"] == "cancelled" and out["cancelled_count"] == 5 and out["done"] + out["failed"] == 2
    assert _describe(world)["eligible"] == 5  # the rest can be indexed later
    with world.engine.connect() as c, pytest.raises(LookupError):
        image_search.cancel(c, world.other, job["id"])


def test_the_could_not_open_reasons_add_up_to_their_total(world, monkeypatch):
    """Review finding: the breakdown counted every failed file of the case, the total only those still in the
    population, in the production and not indexed since."""
    FakeChild(monkeypatch)
    _create(world)
    _drain(world)
    with world.engine.begin() as c:  # the HEIC file is no longer in the production
        c.execute(text("UPDATE phone_files SET outcome = 'missing', disk_relpath = NULL WHERE file_uid = :f"),
                  {"f": world.files["photo.heic"]})
    d = _describe(world)
    assert d["left_out"]["could_not_open"] == 2 and d["left_out"]["not_in_production"] == 2
    assert d["left_out"]["could_not_open_by_reason"] == {"not_image": 1, "cannot_open": 1}


def test_two_index_requests_at_the_same_moment_make_one_job_and_the_second_is_told_why(world):
    """Review finding: two clicks at once made a second job with nothing in it."""
    import threading
    from services.phone import image_search
    first = world.engine.connect()
    tx = first.begin()
    made = image_search.create(first, case_id=world.case, user_id=None)
    out = {}

    def second():
        try:
            with world.engine.begin() as c:
                out["job"] = image_search.create(c, case_id=world.case, user_id=None)
        except Exception as e:  # noqa: BLE001
            out["error"] = e
    t = threading.Thread(target=second)
    t.start()
    t.join(1.0)
    assert t.is_alive()  # the second waits for the first to finish
    tx.commit()
    first.close()
    t.join(30)
    assert made["total"] == 7 and "job" not in out
    assert isinstance(out["error"], image_search.ImageSearchError) and "nothing was queued" in str(out["error"])
    with world.engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM phone_image_index_jobs WHERE case_id = :c"),
                         {"c": world.case}).scalar() == 1


def test_ranking_in_chunks_keeps_the_same_order_as_ranking_all_at_once():
    """Scoring is streamed in chunks with a running top list, so memory is bounded by the chunk; the order, ties
    included (broken by content hash), is the order of scoring everything at once."""
    import numpy as np
    from services.phone import image_search
    rng = np.random.default_rng(7)
    n, dim = 503, 8
    mat = rng.standard_normal((n, dim)).astype("<f4")
    mat /= np.linalg.norm(mat, axis=1, keepdims=True)  # unit vectors, as stored
    qv = rng.standard_normal(dim).astype("<f4")
    qv /= np.linalg.norm(qv)
    mat[300] = mat[100] = mat[7] = qv  # the three best, with equal scores
    shas = ["%064x" % i for i in range(n)]
    exact = np.round(mat.astype(np.float64) @ qv.astype(np.float64), 9)
    whole = [shas[i] for i in np.lexsort((np.arange(n), -exact))[:40]]
    assert whole[:3] == [shas[7], shas[100], shas[300]]  # a tie, in hash order
    for chunk in (1, 2, 37, 1000):
        parts = [(shas[i:i + chunk], mat[i:i + chunk]) for i in range(0, n, chunk)]
        assert image_search.top_k(parts, qv, 40) == whole, chunk
    assert image_search.top_k([], qv, 5) == []


def test_searches_beyond_the_allowed_number_at_once_are_told_to_try_again(world, monkeypatch):
    from services.phone import image_search
    FakeChild(monkeypatch)
    monkeypatch.setattr(image_search, "_SEARCH_SLOTS", threading_semaphore(0))
    monkeypatch.setattr(image_search, "BUSY_WAIT_SECONDS", 0.2)
    with world.engine.connect() as c, pytest.raises(image_search.ImageSearchBusy,
                                                   match="^Another search is running; try again in a moment"):
        image_search.search(c, world.case, "a red square")


def threading_semaphore(n):
    import threading
    return threading.BoundedSemaphore(n) if n else threading.Semaphore(0)


def test_a_failed_draw_of_several_is_drawn_again_one_by_one_so_the_failure_names_its_file(world, monkeypatch):
    from services.phone import image_search
    child = FakeChild(monkeypatch, fail=True)
    _create(world)
    first = image_search.run_pending(world.engine)
    assert sum(1 for g in first if g["state"] == "queued") == 5  # the five read for the model, drawn again
    rest = _drain(world)
    assert len(child.calls) == 6 and all(len(c_["input"]["images"]) == 1 for c_ in child.calls[1:])
    assert {g["reason"] for g in rest} == {"error"}
    with world.engine.connect() as c:
        errors = c.execute(text("SELECT error FROM phone_image_index_items WHERE reason = 'error'")).scalars().all()
    assert len(errors) == 5 and all(e.startswith("This file could not be indexed.") and "Reference:" in e
                                    for e in errors)


def test_the_child_refuses_every_outbound_connection_before_it_loads_anything():
    from services.phone import derive, image_search
    assert image_search._CHILD.startswith(derive.GUARD)
    probe = image_search._CHILD.split("from importlib import metadata")[0] + (
        "\nimport socket\n"
        "for f in (lambda: socket.create_connection(('192.0.2.1', 80), timeout=1),\n"
        "          lambda: socket.socket().connect(('192.0.2.1', 80))):\n"
        "    try:\n        f()\n    except OSError as e:\n        print(e)\n")
    out = subprocess.run([sys.executable, "-I", "-c", probe], capture_output=True, text=True, timeout=60)
    assert out.stdout.count("outbound connections are refused while reading evidence") == 2


def test_the_install_refuses_weights_that_do_not_match_the_pinned_hash(tmp_path):
    from services.phone import image_search_models as M
    asked = []

    def opener(url):
        asked.append(url)
        return io.BytesIO(b"synthetic " + url.encode())
    with pytest.raises(RuntimeError, match="do not match the pinned hash; nothing was installed"):
        M.install(tmp_path, opener=opener)
    assert not (tmp_path / M.MODEL["folder"]).exists()
    assert len(asked) == len(M.FILES)
    assert all(u.startswith("https://huggingface.co/google/siglip2-base-patch16-224/resolve/%s/" % M.MODEL["revision"])
               for u in asked)


_STAND_IN_SERVER = r'''
import json, os, sys
req = json.loads(sys.stdin.readline())
assert req["serve"] and req["mode"] == "text"
print(json.dumps({"ready": True, "pid": os.getpid()}), flush=True)
for line in sys.stdin:
    t = json.loads(line)["text"]
    if t == "stop now":
        sys.stderr.write("synthetic failure\n")
        sys.exit(3)
    if t == "hang":
        import time
        time.sleep(600)
    if t == "partial":
        sys.stdout.write('{"vector": [1.0'); sys.stdout.flush()
        import time
        time.sleep(600)
    if t == "garbage":
        print("not an answer", flush=True)
        continue
    print(json.dumps({"vector": [1.0, 0, 0, 0], "text": t, "pid": os.getpid()}), flush=True)
'''


def test_the_text_model_stays_loaded_between_searches_and_stops_when_idle_or_failed(model, monkeypatch):
    """The kept-warm child: loaded once for several descriptions, stopped after the idle time, started again after
    a failure, which is stated in words."""
    import time
    from services.phone import image_search
    monkeypatch.setattr(image_search, "_CHILD", _STAND_IN_SERVER)
    monkeypatch.setenv("LOUPE_IMAGE_QUERY_IDLE_SECONDS", "1")
    server = image_search._TextServer()
    try:
        a = server.vector("a red square", "w1")
        b = server.vector("a blue circle", "w1")
        assert a["pid"] == b["pid"] and b["text"] == "a blue circle"
        assert server.vector("a red square", "w2")["pid"] != a["pid"]  # other weights: a fresh child
        first = server.proc
        time.sleep(1.5)
        assert server.proc is None and first.poll() is not None  # stopped when idle
        with pytest.raises(image_search.ImageSearchError, match="could not run. Nothing was sent anywhere."):
            server.vector("stop now", "w1")
        assert server.proc is None
        assert server.vector("again", "w1")["text"] == "again"
    finally:
        server._idle()


def test_a_hung_or_garbled_text_child_is_stopped_within_its_deadline_and_said_in_words(model, monkeypatch):
    """Review finding: a child that stopped answering, or wrote half a line, held every search forever; one that
    wrote something other than an answer gave a bare server error."""
    import time
    from services.phone import image_search
    monkeypatch.setattr(image_search, "_CHILD", _STAND_IN_SERVER)
    monkeypatch.setenv("LOUPE_IMAGE_QUERY_IDLE_SECONDS", "60")
    monkeypatch.setattr(image_search, "ANSWER_TIMEOUT_SECONDS", 1)
    server = image_search._TextServer()
    try:
        for value, words in (("hang", "took too long"), ("partial", "took too long"), ("garbage", "could not run")):
            before = server.vector("warm", "w1")["pid"]
            proc = server.proc
            t0 = time.monotonic()
            with pytest.raises(image_search.ImageSearchError, match=words):
                server.vector(value, "w1")
            assert time.monotonic() - t0 < 10
            assert server.proc is None and proc.poll() is not None  # killed and discarded
            assert server.vector("after", "w1")["pid"] != before  # the next search starts a fresh child
    finally:
        server._idle()


def test_a_text_child_that_died_before_the_description_was_sent_is_said_in_words(model, monkeypatch):
    from services.phone import image_search
    monkeypatch.setattr(image_search, "_CHILD", _STAND_IN_SERVER)
    monkeypatch.setenv("LOUPE_IMAGE_QUERY_IDLE_SECONDS", "60")
    server = image_search._TextServer()
    try:
        server.vector("warm", "w1")
        proc = server.proc
        proc.kill()
        proc.wait()
        monkeypatch.setattr(proc, "poll", lambda: None)  # it died between the check and the send
        with pytest.raises(image_search.ImageSearchError, match="stopped. Try the search again"):
            server.vector("a red square", "w1")
        assert server.proc is None
        assert server.vector("again", "w1")["text"] == "again"
    finally:
        server._idle()


def test_a_second_search_waits_a_bounded_time_for_the_text_child_then_is_told_to_try_again(model, monkeypatch):
    import threading
    import time
    from services.phone import image_search
    monkeypatch.setattr(image_search, "_CHILD", _STAND_IN_SERVER)
    monkeypatch.setenv("LOUPE_IMAGE_QUERY_IDLE_SECONDS", "60")
    monkeypatch.setattr(image_search, "ANSWER_TIMEOUT_SECONDS", 3)
    monkeypatch.setattr(image_search, "BUSY_WAIT_SECONDS", 0.3)
    server = image_search._TextServer()
    server.vector("warm", "w1")
    held = threading.Thread(target=lambda: pytest.raises(image_search.ImageSearchError, server.vector, "hang", "w1"))
    held.start()
    time.sleep(0.3)
    try:
        t0 = time.monotonic()
        with pytest.raises(image_search.ImageSearchBusy, match="^Another search is running; try again in a moment"):
            server.vector("a red square", "w1")
        assert time.monotonic() - t0 < 2
    finally:
        held.join(10)
        server._idle()


def test_a_busy_search_is_answered_503_and_a_refusal_422():
    from fastapi import HTTPException
    from routers.phones import _image_search_call
    from services.phone import image_search
    for exc, code in ((image_search.ImageSearchBusy("Another search is running; try again in a moment."), 503),
                      (image_search.ImageSearchError(image_search.NO_MODEL), 422)):
        def boom(e=exc):
            raise e
        with pytest.raises(HTTPException) as got:
            _image_search_call(boom)
        assert got.value.status_code == code and got.value.detail == str(exc)


# ---- the real model ------------------------------------------------------------------------------------------------

def _real_ready():
    from services.phone import image_search_models as M
    if not os.environ.get("LOUPE_IMAGE_MODEL_DIR"):
        return "Set LOUPE_IMAGE_MODEL_DIR to a folder holding the pinned SigLIP 2 model"
    if not M.installed():
        return "The pinned SigLIP 2 model is not installed in LOUPE_IMAGE_MODEL_DIR"
    probe = subprocess.run([sys.executable, "-I", "-c", "import transformers, torch, PIL"], capture_output=True,
                           timeout=300)
    return None if probe.returncode == 0 else "transformers, torch and Pillow are not installed here"


def test_the_real_child_ranks_the_red_square_first_with_the_pinned_model(tmp_path, monkeypatch):
    why = _real_ready()
    if why:
        pytest.skip(why)
    import numpy as np
    from services.phone import image_search
    from services.phone import image_search_models as M
    monkeypatch.setenv("LOUPE_IMAGE_QUERY_IDLE_SECONDS", "60")
    paths = []
    for name, data in (("red", RED), ("blue", BLUE), ("invoice", INVOICE), ("damaged", DAMAGED),
                       ("one-high", _png_size(5, 1)), ("three-high", _png_size(7, 3)), ("one-wide", _png_size(1, 3))):
        (tmp_path / name).write_bytes(data)
        paths.append(str(tmp_path / name))
    got = image_search.run_child({"mode": "image", "images": paths, "draft": image_search.DRAFT_EDGE}, 900)
    # a picture 1 or 3 pixels high or wide is read as height x width x 3, not refused as channels-first
    assert [("vector" in r) for r in got["results"]] == [True, True, True, False, True, True, True], got["results"]
    assert got["results"][3]["reason"] == "cannot_open"
    mat = np.asarray([r["vector"] for r in got["results"][:3]], dtype="<f4")
    assert mat.shape == (3, 768) and np.allclose(np.linalg.norm(mat, axis=1), 1, atol=1e-4)
    ident = image_search.identity()
    assert ident["weights_sha256"] == M.MODEL["weights_sha256"]
    assert ident["model_id"] == "google/siglip2-base-patch16-224@" + M.MODEL["revision"]
    # one child per description, and the kept-warm child, give the same vectors and the same ranking
    one = image_search.run_child({"mode": "text", "text": "a red square", "max_tokens": 64}, 900)
    server = image_search._TextServer()
    try:
        for query, want in (("a red square", 0), ("a blue circle", 1), ("an invoice", 2)):
            q = server.vector(query, ident["weights_sha256"])
            assert len(q["vector"]) == 768 and not q["truncated"]
            assert int(np.argmax(mat @ np.asarray(q["vector"], dtype="<f4"))) == want, query
            if query == "a red square":
                assert np.allclose(q["vector"], one["vector"], atol=1e-5)
    finally:
        server._idle()


def test_the_model_child_is_given_room_for_the_cuda_build_of_torch_and_still_capped(monkeypatch):
    """On this server the CUDA build of torch reserves about 3.2 GB of address space on import and the vision model
    then peaked at 6.43 GB (32 photos) and 6.82 GB (a description); a 6 GB cap left every image unindexed. The child
    gets its own cap above that peak, applies it before loading anything, and the other children's setting does not
    reach it."""
    from services.phone import image_search
    monkeypatch.setenv("LOUPE_PHONE_DERIVE_MEMORY_MB", "6144")
    env = image_search._child_env()
    assert int(env["LOUPE_PHONE_IMAGE_MEMORY_MB"]) >= 7 * 1024 + 512
    assert "LOUPE_PHONE_DERIVE_MEMORY_MB" not in env
    head = image_search._CHILD.split("import torch")[0]
    assert '"LOUPE_PHONE_IMAGE_MEMORY_MB"' in head and "LOUPE_PHONE_DERIVE_MEMORY_MB" not in head and "RLIMIT_AS" in head
    probe = head + "\nimport resource as R\nprint(R.getrlimit(R.RLIMIT_AS)[0] // (1024 * 1024))\n"
    r = subprocess.run([sys.executable, "-I", "-c", probe], input='{"mode": "text"}\n', capture_output=True,
                       text=True, timeout=60, env=env)
    assert r.returncode == 0, r.stderr[-300:]
    assert int(r.stdout.strip().splitlines()[-1]) == int(env["LOUPE_PHONE_IMAGE_MEMORY_MB"])


def test_a_model_failure_is_logged_and_offered_again_and_an_old_unreadable_is_offered_again(world, monkeypatch, caplog):
    """A picture the library opened but the model failed on is "model_error", which another attempt may change; a
    file left out as "unreadable" before 3 Nov (when that code also covered model failures) is offered again too.
    The library's own refusal ("cannot_open") is still not retried."""
    from services.phone import image_search
    child = FakeChild(monkeypatch)
    answer = child.answer

    def model_fails_on_blue(req):
        out = answer(req)
        for p, r in zip(req["images"], out.get("results", [])):
            if open(p, "rb").read() == BLUE:
                r.clear(); r.update(reason="model_error", detail="ValueError: synthetic")
        return out
    child.answer = model_fails_on_blue
    _create(world)
    with caplog.at_level("WARNING", logger="services.phone.image_search"):
        _drain(world)
    f = world.files
    with world.engine.connect() as c:
        rows = {r.file_uid: r for r in c.execute(text(
            "SELECT file_uid::text, state, reason, error FROM phone_image_index_items WHERE case_id = :c"),
            {"c": world.case})}
    assert (rows[f["blue.jpg"]].reason, rows[f["blue.jpg"]].error) == (
        "model_error", "The image search model could not read this picture. The original is unchanged.")
    assert any("ValueError: synthetic" in m for m in caplog.messages)
    d = _describe(world)
    assert d["eligible"] == 1 and d["left_out"]["could_not_open_by_reason"] == {"heic": 1, "not_image": 1,
                                                                              "cannot_open": 1}
    with world.engine.begin() as c:
        c.execute(text("UPDATE phone_image_index_items SET reason = 'unreadable' WHERE case_id = :c AND file_uid = :u"),
                  {"c": world.case, "u": f["damaged.jpg"]})
    d = _describe(world)
    assert d["eligible"] == 2 and d["left_out"]["could_not_open_by_reason"] == {"heic": 1, "not_image": 1}
