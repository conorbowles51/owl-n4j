"""Ledger graph follow-ups run once per host, in the batch-rounds child, not in every web worker.

A web worker with a lock directory hands each request over as a file; the child turns it into an in-process
request and projects it once. Without a lock directory the worker runs them itself, as before.
"""
import asyncio
import contextlib
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from services.financial import batch_rounds, graph_followup, identity_graph, import_batches
from services.financial.projection import LABEL_TRANSACTION
from tests.test_financial_graph_followup import GraphFollowUpTestCase

BACKEND = Path(__file__).resolve().parents[1]


class HandOffTests(GraphFollowUpTestCase):
    def setUp(self):
        super().setUp()
        self.directory = Path(tempfile.mkdtemp(prefix='graph-hand-off-')) / graph_followup.HAND_OFF_DIRECTORY

    def tearDown(self):
        import shutil
        shutil.rmtree(self.directory.parent, ignore_errors=True)
        super().tearDown()

    def files(self, name):
        return sorted(path.name for path in (self.directory / name).iterdir())

    def become_child(self):
        """The same process plays the child: it no longer hands off, it serves the hand-offs."""
        graph_followup._handoff_dir[0] = None
        graph_followup.serve_hand_offs(self.directory)

    def serve(self):
        return graph_followup.serve_round(self.f.SessionLocal, self.graph.session)

    def test_a_worker_request_is_handed_off_and_one_child_round_projects_it_once(self):
        graph_followup.hand_off_to(self.directory)
        self.f.confirm()  # the import's own request, in a worker that hands off
        graph_followup.request_follow_up(self.case, immediate=True)
        self.assertIsNone(graph_followup.pending_state(self.case))  # nothing held in this worker
        self.assertEqual(self.files('requests'), [self.case, self.case + '.immediate'])
        self.assertEqual(self.graph.writes, 0)

        self.become_child()
        results = self.serve()
        self.assertEqual([r['outcome'] for r in results], ['projected'])
        self.assertEqual(self.graph.count(LABEL_TRANSACTION, self.case), 12)
        self.assertEqual(self.files('requests'), [])
        self.assertEqual(self.files('claimed'), [])
        self.assertEqual(self.files('pending'), [])   # caught up
        self.assertEqual(self.files('projected'), [self.case])
        self.assertEqual(self.serve(), [])  # no second projection

    def test_the_quiet_interval_is_counted_from_when_the_worker_asked(self):
        graph_followup.hand_off_to(self.directory)
        self.f.confirm()
        self.become_child()
        self.assertEqual(self.serve(), [])  # asked just now: waits for the quiet interval
        self.assertEqual(self.files('pending'), [self.case])
        graph_followup._reset_for_tests()
        graph_followup.hand_off_to(self.directory)
        graph_followup.request_follow_up(self.case)
        asked = time.time() - graph_followup.QUIET_SECONDS - 1
        os.utime(self.directory / 'requests' / self.case, (asked, asked))
        self.become_child()  # a restarted child: the pending case is requested again, at its own time
        self.assertEqual([r['outcome'] for r in self.serve()], ['projected'])

    def test_a_request_written_while_the_child_claims_is_not_lost(self):
        graph_followup.hand_off_to(self.directory)
        graph_followup.request_follow_up(self.case, immediate=True)
        self.become_child()
        real_rename = os.rename

        def rename_then_a_worker_asks_again(source, target):
            real_rename(source, target)
            graph_followup._write_hand_off(self.directory, self.case, True)  # another worker, same instant
        with patch.object(graph_followup.os, 'rename', side_effect=rename_then_a_worker_asks_again):
            self.assertEqual(graph_followup.claim_hand_offs(), 1)
        self.assertEqual(self.files('requests'), [self.case + '.immediate'])
        with graph_followup._lock:
            generation = graph_followup._states[self.case].request_generation
        self.assertEqual(graph_followup.claim_hand_offs(), 1)
        with graph_followup._lock:
            self.assertEqual(graph_followup._states[self.case].request_generation, generation + 1)
        self.assertEqual(self.files('requests'), [])

    def test_status_says_pending_for_a_handed_off_request(self):
        graph_followup.hand_off_to(self.directory)
        self.f.confirm()
        self.assertEqual(self.status()['status'], 'pending')
        # Claimed by the child and waiting there for the quiet interval: still pending in the worker.
        graph_followup._handoff_dir[0] = None
        graph_followup.serve_hand_offs(self.directory)
        graph_followup.claim_hand_offs()
        graph_followup._states.clear()  # only the child holds it, not the worker reading the status
        graph_followup._serving_dir[0] = None
        graph_followup._handoff_dir[0] = self.directory
        self.assertEqual(self.files('requests'), [])
        self.assertEqual(self.status()['status'], 'pending')
        (self.directory / 'pending' / self.case).unlink()
        self.assertEqual(self.status()['status'], 'not_projected')

    def worker_view(self):
        """This process reads the status as a web worker that hands off (the child's in-process state unseen)."""
        graph_followup._states.clear()
        graph_followup._serving_dir[0] = None
        graph_followup._handoff_dir[0] = self.directory

    def test_status_says_pending_while_a_request_is_being_claimed(self):
        graph_followup.hand_off_to(self.directory)
        graph_followup.request_follow_up(self.case)
        # The child has renamed it into claimed/ and not yet written pending/.
        os.rename(self.directory / 'requests' / self.case, self.directory / 'claimed' / f'{self.case}.12345')
        self.assertEqual(self.status()['status'], 'pending')

    def test_a_failure_the_graph_marker_could_not_record_shows_as_retrying_with_its_reason(self):
        graph_followup.hand_off_to(self.directory)
        graph_followup.request_follow_up(self.case, immediate=True)
        self.become_child()

        def boom(*args, **kwargs):
            raise RuntimeError('graph write refused')
        with patch.object(graph_followup, 'project_case_graph', boom), \
                patch.object(graph_followup, 'record_failure', boom):
            results = self.serve()
        self.assertEqual([r['outcome'] for r in results], ['failed'])
        self.worker_view()
        status = self.status()
        self.assertEqual(status['status'], 'retrying')
        self.assertEqual(status['last_error'], 'graph write refused')
        self.assertEqual(status['attempts'], 1)

    def test_a_request_made_in_the_child_itself_shows_as_pending_at_once(self):
        self.become_child()
        graph_followup.request_follow_up(self.case)  # e.g. a statement saved by the child's rounds thread
        self.assertEqual(self.files('pending'), [self.case])
        self.worker_view()
        self.assertEqual(self.status()['status'], 'pending')

    def test_a_new_request_in_the_child_keeps_a_retrying_case_retrying(self):
        self.become_child()
        graph_followup.request_follow_up(self.case, immediate=True)

        def boom(*args, **kwargs):
            raise RuntimeError('graph write refused')
        with patch.object(graph_followup, 'project_case_graph', boom), \
                patch.object(graph_followup, 'record_failure', boom):
            self.serve()
        graph_followup.request_follow_up(self.case)  # the rounds thread saves another statement
        self.worker_view()
        status = self.status()
        self.assertEqual((status['status'], status['last_error']), ('retrying', 'graph write refused'))

    def test_a_claimed_request_whose_time_cannot_be_read_is_still_taken_up(self):
        graph_followup.hand_off_to(self.directory)
        graph_followup.request_follow_up(self.case)
        self.become_child()
        real = Path.stat

        def stat(path, *args, **kwargs):
            if path.parent.name == 'claimed':
                raise OSError('synthetic')
            return real(path, *args, **kwargs)
        with patch.object(Path, 'stat', stat):
            self.assertEqual(graph_followup.claim_hand_offs(), 1)
        self.assertEqual(self.files('claimed'), [])
        self.assertIn(self.case, graph_followup._states)

    def test_a_request_that_cannot_be_claimed_does_not_stop_the_rest(self):
        graph_followup.hand_off_to(self.directory)
        other = '0f6a3c3e-6f4e-4d55-9b38-6a1f2f8f2b11'
        graph_followup.request_follow_up(other)
        graph_followup.request_follow_up(self.case, immediate=True)
        self.become_child()
        real = os.rename

        def rename(source, target):
            if Path(source).name == other:
                raise PermissionError('synthetic')
            return real(source, target)
        with patch.object(graph_followup.os, 'rename', rename):
            results = self.serve()
        self.assertEqual([r['outcome'] for r in results], ['projected'])
        self.assertEqual(self.files('requests'), [other])  # tried again next round


