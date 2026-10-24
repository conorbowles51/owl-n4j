"""Overlapping movement queries count each movement once (statement_overlap_trim, Neil 2026-10-24).

Invented figures only. A query is trimmed against a SAVED statement of its
account only where the overlap's movements are the same one for one (date,
amount, direction, running balance) and every remaining check still agrees;
anything else is held with its reason.
"""
from datetime import date
from unittest import TestCase
from unittest.mock import patch

from services.financial import statement_overlap_trim as trim
from services.financial.review_arithmetic import arithmetic_checks
from services.financial.statement_import_overlap import later_queries_trim_themselves

# (date, credit/debit, amount, running balance after it); opening 1,000.00
MOVES = [('2024-01-03', 'credit', 50000, 150000), ('2024-01-05', 'debit', 20000, 130000),
         ('2024-01-10', 'debit', 10000, 120000), ('2024-01-12', 'credit', 5000, 125000),
         ('2024-01-20', 'debit', 25000, 100000)]


def control(row_id, kind, description, balance, **fields):
    return dict(id=row_id, kind=kind, excluded=True, issues=[], page_number=1, table_index=0, row_index=0,
                fields=dict(description=description, balance=str(balance), **fields))


def query(moves=MOVES, opening=100000):
    rows = [control('open', 'balance', 'Opening Balance', opening, balance_basis='printed_opening_after_first_movement'),
            control('close', 'balance', 'Closing Balance', moves[-1][3]),
            control('in', 'statement_total', 'Total credit', sum(m[2] for m in moves if m[1] == 'credit'),
                    total_direction='credit'),
            control('out', 'statement_total', 'Total debit', sum(m[2] for m in moves if m[1] == 'debit'),
                    total_direction='debit')]
    for index, (day, direction, amount, balance) in enumerate(moves):
        rows.append(dict(id=f'm{index}', kind='transaction', excluded=False, issues=[], page_number=1, table_index=0,
                         row_index=index + 1, fields=dict(date=day, direction=direction, amount_minor=str(amount),
                                                          balance=str(balance), description='Movement')))
    return rows


def saved(start, end, moves, document='doc-1'):
    return dict(source_document_id=document, evidence_file_id='file-' + document,
                period_start=date.fromisoformat(start), period_end=date.fromisoformat(end),
                movements=[(date.fromisoformat(d), amount, direction, balance) for d, direction, amount, balance in moves])


START, END = date(2024, 1, 1), date(2024, 1, 31)


def plan(neighbours, rows=None):
    return trim.plan_trim(rows or query(), start=START, end=END, neighbours=neighbours)


class PlanTests(TestCase):
    def test_nothing_saved_nothing_to_trim(self):
        self.assertIsNone(plan([]))

    def test_a_saved_movement_outside_its_own_period_holds_the_query(self):
        # The saved statement carries a movement dated after its own end (inside the query's kept dates):
        # trimming would count it twice.
        neighbour = saved('2023-12-15', '2024-01-05', MOVES[:2])
        neighbour['movements'].append((date(2024, 1, 10), 10000, 'debit', 120000))
        self.assertEqual(plan([neighbour]), ('held', 'movements_differ'))
        undated = saved('2023-12-15', '2024-01-05', MOVES[:2])
        undated['movements'].append((None, 10000, 'debit', 120000))
        self.assertEqual(plan([undated]), ('held', 'movements_differ'))

    def test_saved_start_trims_the_query_and_derives_its_opening(self):
        kind, result = plan([saved('2023-12-15', '2024-01-05', MOVES[:2])])
        self.assertEqual(kind, 'trim')
        self.assertEqual((result['period_start'], result['period_end']), ('2024-01-06', '2024-01-31'))
        self.assertEqual((result['before'], result['after']), (['m0', 'm1'], []))
        self.assertEqual((result['opening_minor'], result['closing_minor']), ('130000', '100000'))

    def test_saved_end_trims_the_query_and_derives_its_closing(self):
        kind, result = plan([saved('2024-01-12', '2024-02-28', MOVES[3:])])
        self.assertEqual(kind, 'trim')
        self.assertEqual((result['period_start'], result['period_end']), ('2024-01-01', '2024-01-11'))
        self.assertEqual((result['after'], result['opening_minor'], result['closing_minor']), (['m3', 'm4'], '100000', '120000'))

    def test_both_ends(self):
        kind, result = plan([saved('2023-12-01', '2024-01-03', MOVES[:1], 'a'), saved('2024-01-20', '2024-02-10', MOVES[4:], 'b')])
        self.assertEqual((kind, result['period_start'], result['period_end']), ('trim', '2024-01-04', '2024-01-19'))
        self.assertEqual(len(result['covers']), 2)

    def test_any_difference_in_the_overlap_holds(self):
        for changed in ((MOVES[0][0], 'credit', 50001, 150001), (MOVES[0][0], 'debit', 50000, 150000),
                        ('2024-01-04', 'credit', 50000, 150000), (MOVES[0][0], 'credit', 50000, 150001)):
            with self.subTest(changed=changed):
                self.assertEqual(plan([saved('2023-12-15', '2024-01-05', [changed, MOVES[1]])]), ('held', 'movements_differ'))
        # One movement fewer or one more on the saved side.
        self.assertEqual(plan([saved('2023-12-15', '2024-01-05', MOVES[:1])]), ('held', 'movements_differ'))
        self.assertEqual(plan([saved('2023-12-15', '2024-01-05', MOVES[:2] + [('2024-01-04', 'debit', 1, 129999)])]),
                         ('held', 'movements_differ'))

    def test_a_missing_running_balance_holds(self):
        neighbour = saved('2023-12-15', '2024-01-05', MOVES[:2])
        neighbour['movements'][0] = neighbour['movements'][0][:3] + (None,)
        self.assertEqual(plan([neighbour]), ('held', 'balance_missing'))

    def test_a_cover_in_the_middle_holds(self):
        self.assertEqual(plan([saved('2024-01-09', '2024-01-11', MOVES[2:3])]), ('held', 'covered_in_middle'))

    def test_every_date_saved_with_the_same_movements_is_wholly_counted(self):
        self.assertEqual(plan([saved('2023-12-01', '2024-02-28', MOVES)]), ('held', 'fully_covered'))
        self.assertEqual(plan([saved('2023-12-01', '2024-02-28', MOVES[:4])]), ('held', 'movements_differ'))

    def test_an_unread_movement_is_never_trimmed(self):
        rows = query()
        rows[-1]['issues'] = ['Check this amount.']
        self.assertIsNone(plan([saved('2023-12-15', '2024-01-05', MOVES[:2])], rows))

    def test_printed_figures_that_do_not_prove_the_whole_query_hold(self):
        rows = query()
        next(r for r in rows if r['id'] == 'in')['fields']['balance'] = '1'
        self.assertEqual(plan([saved('2023-12-15', '2024-01-05', MOVES[:2])], rows), ('held', 'checks_differ'))


