"""The Financial page's statement register (GET /api/evidence/statement-register): the evidence listing it asked
for before (include_reading_versions, financial_only), each file given only the fields the register reads. On
d5b330d1 the whole listing is 4.6 MB for 3,176 files; the register's schema dropped every other field."""
import inspect
from unittest.mock import patch

from routers import evidence

FILE = {
    'id': 'f1', 'case_id': 'c', 'original_filename': 'Statement.pdf', 'status': 'processed',
    'created_at': '2026-01-01T00:00:00', 'statement_root_evidence_id': 'f0', 'statement_parent_evidence_id': 'f0',
    'financial_removed': False, 'financial_imports_removed': None, 'financial_visibility_revision': 'initial',
    'financial_visibility_changed_at': None, 'stored_path': '/x/y.pdf', 'sha256': 'ab', 'summary': 'long text',
    'reading_versions': [{'id': 'f0'}], 'transcription': None, 'folder_id': None,
}


def test_the_register_is_the_kept_listing_with_only_the_fields_it_reads():
    asked = []
    from services.financial import view_cache
    with patch.object(view_cache, 'kept_copy', side_effect=lambda name, kw: asked.append((name, kw)) or {'files': [FILE]}), \
            patch.object(evidence, 'list_evidence') as listing:
        answer = evidence.list_statement_register(case_id='c', db='fake-session')
    listing.assert_not_called()
    whole = inspect.signature(inspect.unwrap(evidence.list_evidence)).parameters
    assert asked == [('evidence-list', dict(case_id='c', status_filter=None, include_cellebrite_artifacts=False,
                                            include_reading_versions=True, financial_only=True))]
    assert set(asked[0][1]) == set(whole) - {'db'}, 'the same cached-view key as the listing the register asked for'
    assert answer == {'files': [{field: FILE[field] for field in evidence.STATEMENT_REGISTER_FIELDS}]}
    assert 'stored_path' not in answer['files'][0] and 'reading_versions' not in answer['files'][0]


def test_the_register_reads_the_listing_itself_when_none_is_kept_and_leaves_out_what_it_leaves_out():
    from services.financial import view_cache
    partial = {k: v for k, v in FILE.items() if k != 'financial_visibility_changed_at'}
    with patch.object(view_cache, 'kept_copy', return_value=None), \
            patch.object(evidence, 'list_evidence', return_value={'files': [partial, FILE]}) as listing:
        answer = evidence.list_statement_register(case_id='c', db='fake-session')
    listing.assert_called_once_with(db='fake-session', case_id='c', status_filter=None,
                                    include_cellebrite_artifacts=False, include_reading_versions=True,
                                    financial_only=True)
    assert 'financial_visibility_changed_at' not in answer['files'][0]
    assert answer['files'][1] == {field: FILE[field] for field in evidence.STATEMENT_REGISTER_FIELDS}


def test_the_register_fields_are_the_ones_the_page_reads():
    import pathlib
    import re
    page = pathlib.Path(__file__).resolve().parents[2] / 'frontend_v2/src/features/financial/hooks/use-statement-register.ts'
    source = page.read_text()
    schema = re.search(r'export const statementFile = (?:lazySchema\(\(\) => )?z\.object\(\{(.*?)\n\}\)', source, re.S).group(1)
    assert tuple(re.findall(r'^\s+(\w+):', schema, re.M)) == evidence.STATEMENT_REGISTER_FIELDS
