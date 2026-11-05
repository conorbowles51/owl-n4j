"""What counts as the embedding service refusing or being out, and which ingestion steps went without it.

Embeddings are OpenAI only (app/config.py). A refusal (no credits, rate limit, key rejected, outage) says nothing about
the file being ingested, so it never fails an ingestion: chunks wait in ``pending_chunk_vectors``, entities carry
``vector_pending``, and the steps that only improve on the result are skipped and recorded. Anything else (a bad
request, an oversized text, a bug) still fails the file.
"""
from __future__ import annotations

from contextvars import ContextVar

from openai import (
    APIConnectionError,
    AuthenticationError,
    InternalServerError,
    PermissionDeniedError,
    RateLimitError,
)

# APITimeoutError is an APIConnectionError.
_REFUSALS = (
    APIConnectionError,
    AuthenticationError,
    InternalServerError,
    PermissionDeniedError,
    RateLimitError,
)
_NOT_CONNECTED = "openai is not connected"  # app/services/openai_client.py get_openai_client

ENTITY_DEDUP_SKIPPED = "entity_dedup_without_embeddings"
ENTITY_VECTORS_PENDING = "entity_vectors_pending"

_skipped: ContextVar[list[str] | None] = ContextVar("embedding_skipped_steps", default=None)


def is_embedding_refusal(exc: BaseException) -> bool:
    if isinstance(exc, _REFUSALS):
        return True
    return isinstance(exc, ValueError) and _NOT_CONNECTED in str(exc).lower()


def start_collecting_skipped() -> list[str]:
    """The list this ingestion's skipped steps land in; tasks it starts share it."""
    steps: list[str] = []
    _skipped.set(steps)
    return steps


def note_skipped(step: str) -> None:
    """Record a step that ran without embeddings, for the run's quality report."""
    steps = _skipped.get()
    if steps is not None and step not in steps:
        steps.append(step)


def chunk_progress_message(chunks: list) -> str:
    waiting = sum(1 for chunk in chunks if chunk.metadata.get("vector_pending"))
    message = f"Created {len(chunks)} chunks"
    return f"{message}; {waiting} wait for the search service" if waiting else message
