"""The package's public surface, checked against the modules behind it.

``services.financial.__init__`` is the single place this package declares what
it exports; no module carries its own ``__all__``.  That is a deliberate choice
-- two declarations would need keeping in step -- but it has a failure mode, and
the failure mode has already happened once: ``locators`` was added as a module,
imported directly by its tests, and left out of ``__init__`` entirely.  Nothing
failed, because nothing was looking.  The module was simply unreachable by the
route every other module is reached by, and stayed that way through a commit.

So the invariant asserted here is module reachability: every module in the
package contributes at least one name to ``__all__``.

It is worth being plain about what that does *not* check.  It is not a
name-by-name completeness check, and it must not be mistaken for one.  Several
modules deliberately keep public-looking names out of ``__all__`` --
``money.Marker`` and ``runs.SessionFactory`` are type aliases, ``version.reset_caches``
exists for tests -- and a rule demanding every public name be exported would
force those into the package surface to go green, which is worse than the
problem.  A partial guard that admits it is partial beats a total one that
would have to be neutered with a suppression list.
"""
from __future__ import annotations

import ast
import pathlib
import unittest

import services.financial as package

PACKAGE_ROOT = pathlib.Path(package.__file__).parent


def _module_paths() -> list[pathlib.Path]:
    return sorted(p for p in PACKAGE_ROOT.glob("*.py") if p.name != "__init__.py")


def _definitions(path: pathlib.Path) -> list[str]:
    """Every name this file binds at module level, read from the source.

    Parsed rather than imported so that a name this module merely *imports*
    from a sibling cannot be mistaken for one it defines -- otherwise a module
    that imports an exported constant would appear to contribute an export
    while contributing nothing, which is the exact condition being tested for.

    Underscored names are kept here and filtered by the caller that wants them
    gone.  Doing the filtering in this function is how the ``__all__`` check
    below was first written to be incapable of failing: ``__all__`` begins with
    an underscore, so a private-name filter applied here silently removes the
    one name that check exists to look for.
    """
    tree = ast.parse(path.read_text())
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(node.name)
        elif isinstance(node, ast.Assign):
            names.extend(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
    return names


def _public_definitions(path: pathlib.Path) -> list[str]:
    """The subset of :func:`_definitions` that the package could export."""
    return [name for name in _definitions(path) if not name.startswith("_")]


class PackageSurfaceTests(unittest.TestCase):
    def test_every_module_is_reachable_from_the_package(self):
        """No module may be invisible from ``services.financial``.

        This is the check that would have caught ``locators`` going unexported.
        """
        exported = set(package.__all__)
        for path in _module_paths():
            with self.subTest(module=path.name):
                defined = _public_definitions(path)
                self.assertTrue(
                    defined,
                    f"{path.name} defines no public names at all",
                )
                self.assertTrue(
                    exported.intersection(defined),
                    f"{path.name} contributes nothing to services.financial.__all__; "
                    "it can only be reached by importing the module directly",
                )

    def test_every_exported_name_resolves(self):
        """A name in ``__all__`` that does not exist breaks ``import *`` only.

        Which means it can sit there indefinitely -- nothing else consults the
        list -- until someone uses the one form of import that reads it.
        """
        for name in package.__all__:
            with self.subTest(name=name):
                self.assertTrue(
                    hasattr(package, name),
                    f"{name} is exported but not bound on the package",
                )

    def test_no_name_is_exported_twice(self):
        """Two modules exporting one name means one of them is shadowed.

        The import that lands second wins silently, so the collision shows up
        as a function behaving like a different function of the same name.
        """
        seen = sorted(
            {name for name in package.__all__ if package.__all__.count(name) > 1}
        )
        self.assertEqual(seen, [])

    def test_no_module_declares_its_own_all(self):
        """One declaration of the public surface, not two.

        ``table_geometry`` briefly carried its own ``__all__``, which is how a
        module can look exported while the package knows nothing about it.
        """
        for path in _module_paths():
            with self.subTest(module=path.name):
                self.assertNotIn("__all__", _definitions(path))
