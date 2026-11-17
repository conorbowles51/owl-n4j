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
