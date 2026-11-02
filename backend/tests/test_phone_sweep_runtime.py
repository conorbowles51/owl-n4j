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

def stall(conn, ext, gen):
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
