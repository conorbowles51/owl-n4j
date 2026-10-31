from collections.abc import Generator
from contextlib import contextmanager
import logging
import os
import sys
import threading
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from config import DATABASE_URL

logger = logging.getLogger(__name__)

# Lazy initialization - engine and sessionmaker created on first use
_engine = None
_SessionLocal = None
# Web workers only: background work (lifespan loops, background sessions) has its own small pool, so it can never
# take the connections a person's request waits for. Other processes use the one engine.
_background_engine = None
_BackgroundSessionLocal = None

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
    """QueuePool that measures how long each checkout waited for a free connection: once per checkout (QueuePool
    retries call _do_get again), and without the time spent opening a new connection."""

    _timing = threading.local()

    def _do_get(self):
        timing = self._timing
        if getattr(timing, 'depth', 0):
            return super()._do_get()
        timing.depth, timing.connecting = 1, 0.0
        started = time.perf_counter()
        try:
            return super()._do_get()
        finally:
            timing.depth = 0
            _note_pool_wait(max(0.0, time.perf_counter() - started - timing.connecting), self)

    def _create_connection(self):
        started = time.perf_counter()
        try:
            return super()._create_connection()
        finally:
            timing = self._timing
            if getattr(timing, 'depth', 0):
                timing.connecting += time.perf_counter() - started


def pool_options(environ=None, prefix='POSTGRES', defaults=(5, 10, 30)):
    """Pool size, overflow and wait timeout from <prefix>_POOL_SIZE / _MAX_OVERFLOW / _POOL_TIMEOUT; the request
    pool's defaults are SQLAlchemy's own (5, 10, 30 s)."""
    environ = os.environ if environ is None else environ

    def read(suffix, kind, default):
        # A value that is not a number (or is negative) keeps the default and says so, instead of failing every
        # request at its first database use.
        raw = environ.get(prefix + suffix)
        if raw is None or not str(raw).strip():
            return kind(default)
        try:
            value = kind(str(raw).strip())
        except ValueError:
            value = None
        if value is None or value < 0:
            logger.warning('%s%s=%r is not a usable number; using the default %s', prefix, suffix, raw, default)
            return kind(default)
        return value

    return dict(pool_size=read('_POOL_SIZE', int, defaults[0]),
                max_overflow=read('_MAX_OVERFLOW', int, defaults[1]),
                pool_timeout=read('_POOL_TIMEOUT', float, defaults[2]))


# The web worker's background pool: 2 kept + 6 more when busy (POSTGRES_BACKGROUND_*).
BACKGROUND_POOL_DEFAULTS = (2, 6, 30)


def _database_url():
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
    return db_url


def _new_engine(db_url, role_suffix='', prefix='POSTGRES', defaults=(5, 10, 30)):
    connect_args = {}
    pool_args = {}
    if db_url.startswith("postgresql+psycopg://"):
        connect_args["connect_timeout"] = int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "2"))
        name = application_name()
        if role_suffix:
            role, _, pid = name.rpartition('-')
            name = ('%s%s-%s' % (role, role_suffix, pid))[:63]
        connect_args["application_name"] = name
        pool_args = dict(poolclass=TimedQueuePool, **pool_options(prefix=prefix, defaults=defaults))
    return create_engine(
        db_url,
        pool_pre_ping=True,
        connect_args=connect_args,
        **pool_args,
    )


# Guards the first build of each engine/sessionmaker: without it, threads arriving together each build an engine
# and all but one leak their pool's connections until exit.
_build_lock = threading.RLock()


def _get_engine():
    """Get or create the database engine."""
    global _engine
    if _engine is None:
        with _build_lock:
            if _engine is None:
                _engine = _new_engine(_database_url())
    return _engine


def _get_session_local():
    """Get or create the sessionmaker."""
    global _SessionLocal
    if _SessionLocal is None:
        with _build_lock:
            if _SessionLocal is None:
                engine = _get_engine()
                _SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return _SessionLocal


def _get_background_session_local():
    """The sessionmaker for background work: in a web worker on Postgres, its own pool; elsewhere the one
    sessionmaker (so a process has one pool, and tests that replace _get_session_local are followed)."""
    global _background_engine, _BackgroundSessionLocal
    if process_role() != 'web' or not _database_url().startswith('postgresql+psycopg://'):
        return _get_session_local()
    if _BackgroundSessionLocal is None:
        with _build_lock:
            if _BackgroundSessionLocal is None:
                _background_engine = _new_engine(_database_url(), '-bg', 'POSTGRES_BACKGROUND',
                                                 BACKGROUND_POOL_DEFAULTS)
                _BackgroundSessionLocal = sessionmaker(bind=_background_engine, autoflush=False, autocommit=False)
    return _BackgroundSessionLocal


def _get_background_engine():
    """The engine behind _get_background_session_local (for work that needs a connection of its own)."""
    if process_role() != 'web' or not _database_url().startswith('postgresql+psycopg://'):
        return _get_engine()
    _get_background_session_local()
    return _background_engine


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
    SessionLocal = _get_background_session_local()
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
