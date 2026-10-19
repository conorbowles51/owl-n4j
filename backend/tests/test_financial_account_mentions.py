from unittest import TestCase
from uuid import uuid4
from services.financial.account_mentions import mentions, account_references
from tests.test_financial_duplicates import DuplicateTestCase as Fixture
from postgres.models.enums import LedgerStatus


class AccountMentionTests(TestCase):
    def setUp(self):
        self.f = Fixture()
        self.f.setUp()

    def tearDown(self):
        self.f.tearDown()

    def payment(self, text, *, other=False, status=LedgerStatus.admitted):
        f = self.f
        case, run, account = (f.other_case, f.other_run, f.other_account) if other else (f.case, f.run, f.account)
        document = f.make_document(case=case, run=run)
        period = f.make_period(document, account=account, run=run)
        row = f.add_row(period, document, amount=100, account=account, run=run, status=status)
        row.description = text
        f.db.commit()
        return row, document

    def read(self, **kwargs):
        return account_references(self.f.db, case_id=self.f.case.id, **kwargs)

    def test_only_labelled_references_are_proposed_and_original_spans_are_retained(self):
        for text in ('Merchant 123456 +353 12345678 $10.00', 'account 2023-01-02', 'account 1234.56', 'account balance 9999', 'IBAN unknown', 'Trace 123456789'):
            self.assertEqual(mentions(text), [], text)
        text = 'Transfer to account 1234567890, Card ending in ****8160; Share 0040.'
        refs = mentions(text)
        self.assertEqual([r['value'] for r in refs], ['1234567890', '****8160', '0040'])
        self.assertEqual([r['partial'] for r in refs], [False, True, True])
        for item in refs:
            self.assertEqual(text[item['start']:item['end']], item['printed'])
        iban = mentions('Account GB82 WEST 1234 5698 7654 32 Invoice 4050')[0]
        self.assertEqual(iban['normalised'], 'GB82WEST12345698765432')
        self.assertEqual(iban['printed'], 'Account GB82 WEST 1234 5698 7654 32')

    def test_grouped_payments_are_complete_and_case_and_disposition_scoped(self):
        first, first_source = self.payment('Transfer to account 1234567890')
        first.counterparty_raw = 'Account 1234567890'; self.f.db.commit()
        second, _ = self.payment('Payment from acct 1234567890')
        # PDF imports accepted by the user remain P3. They must be searchable
        # here just like automatically admitted structured records.
        first.proof_class = 'p3'
        first_source.proof_class = 'p3'
        self.f.db.commit()
        self.payment('Payment to account 9999999999', other=True)
        self.payment('Account 8888888888', status=LedgerStatus.rejected)
        _, excluded = self.payment('Account 7777777777'); excluded.status = 'superseded'; self.f.db.commit()
        result = self.read()
        self.assertEqual(result['scanned_payments'], 2)
        self.assertEqual(result['missing_count'], 1)
        self.assertEqual(result['items'][0]['payment_count'], 2)
        self.assertEqual(set(result['items'][0]['payment_ids']), {str(first.id), str(second.id)})
        self.assertEqual(self.read(search='not present')['total'], 0)
        self.assertEqual(account_references(self.f.db, case_id=uuid4())['items'], [])

    def test_possible_statement_is_not_an_identity_decision_and_missing_periods_stay_visible(self):
        self.f.account.identifier_as_printed = '1234567890'
        self.f.db.commit()
        self.payment('Transfer to account 1234567890 and card ending in ****7890')
        result = self.read(show='all')
        self.assertEqual(result['possible_match_count'], 2)
        self.assertEqual(self.read()['total'], 0)
        for item in result['items']:
            self.assertEqual(item['status'], 'possible_statement')
            self.assertEqual(item['possible_accounts'][0]['account_id'], str(self.f.account.id))
        bare = self.f._account(self.f.case.id, identity_key='synthetic-missing-statements')
        bare.identifier_as_printed = '5566778899'
        self.f.db.add(bare); self.f.db.commit()
        self.payment('Transfer to account 5566778899')
        item = self.read()['items'][0]
        self.assertEqual(item['status'], 'no_statement_found')
        self.assertEqual(item['possible_accounts'][0]['statement_count'], 0)

    def test_pagination_and_corrections_change_the_reference_list(self):
        row, _ = self.payment(' '.join(f'Account {10000000+n};' for n in range(28)))
        first, second = self.read(), self.read(offset=25)
        self.assertEqual(first['total'], 28)
        self.assertEqual(len(first['items']), 25)
        self.assertEqual(len(second['items']), 3)
        self.assertFalse(set(i['id'] for i in first['items']) & set(i['id'] for i in second['items']))
        row.description = 'Payment to account 5000999911'; self.f.db.commit()
        changed = self.read()
        self.assertNotEqual(changed['revision'], first['revision'])
        self.assertEqual(changed['total'], 1)
        self.assertEqual(changed['items'][0]['reference'], '5000999911')
