from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from config import DATABASE_URL

# Lazy initialization - engine and sessionmaker created on first use
_engine = None
_SessionLocal = None


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
        
        _engine = create_engine(
            db_url,
            pool_pre_ping=True,
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
