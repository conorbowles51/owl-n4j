"""Phone media entry point (05 section 17.4, unit 05-S12): what a phone file really is, and which local model reads it.

Phone files often carry no name extension (C3 and C9 file elements have none) or one the extension table does not
know (`.opus`, `.amr`, `.caf`, `.3gp`). So the kind of a phone file is taken from its first bytes (magic numbers)
ahead of any extension, and the extension is used only when the bytes say nothing.

Every workload has a provider. The default for every workload is ``local``: the work runs on this server and no
byte of the file leaves it (plan standing decision 8). A third-party provider is never chosen here; it would need
a per-case setting recorded with who decided and when (17.4 point 3), and no such setting exists for derivation.

Machine output names the model that made it: a model id, the implementation's version, and the SHA-256 of the
weights or language data it ran with (``model_identity``), plus the SHA-256 of the input bytes.

Standard library only: the backend (which runs the local models in an isolated child process) and the engine
(which dispatches uploaded files by kind) both load this module.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

LOCAL = "local"
PROVIDER_WORDS = {LOCAL: "Made on this server. Nothing was sent to any outside service."}
WORKLOADS = ("ocr", "transcript", "translation", "image_search")


@dataclass(frozen=True)
class Sniffed:
    kind: str | None      # "image", "audio", "video", "pdf" or None when the bytes are not recognised
    container: str        # e.g. "jpeg", "ogg", "mp4", "caf", "amr"; "unrecognised" when unknown
    suffix: str           # a file name extension that names the container for tools that look at names

    @property
    def recognised(self) -> bool:
        return self.kind is not None


UNRECOGNISED = Sniffed(None, "unrecognised", "")

# ISO base media (ftyp) brands that are audio only; every other ftyp brand is treated as video, and the reader
# checks the streams themselves (a video with only an audio track is still transcribed).
_AUDIO_BRANDS = {b"M4A ", b"M4B ", b"M4P ", b"F4A ", b"F4B "}
_HEIC_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1", b"heim", b"heis", b"avic", b"avif"}
HEAD_BYTES = 64


def sniff_bytes(head: bytes) -> Sniffed:
    """The file's kind from its first bytes. ``head`` should be at least ``HEAD_BYTES`` long when the file is."""
    h = head or b""
    if h[:3] == b"\xff\xd8\xff":
        return Sniffed("image", "jpeg", ".jpg")
    if h[:8] == b"\x89PNG\r\n\x1a\n":
        return Sniffed("image", "png", ".png")
    if h[:6] in (b"GIF87a", b"GIF89a"):
        return Sniffed("image", "gif", ".gif")
    if h[:4] == b"RIFF" and h[8:12] == b"WEBP":
        return Sniffed("image", "webp", ".webp")
    if h[:2] in (b"\xff\xfe", b"\xfe\xff") or h[:3] == b"\xef\xbb\xbf":
        return UNRECOGNISED  # a UTF-16 or UTF-8 byte-order mark: text, never audio (FF FE also fits MPEG frame sync)
    if h[:2] == b"BM" and len(h) >= 18 and h[6:10] == b"\x00\x00\x00\x00" and \
            int.from_bytes(h[14:18], "little") in (12, 40, 52, 56, 64, 108, 124):
        return Sniffed("image", "bmp", ".bmp")
    if h[:4] in (b"II*\x00", b"MM\x00*"):
        return Sniffed("image", "tiff", ".tif")
    if h[:5] == b"%PDF-":
        return Sniffed("pdf", "pdf", ".pdf")
    if h[:4] == b"OggS":
        return Sniffed("audio", "ogg", ".ogg")
    if h[:4] == b"caff":
        return Sniffed("audio", "caf", ".caf")
    if h[:9] == b"#!AMR-WB\n":
        return Sniffed("audio", "amr-wb", ".amr")
    if h[:6] == b"#!AMR\n":
        return Sniffed("audio", "amr", ".amr")
    if h[:4] == b"RIFF" and h[8:12] == b"WAVE":
        return Sniffed("audio", "wav", ".wav")
    if h[:4] == b"RIFF" and h[8:12] == b"AVI ":
        return Sniffed("video", "avi", ".avi")
    if h[:4] == b"FORM" and h[8:12] in (b"AIFF", b"AIFC"):
        return Sniffed("audio", "aiff", ".aiff")
    if h[:4] == b"fLaC":
        return Sniffed("audio", "flac", ".flac")
    if h[4:8] == b"ftyp":
        brand = h[8:12]
        if brand in _HEIC_BRANDS:
            return Sniffed("image", "heif", ".heic")
        if brand in _AUDIO_BRANDS:
            return Sniffed("audio", "mp4", ".m4a")
        if brand[:3] == b"3gp" or brand[:3] == b"3g2":
            return Sniffed("video", "3gp", ".3gp")
        return Sniffed("video", "mp4", ".mp4")
    if h[:4] == b"\x1aE\xdf\xa3":
        return Sniffed("video", "matroska", ".mkv")
    if h[:3] == b"ID3":
        return Sniffed("audio", "mp3", ".mp3")
    if len(h) >= 2 and h[0] == 0xFF and (h[1] & 0xF6) == 0xF0:
        return Sniffed("audio", "aac", ".aac")       # ADTS: sync 0xFFF, layer 00
    if _mpeg_audio_frame(h):
        return Sniffed("audio", "mp3", ".mp3")
    if h[:4] == b"\x00\x00\x01\xba" or h[:4] == b"\x00\x00\x01\xb3":
        return Sniffed("video", "mpeg", ".mpg")
    # MPEG-TS (a 0x47 byte every 188) needs more than HEAD_BYTES to tell apart from text; ffprobe decides it.
    return UNRECOGNISED


