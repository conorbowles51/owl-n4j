"""The ledger export carries account-correction provenance (services.financial.account_correction_provenance):
original beside corrected, who made it, a model's correction as its reading until confirmed, and relayed
confirmations as "Confirmed by X, entered by Y on X's instruction". History shapes are those stored on live accounts
(account_details_history: a relayed confirmation without a note, a later relay with one, an unconfirmed model
number correction), plus a person's correction and an undone one."""
import json
from copy import deepcopy

from tests.test_financial_ledger_summary import LedgerSummaryTests

NEIL = dict(name='Neil Byrne', user_id='f567bf20-4c58-4ca0-9117-54f1fa78d4ee')
CLAUDE = dict(kind='model', model='Claude', at='2026-10-25T23:09:34+00:00', **{'for': NEIL})

HISTORY = [
    dict(id='c1', kind='correction', at='2026-10-25T23:09:34+00:00', origin=CLAUDE, actor_name='Claude (for Neil Byrne)',
         reason='Page 1 prints the holder above the address block.',
         before=dict(holder='LOMAS DE CHAPULTEPEC III SECCION', institution='Kapital'),
         after=dict(holder='INGENIERIA APLICADA R2', institution='Kapital'),
         confirmed=dict(by='Neil Byrne', by_email='neil@example.test', user_id=NEIL['user_id'],
                        at='2026-10-29T23:31:41+00:00', basis='Page 1 prints INGENIERIA APLICADA R2.',
                        relayed=dict(by='Claude (fin-provenance job, for Neil Byrne)', via='message m1',
                                     at_given='2026-10-29T05:45:00+00:00'),
                        later_relays=[dict(by='Claude (fin-smalls)', at='2026-10-30T20:23:18+00:00', via='message m2',
                                           note="Entered by Claude (fin-smalls) on Neil Byrne's instruction of 2026-10-30",
                                           basis='Approved by message on 2026-10-29.')])),
    dict(id='c2', kind='correction', at='2026-10-30T02:47:56+00:00', actor_name='Claude (for Neil Byrne)',
         origin=dict(CLAUDE, citation=dict(file='06 KAPITAL MXN JUN 26.pdf', page=1)),
         reason='The page prints the account number; the saved number was the CLABE.',
         before=dict(holder='INGENIERIA APLICADA R2', institution='Kapital', account_number='128180000000238632'),
         after=dict(holder='INGENIERIA APLICADA R2', institution='Kapital', account_number='194-98075-001-8')),
    dict(id='c3', kind='correction', at='2026-10-30T09:00:00+00:00', actor_name='Ana Analyst', reason='Bank name.',
         before=dict(holder='INGENIERIA APLICADA R2', institution='Kapital'),
         after=dict(holder='INGENIERIA APLICADA R2', institution='Banco Kapital')),
    dict(id='c4', kind='correction', at='2026-10-30T10:00:00+00:00', actor_name='Ana Analyst', reason='Wrong guess.',
         before=dict(holder='INGENIERIA APLICADA R2', institution='Banco Kapital'),
         after=dict(holder='R2 INGENIERIA', institution='Banco Kapital'), undone_at='2026-10-30T10:05:00+00:00',
         undone_by='u1'),
    dict(id='u1', kind='undo', undo_of='c4', at='2026-10-30T10:05:00+00:00', reason='Wrong guess.'),
]


