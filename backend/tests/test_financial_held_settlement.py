"""Held statements that need no person: copies of saved statements (saved_copies) and fund statements
(not_payment_statements), settled before the engine-release selection (held_settlement). Invented data only."""
from types import SimpleNamespace
from uuid import UUID, uuid4, uuid5

import pytest
from sqlalchemy import func, select

from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as BatchItem
from services.financial import held_settlement, not_payment_statements, saved_copies
from tests.test_financial_deployment_recovery import f  # noqa: F401  (fixture)


# Copies of saved statements -------------------------------------------------------------------------------

def _held_copy(f):
    """f.file's statement saved, then filed under other bytes; f.file holds an unworked copy of it."""
    from services.evidence_db_storage import EvidenceDBStorage
    from services.financial.import_batches import assess
    from services.financial.statement_import import read_statement_import
    receipt = f.confirm_legacy()
    other = EvidenceDBStorage.add_files(f.db, f.case.id, [dict(original_filename='other.pdf',
        stored_path=f.file.stored_path, sha256='e' * 64, size=1)], folder_id=f.file.folder_id,
        created_by_id=f.user.id)[0]
    f.db.flush()
    document = f.db.get(FinancialSourceDocument, UUID(receipt['source_document_id']))
    document.evidence_file_id = other.id
    f.db.commit()
    file = f.db.get(EvidenceFile, f.file.id)
    metadata = dict(file.metadata_ or {})
    metadata.pop('financial_duplicate_dispositions', None)
    file.metadata_ = metadata
    f.db.commit()
    with f.SessionLocal() as db:
        proposal = read_statement_import(db, case_id=f.case.id, evidence_file_id=f.file.id)
        assert not proposal.get('current_import')
        state, summary = assess(proposal)
    batch = Batch(id=uuid4(), case_id=f.case.id, created_by=f.user.id, status='review',
        actor=dict(name=f.actor.name, email=f.actor.email, user_id=str(f.actor.user_id)),
        files=[dict(source_id=str(f.file.id), file_id=str(f.file.id), filename=f.file.original_filename,
            expected_revision='initial', status='checked')])
    f.db.add(batch)
    f.db.flush()
    item = BatchItem(id=uuid5(batch.id, 'copy'), batch_id=batch.id, file_id=f.file.id,
        statement_key=proposal.get('statement_id') or '', status='attention',
        summary={**summary, 'source_id': str(f.file.id), 'can_import': False})
    f.db.add(item)
    f.db.commit()
    return receipt, document.id, item.id


def _ledger(f):
    with f.SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(FinancialTransaction).where(
            FinancialTransaction.ledger_status == 'admitted')), set(db.scalars(select(FinancialSourceDocument.id).where(
            FinancialSourceDocument.status == 'admitted')))


def _settle(f, apply=True):
    with f.SessionLocal() as db:
        outcomes = held_settlement.settle_held_statements(db, f.case.id, apply=apply)
        db.commit()
        return outcomes


