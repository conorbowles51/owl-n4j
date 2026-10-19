"""Read-only real-PDF grid nomination smoke check. No database or AI calls.

The same-pass extraction result stands in for a stored snapshot. Every nonempty
row is bound with unknown column meanings solely to exercise source contracts;
no row is classified as a transaction, persisted, normalized or admitted.
"""
import hashlib
import json
import sys
from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import pymupdf
from services.financial.pdf_tables import read_tables
from services.financial.candidate_sources import read_candidate_source
from services.financial.pdf_geometry_candidates import bind_pdf_grid_mapping
from services.financial.pdf_candidates import PdfMappingError


class Snapshot:
    no_autoflush = nullcontext()

    def __init__(self, row):
        self.row = row

    def execute(self, query):
        return self

    def one_or_none(self):
        return self.row


def main():
    results = []
    paths = sorted((ROOT / 'data/loupe-test-pdfs').glob('*.pdf'))
    if not paths:
        raise RuntimeError('Add local test PDFs in data/loupe-test-pdfs first.')
    for path in paths:
        record = dict(file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                      pages=0, tables=0, bound_tables=0, bound_rows=0, blank_pages=[], refused=[])
        with pymupdf.open(path) as document:
            record['pages'] = len(document)
            for number, page in enumerate(document, 1):
                content = page.get_text()
                if not content:
                    pixmap = page.get_pixmap(colorspace=pymupdf.csGRAY, alpha=False)
                    if min(pixmap.samples) == 255:
                        record['blank_pages'].append(number)
                case, file, job = uuid4(), uuid4(), uuid4()
                tables = read_tables(page, number)
                record['tables'] += len(tables)
                snapshot = Snapshot((record['sha256'], content, hashlib.sha256(content.encode()).hexdigest(),
                    [], job, job, [table.to_json() for table in tables]))
                for index in range(len(tables)):
                    try:
                        source = read_candidate_source(snapshot, case_id=case, evidence_file_id=file,
                                                       page_number=number, table_index=index)
                        if not source['rows']:
                            continue
                        proposal = dict(schema_version='pdf-grid-mapping-v1', case_id=str(case),
                            evidence_file_id=str(file), page_number=number, table_index=index,
                            source_revision=source['source_revision'],
                            columns=[dict(column_index=c, meaning='unknown') for c in source['columns']],
                            rows=[dict(row_index=r['row_index'], cells=[{k:c[k] for k in ('column_index', 'expected_text')}
                                  for c in r['cells']]) for r in source['rows']])
                        bound = bind_pdf_grid_mapping(snapshot, case_id=case, proposal=proposal)
                        assert all(c.status == 'pending' for c in bound.candidates)
                        assert bound.applied is False
                        record['bound_tables'] += 1
                        record['bound_rows'] += len(bound.candidates)
                    except PdfMappingError as exc:
                        record['refused'].append(dict(page=number, table=index, reason=str(exc)))
        results.append(record)
        print(json.dumps(record), flush=True)
    output = ROOT / 'data/local-runtime/pdf-inspection'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'candidate-sources.json').write_text(json.dumps(results, indent=2) + '\n')


if __name__ == '__main__':
    main()
