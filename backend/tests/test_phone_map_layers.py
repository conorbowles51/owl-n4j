"""The Map's per-phone layers: every phone listed with its count, and the time-ordered positions for routes."""
from __future__ import annotations

from services.phone import map as M


def test_thin_keeps_first_and_last_and_the_cap():
    keep = M.thin_indexes(100_000, 20_000)
    assert len(keep) == 20_000 and 0 in keep and 99_999 in keep


def test_thin_under_the_cap_keeps_everything():
    assert M.thin_indexes(5, 20_000) == {0, 1, 2, 3, 4}


def test_trajectory_message_states_exact_counts(monkeypatch):
    monkeypatch.setattr(M, "TRAJECTORY_MAX", 3)
    from datetime import datetime, timezone
    rows = [type("R", (), dict(point_uid=i, extraction_id="e", lat=1.0, lon=2.0, accuracy_m=None,
                               instant=datetime(2023, 1, 1, i, tzinfo=timezone.utc)))() for i in range(10)]

    class Conn:
        def execute(self, q, p=None):
            class Res:
                def scalar(s):
                    return 0

                def fetchall(s):
                    return rows
            return Res()
    out = M.trajectory(Conn(), "c", {})
    assert out["total"] == 10 and len(out["items"]) == 3 and "10 timed positions" in out["limits"][0]["message"]
    assert [i["point_uid"] for i in out["items"]][0] == "0" and out["items"][-1]["point_uid"] == "9"