def test_a_copy_the_saved_ledger_agrees_with_is_set_aside_as_a_linked_duplicate(f):
    _, document_id, item_id = _held_copy(f)
    before = _ledger(f)
    assert _settle(f, apply=False) == {'saved_copy:set_aside': 1}
    with f.SessionLocal() as db:
        assert db.get(BatchItem, item_id).status == 'attention'  # the estimate writes nothing
    assert _settle(f) == {'saved_copy:set_aside': 1}
    with f.SessionLocal() as db:
        item = db.get(BatchItem, item_id)
        decision = item.summary['duplicate_disposition']
        assert item.status == 'duplicate_ignored'
        assert decision['status'] == 'ignored' and decision['basis'] == saved_copies.BASIS
        assert decision['retained']['source_document_id'] == str(document_id)
        assert decision['actor'] == dict(name='System') and decision['reason']
        stored = db.get(EvidenceFile, f.file.id).metadata_['financial_duplicate_dispositions'][item.statement_key]
        assert stored['basis'] == saved_copies.BASIS
    # Never saved, the saved statement untouched, nothing counted twice.
    from services.financial import queue_save
    queue_save.sweep_save(f.SessionLocal, budget_seconds=None)
    assert _ledger(f) == before
    # The readiness projection keeps it set aside, and a duplicate recheck keeps the decision.
    from services.financial.import_batches import refresh_file_readiness
    from services.financial.pending_statement_duplicates import apply_duplicate_disposition
    from services.financial.statement_import import read_statement_import
    with f.SessionLocal() as db:
        refresh_file_readiness(db, case_id=f.case.id, file_id=f.file.id)
        db.commit()
        assert db.get(BatchItem, item_id).status == 'duplicate_ignored'
        file = db.get(EvidenceFile, f.file.id)
        proposal = read_statement_import(db, case_id=f.case.id, evidence_file_id=f.file.id,
                                         _include_duplicate_disposition=False)
        again = apply_duplicate_disposition(db, case_id=f.case.id, file=file, proposal=proposal)
        assert again['status'] == 'ignored' and again['basis'] == saved_copies.BASIS
        db.rollback()


def test_a_set_aside_copy_is_restored_by_the_duplicate_restore_and_stays_with_the_person(f):
    from services.financial.pending_statement_duplicates import decide_duplicate_disposition
    from services.financial.statement_import import read_statement_import
    _, _, item_id = _held_copy(f)
    _settle(f)
    with f.SessionLocal() as db:
        item = db.get(BatchItem, item_id)
        proposal = read_statement_import(db, case_id=f.case.id, evidence_file_id=f.file.id,
                                         _include_duplicate_disposition=False)
        decide_duplicate_disposition(db, case_id=f.case.id, evidence_file_id=f.file.id, action='restore',
            expected_reading_revision=proposal['revision'], statement_id=item.statement_key or None,
            expected_decision_revision=item.summary['duplicate_disposition']['revision'], actor=f.actor)
    from services.financial import queue_save
    before = _ledger(f)
    with f.SessionLocal() as db:
        item = db.get(BatchItem, item_id)
        # Back in review (stored readiness follows the restore), and never saved by the System.
        assert item.summary['readiness']['state'] in ('ready', 'attention')
        file = db.get(EvidenceFile, f.file.id)
        assert queue_save.restored_saved_copy(item, file)
        item.status = item.summary['readiness']['state']
        batch = db.get(Batch, item.batch_id)
        batch.files = [{**batch.files[0], queue_save.AUTO_SAVE_MARK: True}]
        db.commit()
    queue_save._SWEPT.clear()
    queue_save.sweep_save(f.SessionLocal, budget_seconds=None)
    assert _ledger(f) == before
    with f.SessionLocal() as db:
        assert db.get(BatchItem, item_id).status in ('ready', 'attention')
    _settle(f)
    with f.SessionLocal() as db:
        assert db.get(BatchItem, item_id).status in ('ready', 'attention')  # the person's decision stands


def test_a_copy_that_differs_stays_held_and_says_what_differs(f):
    _, document_id, item_id = _held_copy(f)
    with f.SessionLocal() as db:
        row = db.scalar(select(FinancialTransaction).where(FinancialTransaction.source_document_id == document_id,
            FinancialTransaction.ledger_status == 'admitted').order_by(FinancialTransaction.row_index))
        row.amount_minor += 1  # the saved statement carries a different payment
        db.commit()
    before = _ledger(f)
    assert _settle(f) == {'saved_copy:differs': 1}
    with f.SessionLocal() as db:
        item = db.get(BatchItem, item_id)
        assert item.status == 'attention'
        check = item.summary['saved_copy_check']
        assert check['outcome'] == 'differs' and check['saved']['source_document_id'] == str(document_id)
        (payments,) = [d for d in check['differences'] if d['field'] == 'payments']
        assert payments['only_in_copy'] == 1 and payments['only_in_saved'] == 1
    assert _ledger(f) == before
    from services.financial.review_queue import saved_copy_sentence
    assert '1 only here, 1 only in the saved one' in saved_copy_sentence(check)


