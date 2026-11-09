"""Guidance settings per person and per case (lx-guide).

A person's choices live in ``phone_user_marks`` (the marks table: one row per person and mark, so a choice follows them
to any browser), under names starting ``guide:``:

- ``guide:off`` / ``guide:on``: the person turned guidance off or on. At most one of the two exists.
- ``guide:tip_off:<kind>``: "Don't show tips like this" for one kind of tip.
- ``guide:tour:<area>:done`` / ``guide:tour:<area>:skipped``: a tour was finished or skipped.
- ``guide:tour:<area>:step:<n>``: where a tour was left, so it resumes there.
- ``guide:history:collapsed``: the step history strip is folded to one History button.

A case admin may set the case default in ``case_guidance``. The person's own choice wins; with neither, guidance is on.
Off means no tours and no popups; next steps after an action still show, as a quiet link.
"""
from __future__ import annotations

import re

from sqlalchemy import text

PREFIX = "guide:"
NAME = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")
TOUR_STATES = ("done", "skipped")


class GuidanceError(ValueError):
    pass


def _name(value: str) -> str:
    if not NAME.match(value or ""):
        raise GuidanceError("Use lower-case letters, digits, '-' or '_' (up to 40).")
    return value


def _marks(conn, user_id) -> list[str]:
    return [r.mark for r in conn.execute(
        text("SELECT mark FROM phone_user_marks WHERE user_id = :u AND mark LIKE 'guide:%' ORDER BY mark"),
        {"u": str(user_id)})]


def _add(conn, user_id, mark: str) -> None:
    conn.execute(text("INSERT INTO phone_user_marks (user_id, mark) VALUES (:u, :m) ON CONFLICT DO NOTHING"),
                 {"u": str(user_id), "m": mark})


def _drop(conn, user_id, *, exact: str | None = None, prefix: str | None = None) -> None:
    if exact is not None:
        conn.execute(text("DELETE FROM phone_user_marks WHERE user_id = :u AND mark = :m"),
                     {"u": str(user_id), "m": exact})
    if prefix is not None:
        conn.execute(text("DELETE FROM phone_user_marks WHERE user_id = :u AND starts_with(mark, :p)"),
                     {"u": str(user_id), "p": prefix})


def case_default(conn, case_id) -> str | None:
    if case_id is None:
        return None
    return conn.execute(text("SELECT guidance FROM case_guidance WHERE case_id = :c"), {"c": str(case_id)}).scalar()


def resolve(marks: list[str], case_value: str | None) -> dict:
    """The settings one person sees, from their marks and the case default (pure; no database)."""
    own = "off" if f"{PREFIX}off" in marks else "on" if f"{PREFIX}on" in marks else None
    tours: dict[str, dict] = {}
    tips_off: list[str] = []
    for mark in marks:
        parts = mark.split(":")
        if len(parts) == 3 and parts[1] == "tip_off":
            tips_off.append(parts[2])
        elif len(parts) == 4 and parts[1] == "tour" and parts[3] in TOUR_STATES:
            tours.setdefault(parts[2], {})["state"] = parts[3]
        elif len(parts) == 5 and parts[1] == "tour" and parts[3] == "step" and parts[4].isdigit():
            tours.setdefault(parts[2], {})["step"] = int(parts[4])
    history_collapsed = f"{PREFIX}history:collapsed" in marks
    guidance = own or case_value or "on"
    source = "user" if own else "case" if case_value else "default"
    return {"guidance": guidance, "source": source, "case_default": case_value, "tips_off": tips_off, "tours": tours,
            "history_collapsed": history_collapsed}


def read(conn, user_id, case_id=None) -> dict:
    return resolve(_marks(conn, user_id), case_default(conn, case_id))


def set_guidance(conn, user_id, value: str, case_id=None) -> dict:
    """``on`` / ``off``: the person's own choice; it wins over the case default."""
    if value not in ("on", "off"):
        raise GuidanceError("Guidance is 'on' or 'off'.")
    _drop(conn, user_id, exact=f"{PREFIX}{'off' if value == 'on' else 'on'}")
    _add(conn, user_id, f"{PREFIX}{value}")
    return read(conn, user_id, case_id)


def hide_tip(conn, user_id, kind: str, case_id=None) -> dict:
    _add(conn, user_id, f"{PREFIX}tip_off:{_name(kind)}")
    return read(conn, user_id, case_id)


def show_tips_again(conn, user_id, case_id=None) -> dict:
    """"Show again": hidden tip kinds and finished or skipped tours come back."""
    _drop(conn, user_id, prefix=f"{PREFIX}tip_off:")
    _drop(conn, user_id, prefix=f"{PREFIX}tour:")
    return read(conn, user_id, case_id)


def set_tour(conn, user_id, area: str, *, state: str | None = None, step: int | None = None, case_id=None) -> dict:
    """Keep where a tour is: ``step`` (resume there), or ``state`` done/skipped; ``state='reset'`` starts it again."""
    area = _name(area)
    base = f"{PREFIX}tour:{area}:"
    if state == "reset":
        _drop(conn, user_id, prefix=base)
        return read(conn, user_id, case_id)
    if state is not None and state not in TOUR_STATES:
        raise GuidanceError("A tour is 'done', 'skipped' or 'reset'.")
    if step is not None:
        if step < 0 or step > 50:
            raise GuidanceError("A tour step is 0 to 50.")
        _drop(conn, user_id, prefix=f"{base}step:")
        _add(conn, user_id, f"{base}step:{step}")
    if state is not None:
        for other in TOUR_STATES:
            _drop(conn, user_id, exact=f"{base}{other}")
        _add(conn, user_id, f"{base}{state}")
    return read(conn, user_id, case_id)


def set_history_collapsed(conn, user_id, collapsed: bool, case_id=None) -> dict:
    mark = f"{PREFIX}history:collapsed"
    if collapsed:
        _add(conn, user_id, mark)
    else:
        _drop(conn, user_id, exact=mark)
    return read(conn, user_id, case_id)


def set_case_default(conn, case_id, value: str | None, user_id) -> str | None:
    """A case admin's default for everyone in the case; ``None`` removes it (guidance is then on unless a person
    turned it off)."""
    if value is None:
        conn.execute(text("DELETE FROM case_guidance WHERE case_id = :c"), {"c": str(case_id)})
        return None
    if value not in ("on", "off"):
        raise GuidanceError("The case default is 'on' or 'off'.")
    conn.execute(text("INSERT INTO case_guidance (case_id, guidance, set_by_user_id) VALUES (:c, :g, :u) "
                      "ON CONFLICT (case_id) DO UPDATE SET guidance = EXCLUDED.guidance, "
                      "set_by_user_id = EXCLUDED.set_by_user_id, set_at = now()"),
                 {"c": str(case_id), "g": value, "u": str(user_id)})
    return value
