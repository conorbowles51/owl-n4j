"""Retry a database write that lost a deadlock or serialization conflict."""
import asyncio
import logging

logger = logging.getLogger(__name__)

# Postgres aborts one side of a deadlock or serialization conflict and the
# other proceeds; the aborted transaction is safe to run again. Evidence
# rows take a per-case audit lock, so many preparation jobs of one case
# (a large batch) can deadlock on a status write. Such a write is retried
# instead of failing the whole file (live: 30 files in 72 h, all deadlocks).
TRANSIENT_SQLSTATES = frozenset({"40P01", "40001"})
TRANSIENT_ATTEMPTS = 5


def is_transient_db_error(error: BaseException) -> bool:
    """True when ``error`` (or its cause) is a deadlock or serialization failure."""
    seen = set()
    current = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        code = getattr(current, "sqlstate", None) or getattr(current, "pgcode", None)
        if code in TRANSIENT_SQLSTATES or type(current).__name__ in (
                "DeadlockDetectedError", "SerializationError"):
            return True
        current = getattr(current, "orig", None) or current.__cause__
    return False


async def retry_transient(operation, *, attempts: int = TRANSIENT_ATTEMPTS, base_delay: float = 0.2):
    """Run ``operation()`` again after a deadlock or serialization failure, with backoff."""
    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except Exception as error:
            if attempt == attempts or not is_transient_db_error(error):
                raise
            logger.warning("Transient database conflict (attempt %d of %d); retrying", attempt, attempts)
            await asyncio.sleep(base_delay * attempt)
