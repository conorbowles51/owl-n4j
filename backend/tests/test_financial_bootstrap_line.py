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

import functools
import importlib.metadata as metadata
import json
import pathlib
import re
import subprocess
import sys
import unittest

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet

BACKEND = pathlib.Path(__file__).resolve().parents[1]
CLAUDE_MD = BACKEND.parent / "CLAUDE.md"
REQUIREMENTS = BACKEND / "requirements.txt"
PIN = re.compile(r'"([A-Za-z0-9._-]+)(?:\[[^\]]*\])?==([^"]+)"')
REQUIREMENT = re.compile(r"^([A-Za-z0-9._-]+)(?:\[[^\]]*\])?\s*(.*)$")

# On the line but not in requirements.txt, with the reason.
TEST_ONLY = {"pytest": "test runner; test modules import it, the app does not",
             "pytest-asyncio": "runs the asyncio-marked tests (evidence routes, uploads, websocket auth)"}
# A test marker that only a pytest plugin understands: without the plugin pytest fails the
# test with "async def functions are not natively supported" instead of running it.
MARKER_PLUGINS = {re.compile(r"^\s*@pytest\.mark\.asyncio\b", re.M): "pytest-asyncio"}


# Import name -> distribution where they differ and the distribution may not be installed here to say so.
IMPORT_ALIASES = {"docx": "python-docx", "whisper": "openai-whisper", "PIL": "pillow", "fitz": "pymupdf",
                  "yaml": "pyyaml", "jose": "python-jose", "dotenv": "python-dotenv", "dateutil": "python-dateutil",
                  "magic": "python-magic", "multipart": "python-multipart"}
# requirements.txt packages a module the suite imports loads inside a function, deliberately not on the line, with
# the reason. Anything else such a module loads lazily must be on the line, or the suite goes red in a venv built
# from it (python-docx and weasyprint, tests/test_agent_artifact_exports.py, 4 Nov: 11 of 14 job venvs lacked one).
NOT_ON_LINE = {
    "chromadb": "VectorDBService degrades without it and prints a warning (CLAUDE.md)",
    "openai-whisper": "pulls torch; phone audio derivation reports the transcriber as unavailable",
    "transformers": "pulls torch; phone image search and translation report the model as unavailable",
    "langchain-anthropic": "loaded only when an Anthropic agent model is chosen; ImportError is a named ValueError",
    "langchain-google-genai": "loaded only when a Gemini agent model is chosen; ImportError is a named ValueError",
    "redis": "opened only when the job-status subscriber or evidence websocket connects to a Redis server",
    "reverse-geocoder": "the geocoder factory catches ImportError and turns the offline backend off",
    "markdown-it-py": "markdown readers (routers/backfill.py, utils/text_extraction.py) fall back to regex stripping on ImportError",
}
# A function-body import (indented), the only kind importing the module does not reach.
LAZY_IMPORT = re.compile(r"^[ \t]+(?:from[ \t]+([A-Za-z_][A-Za-z0-9_]*)[.A-Za-z0-9_]*[ \t]+import|"
                         r"import[ \t]+([A-Za-z_][A-Za-z0-9_]*))", re.M)
BACKEND_IMPORT = re.compile(r"^\s*(?:from[ \t]+((?:services|routers|postgres)(?:\.[A-Za-z0-9_]+)*)[ \t]+import[ \t]+"
                            r"([A-Za-z0-9_, ()]+)|import[ \t]+((?:services|routers|postgres)(?:\.[A-Za-z0-9_]+)*))", re.M)


def _backend_modules_of(test_text: str) -> set[pathlib.Path]:
    """The backend source files a test module imports by name (``from services.x import y`` gives services/x.py,
    or services/x/y.py when y is a module)."""
    found = set()
    for package, names, plain in BACKEND_IMPORT.findall(test_text):
        dotted = package or plain
        base = BACKEND.joinpath(*dotted.split("."))
        candidates = [base.with_suffix(".py"), base / "__init__.py"]
        for name in re.findall(r"[A-Za-z0-9_]+", names or ""):
            candidates.append((base / name).with_suffix(".py"))
        found.update(path for path in candidates if path.is_file())
    return found


@functools.lru_cache(maxsize=1)
def _packages_distributions() -> dict[str, list[str]]:
    return metadata.packages_distributions()


@functools.lru_cache(maxsize=None)
def _lazy_requirements_of(source: pathlib.Path) -> frozenset[str]:
    """Every distribution name ``source`` imports inside a function body (requirements.txt or not)."""
    dists_of = _packages_distributions()
    out = set()
    for groups in LAZY_IMPORT.findall(source.read_text()):
        name = groups[0] or groups[1]
        if name not in sys.stdlib_module_names:
            out |= {_norm(d) for d in dists_of.get(name, [])} | {_norm(IMPORT_ALIASES.get(name, name))}
    return frozenset(out)


def _lazy_requirements(source: pathlib.Path, specs: dict[str, str]) -> set[str]:
    """requirements.txt distributions ``source`` imports inside a function body."""
    return set(_lazy_requirements_of(source)) & set(specs)


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _bootstrap_line() -> str:
    lines = [line for line in CLAUDE_MD.read_text().splitlines()
             if line.startswith("pip install --break-system-packages")]
    assert len(lines) == 1, f"expected one bootstrap pip line in CLAUDE.md, found {len(lines)}"
    return lines[0]


