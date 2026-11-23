"""lx-relevancetest D: the live relevance watch's day numbers and its noise-aware alert rule."""
import importlib.util
import os
from datetime import date, timedelta

_spec = importlib.util.spec_from_file_location('watch_agent_relevance', os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts', 'watch_agent_relevance.py'))
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)

TODAY = date(2026, 11, 20)


def _day(day, runs, empty_every, cite_used=True, cypher_bad=0):
    rs, cs = [], []
    for i in range(runs):
        rid = '%s-%d' % (day, i)
        rs.append(dict(id=rid, day=day, final_answer='see rec://a%d' % i if cite_used else 'no citations'))
        for j in range(4):
            cs.append(dict(run_id=rid, name='search_case', status='success', returned=0 if (j % empty_every == 0) else 3,
                           total=None, preview='{"cite": "rec://a%d"}' % i))
        cs.append(dict(run_id=rid, name='run_readonly_cypher', status='error' if i < cypher_bad else 'success',
                       returned=None, total=None, preview=None))
    return rs, cs


def _metrics(days):
    rs, cs = [], []
    for d in days:
        r, c = _day(*d)
        rs += r
        cs += c
    return W.day_metrics(rs, cs)


def test_day_numbers():
    m = _metrics([(TODAY - timedelta(days=1), 10, 2, True, 3)])[TODAY - timedelta(days=1)]
    assert m['runs'] == 10 and m['search_calls'] == 40
    assert m['empty_share'] == 0.5 and m['used_share'] == 1.0
    assert m['refused_share'] == 0.3 and m['lookups_median'] == 5


def test_a_number_outside_the_week_before_is_sent_to_its_owner():
    days = [(TODAY - timedelta(days=k), 10, 4) for k in range(2, 6)] + [(TODAY - timedelta(days=1), 10, 1)]
    alerts = W.worsened(_metrics(days), TODAY)
    assert [a['metric'] for a in alerts] == ['empty_share']
    assert alerts[0]['owner'] == 'lx-casesearch' and alerts[0]['value'] == 1.0
    assert 'lx-casesearch' not in W.alert_text(alerts[0]) and 'empty searches worsened' in W.alert_text(alerts[0])


def test_no_alert_inside_the_range_or_with_too_few_days_or_answers():
    same = [(TODAY - timedelta(days=k), 10, 4) for k in range(1, 6)]
    assert W.worsened(_metrics(same), TODAY) == []
    short = [(TODAY - timedelta(days=k), 10, 4) for k in range(2, 4)] + [(TODAY - timedelta(days=1), 10, 1)]
    assert W.worsened(_metrics(short), TODAY) == []
    thin_day = [(TODAY - timedelta(days=k), 10, 4) for k in range(2, 6)] + [(TODAY - timedelta(days=1), 3, 1)]
    assert W.worsened(_metrics(thin_day), TODAY) == []
    # today is never judged: it is not complete
    today = [(TODAY - timedelta(days=k), 10, 4) for k in range(1, 5)] + [(TODAY, 10, 1)]
    assert W.worsened(_metrics(today), TODAY) == []


def test_board_shows_each_day_and_the_alert():
    days = [(TODAY - timedelta(days=k), 10, 4) for k in range(2, 6)] + [(TODAY - timedelta(days=1), 10, 1)]
    m = _metrics(days)
    lines = W.board_lines(m, {'search_case': dict(calls=10, empty=5)}, W.worsened(m, TODAY), TODAY)
    assert lines[0].startswith('| Day (UTC) |') and len([x for x in lines if x.startswith('| 2026-')]) == 5
    assert any('search_case 5 of 10' in x for x in lines) and any('sent to lx-casesearch' in x for x in lines)


def _score(rank):
    found = ['R'] if rank and rank <= 10 else []
    return dict(units=10, zero=False, relevant=1, ranks={'R': rank}, first_relevant=rank, rr=1.0 / rank if rank else 0,
                decoy_ranks={}, decoys_top10=[], found_at_10=found, recall_at_10=len(found), found_at_50=found,
                recall_at_50=len(found))