class AccountCorrectionExportTests(LedgerSummaryTests):
    def export(self):
        from services.financial.ledger_snapshot import LedgerSnapshot, _capture_history, capture_ledger_snapshot
        # The export's own capture needs PostgreSQL; this is the same snapshot and history capture on SQLite.
        document = _capture_history(self.db, json.loads(capture_ledger_snapshot(self.db, case_id=self.case.id).content),
                                    case_id=self.case.id)
        return document, LedgerSnapshot(json.dumps(document), 'a' * 64, 0)

    def correct(self, row):
        from postgres.models.financial import FinancialAccount
        account = self.db.get(FinancialAccount, row.account_id)
        account.metadata_ = dict(deepcopy(account.metadata_ or {}), account_details_history=deepcopy(HISTORY))
        self.db.commit()
        return account

    def test_export_carries_each_correction_with_original_who_and_confirmation(self):
        from services.financial.ledger_snapshot import render_ledger_report
        row, _ = self.add(1234)
        self.add(99)
        self.db.commit()
        before, _ = self.export()
        account = self.correct(row)
        after, snapshot = self.export()
        # Same rows and totals: only the provenance is added.
        self.assertEqual(before['ledger'], after['ledger'])
        self.assertEqual(before['working_totals'], after['working_totals'])
        self.assertEqual(before['account_corrections']['corrections'], [])
        records = after['account_corrections']['corrections']
        by = {(item['correction_id'], item['field']): item for item in records}
        self.assertEqual(sorted(by), [('c1', 'holder'), ('c2', 'account_number'), ('c3', 'institution'), ('c4', 'holder')])
        self.assertTrue(all(item['account_id'] == str(account.id) for item in records))
        holder = by[('c1', 'holder')]
        self.assertEqual((holder['original_value'], holder['corrected_value'], holder['current_value']),
                         ('LOMAS DE CHAPULTEPEC III SECCION', 'INGENIERIA APLICADA R2', 'INGENIERIA APLICADA R2'))
        self.assertEqual((holder['made_by'], holder['made_by_kind'], holder['status']), ('Claude for Neil Byrne', 'model', 'confirmed'))
        # The first relay was stored without a note: it says so rather than assume one.
        self.assertEqual(holder['status_text'], 'Confirmed by Neil Byrne, entered by Claude (fin-provenance job, for Neil '
                         'Byrne) (no relay note recorded), 2026-10-29: Page 1 prints INGENIERIA APLICADA R2.')
        self.assertEqual([relay['text'] for relay in holder['relays']], [
            'Confirmed by Neil Byrne, entered by Claude (fin-provenance job, for Neil Byrne) (no relay note recorded), 2026-10-29',
            "Confirmed by Neil Byrne, entered by Claude (fin-smalls) on Neil Byrne's instruction, 2026-10-30"])
        number = by[('c2', 'account_number')]
        self.assertEqual((number['status'], number['status_text']),
                         ('model_reading_not_confirmed', "Corrected by Claude · not confirmed (the model's reading)"))
        self.assertEqual(number['original_value'], '128180000000238632')
        self.assertEqual(number['citation'], dict(file='06 KAPITAL MXN JUN 26.pdf', page=1))
        self.assertEqual((by[('c3', 'institution')]['status'], by[('c3', 'institution')]['made_by']), ('person', 'Ana Analyst'))
        undone = by[('c4', 'holder')]
        self.assertEqual((undone['status'], undone['current_value']), ('undone', 'INGENIERIA APLICADA R2'))
        self.assertEqual(after['account_corrections']['unconfirmed_model_corrections'], 1)
        self.assertTrue(any(v.startswith('1 account-detail correction a model made is not confirmed') for v in after['limitations']))
        self.assertFalse(any('account-detail correction' in v for v in before['limitations']))

        report = render_ledger_report(snapshot)
        self.assertIn('<h2>Account corrections</h2>', report)
        self.assertIn('<td>LOMAS DE CHAPULTEPEC III SECCION</td><td>INGENIERIA APLICADA R2</td>', report)
        self.assertIn('Corrected by Claude · not confirmed (the model&#x27;s reading)', report)
        self.assertIn('Confirmed by Neil Byrne, entered by Claude (fin-smalls) on Neil Byrne&#x27;s instruction, 2026-10-30', report)
        self.assertIn('How confirmations were entered', report)
        self.assertIn('Undone on 2026-10-30; the original value is current', report)
        self.assertNotIn('Account corrections', render_ledger_report(self.export_before_snapshot(before)))

    @staticmethod
    def export_before_snapshot(document):
        from services.financial.ledger_snapshot import LedgerSnapshot
        return LedgerSnapshot(json.dumps(document), 'b' * 64, 0)

    def test_compact_report_marks_rows_of_a_corrected_account(self):
        from services.financial.ledger_snapshot import render_ledger_report
        row, _ = self.add(1)
        self.correct(row)
        document, _ = self.export()
        # The compact payment table (over 200 readings) names each row's account: a corrected account says so there.
        reading = document['ledger']['readings'][0]
        document['ledger']['readings'] = [dict(deepcopy(reading), row=dict(reading['row'], key=f'{index:032x}'))
                                          for index in range(201)]
        report = render_ledger_report(self.export_before_snapshot(document))
        self.assertEqual(report.count('(account number, bank, holder corrected; model reading, not confirmed; see Account '
                                      'corrections)'), 201)

    def test_only_the_captured_accounts_and_this_case(self):
        from services.financial.account_correction_provenance import capture_account_corrections
        row, _ = self.add(1)
        account = self.correct(row)
        self.assertEqual(capture_account_corrections(self.db, case_id=self.other_case.id, account_ids=[account.id])['corrections'], [])
        self.assertEqual(capture_account_corrections(self.db, case_id=self.case.id, account_ids=[])['corrections'], [])

    def test_an_account_export_with_no_rows_still_shows_its_corrections(self):
        from postgres.models.financial import FinancialAccount
        from services.financial.ledger_snapshot import _capture_history, capture_ledger_snapshot
        row, _ = self.add(1)
        account = self.correct(row)
        row.ledger_status = 'rejected'
        self.db.commit()
        empty = FinancialAccount(case_id=self.case.id, identity_key='institution_account\x1fkapital\x1f2', holder_name='R2',
                                 metadata_=dict(account_details_history=[dict(HISTORY[1])]))
        self.db.add(empty)
        self.db.commit()
        document = _capture_history(self.db, json.loads(capture_ledger_snapshot(self.db, case_id=self.case.id,
                                    account_id=empty.id).content), case_id=self.case.id)
        self.assertEqual(document['ledger']['readings'], [])
        self.assertEqual([(item['account_id'], item['field']) for item in document['account_corrections']['corrections']],
                         [(str(empty.id), 'account_number')])
        self.assertNotIn(str(account.id), {item['account_id'] for item in document['account_corrections']['corrections']})