def _bootstrap_pins() -> dict[str, str]:
    return {_norm(name): version for name, version in PIN.findall(_bootstrap_line())}


def _bootstrap_extras() -> dict[str, set[str]]:
    """``psycopg[binary]`` -> {"psycopg": {"binary"}}: the extras the line asks pip for."""
    return {_norm(name): {_norm(extra) for extra in extras.split(",")}
            for name, extras in re.findall(r'"([A-Za-z0-9._-]+)\[([^\]]*)\]==', _bootstrap_line())}


def _requirement_specs() -> dict[str, str]:
    specs = {}
    for line in REQUIREMENTS.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        match = REQUIREMENT.match(line)
        if match:
            specs[_norm(match.group(1))] = match.group(2).split(";", 1)[0].strip()
    return specs


def _with_dependencies(names: set[str], extras: dict[str, set[str]]) -> set[str]:
    """The distributions a real install of ``names`` brings in here: each requirement's environment marker is
    evaluated (platform, python_version, and ``extra`` against the extras the line asks for), as pip does."""
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
        for text in requires:
            requirement = Requirement(text)
            if requirement.marker is not None and not any(
                    requirement.marker.evaluate({"extra": extra}) for extra in sorted(extras.get(name, set())) or [""]):
                continue
            todo.append(_norm(requirement.name))
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

    def test_pytest_markers_have_their_plugin_on_the_line(self):
        pins = _bootstrap_pins()
        missing = {}
        for path in sorted((BACKEND / "tests").glob("test_*.py")):
            text = path.read_text()
            for marker, plugin in MARKER_PLUGINS.items():
                if marker.search(text) and plugin not in pins:
                    missing.setdefault(plugin, []).append(path.name)
        self.assertEqual(missing, {}, "plugin -> test modules whose marker needs it")

    def test_packages_the_suite_loads_lazily_are_on_the_line(self):
        # Importing a module cannot see an import inside one of its functions (the module-import test below), so a
        # test that calls that function goes red only in a fresh venv. Every backend module a test imports by name
        # is read for function-body imports of requirements.txt packages; each must come with the line (pinned, or
        # a dependency of a pin) or be in NOT_ON_LINE with its reason.
        specs = _requirement_specs()
        covered = _with_dependencies(set(_bootstrap_pins()), _bootstrap_extras())
        missing = {}
        for test in sorted((BACKEND / "tests").glob("test_*.py")):
            for source in _backend_modules_of(test.read_text()):
                for dist in _lazy_requirements(source, specs) - covered - set(NOT_ON_LINE):
                    missing.setdefault(dist, set()).add(f"{test.name} -> {source.relative_to(BACKEND)}")
        self.assertEqual({dist: sorted(where) for dist, where in missing.items()}, {},
                         "requirements.txt package -> test -> module that imports it inside a function")

    def test_lazy_import_scan_finds_function_body_imports_only(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory, "m.py")
            source.write_text("import weasyprint\n\ndef f():\n    from docx import Document\n    import json\n")
            self.assertEqual(_lazy_requirements(source, {"python-docx": "", "weasyprint": ""}), {"python-docx"})
        self.assertIn(BACKEND / "services" / "agent" / "exports.py",
                      _backend_modules_of("from services.agent.exports import render_report_pdf\n"))

    def test_extras_on_the_line_are_followed(self):
        self.assertEqual(_bootstrap_extras().get("psycopg"), {"binary"})
        try:
            metadata.distribution("psycopg-binary")
        except metadata.PackageNotFoundError:
            self.skipTest("psycopg-binary not installed here")
        self.assertIn("psycopg-binary", _with_dependencies({"psycopg"}, _bootstrap_extras()))

    def test_requirements_a_real_install_skips_are_not_followed(self):
        from types import SimpleNamespace
        from unittest import mock
        requires = {"top": ['winonly; sys_platform == "win32" and sys_platform != "' + sys.platform + '"',
                            'oldpython; python_version < "3.0"', 'always', 'withbinary; extra == "binary"',
                            'withother; extra == "other"', 'newpython; python_version >= "3.0"']}

        def distribution(name):
            if name not in requires:
                raise metadata.PackageNotFoundError(name)
            return SimpleNamespace(requires=requires[name])
        with mock.patch.object(metadata, "distribution", distribution):
            self.assertEqual(_with_dependencies({"top"}, {}), {"top", "always", "newpython"})
            self.assertEqual(_with_dependencies({"top"}, {"top": {"binary"}}),
                             {"top", "always", "newpython", "withbinary"})

    def test_suite_imports_with_only_what_the_line_installs(self):
        # A fresh sandbox has only the line and its dependencies. Simulate it: in a child interpreter,
        # refuse every installed distribution outside that set, then import what the suite imports.
        # Optional imports (chromadb, python-magic) degrade on ImportError exactly as they do there.
        covered = sorted(_with_dependencies(set(_bootstrap_pins()), _bootstrap_extras()))
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
