"""Saved claims (lx-corrostatement C): Loupe's reading of a sentence, and the chips a named person confirmed.

``parse`` saves the reading as a draft ("Read by Loupe · not confirmed") with the sentence kept as written.
``confirm`` stores the chips the person confirmed or edited under their name and lists which fields they changed from
Loupe's reading; the reading itself is never overwritten. Only a confirmed claim is weighed (``require_confirmed``).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from services.relations import claims as parser


class ClaimError(ValueError):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def _name(user) -> str:
    return getattr(user, "full_name", None) or getattr(user, "name", None) or getattr(user, "email", None) or "a person"


def view(c) -> dict:
    return {"id": str(c.id), "status": c.status, "sentence": c.sentence, "statement_date": c.statement_date,
            "source": c.source or {}, "chips": (c.read or {}).get("chips", {}), "missing": (c.read or {}).get("missing", []),
            "read_by": parser.READ_BY, "confirmed": c.confirmed or {}, "edited": list(c.edited or []),
            "confirmed_by": c.confirmed_by_name, "confirmed_at": c.confirmed_at.isoformat() if c.confirmed_at else None}


def parse(db, store, case_id, *, text: str, statement_date: str | None, speaker: str | None, source: dict | None,
          user, model: bool = False) -> dict:
    from postgres.models.corroborate import CorroborateClaim
    sentence = " ".join(str(text or "").split())
    if not sentence:
        raise ClaimError("Write the claim as a sentence.")
    if len(sentence) > 600:
        raise ClaimError("A claim is one sentence or two, up to 600 characters. Split it and check each part.")
    stmt = None
    if statement_date:
        try:
            stmt = date.fromisoformat(statement_date)
        except ValueError:
            raise ClaimError("The statement date is year-month-day, for example 2024-06-12.")
    read = parser.read_claim(store, sentence, statement_date=stmt, speaker=speaker, model=model)
    row = CorroborateClaim(id=uuid.uuid4(), case_id=uuid.UUID(str(case_id)), sentence=sentence,
                           statement_date=statement_date, source=source or {}, read=read, confirmed={}, edited=[],
                           status="draft", created_by=getattr(user, "id", None), created_by_name=_name(user))
    db.add(row)
    db.commit()
    return view(row)


def get(db, case_id, claim_id):
    from postgres.models.corroborate import CorroborateClaim
    try:
        row = db.get(CorroborateClaim, uuid.UUID(str(claim_id)))
    except ValueError:
        row = None
    if row is None or str(row.case_id) != str(case_id):
        raise LookupError("That claim is not in this case.")
    return row


def _clean(chips: dict) -> dict:
    """The chips as a person confirms them, in the form the weighing reads."""
    who = [{"key": str(w["key"]), "label": str(w.get("label") or w["key"])[:200]} for w in (chips.get("who") or [])
           if isinstance(w, dict) and w.get("key")][:10]
    when = chips.get("when")
    if when is not None:
        try:
            lo, hi = (datetime.fromisoformat(str(when[k]).replace("Z", "+00:00")) for k in ("start", "end"))
        except (KeyError, ValueError, TypeError):
            raise ClaimError("The time window needs a start and an end, each with a date and time and its offset.")
        if lo.tzinfo is None or hi.tzinfo is None or hi <= lo:
            raise ClaimError("The time window must end after it starts, and carry its offset.")
        when = {"start": lo.astimezone(timezone.utc).isoformat(), "end": hi.astimezone(timezone.utc).isoformat(),
                "zone": str(when.get("zone") or "UTC"), "label": str(when.get("label") or "")[:200]}
    where = chips.get("where")
    if where is not None:
        try:
            where = {"name": str(where.get("name") or "")[:200], "lat": float(where["lat"]), "lon": float(where["lon"]),
                     "radius_m": float(where.get("radius_m") or 150.0), "how": str(where.get("how") or "")[:300]}
        except (KeyError, ValueError, TypeError, AttributeError):
            raise ClaimError("A place needs a latitude, a longitude and a radius in metres. Leave it out if it is not known.")
    what = chips.get("what")
    if what is not None:
        if what.get("action") not in ("presence", "contact", "with"):
            raise ClaimError("What was said is one of: was at a place, had contact with someone, was with someone.")
        what = {"action": what["action"], "negated": bool(what.get("negated")),
                "with": [str(k) for k in (what.get("with") or [])][:10], "mode": what.get("mode")}
    text_ = str(chips.get("where_text") or "")[:300] or None
    return {"who": who, "when": when, "where": where, "what": what, **({"where_text": text_} if text_ else {})}


def confirm(db, case_id, claim_id, chips: dict, user) -> dict:
    row = get(db, case_id, claim_id)
    clean = _clean(chips or {})
    if not clean["who"]:
        raise ClaimError("Say who the claim is about before confirming it.")
    read = (row.read or {}).get("chips", {})
    edited = []
    for f in ("who", "when", "where", "what"):
        was = read.get(f, {})
        now = clean[f]
        if f == "who":
            same = {w["key"] for w in (was.get("value") or [])} == {w["key"] for w in now}
        elif now is None or was.get("value") is None:
            same = now is None and was.get("value") is None
        else:
            keys = {"when": ("start", "end"), "where": ("lat", "lon", "radius_m"), "what": ("action", "negated")}[f]
            same = all(str(was["value"].get(k)) == str(now.get(k)) for k in keys) if isinstance(was["value"], dict) else False
        if not same:
            edited.append(f)
    row.confirmed, row.edited, row.status = clean, edited, "confirmed"
    row.confirmed_by, row.confirmed_by_name, row.confirmed_at = getattr(user, "id", None), _name(user), datetime.now(timezone.utc)
    db.commit()
    return view(row)


def require_confirmed(db, case_id, claim_id):
    """The confirmed claim, or ``ClaimError`` (409) in plain words."""
    try:
        row = get(db, case_id, claim_id)
    except LookupError as exc:
        raise ClaimError(str(exc), status=404)
    if row.status != "confirmed":
        raise ClaimError("This claim has not been confirmed. Check what Loupe read from the sentence, then confirm it "
                         "before it is weighed.", status=409)
    return row
