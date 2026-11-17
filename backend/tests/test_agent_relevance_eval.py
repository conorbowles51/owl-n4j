"""lx-relevancetest A-C: the relevance measures, the report tests and the noise-aware gate.

Loads relevance_eval and the runner by file path: neither imports the backend at module level, so these tests need
no database and no model. The judged sets and rubrics are checked for shape here and against the demo bytes in
evidence-engine/tests/relevance/test_relevance_sets.py.
"""
import copy
import importlib.util
import json
import os
import re

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(BACKEND)
REL = os.path.join(REPO, 'evidence-engine', 'tests', 'relevance')


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R = _load('relevance_eval_t', os.path.join(BACKEND, 'services', 'agent', 'relevance_eval.py'))
G = _load('relevance_gate_t', os.path.join(BACKEND, 'scripts', 'financial_agent_relevance.py'))


# ---- units and per-query scores ----------------------------------------------------------------------------------

def test_units_follow_the_order_the_model_reads_and_stop_at_a_record():
    payload = {'result_id': 'res_1', 'data': {
        'by_meaning': {'items': [{'title': 'a.pdf', 'snippet': 'first'}]},
        'groups': [{'group': 'messages', 'total': 0}],
        'items': [{'kind': 'message', 'snippet': {'match': 'second'}, 'links': [{'id': 'x'}]},
                  {'kind': 'document', 'title': 'third'}],
        'totals': [{'currency': 'USD'}]}}
    units = R.result_units(payload)
    assert [R.unit_text(u).split('"')[3] for u in units] == ['a.pdf', 'message', 'document']
    assert R.result_units({'data': {'items': []}}) == []


def test_matching_ignores_case_spacing_and_quote_style():
    t = R.unit_text({'body': 'Unit’s  OPEN'})
    assert R.matches(t, {'any': ["unit's open"]})
    assert R.matches(t, {'all': ['unit', 'open']})
    assert not R.matches(t, {'all': ['unit', 'closed']})
    assert not R.matches(t, {})


def test_score_query_ranks_recall_and_decoys():
    texts = [R.norm(x) for x in ['noise', 'decoy here', 'relevant one', 'noise'] + ['noise'] * 20 + ['relevant two']]
    s = R.score_query(texts, [{'id': 'a', 'any': ['relevant one']}, {'id': 'b', 'any': ['relevant two']},
                              {'id': 'c', 'any': ['never returned']}], [{'id': 'd', 'any': ['decoy']}])
    assert s['ranks'] == {'a': 3, 'b': 25, 'c': None}
    assert s['first_relevant'] == 3 and abs(s['rr'] - 1 / 3) < 1e-9
    assert s['recall_at_10'] == pytest.approx(1 / 3) and s['recall_at_50'] == pytest.approx(2 / 3)
    assert s['decoys_top10'] == ['d'] and not s['zero']
    z = R.score_query([], [{'id': 'a', 'any': ['x']}])
    assert z['zero'] and z['recall_at_10'] == 0 and z['first_relevant'] is None


def test_aggregate_is_micro_recall_and_counts_errors_and_zeros():
    a = R.score_query([R.norm('hit')], [{'id': 'a', 'any': ['hit']}, {'id': 'b', 'any': ['miss']}])
    b = R.score_query([], [{'id': 'c', 'any': ['x']}])
    agg = R.aggregate([dict(kind='phones', score=a), dict(kind='phones', score=b), dict(kind='ledger', error='boom')])
    assert agg['phones']['recall_at_10'] == pytest.approx(1 / 3, abs=1e-4)
    assert agg['phones']['zero_rate'] == 0.5 and agg['phones']['mrr'] == 0.5
    assert agg['ledger']['errors'] == 1 and agg['all']['queries'] == 3


# ---- the gate ----------------------------------------------------------------------------------------------------

