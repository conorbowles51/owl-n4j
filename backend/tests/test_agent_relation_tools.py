"""get_relation_results gives the model one compact overview, so it does not spend its budget re-reading pages (lx-overlaps E)."""
import contextlib
import json
from types import SimpleNamespace
from unittest import mock

from services.agent import relation_tools

ITEMS = [{"ref": "phone_record:p", "type": "phone_record", "id": "p", "label": "Position", "at": "2024-04-13T03:30:00+00:00"},
         {"ref": "financial_transaction:t", "type": "financial_transaction", "id": "t", "label": "Payment", "at": None}]
RESULT = {"says": "These are records that occur together. They do not show why.", "items": ITEMS, "base": {"period_days": 10},
          "candidates": [{"kind": "time_proximity", "strength": "moderate", "members": ["phone_record:p", "financial_transaction:t"], "key": "time",
                          "reasons": ["x" * 900], "chance": {"words": "y" * 900, "reading": "uncommon", "share_of_days": 0.03}}] * 40,
          "no_links": [], "analyses": [{"id": "time_proximity", "pairs": 1, "found": 40, "title": "t", "existing": None}], "out_of_reach": [],
          "counts": {"items": 2, "pairs": 1, "candidates": 40, "no_links": 0}}


def make():
    seen = {}
    context = SimpleNamespace(case_id="00000000-0000-0000-0000-000000000001", user_id="00000000-0000-0000-0000-000000000002",
                              ledger_session_factory=lambda: contextlib.nullcontext(mock.MagicMock()))
    context.result = lambda name, data, summary=None, **kw: seen.update(name=name, data=data, summary=summary, **kw) or seen
    return context, seen


def tool(context):
    with mock.patch("services.case_service.check_case_access"), \
         mock.patch("services.case_selections.describe", return_value={"group_type": "relation_query", "members": []}), \
         mock.patch("services.relations.runs.latest_for", return_value="r"), \
         mock.patch("services.relations.runs.view", return_value={"result": RESULT}):
        return {t.name: t for t in relation_tools.make_relation_tools(context)}["get_relation_results"]


def test_overview_is_one_compact_read_with_totals_and_cites():
    context, seen = make()
    t = tool(context)
    with mock.patch("services.case_service.check_case_access"), \
         mock.patch("services.case_selections.describe", return_value={"group_type": "relation_query", "members": []}), \
         mock.patch("services.relations.runs.latest_for", return_value="r"), \
         mock.patch("services.relations.runs.view", return_value={"result": RESULT}), \
         mock.patch("postgres.models.user.User", create=True):
        context.ledger_session_factory = lambda: contextlib.nullcontext(mock.MagicMock(get=lambda *a: SimpleNamespace(is_active=True)))
        t.func(selection_id="g")
    data = seen["data"]
    assert data["section"] == "overview" and data["candidates_total"] == 40 and len(data["candidates"]) == 30
    assert data["more"] and "rec://p" in data["items"][0]["cite"] and data["items"][1]["cite"] == "txn://t"
    assert len(json.dumps(data)) < 20000  # 40 candidates of 1,800 characters each would be 70,000
    assert "not proof" in data["rule"]