def test_a_copy_with_a_persons_work_or_a_person_decision_is_left(f):
    _, _, item_id = _held_copy(f)
    with f.SessionLocal() as db:
        item = db.get(BatchItem, item_id)
        item.review_request = dict(expected_revision='x', rows=[])
        db.commit()
    assert _settle(f) == {'saved_copy:skipped:person_work': 1}
    with f.SessionLocal() as db:
        assert db.get(BatchItem, item_id).status == 'attention'


def test_copy_set_aside_switched_off_leaves_the_copy_held(f, monkeypatch):
    _, _, item_id = _held_copy(f)
    monkeypatch.setattr(saved_copies, 'ENABLED', False)
    monkeypatch.setattr(not_payment_statements, 'ENABLED', False)
    assert _settle(f) == {}
    with f.SessionLocal() as db:
        assert db.get(BatchItem, item_id).status == 'attention'


def test_compare_holds_without_payments_unread_lines_or_several_agreeing_statements():
    facts = dict(account='123456', start=None, end=None, currency='EUR', payments={}, holds=[])
    assert saved_copies.saved_periods(None, None, facts) == []  # no dates: nothing compared
    proposal = dict(currency='EUR', rows=[
        dict(id='a', kind='transaction', excluded=False, fields=dict(date='2023-01-02', amount_minor='100', direction='debit')),
        dict(id='b', kind='unresolved', excluded=False, fields=dict(description='x')),
        dict(id='c', kind='transaction', excluded=False, fields=dict(date='', amount_minor='5', direction='credit'))])
    facts = saved_copies.copy_facts(proposal, dict(account_number='12-123456', period_start='2023-01-01',
                                                   period_end='2023-01-31', rows=[]))
    assert sorted(facts['holds']) == ['incomplete_payment', 'unread_rows']
    assert sum(facts['payments'].values()) == 1
    period = SimpleNamespace(opening_balance_minor=10, closing_balance_minor=20, currency='EUR')
    facts['opening'], facts['closing'] = 10, 21
    assert [d['field'] for d in saved_copies._differences(facts, period, facts['payments'])] == ['closing']


# Fund statements ------------------------------------------------------------------------------------------

FUND_PAGE = ('ESTADO DE CUENTA \nFONDOS DE INVERSIÓN\nPÁGINA 2 /3\nNUMERO DE\nTITULOS\nPRECIO AL\nCIERRE\n'
             'VALOR DE\nMERCADO\nFONDO A 1,000 10.00 10,000.00\n')
MOVES_PAGE = 'ESTADO DE CUENTA \nFONDOS DE INVERSIÓN\nPÁGINA 3 /3\nDetalle de Movimientos Realizados\nCOMPRA 100\n'
NOTICE = 'Revisa tus datos fiscales\n'


def _text(*pages):
    content, locations = '', []
    for number, page in enumerate(pages, 1):
        locations.append(dict(kind='page', page_number=number, start_char=len(content), end_char=len(content) + len(page)))
        content += page
    return SimpleNamespace(content=content, source_locations=locations)


def _fund_proposal(rows=None, **extra):
    rows = rows if rows is not None else [
        dict(id='u1', kind='unresolved', excluded=False, page_number=3, fields=dict(date='2024-05-04', description='COMPRA')),
        dict(id='n1', kind='unresolved', excluded=False, page_number=1,
             fields=dict(description='The opening balance could not be read.')),
        dict(id='h1', kind='header', excluded=True, page_number=1, fields=dict(description='RFC'))]
    return dict(statement_id='s1', statement_page_numbers=[1, 2, 3], rows=rows, **extra)


FILE = SimpleNamespace(metadata_={})


