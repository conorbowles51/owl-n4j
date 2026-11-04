"""cb-gated-aware F: building approach 4 steps 1 to 4 and approach 5 steps 2 and 4 changes nothing that was already
shown. Group roles (awareness 4.1-groups) and shared markers, complementary use and signs of more than one user
(device_users 5.2-use) on one fixture equal the output the old code gave (``EXPECTED``, recorded from 9395ef45 with
extraction ids replaced by phone labels). Invented data only."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import timedelta

import pytest

from services.phone_analysis import awareness as A
from services.phone_analysis import device_users as U
from tests.phone_analysis_fixture import record
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone
from tests.test_phone_analysis_awareness import _group
from tests.test_phone_analysis_device_users import _iccid, _use

OLD_KINDS = {"group_roles", "shared_markers", "complementary_use", "more_than_one_user"}
EXPECTED = ("1bd3b9b5b8459ab70b5c93c5f768aeb315ad8f5bf48ee6176b8ff4e734b4ac18"
            "5b697814f13267478198b0aa928ee9b28a15ddff62397cf4b3d472c33edd7d09")
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


@pytest.fixture
def engine():
    with fresh_engine() as e:
        yield e


def _fixture(c):
    case = make_case(c)
    t = at(2023, 5, 1, 10)
    x, _ = phone(c, case, label="C1", events=[
        {"instant": t, "direction": "incoming", "thread": "one",
         "parties": [("phone:+12025550143", "sender", False, "Synthetic Sender", "+12025550143"),
                     ("phone:+12025550100", "recipient", True, None, "+12025550100", None, t + timedelta(minutes=5))]},
        {"instant": t + timedelta(minutes=20), "direction": "outgoing", "thread": "one",
         "parties": [("phone:+12025550100", "sender", True, None, "+12025550100")]}])
    y, _ = phone(c, case, label="C2", owner="phone:+12025550111", events=[])
    _group(c, case, x, 5000, 4, admin_index=2,
           activities=[("ParticipantAdded", t, "Synthetic Person 3"), ("ParticipantLeft", None, "Synthetic X")])
    _iccid(c, x, "89441000000000000001")
    _iccid(c, y, "89441000000000000001")
    _use(c, case, x, 9, 12, 14, at(2023, 1, 2, 0))
    _use(c, case, y, 12, 15, 14, at(2023, 1, 2, 0))
    record(c, case, y, 500, "User", [("UserType", "UserType", "Owner")])
    record(c, case, y, 501, "User", [("UserType", "UserType", "Guest")])
    return case, {x: "C1", y: "C2"}


def normalised(results, labels):
    out = []
    for r in results:
        if r["kind"] not in OLD_KINDS:
            continue
        s = json.dumps(r, sort_keys=True, default=str)
        for e, lab in labels.items():
            s = s.replace(str(e), lab)
        # record ids derive from the random extraction id: the shape of the records is compared, not their ids
        out.append(UUID_RE.sub("<id>", s))
    return sorted(out)


def digest(results, labels):
    return hashlib.sha256("\n".join(normalised(results, labels)).encode()).hexdigest()


@needs_template
def test_group_roles_and_complementary_use_are_unchanged(engine):
    with engine.begin() as c:
        case, labels = _fixture(c)
    with engine.connect() as c:
        aw, _ = A.analyse(c, case, {k: v["default"] for k, v in getattr(A, "PARAMETERS", {}).items()})
        du, _ = U.analyse(c, case, {k: v["default"] for k, v in U.PARAMETERS.items()})
    got = normalised(aw, labels) + normalised(du, labels)
    kinds = sorted(json.loads(s)["kind"] for s in got)
    assert kinds == ["complementary_use", "group_roles", "more_than_one_user", "shared_markers"]
    assert digest(aw, labels) + digest(du, labels) == EXPECTED, "\n".join(got)
