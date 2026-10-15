"""A review saved on a file-level reading carries to the one period a newer reading names."""
from types import SimpleNamespace

from services.financial import review_carry
from services.financial.review_carry import carry_file_level_review, conflict_problems, same_value


def proposal(statement_id='p1', **metadata):
    return dict(revision='r-new', statement_id=statement_id, currency='USD', rows=[],
                metadata={**dict(holder='', account_number='', institution='', period_start='', period_end=''), **metadata})


def saved(**request):
    base = dict(expected_revision='r-old', statement_id=None, currency='USD', holder='', account_number='',
                institution='', period_start='', period_end='', rows=[])
    return dict(request={**base, **request}, review_revision='rev-old', saved_at='2026-10-14T00:00:00+00:00',
                saved_by=dict(user_id='u1', name='Investigator'))


def file_with(record):
    return SimpleNamespace(metadata_=dict(financial_review_progress={'': record}))


def test_values_written_differently_are_the_same():
    assert same_value('institution', 'Santander', 'BANCO SANTANDER MEXICO')
    assert same_value('account_number', '12-34567890-1', '12345678901')
    assert same_value('holder', 'ALDEA INVENTADA S.A. DE C.V.', 'ALDEA INVENTADA SA DE CV')
    assert not same_value('account_number', '98-76543210-9', '12345600002')
    assert not same_value('institution', 'Santander', 'BBVA Mexico')


def test_fills_and_equivalent_values_carry_without_a_question():
    file = file_with(saved(holder='ALDEA INVENTADA SA DE CV', account_number='12-34567890-1', institution='Santander'))
    record = carry_file_level_review(file, proposal(account_number='12345678901', institution='BANCO SANTANDER MEXICO'), ['p1'])
    assert record['request']['holder'] == 'ALDEA INVENTADA SA DE CV'
    assert record['request']['account_number'] == '12-34567890-1'
    assert record['request']['expected_revision'] == 'r-new' and record['request']['statement_id'] == 'p1'
    assert 'carry_conflicts' not in record
    assert set(record['carried_from']['fields']) == {'holder', 'account_number', 'institution'}
    progress = file.metadata_['financial_review_progress']
    assert '' not in progress and progress['p1'] is record
    assert file.metadata_['financial_review_history'][-1]['review_revision'] == 'rev-old'


def test_a_value_the_reading_now_prints_differently_is_the_one_question():
    file = file_with(saved(holder='OTRA INVENTADA SA DE CV', account_number='98-76543210-9', institution='Santander'))
    p = proposal(account_number='12345600002', institution='BANCO SANTANDER MEXICO')
    record = carry_file_level_review(file, p, ['p1'])
    assert record['carry_conflicts'] == {'account_number': dict(yours='98-76543210-9', reading='12345600002')}
    assert record['request']['account_number'] == '12345600002'  # nothing chosen for her
    assert record['request']['holder'] == 'OTRA INVENTADA SA DE CV'
    problems = conflict_problems({**p, 'saved_review': record}, record['request'])
    assert [x['field'] for x in problems] == ['account_number']
    assert '98-76543210-9' in problems[0]['message'] and '12345600002' in problems[0]['message']
    # Any later save of that period answers it.
    assert conflict_problems({**p, 'saved_review': record}, {**record['request'], 'account_number': '98-76543210-9'}) == []


def test_nothing_is_carried_when_it_would_need_a_guess():
    edited = saved(rows=[dict(id='a', reason='amount corrected')])
    assert carry_file_level_review(file_with(edited), proposal(), ['p1']) is None
    assert carry_file_level_review(file_with(saved(holder='X')), proposal(), ['p1', 'p2']) is None
    assert carry_file_level_review(file_with(saved(holder='X')), proposal(statement_id=None), ['p1']) is None
    own = SimpleNamespace(metadata_=dict(financial_review_progress={'': saved(holder='X'), 'p1': saved(holder='Y')}))
    assert carry_file_level_review(own, proposal(), ['p1']) is None
