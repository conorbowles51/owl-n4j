"""05-S12 (05 section 17.4): a phone file's kind comes from its bytes ahead of its name; only the local provider
runs; machine output names its model by id, version and weights hash.

Before: dispatch was by extension only, so a phone file with no extension (C3 and C9 files carry none) or with
.opus, .amr or .caf was "Unsupported file type", and nothing recorded which weights made a transcript.
Synthetic headers only.
"""
import hashlib
from pathlib import Path

import pytest

from app.pipeline import extract_text as module
from app.pipeline import phone_media as pm
from app.pipeline.extract_text import ExtractedDocument, extract_text

HEADERS = {
    "jpeg": (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00", "image", ".jpg"),
    "png": (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", "image", ".png"),
    "gif": (b"GIF89a\x01\x00\x01\x00", "image", ".gif"),
    "webp": (b"RIFF\x24\x00\x00\x00WEBPVP8 ", "image", ".webp"),
    "heif": (b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00", "image", ".heic"),
    "ogg": (b"OggS\x00\x02" + b"\x00" * 20 + b"OpusHead", "audio", ".ogg"),
    "caf": (b"caff\x00\x01\x00\x00desc", "audio", ".caf"),
    "amr": (b"#!AMR\n\x3c\x48", "audio", ".amr"),
    "amr-wb": (b"#!AMR-WB\n\x04", "audio", ".amr"),
    "wav": (b"RIFF\x24\x00\x00\x00WAVEfmt ", "audio", ".wav"),
    "aiff": (b"FORM\x00\x00\x00\x00AIFFCOMM", "audio", ".aiff"),
    "flac": (b"fLaC\x00\x00\x00\x22", "audio", ".flac"),
    "mp4-audio": (b"\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00", "audio", ".m4a"),
    "mp4": (b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00", "video", ".mp4"),
    "mov": (b"\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00", "video", ".mp4"),
    "3gp": (b"\x00\x00\x00\x18ftyp3gp4\x00\x00\x02\x00", "video", ".3gp"),
    "matroska": (b"\x1aE\xdf\xa3\x9fB\x86\x81\x01", "video", ".mkv"),
    "mp3-id3": (b"ID3\x04\x00\x00\x00\x00\x00\x00", "audio", ".mp3"),
    "mp3-frame": (b"\xff\xfb\x90\x64\x00", "audio", ".mp3"),
    "aac-adts": (b"\xff\xf1\x50\x80\x02\x1f\xfc", "audio", ".aac"),
    "pdf": (b"%PDF-1.7\n", "pdf", ".pdf"),
    "bmp": (b"BM\x36\x00\x0c\x00\x00\x00\x00\x00\x36\x00\x00\x00\x28\x00\x00\x00", "image", ".bmp"),
}


@pytest.mark.parametrize("name", sorted(HEADERS))
def test_kind_comes_from_the_first_bytes(name):
    head, kind, suffix = HEADERS[name]
    got = pm.sniff_bytes(head + b"\x00" * 64)
    assert (got.kind, got.suffix) == (kind, suffix)


def test_bytes_that_name_nothing_are_unrecognised_and_the_name_is_the_fallback(tmp_path):
    for junk in (b"", b"\x00\xff\x10binary", b"plain words in a text file", b"PK\x03\x04zip",
                 b"\xff\xfeh\x00i\x00", b"\xfe\xff\x00h\x00i", b"\xef\xbb\xbfhello",  # text with a byte-order mark
                 b"BM is how these notes begin", b"\xff\xff\xff\xff", b"\xff\xfb\xf0\x00"):  # reserved MPEG values
        assert pm.sniff_bytes(junk) == pm.UNRECOGNISED
    f = tmp_path / "voice.opus"
    f.write_bytes(b"\x00" * 32)
    assert (pm.kind_of(f, f.name).kind, pm.kind_of(f, f.name).container) == ("audio", "by-name")
    g = tmp_path / "noname"
    g.write_bytes(b"\x00" * 32)
    assert not pm.kind_of(g, g.name).recognised


def test_bytes_win_over_a_wrong_name(tmp_path):
    f = tmp_path / "photo.jpg"
    f.write_bytes(HEADERS["ogg"][0] + b"\x00" * 64)
    assert pm.kind_of(f, f.name).kind == "audio"


def test_only_the_local_provider_runs():
    for workload in pm.WORKLOADS:
        assert pm.provider_for(workload) == "local"
        assert pm.provider_for(workload, {workload: "local"}) == "local"
        with pytest.raises(ValueError, match="nothing is sent outside this server"):
            pm.provider_for(workload, {workload: "openai"})
    with pytest.raises(ValueError):
        pm.provider_for("faces")


def test_model_identity_carries_the_weights_hash(tmp_path):
    weights = tmp_path / "base.pt"
    weights.write_bytes(b"synthetic weights " * 1000)
    ident = pm.whisper_identity(weights, "20250625")
    assert ident == {"model": "Whisper", "model_id": "openai-whisper/base", "model_version": "base 20250625",
                     "weights_sha256": hashlib.sha256(weights.read_bytes()).hexdigest(), "provider": "local"}
    weights.write_bytes(b"other weights")  # a changed file is hashed again, never served from the cache
    assert pm.whisper_identity(weights, "20250625")["weights_sha256"] == hashlib.sha256(b"other weights").hexdigest()
    assert pm.tessdata_dir("zz-not-a-language") is None
    tess = tmp_path / "tessdata"
    tess.mkdir()
    (tess / "eng.traineddata").write_bytes(b"eng data")
    (tess / "spa.traineddata").write_bytes(b"spa data")
    one = pm.tesseract_identity("5.3.4", tess, "eng")
    two = pm.tesseract_identity("5.3.4", tess, "eng+spa")
    assert one["model_id"] == "tesseract/eng" and two["model_id"] == "tesseract/eng+spa"
    assert one["weights_sha256"] != two["weights_sha256"] and one["provider"] == "local"
    with pytest.raises(FileNotFoundError):
        pm.tesseract_identity("5.3.4", tess, "fra")


@pytest.fixture
def dispatched(monkeypatch):
    seen = []

    async def image(path, name):
        seen.append("image")
        return ExtractedDocument(text="", metadata={"file_type": "image"})

    async def video(path, name):
        seen.append("video")
        return ExtractedDocument(text="", metadata={"file_type": "video"})

    async def audio(path, progress_callback=None):
        seen.append("audio")
        return ExtractedDocument(text="", metadata={"file_type": "audio"})

    monkeypatch.setattr(module, "_extract_image", image)
    monkeypatch.setattr(module, "_extract_video", video)
    monkeypatch.setattr(module, "_extract_audio", audio)
    return seen


@pytest.mark.asyncio
@pytest.mark.parametrize(("header", "name", "expected"), [
    ("jpeg", "IMG_0001", "image"),          # no extension (C3 and C9)
    ("ogg", "voice-note", "audio"),
    ("ogg", "PTT-2022.opus", "audio"),       # .opus is not in the extension table
    ("amr", "rec.amr", "audio"),
    ("caf", "Audio Message.caf", "audio"),
    ("mov", "clip.mov", "video"),
    ("mp4-audio", "clip.mp4", "audio"),     # an audio-only MP4 goes to audio, not to frame reading
    ("png", "screenshot.jpg", "image"),
    ("mp4", "recording.m4a", "audio"),       # an .m4a with a generic MP4 brand stays audio
    ("3gp", "voice.m4a", "audio"),
])
async def test_engine_dispatches_media_by_its_bytes(tmp_path: Path, dispatched, header, name, expected):
    f = tmp_path / name
    f.write_bytes(HEADERS[header][0] + b"\x00" * 64)
    await extract_text(str(f), name)
    assert dispatched == [expected]


@pytest.mark.asyncio
async def test_engine_keeps_the_extension_when_the_bytes_say_nothing(tmp_path: Path, dispatched):
    f = tmp_path / "old.jpg"
    f.write_bytes(b"\x00" * 64)
    await extract_text(str(f), f.name)
    assert dispatched == ["image"]
    t = tmp_path / "subtitles.srt"
    t.write_bytes(b"\xff\xfe1\x00\n\x00")  # UTF-16 text with an unknown extension is never sent to transcription
    with pytest.raises(ValueError, match=r"Unsupported file type: \.srt"):
        await extract_text(str(t), t.name)
    g = tmp_path / "payload.bin"
    g.write_bytes(b"\x00\xff\x10binary")
    with pytest.raises(ValueError, match=r"Unsupported file type: \.bin"):
        await extract_text(str(g), g.name)
    assert dispatched == ["image"]


@pytest.mark.asyncio
async def test_documents_and_text_are_never_sniffed(tmp_path: Path, dispatched):
    f = tmp_path / "notes.txt"
    f.write_bytes(b"ID3 is the start of these notes, not an mp3")
    doc = await extract_text(str(f), f.name)
    assert doc.metadata["file_type"] == "text" and dispatched == []
