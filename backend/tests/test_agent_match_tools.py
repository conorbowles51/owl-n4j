"""lx-matchgrades F: the agent reads every possible match with its strength, paged with exact totals."""
from datetime import date
from unittest.mock import patch

from services.agent import graph, match_tools as M


def _row(n, direction, day, account, holder, name=None):
    return dict(id='00000000-0000-0000-0000-%012d' % n, account_id='00000000-0000-0000-0000-0000000000a%d' % account,
                source_document_id='00000000-0000-0000-0000-0000000000d%d' % account, amount_minor=500000,
                currency='USD', direction=direction, ordering_date=date(2024, 3, day), ordering_date_source='transaction',
                transaction_date=date(2024, 3, day), posted_date=None, value_date=None, effective_date=None,
                description='TRANSFER', holder=holder, institution='Synthetic Bank', identifier='1234',
                name=name, reason='', other_holders=[])


def test_transfer_pairs_lists_a_fifteen_day_pair_as_weak_and_pages_with_totals():
    rows = [_row(1, 'debit', 1, 1, 'ALPHA LLC'), _row(2, 'credit', 16, 2, 'BRAVO INC'),
            _row(3, 'credit', 2, 3, 'CHARLIE CO')]
    with patch('services.financial.payment_party_matches.case_rows', return_value=rows):
        out = M.transfer_pairs(None, 'case', limit=1)
        assert out['total'] == 2 and out['returned'] == 1 and out['has_more'] and out['next_offset'] == 1
        assert out['by_strength'] == {'strong': 0, 'moderate': 0, 'weak': 2, 'faint': 0}
        rest = M.transfer_pairs(None, 'case', offset=1, limit=1)
        weak = M.transfer_pairs(None, 'case', strength='weak')
    assert rest['returned'] == 1 and not rest['has_more']
    days = sorted(i['days_apart'] for i in weak['items'])
    assert days == [1, 15]
    item = next(i for i in weak['items'] if i['days_apart'] == 15)
    assert item['strength'] == 'weak' and '15 days apart' in item['how_well_matched']
    assert item['money_out']['financial_href'].endswith('payment=' + rows[0]['id'])


def test_the_tools_are_registered_and_the_final_answer_lists_weak_matches_as_weak():
    class Ctx:
        case_id = '00000000-0000-0000-0000-000000000001'
        significant_scope = None
        ledger_session_factory = None
    names = [t.name for t in M.make_match_tools(Ctx())]
    assert names == ['get_transfer_pairs', 'get_payment_other_legs', 'get_identity_suggestions']
    final = graph._final_answer_system_prompt()
    assert "possible transfers between accounts, a payment's possible other legs and phone identity" in final
    assert "list weak and faint ones as weak or faint rather than dropping them" in final
    for n in names:
        assert n in graph._INTERNAL_TOOL_MARKERS
    from services.agent.run_record import CATEGORY_BY_TOOL
    assert {n: CATEGORY_BY_TOOL[n] for n in names} == {'get_transfer_pairs': 'ledger', 'get_payment_other_legs': 'ledger',
                                                        'get_identity_suggestions': 'phones'}
