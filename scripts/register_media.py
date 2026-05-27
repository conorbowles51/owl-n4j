"""Standalone media-registration (Cellebrite ingest Step 9) — link a report's
media files to evidence rows so audio/image/video attachments RESOLVE and
render in the comms chat view.

WHY: the fast CLI ingests ran with CELLEBRITE_SKIP_MEDIA_REGISTRATION=1, so
C6/C8/C2/C4/C9/C1-06304890 never got their evidence rows tagged with the
Cellebrite file UUID. Messages carry attachment_file_ids, but
evidence_storage.get_by_cellebrite_file_ids finds nothing → attachments come
back missing:true → no audio player / no image in the chat. The binaries are
already on disk (bulk-registered); this pass just runs the registration step
(no graph re-ingest) to patch cellebrite_file_id/category onto those rows.

Concurrency-safe with a running backend: register_media_files writes through
evidence_storage._file_locked (reload-mutate-save), and the backend's reads
call _refresh_if_stale (mtime) so it picks up the new tags WITHOUT a restart.

Run:
  sudo -u conorbowles51 env PYTHONPATH=backend venv/bin/python \
      scripts/register_media.py C6 [C8 C2 C4 C9 C1b]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.append(str(ROOT / "ingestion" / "scripts"))
sys.path.append(str(ROOT / "scripts"))

from cellebrite.parser import CellebriteXMLParser          # noqa: E402
from cellebrite.file_linker import CellebriteFileLinker     # noqa: E402
from services.evidence_storage import evidence_storage      # noqa: E402
from forensic_export import REPORTS, CASE_DIR               # noqa: E402

CASE_ID = "43f1afb1-1d2b-4b3f-a832-19cd049c8a9e"
OWNER = "oferreira@owlconsultancygroup.com"   # case custodian (attribution only)


def register(label: str, xml_path: Path) -> None:
    report_dir = xml_path.parent
    parser = CellebriteXMLParser(str(xml_path))
    report = parser.parse_header()
    report_key = (
        f"cellebrite-{report.case_info.case_number or 'unknown'}"
        f"-{report.case_info.evidence_number or 'unknown'}"
    )
    tagged_files = parser.parse_tagged_files()
    linker = CellebriteFileLinker(
        report_dir=report_dir, tagged_files=tagged_files,
        case_id=CASE_ID, report_key=report_key,
    )
    # model_file_map back-links each media file to the model that referenced it
    models = []
    for batch in parser.stream_models(batch_size=500):
        models.extend(batch)
    model_file_map = linker.build_model_file_map(models)

    t0 = time.time()
    n = linker.register_media_files(
        evidence_storage=evidence_storage, owner=OWNER, model_file_map=model_file_map,
    )
    print(f"[{label}] key={report_key} resolved_files={linker.resolved_count} "
          f"media_registered={n} ({time.time()-t0:.0f}s)", flush=True)


def main():
    labels = [a for a in sys.argv[1:] if a in REPORTS]
    if not labels:
        print("usage: register_media.py <LABEL...>  (e.g. C6 C8 C2 C4 C9 C1b)")
        return
    for label in labels:
        xml = CASE_DIR / REPORTS[label]
        if not xml.exists():
            print(f"[{label}] MISSING xml: {xml}")
            continue
        register(label, xml)


if __name__ == "__main__":
    main()
