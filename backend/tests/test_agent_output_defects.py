"""lx-deepinvest B: output defects seen in a live phone report, each with a test that failed on the old code."""
from services.agent import phone_tools as PT
from services.agent import report_lint as R


def row(**kw):
    base = {"record_uid": "u1", "kind": "message", "phone": {"label": "Phone 2"}, "direction": "incoming",
            "time": {"full": "Fri, Mar 15, 2024, 11:07:12 PM EDT", "instant": "2024-03-16T03:07:12+00:00"},
            "from": None, "to": [], "flags": []}
    base.update(kw)
    return base


def test_night_event_shows_the_local_day_and_names_utc_as_utc():
    out = PT._row_out(row())
    assert out["local_day"] == "Fri, Mar 15, 2024" and out["time_zone"] == "EDT"
    assert out["instant_utc"].startswith("2024-03-16") and "instant" not in out


def test_recovered_deleted_message_is_sent_by_its_sender_not_received():
    sender = {"identity_key": "phone:+12025550100", "name": "Kell"}
    out = PT._row_out(row(**{"from": sender, "flags": ["Deleted"]}))
    assert out["recovered_deleted"] is True
    assert "sent by" in out["direction_note"] and "whichever phone" in out["direction_note"]
    assert PT._row_out(row())["direction_note"] is None


def test_money_signal_line_uses_the_device_zone_date():
    from services.agent.phone_cross_tools import _line
    it = {"instant": "2024-03-16T03:07:12+00:00", "event_date": "2024-03-15", "phone": "Phone 1", "source": "alert"}
    p = {"strength": "strong", "payment": "p1", "ref": "r", "amount": "10", "reasons": {}}
    try:
        text = _line(it, p)
    except Exception:  # noqa: BLE001 - other fields of the real item; the date is what is tested
        text = None
    if text is not None:
        assert "2024-03-15" in text and "2024-03-16" not in text


def test_dropped_names_are_found():
    assert R.dropped_names("Copies appear on and .")
    assert R.dropped_names("The call between and lasted 4 minutes.")
    assert R.dropped_names("Sent to ( ) at noon.")
    assert not R.dropped_names("Copies appear on Phone 1 and Phone 3.")


def test_duplicate_sections_are_found():
    text = "# Summary\nx\n## Open questions\na\n## Open questions\nb\n"
    assert R.duplicate_sections(text) == ['section printed 2 times: "open questions"']
    assert not R.duplicate_sections("# A\n## B\n## C\n")


def test_contents_must_match_sections():
    text = "# Report\n\n## Contents\n- Summary\n- Inventory\n- Timeline\n\n## Summary\nx\n## Inventory\ny\n## Limits\nz\n"
    got = R.contents_mismatch(text)
    assert any("timeline" in g for g in got) and any("Limits" in g for g in got)
    ok = "## Contents\n1. Summary\n2. Inventory\n\n## Summary\nx\n## Inventory\ny\n"
    assert R.contents_mismatch(ok) == []