def test_hand_offs_that_cannot_be_taken_up_are_retried_and_the_rounds_go_on(monkeypatch, fresh, caplog):
    import threading
    attempts, served = [], []

    def serve_hand_offs(directory):
        attempts.append(directory)
        if len(attempts) == 1:
            raise PermissionError('synthetic')
    monkeypatch.setattr(graph_followup, 'serve_hand_offs', serve_hand_offs)
    monkeypatch.setattr(graph_followup, 'serve_round', lambda factory, graph, stop: served.append(1) or [])
    monkeypatch.setattr(batch_rounds, 'GRAPH_FOLLOW_UP_SECONDS', 0.01)
    stop = threading.Event()
    threading.Timer(0.2, stop.set).start()
    batch_rounds.graph_follow_up_forever(stop, 'factory', hand_offs='dir')
    assert attempts == ['dir', 'dir']  # once more after the failure, then not again
    assert len(served) >= 2
    assert any('could not be taken up' in r.getMessage() for r in caplog.records)


def test_the_child_starts_its_rounds_before_taking_up_the_hand_offs():
    import inspect
    main = inspect.getsource(batch_rounds.main)
    assert 'serve_hand_offs' not in main  # a failure there ended the child before any round ran


@pytest.fixture
def fresh():
    graph_followup._reset_for_tests()
    yield
    graph_followup._reset_for_tests()


