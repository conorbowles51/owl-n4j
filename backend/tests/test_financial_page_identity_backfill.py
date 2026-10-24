"""Page identities for files prepared before page identity existed (r11-copy-audit).

Synthetic statements only (the r10-copies page-copy fixture). The legacy state
is a batch prepared with page identity switched off: the copy, read badly, is
not recognised. The dry run renders the files read only and says what the copy
rule would decide; the backfill stores only the identities.
"""
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID

from sqlalchemy import select

from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialSourceDocument
from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
from services.financial import page_identity, queue_save
from tests import test_financial_page_identity_copies as copies_fixture



_fixture = copies_fixture.PageCopyTests


class PageIdentityBackfillTests(TestCase):
    setUp, tearDown = _fixture.setUp, _fixture.tearDown
    _store, copy, spoil, batch, drain, items = (_fixture._store, _fixture.copy, _fixture.spoil,
                                                _fixture.batch, _fixture.drain, _fixture.items)

    def legacy(self):
        copy = self.copy()
        self.spoil(copy)
        with patch.object(page_identity, 'ENABLED', False), patch.object(queue_save, 'AUTO_SAVE_READY', False):
            batch = self.batch(self.primary, copy)
            for _ in range(10):
                self.fixture.b.advance(batch)
        return copy

    def state(self):
        with self.f.SessionLocal() as db:
            items = sorted((str(i.file_id), i.status, i.summary.get('duplicate_disposition', {}).get('status'))
                           for i in db.scalars(select(Item)) if i.status not in ('removed', 'superseded_reading'))
            identities = {str(f.id): bool(page_identity.stored(f)) for f in db.scalars(select(EvidenceFile))}
            saved = len(list(db.scalars(select(FinancialSourceDocument))))
        return items, identities, saved

    def test_dry_run_says_what_the_copy_rule_decides_and_stores_nothing(self):
        from scripts.financial_page_identity_backfill import dry_run
        copy = self.legacy()
        before = self.state()
        self.assertFalse(any(before[1].values()), 'legacy files carry no identity')
        report, detail = dry_run(self.f.SessionLocal, case_id=self.f.case.id, resolve_path=Path)
        self.assertEqual(self.state(), before, 'a dry run writes nothing')
        case = report['cases'][str(self.f.case.id)[:8]]
        self.assertEqual((case['page_copy_groups'], case['page_copy_files']), (1, 2))
        self.assertEqual(report['would_record'], 2)
        outcomes = {o['file_id']: o for o in detail[str(self.f.case.id)]['outcomes']}
        self.assertEqual((outcomes[str(copy.id)]['after'], outcomes[str(copy.id)]['basis']), ('ignored', 'identical_pages'))
        self.assertEqual(outcomes[str(self.primary.id)]['after'], 'retained')
        self.assertEqual((case.get('decision_ignored'), case.get('newly_set_aside_as_linked_copies')), (1, 1))
        self.assertNotIn('set_aside_copies_that_would_return', case)

    def test_backfill_stores_only_the_identities(self):
        from scripts.financial_page_identity_backfill import backfill, dry_run
        self.legacy()
        items, identities, saved = self.state()
        result = backfill(self.f.SessionLocal, case_id=self.f.case.id, resolve_path=Path)
        self.assertEqual((result['recorded'], result['without_identity_after']), (2, 0), result)
        after_items, after_identities, after_saved = self.state()
        self.assertEqual((after_items, after_saved), (items, saved), 'no batch item, statement or admission changed')
        with self.f.SessionLocal() as db:
            first, second = (db.get(EvidenceFile, UUID(i)) for i in sorted(after_identities) if after_identities[i])
            self.assertTrue(page_identity.same_pages(first, second))
        # A second run finds nothing to record; the dry run now reads the stored identities.
        self.assertEqual(backfill(self.f.SessionLocal, case_id=self.f.case.id, resolve_path=Path).get('attempted', 0), 0)
        report, _ = dry_run(self.f.SessionLocal, case_id=self.f.case.id, resolve_path=Path)
        self.assertEqual((report['would_record'], report['stored_already']), (0, 2))


del _fixture  # borrowed, not collected again here
