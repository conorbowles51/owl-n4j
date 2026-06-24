"""
Unit tests for the Comms PDF export HTML generators.

Regression coverage for DKT-21 self-review findings:
  - Timeline From/To columns were blank because the generator read flat
    `from_name`/`to_name`, but neo4j_service emits nested `sender` (dict)
    and `recipients` (list of dicts).
  - Conversation export 500'd because `html.escape` was called on the
    `sender` dict directly.
  - Call duration was dropped because the generator read `duration_seconds`
    but the data carries `duration`.

These tests feed the generators item shapes that mirror exactly what
`neo4j_service.get_cellebrite_comms_between` (timeline) and
`get_cellebrite_thread_detail` (conversation) return, so the field mapping
stays in sync. They exercise the pure HTML builders only — no Neo4j and no
WeasyPrint render needed.

Run:
    PYTHONPATH=backend python -m pytest tests/test_comms_export_service.py -xvs
Or directly:
    PYTHONPATH=backend python tests/test_comms_export_service.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from services.comms_export_service import (  # noqa: E402
    generate_timeline_pdf,
    generate_conversation_pdf,
)


# --- Fixtures mirroring neo4j_service output shapes ------------------------

def _timeline_items():
    """Shape mirrors get_cellebrite_comms_between(...)['items']."""
    return [
        {
            "id": "m1",
            "type": "message",
            "timestamp": "2026-01-02T09:30:00",
            "source_app": "WhatsApp",
            "body": "Hey, are we still on for tomorrow?",
            "sender": {"key": "phone-111", "name": "Alex Romero", "is_owner": True},
            "recipients": [{"key": "phone-222", "name": "Jordan Pike"}],
            "attachments": [],
        },
        {
            "id": "c1",
            "type": "call",
            "timestamp": "2026-01-02T11:05:00",
            "source_app": "Phone",
            "direction": "outgoing",
            "duration": 185,  # 3m 05s — must NOT be dropped
            "sender": {"key": "phone-111", "name": "Alex Romero", "is_owner": True},
            "recipients": [{"key": "phone-222", "name": "Jordan Pike"}],
            "attachments": [],
        },
        {
            "id": "e1",
            "type": "email",
            "timestamp": "2026-01-03T14:00:00",
            "source_app": "Gmail",
            "subject": "Contract draft",
            "body": "See attached.",
            "sender": {"key": "email-aaa", "name": "Alex Romero", "is_owner": False},
            "recipients": [{"key": "email-bbb", "name": "Jordan Pike"}],
            "attachments": [],
        },
    ]


def _conversation_items():
    """Shape mirrors get_cellebrite_thread_detail(...)['items'] for a chat."""
    return [
        {
            "id": "m1",
            "type": "message",
            "timestamp": "2026-01-02T09:30:00",
            "body": "Hey, are we still on for tomorrow?",
            # sender is a DICT — escaping it directly used to 500
            "sender": {"key": "phone-111", "name": "Alex Romero", "is_owner": True},
            "attachments": [],
        },
        {
            "id": "m2",
            "type": "message",
            "timestamp": "2026-01-02T09:31:00",
            "body": "Yep, 10am works.",
            "sender": {"key": "phone-222", "name": "Jordan Pike", "is_owner": False},
            "attachments": [],
        },
        {
            "id": "c1",
            "type": "call",
            "timestamp": "2026-01-02T11:05:00",
            "direction": "outgoing",
            "duration": 185,
            "sender": {"key": "phone-111", "name": "Alex Romero", "is_owner": True},
            "recipient": {"key": "phone-222", "name": "Jordan Pike", "is_owner": False},
            "attachments": [],
        },
    ]


# --- Timeline mode ---------------------------------------------------------

def test_timeline_renders_from_and_to_names():
    html = generate_timeline_pdf(
        _timeline_items(),
        filters_summary={"participants": "Alex Romero (+15551112222)"},
        case_label="abcd1234",
    )
    # From/To columns must be populated from nested sender/recipients,
    # not blank.
    assert "Alex Romero" in html
    assert "Jordan Pike" in html
    assert "from_name" not in html  # no raw key names leaking


def test_timeline_keeps_call_duration():
    html = generate_timeline_pdf(_timeline_items(), filters_summary={}, case_label="x")
    # 185s -> "3m 05s"; must not be dropped.
    assert "3m 05s" in html


def test_timeline_renders_message_and_email_content():
    html = generate_timeline_pdf(_timeline_items(), filters_summary={}, case_label="x")
    assert "still on for tomorrow" in html
    assert "Contract draft" in html  # email subject


# --- Conversation mode -----------------------------------------------------

def test_conversation_does_not_crash_on_dict_sender():
    # The core 500 regression: a dict sender must be handled, not escaped raw.
    html = generate_conversation_pdf(
        {"participants": ["Alex Romero (+15551112222)"], "thread_type": "chat"},
        _conversation_items(),
        case_label="abcd1234",
    )
    assert "Alex Romero" in html
    assert "Jordan Pike" in html
    # Sender dict repr must never leak into the output.
    assert "'is_owner'" not in html
    assert "{'key'" not in html


def test_conversation_renders_call_and_message():
    html = generate_conversation_pdf(
        {"participants": [], "thread_type": "chat"},
        _conversation_items(),
        case_label="x",
    )
    assert "Yep, 10am works." in html
    assert "3m 05s" in html  # call duration surfaced in conversation too


def test_conversation_marks_owner_messages_outbound():
    html = generate_conversation_pdf(
        {"participants": [], "thread_type": "chat"},
        _conversation_items(),
        case_label="x",
    )
    # Owner-sent bubbles get the "out" class; counterparty bubbles don't.
    assert "bubble out" in html


if __name__ == "__main__":
    # Allow running without pytest installed.
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL  {fn.__name__}: {exc!r}")
    print(f"\n{len(fns) - failures}/{len(fns)} passed")
    sys.exit(1 if failures else 0)