def _origin(at, sha, ranks, kind='meaning', set_hash='s1'):
    return dict(meta=dict(at=at, sha=sha, set_hash=set_hash), runs=[dict(queries={
        'demo:q%d' % i: dict(kind=kind, tool='search_by_meaning', case='demo', score=_score(r))
        for i, r in enumerate(ranks)})])


def test_origin_drift_from_data_alone_goes_to_the_owner():
    # Same code, the data moved: 17 Nov 07:35 to 09:31 meaning MRR fell 0.58 to 0.44 and the gate (both sides on the
    # same data) never saw it.
    before = _origin('2026-11-17T07:35:00Z', 'd9dadc843704', [1, 1, 2, 4, 1, 3])
    after = _origin('2026-11-17T09:31:00Z', '97dba47b113c', [2, 2, 4, 16, 2, 11])
    out = W.origin_drift([after, before])
    assert [d['kind'] for d in out] == ['meaning']
    d = out[0]
    assert d['owner'] == 'lx-embedall' and d['prev_sha'] == 'd9dadc843704' and d['sha'] == '97dba47b113c'
    assert set(d['fell']) == {'mrr', 'recall_at_10'}
    assert d['out_of_top10'] == ['demo:q3 R', 'demo:q5 R']
    text = W.drift_text(d)
    assert 'mrr 0.68 to 0.32' in text and 'recall@10 1.00 to 0.67' in text and 'd9dadc843704..97dba47b113c' in text
    lines = W.board_lines({}, {}, [], TODAY, out)
    assert any('Origin meaning search fell' in x and 'lx-embedall' in x for x in lines)


def test_origin_drift_ignores_noise_small_kinds_other_sets_and_queries_one_side_lacks():
    base = _origin('2026-11-17T07:00:00Z', 'a', [1, 1, 2, 4, 1, 3])
    assert W.origin_drift([base, _origin('2026-11-17T08:00:00Z', 'a', [1, 1, 2, 4, 1, 3])]) == []
    assert W.origin_drift([base, _origin('2026-11-17T08:00:00Z', 'b', [1, 1, 2, 5, 1, 3])]) == []  # 0.01 is noise
    small = _origin('2026-11-17T07:00:00Z', 'a', [1, 1, 1], kind='exact')
    assert W.origin_drift([small, _origin('2026-11-17T08:00:00Z', 'b', [9, 9, 9], kind='exact')]) == []
    assert W.origin_drift([base, _origin('2026-11-17T08:00:00Z', 'b', [9] * 6, set_hash='s2')]) == []
    grown = _origin('2026-11-17T08:00:00Z', 'b', [1, 1, 2, 4, 1, 3])
    grown['runs'][0]['queries']['demo:new'] = dict(kind='meaning', score=_score(None))
    assert W.origin_drift([base, grown]) == []
    rejudged = _origin('2026-11-17T08:00:00Z', 'b', [9] * 6)
    for q in rejudged['runs'][0]['queries'].values():
        q['score']['ranks']['F-other-area'] = None  # more records judged (cross-area carriers), not a worse search
    assert W.origin_drift([base, rejudged]) == []
    phones = W.origin_drift([_origin('2026-11-17T07:00:00Z', 'a', [1] * 6, kind='phones'),
                             _origin('2026-11-17T08:00:00Z', 'b', [3] * 6, kind='phones')])
    assert [d['owner'] for d in phones] == ['lx-casesearch']


def test_follow_ups_do_not_move_the_lookups_median():
    # a day of 10 opening questions (5 lookups each) plus 20 follow-ups (3 lookups each)
    rs, cs = _day(TODAY - timedelta(days=1), 10, 1)
    for i in range(20):
        rid = 'f%d' % i
        rs.append(dict(id=rid, day=TODAY - timedelta(days=1), final_answer='x', follow_up=True))
        cs += [dict(run_id=rid, name='get_ledger', status='success', returned=1, total=1, preview=None)] * 3
    m = W.day_metrics(rs, cs)[TODAY - timedelta(days=1)]
    assert m['lookups_median'] == 5 and m['runs'] == 30
