"""AI spending limits: per case and per calendar month, read from one saved setting.

The numbers are a person's. Nothing here has a default: with no limit saved there is no cap, no query is made, and the
admin page says so. The setting is one row of ai_model_policies (key 'ai_budget'), as the vector-search threshold is,
so every process and the evidence engine read the same value at the moment a run starts:

    {"case_limit_usd": number | null,       each case, its whole recorded spend
     "month_limit_usd": number | null,      all cases and uncased work, this calendar month (UTC)
     "case_limits": {"<case id>": number},  a tighter limit for one case, set by the person managing it
     "alerts": [...]}                       each crossing of 80 % and of the limit, once

Spend is what cost_records holds, so it survives a restart and matches the admin page and the case's cost report.

At a limit a new model run is refused (``BudgetRefused``, HTTP 402 with the reason and the sum). Work already sent to a
model finishes; the evidence engine holds a running batch after its current file (evidence-engine ai_budget), resumable
and with the reason on the job. Nothing is dropped.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from postgres.models.cost_record import CostRecord
from postgres.models.runtime_state import AIModelPolicy

logger = logging.getLogger(__name__)

SETTINGS_KEY = "ai_budget"
ALERT_PERCENT = 80
MAX_KEPT_ALERTS = 200


class BudgetRefused(ValueError):
    """A new model run is refused: a limit has been reached. A ValueError, so a route that answers 400 with the message
    still states the reason and the sum; main.py answers 402 for the rest. ``payload`` carries the figures."""

    def __init__(self, *, scope: str, spent_usd: float, limit_usd: float, what: str, case_id: Any = None):
        self.scope = scope
        self.spent_usd = round(float(spent_usd), 2)
        self.limit_usd = round(float(limit_usd), 2)
        self.what = what
        self.case_id = str(case_id) if case_id else None
        super().__init__(refusal_sentence(scope, spent_usd, limit_usd, what))

    @property
    def reason(self) -> str:
        return str(self)

    @property
    def payload(self) -> dict[str, Any]:
        return {"code": "ai_budget_reached", "message": self.reason, "scope": self.scope,
                "spent_usd": self.spent_usd, "limit_usd": self.limit_usd, "case_id": self.case_id}


def refusal_sentence(scope: str, spent_usd: float, limit_usd: float, what: str) -> str:
    where = "this case's AI spending limit" if scope == "case" else "this month's AI spending limit"
    return (f"Not started: {what} would pass {where}. ${float(spent_usd):,.2f} spent of the ${float(limit_usd):,.2f} "
            "limit. An administrator can raise the limit on the AI costs page.")


def _number(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def get_settings(db: Session) -> dict[str, Any]:
    record = db.get(AIModelPolicy, SETTINGS_KEY)
    stored = (record.configuration or {}) if record is not None else {}
    limits = {str(k).lower(): _number(v) for k, v in (stored.get("case_limits") or {}).items()}
    return {
        "case_limit_usd": _number(stored.get("case_limit_usd")),
        "month_limit_usd": _number(stored.get("month_limit_usd")),
        "case_limits": {k: v for k, v in limits.items() if v is not None},
        "alerts": list(stored.get("alerts") or []),
        "updated_by": record.updated_by if record is not None else None,
        "revision": record.revision if record is not None else 0,
    }


def _write(db: Session, change: dict[str, Any], *, updated_by: str | None) -> None:
    record = db.scalar(select(AIModelPolicy).where(AIModelPolicy.key == SETTINGS_KEY).with_for_update())
    if record is None:
        db.add(AIModelPolicy(key=SETTINGS_KEY, revision=1, configuration=change, updated_by=updated_by))
    else:
        record.configuration = {**(record.configuration or {}), **change}
        record.revision = (record.revision or 0) + 1
        record.updated_by = updated_by or record.updated_by


def set_limits(db: Session, *, case_limit_usd: float | None, month_limit_usd: float | None,
               updated_by: str | None) -> None:
    """Save the two limits for the deployment. None clears a limit: no cap."""
    for value in (case_limit_usd, month_limit_usd):
        if value is not None and (isinstance(value, bool) or float(value) < 0):
            raise ValueError("A limit is a number of dollars, zero or more.")
    _write(db, {"case_limit_usd": None if case_limit_usd is None else float(case_limit_usd),
                "month_limit_usd": None if month_limit_usd is None else float(month_limit_usd)}, updated_by=updated_by)
    db.commit()


def set_case_limit(db: Session, case_id: Any, limit_usd: float | None, *, updated_by: str | None) -> None:
    """A tighter limit for one case. It can only lower what applies: the deployment's limit still holds."""
    if limit_usd is not None and (isinstance(limit_usd, bool) or float(limit_usd) < 0):
        raise ValueError("A limit is a number of dollars, zero or more.")
    limits = dict(get_settings(db)["case_limits"])
    if limit_usd is None:
        limits.pop(str(case_id).lower(), None)
    else:
        limits[str(case_id).lower()] = float(limit_usd)
    _write(db, {"case_limits": limits}, updated_by=updated_by)
    db.commit()