def test_a_fund_statement_with_holdings_and_no_movement_ledger_is_not_a_payment_statement():
    result = not_payment_statements.classify(FILE, _text(NOTICE, FUND_PAGE, MOVES_PAGE), _fund_proposal())
    assert result['kind'] == 'fund_holdings' and result['status'] == 'set_aside' and result['reason']
    assert result['evidence']['title_pages'] == [2, 3] and result['evidence']['holdings_pages'] == [2]
    assert result['evidence']['reader_notes'] == 1


@pytest.mark.parametrize('change', ['payment', 'row_off_fund_pages', 'no_holdings', 'no_title', 'saved_review',
                                    'imported', 'restored', 'switch_off'])
def test_a_fund_statement_is_recognised_only_on_clear_evidence(change, monkeypatch):
    pages = [NOTICE, FUND_PAGE, MOVES_PAGE]
    proposal, file = _fund_proposal(), FILE
    if change == 'payment':  # the document also has a movement ledger: it keeps its ledger reading
        proposal['rows'].append(dict(id='t1', kind='transaction', excluded=False, page_number=3,
                                     fields=dict(date='2024-05-04', amount_minor='100', direction='debit')))
    elif change == 'row_off_fund_pages':
        proposal['rows'].append(dict(id='b1', kind='balance', excluded=True, page_number=1, fields=dict(balance='100')))
    elif change == 'no_holdings':
        pages[1] = pages[1].replace('VALOR DE\nMERCADO', '')
    elif change == 'no_title':
        pages = [page.replace('FONDOS DE INVERSIÓN', 'CUENTA MAESTRA') for page in pages]
    elif change == 'saved_review':
        proposal['saved_review'] = dict(request={})
    elif change == 'imported':
        proposal['current_import'] = dict(source_document_id='x')
    elif change == 'restored':
        file = SimpleNamespace(metadata_={not_payment_statements.METADATA_KEY: {'s1': dict(status='restored')}})
    else:
        monkeypatch.setattr(not_payment_statements, 'ENABLED', False)
    assert not_payment_statements.classify(file, _text(*pages), proposal) is None


# Online balance positions ---------------------------------------------------------------------------------

POSITION_PAGE = ('11/7/25, 13:13\nindex\nhttps://bank.example/portal\n1/1\nPosición Global - Posición\nDETALLE\n'
                 'Revise el balance y posición de sus Cuentas de Cheques\nCheques\n1,000.00 USD\nVista\n0.00 USD\n'
                 'Plazo\n0.00 USD\nTotal de la cartera:\n1,000.00 USD\nDetalle\n')


def _position_proposal(**extra):
    rows = [dict(id='u%d' % i, kind='unclassified', excluded=True, page_number=1, fields={}) for i in range(3)]
    return {**dict(statement_id=None, statement_choices=[], period_dates=None, statement_page_numbers=[1], rows=rows), **extra}


def test_a_printed_online_balance_position_is_not_a_payment_statement():
    result = not_payment_statements.classify(FILE, _text(POSITION_PAGE), _position_proposal())
    assert result['kind'] == 'online_balance_position' and result['status'] == 'set_aside'
    assert result['label'] == not_payment_statements.LABEL and result['evidence']['position_pages'] == [1]
    assert not_payment_statements.titled(POSITION_PAGE)


@pytest.mark.parametrize('change', ['period_line', 'movements', 'statement_title', 'no_total', 'no_heading',
                                    'second_page', 'statement_found', 'payment', 'saved_review', 'restored',
                                    'switch_off', 'all_off'])
