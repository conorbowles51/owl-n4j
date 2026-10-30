"""Deployment-wide vector-search confidence threshold, read at every search.

The threshold used to live in the memory of whichever API process handled the change (config module attribute
plus os.environ), while rag_service had copied the start-up value by name at import, so a change reached no
search at all until a restart, and after a restart it was gone. The value is now one row of ai_model_policies
(key 'vector_search'), shared by every worker process, read when a search runs. Without a row, the start-up
value from config (VECTOR_SEARCH_CONFIDENCE_THRESHOLD, environment) applies.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

import config
from postgres.models.runtime_state import AIModelPolicy

logger = logging.getLogger(__name__)

SETTINGS_KEY = "vector_search"
MIN_THRESHOLD = 0.0
MAX_THRESHOLD = 5.0


def _stored(db: Session) -> float | None:
    record = db.get(AIModelPolicy, SETTINGS_KEY)
    value = (record.configuration or {}).get("confidence_threshold") if record is not None else None
    return float(value) if value is not None else None


def get_confidence_threshold(db: Session | None = None) -> float:
    """The threshold in force now: the saved setting, else the start-up value."""
    try:
        if db is not None:
            stored = _stored(db)
        else:
            from postgres.session import get_background_session

            with get_background_session() as session:
                stored = _stored(session)
    except Exception:
        logger.exception("vector search threshold: saved setting unreadable, using the start-up value")
        stored = None
    return stored if stored is not None else float(config.VECTOR_SEARCH_CONFIDENCE_THRESHOLD)


def set_confidence_threshold(db: Session, threshold: float, *, updated_by: str | None) -> float:
    threshold = float(threshold)
    if not (MIN_THRESHOLD <= threshold <= MAX_THRESHOLD):
        raise ValueError(f"Confidence threshold must be between {MIN_THRESHOLD} and {MAX_THRESHOLD}")
    record = db.get(AIModelPolicy, SETTINGS_KEY)
    if record is None:
        record = AIModelPolicy(key=SETTINGS_KEY, revision=1, configuration={"confidence_threshold": threshold},
                               updated_by=updated_by)
        db.add(record)
    else:
        record.configuration = {**(record.configuration or {}), "confidence_threshold": threshold}
        record.revision = (record.revision or 0) + 1
        record.updated_by = updated_by
    db.commit()
    return threshold
