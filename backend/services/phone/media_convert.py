"""A converted copy of a phone file the browsers cannot play (03 8.3; measured in 03 20.5).

Chromium and Firefox play none of CAF, AMR, AIFF, MPEG-TS and ALAC, give sound with no picture for H.263 and MPEG-4
Part 2, and no picture for HEVC in Chromium (docs/cellebrite/measurements/a3/browser-playback). For such a file the
viewer asks for a converted copy: H.264 video with AAC sound in MP4, or AAC sound in M4A, made on demand with ffmpeg
and kept beside the case's files under ``<case>/_converted/``. The original is never changed, moved or replaced; the
copy is only for watching or listening, and the viewer says so. A stream that is already H.264 or AAC is copied as
it is, not re-encoded.
"""
from __future__ import annotations

import fcntl
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

CONVERT_TIMEOUT_S = 300
FOLDER = "_converted"
WORDS = "Playing a converted copy. The original file is unchanged."


class NotConvertible(LookupError):
    pass


def _ffmpeg():
    from config import FFMPEG_CMD
    exe = shutil.which(FFMPEG_CMD) or shutil.which("ffmpeg")
    if not exe:
        raise NotConvertible("No converted copy can be made on this server (ffmpeg is not installed).")
    return exe


def _ffprobe(ffmpeg):
    probe = shutil.which(os.path.join(os.path.dirname(ffmpeg), "ffprobe")) or shutil.which("ffprobe")
    if not probe:
        raise NotConvertible("No converted copy can be made on this server (ffprobe is not installed).")
    return probe


def _streams(probe, src):
    p = subprocess.run([probe, "-v", "error", "-show_entries", "stream=codec_type,codec_name,pix_fmt", "-of",
                        "json", str(src)], capture_output=True, text=True, timeout=60)
    try:
        streams = json.loads(p.stdout or "{}").get("streams", [])
    except ValueError:
        streams = []
    # a cover picture in an audio file is a "video" stream of an image codec: it is not a picture to play
    video = [s for s in streams if s.get("codec_type") == "video" and s.get("codec_name") not in (
        "mjpeg", "png", "bmp", "gif")]
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    return video, audio


def plan(video, audio):
    """``(suffix, media_type, ffmpeg output arguments)`` for a file with these streams."""
    a = []
    if audio:
        a = ["-map", "0:a:0", "-c:a"] + (["copy"] if audio[0].get("codec_name") == "aac" else ["aac", "-b:a", "128k"])
    if video:
        v = video[0]
        copy = v.get("codec_name") == "h264" and v.get("pix_fmt") in ("yuv420p", "yuvj420p")
        vargs = ["-map", "0:v:0", "-c:v"] + (["copy"] if copy else [
            "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2"])
        return ".mp4", "video/mp4", vargs + a + ["-movflags", "+faststart", "-f", "mp4"]
    if audio:
        return ".m4a", "audio/mp4", a + ["-vn", "-movflags", "+faststart", "-f", "mp4"]
    raise NotConvertible("No converted copy can be made: no sound or picture was found in this file.")


def converted(case_dir: Path, file_uid, size: int, opener):
    """``(path, media_type)`` of the converted copy of one phone file, made now if it is not there yet. Two
    requests for the same file make it once (a lock file); a failed conversion leaves nothing behind."""
    ffmpeg = _ffmpeg()
    probe = _ffprobe(ffmpeg)
    out_dir = Path(case_dir) / FOLDER
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = "%s.%d" % (file_uid, int(size))
    for suffix, kind in ((".mp4", "video/mp4"), (".m4a", "audio/mp4")):
        if (out_dir / (stem + suffix)).is_file():
            return out_dir / (stem + suffix), kind
    with open(out_dir / (stem + ".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for suffix, kind in ((".mp4", "video/mp4"), (".m4a", "audio/mp4")):
            if (out_dir / (stem + suffix)).is_file():  # made by another request while this one waited
                return out_dir / (stem + suffix), kind
        work = Path(tempfile.mkdtemp(prefix=stem + ".", dir=out_dir))
        try:
            src = work / "source"
            with opener() as fh, open(src, "wb") as dst:  # the source is read, never written
                shutil.copyfileobj(fh, dst, 1024 * 1024)
            video, audio = _streams(probe, src)
            suffix, kind, args = plan(video, audio)
            tmp = work / ("out" + suffix)
            cmd = [ffmpeg, "-nostdin", "-v", "error", "-y", "-threads", "2", "-i", str(src)] + args + [str(tmp)]
            if shutil.which("nice"):
                cmd = ["nice", "-n", "10"] + cmd  # the app stays responsive while a copy is made
            try:
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=CONVERT_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                raise NotConvertible("Making a converted copy took longer than %d seconds and was stopped."
                                     % CONVERT_TIMEOUT_S) from None
            if p.returncode or not tmp.is_file() or tmp.stat().st_size == 0:
                raise NotConvertible("No converted copy could be made of this file: %s"
                                     % ((p.stderr or "").strip().splitlines() or ["ffmpeg failed"])[-1][:200])
            final = out_dir / (stem + suffix)
            os.replace(tmp, final)
            return final, kind
        finally:
            shutil.rmtree(work, ignore_errors=True)
