"""One-shot rebuild of C5 evidence rows from on-disk files.

The 4th C5 upload (2026-05-22 18:47-19:43) completed but its 93k evidence
rows were wiped by a subsequent multi-worker stale-state overwrite (a single
DELETE request landed on a worker that loaded a pre-upload snapshot). Files
are intact on disk; this script walks them, computes SHA-256, and inserts
fresh evidence rows directly via evidence_storage (now multi-process safe).

Usage:  python3 scripts/rebuild_c5_evidence_rows.py
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path
from datetime import datetime

# Make backend importable
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "backend"))

from services.evidence_storage import evidence_storage, EVIDENCE_ROOT_DIR  # noqa: E402

CASE_ID = "43f1afb1-1d2b-4b3f-a832-19cd049c8a9e"
FOLDER = "220049582_06306946_C5_2022-12-15_Report"
OWNER = "asolorzano@owlconsultancygroup.com"

case_dir = EVIDENCE_ROOT_DIR / CASE_ID
folder_dir = case_dir / FOLDER

if not folder_dir.exists():
    print(f"ERR: {folder_dir} does not exist")
    sys.exit(1)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# Walk files
print(f"Walking {folder_dir}")
all_files = []
for root, _dirs, files in os.walk(folder_dir):
    for f in files:
        all_files.append(Path(root) / f)
print(f"Found {len(all_files)} files")

# Prepare file_info batches.
# We deliberately do NOT use evidence_storage.add_files's per-file SHA dedup
# scan (it's O(n) over the entire records dict, ~67k entries, repeated 93k
# times → O(n²)). For an initial bulk-insert against a wiped slice, dedup
# adds nothing — the new SHA values shouldn't collide with the surviving
# non-cellebrite records. Insert raw via a single file-locked save.

# Two passes: (1) hash all files (no JSON I/O); (2) single file-locked merge
# that inserts ALL 93,150 records. Duplicates by SHA (within C5 or cross-case)
# get a `_<n>` suffix and is_duplicate=True. Skipping content-duplicate files
# would be wrong — each on-disk file must still be addressable as evidence so
# the cellebrite ingestion can map its UFED file_id to a record.
print("Hashing files...")
start = time.time()
hashed = []  # list of (path, size, sha)
report = max(1, len(all_files) // 20)
for idx, path in enumerate(all_files, 1):
    try:
        size = path.stat().st_size
        sha = sha256_of(path)
    except OSError as e:
        print(f"  skip (read err): {path}: {e}")
        continue
    hashed.append((path, size, sha))
    if idx % report == 0:
        elapsed = time.time() - start
        rate = idx / elapsed if elapsed else 0
        eta = (len(all_files) - idx) / rate if rate else 0
        print(f"  {idx}/{len(all_files)} ({100*idx/len(all_files):.1f}%) {rate:.0f}/s ETA {eta:.0f}s")
print(f"Hashed {len(hashed)}/{len(all_files)} files in {time.time()-start:.0f}s")

print("Merging into evidence.json under file lock...")
with evidence_storage._file_locked() as records:
    before = len(records)
    # Build sha -> first-record index ONCE so the dedup lookup is O(1) per
    # insert. Without this, naïve add_files is O(n) per insert => O(n²).
    sha_to_primary = {}
    for r in records.values():
        s = r.get("sha256")
        if s and s not in sha_to_primary:
            sha_to_primary[s] = r

    now = datetime.now().isoformat()
    added = 0
    dupes = 0
    for path, size, sha in hashed:
        primary = sha_to_primary.get(sha)
        rel = str(path.relative_to(case_dir))
        if primary is None:
            # First record for this SHA — primary
            evidence_id = f"ev_{sha[:16]}"
            suffix = 1
            while evidence_id in records:
                evidence_id = f"ev_{sha[:12]}_{suffix}"
                suffix += 1
            record = {
                "id": evidence_id,
                "case_id": CASE_ID,
                "owner": OWNER,
                "original_filename": path.name,
                "stored_path": str(path),
                "size": size,
                "sha256": sha,
                "status": "unprocessed",
                "is_duplicate": False,
                "duplicate_of": None,
                "is_relevant": False,
                "created_at": now,
                "processed_at": None,
                "last_error": None,
                "relative_path": rel,
            }
            records[evidence_id] = record
            sha_to_primary[sha] = record
            added += 1
        else:
            # Content-duplicate of an existing record — suffix
            sha_short = sha[:12]
            suffix = 1
            while f"ev_{sha_short}_{suffix}" in records:
                suffix += 1
            evidence_id = f"ev_{sha_short}_{suffix}"
            record = {
                "id": evidence_id,
                "case_id": CASE_ID,
                "owner": OWNER,
                "original_filename": path.name,
                "stored_path": str(path),
                "size": size,
                "sha256": sha,
                "status": "unprocessed",
                "is_duplicate": True,
                "duplicate_of": primary.get("id"),
                "is_relevant": False,
                "created_at": now,
                "processed_at": None,
                "last_error": None,
                "relative_path": rel,
            }
            records[evidence_id] = record
            dupes += 1
    after = len(records)
print(f"Done. evidence.json grew {before} -> {after} (primary added: {added}, dupes added: {dupes})")
