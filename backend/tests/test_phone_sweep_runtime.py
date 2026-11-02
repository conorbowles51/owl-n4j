"""02-U17: the sweep survives being killed mid-pass (02 sections 1.3 and 5.7).

A child process runs one pass and is killed with SIGKILL after generation n+1 is written and before it commits.
The previous generation stays readable and the state row unchanged; the next run completes the pass.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

from sqlalchemy import text

from services.phone import generic, registry, sweep
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.test_phone_generic import _unknown_type_extraction

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHILD = r'''
import sys, time
sys.path.insert(0, %(backend)r)
from sqlalchemy import create_engine, text
from services.phone import sweep

def stall(conn, ext, gen, plan=None):
    n = conn.execute(text("SELECT count(*) FROM phone_time_values WHERE extraction_id = :e AND generation = :g"),
                     {"e": ext, "g": gen}).scalar()
    open(%(marker)r, "w").write("%%d %%d" %% (gen, n))
    time.sleep(120)
    return {}

sweep.register_applier(stall)
sweep.interpret_one(create_engine(%(url)r), %(ext)r)
'''


def _counts(c, ext):
    return {t: dict(c.execute(text("SELECT generation, count(*) FROM %s WHERE extraction_id = :e GROUP BY 1" % t),
                              {"e": ext}).fetchall()) for t in generic.DERIVED_TABLES}


@needs_template
def test_a_pass_killed_before_commit_leaves_the_previous_generation_and_the_next_run_completes(tmp_path):
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            ext = _unknown_type_extraction(c, make_case(c))
        assert sweep.interpret_one(engine, ext)["generation"] == 1
        with engine.begin() as c:  # make it stale again
            c.execute(text("UPDATE phone_interpretation_state SET interpreter_version = 'old' WHERE extraction_id = :e"),
                      {"e": ext})
        with engine.connect() as c:
            before = _counts(c, ext)
            state_before = c.execute(text("SELECT generation, interpreter_version FROM phone_interpretation_state "
                                          "WHERE extraction_id = :e"), {"e": ext}).one()
        marker = str(tmp_path / "written")
        script = tmp_path / "child.py"
        script.write_text(CHILD % {"backend": BACKEND, "marker": marker, "ext": str(ext),
                                   "url": engine.url.render_as_string(hide_password=False)})
        child = subprocess.Popen([sys.executable, "-I", str(script)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 60
        while not os.path.exists(marker) and time.monotonic() < deadline and child.poll() is None:
            time.sleep(0.1)
        assert os.path.exists(marker), child.communicate(timeout=5)
        gen, written = map(int, open(marker).read().split())
        assert gen == 2 and written > 0  # generation 2 was written inside the open transaction
        os.kill(child.pid, signal.SIGKILL)
        child.wait(timeout=30)
        deadline = time.monotonic() + 30
        with engine.connect() as c:
            while c.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND "
                                 "pid <> pg_backend_pid() AND state <> 'idle'")).scalar() and time.monotonic() < deadline:
                time.sleep(0.2)
                c.rollback()
        with engine.connect() as c:
            assert _counts(c, ext) == before  # nothing of generation 2 survived; generation 1 readable
            assert c.execute(text("SELECT count(*) FROM pv_timeline_entry WHERE extraction_id = :e"),
                             {"e": ext}).scalar() > 0
            assert tuple(c.execute(text("SELECT generation, interpreter_version FROM phone_interpretation_state "
                                        "WHERE extraction_id = :e"), {"e": ext}).one()) == tuple(state_before)
        out = sweep.interpret_one(engine, ext)  # the next start completes it (the advisory lock died with the child)
        assert out["status"] == "done" and out["generation"] == 2
        with engine.connect() as c:
            after = _counts(c, ext)
            assert {t: sorted(v) for t, v in after.items() if v} == {t: [2] for t, v in before.items() if v}
            assert {t: sum(v.values()) for t, v in after.items()} == {t: sum(v.values()) for t, v in before.items()}


@needs_template
def test_one_sweep_process_per_box_and_it_stops_on_sigterm():
    from services.phone import sweep_worker
    with fresh_engine() as engine:
        env = dict(os.environ, DATABASE_URL=engine.url.render_as_string(hide_password=False), LOUPE_DB_ROLE="phone-sweep")
        first = subprocess.Popen(sweep_worker.command(), cwd=sweep_worker.BACKEND_DIR, env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 60
            held = False
            while time.monotonic() < deadline and first.poll() is None and not held:
                with engine.connect() as c:
                    held = bool(c.execute(text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND "
                                               "granted")).scalar())
                time.sleep(0.2)
            assert held, first.communicate(timeout=5)
            second = subprocess.run(sweep_worker.command(), cwd=sweep_worker.BACKEND_DIR, env=env, timeout=60,
                                    capture_output=True)
            assert second.returncode == sweep_worker.EXIT_ALREADY_RUNNING, second.stderr[-2000:]
            first.send_signal(signal.SIGTERM)
            assert first.wait(timeout=60) == 0
        finally:
            if first.poll() is None:
                first.kill()


@needs_template
def test_a_purge_cut_short_is_finished_at_worker_start(monkeypatch):
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            ext = _unknown_type_extraction(c, make_case(c))
        sweep.interpret_one(engine, ext)
        with engine.begin() as c:
            c.execute(text("UPDATE phone_interpretation_state SET interpreter_version = 'old' WHERE extraction_id = :e"),
                      {"e": ext})
        with monkeypatch.context() as m:  # the process stops after the swap commits, before the purge
            m.setattr(generic, "purge_generations_before", lambda *a, **k: {})
            m.setattr(sweep, "_purged", lambda *a, **k: None)
            assert sweep.interpret_one(engine, ext)["generation"] == 2
        with engine.connect() as c:
            left = _counts(c, ext)
            assert any(sorted(v) == [1, 2] for v in left.values())
            assert c.execute(text("SELECT counts ? 'purge_pending' FROM phone_interpretation_state "
                                  "WHERE extraction_id = :e"), {"e": ext}).scalar()
        assert sweep.purge_leftovers(engine) == {str(ext): sum(v.get(1, 0) for v in left.values())}
        with engine.connect() as c:
            assert {t: sorted(v) for t, v in _counts(c, ext).items() if v} == {t: [2] for t, v in left.items() if v}
            assert not c.execute(text("SELECT counts ? 'purge_pending' FROM phone_interpretation_state "
                                      "WHERE extraction_id = :e"), {"e": ext}).scalar()
        assert sweep.purge_leftovers(engine) == {}


def test_the_purge_walk_crosses_batches_without_rereading(monkeypatch):
    """Batch size 1 forces the ordered walk through every row; the plain pass after it finds nothing left."""
    if not os.environ.get("LOUPE_TEST_PHONE_PG_TEMPLATE_URL"):
        import pytest
        pytest.skip("needs the phone PostgreSQL template")
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            ext = _unknown_type_extraction(c, make_case(c))
        sweep.interpret_one(engine, ext)
        with engine.connect() as c:
            before = _counts(c, ext)
        out = generic.purge_generations_before(engine, ext, 2, batch=1)
        assert sum(out.values()) == sum(sum(v.values()) for v in before.values())
        with engine.connect() as c:
            assert all(not v for v in _counts(c, ext).values())
