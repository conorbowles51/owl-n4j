"""The backend bootstrap line in CLAUDE.md, checked against what the suite loads.

CLAUDE.md "Tests" gives one ``pip install`` line instead of ``requirements.txt``
(which pulls torch through ``openai-whisper``).  The line is a hand-kept copy, so
it drifts: ``orjson`` became a load-time import of ``services.neo4j.graph_read_cache``
and a fresh sandbox following the line could no longer import the suite.

Two invariants:
- every pin on the line is the pin in ``requirements.txt`` (same package, same version);
- the package surface (``routers`` and ``services.financial``, the import chain
  every router-level test drags in) imports when every installed distribution
  outside the line and its dependencies is refused, as in a fresh sandbox.
"""
from __future__ import annotations

import importlib.metadata as metadata
import json
import pathlib
import re
import subprocess
import sys
import unittest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
CLAUDE_MD = BACKEND.parent / "CLAUDE.md"
REQUIREMENTS = BACKEND / "requirements.txt"
PIN = re.compile(r'"([A-Za-z0-9._-]+)(?:\[[^\]]*\])?==([^"]+)"')


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _bootstrap_pins() -> dict[str, str]:
    lines = [line for line in CLAUDE_MD.read_text().splitlines()
             if line.startswith("pip install --break-system-packages")]
    assert len(lines) == 1, f"expected one bootstrap pip line in CLAUDE.md, found {len(lines)}"
    return {_norm(name): version for name, version in PIN.findall(lines[0])}


def _requirement_pins() -> dict[str, str]:
    pins = {}
    for line in REQUIREMENTS.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if "==" in line:
            name, version = line.split("==", 1)
            pins[_norm(name.split("[", 1)[0])] = version.strip()
    return pins


def _with_dependencies(names: set[str]) -> set[str]:
    seen, todo = set(), list(names)
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        try:
            requires = metadata.distribution(name).requires or []
        except metadata.PackageNotFoundError:
            continue
        for requirement in requires:
            if "extra ==" in requirement:
                continue
            match = re.match(r"[A-Za-z0-9._-]+", requirement)
            if match:
                todo.append(_norm(match.group(0)))
    return seen


class BootstrapLineTests(unittest.TestCase):
    def test_every_pin_matches_requirements(self):
        requirements = _requirement_pins()
        wrong = {name: (version, requirements.get(name))
                 for name, version in _bootstrap_pins().items() if requirements.get(name) != version}
        self.assertEqual(wrong, {}, "bootstrap pin -> (line version, requirements.txt version)")

    def test_package_surface_imports_with_only_what_the_line_installs(self):
        # A fresh sandbox has only the line and its dependencies. Simulate it: in a child interpreter,
        # refuse every installed distribution outside that set, then import the surface the suite loads.
        # Optional imports (chromadb, python-magic) degrade on ImportError exactly as they do there.
        covered = sorted(_with_dependencies(set(_bootstrap_pins())))
        child = subprocess.run([sys.executable, "-c", _CHILD, json.dumps(covered)], cwd=BACKEND,
                               capture_output=True, text=True, timeout=600)
        refused = re.findall(r"BOOTSTRAP-REFUSED (\S+) \((.+?)\)", child.stderr)
        self.assertEqual(child.returncode, 0, f"import failed; refused: {refused}\n{child.stderr[-2000:]}")


_CHILD = """
import importlib, importlib.abc, importlib.metadata as metadata, json, re, sys
covered = set(json.loads(sys.argv[1]))
dists_of = metadata.packages_distributions()
norm = lambda name: re.sub(r"[-_.]+", "-", name).lower()

class Refuse(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if "." in name or name in sys.stdlib_module_names or name not in dists_of:
            return None
        dists = {norm(d) for d in dists_of[name]}
        if dists & covered:
            return None
        print(f"BOOTSTRAP-REFUSED {name} ({', '.join(sorted(dists))})", file=sys.stderr)
        raise ModuleNotFoundError(f"No module named {name!r}", name=name)

sys.meta_path.insert(0, Refuse())
import routers, services.financial
"""


if __name__ == "__main__":
    unittest.main()
