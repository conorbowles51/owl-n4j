"""07 J-16 / 05 section 5.3: the keys that find one message on two phones. No database: rows are invented."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as R

from services.phone.compare import family, match

T0 = datetime(2023, 3, 14, 19, 0, tzinfo=timezone.utc)
A, B = "a", "b"


def ev(side, secs, body="a synthetic message long enough", kind="message", app="WhatsApp", d=None, direction="incoming"):
    return R(extraction_id=side, kind=kind, app=app, at=T0 + timedelta(seconds=secs), body=body, d=d,
             direction=direction)


def test_sent_and_received_times_up_to_two_minutes_apart_are_one_message():
    evs = [ev(A, 0), ev(B, 95), ev(A, 1000), ev(B, 1000 + 121)]
    assert match(evs, A, B) == {0, 1}


def test_each_message_pairs_once_closest_first_and_two_real_messages_are_not_collapsed():
    evs = [ev(A, 0), ev(A, 0), ev(B, 10)]
    assert len(match(evs, A, B)) == 2  # one of the two on A pairs; the other stays "only on A"


def test_decorative_letters_case_and_spacing_do_not_split_a_message():
    evs = [ev(A, 0, body="Meet At  The Dock tonight"), ev(B, 3, body="meet at the dock TONIGHT")]
    assert match(evs, A, B) == {0, 1}


def test_a_short_or_common_text_pairs_only_when_one_side_sent_it():
    assert match([ev(A, 0, body="ok"), ev(B, 2, body="ok")], A, B) == set()
    assert match([ev(A, 0, body="ok"), ev(B, 2, body="ok", direction="outgoing")], A, B) == {0, 1}


def test_app_family_and_call_duration():
    assert family("message", None) == family("message", "Native Messages") == "sms"
    assert family("call", "Phone") == family("call", None) == "phone"
    assert match([ev(A, 0, app="Telegram"), ev(B, 0)], A, B) == set()
    calls = [ev(A, 0, kind="call", app="Phone", d=61, body=None), ev(B, 4, kind="call", app=None, d=60, body=None),
             ev(A, 500, kind="call", app="Phone", d=61, body=None), ev(B, 500, kind="call", app=None, d=90, body=None)]
    assert match(calls, A, B) == {0, 1}
