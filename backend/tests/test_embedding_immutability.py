import inspect
import os
import subprocess
import sys
from pathlib import Path

import pytest

from config import EMBEDDING_MODEL, EMBEDDING_PROVIDER
from services.embedding_service import EmbeddingService


BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_embedding_service_has_one_fixed_provider_and_model() -> None:
    service = EmbeddingService()

    assert service.provider == "openai"
    assert service.model == "text-embedding-3-small"
    assert EMBEDDING_PROVIDER == service.provider
    assert EMBEDDING_MODEL == service.model
    assert service.get_embedding_dimension() == 1536


def test_embedding_service_does_not_accept_runtime_overrides() -> None:
    assert list(inspect.signature(EmbeddingService).parameters) == []

    with pytest.raises(TypeError):
        EmbeddingService(provider="ollama")  # type: ignore[call-arg]

    with pytest.raises(TypeError):
        EmbeddingService(model="text-embedding-3-large")  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("EMBEDDING_PROVIDER", "ollama"),
        ("EMBEDDING_MODEL", "text-embedding-3-large"),
    ],
)
def test_backend_rejects_embedding_environment_overrides(
    variable: str,
    value: str,
) -> None:
    environment = os.environ.copy()
    environment[variable] = value
    result = subprocess.run(
        [sys.executable, "-c", "import config"],
        cwd=BACKEND_DIR,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert f"{variable} is fixed" in result.stderr
