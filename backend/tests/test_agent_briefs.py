"""Dated "what changed" briefs (services/agent/briefs.py).

The pure part (``diff``) is tested on hand-made snapshots. The database part (``snapshot``, ``build``, ``latest``,
``sweep_once`` and the import request) runs against a PostgreSQL test database when ``AGENT_BRIEFS_TEST_DATABASE_URL``
names one holding the Loupe schema and at least one case with financial records (skipped otherwise, with the reason).
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from services.agent import briefs as B


def _acc(covered, gaps=(), label="Bank ending 0100"):
    return {"read": True, "label": label, "statements": len(covered), "from": covered[0][0] if covered else None,
            "to": covered[-1][1] if covered else None, "covered": [list(c) for c in covered],
            "gaps": [list(g) for g in gaps], "breaks": 0, "excluded": 0}


def _snap(**over):
    base = {
        "ledger_revision": "r1", "input_revision": "i1",
        "totals": {"available": True, "considered_rows": 3, "verified_rows": 0, "working_rows": 3,
                   "outside_verified_rows": 3, "verified": {},
                   "working": {"USD": {"rows": 3, "credits_minor": "1000", "debits_minor": "400",
                                       "net_minor": "600"}}},
        "accounts": {"a1": _acc([("2024-01-01", "2024-01-31"), ("2024-03-01", "2024-03-31")],
                                [("2024-01-31", "2024-03-01", 29)])},
        "references": {"g1": {"reference": "ending 9999", "kind": "account", "status": "no_statement_found",
                              "payments": 2}},
        "phone": {"phones": 0},
        "judgements": {"open": 2, "confirmed": 0, "corrected": 0, "open_by_rule": {"r.date": 2}, "total": 2,
                       "by_rule": {"r.date": 2}},
        "conclusions": {"items": {"entry:e1": {"kind": "hypothesis", "id": "e1", "title": "Rent paid from A",
                                               "state": "proposed", "rows": ["t1"]}},
                        "rows": {"t1": {"status": "admitted", "replaced_by": None, "amount_minor": "400",
                                        "currency": "USD", "direction": "debit", "date": "2024-01-05",
                                        "counterparty": "Landlord", "proof_class": "p2"}},
                        "hypotheses_open": 1},
    }
    base.update(over)
    return base


def test_a_statement_filling_a_gap_closes_the_lead_and_makes_its_days_testable():
    before = _snap()
    after = _snap(ledger_revision="r2", accounts={"a1": _acc([("2024-01-01", "2024-01-31"), ("2024-02-01", "2024-02-29"),
                                                              ("2024-03-01", "2024-03-31")])})
    c = B.diff(before, after)
    assert c["leads_closed"]["count"] == 1
    lead = c["leads_closed"]["items"][0]
    assert lead["kind"] == "missing_period" and lead["days_now_covered"] == 29 and lead["days_still_missing"] == 0
    assert c["newly_testable"]["days"] == 29
    assert c["newly_testable"]["spans"]["items"][0]["from"] == "2024-02-01"
    assert c["open_leads"]["missing_periods"] == 0
    assert c["something_changed"]


def test_a_gap_that_only_moved_is_not_a_closed_lead():
    """The run's last statement moved later, so the seam keys change, but no missing day was covered."""
    before = _snap()
    after = _snap(accounts={"a1": _acc([("2024-01-01", "2024-01-31"), ("2024-03-01", "2024-03-31"),
                                        ("2024-05-01", "2024-05-31")],
                                       [("2024-01-31", "2024-03-01", 29), ("2024-03-31", "2024-05-01", 30)])})
    c = B.diff(before, after)
    assert c["leads_closed"]["count"] == 0
    assert c["leads_opened"]["count"] == 1 and c["leads_opened"]["items"][0]["days"] == 30


def test_a_statement_inside_a_long_gap_closes_part_of_it_and_opens_no_new_lead():
    before = _snap(accounts={"a1": _acc([("2024-01-01", "2024-01-31"), ("2024-12-01", "2024-12-31")],
                                        [("2024-01-31", "2024-12-01", 304)])})
    after = _snap(accounts={"a1": _acc([("2024-01-01", "2024-01-31"), ("2024-06-01", "2024-06-30"),
                                        ("2024-12-01", "2024-12-31")],
                                       [("2024-01-31", "2024-06-01", 121), ("2024-06-30", "2024-12-01", 153)])})
    c = B.diff(before, after)
    assert c["leads_closed"]["count"] == 1 and c["leads_closed"]["items"][0]["days_now_covered"] == 30
    assert c["leads_closed"]["items"][0]["days_still_missing"] == 274
    assert c["leads_opened"]["count"] == 0


