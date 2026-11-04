"""An empty SQLite schema built once per test process and copied into each test's own database file.

``MetaData.create_all`` on a fresh file costs a table check and a CREATE per table, every test (0.41 s of the
0.86 s ``DuplicateTestCase.setUp``, measured under cProfile on the shared box). The schema is the same for every
test of a fixture, so it is created once into a template file and each test starts from a byte copy of it: the
same DDL, still an empty database of the test's own, still deleted with the test's directory.
"""
from __future__ import annotations

import atexit
import os
import shutil
import tempfile

from sqlalchemy import create_engine

_templates: dict[tuple, str] = {}
_root: str | None = None


def _template_root() -> str:
    global _root
    if _root is None or not os.path.isdir(_root):
        _root = tempfile.mkdtemp(prefix="loupe-schema-templates-")
        atexit.register(shutil.rmtree, _root, True)
    return _root


def copy_empty_schema(path, metadata, tables) -> None:
    """Write an empty SQLite database holding ``tables`` (created as ``metadata.create_all(tables=tables)``
    would) to ``path``."""
    key = (id(metadata), tuple(table.fullname for table in tables))
    template = _templates.get(key)
    if template is None or not os.path.exists(template):
        template = os.path.join(_template_root(), f"schema-{len(_templates)}.db")
        engine = create_engine(f"sqlite+pysqlite:///{template}", future=True)
        try:
            metadata.create_all(engine, tables=tables)
        finally:
            engine.dispose()
        _templates[key] = template
    shutil.copyfile(template, path)
