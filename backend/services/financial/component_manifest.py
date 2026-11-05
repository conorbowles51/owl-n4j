"""The software behind one processing run, stored with the run when it starts.

A later export reads this record; it never substitutes the versions installed at export time for the versions that
did the work. Model names are the configured names: a provider's answer may not prove a fixed model revision.
"""
from datetime import datetime, timezone
from importlib import metadata
import os
import platform

COMPONENT_SCHEMA = 'loupe.financial.component_manifest/1'
_PACKAGES = ('PyMuPDF', 'pdfplumber', 'pypdf', 'Pillow', 'pytesseract', 'openai', 'anthropic', 'SQLAlchemy', 'pydantic')
_MODEL_SETTINGS = ('OPENAI_MODEL', 'OPENAI_EXTRACTION_MODEL', 'OPENAI_VISION_MODEL', 'LLM_MODEL')
_installed = {}


def _package_versions():
    if not _installed:
        for name in _PACKAGES:
            try:
                _installed[name] = metadata.version(name)
            except metadata.PackageNotFoundError:
                _installed[name] = None
    return dict(_installed)


def _running_commit():
    from services.runtime_version import record_started_commit, started_commit
    # A worker process has not been through the web process's start-up; its checkout is the one it started from.
    return started_commit() if started_commit().get('commit') else record_started_commit()


def run_components():
    """Never raises: a run that cannot describe itself is still recorded, with what is unknown left empty."""
    from services.financial.statement_import_proposal import VERSION as statement_reader
    from services.financial.version import PIPELINE_VERSION, code_version
    try:
        commit = _running_commit()
    except Exception:
        commit = dict(commit=None, commit_clean=False)
    return dict(schema_version=COMPONENT_SCHEMA, recorded_at=datetime.now(timezone.utc).isoformat(),
        commit=commit.get('commit'), commit_clean=bool(commit.get('commit_clean')), code_version=code_version(),
        pipeline_version=PIPELINE_VERSION, statement_reader=statement_reader, python_version=platform.python_version(),
        packages=_package_versions(), configured_models={name: os.environ.get(name) or None for name in _MODEL_SETTINGS})
