#!/usr/bin/env python3
"""Encode the raw site films (journeys/site-films.mjs) into the files the public site uses (lx-sitefilms C, D).

    python3 journeys/site-films-encode.py <raw dir> <out dir> [film ...]

Per film: keeps only the recorded segments (loading frames are cut), crops 1440x900 to 16:9 (1440x810, 45 px off top
and bottom), and writes <film>.mp4 (H.264, yuv420p, CRF 26, faststart, no audio), <film>.webm (VP9, CRF 36, no audio),
<film>-poster.webp (the frame the script marked as the film's point) and three check frames at 10, 50 and 90 % in
<out>/check/. An mp4 of 4 MB or more is encoded again at a higher CRF until it is under 4 MB.

Every quarter second of the finished film is read with tesseract (when installed); a frame showing loading, error or
sign-in text is listed under "flagged" and printed. A film with flagged frames fails the check (lx-sitefilms D).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

LIMIT = 4 * 1024 * 1024
# Text that must never be on screen in a site film.
BAD = re.compile(r"Loading|Reading the theory|could not be loaded|failed|went wrong|Cannot check sign-in|Sign in to|"
                 r"No data yet|Try again", re.I)


def scan(mp4):
    """Times (s) and lines of quarter-second frames whose OCR text matches BAD; None when tesseract is missing."""
    if not shutil.which("tesseract"):
        return None
    hits = []
    with tempfile.TemporaryDirectory(dir=os.path.dirname(mp4)) as tmp:
        run(["ffmpeg", "-loglevel", "error", "-i", mp4, "-vf", "fps=4", os.path.join(tmp, "f%04d.png")])
        names = sorted(os.listdir(tmp))
        # One thread per tesseract: its default OpenMP threads take ~50 s a frame on a loaded box, one takes ~2 s.
        env = {**os.environ, "OMP_THREAD_LIMIT": "1"}

        def read(name):
            return subprocess.run(["tesseract", os.path.join(tmp, name), "-", "--psm", "11"],
                                  capture_output=True, text=True, env=env).stdout

        with ThreadPoolExecutor(3) as pool:
            for name, text in zip(names, pool.map(read, names)):
                for line in text.splitlines():
                    if BAD.search(line):
                        hits.append([round((int(name[1:5]) - 1) / 4, 2), line.strip()[:80]])
    return hits


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         check=True, capture_output=True, text=True).stdout.strip()
    return float(out)


def encode(raw, out, name):
    meta = json.load(open(os.path.join(raw, f"{name}.json")))
    src = os.path.join(raw, f"{name}.webm")
    segs = [s for s in meta["segments"] if s[1] - s[0] > 0.2]
    if not segs:
        raise SystemExit(f"{name}: no kept segments")
    parts = "".join(f"[0:v]trim={a}:{b},setpts=PTS-STARTPTS[s{i}];" for i, (a, b) in enumerate(segs))
    joined = "".join(f"[s{i}]" for i in range(len(segs)))
    graph = f"{parts}{joined}concat=n={len(segs)}:v=1:a=0,crop=1440:810:0:45,fps=25,format=yuv420p[v]"
    mp4 = os.path.join(out, f"{name}.mp4")
    webm = os.path.join(out, f"{name}.webm")
    for crf in (26, 28, 30, 32):
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-filter_complex", graph, "-map", "[v]", "-an",
             "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart", mp4])
        if os.path.getsize(mp4) < LIMIT:
            break
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp4, "-an", "-c:v", "libvpx-vp9", "-crf", "36", "-b:v", "0",
         "-row-mt", "1", "-deadline", "good", "-cpu-used", "4", webm])
    # The poster: the marked moment, moved into the cut film's time.
    kept_before, at = 0.0, None
    for a, b in segs:
        if meta.get("poster") is not None and a <= meta["poster"] <= b:
            at = kept_before + meta["poster"] - a
        kept_before += b - a
    total = duration(mp4)
    at = min(at if at is not None else total * 0.6, total - 0.1)
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{at:.2f}", "-i", mp4, "-frames:v", "1", "-c:v", "libwebp",
         "-quality", "85", os.path.join(out, f"{name}-poster.webp")])
    check = os.path.join(out, "check")
    os.makedirs(check, exist_ok=True)
    for pct in (10, 50, 90):
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{total * pct / 100:.2f}", "-i", mp4, "-frames:v", "1",
             os.path.join(check, f"{name}-{pct}.png")])
    return {"film": name, "duration_s": round(total, 1), "mp4_bytes": os.path.getsize(mp4),
            "webm_bytes": os.path.getsize(webm), "poster_s": round(at, 1), "segments": segs, "flagged": scan(mp4)}


def main():
    raw, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    names = sys.argv[3:] or sorted(f[:-5] for f in os.listdir(raw) if f.endswith(".json") and not f.startswith("r"))
    rows = [encode(raw, out, n) for n in names]
    for r in rows:
        print(f"{r['film']:16} {r['duration_s']:5.1f} s  mp4 {r['mp4_bytes'] / 1048576:.2f} MB  webm {r['webm_bytes'] / 1048576:.2f} MB  poster at {r['poster_s']} s")
        if r["flagged"] is None:
            print("    text scan skipped: tesseract is not installed")
        for t, line in r["flagged"] or []:
            print(f"    FLAGGED at {t:5.2f} s: {line}")
    with open(os.path.join(out, "encode.json"), "a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main()
