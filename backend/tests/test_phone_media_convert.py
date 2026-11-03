"""A converted copy of phone media the browsers cannot play (03 8.3; groups measured in 03 20.5).

Samples are made here by ffmpeg from its test sources (no case material). The case check and the phone's file
lookup are faked; the route, the conversion and the zip member read are real."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import zipfile
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from routers import phones
from services.phone import media_convert

FF = shutil.which("ffmpeg") and shutil.which("ffprobe")
needs_ffmpeg = pytest.mark.skipif(not FF, reason="needs ffmpeg and ffprobe")

VIDEO = ["-f", "lavfi", "-i", "testsrc=size=176x144:rate=10:duration=2", "-f", "lavfi", "-i",
         "sine=frequency=440:duration=2"]
AUDIO = ["-f", "lavfi", "-i", "sine=frequency=440:duration=2"]
SAMPLES = {  # the groups neither measured browser plays, with picture where there is one
    "clip.ts": VIDEO + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-f", "mpegts"],
    "clip.3gp": VIDEO + ["-c:v", "h263", "-c:a", "aac", "-ar", "8000", "-ac", "1"],
    "clip.m4v": VIDEO + ["-c:v", "mpeg4", "-c:a", "aac", "-f", "mp4"],
    "voice.caf": AUDIO + ["-c:a", "pcm_s16le", "-f", "caf"],
    "voice.aiff": AUDIO + ["-c:a", "pcm_s16be", "-f", "aiff"],
}


def _make(tmp_path, name):
    path = tmp_path / name
    if name == "voice.amr":  # ffmpeg has no AMR-NB encoder here: RFC 4867 storage format, 150 mode-0 frames
        path.write_bytes(b"#!AMR\n" + (bytes([0x04]) + bytes(12)) * 150)
        return path
    p = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y"] + SAMPLES[name] + [str(path)],
                       capture_output=True, text=True)
    if p.returncode:
        pytest.skip("this ffmpeg cannot make %s: %s" % (name, p.stderr[-200:]))
    return path


def _probe(path):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width", "-of",
                        "json", str(path)], capture_output=True, text=True)
    return {s["codec_type"]: s for s in json.loads(p.stdout)["streams"]}


def _body(response):
    import asyncio

    async def collect():
        out = b""
        async for block in response.body_iterator:
            out += block
        return out
    return asyncio.run(collect())


def _converted(case_root, name, opener, size, range_header=None):
    with patch.object(phones, "authorize_case"), patch("config.EVIDENCE_DATA_ROOT", str(case_root)), \
            patch("services.phone.media.content", return_value=(name, size, opener)):
        return phones.phone_media_converted(FILE, CASE, SimpleNamespace(connection=lambda: None),
                                            SimpleNamespace(), range_header)


FILE = uuid4()
CASE = uuid4()


@needs_ffmpeg
@pytest.mark.parametrize("name", sorted(SAMPLES) + ["voice.amr"])
def test_unplayable_groups_get_an_h264_aac_copy_and_the_original_is_unchanged(tmp_path, name):
    src = _make(tmp_path, name)
    before = hashlib.sha256(src.read_bytes()).hexdigest()
    root = tmp_path / "evidence-data"
    r = _converted(root, name, lambda: open(src, "rb"), src.stat().st_size)
    assert r.status_code == 200 and r.headers["x-converted-copy"] == "1"
    out = tmp_path / ("out" + (".mp4" if r.media_type == "video/mp4" else ".m4a"))
    out.write_bytes(_body(r))
    streams = _probe(out)
    assert streams["audio"]["codec_name"] == "aac"
    if name.startswith("clip"):
        assert r.media_type == "video/mp4"
        assert streams["video"]["codec_name"] == "h264" and streams["video"]["width"] == 176
    else:
        assert r.media_type == "audio/mp4" and "video" not in streams
    assert hashlib.sha256(src.read_bytes()).hexdigest() == before
    kept = list((root / str(CASE) / media_convert.FOLDER).iterdir())
    assert [p.suffix for p in kept if p.suffix != ".lock"] == [out.suffix]  # no work files left behind


@needs_ffmpeg
def test_a_zip_member_is_converted_once_and_the_copy_answers_ranges(tmp_path):
    src = _make(tmp_path, "clip.ts")
    zpath = tmp_path / "production.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.write(src, "files/clip.ts")

    def opener():
        return zipfile.ZipFile(zpath).open("files/clip.ts")
    root = tmp_path / "evidence-data"
    whole = _body(_converted(root, "clip.ts", opener, src.stat().st_size))
    copy = next((root / str(CASE) / media_convert.FOLDER).glob("*.mp4"))
    made = copy.stat().st_mtime_ns
    r = _converted(root, "clip.ts", lambda: pytest.fail("the source was read again"), src.stat().st_size,
                   "bytes=100-199")
    assert r.status_code == 206 and _body(r) == whole[100:200]
    assert copy.stat().st_mtime_ns == made


@needs_ffmpeg
def test_a_file_with_no_sound_or_picture_is_refused_with_words(tmp_path):
    src = tmp_path / "notes.ts"
    src.write_bytes(b"not media at all" * 100)
    root = tmp_path / "evidence-data"
    with pytest.raises(phones.HTTPException) as e:
        _converted(root, "notes.ts", lambda: open(src, "rb"), src.stat().st_size)
    assert e.value.status_code == 422 and "converted copy" in e.value.detail
    left = [p for p in (root / str(CASE) / media_convert.FOLDER).iterdir() if p.suffix != ".lock"]
    assert left == []


def test_an_h264_aac_source_is_copied_not_reencoded():
    _s, kind, args = media_convert.plan([{"codec_name": "h264", "pix_fmt": "yuv420p"}], [{"codec_name": "aac"}])
    assert kind == "video/mp4" and args[args.index("-c:v") + 1] == "copy" and args[args.index("-c:a") + 1] == "copy"
    _s, kind, args = media_convert.plan([{"codec_name": "hevc", "pix_fmt": "yuv420p10le"}], [{"codec_name": "amr_nb"}])
    assert args[args.index("-c:v") + 1] == "libx264" and args[args.index("-c:a") + 1] == "aac"


@pytest.mark.parametrize("name,kind", [("clip.ts", "video/mp2t"), ("voice.amr", "audio/amr"),
                                       ("voice.caf", "audio/x-caf"), ("clip.3gp", "video/3gpp"),
                                       ("voice.aiff", "audio/aiff"), ("CLIP.TS", "video/mp2t")])
def test_phone_media_types_are_sent_inline_as_media(tmp_path, name, kind):
    path = tmp_path / "f"
    path.write_bytes(b"\0" * 64)
    with patch.object(phones, "authorize_case"), \
            patch("services.phone.media.content", return_value=(name, 64, lambda: open(path, "rb"))):
        r = phones.phone_media_content(uuid4(), uuid4(), SimpleNamespace(connection=lambda: None),
                                       SimpleNamespace(), None)
    assert r.media_type == kind
    assert r.headers["content-disposition"].startswith("inline")