def _run(found_b=True, decoy=False, extra_noise=None):
    """One run of two queries; ``found_b`` plants (or removes) a relevant record."""
    texts1 = [R.norm('alpha record')] + ([R.norm('decoy')] if decoy else [])
    texts2 = [R.norm('noise')] * 4 + ([R.norm('beta record')] if found_b else [])
    q = {'demo:q1': dict(kind='phones', score=R.score_query(texts1, [{'id': 'A', 'any': ['alpha']}],
                                                            [{'id': 'D', 'any': ['decoy']}])),
         'demo:q2': dict(kind='ledger', score=R.score_query(texts2, [{'id': 'B', 'any': ['beta']}]))}
    if extra_noise is not None:
        texts3 = [R.norm('noise')] * extra_noise + [R.norm('gamma record')]
        q['demo:q3'] = dict(kind='meaning', score=R.score_query(texts3, [{'id': 'C', 'any': ['gamma']}]))
    return dict(queries=q, aggregate=R.aggregate(q.values()))


def test_identical_runs_pass():
    cmp = R.compare([_run(), _run()], [_run(), _run()])
    assert cmp['verdict'] == 'PASS' and not cmp['losses'] and not cmp['lost_records']


def test_gate_fails_a_planted_regression():
    """The planted regression: the candidate no longer finds a record every baseline run found."""
    cmp = R.compare([_run()], [_run(found_b=False)])
    assert cmp['verdict'] == 'FAIL'
    assert cmp['lost_records'] == [dict(query='demo:q2', record='B', why='found before, not found now')]
    assert any(e['kind'] == 'ledger' and e['metric'] == 'recall_at_10' for e in cmp['losses'])
    lines = R.verdict_lines(cmp, _run()['aggregate'], _run(found_b=False)['aggregate'])
    assert lines[0].startswith('retrieval gate: FAIL') and any(x.startswith('LOST demo:q2 B') for x in lines)


def test_gate_fails_a_new_decoy_in_the_top_ten():
    cmp = R.compare([_run(), _run()], [_run(decoy=True), _run(decoy=True)])
    assert cmp['verdict'] == 'FAIL'
    assert any(e['metric'] == 'decoys_top10' for e in cmp['losses'])


def test_a_difference_inside_the_spread_of_same_settings_runs_is_not_a_loss():
    """A model step (reranking) moves a record between rank 1 and rank 3 from run to run: noise, not a loss."""
    base = [_run(extra_noise=0), _run(extra_noise=2), _run(extra_noise=0)]
    cand = [_run(extra_noise=2), _run(extra_noise=0), _run(extra_noise=2)]
    cmp = R.compare(base, cand)
    assert cmp['verdict'] == 'PASS', cmp
    # The same drop on single runs with no spread is a loss.
    assert R.compare([_run(extra_noise=0)], [_run(extra_noise=2)])['verdict'] == 'FAIL'


def test_a_crashing_candidate_tool_loses_the_records_it_found():
    cand = _run()
    cand['queries']['demo:q1'] = dict(kind='phones', error='TypeError: boom')
    cand['aggregate'] = R.aggregate(cand['queries'].values())
    cmp = R.compare([_run()], [cand])
    assert cmp['verdict'] == 'FAIL' and cmp['lost_records'][0]['why'] == "the candidate's tool failed"


def test_compare_command_exits_one_on_a_planted_regression(tmp_path):
    base, cand = tmp_path / 'b.json', tmp_path / 'c.json'
    base.write_text(json.dumps(dict(meta={}, runs=[_run()])))
    cand.write_text(json.dumps(dict(meta={}, runs=[_run(found_b=False)])))
    assert G.main(['compare', '--base', str(base), '--cand', str(cand)]) == 1
    cand.write_text(json.dumps(dict(meta={}, runs=[_run()])))
    assert G.main(['compare', '--base', str(base), '--cand', str(cand)]) == 0


# ---- the judged sets ---------------------------------------------------------------------------------------------

KINDS = {'phones', 'documents', 'exact', 'ledger', 'graph', 'timeline', 'casework', 'meaning', 'case_search'}


def _sets():
    return [json.load(open(p)) for p in G.existing_sets()]


