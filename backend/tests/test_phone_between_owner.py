"""Between A and the owner of each phone (07 J-3): a phone with no known owner key is not dropped silently. The
report's own IsPhoneOwner mark still names the owner's part, and the phone is named in the list's limits.

Invented data only: 555 numbers and made-up text. Needs the PostgreSQL phone template.
"""
from __future__ import annotations

from services.phone import streams as S
from services.phone.filters import StreamFilter
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

pytestmark = needs_template
OWNER, ANA, BEN = "phone:+12025550100", "phone:+12025550143", "phone:+12025550188"


def _m(instant, sender, recips, owner_flag=True):
    parties = [(sender, "sender", owner_flag and sender == OWNER, None, None)] + [
        (r, "recipient", owner_flag and r == OWNER, None, None) for r in recips]
    return dict(kind="message", instant=instant, body="synthetic", thread="t", parties=parties,
                direction="outgoing" if sender == OWNER else "incoming")


def test_between_a_and_the_owner_keeps_a_phone_with_no_owner_key_and_names_it():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            known, _ = phone(c, case, label="C1", events=[_m(at(2023, 3, 1, 9), ANA, [OWNER])])
            unknown, _ = phone(c, case, label="C2", owner=None, events=[
                _m(at(2023, 3, 2, 9), ANA, [OWNER]), _m(at(2023, 3, 2, 10), OWNER, [ANA]),
                _m(at(2023, 3, 2, 11), ANA, [BEN])])
        with engine.connect() as c:
            f = StreamFilter.model_validate({"case_id": str(case), "participants": [ANA, S.PHONE_OWNER],
                                             "participant_mode": "between"})
            assert S.shown_count(c, f) == 3  # one on C1, two on C2 (the message to someone else is not between)
            lim = S.limits_for(c, f)
            assert [l["kind"] for l in lim] == ["owner_unknown"] and lim[0]["phone"] == str(unknown)
            assert lim[0]["message"].startswith("No owner is known for ")
            plain = StreamFilter.model_validate({"case_id": str(case), "participants": [ANA]})
            assert S.limits_for(c, plain) == []
