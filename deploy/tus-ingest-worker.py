#!/usr/bin/env python3
"""Detached worker spawned by the tusd post-finish hook.

Takes a finished upload (a Cellebrite .zip landed in <case>/_incoming) and runs
the SAME path a manual/auto-routed upload would: extract it so the UFED *.xml is
at a folder's top level, then call evidence_service._maybe_autoingest_cellebrite,
which detects the report, creates a `cellebrite_ingestion` background task (shown
in the UI), and runs process_cellebrite_report.

Runs detached from tusd (heavy extraction + ingestion must not block the upload
response). Logs to /mnt/owl-data/uploads-tus/ingest.log.

Usage: tus-ingest-worker.py <case_id> <src_zip> [owner_email]
"""
import sys, os, time, zipfile, shutil, traceback

LOG = "/mnt/owl-data/uploads-tus/ingest.log"
# Direct data-disk path (same mount as the tus store -> atomic ops). The app
# sees the same files via its bind mount at ingestion/data/<case_id>/...
DATA_ROOT = "/mnt/owl-data/ingestion-data"
CB_NS = b"http://pa.cellebrite.com/report/2.0"

def log(msg):
    try:
        with open(LOG, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} ingest-worker: {msg}\n")
    except Exception:
        pass

def safe_extract(zip_path, dest_dir):
    """Stream-extract with zip-slip protection; skip mac sidecars."""
    os.makedirs(dest_dir, exist_ok=True)
    dest_real = os.path.realpath(dest_dir)
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename
            if name.endswith("/"):
                continue
            base = os.path.basename(name)
            if "__MACOSX" in name or base.startswith("._") or base == ".DS_Store":
                continue
            target = os.path.realpath(os.path.join(dest_dir, name))
            if not (target == dest_real or target.startswith(dest_real + os.sep)):
                raise ValueError(f"zip-slip blocked: {name}")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(info) as srcf, open(target, "wb") as outf:
                shutil.copyfileobj(srcf, outf, length=4 * 1024 * 1024)

def find_report_dir(root):
    """Return the dir holding the Cellebrite UFED *.xml (namespace match)."""
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if fn.lower().endswith(".xml"):
                try:
                    with open(os.path.join(dirpath, fn), "rb") as f:
                        if CB_NS in f.read(4096):
                            return dirpath
                except Exception:
                    pass
    return None

def main():
    case_id = sys.argv[1]
    src_zip = sys.argv[2]
    owner = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else None
    log(f"start case={case_id} src={src_zip} owner={owner}")

    if not os.path.exists(src_zip):
        log(f"ERROR: source missing {src_zip}"); return
    if not zipfile.is_zipfile(src_zip):
        log(f"NOTE: {src_zip} is not a zip — leaving as-is, no ingest."); return

    # extract into a sibling report folder named after the zip stem
    stem = os.path.splitext(os.path.basename(src_zip))[0] or "report"
    extract_dir = os.path.join(DATA_ROOT, case_id, stem)
    if os.path.exists(extract_dir):
        extract_dir = f"{extract_dir}-{int(os.path.getmtime(src_zip))}"
    log(f"extracting -> {extract_dir}")
    try:
        safe_extract(src_zip, extract_dir)
    except Exception:
        log("EXTRACT FAILED:\n" + traceback.format_exc()); return

    report_dir = find_report_dir(extract_dir)
    if not report_dir:
        log(f"ERROR: no Cellebrite UFED xml found under {extract_dir}"); return
    # folder_name is relative to the case dir (what _maybe_autoingest expects)
    folder_name = os.path.relpath(report_dir, os.path.join(DATA_ROOT, case_id))
    log(f"report dir found; folder_name={folder_name}")

    # free the uploaded zip now that it's extracted (reclaim 30GB)
    try:
        os.remove(src_zip)
    except Exception:
        pass

    # hand off to the EXACT auto-route used by API uploads
    os.chdir("/home/conorbowles51/app_v2/backend")
    sys.path.insert(0, ".")
    sys.path.append("../ingestion/scripts")
    try:
        from services.evidence_service import evidence_service
        log(f"calling _maybe_autoingest_cellebrite(case={case_id}, folder={folder_name})")
        evidence_service._maybe_autoingest_cellebrite(
            case_id=case_id, folder_name=folder_name, owner=owner)
        log("ingest handoff returned (task created + processed)")
    except Exception:
        log("INGEST HANDOFF FAILED:\n" + traceback.format_exc())

if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("FATAL:\n" + traceback.format_exc())
