from types import SimpleNamespace

from sqlalchemy import select

from postgres.models.financial_recovery import FinancialRecoveryItem as Item, FinancialRecoveryRun as Run
from services.financial import deployment_recovery as recovery
from services.financial.file_scope import mark_financial_workspace
from services.financial.recovery_campaigns import RecoveryCampaign
from tests.test_financial_deployment_recovery import f


def test_diagnosed_andrews_campaign_is_registered_but_not_automatically_scheduled():
    from services.financial.recovery_campaigns import CAMPAIGNS, ANDREWS_BALANCE_RELEASE, manifest
    assert manifest(ANDREWS_BALANCE_RELEASE) is not None
    assert ANDREWS_BALANCE_RELEASE not in {campaign.release for campaign in CAMPAIGNS}


def test_selective_campaign_requires_affected_reader_revision_and_unresolved_outcome():
    campaign = RecoveryCampaign('synthetic-reader-repair-v2', {'bbva-mexico-cash-management': ('reader-v1',)})
    def previous(state='review', readers=None):
        return SimpleNamespace(status=state, result=dict(readers=readers or {}))
    affected = {'bbva-mexico-cash-management': 'reader-v1'}
    assert campaign.eligible(previous(readers=affected))
    assert not campaign.eligible(previous('recovered', affected))
    assert not campaign.eligible(previous('unchanged', affected))
    assert not campaign.eligible(previous('kept', affected))
    assert not campaign.eligible(previous())
    assert not campaign.eligible(previous(readers={'bbva-mexico-cash-management': 'reader-v2'}))
    assert not campaign.eligible(previous(readers={'santander-mexico-movements': 'reader-v1'}))
    assert not campaign.eligible(None)


def test_new_campaign_revisits_only_affected_unresolved_source_once(f):
    unaffected = f.evidence('c' * 64)
    successful = f.evidence('d' * 64)
    for file in (unaffected, successful):
        mark_financial_workspace(file, user_id=f.user.id)
    f.db.commit()
    with f.SessionLocal() as db:
        recovery.snapshot_case(db, f.case.id, recovery.activate(db))
        original = db.scalar(select(Run).where(Run.case_id == f.case.id))
        original.status = 'complete'
        original_items = list(db.scalars(select(Item).where(Item.run_id == original.id)))
        for item in original_items:
            item.status = 'unchanged' if item.file_id == successful.id else 'review'
            reader = 'bbva-mexico-cash-management' if item.file_id in (f.file.id, successful.id) else 'santander-mexico-movements'
            item.result = {**item.result, 'readers': {reader: 'reader-v1'}}
        db.commit()
        campaign = RecoveryCampaign('statement-recovery-2026-09-25-synthetic', {'bbva-mexico-cash-management': ('reader-v1',)})
        cutoff = recovery.activate(db, campaign.release)
        recovery.snapshot_case(db, f.case.id, cutoff, campaign)
        current = db.scalar(select(Run).where(Run.case_id == f.case.id, Run.release == campaign.release))
        items = list(db.scalars(select(Item).where(Item.run_id == current.id)))
        assert [item.file_id for item in items] == [f.file.id]
        assert items[0].result['previous_item_id']
        recovery.snapshot_case(db, f.case.id, cutoff, campaign)
        assert len(list(db.scalars(select(Item).where(Item.run_id == current.id)))) == 1
        state = recovery.status(db, f.case.id)
        assert state['run']['id'] == str(current.id)
        assert state['previous_runs'] == [dict(id=str(original.id), release=original.release, status='complete')]
        assert recovery.status(db, f.case.id, run_id=original.id)['total'] == len(original_items)
        assert recovery.status(db, f.other_case.id, run_id=current.id)['run'] is None
        recovery.control(db, f.case.id, 'pause', run_id=current.id)
        assert db.get(Run, current.id).status == 'paused'
        assert db.get(Run, original.id).status == 'complete'


def test_empty_selective_snapshot_stays_complete_after_later_outcome_changes(f):
    campaign = RecoveryCampaign('statement-recovery-2026-09-25-empty', {'bbva-mexico-cash-management': ('reader-v1',)})
    with f.SessionLocal() as db:
        recovery.snapshot_case(db, f.case.id, recovery.activate(db))
        old = db.scalar(select(Item))
        old.status = 'unchanged'
        old.result = {**old.result, 'readers': {'bbva-mexico-cash-management': 'reader-v1'}}
        db.commit()
        cutoff = recovery.activate(db, campaign.release)
        recovery.snapshot_case(db, f.case.id, cutoff, campaign)
        state = recovery.status(db, f.case.id)
        assert state['run']['status'] == 'complete' and state['total'] == 0
        old.status = 'review'
        db.commit()
        recovery.snapshot_case(db, f.case.id, cutoff, campaign)
        assert recovery.status(db, f.case.id)['total'] == 0


