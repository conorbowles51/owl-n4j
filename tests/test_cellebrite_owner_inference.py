"""Unit tests for device-owner phone-number inference.

Full-file-system Cellebrite extractions (iOS FFS, modern Android) omit the
header <MSISDN>, and the IsPhoneOwner Party is empty — the owner's own number
only appears as the comm-level `Account` (e.g. WhatsApp
"13015498311@s.whatsapp.net"). CellebriteNeo4jWriter.infer_owner_msisdn()
recovers it from the most-frequent phone-resolvable Account. These tests pin
that behaviour (the real-world regression: case 34fbbb06 / Timothy + 5e374d4f
/ Abraham C1 fell back to manual entry because nothing harvested Account).

Pure in-memory — no Neo4j needed (the writer's __init__ only stores the client;
infer_owner_msisdn touches no DB).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "ingestion" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "backend"))

from cellebrite.models import ParsedModel, CellebriteReport  # noqa: E402
from cellebrite.neo4j_writer import CellebriteNeo4jWriter  # noqa: E402


def _writer() -> CellebriteNeo4jWriter:
    return CellebriteNeo4jWriter(
        neo4j_client=None,
        case_id="test-case",
        report_key="test-report",
        report=CellebriteReport(),
        default_region="US",
    )


def _comm(account: str | None, model_type: str = "InstantMessage") -> ParsedModel:
    """A communication model carrying (optionally) an owner Account field."""
    m = ParsedModel(model_type=model_type)
    if account is not None:
        m.fields["Account"] = account
    return m


def test_infers_owner_number_from_whatsapp_account_jid():
    """The Timothy case: owner number only present as a WhatsApp Account JID."""
    w = _writer()
    models = [_comm("13015498311@s.whatsapp.net") for _ in range(5)]
    w.collect_phone_owner_info(models)
    assert w.infer_owner_msisdn() == "+13015498311"


def test_most_frequent_account_wins():
    """The owner's account dominates; a chatty counterparty account doesn't."""
    w = _writer()
    models = (
        [_comm("13015498311@s.whatsapp.net") for _ in range(8)]
        + [_comm("13014089643@s.whatsapp.net") for _ in range(2)]
    )
    w.collect_phone_owner_info(models)
    assert w.infer_owner_msisdn() == "+13015498311"


def test_bare_number_account_is_normalised():
    """A plain national-format Account normalises to E.164 via the case region."""
    w = _writer()
    w.collect_phone_owner_info([_comm("(301) 549-8311") for _ in range(3)])
    assert w.infer_owner_msisdn() == "+13015498311"


def test_no_phone_resolvable_account_returns_none():
    """Email-style / group accounts don't resolve to a phone -> no inference."""
    w = _writer()
    models = [
        _comm("owner@example.com"),
        _comm("120363041234567890@g.us"),  # WhatsApp GROUP jid (not a person)
        _comm(None),
    ]
    w.collect_phone_owner_info(models)
    assert w.infer_owner_msisdn() is None


def test_empty_scan_returns_none():
    w = _writer()
    assert w.infer_owner_msisdn() is None


if __name__ == "__main__":
    import traceback

    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception:
                failures += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"\n{'ALL PASS' if not failures else str(failures) + ' FAILED'}")
    sys.exit(1 if failures else 0)
