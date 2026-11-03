"""02 decision 46: the sweep's write pace and the probe that measures it.

The pace is a measured value: at 2.0, a first reading of P14 (967,543 records) raised the p95 of a read probe on
another case's phone by more than half on samples of equal host CPU pressure, which is decision 46's reverse-if.
The timing script's probe reads only the other phone: a probe that also counts the phone being read measures its
own growing work as well as the pass.
"""
from __future__ import annotations

import importlib.util
import os
import re

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _timing_script():
    spec = importlib.util.spec_from_file_location("phone_sweep_timing",
                                                  os.path.join(BACKEND, "scripts", "phone_sweep_timing.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_default_pace_is_the_one_measured_under_half_again():
    from services.phone import sweep_worker
    assert sweep_worker.DEFAULT_PACE == 4.0


def test_the_worker_takes_the_default_pace_unless_overridden():
    from services.phone import sweep_worker
    src = open(sweep_worker.__file__).read()
    assert 'os.environ.get("LOUPE_PHONE_SWEEP_PACE", DEFAULT_PACE)' in src


def test_the_timing_probe_reads_only_the_other_phone():
    mod = _timing_script()
    assert mod.PROBE_QUERIES
    for sql in mod.PROBE_QUERIES.values():
        assert re.findall(r":(\w+)", sql) == ["x"], sql


def test_the_timing_script_refuses_to_probe_the_phone_it_reads(monkeypatch):
    mod = _timing_script()
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://nobody@127.0.0.1:1/none")
    with pytest.raises(SystemExit, match="another phone"):
        mod.main(["x", "same", "same", "4.0"])


def test_quiet_samples_are_summarised_apart_from_the_rest():
    mod = _timing_script()
    samples = []
    for i, cpu in enumerate([1.0] * 20 + [40.0] * 20):
        s = {"t": i, "cpu": cpu, "io": 0.0, "total": 0.01 if cpu < 5 else 1.0}
        for k in mod.PROBE_QUERIES:
            s[k] = {"seconds": 0.0, "hit": 10, "read": 0, "plan": "Seq Scan(t)"}
        samples.append(s)
    out = mod.summary(samples)
    assert out["quiet"]["n"] == 20 and out["quiet"]["p95_ms"] == 10.0
    assert out["all"]["n"] == 40 and out["all"]["p95_ms"] == 1000.0