def install_affected_andrews(f, *, damaged=True, fingerprint=None):
    from postgres.models.evidence import EvidenceDocumentText, EvidenceTableGeometry
    from services.financial.pdf_candidates import _digest
    from tests.test_financial_pdf_processing_manifest import manifest as preparation_manifest
    from tests.test_financial_statement_import_andrews import two_shares
    from tests.test_financial_pdf_geometry_candidates import rectangle
    grid = two_shares()
    if damaged:
        grid['rows'][14]['cells'][3]['expected_text'] = '18O.00'
    doc = f.db.get(EvidenceDocumentText, f.file.id)
    preparation = preparation_manifest()
    preparation['content']['source_files_sha256']['pdf_extraction.py'] = fingerprint or 'ec9cfca7b4120060c7292491f83daccfb9f0591f7e66d90f950a93638ac1d5b4'
    preparation['sha256'] = _digest(preparation['content'])
    doc.processing_manifest = preparation
    geometry = f.db.get(EvidenceTableGeometry, (f.file.id, 1))
    geometry.payload = [dict(table_source='text_alignment', geometry_source='cell_rectangles',
        table=dict(page=1, table=rectangle(0,x=0,width=600,height=800), unlocated_values=0,
            values=[dict(row=row['row_index'],column=cell['column_index'],text=cell['expected_text'],locator=cell['locator'])
                for row in grid['rows'] for cell in row['cells']]))]
    f.db.commit()


def selective_snapshot(f):
    from services.financial.recovery_campaigns import ANDREWS_BALANCE_RELEASE, manifest
    campaign = manifest(ANDREWS_BALANCE_RELEASE)
    with f.SessionLocal() as db:
        recovery.snapshot_case(db, f.case.id, recovery.activate(db))
        old = db.scalar(select(Item).where(Item.file_id == f.file.id))
        old.status = 'review'
        db.get(Run, old.run_id).status = 'complete'
        assert not old.result.get('readers')
        db.commit()
        cutoff = recovery.activate(db,campaign.release)
        recovery.snapshot_case(db, f.case.id, cutoff,campaign)
        run = db.scalar(select(Run).where(Run.release==campaign.release))
        return list(db.scalars(select(Item.id).where(Item.run_id==run.id)))


def test_legacy_source_campaign_requires_the_recorded_reader_and_actual_missing_balance(f):
    from services.financial.recovery_campaigns import ANDREWS_BALANCE_RELEASE, manifest, source_reader_evidence
    campaign = manifest(ANDREWS_BALANCE_RELEASE)
    install_affected_andrews(f, damaged=False)
    assert source_reader_evidence(f.db, f.file, campaign) == {}
    install_affected_andrews(f, fingerprint='b'*64)
    assert source_reader_evidence(f.db, f.file, campaign) == {}
    install_affected_andrews(f)
    assert source_reader_evidence(f.db, f.file, campaign) == {'andrews-share-statement':'statement-review-v31'}
    items = selective_snapshot(f)
    assert len(items)==1
    with f.SessionLocal() as db:
        assert db.get(Item,items[0]).result['fresh_reading']
        recovery.snapshot_case(db,f.case.id,recovery.activate(db,campaign.release),campaign)
        run=db.scalar(select(Run).where(Run.release==campaign.release))
        assert len(list(db.scalars(select(Item.id).where(Item.run_id==run.id))))==1


def test_affected_legacy_reading_gets_a_separate_reading_request_not_a_ledger_write(f):
    from pathlib import Path
    from postgres.models.financial import FinancialTransaction
    from postgres.models.evidence import EvidenceDocumentText
    install_affected_andrews(f)
    before=f.db.get(EvidenceDocumentText,f.file.id).content
    [item_id]=selective_snapshot(f)
    request=recovery.recover_one(f.SessionLocal,item_id,Path)
    assert request['needs_reading'] and request['file_id']==f.file.id
    assert list(f.db.scalars(select(FinancialTransaction)))==[]
    assert f.db.get(EvidenceDocumentText,f.file.id).content==before


def test_legacy_repair_preserves_saved_review_and_ignored_duplicate(f):
    from pathlib import Path
    from uuid import uuid4
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as BatchItem
    install_affected_andrews(f)
    [item_id]=selective_snapshot(f)
    with f.SessionLocal() as db:
        file=db.get(EvidenceFile,f.file.id)
        file.metadata_={**(file.metadata_ or {}),'financial_review_progress':{'saved':{'holder':'Investigator correction'}}}
        db.commit()
    assert recovery.recover_one(f.SessionLocal,item_id,Path) is None
    with f.SessionLocal() as db:
        item=db.get(Item,item_id)
        assert item.status=='review' and not item.result.get('reading_file_id')
        file=db.get(EvidenceFile,f.file.id)
        assert file.metadata_['financial_review_progress']['saved']['holder']=='Investigator correction'
        file.metadata_={key:value for key,value in file.metadata_.items() if key!='financial_review_progress'}
        item.status='pending'
        batch=Batch(id=uuid4(),case_id=f.case.id,created_by=f.user.id,status='review',files=[],actor={})
        db.add(batch);db.flush()
        db.add(BatchItem(id=uuid4(),batch_id=batch.id,file_id=f.file.id,statement_key='synthetic',status='duplicate_ignored',summary={}))
        db.commit()
    assert recovery.recover_one(f.SessionLocal,item_id,Path) is None
    with f.SessionLocal() as db:
        assert db.get(Item,item_id).status=='kept'
        assert not db.get(Item,item_id).result.get('reading_file_id')
