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
_CANDIDATE = re.compile(r"assert[^\n]*time\.(?:time|monotonic|perf_counter)\(\)\s*-")


def _is_wall_call(node: ast.AST) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in WALL
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "time")


def _elapsed_bound(node: ast.AST) -> bool:
    """`assert time.monotonic() - started < 5`: an elapsed wall-clock time compared with a bound."""
    if not (isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare)):
        return False
    operands = [node.test.left, *node.test.comparators]
    return any(isinstance(op, ast.BinOp) and isinstance(op.op, ast.Sub) and _is_wall_call(op.left) for op in operands)


def wall_clock_bounds_on_computation(root: pathlib.Path = TESTS) -> list[str]:
    found = []
    for path in sorted(root.rglob("test_*.py")):
        source = path.read_text(encoding="utf-8")
        if not _CANDIDATE.search(source):
            continue
        for fn in ast.walk(ast.parse(source)):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or not fn.name.startswith("test"):
                continue
            if not any(_elapsed_bound(node) for node in ast.walk(fn)):
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