def test_an_account_named_in_payments_closes_when_a_statement_may_hold_it():
    after = _snap(references={"g1": {"reference": "ending 9999", "kind": "account", "status": "possible_statement",
                                     "payments": 2}})
    c = B.diff(_snap(), after)
    assert [l["kind"] for l in c["leads_closed"]["items"]] == ["missing_account"]
    assert "ending 9999" in c["leads_closed"]["items"][0]["sentence"]


def test_totals_before_and_after_carry_both_revisions():
    after = _snap(ledger_revision="r2", totals={**_snap()["totals"], "working": {
        "USD": {"rows": 5, "credits_minor": "1500", "debits_minor": "400", "net_minor": "1100"},
        "EUR": {"rows": 1, "credits_minor": "10", "debits_minor": "0", "net_minor": "10"}},
        "verified": {"EUR": {"rows": 1, "credits_minor": "10", "debits_minor": "0", "net_minor": "10"}}})
    t = B.diff(_snap(), after)["totals"]
    assert t["before_revision"] == "r1" and t["after_revision"] == "r2"
    usd = next(x for x in t["currencies"] if x["currency"] == "USD" and x["population"] == "working")
    assert usd["credits_change_minor"] == "500" and usd["rows_change"] == 2 and usd["before"]["credits_minor"] == "1000"
    eur = [x for x in t["currencies"] if x["currency"] == "EUR"]
    assert [x["population"] for x in eur] == ["verified", "working"] and all(x["before"] is None for x in eur)
    # verified and working are separate lines, never added together
    assert t["changed"] == 3 and not any(x["population"] == "verified" and x["currency"] == "USD"
                                         for x in t["currencies"])


def test_judgement_calls_added_and_resolved_are_counted_per_rule():
    after = _snap(judgements={"open": 3, "confirmed": 1, "corrected": 0, "open_by_rule": {"r.date": 1, "r.amount": 2},
                              "total": 4, "by_rule": {"r.date": 2, "r.amount": 2}})
    j = B.diff(_snap(), after)["judgement_calls"]
    assert j["added_open"] == 2 and j["added_by_rule"] == {"r.amount": 2} and j["resolved"] == 1
    assert j["open_before"] == 2 and j["open"] == 3


def test_calls_added_and_resolved_under_one_rule_are_not_netted():
    """3 added and 3 resolved under the same rule: 3 added, 3 resolved (a net count would say 0 added)."""
    after = _snap(judgements={"open": 2, "confirmed": 2, "corrected": 1, "open_by_rule": {"r.date": 2}, "total": 5,
                              "by_rule": {"r.date": 5}})
    j = B.diff(_snap(), after)["judgement_calls"]
    assert j["added_open"] == 3 and j["resolved"] == 3


def test_a_rejected_proposal_counts_as_resolved():
    """A case agent's proposal a person rejected is answered (agent-proposals' status); old code left it out."""
    after = _snap(judgements={"open": 1, "confirmed": 0, "corrected": 0, "rejected": 1, "open_by_rule": {"r.date": 1},
                              "total": 2, "by_rule": {"r.date": 2}})
    j = B.diff(_snap(), after)["judgement_calls"]
    assert j["resolved"] == 1


def test_a_conclusion_whose_cited_row_was_corrected_is_named():
    rows = dict(_snap()["conclusions"]["rows"])
    rows["t1"] = {**rows["t1"], "status": "superseded", "replaced_by": "t9"}
    after = _snap(conclusions={**_snap()["conclusions"], "rows": rows})
    c = B.diff(_snap(), after)["conclusions_changed"]
    assert c["count"] == 1 and c["items"][0]["title"] == "Rent paid from A"
    assert c["items"][0]["rows"][0]["before"]["status"] == "admitted"
    assert c["items"][0]["rows"][0]["after"]["replaced_by"] == "t9"


def test_nothing_changed_writes_no_new_brief():
    c = B.diff(_snap(), _snap())
    assert not c["something_changed"]
    assert c["leads_closed"]["count"] == 0 and c["totals"]["changed"] == 0


def test_a_first_brief_closes_nothing_and_states_the_starting_point():
    c = B.diff(None, _snap())
    assert c["first"] and c["something_changed"]
    assert c["leads_closed"]["count"] == 0 and c["leads_opened"]["count"] == 0
    assert c["open_leads"] == {"accounts_not_read": 0, "missing_periods": 1, "missing_days": 29,
                            "missing_accounts": 1, "phone_leads": 0}
    assert c["totals"]["currencies"][0]["after"]["credits_minor"] == "1000"
    assert c["totals"]["currencies"][0]["population"] == "working" and c["totals"]["changed"] == 0


