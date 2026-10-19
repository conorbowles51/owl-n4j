"""Read PDFs with the evidence engine's own PDF preparation code.

Runs in a separate process from the backend side of the harness, just as the
engine is a separate service in production. For each PDF this calls the same
functions ``app.pipeline.prepare_pdf_review`` calls -- ``extract_text`` (native
text, table geometry, OCR fallback and the quality-triggered image reread),
``build_canonical_document_text`` and ``group_per_table_by_page`` -- and writes
what would have been persisted to ``evidence_document_text`` and
``evidence_table_geometry``. Only the job queue and the async database write
are not exercised.

Usage (cwd anywhere): python engine_read.py OUT.json CONCURRENCY PDF [PDF ...]
"""
import asyncio
import json
import os
import resource
import sys
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3] / 'evidence-engine'


async def _read(path, semaphore):
    from app.pipeline.extract_text import extract_text
    from app.services.evidence_document_text import build_canonical_document_text
    from app.services.evidence_table_geometry import group_per_table_by_page
    async with semaphore:
        started = time.monotonic()
        try:
            document = await extract_text(path, Path(path).name, pdf_reading_mode='automatic')
        except Exception as error:  # A failed reading is a measured outcome.
            return path, dict(error=f'{type(error).__name__}: {error}', seconds=time.monotonic() - started)
        seconds = time.monotonic() - started
    canonical = build_canonical_document_text(document)
    by_page, without_geometry, invalid = group_per_table_by_page(document.metadata)
    return path, dict(content=canonical.content, content_sha256=canonical.content_sha256,
                      character_count=canonical.character_count, source_locations=canonical.source_locations,
                      processing_manifest=document.metadata.get('processing_manifest'),
                      geometry={str(page): entries for page, entries in by_page.items()},
                      entries_without_geometry=without_geometry, entries_invalid=invalid, seconds=seconds)


async def _main(out, concurrency, paths):
    semaphore = asyncio.Semaphore(concurrency)
    results = await asyncio.gather(*(_read(path, semaphore) for path in paths))
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    Path(out).write_text(json.dumps(dict(readings=dict(results),
        child_cpu_seconds=children.ru_utime + children.ru_stime), default=str))


if __name__ == '__main__':
    sys.path.insert(0, str(ENGINE))
    os.chdir(ENGINE)
    asyncio.run(_main(sys.argv[1], int(sys.argv[2]), sys.argv[3:]))
