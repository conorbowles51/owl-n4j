"""A test that bounds how long pure computation takes measures CPU time, not wall clock.

Wall-clock bounds on computation fail whenever the box is loaded (2026-11-03: two phone tests went red in a
full suite at load average 15-27 and passed serially in 1.77 s). Tests that time sleeps, timeouts, threads,
child processes or signals are about waiting, so wall clock is right for them and they are left alone."""
from __future__ import annotations

import ast
import pathlib
import re

TESTS = pathlib.Path(__file__).resolve().parent
WALL = {"time", "monotonic", "perf_counter"}
WAITING = ("sleep", "Thread", "subprocess", "signal", "Popen", "Event", "timeout", "TIMEOUT", "_TextServer", "wait")
_CANDIDATE = re.compile(r"time\.(?:time|monotonic|perf_counter)\(\)\s*-")


def _is_wall_call(node: ast.AST) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in WALL
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "time")


def _elapsed_bound(node: ast.AST) -> bool:
    """`assert time.monotonic() - started < 5`: an elapsed wall-clock time compared with a bound."""
    if not (isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare)):
        return False
    operands = [node.test.left, *node.test.comparators]
    return any(isinstance(op, ast.BinOp) and isinstance(op.op, ast.Sub) and _is_wall_call(op.left) for op in operands)


def _elapsed_names(fn: ast.AST) -> set[str]:
    """Names bound to an elapsed wall-clock time: `took = time.perf_counter() - t0`."""
    names = set()
    for node in ast.walk(fn):
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.BinOp) and isinstance(node.value.op, ast.Sub)
                and _is_wall_call(node.value.left)):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def _bounds_elapsed_name(node: ast.AST, names: set[str]) -> bool:
    """`assert took < 5` or `assert t_join < t_nested` where a side is an elapsed wall-clock time."""
    if not (names and isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare)):
        return False
    operands = [node.test.left, *node.test.comparators]
    return any(isinstance(op, ast.Name) and op.id in names for op in operands)


def wall_clock_bounds_on_computation(root: pathlib.Path = TESTS) -> list[str]:
    found = []
    for path in sorted(root.rglob("test_*.py")):
        source = path.read_text(encoding="utf-8")
        if not _CANDIDATE.search(source):
            continue
        for fn in ast.walk(ast.parse(source)):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or not fn.name.startswith("test"):
                continue
            names = _elapsed_names(fn)
            if not any(_elapsed_bound(node) or _bounds_elapsed_name(node, names) for node in ast.walk(fn)):
                continue
            body = ast.get_source_segment(source, fn) or ""
            if not any(word in body for word in WAITING):
                found.append(f"{path.relative_to(root)}::{fn.name}")
    return found


def test_no_test_bounds_computation_by_wall_clock():
    assert wall_clock_bounds_on_computation() == []


def test_the_check_sees_a_wall_clock_bound_and_ignores_a_waiting_test(tmp_path):
    (tmp_path / "test_x.py").write_text(
        "import time\n"
        "def test_compute():\n    t = time.monotonic()\n    sum(range(9))\n    assert time.monotonic() - t < 5\n"
        "def test_cpu():\n    t = time.process_time()\n    assert time.process_time() - t < 5\n"
        "def test_waits():\n    t = time.monotonic()\n    time.sleep(0)\n    assert time.monotonic() - t < 5\n"
        "def test_deadline():\n    assert run(deadline=time.time() - 1) == 0 and 0 <= time.time()\n",
        encoding="utf-8",
    )
    assert wall_clock_bounds_on_computation(tmp_path) == ["test_x.py::test_compute"]


def test_the_check_sees_an_elapsed_time_kept_in_a_name(tmp_path):
    (tmp_path / "test_y.py").write_text(
        "import time\n"
        "def test_faster():\n    t0 = time.perf_counter()\n    a = time.perf_counter() - t0\n"
        "    t0 = time.perf_counter()\n    b = time.perf_counter() - t0\n    assert a < b\n"
        "def test_cpu_named():\n    t0 = time.process_time()\n    a = time.process_time() - t0\n    assert a < 5\n",
        encoding="utf-8",
    )
    assert wall_clock_bounds_on_computation(tmp_path) == ["test_y.py::test_faster"]
