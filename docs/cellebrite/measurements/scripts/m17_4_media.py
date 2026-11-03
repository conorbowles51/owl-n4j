"""M-17.4 (05 section 17.4 gate): per phone, audio files by sniffed type and total duration; images in screenshot paths.

Read-only over the server corpus. Writes counts and seconds only (no names, paths or hashes) to <out>/<label>.json,
plus a private sample list of voice notes for the transcription speed measurement (item B) to <out>/<label>.sample,
mode 600, never committed.

Usage (one report at a time, memory-capped, lowest priority):
  systemd-run --scope -p MemoryMax=2G nice -n 19 ionice -c3 python3 -I m17_4_media.py corpus.json out_dir P01,P02,...

Definitions:
- audio: a tagged file whose Tags is "Audio";
- sniffed type: the container from the file's first bytes (magic numbers), not its name;
- duration: ffprobe format duration in seconds; files ffprobe cannot time are counted under "no duration";
- messaging path: the file's original path names a messaging app or voice-message folder (VOICE_PATH_RE). This is
  the voice-note subset; "all audio" is an upper bound that also holds ringtones, music and recordings;
- screenshot path: the image's original or local path contains "screenshot".
"""
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter

VOICE_PATH_RE = re.compile(r"whatsapp|telegram|signal|viber|messenger|wechat|snapchat|instagram|voice|ptt|"
                           r"audio ?message|recordings|kakao|line/|imo|botim", re.I)
SCREENSHOT_RE = re.compile(r"screen ?shot", re.I)


def ln(t):
    return t.rsplit("}", 1)[-1]


def sniff(head):
    """Container from magic bytes; mirrors the production sniffer's names (evidence-engine phone_media)."""
    if head[:4] == b"OggS":
        return "ogg"
    if head[:4] == b"caff":
        return "caf"
    if head[:6] == b"#!AMR\n":
        return "amr"
    if head[:9] == b"#!AMR-WB\n":
        return "amr-wb"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if head[:4] == b"FORM" and head[8:12] in (b"AIFF", b"AIFC"):
        return "aiff"
    if head[:4] == b"fLaC":
        return "flac"
    if head[4:8] == b"ftyp":
        return "mp4"
    if head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "mp3-or-adts"
    if head[:4] == b"\x1aE\xdf\xa3":
        return "matroska"
    return "unrecognised"


def probe(path):
    try:
        p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
                           capture_output=True, text=True, timeout=30)
        d = (json.loads(p.stdout or "{}").get("format") or {}).get("duration")
        return float(d) if d not in (None, "N/A") else None
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return None


def run(label, spec, out_dir):
    root = spec["root"]
    xml = os.path.join(root, spec["report"])
    c = Counter()
    secs = Counter()
    sample = []
    t0 = time.monotonic()
    stack = []
    els = []
    with open(xml, "rb") as fh:
        for ev, el in ET.iterparse(fh, events=("start", "end")):
            tag = ln(el.tag)
            if ev == "start":
                stack.append(tag)
                els.append(el)
                continue
            stack.pop()
            els.pop()
            parent = stack[-1] if stack else None
            if tag == "file" and parent == "taggedFiles":
                items = {}
                for md in el:
                    if ln(md.tag) == "metadata":
                        for it in md:
                            if ln(it.tag) == "item":
                                items[it.get("name")] = (it.text or "").strip()
                cat = items.get("Tags") or ""
                lp = (items.get("Local Path") or "").replace("\\", "/")
                orig = el.get("path") or ""
                if cat == "Image" and (SCREENSHOT_RE.search(orig) or SCREENSHOT_RE.search(lp)):
                    c["images in screenshot paths"] += 1
                if cat == "Audio":
                    voice = bool(VOICE_PATH_RE.search(orig) or VOICE_PATH_RE.search(lp))
                    full = os.path.join(root, lp) if lp else ""
                    if not lp or not os.path.isfile(full):
                        c["audio not on disk"] += 1
                    else:
                        with open(full, "rb") as f:
                            kind = sniff(f.read(16))
                        dur = probe(full)
                        c["audio | " + kind] += 1
                        c["audio on disk"] += 1
                        if dur is None:
                            c["audio no duration"] += 1
                        else:
                            secs["all audio"] += dur
                            secs["audio | " + kind] += dur
                        if voice:
                            c["voice-path audio on disk"] += 1
                            if dur is not None:
                                secs["voice-path audio"] += dur
                                if kind in ("ogg", "amr", "mp4", "caf") and 2 <= dur <= 300:
                                    sample.append((dur, full, kind))
                el.clear()
                if els:
                    els[-1].remove(el)
            elif tag in ("modelType", "decodedData", "extraInfos", "carvedFiles", "infectedFiles"):
                el.clear()
            elif parent in ("modelType", "decodedData", "extraInfos", "carvedFiles", "infectedFiles"):
                el.clear()
                if els:
                    els[-1].remove(el)
    out = {"label": label, "case": spec.get("case"), "counts": dict(sorted(c.items())),
           "seconds": {k: round(v, 1) for k, v in sorted(secs.items())},
           "hours": {k: round(v / 3600, 2) for k, v in sorted(secs.items())},
           "elapsed_s": round(time.monotonic() - t0, 1)}
    with open(os.path.join(out_dir, label + ".json"), "w") as f:
        json.dump(out, f, indent=1)
    fd = os.open(os.path.join(out_dir, label + ".sample"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        for dur, full, kind in sample:
            f.write("%s\t%.2f\t%s\n" % (kind, dur, full))
    print(json.dumps({"label": label, "counts": out["counts"], "hours": out["hours"], "elapsed_s": out["elapsed_s"]}),
          flush=True)


def main(argv):
    corpus = json.load(open(argv[0], encoding="utf-8"))
    for label in argv[2].split(","):
        run(label, corpus[label], argv[1])
    print("M17-4-DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
