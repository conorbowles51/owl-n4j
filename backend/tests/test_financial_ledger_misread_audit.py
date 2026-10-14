"""The admitted-ledger misread audit compares machine-read admitted cells and writes nothing."""
import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from postgres.models.evidence import EvidenceDocumentText
from postgres.models.financial import FinancialSourceDocument
from tests.test_financial_deployment_recovery import f  # noqa: F401  (fixture)
from tests.test_financial_reader_recovery_estimate import live_state

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/financial_ledger_misread_audit.py'


def load():
    spec = importlib.util.spec_from_file_location('ledger_misread_audit_under_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def admitted(f, *, image=True):
    receipt = f.confirm_legacy()
    if image:
        text = f.db.get(EvidenceDocumentText, f.file.id)
        text.source_locations = [dict(location, text_origin='ocr') for location in text.source_locations]
        f.db.commit()
    return UUID(receipt['source_document_id'])


def retained_reader(f):
    def reader(paths, scratch, python, concurrency):
        with f.SessionLocal() as db:
            text = db.get(EvidenceDocumentText, f.file.id)
            from postgres.models.evidence import EvidenceTableGeometry
            geometry = {str(row.page_number): row.payload for row in db.scalars(select(EvidenceTableGeometry).where(
                EvidenceTableGeometry.evidence_file_id == f.file.id))}
            reading = dict(content=text.content, content_sha256=text.content_sha256, character_count=text.character_count,
                source_locations=text.source_locations, processing_manifest=text.processing_manifest, geometry=geometry)
        return {key: deepcopy(reading) for key in paths}
    return reader


def rewrite_admitted(f, document_id, *, request=True, original=True, delta=100):
    """Make one admitted payment differ from what the reading says."""
    document = f.db.get(FinancialSourceDocument, document_id)
    metadata = deepcopy(document.metadata_)
    rows = metadata['statement_import_request']['rows']
    target = next(row for row in rows if not row['excluded'] and row.get('amount_minor') not in (None, '', '0'))
    if request:
        target['amount_minor'] = str(int(target['amount_minor']) + delta)
    if original:
        source = next(row for row in metadata['statement_import_original']['rows'] if row['id'] == target['id'])
        source['fields']['amount_minor'] = str(int(source['fields']['amount_minor']) + delta)
    document.metadata_ = metadata
    f.db.commit()


def run(f, tmp_path, audit):
    return audit.audit(f.SessionLocal, f.case.id, scratch_root=tmp_path, resolve_path=Path, reader=retained_reader(f))


def test_consistent_admission_is_not_flagged_and_nothing_is_written(f, tmp_path):
    audit = load()
    admitted(f)
    before = live_state(f)
    report = run(f, tmp_path, audit)
    assert live_state(f) == before
    assert report['outcomes'] == {'consistent': 1}
    assert report['cells']['agrees'] >= 1 and not report['cells'].get('disagrees')
    assert not list(tmp_path.iterdir())


def test_machine_misread_admitted_value_is_flagged(f, tmp_path):
    audit = load()
    document = admitted(f)
    rewrite_admitted(f, document)
    report = run(f, tmp_path, audit)
    (period,) = report['periods']
    assert period['outcome'] == 'flagged' and period['source_document_id'] == str(document)
    assert period['cells']['disagrees'] == 1
    text = audit.render(report)
    assert str(document) in text and f.file.original_filename not in text
    assert f.file.original_filename not in json.dumps(report)


def test_investigator_entered_value_is_counted_but_not_flagged(f, tmp_path):
    audit = load()
    document = admitted(f)
    rewrite_admitted(f, document, original=False)
    report = run(f, tmp_path, audit)
    (period,) = report['periods']
    assert period['outcome'] == 'consistent' and period['cells']['investigator_disagrees'] == 1


def test_native_text_statements_are_skipped(f, tmp_path):
    audit = load()
    admitted(f, image=False)
    report = audit.audit(f.SessionLocal, f.case.id, scratch_root=tmp_path, resolve_path=Path,
        reader=lambda *args: (_ for _ in ()).throw(AssertionError('native text must not be re-read')))
    assert report['skipped'] == {'native_text_only': 1} and report['periods'] == []


def test_native_reading_over_invisible_text_is_audited_with_the_current_origin_rule(f, tmp_path):
    """A retained reading that called a page born-digital is audited when the
    original, measured now, has mostly invisible text (r1-reproduced)."""
    import fitz
    audit = load()
    admitted(f, image=False)
    document = fitz.open()
    page = document.new_page(width=200, height=200)
    page.insert_text((20, 100), 'Purchase 12.34', render_mode=3)
    Path(f.file.stored_path).write_bytes(document.tobytes())
    report = audit.audit(f.SessionLocal, f.case.id, scratch_root=tmp_path, resolve_path=Path, reader=retained_reader(f))
    assert 'native_text_only' not in report['skipped']
    assert report['considered'] == 1