def test_judged_sets_are_well_formed():
    sets = _sets()
    assert sets, 'no judged set found'
    for s in sets:
        ids = [q['id'] for q in s['queries']]
        assert len(ids) == len(set(ids))
        assert s['case_id'] is None or re.fullmatch(r'[0-9a-f-]{36}', s['case_id'])
        for q in G.expand(s):
            assert q['kind'] in KINDS and q['tool'] and isinstance(q['args'], dict)
            for item in (q.get('relevant') or []) + (q.get('decoys') or []):
                assert item['id'] and (item.get('any') or item.get('all'))
        kinds = {q['kind'] for q in s['queries']}
        assert {'phones', 'documents', 'ledger', 'graph', 'timeline'} <= kinds
        assert any(q.get('decoys') for q in s['queries']), 'a set needs hard negatives'
    assert len(sets) >= 2, 'the demo case and a second invented case'
    assert {'casework'} <= {q['kind'] for s in sets for q in s['queries']}


def test_every_search_kind_is_also_run_through_meaning_search():
    demo = json.load(open(os.path.join(REL, 'demo-relevance-set.json')))
    extra = G.expand(demo)
    assert any(q['kind'] == 'meaning' and q['tool'] == 'search_by_meaning' for q in extra)
    q = next(q for q in extra if q['id'] == 'meaning~led-storage')
    assert q['args'] == {'limit': 50, 'query': 'storage'}


# ---- reports -----------------------------------------------------------------------------------------------------

SAMPLE = os.path.join(REL, 'sample-phone-report.md')


def test_the_sample_report_is_the_standard_and_passes():
    s = R.score_report(open(SAMPLE).read(), G.rubric('R1'))
    assert s['passed'], s['fails_because']
    assert s['facts_found'] >= 15 and not s['decoys_wrong']
    assert {'F03', 'F04', 'F05'} <= set(s['found'])


THIN = """Six phones were extracted. Phone 3 is the prepaid phone found in the tow truck.

| Phone | Owner |
|---|---|
| Phone 1 | Mateo Ruiz |
| Phone 2 | Travis Kell |

Phone 3 often sits near Phone 2 in the evenings, which suggests the two travelled together (rec://a1b2c3d4).
Kell and Okafor message each other on Telegram (rec://e5f6a7b8). No other suspicious communications were found."""


def test_a_thin_report_fails():
    s = R.score_report(THIN, G.rubric('R1'))
    assert not s['passed']
    assert s['facts_found'] < 15 and any('misses F03' in r for r in s['fails_because'])


def test_a_report_with_the_facts_but_no_citations_or_reasons_fails():
    bare = re.sub(R.CITATION, '', open(SAMPLE).read())
    bare = re.sub(R.WHY, 'and', bare)
    s = R.score_report(bare, G.rubric('R1'))
    assert not s['passed']
    assert any('cited' in r for r in s['fails_because']) and any('say why' in r for r in s['fails_because'])


def test_a_linked_decoy_fails_the_report():
    s = R.score_report(open(SAMPLE).read() + '\n\nCurtis Fallowby is the owner of the prepaid phone.', G.rubric('R1'))
    assert 'F29' in s['decoys_wrong'] and not s['passed']


def test_report_rubrics_cover_phones_money_and_documents():
    for rid in ('R1', 'R2', 'R3'):
        rb = G.rubric(rid)
        assert rb['question'] and rb['facts'] and rb['decoys'] and rb['pass']['facts_min'] <= len(rb['facts'])
        for fid in rb['pass'].get('must_state') or []:
            assert fid in {f['id'] for f in rb['facts']}


def test_report_comparison_is_noise_aware():
    rb = G.rubric('R1')
    full = R.score_report(open(SAMPLE).read(), rb)
    thin = R.score_report(THIN, rb)
    assert R.compare_reports([full, full, full], [full, full, full])['verdict'] == 'PASS'
    worse = R.compare_reports([full, full, full], [thin, thin, thin])
    assert worse['verdict'] == 'FAIL' and 'F03' in worse['lost_facts']
    # A fact stated in one baseline run of three and in no candidate run is inside the noise, not lost.
    mixed = copy.deepcopy(full)
    mixed['found'] = [f for f in full['found'] if f != 'F43']
    mixed['missed'] = full['missed'] + ['F43']
    mixed['facts_found'] -= 1
    assert R.compare_reports([full, mixed, mixed], [mixed, mixed, full])['verdict'] == 'PASS'


