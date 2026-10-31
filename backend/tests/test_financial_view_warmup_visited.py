"""The release prepare also warms every view a person opened in the last day, with the parameters it was opened with
(live 2026-10-31 09:10: statement coverage on 49494305 took 13.9 s on the first visit after a release because no
fixed warm list named it)."""
import json
import os
import time
from uuid import UUID, uuid4

from fastapi import Query

from services.financial import view_cache, view_warmup


def _save(directory, key, age=0):
    path = directory / ('%s.view' % abs(hash(key)))
    path.write_bytes(json.dumps(dict(key=list(key))).encode() + b'\n{}')
    stamp = time.time() - age
    os.utime(path, (stamp, stamp))


def test_a_view_opened_in_the_last_day_is_warmed_with_its_own_parameters(tmp_path, monkeypatch):
    monkeypatch.setattr(view_cache, '_saved_dir', lambda: tmp_path)
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(tmp_path / 'memo'))  # no visits noted yet: saved copies' times
    calls = []

    @view_cache.cached_view('visited-test')
    def coverage(case_id: UUID = Query(...), offset: int = Query(0, ge=0), db=None):
        calls.append((case_id, offset))
        return {}
    case, other = uuid4(), uuid4()
    opened = view_cache.view_key('visited-test', dict(case_id=case, offset=50))
    first_form = view_cache.view_key('visited-test', dict(case_id=other, offset=0))
    old = view_cache.view_key('visited-test', dict(case_id=case, offset=100))
    _save(tmp_path, opened)
    _save(tmp_path, first_form)
    _save(tmp_path, old, age=view_warmup.VISITED_MAX_AGE_SECONDS + 60)
    found = view_warmup._visited_views([(other, view_cache.handlers['visited-test'], dict(offset=0))])
    assert [(task_case, name) for task_case, (name, _, _) in found] == [(case, 'visited visited-test')]
    task_case, (_, route, defaults) = found[0]
    token = view_cache._recording.set(object())  # call the handler itself, as inside a computation
    try:
        route(case_id=task_case, **defaults, db=None)
    finally:
        view_cache._recording.reset(token)
    assert calls == [(case, 50)]


def test_a_saved_key_that_does_not_rebuild_to_itself_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(view_cache, '_saved_dir', lambda: tmp_path)
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(tmp_path / 'memo'))  # no visits noted yet: saved copies' times

    @view_cache.cached_view('visited-test-2')
    def view(case_id: UUID = Query(...), offset: int = Query(0), db=None):
        return {}
    _save(tmp_path, ('visited-test-2', json.dumps({'case_id': str(uuid4()), 'offset': '07'}, sort_keys=True)))
    assert view_warmup._visited_views(set()) == []


def test_a_route_default_the_fixed_lists_do_not_warm_is_warmed(tmp_path, monkeypatch):
    """The fixed lists warm some views in a form other than the route's defaults (posting graph label_origins=False,
    whose route default is True): a person's default-form visit is warmed, the fixed form is not warmed twice."""
    monkeypatch.setattr(view_cache, '_saved_dir', lambda: tmp_path)
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(tmp_path / 'memo'))  # no visits noted yet: saved copies' times
    calls = []

    @view_cache.cached_view('visited-test-3')
    def graph(case_id: UUID = Query(...), label_origins: bool = Query(True), db=None):
        calls.append((case_id, label_origins))
        return {}
    case = uuid4()
    route_default = view_cache.view_key('visited-test-3', dict(case_id=case, label_origins=True))
    fixed_form = view_cache.view_key('visited-test-3', dict(case_id=case, label_origins=False))
    _save(tmp_path, route_default)
    _save(tmp_path, fixed_form, age=10)
    found = view_warmup._visited_views([(case, view_cache.handlers['visited-test-3'], dict(label_origins=False))])
    assert [(task_case, name) for task_case, (name, _, _) in found] == [(case, 'visited visited-test-3')]
    task_case, (_, route, defaults) = found[0]
    token = view_cache._recording.set(object())  # call the handler itself, as inside a computation
    try:
        route(case_id=task_case, **defaults, db=None)
    finally:
        view_cache._recording.reset(token)
    assert calls == [(case, True)]


def test_the_views_people_opened_are_warmed_not_the_ones_only_warm_ups_rewrote(tmp_path, monkeypatch):
    """Every warm-up rewrites the saved copies, so their times say nothing about visits: once visits are noted the
    release warms what a person opened in the last day, and a view nobody opened for a day drops out."""
    monkeypatch.setattr(view_cache, '_saved_dir', lambda: tmp_path / 'views')
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(tmp_path))
    monkeypatch.setattr(view_cache, '_visits_noted', {})
    (tmp_path / 'views').mkdir()

    @view_cache.cached_view('visited-test-4')
    def view(case_id: UUID = Query(...), offset: int = Query(0), db=None):
        return {}
    case = uuid4()
    opened = view_cache.view_key('visited-test-4', dict(case_id=case, offset=5))
    rewritten = view_cache.view_key('visited-test-4', dict(case_id=case, offset=9))
    stale = view_cache.view_key('visited-test-4', dict(case_id=case, offset=7))
    for key in (opened, rewritten, stale):
        _save(tmp_path / 'views', key)  # all just rewritten by a warm-up
    view_cache.note_visit(opened)
    view_cache.note_visit(stale)
    path = view_cache._visit_path(tmp_path / view_cache.VISITED_DIR, stale)
    old = time.time() - view_warmup.VISITED_MAX_AGE_SECONDS - 60
    os.utime(path, (old, old))
    token = view_cache.not_a_visit.set(True)
    try:
        view_cache.note_visit(rewritten)  # a warm-up's call
    finally:
        view_cache.not_a_visit.reset(token)
    found = view_warmup._visited_views([])
    assert [name for _, (name, _, _) in found] == ['visited visited-test-4']
    task_case, (_, route, defaults) = found[0]
    assert task_case == case
    assert not view_cache._visit_path(tmp_path / view_cache.VISITED_DIR, rewritten).exists()


def test_a_visit_is_noted_at_most_once_per_interval(tmp_path, monkeypatch):
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(tmp_path))
    monkeypatch.setattr(view_cache, '_visits_noted', {})
    key = ('visited-test-5', '{}')
    view_cache.note_visit(key)
    path = view_cache._visit_path(tmp_path / view_cache.VISITED_DIR, key)
    os.utime(path, (1, 1))
    view_cache.note_visit(key)
    assert path.stat().st_mtime == 1  # within VISIT_NOTE_SECONDS: no write
    view_cache._visits_noted[key] = 0.0
    view_cache.note_visit(key)
    assert path.stat().st_mtime > 1


def test_warm_ups_and_refreshes_are_not_visits(monkeypatch):
    from services.financial import view_refresh
    monkeypatch.setattr(view_warmup, '_warm_cases_now', lambda share, stop: view_cache.not_a_visit.get())
    assert view_warmup._warm_cases() is True
    monkeypatch.setattr(view_refresh, '_refresh_one', lambda *args: view_cache.not_a_visit.get())
    assert view_refresh.refresh_one(None, dict(key=['x', '{}'])) is True
    assert view_cache.not_a_visit.get() is False
