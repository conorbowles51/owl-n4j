"""Local time beside UTC times in tool results (followups m11180017126956 item 4). Fails on the old code, which gave
the model only the UTC instant of a position or payment: the demo case's 3 May 23:10 hospital arrival read as 4 May."""
from services.agent import local_times
from services.agent.tools import AgentToolContext


def test_a_utc_time_gets_its_local_time_in_the_case_zone_and_message_rows_are_left_alone():
    ctx = AgentToolContext(case_id="c", local_zone="America/New_York")
    out = ctx.result("get_day_activity", {
        "start": "2024-05-04T03:10:00+00:00",
        "items": [{"at": "2024-05-04T03:10:00Z", "kind": "position"},
                  {"time": "Fri, May 3, 2024, 11:10:00 PM EDT", "local_day": "Fri, May 3, 2024",
                   "instant_utc": "2024-05-04T03:10:00+00:00"}],
        "day": "2024-05-03"}, summary="x")
    data = out["data"]
    assert data["start_local"] == "Fri 2024-05-03 23:10 EDT"
    assert data["items"][0]["at_local"] == "Fri 2024-05-03 23:10 EDT"
    assert "instant_utc_local" not in data["items"][1]  # the row already says its local day and zone
    assert "day_local" not in data  # a date alone is not an instant
    assert ctx.result_store[out["result_id"]]["start_local"] == "Fri 2024-05-03 23:10 EDT"


def test_a_utc_case_adds_nothing():
    ctx = AgentToolContext(case_id="c", local_zone="")
    assert "start_local" not in ctx.result("x", {"start": "2024-05-04T03:10:00+00:00"}, summary="x")["data"]
    assert local_times.annotate({"a": "2024-05-04T03:10:00Z"}, "UTC") == {"a": "2024-05-04T03:10:00Z"}


def test_winter_times_name_standard_time():
    assert local_times.local_text("2024-03-16T06:05:00+00:00", "America/New_York") == "Sat 2024-03-16 02:05 EDT"
    assert local_times.local_text("2024-01-16T06:05:00Z", "America/New_York") == "Tue 2024-01-16 01:05 EST"


def test_the_zone_is_read_only_for_a_result_holding_a_utc_time():
    # The zone read opens a session: a ledger read with dates only must not open one (journey test, 18 Nov 5 != 4).
    from services.agent import local_times as LT
    calls = []

    def zone():
        calls.append(1)
        return "America/New_York"
    assert LT.annotate({"rows": [{"date": "2024-05-03", "amount": "12.00"}]}, zone) == {
        "rows": [{"date": "2024-05-03", "amount": "12.00"}]}
    assert calls == []
    out = LT.annotate({"rows": [{"at": "2024-05-04T03:10:00Z"}]}, zone)
    assert calls == [1] and out["rows"][0]["at_local"] == "Fri 2024-05-03 23:10 EDT"
