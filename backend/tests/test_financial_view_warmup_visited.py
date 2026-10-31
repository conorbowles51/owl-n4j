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
    found = view_warmup._visited_views({(other, view_cache.handlers['visited-test'], ('offset',))})
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

    @view_cache.cached_view('visited-test-2')
    def view(case_id: UUID = Query(...), offset: int = Query(0), db=None):
        return {}
    _save(tmp_path, ('visited-test-2', json.dumps({'case_id': str(uuid4()), 'offset': '07'}, sort_keys=True)))
    assert view_warmup._visited_views(set()) == []