def month_key(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m")


def _month_start(now: datetime | None = None) -> datetime:
    return (now or datetime.now(timezone.utc)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def case_spend(db: Session, case_id: Any) -> float:
    return float(db.scalar(select(func.coalesce(func.sum(CostRecord.cost_usd), 0))
                           .where(CostRecord.case_id == uuid.UUID(str(case_id)))) or 0)


def month_spend(db: Session, now: datetime | None = None) -> float:
    return float(db.scalar(select(func.coalesce(func.sum(CostRecord.cost_usd), 0))
                           .where(CostRecord.created_at >= _month_start(now))) or 0)


def case_limit(settings: dict[str, Any], case_id: Any) -> float | None:
    """The limit in force for one case: the tighter of the deployment's and the case's own."""
    limits = [settings.get("case_limit_usd"), settings.get("case_limits", {}).get(str(case_id).lower())]
    limits = [limit for limit in limits if limit is not None]
    return min(limits) if limits else None


def limit_in_force(db: Session, case_id: Any = None, *, settings: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """The first limit reached for this case, or None. Reads spend only when a limit is set."""
    settings = settings if settings is not None else get_settings(db)
    limit = case_limit(settings, case_id) if case_id else None
    if limit is not None:
        spent = case_spend(db, case_id)
        if spent >= limit:
            return {"scope": "case", "spent_usd": spent, "limit_usd": limit, "case_id": case_id}
    limit = settings.get("month_limit_usd")
    if limit is not None:
        spent = month_spend(db)
        if spent >= limit:
            return {"scope": "month", "spent_usd": spent, "limit_usd": limit, "case_id": case_id}
    return None


def check(db: Session, case_id: Any, what: str) -> None:
    """Refuse a new model run at a limit. ``what``: the run in plain words, e.g. "this agent question".

    A failure to read the setting or the spend never stops work: a limit that cannot be read is logged and is no limit,
    since the setting exists to warn about bills, not to take the application down with a database hiccup."""
    try:
        reached = limit_in_force(db, case_id)
    except Exception:  # noqa: BLE001
        logger.exception("AI budget could not be read; the run goes ahead")
        return
    if reached:
        raise BudgetRefused(scope=reached["scope"], spent_usd=reached["spent_usd"], limit_usd=reached["limit_usd"],
                            what=what, case_id=case_id)


def check_new_session(case_id: Any, what: str) -> None:
    """``check`` for a caller without a session (the model-calling services that run outside a request)."""
    from postgres.session import get_background_session
    with get_background_session() as session:
        check(session, case_id, what)


# ------------------------------------------------------------------------------------------------------------- alerts

def _crossings(db: Session, settings: dict[str, Any]) -> list[dict[str, Any]]:
    """Every limit now at 80 % or more, once for its level: the case limits, then the month."""
    found: list[dict[str, Any]] = []

    def level(spent: float, limit: float) -> int | None:
        if limit <= 0 or spent >= limit:
            return 100
        return ALERT_PERCENT if spent >= limit * ALERT_PERCENT / 100 else None

    default = settings.get("case_limit_usd")
    overrides = settings.get("case_limits") or {}
    if default is not None or overrides:
        query = select(CostRecord.case_id, func.sum(CostRecord.cost_usd)).where(CostRecord.case_id.is_not(None))
        for case_id, spent in db.execute(query.group_by(CostRecord.case_id)).all():
            limit = case_limit(settings, case_id)
            percent = level(float(spent or 0), limit) if limit is not None else None
            if percent:
                found.append({"key": f"case:{case_id}:{percent}:{limit}", "scope": "case", "case_id": str(case_id),
                              "level": percent, "spent_usd": round(float(spent), 2), "limit_usd": limit})
    month_limit = settings.get("month_limit_usd")
    if month_limit is not None:
        spent = month_spend(db)
        percent = level(spent, month_limit)
        if percent:
            month = month_key()
            found.append({"key": f"month:{month}:{percent}:{month_limit}", "scope": "month", "month": month,
                          "case_id": None, "level": percent, "spent_usd": round(spent, 2), "limit_usd": month_limit})
    return found


def record_alerts(db: Session) -> list[dict[str, Any]]:
    """Note every new crossing, once. Called by the fleet's delivery and by the admin page, so a crossing made by the
    evidence engine is noted without the engine writing the setting."""
    settings = get_settings(db)
    if settings["case_limit_usd"] is None and settings["month_limit_usd"] is None and not settings["case_limits"]:
        return []
    seen = {alert.get("key") for alert in settings["alerts"]}
    new = [crossing for crossing in _crossings(db, settings) if crossing["key"] not in seen]
    if not new:
        return []
    now = datetime.now(timezone.utc).isoformat()
    for crossing in new:
        crossing.update(at=now, delivered_at=None)
    _write(db, {"alerts": (settings["alerts"] + new)[-MAX_KEPT_ALERTS:]}, updated_by=None)
    db.commit()
    return new


def alert_sentence(alert: dict[str, Any], case_title: str | None = None) -> str:
    subject = (f"Case {case_title or str(alert.get('case_id'))[:8]}" if alert.get("scope") == "case"
               else f"AI spending for {alert.get('month')}")
    reached = "has reached its limit" if alert.get("level") == 100 else f"has passed {alert.get('level')} % of its limit"
    tail = ": new AI runs are refused until the limit is raised" if alert.get("level") == 100 else ""
    return f"{subject} {reached}: ${alert.get('spent_usd'):,.2f} of ${alert.get('limit_usd'):,.2f}{tail}."


def undelivered_alerts(db: Session) -> list[dict[str, Any]]:
    return [alert for alert in get_settings(db)["alerts"] if not alert.get("delivered_at")]


def mark_delivered(db: Session, keys: Iterable[str]) -> None:
    keys = set(keys)
    now = datetime.now(timezone.utc).isoformat()
    alerts = [dict(alert, delivered_at=now) if alert.get("key") in keys else alert
              for alert in get_settings(db)["alerts"]]
    _write(db, {"alerts": alerts}, updated_by=None)
    db.commit()


# --------------------------------------------------------------------------------------------------------- admin view

def overview(db: Session) -> dict[str, Any]:
    """What the admin page shows. With nothing set it says there is no cap and queries no spend beyond the month's."""
    record_alerts(db)
    settings = get_settings(db)
    from postgres.models.case import Case
    month_spent = month_spend(db)
    month_limit = settings["month_limit_usd"]
    capped = settings["case_limit_usd"] is not None or bool(settings["case_limits"])
    rows = db.execute(select(CostRecord.case_id, func.sum(CostRecord.cost_usd), func.count())
                      .where(CostRecord.case_id.is_not(None)).group_by(CostRecord.case_id)).all()
    titles = dict(db.execute(select(Case.id, Case.title).where(Case.id.in_([row[0] for row in rows]))).all()) if rows else {}
    cases = []
    for case_id, spent, calls in rows:
        limit = case_limit(settings, case_id)
        cases.append({"case_id": str(case_id), "title": titles.get(case_id) or str(case_id)[:8], "calls": calls,
                      "spent_usd": round(float(spent or 0), 2), "limit_usd": limit,
                      "percent": round(float(spent or 0) / limit * 100, 1) if limit else None})
    cases.sort(key=lambda row: row["spent_usd"], reverse=True)
    alerts = [dict(alert, message=alert_sentence(alert, titles.get(_uuid(alert.get("case_id")))))
              for alert in settings["alerts"]]
    return {
        "capped": capped or month_limit is not None,
        "case_limit_usd": settings["case_limit_usd"],
        "month_limit_usd": month_limit,
        "case_limits": settings["case_limits"],
        "month": month_key(),
        "month_spent_usd": round(month_spent, 2),
        "month_percent": round(month_spent / month_limit * 100, 1) if month_limit else None,
        "cases": cases,
        "alerts": alerts[-20:][::-1],
        "updated_by": settings["updated_by"],
    }


def _uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None
