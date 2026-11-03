"""05-S3, approach 1a: money signals on the phone (docs/cellebrite/05 section 4.9, tests 1 to 12).

Invented data only: a synthetic institution in a test directory, 555 numbers, a synthetic ledger written past the
services. Opt-in PostgreSQL through ``LOUPE_TEST_PHONE_PG_TEMPLATE_URL``.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.financial.decisions import Actor
from services.phone_analysis import framework as F
from services.phone_analysis import institutions as INST
from services.phone_analysis import money_parse as P
from services.phone_analysis import money_signals as MS
from tests.phone_pg import fld, fresh_engine, make_case, make_extraction, model, needs_template, refs

REVIEW = {"reviewed_by": "Synthetic Person", "reviewed_on": "2026-11-03", "source_note": "test entry"}
BANK = {"institution_id": "inst:synthbank", "display_name": "Synthetic Bank", "kind": "bank", "country": "US",
        "app_packages": ["test.synthbank.mobile"], "web_domains": ["synthbank.test"],
        "sms_senders": [{"country": "US", "sender": "72345"}], "email_domains": ["synthbank.test"],
        "currencies": ["USD"], "templates": [{"channel": "notification", "name": "synthbank-alert"}], "review": REVIEW}
TWO_DOLLARS = {"institution_id": "inst:twodollar", "display_name": "Two Dollar Exchange", "kind": "exchange",
               "app_packages": ["test.twodollar.app"], "currencies": ["USD", "CAD"], "review": REVIEW}
OTHER = {"institution_id": "inst:otherbank", "display_name": "Other Synthetic Bank", "kind": "bank",
         "web_domains": ["othersynth.test"], "currencies": ["USD"], "review": REVIEW}
DRAFT = {"institution_id": "inst:draftbank", "display_name": "Draft Bank", "kind": "bank",
         "app_packages": ["test.draft.app"], "currencies": ["USD"],
         "review": {"reviewed_by": None, "reviewed_on": None, "source_note": "drafted by a model"}}
WHEN = datetime(2024, 3, 2, 15, 0, tzinfo=timezone.utc)
FORBIDDEN = re.compile(r"—|\bsubpoena|\brequest|\bobtain", re.I)

pytestmark = needs_template


@pytest.fixture(autouse=True)
def directory():
    from services.phone_analysis import approaches
    INST.use_entries([BANK, TWO_DOLLARS, OTHER, DRAFT])
    approaches.install()
    F.register(MS)
    yield
    INST.use_entries(None)


@pytest.fixture
def hooks():
    import copy
    from services.phone import identities, sweep
    saved = copy.copy(sweep._hooks), {k: list(v) for k, v in sweep._hooks.items() if isinstance(v, list)}
    identities.install()
    yield
    sweep._hooks.clear()
    sweep._hooks.update(saved[0])
    sweep._hooks.update(saved[1])


# ---- the phone -----------------------------------------------------------------------------------------------------

class Phone:
    def __init__(self):
        self.records, self.stamps, self.o = [], [], 0

    def _stamp(self, ordinal, position, mt, when):
        self.stamps.append({"o": ordinal, "bp": "%d.0" % position, "mt": mt, "fn": "TimeStamp", "ot": when.isoformat(),
                            "i": when, "os": "explicit", "off": 0})

    def notification(self, package, body, when=WHEN):
        o = self.o
        self.records.append((o, None, o, model("Notification", [
            fld("ServiceIdentifier", ("String", package)), fld("Body", ("String", body)),
            fld("TimeStamp", ("TimeStamp", when.isoformat()))])))
        self._stamp(o, 2, "Notification", when)
        self.o += 1

    def sms(self, sender, body, smsc=None, when=WHEN):
        o = self.o
        f = [fld("Body", ("String", body)), fld("TimeStamp", ("TimeStamp", when.isoformat())),
             refs("From", o + 1, kind="modelField")]
        if smsc:
            f.append(fld("SMSC", ("String", smsc)))
        self.records += [(o, None, o, model("InstantMessage", f)),
                         (o + 1, o, o, model("Party", [fld("Identifier", ("String", sender)),
                                                       fld("Role", ("PartyRole", "From"))]))]
        self._stamp(o, 1, "InstantMessage", when)
        self.o += 2

    def simple(self, mt, **fields):
        self.records.append((self.o, None, self.o, model(mt, [fld(k, ("String", v)) for k, v in fields.items()])))
        self.o += 1

    def make(self, engine, case):
        from services.phone import registry, sweep
        with engine.begin() as c:
            registry.apply_seed(c)
            ext = make_extraction(c, case, self.records, timestamps=self.stamps)
        assert sweep.interpret_one(engine, ext)["status"] == "done"
        return ext


# ---- the ledger ----------------------------------------------------------------------------------------------------

class Ledger:
    def __init__(self, c, case, first_row=0):
        self.c, self.case, self.row = c, case, first_row
        uid = c.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": case}).scalar_one()
        self.run, self.file, self.doc = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        c.execute(text("INSERT INTO financial_ingestion_runs (id, case_id, status, code_version, ruleset_version, "
                       "started_by_user_id, started_by_email, created_at, updated_at) VALUES (:i, :c, 'completed', 't', "
                       "'t', :u, 't@x.test', now(), now())"), {"i": self.run, "c": case, "u": uid})
        c.execute(text("INSERT INTO evidence_files (id, case_id, original_filename, stored_path, sha256) VALUES (:i, :c, "
                       "'synthetic.pdf', '/nowhere/synthetic.pdf', :h)"), {"i": self.file, "c": case, "h": "b" * 64})
        c.execute(text("INSERT INTO financial_source_documents (id, case_id, evidence_file_id, ingestion_run_id, "
                       "sha256_at_ingestion, document_type, proof_class, extraction_layer, parser_name, parser_version, "
                       "created_at, updated_at) VALUES (:i, :c, :f, :r, :h, 'bank_statement', 'p2', 2, 't', '1', now(), "
                       "now())"), {"i": self.doc, "c": case, "f": self.file, "r": self.run, "h": "b" * 64})

    def account(self, institution, printed, holder="Sam Synthetic", statement=True):
        aid = uuid.uuid4()
        self.c.execute(text("INSERT INTO financial_accounts (id, case_id, identity_key, institution_name, "
                            "identifier_as_printed, holder_name, currency, created_at, updated_at) VALUES (:i, :c, :k, "
                            ":n, :p, :h, 'USD', now(), now())"),
                       {"i": aid, "c": self.case, "k": "synthetic-%s" % aid, "n": institution, "p": printed,
                        "h": holder})
        if statement:
            self.c.execute(text("INSERT INTO financial_statement_periods (id, case_id, source_document_id, account_id, "
                                "ingestion_run_id, currency) VALUES (:i, :c, :d, :a, :r, 'USD')"),
                           {"i": uuid.uuid4(), "c": self.case, "d": self.doc, "a": aid, "r": self.run})
        return aid

    def period(self, account, start, end, opening, closing, status="balanced"):
        pid = uuid.uuid4()
        self.c.execute(text("INSERT INTO financial_statement_periods (id, case_id, source_document_id, account_id, "
                            "ingestion_run_id, currency, period_start, period_end, opening_balance_minor, "
                            "closing_balance_minor, opening_balance_source, closing_balance_source, period_start_source, "
                            "period_end_source, reconciliation_status) VALUES (:i, :c, :d, :a, :r, 'USD', :s, :e, :o, :cl, "
                            "'printed', 'printed', 'printed', 'printed', :st)"),
                       {"i": pid, "c": self.case, "d": self.doc, "a": account, "r": self.run, "s": start, "e": end,
                        "o": opening, "cl": closing, "st": status})
        return pid

    def txn(self, account, amount_minor, day, direction="debit", period=None):
        self.row += 1
        tid = uuid.uuid4()
        self.c.execute(text(
            "INSERT INTO financial_transactions (id, case_id, account_id, source_document_id, ingestion_run_id, ref_id, "
            "row_index, amount_minor, currency, direction, transaction_date, ordering_date, ordering_date_source, "
            "proof_class, extraction_layer, ledger_status, content_hash, provenance, metadata, created_at, updated_at) "
            "VALUES (:i, :c, :a, :d, :r, :ref, :n, :amt, 'USD', :dir, :td, :td, 'transaction', 'p2', 2, 'admitted', :h, "
            "'{}', '{}', now(), now())"),
            {"i": tid, "c": self.case, "a": account, "d": self.doc, "r": self.run, "ref": "T-%d" % self.row,
             "n": self.row, "amt": amount_minor, "dir": direction, "td": day, "h": uuid.uuid4().hex})
        if period is not None:
            self.c.execute(text("UPDATE financial_transactions SET statement_period_id = :p WHERE id = :i"),
                           {"p": period, "i": tid})
        return tid

    def supersede(self, old, new):
        self.c.execute(text("UPDATE financial_transactions SET ledger_status = 'superseded', superseded_by_id = :n "
                            "WHERE id = :o"), {"n": new, "o": old})


def _actor(c, case):
    uid, email = c.execute(text("SELECT u.id, u.email FROM users u JOIN cases k ON k.owner_user_id = u.id WHERE "
                                "k.id = :c"), {"c": case}).one()
    return Actor(name="Synthetic Reviewer", email=email, user_id=uid)


def _run(engine, case, params=None):
    with engine.begin() as c:
        run, _ = F.request_run(c, str(case), "money_signals", params, "t@x.test")
    out = F.execute(engine, run["id"])
    assert out["status"] == "completed", out
    with engine.connect() as c:
        items = F.results(c, str(case), run["id"], limit=500)["items"]
    return run["id"], items


def _reading(items, record_uid=None, amount=None):
    rs = [i for i in items if i["kind"] == "money_reading" and (amount is None or i["measures"]["amount_minor"] == amount)]
    assert len(rs) == 1, [i["measures"].get("amount_text") for i in rs]
    return rs[0]


# ---- 1, 2, 6, 9: a reviewed alert binds, corroborates, and the ledger row is unchanged ------------------------------

def _alert_case(engine):
    with engine.begin() as c:
        case = make_case(c)
        L = Ledger(c, case)
        acct = L.account("Synthetic Bank", "XXXX-XXXX-1234")
        L.account("Synthetic Bank", "XXXX-XXXX-9999")
        row = L.txn(acct, 1250, date(2024, 3, 5))       # event date + 3
        old = L.txn(acct, 4000, date(2024, 3, 3))       # read as 40.00, corrected to 41.00
        new = L.txn(acct, 4100, date(2024, 3, 3))
        L.supersede(old, new)
    p = Phone()
    p.notification("test.synthbank.mobile", "Synthetic Bank: Purchase of $12.50 at CORNER CAFE on card ending 1234")
    p.notification("test.synthbank.mobile", "Synthetic Bank: Purchase of $99.00 on card ending 1234")
    p.notification("test.synthbank.mobile", "Synthetic Bank: Purchase of $41.00 on card ending 1234")
    ext = p.make(engine, case)
    return case, ext, acct, row, old, new


def test_1_2_6_9_a_reviewed_alert_binds_by_ending_corroborates_and_never_changes_the_ledger():
    with fresh_engine() as engine:
        case, ext, acct, row, old, new = _alert_case(engine)
        run_id, items = _run(engine, case, {"phase": "1a"})
        # 1: one reading, strength institution_template, a p4 claim, bound to the one account ending 1234
        r = _reading(items, amount=1250)
        m = r["measures"]
        assert r["strength"] == "institution_template" and m["proof_class"] == "p4"
        assert (m["currency"], m["direction"], m["account_ref"]) == ("USD", "debit", "ending 1234")
        assert m["binding"]["outcome"] == "bound" and [a["id"] for a in m["binding"]["accounts"]] == [str(acct)]
        # 2: corroborated against the row three days later; the row's class is unchanged by the run
        assert m["outcome"] == "corroborated" and m["matched"][0]["transaction_id"] == str(row)
        assert m["lag_days"] == [3]
        with engine.connect() as c:
            assert c.execute(text("SELECT proof_class, ledger_status FROM financial_transactions WHERE id = :i"),
                             {"i": row}).one() == ("p2", "admitted")
            links = MS.phone_links(c, case, [row])
            assert links[str(row)][0]["proof_class"] == "p4" and links[str(row)][0]["link"].startswith("rec://")
            detail = F.result_detail(c, str(case), r["id"])
            assert {x["role"] for x in detail["records"]} == {"evidence", "ledger_match"}
            assert [x["ledger_ref_id"] for x in detail["records"] if x["role"] == "ledger_match"] == ["T-1"]
        # 6: no matching row is unresolved, never contradicted, and says an authorisation may not post
        u = _reading(items, amount=9900)["measures"]
        assert u["outcome"] == "unresolved"
        assert "authorization_may_not_post" in [d["code"] for d in _reading(items, amount=9900)["directions"]["undercuts"]]
        assert all(p["outcome"] != "contradicted" for p in u["per_account"])
        # 9: the corrected amount is the one compared; the superseded row is never a candidate
        k = _reading(items, amount=4100)["measures"]
        assert k["outcome"] == "corroborated" and [x["transaction_id"] for x in k["matched"]] == [str(new)]
        assert str(old) not in json.dumps(items)


# ---- 3, 4: currency and separators ---------------------------------------------------------------------------------

def test_3_a_dollar_from_an_institution_with_two_dollar_currencies_is_currency_unknown_and_makes_no_claim():
    r = P.parse("You sent $25.00", institution=TWO_DOLLARS)
    assert r.currency is None and "currency_unknown" in r.flags and not r.testable
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            L = Ledger(c, case)
            L.account("Two Dollar Exchange", "XXXX5555")
        p = Phone()
        p.notification("test.twodollar.app", "You sent $25.00 from account ending 5555")
        p.make(engine, case)
        _, items = _run(engine, case)
        m = _reading(items)["measures"]
        assert "currency_unknown" in m["flags"] and m["currency"] is None
        assert m["binding"]["outcome"] == "bound" and m["per_account"] == []  # bound, but no claim was made
        assert m["outcome"] == "not_tested" and m["reason"] == "amount_or_currency_missing"


def test_4_separators_read_by_locale_else_flagged():
    comma = dict(BANK, decimal_separator=",", currencies=["EUR"])
    assert P.parse("Betrag 1.234,56 EUR belastet", institution=comma).amount_minor == 123456
    r = P.parse("Payment of $1,234 sent", institution=BANK)
    assert r.amount_minor is None and "ambiguous_separator" in r.flags
    assert P.parse("Payment of $1,234 sent", institution=dict(BANK, decimal_separator=".")).amount_minor == 123400
    assert P.parse("Payment of $1,234.56 sent", institution=BANK).amount_minor == 123456
    assert P.parse("Paid 12.50 USD").amount_minor == 1250
    assert P.parse("Order #1234 shipped") is None   # no currency, no amount
    assert P.parse("Purchase on your credit card of $5.00").direction == "debit"


# ---- 5: the sender is the key, never the SMSC ----------------------------------------------------------------------

def test_5_a_text_from_a_personal_number_through_the_banks_smsc_is_not_the_bank():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
        p = Phone()
        p.sms("+12025550177", "I sent you $40.00 for the tickets", smsc="72345")
        p.sms("72345", "Synthetic Bank: you sent $15.00")
        p.make(engine, case)
        _, items = _run(engine, case)
        personal = _reading(items, amount=4000)
        assert personal["measures"]["institution"] is None and personal["strength"] == "unattributed"
        assert personal["measures"]["signal"] == "S9"
        bank = _reading(items, amount=1500)["measures"]
        assert bank["institution"]["id"] == "inst:synthbank" and bank["signal"] == "S2"
        assert "country_unknown" in bank["flags"]  # the phone's country is not known: reported, strength lowered


# ---- 7: two accounts with one ending -------------------------------------------------------------------------------

def test_7_two_accounts_ending_alike_at_one_institution_are_ambiguous_tested_against_both_merged_into_neither():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            L = Ledger(c, case)
            a = L.account("Synthetic Bank", "****5678", holder="Sam Synthetic")
            b = L.account("SYNTHETIC BANK N.A.", "XXXXXXXX5678", holder="Alex Synthetic")
        p = Phone()
        p.notification("test.synthbank.mobile", "Synthetic Bank: Purchase of $7.00 on card ending 5678")
        p.make(engine, case)
        _, items = _run(engine, case)
        m = _reading(items)["measures"]
        assert m["binding"]["outcome"] == "ambiguous"
        assert sorted(x["id"] for x in m["binding"]["accounts"]) == sorted([str(a), str(b)])
        assert sorted(p["account_id"] for p in m["per_account"]) == sorted([str(a), str(b)])
        with engine.connect() as c:  # merged into neither: no account gained an identifier
            assert c.execute(text("SELECT count(*) FROM financial_accounts WHERE case_id = :c AND metadata::text LIKE "
                                  "'%identity_review%'"), {"c": case}).scalar() == 0


# ---- 8: a presence lead and its status on rerun --------------------------------------------------------------------

def test_8_a_bank_cookie_with_no_account_is_a_presence_lead_until_a_statement_arrives():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
        p = Phone()
        p.simple("Cookie", Domain=".www.othersynth.test", Value="synthetic-session-value")
        p.simple("InstalledApplication", Identifier="test.draft.app", Name="Draft Bank")  # unreviewed: never used
        p.make(engine, case)
        _, items = _run(engine, case)
        leads = [i for i in items if i["kind"] == "account_lead"]
        assert len(leads) == 1
        lead = leads[0]
        assert lead["strength"] == "presence" and lead["measures"]["status"] == "no_statement_found"
        assert lead["measures"]["institution"]["id"] == "inst:otherbank"
        assert lead["measures"]["sentence"] == ("This phone had signs of Other Synthetic Bank on it. No account at "
                                                "Other Synthetic Bank is among the financial records in this case.")
        assert "synthetic-session-value" not in json.dumps(items)
        with engine.begin() as c:
            Ledger(c, case, first_row=100).account("Other Synthetic Bank", "XXXX4444")
        _, again = _run(engine, case)
        lead = [i for i in again if i["kind"] == "account_lead"][0]
        assert lead["measures"]["status"] == "possible_statement"


# ---- 10: card numbers ----------------------------------------------------------------------------------------------

def test_10_a_card_number_is_never_returned_unmasked_and_a_reveal_names_actor_and_locator(hooks):
    from services.phone import sensitive
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            actor = _actor(c, case)
        p = Phone()
        p.simple("CreditCard", CreditCardNumber="4111 1111 1111 1234", NameOnCard="Sam Synthetic")
        ext = p.make(engine, case)
        run_id, items = _run(engine, case)
        blob = json.dumps(items)
        assert "4111" not in blob and "1111 1111" not in blob
        lead = [i for i in items if i["kind"] == "account_lead"][0]
        assert lead["measures"]["account_ref"] == "ending 1234" and lead["strength"] == "account"
        with engine.connect() as c:
            assert "4111" not in json.dumps(F.result_detail(c, str(case), lead["id"]), default=str)
            uid = c.execute(text("SELECT record_uid FROM pv_record WHERE extraction_id = :e AND model_type = "
                                 "'CreditCard'"), {"e": ext}).scalar()
        with Session(engine) as db:
            assert sensitive.reveal(db, str(case), str(uid), "CreditCardNumber", 0, actor)["value"].endswith("1234")
            db.commit()
        with engine.connect() as c:
            log = sensitive.reveals(c, str(case))
        assert [(r["record_uid"], r["field_path"], r["by"]) for r in log] == [(str(uid), "CreditCardNumber",
                                                                               actor.name)]


# ---- 11: idempotent runs, supersession, decisions carry over ---------------------------------------------------------

def test_11_same_inputs_same_run_a_ledger_change_supersedes_and_decisions_carry_over():
    with fresh_engine() as engine:
        case, ext, acct, row, old, new = _alert_case(engine)
        first, items = _run(engine, case)
        with engine.begin() as c:
            again, created = F.request_run(c, str(case), "money_signals", None, "t@x.test")
            assert not created and again["id"] == first
            actor = _actor(c, case)
        r = _reading(items, amount=9900)
        with Session(engine) as db:
            F.decide(db, str(case), r["id"], "confirmed", "Read the alert on the phone myself", actor)
            db.commit()
        with engine.begin() as c:
            Ledger(c, case, first_row=100).txn(acct, 777, date(2024, 1, 1))  # the ledger changed
        second, items2 = _run(engine, case)
        assert second != first
        with engine.connect() as c:
            assert F.get_run(c, str(case), first)["status"] == "superseded"
        carried = _reading(items2, amount=9900)
        assert carried["result_key"] == r["result_key"] and carried["decision"] == "confirmed"


# ---- 12: copy ------------------------------------------------------------------------------------------------------

def test_12_lead_copy_has_no_em_dash_and_never_says_what_to_ask_for():
    sentences = [MS.lead_sentence(n, e, counts, f, l, s)
                 for n in ("Synthetic Bank", None) for e in ("1234", None)
                 for counts in ({"transactional": 14}, {"transactional": 1}, {"account": 1}, {"presence": 2})
                 for f, l in ((WHEN, WHEN), (WHEN, datetime(2024, 5, 1, tzinfo=timezone.utc)), (None, None))
                 for s in ("no_statement_found", "referenced_only", "possible_statement")
                 if n or e]
    assert sentences and not [s for s in sentences if FORBIDDEN.search(s)]
    assert MS.lead_sentence("Synthetic Bank", "1234", {"transactional": 14}, WHEN, datetime(2024, 5, 1, tzinfo=
                            timezone.utc), "no_statement_found") == (
        "This phone holds 14 alerts from Synthetic Bank for an account ending 1234, from March 2, 2024 to May 1, 2024. "
        "No statement for an account ending 1234 at Synthetic Bank is among the financial records in this case.")
    assert not FORBIDDEN.search(F.LEAD_LABEL)
    for d in MS.reading_result.__code__.co_consts:
        if isinstance(d, str):
            assert not FORBIDDEN.search(d), d
    # the screen's own copy is checked on the rendered page (MoneySignalsPage.test.tsx)


def test_a_drafted_directory_entry_is_never_used_and_a_model_cannot_review():
    d = INST.Directory(INST.load())
    assert d.by_package("test.draft.app") is None and d.by_package("test.synthbank.mobile") is not None
    with pytest.raises(INST.DirectoryError):
        INST.use_entries([dict(BANK, review={"reviewed_by": "Claude", "reviewed_on": "2026-11-03"})])
        INST.load()
    INST.use_entries([BANK])
    assert INST.Directory(INST.load()).by_domain("https://m.synthbank.test/x") is not None
    assert INST.Directory(INST.load()).by_domain("notsynthbank.test") is None


def test_money_named_between_two_people_counts_on_their_link_only_while_the_phone_is_active():
    from services.phone import link_edges as LE
    from tests.phone_streams_fixture import at, phone
    owner, ana = "phone:+12025550100", "phone:+12025550143"
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            ext, _ = phone(c, case, label="C1", events=[
                dict(kind="message", instant=at(2024, 3, 2, 9), body="I sent you $40.00 for the van", thread="t",
                     app="WhatsApp", direction="incoming",
                     parties=[(ana, "sender", False, None, None), (owner, "recipient", True, None, None)])])
        _run(engine, case)
        with engine.connect() as c:
            assert LE.money_mentioned(c, case, [owner], [ana]) == 1
            other = make_case(c)
            assert LE.money_mentioned(c, other, [owner], [ana]) is None
        with engine.begin() as c:
            c.execute(text("UPDATE phone_extractions SET standing = 'superseded' WHERE id = :e"), {"e": ext})
        with engine.connect() as c:
            assert LE.money_mentioned(c, case, [owner], [ana]) == 0


def test_the_shipped_directory_loads_and_no_drafted_entry_is_used():
    INST.use_entries(None)
    d = INST.load()
    assert d["version"] == "v1" and d["entries"]
    for e in d["entries"]:
        if not INST.reviewed(e):
            assert INST.Directory(d).by_package((e.get("app_packages") or ["none"])[0]) is None, e["institution_id"]


def test_the_measurements_run_on_a_case_count_only_and_record_their_gate():
    from services.phone_analysis import measurements as M
    with fresh_engine() as engine:
        case, ext, acct, row, old, new = _alert_case(engine)
        with engine.begin() as c:
            out = {code: M.record(c, "case", case, code, "t@x.test") for code in sorted(M.MEASURES)}
        assert set(out) == {"money_signals", "message_reconciliation", "deletion_timeline", "awareness", "device_users",
                            "other_devices", "typed_words", "media_spread", "intent", "plans", "relationships",
                            "extraction_comparison", "incident_window"}
        m1 = out["money_signals"]["result"]
        assert m1["m1c_binding"] == {"bound": 3} and m1["m1d_outcome"]["corroborated"] == 2
        assert m1["m1a"][next(iter(m1["m1a"]))]["in_reviewed_directory"] == 1
        assert out["money_signals"]["gate"] == "do_not_build"  # 3 bound readings < 20 and no lead without statement
        assert out["message_reconciliation"]["gate"] == "inconclusive"  # one phone: not measurable
        blob = json.dumps(out, default=str)
        assert "Purchase" not in blob and "CORNER CAFE" not in blob  # counts only, never content
        with engine.connect() as c:
            assert len(M.rows(c, case)) == 13



# ---- 05-S4, phase 1b: coverage from the statement run ----------------------------------------------------------------

def _run_case(engine, periods, rows=(), alert="Synthetic Bank: Purchase of $50.00 on card ending 1234",
              when=datetime(2024, 2, 10, 15, tzinfo=timezone.utc)):
    with engine.begin() as c:
        case = make_case(c)
        L = Ledger(c, case)
        acct = L.account("Synthetic Bank", "XXXX1234", statement=False)
        pids = [L.period(acct, *p) for p in periods]
        for amount, day in rows:
            L.txn(acct, amount, day, period=pids[0] if pids else None)
    p = Phone()
    p.notification("test.synthbank.mobile", alert, when=when)
    p.make(engine, case)
    return case


JAN, FEB, MAR = (date(2024, 1, 1), date(2024, 1, 31)), (date(2024, 2, 1), date(2024, 2, 29)), \
    (date(2024, 3, 1), date(2024, 3, 31))


def test_1b_a_complete_reconciled_run_without_the_payment_contradicts_and_says_why_it_may_not_post():
    with fresh_engine() as engine:
        case = _run_case(engine, [(*JAN, 100000, 90000), (*FEB, 90000, 80000), (*MAR, 80000, 70000)])
        _, items = _run(engine, case)
        r = _reading(items)
        assert r["measures"]["outcome"] == "contradicted" and r["measures"]["reason"] == "no_transaction"
        assert "authorization_may_not_post" in [d["code"] for d in r["directions"]["undercuts"]]
        assert r["measures"]["proof_class"] == "p4"
        _, items_1a = _run(engine, case, {"phase": "1a"})
        assert _reading(items_1a)["measures"]["outcome"] == "unresolved"  # 1a never contradicts


def test_1b_a_gap_or_an_unreconciled_period_in_the_window_leaves_it_unresolved():
    with fresh_engine() as engine:
        gap = _run_case(engine, [(*JAN, 100000, 90000), (*MAR, 80000, 70000)])
        m = _reading(_run(engine, gap)[1])["measures"]
        assert m["outcome"] == "unresolved" and m["reason"] in ("records_incomplete", "outside_coverage")
        unbalanced = _run_case(engine, [(*JAN, 100000, 90000), (*FEB, 90000, 80000, "unbalanced"),
                                        (*MAR, 80000, 70000)])
        m = _reading(_run(engine, unbalanced)[1])["measures"]
        assert m["outcome"] == "unresolved" and m["reason"] == "records_incomplete"


def test_1b_a_payment_in_a_reconciled_period_corroborates_without_the_unverified_note():
    with fresh_engine() as engine:
        case = _run_case(engine, [(*FEB, 90000, 85000)], rows=[(5000, date(2024, 2, 12))])
        m = _reading(_run(engine, case)[1])["measures"]
        assert m["outcome"] == "corroborated"
        assert all("does not reconcile" not in n for p in m["per_account"] for n in p["notes"])


# ---- review cases: several candidates, effective links, no time, parser shapes, reviewers ---------------------------

def test_two_payments_that_could_both_be_the_alert_link_neither_and_are_listed_as_candidates():
    with fresh_engine() as engine:
        case = _run_case(engine, [(*FEB, 90000, 80000)], rows=[(5000, date(2024, 2, 11)), (5000, date(2024, 2, 12))])
        _, items = _run(engine, case)
        r = _reading(items)
        assert r["measures"]["outcome"] == "several_candidates"
        assert r["measures"]["reason"] == "several_payments_match"
        codes = [d["code"] for d in r["directions"]["undercuts"]]
        assert "several_candidates" in codes
        assert not any(d["code"] in ("corroborated", "exact_amount") for d in r["directions"]["supports"])
        with engine.connect() as c:
            roles = [x.role for x in c.execute(text(
                "SELECT x.role FROM phone_analysis_result_records x WHERE x.result_id = :r AND "
                "x.ledger_transaction_id IS NOT NULL"), {"r": r["id"]})]
            assert sorted(roles) == ["ledger_candidate", "ledger_candidate"]
            ids = [str(t) for (t,) in c.execute(text("SELECT id FROM financial_transactions WHERE case_id = :c"),
                                                {"c": str(case)})]
            assert not any(MS.phone_links(c, case, ids).values())


def test_a_link_to_a_payment_that_was_later_superseded_is_not_shown_on_the_ledger():
    with fresh_engine() as engine:
        case = _run_case(engine, [(*FEB, 90000, 85000)], rows=[(5000, date(2024, 2, 12)), (7000, date(2024, 2, 25))])
        _, items = _run(engine, case)
        assert _reading(items)["measures"]["outcome"] == "corroborated"
        with engine.begin() as c:
            match, other = [str(t) for (t,) in c.execute(text(
                "SELECT id FROM financial_transactions WHERE case_id = :c ORDER BY amount_minor"), {"c": str(case)})]
            links = MS.phone_links(c, case, [match])
            assert len(links[match]) == 1 and "device_zone" in links[match][0]
            c.execute(text("UPDATE financial_transactions SET ledger_status = 'superseded', superseded_by_id = :n "
                           "WHERE id = :o"), {"n": other, "o": match})
            assert not MS.phone_links(c, case, [match]).get(match)


def test_an_alert_with_no_time_on_the_phone_is_not_checked_and_says_why():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            L = Ledger(c, case)
            acct = L.account("Synthetic Bank", "XXXX1234")
            L.txn(acct, 5000, date(2024, 2, 12))
        p = Phone()
        p.simple("Notification", ServiceIdentifier="test.synthbank.mobile",
                 Body="Synthetic Bank: Purchase of $50.00 on card ending 1234")
        p.make(engine, case)
        m = _reading(_run(engine, case)[1])["measures"]
        assert m["outcome"] == "not_tested" and m["reason"] == "event_time_missing"


@pytest.mark.parametrize("text_, amount, currency, digits, flags", [
    ("A/c XX1234 INR 500.00 debited", 50000, "INR", "1234", set()),
    ("Purchase of $50.00 on card ending 1234. Available balance $1,200.00", 5000, None, "1234",
     {"balance_mentioned", "several_amounts"}),
    ("Your payment of $75.00 is due on 03/12", 7500, None, None, {"payment_due_notice", "direction_unknown"}),
    ("You sent $20.00 to account ending 5678", 2000, None, None, {"other_side_account"}),
    ("Purchase of $1 234.50 at SHOP", None, None, None, {"ambiguous_separator"}),
])
def test_parser_shapes_from_the_review(text_, amount, currency, digits, flags):
    r = P.parse(text_, institution=None, phone_country="US", template=None)
    assert (r.amount_minor, r.currency, r.account_digits) == (amount, currency, digits)
    assert flags <= set(r.flags)


def test_a_grouped_card_number_is_read_whole_and_shown_as_its_last_four():
    r = P.parse("Card 4111 1111 1111 1234 charged $5.00", institution=None, phone_country="US", template=None)
    assert r.account_digits == "4111111111111234" and r.amount_minor == 500
    assert MS._masked_ref(r) == "ending 1234"


def test_a_reviewer_is_a_person_with_a_date_and_never_a_model_by_any_product_name():
    assert INST.reviewed({"review": {"reviewed_by": "Ai Tanaka", "reviewed_at": "2026-11-03T10:00:00Z"}})
    assert not INST.reviewed({"review": {"reviewed_by": "Ai Tanaka"}})
    for name in ("ChatGPT", "Gemini 2", "Claude3", "GitHub Copilot", "Llama reviewer", "Mistral"):
        assert not INST.reviewed({"review": {"reviewed_by": name, "reviewed_on": "2026-11-03"}}), name


# ---- second review: merged accounts, period changes, dates after an ending, reviewers ------------------------------

def test_an_account_merged_with_another_never_turns_an_absence_into_a_contradiction():
    """The alert binds A by its ending; A is merged with B and the payment is on B's statement. A's own rows lack
    it, so a contradiction would be false: the absence stays unresolved."""
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            L = Ledger(c, case)
            a = L.account("Synthetic Bank", "XXXX1234", statement=False)
            b = L.account("Synthetic Bank", "XXXX9876", statement=False)
            for acct in (a, b):
                for p in (JAN, FEB, MAR):
                    L.period(acct, *p, 100000, 100000)
            pid = c.execute(text("SELECT id FROM financial_statement_periods WHERE account_id = :b AND period_start = "
                                 ":s"), {"b": b, "s": FEB[0]}).scalar_one()
            L.txn(b, 5000, date(2024, 2, 12), period=pid)
            c.execute(text("UPDATE financial_accounts SET metadata = CAST(:m AS jsonb) WHERE id = :b"),
                      {"m": json.dumps({"canonical_account_id": str(a)}), "b": b})
        p = Phone()
        p.notification("test.synthbank.mobile", "Synthetic Bank: Purchase of $50.00 on card ending 1234",
                       when=datetime(2024, 2, 10, 15, tzinfo=timezone.utc))
        p.make(engine, case)
        m = _reading(_run(engine, case)[1])["measures"]
        assert m["outcome"] != "contradicted", m


def test_a_statement_period_that_stops_reconciling_makes_the_run_read_again():
    with fresh_engine() as engine:
        case = _run_case(engine, [(*JAN, 100000, 90000), (*FEB, 90000, 80000), (*MAR, 80000, 70000)])
        with engine.connect() as c:
            before = MS.ledger_revision(c, case)
        with engine.begin() as c:
            c.execute(text("UPDATE financial_statement_periods SET reconciliation_status = 'unbalanced' WHERE "
                           "case_id = :c AND period_start = :s"), {"c": str(case), "s": FEB[0]})
        with engine.connect() as c:
            assert MS.ledger_revision(c, case) != before
        m = _reading(_run(engine, case)[1])["measures"]
        assert m["outcome"] == "unresolved" and m["reason"] == "records_incomplete"


@pytest.mark.parametrize("text_", ["Card ending 1234 12/05 $25.00", "Acct ending in 1234 2025-11-02 purchase $40.00",
                                   "Card x1234 2024 purchase $9.00"])
def test_a_date_or_year_after_an_ending_is_never_read_into_the_account(text_):
    r = P.parse(text_, institution=None, phone_country="US", template=None)
    assert r.account_digits == "1234"


def test_a_person_whose_name_contains_a_model_name_is_a_person():
    for name in ("Claude Smith", "Claudette Ng", "Sam Bot"):
        assert INST.reviewed({"review": {"reviewed_by": name, "reviewed_on": "2026-11-03"}}), name
    for name in ("Claude", "claude-opus-5-5", "DeepSeek V3", "gpt-4o"):
        assert not INST.reviewed({"review": {"reviewed_by": name, "reviewed_on": "2026-11-03"}}), name


@pytest.mark.parametrize("text_", ["Your card 4111 1111 1111 1234. Charged $20.00",
                                   "Spending on card 4111 1111 1111 1234 $20.00",
                                   "Card 4111-1111-1111-1234, charged $20.00"])
def test_a_grouped_card_number_is_read_whole_before_punctuation_and_after_any_word(text_):
    r = P.parse(text_, institution=None, phone_country="US", template=None)
    assert r.account_digits == "4111111111111234" and MS._masked_ref(r) == "ending 1234"
