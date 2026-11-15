"""Claims an earlier ingestion left unreviewed are checked through the ingestion check (lx-citeproof D)."""
import pytest

from app.pipeline.verify_claims import CandidateCheck
from app.services import claim_backfill as B


def test_the_context_is_the_ingestion_window_around_the_quote():
    document = "Header\n" + "x" * 3000 + "\nDana Reyes paid USD 5,150.\n" + "y" * 3000
    start = document.index("Dana")
    quote = "Dana Reyes paid USD 5,150."
    window = B._context(document, quote, {"quote_start_char": start, "quote_end_char": start + len(quote)})
    assert quote in window and len(window) <= 1800
    # offsets from an older text: found where the text holds it now
    assert quote in B._context(document, quote, {"quote_start_char": 5, "quote_end_char": 9})
    assert B._context(document, "absent", {}) == "absent"


def test_a_relationship_statement_names_both_sides():
    row = {"claim_type": "relationship", "subject_id": "E1", "predicate": "PAID",
           "object_value": {"target_entity_id": "E2", "detail": "fee"}}
    assert B._statement(row, {"E1": "Blue Heron", "E2": "Northgate"}) == "Blue Heron PAID Northgate: fee"


class _Db:
    def __init__(self, writes):
        self.writes = writes

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, statement, params=None):
        self.writes.append(params)

    async def commit(self):
        pass


@pytest.mark.asyncio
async def test_cheapest_file_first_earlier_verdict_kept_and_the_limit_stops_the_case(monkeypatch):
    writes = []

    async def counts(db):
        return [{"case_id": "c1", "unreviewed": 4, "files": [
            {"evidence_file_id": "00000000-0000-0000-0000-00000000000a", "unreviewed": 1},
            {"evidence_file_id": "00000000-0000-0000-0000-00000000000b", "unreviewed": 3}]}]

    async def candidates(db, case_id, file_id):
        n = 1 if file_id.endswith("a") else 3
        return [{"candidate_id": f"{file_id}-{i}", "_row": {"id": f"{file_id}-{i}", "status": "unreviewed",
                 "object_value": {"verification_reason": "budget exhausted"}}} for i in range(n)]

    seen = []

    async def check(chosen, *, case_id):
        seen.append(len(chosen))
        if len(seen) == 1:
            return CandidateCheck(
                {chosen[0]["candidate_id"]: ("SUPPORTED", "stated")}, chosen, [], None)
        return CandidateCheck(
            {chosen[0]["candidate_id"]: ("REJECTED", "not stated")}, chosen[:1], chosen[1:],
            "Not checked: this case's AI spending limit was reached after 1 of 3 claims")

    monkeypatch.setattr(B, "unreviewed_counts", counts)
    monkeypatch.setattr(B, "_file_candidates", candidates)
    monkeypatch.setattr(B, "check_candidates", check)
    monkeypatch.setattr(B.uuid, "UUID", lambda value: value)

    async def no_policy(db):
        return {}
    from app.services import ai_model_policy
    monkeypatch.setattr(ai_model_policy, "load_ai_model_policy", no_policy)
    outcome = await B.check_case(lambda: _Db(writes), "c1", apply=True)
    assert seen == [1, 3]  # the smaller file first
    assert [(f.checked, f.left) for f in outcome.files] == [(1, 0), (1, 2)]
    assert "spending limit" in outcome.files[1].stop_reason
    statuses = [w["s"] for w in writes if w]
    assert statuses == ["verified", "rejected"]
    assert '"previous_verification": {"status": "unreviewed", "reason": "budget exhausted"}' in writes[0]["v"]
    assert B.summary([outcome])["stopped"][0]["left"] == 2


@pytest.mark.asyncio
async def test_without_apply_nothing_is_called_or_written(monkeypatch):
    async def counts(db):
        return [{"case_id": "c1", "unreviewed": 2, "files": [{"evidence_file_id": "f", "unreviewed": 2}]}]

    async def candidates(db, case_id, file_id):
        return [{"candidate_id": "x", "_row": {}}, {"candidate_id": "y", "_row": {}}]

    async def never(*a, **k):
        raise AssertionError("no model call without --apply")

    writes = []
    monkeypatch.setattr(B, "unreviewed_counts", counts)
    monkeypatch.setattr(B, "_file_candidates", candidates)
    monkeypatch.setattr(B, "check_candidates", never)
    outcome = await B.check_case(lambda: _Db(writes), "c1", apply=False)
    assert outcome.files[0].left == 2 and writes == []
