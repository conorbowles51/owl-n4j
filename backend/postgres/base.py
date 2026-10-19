from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.compiler import compiles


@compiles(UUID, "sqlite")
def _sqlite_uuid_as_text(type_, compiler, **kwargs):
    # SQLite gives a column declared UUID numeric affinity. A randomly generated
    # UUID containing only digits (or exponent-like text) can therefore become a
    # float and lose identity on INSERT ... RETURNING. PostgreSQL retains its
    # native UUID type; local SQLite fixtures must store the bound hex as text.
    return "CHAR(32)"


class Base(DeclarativeBase):
    pass
