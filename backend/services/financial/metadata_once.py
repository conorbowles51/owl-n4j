"""Read several fields of a large stored JSON column with one decompression per row (PostgreSQL)."""
from sqlalchemy import case, func, literal, select, type_coerce


def read_once(session, column):
    """The saved metadata as PostgreSQL decompresses it once per row, and how to join it.

    Each field read from a large stored JSON value decompresses the whole value again (d5b330d1: 1,367 saved
    statements, 120 MB stored, 0.7 s per field). Concatenating an empty object makes one in-memory copy per row,
    equal to the stored object, made once in a lateral subquery that every field then reads. A value that is not
    an object is read as stored. Other databases read the column as before: ``(column, None)``.

    Use: ``metadata, once = read_once(session, Model.metadata_)``; select fields of ``metadata``, add
    ``.select_from(Model)`` and, when ``once`` is not None, ``.join(once, true())``.
    """
    if session.get_bind().dialect.name != 'postgresql':
        return column, None
    copy = case((func.jsonb_typeof(column) == 'object', column.op('||')(literal({}, column.type))), else_=column)
    once = select(type_coerce(copy, column.type).label('metadata')).correlate(column.table).offset(0).lateral('metadata_once')
    return once.c.metadata, once
