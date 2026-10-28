import unittest

from services.financial.party_coverage import BARE, NAMED, REASON, bank_of, classify, compare, tally


def row(description, direction='debit', institution='Example Bank', account_type='checking', raw=None, labels=None, case='c1'):
    return dict(case_id=case, description=description, direction=direction, institution_name=institution,
                account_type=account_type, counterparty_raw=raw, labels=labels)


class PartyCoverageTests(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(classify(**{k: v for k, v in _args(row('DEPOSIT', raw='ACME LLC')).items()}), NAMED)
        self.assertEqual(classify(**_args(row('XQZ 123', labels={'to_name': 'Jane Example'}))), NAMED)
        self.assertEqual(classify(**_args(row('XQZ 123', labels={'counterparty_link': {'kind': 'party', 'id': 'p', 'label': 'P'}}))), NAMED)
        self.assertEqual(classify(**_args(row('Withdrawal Online Banking Transfer To RANDOLPH-SCHONEC xxxxxxxxxx Share 0040'))), NAMED)
        self.assertEqual(classify(**_args(row('W01 TRASPASO A TERCEROS 0001234 BMRCASH Ref. REFBNTC00123'))), REASON)
        self.assertEqual(classify(**_args(row('XQZ 123'))), BARE)
        # A person's label on the other side only.
        self.assertEqual(classify(**_args(row('XQZ 123', labels={'from_name': 'Holder'}))), BARE)

    def test_bank_of(self):
        self.assertEqual(bank_of('Banco Santander Mexico'), 'SANTANDER')
        self.assertEqual(bank_of('BBVA Mexico'), 'BBVA')
        self.assertEqual(bank_of(None), 'UNKNOWN')

    def test_gate_fails_on_a_rise_and_on_a_new_mostly_bare_layout(self):
        baseline = tally([row('XQZ 1')] * 2 + [row('ACME', raw='ACME')] * 38)          # 5% bare
        same = tally([row('XQZ 1')] * 2 + [row('ACME', raw='ACME')] * 38)
        self.assertEqual(compare(same, baseline), [])
        worse = tally([row('XQZ 1')] * 4 + [row('ACME', raw='ACME')] * 36)              # 10% bare
        failures = compare(worse, baseline)
        self.assertEqual(len(failures), 1)
        self.assertIn('EXAMPLE', failures[0])
        # A layout the baseline never saw, mostly bare, fails even where the bank's share is unchanged overall.
        new = tally([row('XQZ 1')] * 2 + [row('ACME', raw='ACME')] * 38 + [row('XQZ 1', account_type='credit_card')] * 30)
        self.assertTrue(any('EXAMPLE/credit_card' in f and 'newly read layout' in f for f in compare(new, baseline)))
        # Small banks never fail.
        self.assertEqual(compare(tally([row('XQZ 1', institution='Tiny Bank')] * 5), baseline), [])


def _args(r):
    return dict(description=r['description'], direction=r['direction'], account_type=r['account_type'],
                institution=r['institution_name'], counterparty_raw=r['counterparty_raw'], labels=r['labels'])


if __name__ == '__main__':
    unittest.main()