def test_phone_leads_close_and_unresolved_readings_become_decided():
    """Readings are counted by outcome: a corroborated reading's result key changes when it gains its ledger match."""
    before = _snap(phone={"phones": 1, "run_id": "x", "leads": {"k1": {"status": "no_statement_found",
                                                                      "account_ref": "ending 0100",
                                                                      "institution": "Synthetic Bank"}},
                          "outcomes": {"unresolved": 2, "corroborated": 5}})
    after = _snap(phone={"phones": 1, "run_id": "y", "leads": {"k1": {"status": "possible_statement",
                                                                     "account_ref": "ending 0100",
                                                                     "institution": "Synthetic Bank"}},
                         "outcomes": {"corroborated": 6, "contradicted": 1}})
    c = B.diff(before, after)
    assert [l["kind"] for l in c["leads_closed"]["items"]] == ["phone_lead"]
    assert "may now be covered" in c["leads_closed"]["items"][0]["sentence"]
    t = c["newly_testable"]
    assert t["phone_unresolved_change"] == -2 and t["phone_corroborated_change"] == 1
    assert t["phone_contradicted_change"] == 1


def test_an_earlier_unread_account_or_total_is_never_a_baseline():
    before = _snap(accounts={"a1": {"read": False}}, totals={"available": False, "reason": "x", "verified": {},
                                                             "working": {}})
    c = B.diff(before, _snap())
    assert c["newly_testable"]["days"] == 0 and c["leads_opened"]["count"] == 0
    assert c["totals"]["before_unavailable"] and c["totals"]["changed"] == 0


def test_long_sections_state_what_is_not_shown():
    accounts = {"a%d" % i: _acc([("2024-01-01", "2024-01-31"), ("2024-03-01", "2024-03-31")]) for i in range(60)}
    before = _snap(accounts={k: _acc([("2024-01-01", "2024-01-31")]) for k in accounts})
    c = B.diff(before, _snap(accounts=accounts))
    spans = c["newly_testable"]["spans"]
    assert spans["count"] == 60 and len(spans["items"]) == B.LIST_LIMIT and spans["not_shown"] == 60 - B.LIST_LIMIT


def test_cited_rows_are_read_from_txn_links_and_payment_paths():
    found = B._cited(set(), "See txn://0E3C9F7A-1111-4222-8333-944445555666 and /financial?view=transactions&payment="
                            "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee.")
    assert found == {"0e3c9f7a-1111-4222-8333-944445555666", "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"}


def test_account_numbers_are_masked_to_four():
    assert B.mask("12345678") == "ending 5678"
    assert B.mask("GB29 NWBK 6016 1331 9268 19") == "ending 6819"


def test_the_statement_writer_asks_for_a_brief():
    import inspect
    from services.financial import statement_import
    src = inspect.getsource(statement_import.confirm_statement_import)
    assert "request_brief(case_id, 'import', session_factory)" in src


def test_a_brief_request_uses_the_callers_database_and_never_raises():
    calls = []

    class Broken:
        def __enter__(self):
            calls.append("opened")
            raise RuntimeError("database down")

        def __exit__(self, *a):
            return False
    B.request_brief("00000000-0000-4000-8000-000000000000", "import", lambda: Broken())
    assert calls == ["opened"]


# ---- PostgreSQL ----------------------------------------------------------------------------------------------------

URL = os.environ.get("AGENT_BRIEFS_TEST_DATABASE_URL")
pg = pytest.mark.skipif(not URL, reason="Needs AGENT_BRIEFS_TEST_DATABASE_URL: a PostgreSQL test database holding the "
                                        "Loupe schema and a case with financial records")


@pytest.fixture
def factory():
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(URL)
    f = sessionmaker(bind=engine)
    yield f
    engine.dispose()


def _a_case(factory):
    from sqlalchemy import text
    with factory() as s:
        cid = os.environ.get("AGENT_BRIEFS_TEST_CASE") or s.execute(text(
            "SELECT t.case_id FROM financial_transactions t JOIN financial_source_documents d ON d.id = "
            "t.source_document_id WHERE d.status = 'admitted' AND t.ledger_status = 'admitted' GROUP BY 1 ORDER BY "
            "count(*) LIMIT 1")).scalar()
        s.execute(text("DELETE FROM case_briefs WHERE case_id = :c"), {"c": str(cid)})
        s.execute(text("DELETE FROM case_brief_requests WHERE case_id = :c"), {"c": str(cid)})
        s.commit()
    return str(cid)


