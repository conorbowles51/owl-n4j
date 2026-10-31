from collections.abc import Generator
from contextlib import contextmanager
import logging
import os
import sys
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from config import DATABASE_URL

logger = logging.getLogger(__name__)

# Lazy initialization - engine and sessionmaker created on first use
_engine = None
_SessionLocal = None

# A wait for a pooled connection at least this long is logged with the process role, so pool exhaustion is
# visible before it becomes a 30 s timeout.
POOL_WAIT_LOG_SECONDS = 1.0


def process_role(argv=None, environ=None):
    """What this process is, for Postgres's application_name: LOUPE_DB_ROLE when set, else the entry point
    (``web`` for uvicorn, ``prepare`` for the release prepare, else the script or module name)."""
    environ = os.environ if environ is None else environ
    if environ.get('LOUPE_DB_ROLE'):
        return environ['LOUPE_DB_ROLE']
    argv = sys.argv if argv is None else argv
    name = os.path.basename(argv[0] if argv else '') or 'python'
    name = name[:-3] if name.endswith('.py') else name
    if name in ('uvicorn', 'gunicorn'):
        return 'web'
    if name == 'view_warmup' and any(flag in argv[1:] for flag in ('--prepare', '--prepare-share')):
        return 'prepare'
    return name


def application_name(argv=None, environ=None, pid=None):
    """``loupe-<role>-<pid>``, within Postgres's 63-byte limit."""
    return ('loupe-%s-%d' % (process_role(argv, environ), os.getpid() if pid is None else pid))[:63]


def _note_pool_wait(seconds, pool):
    """Hands the wait to the request timing (when it records pool waits) and logs a long one."""
    try:
        from services import request_speed
        note = getattr(request_speed, 'note_pool_wait', None)
        if note is not None:
            note(seconds)
    except Exception:
        pass
    if seconds >= POOL_WAIT_LOG_SECONDS:
        logger.warning('Postgres pool wait %.2f s in %s (%s)', seconds, application_name(), pool.status())


class TimedQueuePool(QueuePool):
    """QueuePool that measures how long each checkout waited for a free connection."""

    def _do_get(self):
        started = time.perf_counter()
        try:
            return super()._do_get()
        finally:
            _note_pool_wait(time.perf_counter() - started, self)


def pool_options(environ=None):
    """Pool size, overflow and wait timeout from POSTGRES_POOL_SIZE / POSTGRES_MAX_OVERFLOW /
    POSTGRES_POOL_TIMEOUT; the defaults are SQLAlchemy's own (5, 10, 30 s)."""
    environ = os.environ if environ is None else environ
    return dict(pool_size=int(environ.get('POSTGRES_POOL_SIZE', '5')),
                max_overflow=int(environ.get('POSTGRES_MAX_OVERFLOW', '10')),
                pool_timeout=float(environ.get('POSTGRES_POOL_TIMEOUT', '30')))


def _get_engine():
    """Get or create the database engine."""
    global _engine
    if _engine is None:
        if DATABASE_URL is None:
            raise RuntimeError(
                "DATABASE_URL is not set. Please configure it in your .env file. "
                "Example: DATABASE_URL=postgresql+psycopg://user:password@localhost/dbname"
            )
        # Convert postgresql:// to postgresql+psycopg:// for psycopg3 compatibility
        db_url = DATABASE_URL
        if db_url.startswith("postgresql://") and "+psycopg" not in db_url:
            db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
        elif db_url.startswith("postgres://") and "+psycopg" not in db_url:
            db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
        
        connect_args = {}
        pool_args = {}
        if db_url.startswith("postgresql+psycopg://"):
            connect_args["connect_timeout"] = int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "2"))
            connect_args["application_name"] = application_name()
            pool_args = dict(poolclass=TimedQueuePool, **pool_options())

        _engine = create_engine(
            db_url,
            pool_pre_ping=True,
            connect_args=connect_args,
            **pool_args,
        )
    return _engine


def _get_session_local():
    """Get or create the sessionmaker."""
    global _SessionLocal
    if _SessionLocal is None:
        engine = _get_engine()
        _SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Get a database session."""
    SessionLocal = _get_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_background_session() -> Generator[Session, None, None]:
    """Get a database session for use in background threads outside the request lifecycle."""
    SessionLocal = _get_session_local()
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