def test_report_scorer_agrees_with_the_walk_scorer_on_words_and_dates():
    """expect_hit is journeys/demo-key-score.mjs expectHit (cases in journeys/demo-key-score-cases.json)."""
    cases = json.load(open(os.path.join(REPO, 'frontend_v2', 'journeys', 'demo-key-score-cases.json')))
    rows = cases.get('cases') if isinstance(cases, dict) else None
    if not rows:
        pytest.skip('no expect_hit cases in demo-key-score-cases.json')
    for row in rows:
        assert R.expect_hit(row['term'], row['text']) == row['hit'], row


def test_a_fuller_report_that_cites_a_smaller_share_is_not_a_loss():
    """Measured 17 Nov: the gate compared the sample report (35% of findings cited) with thin DeepSeek reports
    (44-50%) and failed it on the share; a share is a floor, not a comparison."""
    rb = G.rubric('R1')
    full = R.score_report(open(SAMPLE).read(), rb)
    thin = dict(R.score_report(THIN, rb), cited_share=0.5, why_share=0.2)
    assert R.compare_reports([thin, thin], [full])['verdict'] == 'PASS'
    bare = R.score_report(re.sub(R.CITATION, '', open(SAMPLE).read()), rb)
    assert R.compare_reports([full], [bare])['verdict'] == 'FAIL'


def test_answer_ratings_become_judged_sets_per_case(tmp_path):
    """lx-agenttools' rating export: a rated question with picked records is judged through meaning search; one
    with none picked is counted, not scored; sets are written outside the repo, one per case."""
    items = [dict(id='rating-1', kind='rating', complaint='missed', question='who paid the rent', case_id='c1' * 8,
                  relevant=[dict(id='picked', any=['rec://aaaa'])], decoys=[]),
             dict(id='rating-2', kind='rating', complaint='thin', question='anything odd', case_id='c1' * 8,
                  relevant=[], decoys=[]),
             dict(id='rating-3', kind='rating', complaint='not relevant', question='the April transfer',
                  case_id='d2' * 8, relevant=[dict(id='picked', any=['txn://bbbb'])], decoys=[])]
    export = tmp_path / 'ratings.json'
    export.write_text(json.dumps(dict(items=items)))
    said = []
    paths = G.rating_sets(str(export), str(tmp_path / 'out'), log=said.append)
    assert len(paths) == 2
    sets = [json.load(open(p)) for p in paths]
    assert [len(s['queries']) for s in sets] == [1, 1]
    q = sets[0]['queries'][0]
    assert (q['tool'], q['kind'], q['args']) == ('search_by_meaning', 'rating', dict(query='who paid the rent', limit=50))
    assert '2 rated questions' in said[0] and '1 with none picked' in said[0]
    plan = G.plan_queries(paths, log=lambda *a: None)
    assert [p[2]['id'] for p in plan] == ['rating-1', 'rating-3']


def test_cross_area_records_count_only_for_tools_that_search_every_area():
    q = dict(id='q', kind='documents', tool='search_documents', args=dict(query='x'),
             relevant=[dict(id='doc', any=['the-doc'])], cross_area=[dict(id='row', any=['LAKE ORRIN CABINS'])])
    assert [r['id'] for r in G.judged_relevant(q)] == ['doc']
    meaning = [x for x in G.expand(dict(case='t', case_id='c', queries=[q], also_through=[dict(
        kind='meaning', tool='search_by_meaning', arg='query', extra={}, from_kinds=['documents'])]))
        if x['kind'] == 'meaning'][0]
    assert [r['id'] for r in G.judged_relevant(meaning)] == ['doc', 'row']
    assert [r['id'] for r in G.judged_relevant(dict(q, tool='search_case'))] == ['doc', 'row']


def test_model_calls_stop_at_the_cap():
    used = [0]
    call = G.capped_call(lambda prompt: 'ok', 2, used)
    assert [call('a'), call('b')] == ['ok', 'ok']
    with pytest.raises(RuntimeError, match='cap'):
        call('c')
    assert used == [2]


