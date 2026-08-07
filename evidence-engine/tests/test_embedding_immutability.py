import inspect
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import EMBEDDING_MODEL, EMBEDDING_PROVIDER
from app.services.openai_client import embed_texts


EVIDENCE_ENGINE_DIR = Path(__file__).resolve().parents[1]


def test_evidence_engine_embedding_api_is_fixed() -> None:
    assert EMBEDDING_PROVIDER == "openai"
    assert EMBEDDING_MODEL == "text-embedding-3-small"
    assert list(inspect.signature(embed_texts).parameters) == ["texts"]


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("EMBEDDING_PROVIDER", "ollama"),
        ("EMBEDDING_MODEL", "text-embedding-3-large"),
        ("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"),
    ],
)
def test_evidence_engine_rejects_embedding_environment_overrides(
    variable: str,
    value: str,
) -> None:
    environment = os.environ.copy()
    environment[variable] = value
    result = subprocess.run(
        [sys.executable, "-c", "import app.config"],
        cwd=EVIDENCE_ENGINE_DIR,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert f"{variable} is fixed" in result.stderr