class ApplyTests(TestCase):
    def test_trimmed_rows_are_kept_excluded_and_cited_and_the_rest_reconciles(self):
        rows = query()
        kind, result = trim.plan_trim(rows, start=START, end=END,
                                      neighbours=[saved('2023-12-15', '2024-01-05', MOVES[:2]),
                                                  saved('2024-01-20', '2024-02-10', MOVES[4:], 'doc-2')])
        trimmed = trim.apply_trim(rows, result)
        by_id = {r['id']: r for r in trimmed}
        self.assertEqual(len(trimmed), len(rows))  # nothing deleted
        for row_id, document in (('m0', 'doc-1'), ('m1', 'doc-1'), ('m4', 'doc-2')):
            self.assertTrue(by_id[row_id]['excluded'])
            self.assertEqual(by_id[row_id]['fields']['covered_by']['source_document_id'], document)
            self.assertTrue(by_id[row_id]['covered_reason'].startswith('Counted once:'))
        self.assertFalse(any(by_id[i]['excluded'] for i in ('m2', 'm3')))
        opening, closing = by_id['open']['fields'], by_id['close']['fields']
        self.assertEqual((opening['balance'], opening['balance_basis']), ('130000', trim.OPENING_BASIS))
        self.assertEqual(opening['balance_derivation']['trimmed_from'], '100000')
        self.assertEqual((closing['balance'], closing['balance_basis']), ('125000', trim.CLOSING_BASIS))
        self.assertEqual(closing['balance_derivation']['printed_closing_minor'], '100000')
        self.assertEqual((by_id['in']['fields']['balance'], by_id['in']['fields']['printed_total_minor']), ('5000', '55000'))
        self.assertEqual(by_id['out']['fields']['balance'], '10000')
        checks = arithmetic_checks(trimmed)
        self.assertTrue(checks)
        self.assertFalse([c for c in checks if c['status'] == 'difference'])
        self.assertEqual(rows[4]['excluded'], False)  # the reading passed in is not changed


class OverlapTrimTests(TestCase):
    def test_only_movement_queries_and_the_switch(self):
        rows = query()
        self.assertEqual(trim.overlap_trim(None, case_id=None, file=None, selected=dict(form='monthly'), rows=rows,
                                           metadata={}, currency='MXN', statement_id=None, current=None), (rows, None))
        with patch.object(trim, 'TRIM_OVERLAPS', False):
            self.assertEqual(trim.overlap_trim(None, case_id=None, file=None, selected=dict(form='movement_query'),
                                               rows=rows, metadata={}, currency='MXN', statement_id=None,
                                               current=None), (rows, None))


class LaterQueriesTests(TestCase):
    def review(self, *candidates):
        return dict(available=True, revision='r', candidates=list(candidates), matching_statement=False)

    def candidate(self, start, end, status='awaiting_import', form='movement_query', file_id='f2', matching=False):
        return dict(period_start=start, period_end=end, status=status, statement_form=form, file_id=file_id,
                    statement_id='s', matching_statement=matching)

    def test_a_later_waiting_query_trims_itself_so_the_first_is_not_held(self):
        own = dict(period_start='2024-01-01', period_end='2024-01-31')
        later = self.candidate('2024-01-20', '2024-02-28')
        earlier = self.candidate('2023-12-15', '2024-01-05')
        saved_one = self.candidate('2024-01-20', '2024-02-28', status='imported')
        monthly = self.candidate('2024-01-20', '2024-02-28', form=None)
        copy = self.candidate('2024-01-20', '2024-02-28', matching=True)
        result = later_queries_trim_themselves(self.review(later, earlier, saved_one, monthly, copy), own,
                                               file_id='f1', statement_id='s', summary=dict(statement_form='movement_query'))
        self.assertEqual(result['candidates'], [earlier, saved_one, monthly, copy])
        self.assertEqual(result['later_queries'], 1)

    def test_other_statements_keep_every_candidate(self):
        review = self.review(self.candidate('2024-01-20', '2024-02-28'))
        self.assertIs(later_queries_trim_themselves(review, dict(period_start='2024-01-01', period_end='2024-01-31'),
                                                    file_id='f1', statement_id='s', summary={}), review)