@pg
def test_first_build_then_unchanged_check_then_withdrawn_statement(factory):
    from sqlalchemy import text
    cid = _a_case(factory)
    with factory() as s:
        r1 = B.build(s, cid, "first")
    assert r1["created"] and r1["brief"]["changes"]["first"]
    assert r1["brief"]["cost"]["model_calls"] == 0
    with factory() as s:
        r2 = B.build(s, cid, "nightly")
    assert not r2["created"] and r2["brief"]["id"] == r1["brief"]["id"]
    with factory() as s:
        latest = B.latest(s.connection(), cid)
        assert latest["out_of_date"] is False
        # a statement's verified rows leave the ledger (its source no longer admitted), in a transaction rolled back
        doc = s.execute(text("SELECT t.source_document_id, count(*) n FROM financial_transactions t JOIN "
                             "financial_source_documents d ON d.id = t.source_document_id WHERE t.case_id = :c AND "
                             "t.ledger_status = 'admitted' AND t.superseded_by_id IS NULL AND d.status = 'admitted' "
                             "GROUP BY 1 ORDER BY 2 LIMIT 1"), {"c": cid}).first()
        assert doc is not None, "the test case needs a statement with verified rows"
        s.execute(text("UPDATE financial_source_documents SET status = 'rejected', updated_at = now() + interval "
                       "'1 minute' WHERE id = :d"), {"d": doc.source_document_id})
        assert B.latest(s.connection(), cid)["out_of_date"] is True
        cur = B.snapshot(s, cid)
        s.rollback()
    with factory() as s:
        prev = s.execute(text("SELECT snapshot FROM case_briefs WHERE id = :i"), {"i": r1["brief"]["id"]}).scalar()
    c = B.diff(prev, cur)
    assert c["something_changed"]
    moved = sum(abs(t["rows_change"]) for t in c["totals"]["currencies"] if t["population"] == "working")
    assert moved == doc.n
    assert c["totals"]["before_revision"] != c["totals"]["after_revision"] or moved


@pg
def test_case_runs_read_what_read_account_continuity_reads(factory):
    from services.financial.continuity import read_account_continuity
    cid = _a_case(factory)
    with factory() as s:
        runs = B.case_runs(s, cid)
        assert runs
        for root, run in runs.items():
            one = read_account_continuity(s, case_id=uuid.UUID(cid), account_id=root)
            assert [(p.period_id, p.start, p.end) for p in run.periods] == \
                [(p.period_id, p.start, p.end) for p in one.periods]
            assert [(x.kind, x.agreement, x.uncovered_days) for x in run.seams] == \
                [(x.kind, x.agreement, x.uncovered_days) for x in one.seams]
            assert sorted((e.period_id, e.reason) for e in run.excluded) == \
                sorted((e.period_id, e.reason) for e in one.excluded)


@pg
def test_an_import_request_waits_until_the_case_is_quiet(factory):
    from sqlalchemy import text
    cid = _a_case(factory)
    now = datetime.now(timezone.utc)
    with factory() as s:
        s.execute(text("INSERT INTO case_brief_requests (case_id, first_requested_at, last_requested_at, reason) VALUES "
                       "(:c, :n, :n, 'import')"), {"c": cid, "n": now})
        s.commit()
        assert cid not in dict(B.due_cases(s.connection(), now + timedelta(seconds=10)))
        assert dict(B.due_cases(s.connection(), now + timedelta(seconds=B.QUIET_SECONDS + 1))).get(cid) == "import"
    done = B.sweep_once(factory, now + timedelta(seconds=B.QUIET_SECONDS + 1), scan=False, nightly=False)
    assert [d[0] for d in done] == [cid] and done[0][1]
    with factory() as s:
        assert s.execute(text("SELECT count(*) FROM case_brief_requests WHERE case_id = :c"), {"c": cid}).scalar() == 0
        assert B.history(s.connection(), cid)["total"] == 1


def test_a_person_deciding_a_phone_match_is_a_change_and_a_brief_without_match_counts_takes_them():
    """05 4.3.8: confirming or rejecting a phone-to-payment match changes what the brief counts, so a new brief is
    written; a brief made before matches were counted is not compared, but the first counts are a change."""
    m0 = {"by_level": {"strong": 18, "moderate": 0, "weak": 10, "faint": 41}, "confirmed": 0, "rejected": 0}
    m1 = {"by_level": {"strong": 18, "moderate": 0, "weak": 9, "faint": 41}, "confirmed": 1, "rejected": 1}
    ph = {"phones": 1, "run_id": "x", "leads": {}, "outcomes": {"corroborated": 16}}
    assert not B.diff(_snap(phone=dict(ph, matches=m0)), _snap(phone=dict(ph, matches=m0)))["something_changed"]
    c = B.diff(_snap(phone=dict(ph, matches=m0)), _snap(phone=dict(ph, matches=m1)))
    assert c["something_changed"] and c["newly_testable"]["phone_matches_after"] == m1
    assert B.diff(_snap(phone=ph), _snap(phone=dict(ph, matches=m0)))["something_changed"]