def _mpeg_audio_frame(h: bytes) -> bool:
    """An MPEG audio frame header: 11 sync bits, then no reserved version, layer, bitrate or sample-rate value."""
    if len(h) < 3 or h[0] != 0xFF or (h[1] & 0xE0) != 0xE0:
        return False
    version, layer = (h[1] >> 3) & 3, (h[1] >> 1) & 3
    bitrate, rate = h[2] >> 4, (h[2] >> 2) & 3
    return version != 1 and layer != 0 and bitrate != 0xF and rate != 3


def sniff_path(path) -> Sniffed:
    with open(path, "rb") as f:
        return sniff_bytes(f.read(HEAD_BYTES))


_BY_SUFFIX = {
    **{s: "image" for s in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".heif")},
    **{s: "audio" for s in (".mp3", ".m4a", ".wav", ".ogg", ".oga", ".opus", ".flac", ".amr", ".aac", ".caf",
                             ".aif", ".aiff", ".mpga", ".mpeg")},
    **{s: "video" for s in (".mp4", ".mov", ".m4v", ".3gp", ".3g2", ".mkv", ".webm", ".avi", ".mpg", ".ts")},
    ".pdf": "pdf",
}


def kind_of(path, name: str | None = None) -> Sniffed:
    """Sniff first; fall back to the name's extension only when the bytes are not recognised."""
    s = sniff_path(path)
    if s.recognised:
        return s
    suffix = Path(name or str(path)).suffix.lower()
    kind = _BY_SUFFIX.get(suffix)
    return Sniffed(kind, "by-name" if kind else "unrecognised", suffix if kind else "")


def provider_for(workload: str, case_setting: dict | None = None) -> str:
    """The provider for one workload in one case. Always ``local``: a third-party provider needs a recorded
    per-case setting (17.4 point 3), which derivation does not offer. ``case_setting`` is accepted so a later
    setting has one place to land; any value other than local is refused rather than silently used."""
    if workload not in WORKLOADS:
        raise ValueError("Unknown workload: %s" % workload)
    chosen = (case_setting or {}).get(workload) or LOCAL
    if chosen != LOCAL:
        raise ValueError("Only the local provider is available for %s; nothing is sent outside this server."
                         % workload)
    return LOCAL


def sha256_file(path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


_IDENTITY_CACHE: dict = {}


def weights_sha256(path) -> str:
    """SHA-256 of a weights or language-data file, cached by (path, size, mtime) so a 140 MB model is hashed once
    per process and again only when the file changes."""
    p = Path(path)
    st = p.stat()
    key = (str(p.resolve()), st.st_size, st.st_mtime_ns)
    got = _IDENTITY_CACHE.get(key)
    if got is None:
        got = sha256_file(p)
        _IDENTITY_CACHE[key] = got
    return got


def whisper_identity(model_path, package_version: str | None) -> dict:
    """Model id, version and weights hash for a local Whisper checkpoint (e.g. ``base.pt``)."""
    name = Path(model_path).stem
    return {"model": "Whisper", "model_id": "openai-whisper/%s" % name,
            "model_version": ("%s %s" % (name, package_version or "")).strip(),
            "weights_sha256": weights_sha256(model_path), "provider": LOCAL}


def tesseract_identity(version: str | None, tessdata_dir, languages: str) -> dict:
    """Tesseract's version, and one hash over the language data files it reads (in the order given)."""
    h = hashlib.sha256()
    for lang in languages.split("+"):
        f = Path(tessdata_dir) / ("%s.traineddata" % lang)
        h.update(lang.encode() + b"\0" + weights_sha256(f).encode() + b"\0")
    return {"model": "Tesseract", "model_id": "tesseract/%s" % languages, "model_version": version or "",
            "weights_sha256": h.hexdigest(), "provider": LOCAL}


def tessdata_dir(languages: str = "eng") -> str | None:
    """A folder holding the language data for every language asked for. The caller passes it to Tesseract
    (``--tessdata-dir``), so the hashed files are the files read."""
    env = os.environ.get("TESSDATA_PREFIX")
    candidates = ([env, os.path.join(env, "tessdata")] if env else []) + [
        "/usr/share/tesseract-ocr/5/tessdata", "/usr/share/tesseract-ocr/4.00/tessdata", "/usr/share/tessdata"]
    for c in candidates:
        if c and all(Path(c, "%s.traineddata" % lang).is_file() for lang in languages.split("+")):
            return c
    return None
