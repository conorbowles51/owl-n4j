"""05 section 4.3.8: every candidate pairing of a phone money reading with a ledger row, its strength by rule, and a
person's confirm or reject remembered across reruns (Neil 2026-11-04).

Invented data only (the synthetic institution and ledger of the approach 1 tests). Opt-in PostgreSQL through
``LOUPE_TEST_PHONE_PG_TEMPLATE_URL``.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.phone_analysis import framework as F
from services.phone_analysis import money_pairings as MP
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.test_phone_analysis_money_signals import Ledger, Phone, _actor, _run, directory  # noqa: F401

pytestmark = needs_template
WHEN = datetime(2024, 3, 2, 15, 0, tzinfo=timezone.utc)
ALERT = "Synthetic Bank: Purchase of $50.00 on card ending 1234"


@pytest.fixture(autouse=True)
def inbox(tmp_path, monkeypatch):
    from services import manual_changes
    monkeypatch.setattr(manual_changes, "INBOX", tmp_path / "MANUAL-CHANGES.jsonl")
    return tmp_path / "MANUAL-CHANGES.jsonl"


def _reading(items, amount):
    rs = [i for i in items if i["kind"] == "money_reading" and i["measures"]["amount_minor"] == amount]
    assert len(rs) == 1
    return rs[0]


def _weak_case(engine):
    """One bound alert of $50.00; ledger rows: 8 days later at the same amount, the same day 16% more (fees beyond
    the tolerance), 40 days later (outside the search), and the same day ten times the amount (outside it too)."""
    with engine.begin() as c:
        case = make_case(c)
        L = Ledger(c, case)
        acct = L.account("Synthetic Bank", "XXXX-XXXX-1234")
        late = L.txn(acct, 5000, date(2024, 3, 10))
        fees = L.txn(acct, 5800, date(2024, 3, 2))
        L.txn(acct, 5000, date(2024, 4, 11))
        L.txn(acct, 50000, date(2024, 3, 2))
    p = Phone()
    p.notification("test.synthbank.mobile", ALERT, when=WHEN)
    p.make(engine, case)
    return case, acct, late, fees


def test_weak_pairings_an_8_day_lag_and_an_amount_off_by_fees_are_listed_with_strength_and_what_was_left_out():
    with fresh_engine() as engine:
        case, acct, late, fees = _weak_case(engine)
        _, items = _run(engine, case)
        r = _reading(items, 5000)
        m = r["measures"]
        # the outcome rules are unchanged: neither row is within the window and the tolerance at once
        assert m["outcome"] == "unresolved"
        by = {p["transaction_id"]: p for p in m["pairings"]}
        assert set(by) == {str(late), str(fees)}
        assert by[str(late)]["level"] == "weak" and by[str(late)]["lag_days"] == 8
        assert by[str(late)]["fits"] == {"amount": 3, "date": 0, "account": 3}
        assert "same amount to the cent" in by[str(late)]["reasons"]["match"]
        assert "payment 8 days after the phone record" in by[str(late)]["reasons"]["match"]
        assert by[str(fees)]["level"] == "weak" and by[str(fees)]["fits"]["amount"] == 1
        assert any("more than the tolerance" in x for x in by[str(fees)]["reasons"]["match"])
        assert "the bank's usual alert wording" in by[str(fees)]["reasons"]["substantiation"]
        # nothing outside the search is hidden: it is counted and said
        assert m["pairings_left_out"]["beyond_days"] == 1 and m["pairings_left_out"]["beyond_amount"] == 1
        assert "1 more than 31 days away" in m["pairings_left_out_words"]
        assert "1 whose amount differs by more than half" in m["pairings_left_out_words"]
        # strongest first, and the reading orders by its best pairing
        assert [p["level"] for p in m["pairings"]] == sorted((p["level"] for p in m["pairings"]),
                                                             key=MP.LEVELS.index)
        assert m["match_rank"] > 0


def test_an_exact_same_day_bound_alert_is_strong_and_an_ambiguous_account_is_moderate():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            L = Ledger(c, case)
            a = L.account("Synthetic Bank", "XXXX-XXXX-1234")
            exact = L.txn(a, 5000, date(2024, 3, 2))
            b1 = L.account("Synthetic Bank", "****5678")
            L.account("SYNTHETIC BANK N.A.", "XXXXXXXX5678", holder="Alex Synthetic")
            amb = L.txn(b1, 700, date(2024, 3, 2))
        p = Phone()
        p.notification("test.synthbank.mobile", ALERT, when=WHEN)
        p.notification("test.synthbank.mobile", "Synthetic Bank: Purchase of $7.00 on card ending 5678", when=WHEN)
        p.make(engine, case)
        _, items = _run(engine, case)
        s = _reading(items, 5000)["measures"]
        assert s["outcome"] == "corroborated"
        assert s["pairings"][0]["transaction_id"] == str(exact) and s["pairings"][0]["level"] == "strong"
        assert s["pairings"][0]["rule_match"] is True
        mo = _reading(items, 700)["measures"]
        assert mo["binding"]["outcome"] == "ambiguous"
        top = mo["pairings"][0]
        assert top["transaction_id"] == str(amb) and top["level"] == "moderate" and top["fits"]["account"] == 1
        assert "more than one account fits (ambiguous)" in top["reasons"]["match"]


def test_an_unbound_alert_is_still_offered_against_the_banks_accounts_at_account_fit_zero():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            L = Ledger(c, case)
            a = L.account("Synthetic Bank", "XXXX-XXXX-1234")
            row = L.txn(a, 2500, date(2024, 3, 2))
        p = Phone()
        p.notification("test.synthbank.mobile", "Synthetic Bank: Purchase of $25.00 on card ending 0000", when=WHEN)
        p.make(engine, case)
        _, items = _run(engine, case)
        m = _reading(items, 2500)["measures"]
        assert m["binding"]["outcome"] != "bound" and m["outcome"] == "not_tested"
        top = m["pairings"][0]
        assert top["transaction_id"] == str(row) and top["fits"]["account"] == 0
        assert top["level"] in ("moderate", "weak")
        assert any("unbound" in x for x in top["reasons"]["match"])


def _decide(engine, case, m, tid, decision, note=None):
    with Session(engine) as db:
        actor = _actor(db.connection(), case)
        out = MP.decide(db, str(case), m["record_uid"], m["field_path"], str(tid), decision, note, actor)
        db.commit()
    return out


def test_a_decision_survives_a_rerun_rejected_is_left_out_of_counts_and_undo_restores(inbox):
    with fresh_engine() as engine:
        case, acct, late, fees = _weak_case(engine)
        _, items = _run(engine, case)
        m = _reading(items, 5000)["measures"]
        _decide(engine, case, m, late, "confirmed", "Same merchant on the phone and the statement")
        _decide(engine, case, m, fees, "rejected", "Different merchant")
        # the ledger changes, so the rerun is a new run with new result ids
        with engine.begin() as c:
            Ledger(c, case, first_row=100).txn(acct, 777, date(2024, 1, 1))
        run2, items2 = _run(engine, case)
        m2 = _reading(items2, 5000)["measures"]
        by = {p["transaction_id"]: p for p in m2["pairings"]}
        assert by[str(late)]["decision"] == "confirmed"
        assert by[str(late)]["decision_words"].startswith("confirmed by Synthetic Reviewer ")
        assert by[str(late)]["rule_words"] == "found by the rule, strength weak"
        assert by[str(fees)]["decision"] == "rejected"
        assert by[str(fees)]["decision_words"] == "rejected by Synthetic Reviewer: Different merchant"
        assert m2["pair_counts"] == {"by_level": {"strong": 0, "moderate": 0, "weak": 1, "faint": 0},
                                     "confirmed": 1, "rejected": 1}
        # undo restores the state before the last decision
        out = _decide(engine, case, m2, fees, "undo")
        assert out["decision"] is None
        with engine.connect() as c:
            again = F.results(c, str(case), run2, limit=50)["items"]
        p = {x["transaction_id"]: x for x in _reading(again, 5000)["measures"]["pairings"]}
        assert p[str(fees)]["decision"] is None and p[str(late)]["decision"] == "confirmed"
        # every decision is in the decision ledger and the manual-change feed (ids only for phone lines)
        with engine.connect() as c:
            kinds = [r[0] for r in c.execute(text("SELECT decision FROM adjudications WHERE case_id = :c ORDER BY "
                                                  "created_at, subject_sequence"), {"c": case})]
            assert sorted(kinds) == sorted(["confirm_phone_result", "reject_phone_result",
                                            "undo_phone_result_decision"])
            rows = c.execute(text("SELECT kind, change_type, link FROM manual_changes WHERE case_id = :c ORDER BY "
                                  "created_at"), {"c": case}).fetchall()
            feed = [(r.kind, r.change_type) for r in rows]
        assert {r.link for r in rows} == {"/cases/%s/phone-money" % case}  # the matches screen's route
        assert ("phone_money_match", "confirm") in feed and ("phone_money_match", "set_aside") in feed
        assert ("phone_money_match_undo", "change") in feed
        assert "Different merchant" not in inbox.read_text()


def test_a_corrected_row_keeps_its_decision_and_a_pairing_no_longer_found_stays_visible():
    with fresh_engine() as engine:
        case, acct, late, fees = _weak_case(engine)
        _, items = _run(engine, case)
        m = _reading(items, 5000)["measures"]
        _decide(engine, case, m, late, "confirmed")
        _decide(engine, case, m, fees, "confirmed")
        with engine.begin() as c:
            L = Ledger(c, case, first_row=200)
            fixed = L.txn(acct, 5000, date(2024, 3, 10))   # the late row re-read: superseded by its correction
            L.supersede(late, fixed)
            gone = L.txn(acct, 9900, date(2024, 3, 2))       # the fees row corrected to an amount no longer in reach
            L.supersede(fees, gone)
        _, items2 = _run(engine, case)
        m2 = _reading(items2, 5000)["measures"]
        by = {p["transaction_id"]: p for p in m2["pairings"]}
        assert by[str(fixed)]["decision"] == "confirmed" and by[str(fixed)]["found_by_rule"] is True
        assert by[str(gone)]["found_by_rule"] is False
        assert by[str(gone)]["decision_words"].endswith(", no longer found by the rule")
        assert by[str(gone)]["decision_words"].startswith("confirmed by Synthetic Reviewer")


def test_a_decision_needs_a_pairing_the_rule_found_or_decided_before():
    with fresh_engine() as engine:
        case, acct, late, fees = _weak_case(engine)
        _, items = _run(engine, case)
        m = _reading(items, 5000)["measures"]
        with engine.begin() as c:
            other = Ledger(c, case, first_row=300).txn(acct, 123, date(2023, 1, 1))
        with pytest.raises(MP.PairNotFound):
            _decide(engine, case, m, other, "confirmed")
        with pytest.raises(MP.PairError):
            _decide(engine, case, m, late, "undo")


def test_the_agent_lists_every_pairing_with_strength_and_who_decided_and_leaves_rejected_out_of_totals():
    from services.agent import phone_cross_tools as X
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            L = Ledger(c, case)
            a = L.account("Synthetic Bank", "XXXX-XXXX-1234")
            exact = L.txn(a, 5000, date(2024, 3, 2))
            late = L.txn(a, 5000, date(2024, 3, 10))
        p = Phone()
        p.notification("test.synthbank.mobile", ALERT, when=WHEN)
        p.make(engine, case)
        _, items = _run(engine, case)
        m = _reading(items, 5000)["measures"]
        with engine.connect() as c:
            before = X.money_signal_matches(c, case)
        assert before["by_outcome"] == {"corroborated": 1}
        assert before["by_strength"]["strong"] == 1 and before["by_strength"]["weak"] == 1
        pairs = before["items"][0]["pairings"]
        assert [x["strength"] for x in pairs] == ["strong", "weak"]
        assert all(x["status"] == "found by the rule, not confirmed" for x in pairs)
        assert pairs[1]["how_well_matched"][1] == "payment 8 days after the phone record"
        _decide(engine, case, m, exact, "rejected", "Refund, not the purchase")
        _decide(engine, case, m, late, "confirmed")
        with engine.connect() as c:
            after = X.money_signal_matches(c, case)
        assert after["by_outcome"] == {"rule match rejected by a person": 1}
        assert after["by_strength"] == {"strong": 0, "moderate": 0, "weak": 1, "faint": 0}
        assert after["confirmed_by_person"] == 1 and after["rejected_by_person"] == 1
        st = {x["payment"]: x["status"] for x in after["items"][0]["pairings"]}
        assert st == {str(late): "confirmed by a person"}
        assert [x["payment"] for x in after["items"][0]["rejected_pairings"]] == [str(exact)]
        assert "never call a rule-found pairing confirmed" in after["note"]
        assert "1 confirmed by a person, 1 rejected by a person" in after["coverage"]


def test_the_final_answer_prompt_carries_the_strength_and_confirmation_wording():
    from services.agent.graph import _final_answer_system_prompt
    s = _final_answer_system_prompt()
    assert "never call a rule-found pairing confirmed" in s and "weak and faint" in s
    assert "never replace them with examples" in s and "list rejected pairings apart" in s


def test_before_a_rerun_a_corrected_row_keeps_its_decision_and_every_reader_leaves_a_rejected_match_out():
    from services.agent import phone_tools
    from services.phone_analysis import money_signals as MS
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            L = Ledger(c, case)
            a = L.account("Synthetic Bank", "XXXX-XXXX-1234")
            exact = L.txn(a, 5000, date(2024, 3, 2))
            late = L.txn(a, 5000, date(2024, 3, 10))
        p = Phone()
        p.notification("test.synthbank.mobile", ALERT, when=WHEN)
        p.make(engine, case)
        run_id, items = _run(engine, case)
        m = _reading(items, 5000)["measures"]
        _decide(engine, case, m, exact, "rejected", "Refund")
        # the late row is corrected after the run and before any rerun: Confirm on the stored id still works
        with engine.begin() as c:
            fixed = Ledger(c, case, first_row=50).txn(a, 5000, date(2024, 3, 10))
            Ledger(c, case, first_row=60).supersede(late, fixed)
        _decide(engine, case, m, late, "confirmed")
        with engine.connect() as c:
            got = _reading(F.results(c, str(case), run_id, limit=50)["items"], 5000)["measures"]
            readings = phone_tools.money_readings(c, case, outcome="corroborated")
            links = MS.phone_links(c, case, [exact])
        by = {x["transaction_id"]: x for x in got["pairings"]}
        assert by[str(late)]["decision"] == "confirmed" and by[str(late)]["corrected_to"] == str(fixed)
        assert by[str(exact)]["decision"] == "rejected"
        assert len(got["pairings"]) == 2  # no second entry for the corrected row
        assert got["pair_counts"]["by_level"]["strong"] == 0 and got["pair_counts"]["rejected"] == 1
        # the badge reads the strongest pairing not rejected
        assert got["best_level"] == "weak"
        # the other readers: the rejected rule match is not corroboration
        assert readings["total_matching"] == 0
        assert links == {}


def test_rows_outside_the_search_are_all_counted_and_said_including_the_other_direction():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            L = Ledger(c, case)
            a = L.account("Synthetic Bank", "XXXX-XXXX-1234")
            L.txn(a, 99999, date(2024, 6, 1))                       # beyond both the days and the amount
            L.txn(a, 5000, date(2024, 3, 2), direction="credit")     # the other direction
        p = Phone()
        p.notification("test.synthbank.mobile", ALERT, when=WHEN)
        p.make(engine, case)
        _, items = _run(engine, case)
        m = _reading(items, 5000)["measures"]
        assert m["pairings"] == []
        assert m["pairings_left_out"]["beyond_days"] == 1 and m["pairings_left_out"]["other_direction"] == 1
        assert "1 in the other direction (money in, where the phone says out)" in m["pairings_left_out_words"]