def test_an_online_balance_position_is_recognised_only_on_clear_evidence(change, monkeypatch):
    pages, proposal, file = [POSITION_PAGE], _position_proposal(), FILE
    if change == 'period_line':
        pages = [POSITION_PAGE + 'DEL 01/06/2025 AL 30/06/2025\n']
    elif change == 'movements':
        pages = [POSITION_PAGE + 'Movimientos del mes\n']
    elif change == 'statement_title':
        pages = [POSITION_PAGE + 'ESTADO DE CUENTA\n']
    elif change == 'no_total':
        pages = [POSITION_PAGE.replace('Total de la cartera', 'Total')]
    elif change == 'no_heading':
        pages = [POSITION_PAGE.replace('Revise el balance y posición de sus Cuentas', 'Cuentas')]
    elif change == 'second_page':  # another page of the reading is not the position page
        pages, proposal = [POSITION_PAGE, NOTICE], _position_proposal(statement_page_numbers=[1, 2])
    elif change == 'statement_found':
        proposal = dict(proposal, period_dates=dict(start='2025-06-01', end='2025-06-30'))
    elif change == 'payment':
        proposal['rows'].append(dict(id='t1', kind='transaction', excluded=False, page_number=1,
                                     fields=dict(date='2025-07-01', amount_minor='100', direction='debit')))
    elif change == 'saved_review':
        proposal['saved_review'] = dict(request={})
    elif change == 'restored':
        file = SimpleNamespace(metadata_={not_payment_statements.METADATA_KEY: {'': dict(status='restored')}})
    elif change == 'switch_off':
        monkeypatch.setattr(not_payment_statements, 'POSITIONS', False)
    else:
        monkeypatch.setattr(not_payment_statements, 'ENABLED', False)
    assert not_payment_statements.classify(file, _text(*pages), proposal) is None


def test_a_set_aside_balance_position_is_never_saveable():
    from services.financial.pdf_candidates import PdfMappingError
    from services.financial.statement_import import check_import_request
    flag = not_payment_statements.classify(FILE, _text(POSITION_PAGE), _position_proposal())
    with pytest.raises(PdfMappingError, match='online balance position'):
        check_import_request(dict(_position_proposal(), not_payment_statement=flag), None)


def test_a_set_aside_fund_statement_is_never_saveable_and_leaves_the_waiting_queue():
    from services.financial.import_batches import assess
    from services.financial.pdf_candidates import PdfMappingError
    from services.financial.review_queue import classify as bucket
    from services.financial.statement_import import check_import_request
    flag = not_payment_statements.classify(FILE, _text(NOTICE, FUND_PAGE, MOVES_PAGE), _fund_proposal())
    proposal = dict(_fund_proposal(), not_payment_statement=flag)
    with pytest.raises(PdfMappingError):
        check_import_request(proposal, None)
    summary = dict(not_payment_statement=flag, can_import=False, problems=[], problem_count=0)
    assert bucket(SimpleNamespace(status='attention', summary=summary)) == 'not_payment'
    assert bucket(SimpleNamespace(status='attention', summary=dict(summary, not_payment_statement=None,
        problems=[dict(message='Opening balance not read', row_id=None)]))) in ('waiting', 'unreadable')


def test_assess_holds_a_fund_statement_out_of_saving_unless_a_person_added_payments(f):
    from services.financial.import_batches import assess, initial_request
    from services.financial.statement_import import read_statement_import
    with f.SessionLocal() as db:
        proposal = read_statement_import(db, case_id=f.case.id, evidence_file_id=f.file.id)
    proposal = {**proposal, 'rows': [row for row in proposal['rows'] if row['kind'] != 'transaction']}
    flag = not_payment_statements.classify(FILE, _text(NOTICE, FUND_PAGE, MOVES_PAGE), _fund_proposal())
    state, summary = assess({**proposal, 'not_payment_statement': flag})
    assert state == 'attention' and summary['can_import'] is False and summary['problems'] == []
    assert summary['not_payment_statement']['kind'] == 'fund_holdings'
    request = initial_request(proposal)
    request['rows'].append(dict(id='manual:1', manual_page=1, excluded=False, date='2023-01-05', amount_minor='100',
                                direction='debit', description='typed by a person'))
    _, summary = assess({**proposal, 'not_payment_statement': flag}, request)
    assert 'not_payment_statement' not in summary and summary['can_import'] is False  # her draft stays in review


