"""The backend bootstrap line in CLAUDE.md, checked against what the suite loads.

CLAUDE.md "Tests" gives one ``pip install`` line instead of ``requirements.txt``
(which pulls torch through ``openai-whisper``).  The line is a hand-kept copy, so
it drifts: a fresh venv built from it could not import ``config`` (python-dotenv),
the auth chain (bcrypt, cryptography), or the test modules that use pytest,
PyMuPDF and pypdf, and the suite reported those as dozens of import errors.

Two invariants:
- every pin on the line agrees with ``requirements.txt`` (the same pin, or inside its
  range); a package ``requirements.txt`` does not name must be in ``TEST_ONLY``;
- the package surface (``routers``, ``services.financial``) and every
  ``test_financial_*`` module import when every installed distribution outside the
  line and its dependencies is refused, as in a fresh sandbox.

An import inside a function body (``fitz`` in the PDF tests) is not reached by
importing the module, so this cannot see it; a full suite run in a fresh venv
built from the line can.
"""
from __future__ import annotations

import importlib.metadata as metadata
import json
import pathlib
import re
import subprocess
import sys
import unittest

from packaging.specifiers import SpecifierSet

BACKEND = pathlib.Path(__file__).resolve().parents[1]
CLAUDE_MD = BACKEND.parent / "CLAUDE.md"
REQUIREMENTS = BACKEND / "requirements.txt"
PIN = re.compile(r'"([A-Za-z0-9._-]+)(?:\[[^\]]*\])?==([^"]+)"')
REQUIREMENT = re.compile(r"^([A-Za-z0-9._-]+)(?:\[[^\]]*\])?\s*(.*)$")

# On the line but not in requirements.txt, with the reason.
TEST_ONLY = {"pytest": "test runner; test modules import it, the app does not"}


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _bootstrap_pins() -> dict[str, str]:
    lines = [line for line in CLAUDE_MD.read_text().splitlines()
             if line.startswith("pip install --break-system-packages")]
    assert len(lines) == 1, f"expected one bootstrap pip line in CLAUDE.md, found {len(lines)}"
    return {_norm(name): version for name, version in PIN.findall(lines[0])}


def _requirement_specs() -> dict[str, str]:
    specs = {}
    for line in REQUIREMENTS.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        match = REQUIREMENT.match(line)
        if match:
            specs[_norm(match.group(1))] = match.group(2).split(";", 1)[0].strip()
    return specs


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
    def test_every_pin_agrees_with_requirements(self):
        specs = _requirement_specs()
        wrong = {}
        for name, version in _bootstrap_pins().items():
            if name in TEST_ONLY:
                if name in specs:
                    wrong[name] = (version, f"listed as test-only but requirements.txt has {specs[name]!r}")
            elif name not in specs:
                wrong[name] = (version, "not in requirements.txt")
            elif version not in SpecifierSet(specs[name]):
                wrong[name] = (version, specs[name])
        self.assertEqual(wrong, {}, "bootstrap pin -> (line version, requirements.txt)")

    def test_suite_imports_with_only_what_the_line_installs(self):
        # A fresh sandbox has only the line and its dependencies. Simulate it: in a child interpreter,
        # refuse every installed distribution outside that set, then import what the suite imports.
        # Optional imports (chromadb, python-magic) degrade on ImportError exactly as they do there.
        covered = sorted(_with_dependencies(set(_bootstrap_pins())))
        modules = sorted(f"tests.{path.stem}" for path in (BACKEND / "tests").glob("test_financial_*.py"))
        child = subprocess.run([sys.executable, "-c", _CHILD, json.dumps(covered), json.dumps(modules)],
                               cwd=BACKEND, capture_output=True, text=True, timeout=900)
        failed = re.findall(r"^BOOTSTRAP-FAILED (.+)$", child.stderr, re.M)
        self.assertEqual((child.returncode, failed), (0, []), child.stderr[-3000:])


_CHILD = """
import importlib, importlib.abc, importlib.metadata as metadata, json, re, sys
covered = set(json.loads(sys.argv[1]))
dists_of = metadata.packages_distributions()
norm = lambda name: re.sub(r"[-_.]+", "-", name).lower()

class Refuse(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if "." in name or name in sys.stdlib_module_names or name not in dists_of:
            return None
        if {norm(d) for d in dists_of[name]} & covered:
            return None
        raise ModuleNotFoundError(f"No module named {name!r} (not installed by the bootstrap line)", name=name)

sys.meta_path.insert(0, Refuse())
for module in ["routers", "services.financial"] + json.loads(sys.argv[2]):
    try:
        importlib.import_module(module)
    except ImportError as error:
        print(f"BOOTSTRAP-FAILED {module}: {error}", file=sys.stderr)
"""


if __name__ == "__main__":
    unittest.main()
