"""Portable, versioned case export and import.

A package is one tar file holding a whole case: its PostgreSQL rows, its graph, its vectors and its evidence files, with
a versioned manifest giving every part's row count and SHA-256. ``docs/case-export.md`` is the operator's description.

- ``inventory``: which tables make up a case, computed from the database's own catalog, and what is left out and why.
- ``package``: the format: writing a package to disk as a stream, and verifying one.
- ``export``: building a package from a live case.
- ``importer``: loading a verified package into a new case, never over an existing one.
- ``jobs``: export as background work.
- ``__main__``: the commands ``python -m services.caseport verify|export|import``.

Nothing here imports the web application or the ORM models: an export runs as a small process of its own.
"""