def test_fund_statement_decision_restores_and_sets_aside_again(f, monkeypatch):
    """decide(): put back for review (recorded on the file, items assessed again), then set aside again."""
    from services.financial import import_batches, statement_import
    batch = Batch(id=uuid4(), case_id=f.case.id, created_by=f.user.id, status='review',
        actor=dict(name=f.actor.name, email=f.actor.email, user_id=str(f.actor.user_id)),
        files=[dict(source_id=str(f.file.id), file_id=str(f.file.id), filename=f.file.original_filename,
            expected_revision='initial', status='checked')])
    f.db.add(batch)
    f.db.flush()
    item = BatchItem(id=uuid5(batch.id, 'fund'), batch_id=batch.id, file_id=f.file.id, statement_key='s1',
                     status='attention', summary=dict(source_id=str(f.file.id), revision='r'))
    f.db.add(item)
    f.db.commit()
    flag = not_payment_statements.classify(FILE, _text(NOTICE, FUND_PAGE, MOVES_PAGE), _fund_proposal())

    def reading(session, *, evidence_file_id, statement_id=None, **_):
        file = session.get(EvidenceFile, evidence_file_id)
        restored = (not_payment_statements.decision(file, statement_id) or {}).get('status') == 'restored'
        return dict(_fund_proposal(), revision='r', **({} if restored else {'not_payment_statement': flag}))
    monkeypatch.setattr(statement_import, 'read_statement_import', reading)
    monkeypatch.setattr(import_batches, 'assess', lambda proposal, request=None: ('attention', dict(
        revision='r', can_import=False, problems=[] if proposal.get('not_payment_statement') else [
            dict(message='Opening balance not read', row_id=None)],
        **({'not_payment_statement': proposal['not_payment_statement']} if proposal.get('not_payment_statement') else {}))))
    monkeypatch.setattr(import_batches, 'refresh_file_readiness', lambda *a, **k: None)
    with f.SessionLocal() as db:
        result = not_payment_statements.decide(db, case_id=f.case.id, evidence_file_id=f.file.id, statement_id='s1',
                                               action='restore', actor=f.actor)
    assert result['not_payment_statement'] is None and result['decision']['status'] == 'restored'
    with f.SessionLocal() as db:
        restored = db.get(BatchItem, item.id)
        assert 'not_payment_statement' not in restored.summary and restored.summary['problems']
        assert db.get(EvidenceFile, f.file.id).metadata_[not_payment_statements.METADATA_KEY]['s1']['actor']['user_id']
    with f.SessionLocal() as db:
        result = not_payment_statements.decide(db, case_id=f.case.id, evidence_file_id=f.file.id, statement_id='s1',
                                               action='set_aside', actor=f.actor)
    assert result['not_payment_statement']['kind'] == 'fund_holdings'
    with f.SessionLocal() as db:
        again = db.get(BatchItem, item.id)
        assert again.summary['not_payment_statement']['kind'] == 'fund_holdings' and again.summary['problems'] == []
        history = db.get(EvidenceFile, f.file.id).metadata_[not_payment_statements.METADATA_KEY]['s1']['history']
        assert [entry['status'] for entry in history] == ['restored']


def test_the_engine_release_snapshot_settles_held_copies_before_selecting(f):
    from postgres.models.evidence import IngestionLog
    from tests.test_financial_recovery_readers import snapshot
    _, _, item_id = _held_copy(f)
    snapshot(f)
    with f.SessionLocal() as db:
        assert db.get(BatchItem, item_id).status == 'duplicate_ignored'
        log = db.scalar(select(IngestionLog).where(IngestionLog.extra['operation'].as_string()
                                                   == 'statement_recovery_reader_snapshot'))
        assert log.extra['scope']['settled'] == {'saved_copy:set_aside': 1}
