import unittest
from services.financial.ledger_exhibits import capture_ledger_exhibits
from services.financial.ledger_summary import LedgerSummaryError


def reading(key, amount, direction='credit', proof='p0', exclusion=None, currency='GBP'):
    return dict(included=exclusion is None, exclusion_reason=exclusion,
        row=dict(key=key, ref_id='TX-'+key, amount_minor=str(amount), direction=direction,
                 proof_class=proof,currency=currency),
        source=dict(id='document-'+key, evidence_file_id='file-'+key,sha256_at_ingestion='a'*64))


def document(rows, table=None):
    result=dict(export_ready=True, ledger=dict(history_captured=True,readings=rows))
    if table is not None: result['table_view']=dict(row_ids=table)
    return result


class LedgerExhibitTests(unittest.TestCase):
    def test_exact_net_composition_and_disclosure_are_bound_to_sources(self):
        result=capture_ledger_exhibits(document([reading('a',9007199254740993),reading('b',17,'debit')]))
        verified=result['sections'][0]
        self.assertEqual(verified['software_rule'],'rule_1006')
        self.assertEqual(verified['net_postings_minor'],'9007199254740976')
        self.assertEqual(verified['references'],['TX-a','TX-b'])
        self.assertEqual(sum(p['rows'] for p in verified['proof_composition']),2)
        self.assertTrue(verified['outstanding_conditions'])
        self.assertTrue(all(not s['disclosure_recorded'] for s in verified['sources']))

    def test_p3_stays_illustrative_in_working_population(self):
        sections=capture_ledger_exhibits(document([reading('a',100),reading('b',50,proof='p3',exclusion='proof_class_not_included')]))['sections']
        self.assertEqual(sections[0]['row_ids'],['a'])
        self.assertEqual(sections[0]['software_rule'],'rule_1006')
        self.assertEqual(sections[1]['row_ids'],['a','b'])
        self.assertEqual(sections[1]['software_rule'],'rule_107')
        self.assertEqual(sections[1]['net_postings_minor'],'150')
        self.assertFalse(any('below the ledger' in c for c in sections[1]['caveats']))
        self.assertTrue(any('arithmetic agrees' in c for c in sections[1]['caveats']))

    def test_empty_verified_set_is_unavailable_not_zero_evidence(self):
        sections=capture_ledger_exhibits(document([reading('a',0,proof='p3',exclusion='proof_class_not_included')]))['sections']
        self.assertFalse(sections[0]['available'])
        self.assertTrue(sections[1]['available'])
        self.assertEqual(sections[1]['net_postings_minor'],'0')

    def test_excluded_source_cannot_get_table_summary_assessment(self):
        sections=capture_ledger_exhibits(document([reading('a',100,exclusion='source_not_admitted')],['a']))['sections']
        self.assertFalse(sections[-1]['available'])
        self.assertIn('excluded',sections[-1]['reason'])

    def test_table_selection_order_and_currencies_remain_separate(self):
        rows=[reading('a',100),reading('b',300,currency='USD'),reading('c',200)]
        sections=capture_ledger_exhibits(document(rows,['c','a']))['sections']
        table=next(s for s in sections if s['population']=='table_view')
        self.assertEqual(table['row_ids'],['c','a'])
        self.assertEqual(table['net_postings_minor'],'300')
        self.assertEqual([s['currency'] for s in sections if s['population']=='verified_totals'],['GBP','USD'])

    def test_incomplete_capture_refused(self):
        source=document([reading('a',100)])
        source['ledger']['history_captured']=False
        with self.assertRaises(LedgerSummaryError):capture_ledger_exhibits(source)