def test_gate_refuses_model_calls_at_peak_price(monkeypatch):
    real = G.time.gmtime
    monkeypatch.setattr(G.time, 'gmtime', lambda *a: real(1794880800))  # 2026-11-17 02:00 UTC
    monkeypatch.delenv(G.MODEL_CALLS_ENV, raising=False)
    with pytest.raises(SystemExit, match='01:00 and 04:00'):
        G.main(['gate', '--label', 't', '--model-calls', '10'])
    assert G.MODEL_CALLS_ENV not in os.environ


def test_a_decoy_counts_only_in_the_record_a_whole_unit_cites():
    month = {'cite': 'txn://t2', 'month': '2024-03', 'rows': [
        {'txn': 'txn://t1', 'payee': 'Decoy Hardware'},
        {'txn': 'txn://t2', 'payee': 'Acme Tools'},
        {'txn': 'txn://t3', 'payee': 'Other Decoy'}]}
    units = [month]
    texts = [R.unit_text(u) for u in units]
    decoys = [{'id': 'd1', 'any': ['decoy hardware']}, {'id': 'd2', 'any': ['acme tools']}]
    s = R.score_query(texts, [{'id': 'a', 'any': ['acme tools']}], decoys, decoy_texts=[R.cited_text(u) for u in units])
    assert s['found_at_10'] == ['a']
    assert s['decoys_top10'] == ['d2']  # the neighbour row's decoy text is not the cited record


def test_the_runner_scores_decoys_on_the_cited_record():
    import inspect
    import scripts.financial_agent_relevance as F
    assert 'decoy_texts=[R.cited_text(u) for u in units]' in inspect.getsource(F.Runner.run)


def _paged_run(page1_has_c, page2_has_c=None):
    """One meaning query with a full first page; record C sits at the end of page 1 or on page 2."""
    texts = [R.norm('noise')] * 47 + ([R.norm('gamma record')] if page1_has_c else []) + [R.norm('noise')] * 2
    texts = texts[:50] if page1_has_c else [R.norm('noise')] * 50
    rel = [{'id': 'C', 'any': ['gamma']}]
    score = R.score_query(texts, rel)
    if page2_has_c is not None:
        R.add_next_page(score, [R.norm('noise')] + ([R.norm('gamma record')] if page2_has_c else []), rel)
    q = {'demo:q3': dict(kind='meaning', score=score)}
    return dict(queries=q, aggregate=R.aggregate(q.values()))


def test_a_record_pushed_onto_the_next_page_is_moved_not_lost():
    """lx-casesearch 17 Nov: a record at 48 of 50 went to 51 because three units ranked above it, and the gate called
    it lost. On page 2 it is found: listed with both ranks, counted through recall at 50, never LOST."""
    cmp = R.compare([_paged_run(True)], [_paged_run(False, page2_has_c=True)])
    assert not cmp['lost_records']
    assert cmp['moved_past_first_page'] == [dict(query='demo:q3', record='C', base=48, cand=52)]
    assert any(e['metric'] == 'recall_at_50' for e in cmp['losses'])  # the drop still counts in the metric
    lines = R.verdict_lines(cmp, _paged_run(True)['aggregate'], _paged_run(False, True)['aggregate'])
    assert any(x.startswith('moved past the first page: demo:q3 C: rank 48 -> 52') for x in lines)


def test_a_record_on_neither_page_is_still_lost():
    for cand in (_paged_run(False, page2_has_c=False), _paged_run(False)):
        cmp = R.compare([_paged_run(True)], [cand])
        assert cmp['verdict'] == 'FAIL' and [e['record'] for e in cmp['lost_records']] == ['C']


def test_next_offset_reads_the_tools_page_marker():
    assert R.next_offset({'result_id': 'r', 'data': {'next_offset': 50, 'items': []}}) == 50
    assert R.next_offset({'next_offset': None}) is None and R.next_offset({'next_offset': True}) is None
    assert R.next_offset([1, 2]) is None