def _one_turn(follow_up_round):
    """Run the worker's batch-turn loop for a moment; returns how often it turned."""
    turns = []

    def turn_batches(db):
        turns.append(1)
        return []

    async def run():
        task = asyncio.create_task(import_batches._turns_forever(
            lambda: (lambda: contextlib.nullcontext(None)), lambda path: path, None))
        await asyncio.sleep(0.3)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    with patch.object(import_batches, 'turn_batches', side_effect=turn_batches), \
            patch.object(graph_followup, 'follow_up_round', follow_up_round):
        asyncio.run(run())
    return len(turns)


def test_the_worker_turn_leaves_the_graph_to_the_child_when_there_is_a_lock_location(tmp_path, monkeypatch, fresh):
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(tmp_path))
    assert batch_rounds.decide_child_mode() is True
    assert graph_followup.handing_off()
    follow_up_round = AsyncMock(return_value=[])
    assert _one_turn(follow_up_round) >= 1
    follow_up_round.assert_not_called()


def test_without_a_lock_location_the_worker_turn_still_runs_the_graph_follow_up(monkeypatch, fresh):
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', '')
    assert batch_rounds.decide_child_mode() is False
    assert not graph_followup.handing_off()
    follow_up_round = AsyncMock(return_value=[])
    assert _one_turn(follow_up_round) >= 1
    follow_up_round.assert_called()


def test_the_child_runs_the_graph_follow_up_beside_the_rounds_and_stops_with_them(monkeypatch, fresh):
    import threading
    served = []
    monkeypatch.setattr(graph_followup, 'serve_round', lambda factory, graph, stop: served.append(stop) or [])
    monkeypatch.setattr(batch_rounds, 'rounds', lambda stop, factory, resolve_path, groups=None: stop.wait(0.3))
    monkeypatch.setattr(batch_rounds, 'GRAPH_FOLLOW_UP_SECONDS', 0.05)
    stop = threading.Event()
    threading.Timer(0.3, stop.set).start()
    batch_rounds.child_work(stop, 'factory', lambda path: path)
    assert served and all(s is stop for s in served)
    assert not [t for t in threading.enumerate() if t.name == 'graph-follow-up']


def test_a_failed_graph_round_is_logged_and_retried(monkeypatch, fresh, caplog):
    import threading
    calls = []

    def fail(factory, graph, stop):
        calls.append(1)
        raise RuntimeError('graph down')
    monkeypatch.setattr(graph_followup, 'serve_round', fail)
    monkeypatch.setattr(batch_rounds, 'GRAPH_FOLLOW_UP_SECONDS', 0.01)
    stop = threading.Event()
    threading.Timer(0.2, stop.set).start()
    batch_rounds.graph_follow_up_forever(stop, 'factory')
    assert len(calls) >= 2
    assert any('graph follow-up round failed' in r.getMessage() for r in caplog.records)


CHILD_STAMP = """
import sys
from pathlib import Path
from services.financial import graph_followup
graph_followup.serve_hand_offs(Path(sys.argv[1]))
graph_followup._notify_identity_graph(sys.argv[2])
"""


def test_a_projection_in_the_child_wakes_the_workers_identity_sweep(tmp_path, monkeypatch, fresh):
    case = '0f6a3c3e-6f4e-4d55-9b38-6a1f2f8f2b11'
    directory = tmp_path / graph_followup.HAND_OFF_DIRECTORY
    graph_followup.hand_off_to(directory)   # this process: a web worker

    calls = []

    @contextlib.contextmanager
    def session():
        from types import SimpleNamespace
        yield SimpleNamespace(scalars=lambda statement: [case])
    from postgres import session as sql_session
    from sqlalchemy import create_engine
    monkeypatch.setattr(sql_session, 'get_background_session', session)
    monkeypatch.setattr(sql_session, '_get_engine', lambda: create_engine('sqlite://'))
    monkeypatch.setattr(identity_graph, 'synchronize_case', lambda case_id: calls.append(case_id) or True)
    identity_graph._clear_deferral(case)

    identity_graph.sync_saved_identities()          # first look: nothing projected yet
    assert calls == [case]
    identity_graph._defer(case, identity_graph.WAITING_FOR_PAYMENTS, missing=3)
    identity_graph.sync_saved_identities()
    assert calls == [case]                          # backing off

    script = tmp_path / 'child_stamp.py'
    script.write_text(CHILD_STAMP)
    subprocess.run([sys.executable, str(script), str(directory), case], cwd=str(BACKEND), check=True,
                   env=dict(os.environ, PYTHONPATH=str(BACKEND)), timeout=600)  # hang guard: the child's import passed 300 s at load 110; nothing asserts wall time
    assert (directory / 'projected' / case).exists()

    identity_graph.sync_saved_identities()          # the child's stamp moved: the case is retried now
    assert calls == [case, case]
    identity_graph._clear_deferral(case)
