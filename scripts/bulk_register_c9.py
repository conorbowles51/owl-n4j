"""One-shot bulk registration of the C9 cellebrite report from on-disk files.

Context (2026-05-25 evening): the C9 folder upload (29,107 files) was registering
through the per-100-file evidence.json rewrite path at ~2.4 files/s (~2.3h ETA)
because evidence.json has grown to ~1GB and is fully rewritten every batch. All
C9 files are already on disk (consolidated into the case dir from _staging), so
this replaces the grind with the proven bulk_register_reports.py pattern: hash
all files (no lock), then a SINGLE evidence_storage._file_locked() write that
(a) drops the partial rows already registered for C9 and (b) inserts fresh rows
for every on-disk file. Same fcntl-locked / reload-before-save / atomic store.

Run as conorbowles51 so evidence.json stays conorbowles51-owned:
  sudo -u conorbowles51 venv/bin/python scripts/bulk_register_c9.py
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "backend"))

from services.evidence_storage import evidence_storage, EVIDENCE_ROOT_DIR  # noqa: E402

CASE_ID = "43f1afb1-1d2b-4b3f-a832-19cd049c8a9e"
OWNER = "oferreira@owlconsultancygroup.com"
REPORTS = [
    "220029502_06310028_C9_2023-03-02_Report",
]

case_dir = EVIDENCE_ROOT_DIR / CASE_ID


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def top_seg(r: dict) -> str | None:
    rel = r.get("relative_path")
    if rel:
        return rel.split("/")[0]
    sp = r.get("stored_path") or ""
    marker = f"{CASE_ID}/"
    if marker in sp:
        return sp.split(marker, 1)[1].split("/")[0]
    return None


# --- Pass 1: enumerate + hash (no lock) ---
print("Enumerating files in C9 report folder...")
all_files: list[Path] = []
per_report_count: dict[str, int] = {}
for rep in REPORTS:
    folder = case_dir / rep
    if not folder.exists():
        print(f"  ERR: missing {folder}")
        sys.exit(1)
    n = 0
    for root, _dirs, files in os.walk(folder):
        for f in files:
            all_files.append(Path(root) / f)
            n += 1
    per_report_count[rep] = n
    print(f"  {rep}: {n} files")
print(f"Total files to register: {len(all_files)}")

print("Hashing...")
start = time.time()
hashed: list[tuple[Path, int, str]] = []
report_every = max(1, len(all_files) // 20)
for idx, path in enumerate(all_files, 1):
    try:
        size = path.stat().st_size
        sha = sha256_of(path)
    except OSError as e:
        print(f"  skip (read err): {path}: {e}")
        continue
    hashed.append((path, size, sha))
    if idx % report_every == 0:
        el = time.time() - start
        rate = idx / el if el else 0
        eta = (len(all_files) - idx) / rate if rate else 0
        print(f"  {idx}/{len(all_files)} ({100*idx/len(all_files):.1f}%) {rate:.0f}/s ETA {eta:.0f}s")
print(f"Hashed {len(hashed)}/{len(all_files)} in {time.time()-start:.0f}s")

# --- Pass 2: single locked drop + insert ---
DROP = set(REPORTS)
print("Acquiring evidence.json lock for drop + insert...")
with evidence_storage._file_locked() as records:
    before = len(records)

    # (a) drop partial rows for C9
    drop_keys = [
        k for k, r in records.items()
        if isinstance(r, dict) and r.get("case_id") == CASE_ID and top_seg(r) in DROP
    ]
    for k in drop_keys:
        del records[k]
    after_drop = len(records)
    print(f"  dropped {len(drop_keys)} partial rows ({before} -> {after_drop})")

    # (b) rebuild sha->primary index from REMAINING records (O(1) dedup)
    sha_to_primary = {}
    for r in records.values():
        s = r.get("sha256")
        if s and s not in sha_to_primary:
            sha_to_primary[s] = r

    now = datetime.now(timezone.utc).isoformat()
    added = dupes = 0
    for path, size, sha in hashed:
        rel = str(path.relative_to(case_dir))
        primary = sha_to_primary.get(sha)
        if primary is None:
            eid = f"ev_{sha[:16]}"
            n = 1
            while eid in records:
                eid = f"ev_{sha[:12]}_{n}"; n += 1
            rec = {
                "id": eid, "case_id": CASE_ID, "owner": OWNER,
                "original_filename": path.name, "stored_path": str(path),
                "size": size, "sha256": sha, "status": "unprocessed",
                "is_duplicate": False, "duplicate_of": None, "is_relevant": False,
                "created_at": now, "processed_at": None, "last_error": None,
                "relative_path": rel,
            }
            records[eid] = rec
            sha_to_primary[sha] = rec
            added += 1
        else:
            short = sha[:12]; n = 1
            while f"ev_{short}_{n}" in records:
                n += 1
            eid = f"ev_{short}_{n}"
            records[eid] = {
                "id": eid, "case_id": CASE_ID, "owner": OWNER,
                "original_filename": path.name, "stored_path": str(path),
                "size": size, "sha256": sha, "status": "unprocessed",
                "is_duplicate": True, "duplicate_of": primary.get("id"), "is_relevant": False,
                "created_at": now, "processed_at": None, "last_error": None,
                "relative_path": rel,
            }
            dupes += 1
    print(f"  inserted {added} primary + {dupes} duplicate = {added+dupes} rows")
    print(f"  evidence.json records: {before} -> {len(records)}")
print("Done (saved under lock).")
