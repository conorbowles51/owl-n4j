"""Report a problem on phone screens (07 section 9, UXD-24).

A report holds structured fields (screen, scope as kinds and counts, the action chosen from a list, whether a
refresh changes it, build id, time, last request id, viewport, component ids) and an optional "What did you
expect?" text. No screenshot. The text stays in the database: the team is told only ids, kinds, counts and the
build id, by ``jobs_line``, delivered to the coordinator by ``scripts/deliver_ui_problem_reports.py`` (the
database's ``delivered_at`` is the queue). Reports do not go through the corrections feed.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

FIELDS = json.loads((Path(__file__).with_name("ux_event_fields.json")).read_text())
SCREENS = frozenset(FIELDS["field_types"]["screen"]["enum"])
ACTION_KINDS = ("reading", "searching", "filtering", "selecting", "adding-to", "deciding", "copying", "exporting",
                "opening-a-record", "waiting", "other")
REFRESH = ("yes", "no", "not-tried")
SCOPE_KINDS = ("phones", "people", "threads", "messages", "calls", "contacts", "locations", "media", "records",
               "selected", "readings", "results")
MAX_COUNT = 100_000_000
MAX_COMPONENTS = 12
MAX_EXPECTED = 2000
_IDENT = re.compile(r"^[a-z][a-z0-9-]{0,47}$")
_BUILD = re.compile(r"^([0-9a-f]{7,64}|dev)$")  # the frontend tree hash (index.html loupe-build), or "dev"
_REQUEST = re.compile(r"^[0-9a-f-]{8,64}$")  # X-Request-ID as minted by the server: hex and dashes
JOBS_EMAILS = {e.strip().lower() for e in os.environ.get(
    'LOUPE_JOBS_EMAILS', 'jobs-verify@loupe.invalid,ui-walkthrough@loupe.invalid').split(',') if e.strip()}
# The keys a line to jobs may hold. Nothing typed and nothing read from the case is among them.
JOBS_KEYS = ("report_id", "case_id", "at", "screen", "action_kind", "refresh_changes", "build_id", "scope",
             "components", "viewport", "has_text", "test")


class Refused(ValueError):
    pass


def clean(body: dict) -> dict:
    """The fields as stored, or Refused naming the first field that is not allowed."""
    screen = body.get("screen")
    if screen not in SCREENS:
        raise Refused("screen is not a phone screen")
    if body.get("action_kind") not in ACTION_KINDS:
        raise Refused("action_kind is not one of the listed actions")
    if body.get("refresh_changes") not in REFRESH:
        raise Refused("refresh_changes must be yes, no or not-tried")
    build = body.get("build_id")
    if not isinstance(build, str) or not _BUILD.match(build):
        raise Refused("build_id is not a build id")
    request_id = body.get("last_request_id")
    if request_id is not None and (not isinstance(request_id, str) or not _REQUEST.match(request_id)):
        raise Refused("last_request_id is not a request id")
    scope = body.get("scope") or {}
    if not isinstance(scope, dict):
        raise Refused("scope must be kinds and counts")
    for kind, count in scope.items():
        if kind not in SCOPE_KINDS:
            raise Refused(f"scope kind {kind} is not allowed")
        if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= MAX_COUNT:
            raise Refused(f"scope {kind} must be a count")
    components = body.get("components") or []
    if not isinstance(components, list) or len(components) > MAX_COMPONENTS:
        raise Refused(f"components must be a list of at most {MAX_COMPONENTS} ids")
    for c in components:
        if not isinstance(c, str) or not _IDENT.match(c):
            raise Refused("a component id is not an id")
    viewport = []
    for key in ("viewport_w", "viewport_h"):
        v = body.get(key)
        if v is not None and (isinstance(v, bool) or not isinstance(v, int) or not 0 < v <= 20000):
            raise Refused(f"{key} must be a size in pixels")
        viewport.append(v)
    expected = body.get("expected")
    if expected is not None:
        if not isinstance(expected, str):
            raise Refused("expected must be text")
        expected = expected.strip()[:MAX_EXPECTED + 1]
        if len(expected) > MAX_EXPECTED:
            raise Refused(f"What did you expect? takes up to {MAX_EXPECTED} characters")
        expected = expected or None
    return dict(screen=screen, action_kind=body["action_kind"], refresh_changes=body["refresh_changes"],
                build_id=build, last_request_id=request_id, scope=dict(scope), components=list(components),
                viewport_w=viewport[0], viewport_h=viewport[1], expected=expected)


def create(db, *, case_id, user, body: dict):
    from postgres.models.ui_problem_report import UiProblemReport
    from services.manual_changes import VERIFICATION_CASE
    fields = clean(body)
    email = (getattr(user, "email", "") or "").lower()
    report = UiProblemReport(case_id=case_id, user_id=getattr(user, "id", None),
                             is_test=email in JOBS_EMAILS or str(case_id) == VERIFICATION_CASE, **fields)
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def reference(report) -> str:
    return str(report.id)[:8]


def view(report) -> dict:
    """What a case member sees, including their own words."""
    return dict(id=str(report.id), reference=reference(report), case_id=str(report.case_id),
                user_id=str(report.user_id) if report.user_id else None,
                created_at=report.created_at.isoformat() if report.created_at else None, screen=report.screen,
                action_kind=report.action_kind, refresh_changes=report.refresh_changes, build_id=report.build_id,
                last_request_id=report.last_request_id, viewport_w=report.viewport_w, viewport_h=report.viewport_h,
                scope=report.scope, components=report.components, expected=report.expected,
                delivered=report.delivered_at is not None)


def jobs_line(report) -> dict:
    """What the team is told: ids, kinds, counts and the build id. Never the text, never a case value."""
    line = dict(report_id=str(report.id), case_id=str(report.case_id),
                at=report.created_at.isoformat() if report.created_at else None, screen=report.screen,
                action_kind=report.action_kind, refresh_changes=report.refresh_changes, build_id=report.build_id,
                scope={k: int(v) for k, v in (report.scope or {}).items() if k in SCOPE_KINDS},
                components=[c for c in (report.components or []) if _IDENT.match(c)],
                viewport=[report.viewport_w, report.viewport_h], has_text=bool(report.expected), test=bool(report.is_test))
    assert tuple(line) == JOBS_KEYS
    return line


def jobs_message(report) -> str:
    """One line for the coordinator's inbox, built only from jobs_line."""
    line = jobs_line(report)
    scope = ", ".join(f"{k} {v}" for k, v in line["scope"].items()) or "no scope"
    return (f"ui problem report {line['report_id'][:8]} (case {line['case_id'][:8]}{', test' if line['test'] else ''}): "
            f"screen {line['screen']}, while {line['action_kind']}, refresh changes it: {line['refresh_changes']}, "
            f"build {line['build_id'][:12]}, {scope}, components {'/'.join(line['components']) or 'none'}, "
            f"viewport {line['viewport'][0]}x{line['viewport'][1]}, text {'given (in the database only)' if line['has_text'] else 'none'}. "
            f"JSON: {json.dumps(line, separators=(',', ':'))}")


def undelivered(db, include_test=False):
    from sqlalchemy import select
    from postgres.models.ui_problem_report import UiProblemReport as R
    query = select(R).where(R.delivered_at.is_(None))
    if not include_test:
        query = query.where(R.is_test.is_(False))
    return list(db.scalars(query.order_by(R.created_at)))
