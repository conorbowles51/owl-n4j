"""agent-evidence-rest A, B, C, E, F on real phone and ledger tables (invented data; opt-in PostgreSQL through
``LOUPE_TEST_PHONE_PG_TEMPLATE_URL``). Every test fails on the code before this job."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from postgres.models.user import User
from services.agent import glossary, phone_cross_tools as X, workspace_proposals as W
from services.agent.proposals import ProposalError
from services.financial.model_work import model_origin
from services.phone import link_edges as LE
from services.phone_analysis import framework as F, money_pairings as MP, monitoring_apps as MA
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone
from tests.test_agent_phone_cross_tools import ANA, OWNER, dossier, msg
from tests.test_phone_analysis_money_signals import Ledger, Phone, _run, directory  # noqa: F401

pytestmark = needs_template
ALERT = "Synthetic Bank: Purchase of $50.00 on card ending 1234"


def _origin():
    return model_origin(for_name="Alex", model="DeepSeek V4 Pro", model_id="deepseek-v4-pro", how="case agent proposal")


class Person:
    def __init__(self, conn, case):
        self.id, self.name, self.email = conn.execute(text(
            "SELECT u.id, u.name, u.email FROM users u JOIN cases k ON k.owner_user_id = u.id WHERE k.id = :c"),
            {"c": case}).one()


# ---- A: leads in a stated order, with the reason, every lead listed ------------------------------------------------

@pytest.fixture
def leads_case(directory):  # noqa: F811
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            Ledger(c, case).account("Other Bank", "XXXX0000")
        p = Phone()
        # the lead with fewer alerts is the earliest, so the old order (by time) shows it first
        p.simple("InstalledApplication", Identifier="test.twodollar.app", Name="Two Dollar Exchange")
        p.notification("test.synthbank.mobile", ALERT, when=datetime(2023, 1, 2, 9, tzinfo=timezone.utc))
        p.notification("test.synthbank.mobile", ALERT.replace("1234", "7777"),
                       when=datetime(2024, 2, 10, 15, tzinfo=timezone.utc))
        p.notification("test.synthbank.mobile", ALERT.replace("1234", "7777").replace("50", "60"),
                       when=datetime(2024, 5, 1, 9, tzinfo=timezone.utc))
        p.make(engine, case)
        _run(engine, case)
        yield engine, case


def test_leads_come_by_class_then_count_then_recency_with_the_reason_and_none_is_dropped(leads_case):
    engine, case = leads_case
    with engine.connect() as c:
        out = X.money_signal_leads(c, case)
    assert out["total_matching"] == len(out["items"]) >= 3
    assert [i["rank"] for i in out["items"]] == list(range(1, len(out["items"]) + 1))
    first, second = out["items"][:2]
    assert first["account"] == "ending 7777" and first["rank_reason"].startswith("2 payment alerts")
    assert second["account"] == "ending 1234" and second["rank_reason"].startswith("1 payment alert,")
    last = out["items"][-1]
    assert last["evidence_counts"].get("transactional") is None and last["rank_reason"].startswith("1 app, cookie")
    assert "stays listed" in out["rank_rule"]


def test_the_screen_order_is_the_same_rule(leads_case):
    engine, case = leads_case
    with engine.connect() as c:
        run = X._last_run(c, case, "money_signals")
        screen = F.results(c, case, run.id, kind="account_lead", order="lead_rank")
        tool = X.money_signal_leads(c, case)
    assert [i["id"] for i in screen["items"]] == [i["result_id"] for i in tool["items"]]
    assert all(i["rank_reason"] for i in screen["items"])


def test_the_lead_card_words_stay_off_the_phone_screen(leads_case):
    engine, case = leads_case
    with engine.connect() as c:
        run = X._last_run(c, case, "money_signals")
        screen = F.results(c, case, run.id, kind="account_lead", order="lead_rank")
    words = " ".join(str(i.get("rank_reason")) + str((i["measures"] or {}).get("sentence")) for i in screen["items"])
    assert not any(w in words.lower() for w in ("subpoena", "request", "obtain"))


# ---- B: the base rate beside a pairing ------------------------------------------------------------------------------

@pytest.fixture
def base_case(directory):  # noqa: F811
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            L = Ledger(c, case)
            acct = L.account("Synthetic Bank", "XXXX-XXXX-1234")
            for day in (1, 2, 3, 4):
                L.txn(acct, 5000, date(2024, 2, day))        # the amount, four times
            L.txn(acct, 1234, date(2024, 2, 5))              # another amount
            L.txn(acct, 5000, date(2024, 2, 6), direction="credit")  # same amount, the other way: not in the base
            old = L.txn(acct, 5000, date(2024, 2, 7))
            L.supersede(old, L.txn(acct, 5100, date(2024, 2, 7)))  # corrected away: not counted as that amount
        p = Phone()
        p.notification("test.synthbank.mobile", ALERT, when=datetime(2024, 2, 3, 15, tzinfo=timezone.utc))
        p.make(engine, case)
        yield engine, case


def test_each_pairing_carries_the_true_count_and_base_and_changes_nothing_else(base_case):
    engine, case = base_case
    _, items = _run(engine, case)
    reading = next(i for i in items if i["kind"] == "money_reading")
    pairs = reading["measures"]["pairings"]
    exact = [p for p in pairs if p["amount_minor"] == 5000]
    assert len(exact) == 4  # a common amount still lists every candidate
    for p in exact:
        assert (p["base_rate"]["same_amount"], p["base_rate"]["rows"]) == (4, 6)
        assert p["base_rate"]["words"] == "This amount occurs on 4 of 6 USD money-out rows on this account."
    with engine.connect() as c:
        again = MP.overlay(c, case, [dict(reading, measures={k: v for k, v in reading["measures"].items()})])[0]
    assert [p["level"] for p in again["measures"]["pairings"]] == [p["level"] for p in pairs]


def test_the_base_is_the_rows_a_pairing_is_matched_against(base_case):
    engine, case = base_case
    _, items = _run(engine, case)
    with engine.begin() as c:
        c.execute(text("UPDATE financial_transactions SET provenance = '{\"date_basis\": "
                       "\"statement_end_ordering_only\"}' WHERE case_id = :c AND amount_minor = 1234"), {"c": case})
    with engine.connect() as c:
        reading = MP.overlay(c, case, [next(i for i in items if i["kind"] == "money_reading")])[0]
    assert reading["measures"]["pairings"][0]["base_rate"]["rows"] == 5  # a row with no real date cannot be matched, so it is not in the base


def test_a_row_corrected_since_the_run_counts_at_its_corrected_amount(base_case):
    engine, case = base_case
    _, items = _run(engine, case)
    reading = next(i for i in items if i["kind"] == "money_reading")
    first = next(p for p in reading["measures"]["pairings"] if p["amount_minor"] == 5000)
    with engine.begin() as c:
        L = Ledger(c, case, first_row=100)
        acct = c.execute(text("SELECT account_id FROM financial_transactions WHERE id = :i"),
                         {"i": first["transaction_id"]}).scalar_one()
        L.supersede(first["transaction_id"], L.txn(acct, 7777, date(2024, 2, 1)))
    with engine.connect() as c:
        pairs = MP.overlay(c, case, [reading])[0]["measures"]["pairings"]
    rate = next(p for p in pairs if p["transaction_id"] == first["transaction_id"])["base_rate"]
    assert (rate["same_amount"], rate["rows"]) == (1, 6)


def test_the_agent_line_states_the_base_rate(base_case):
    engine, case = base_case
    _run(engine, case)
    with engine.connect() as c:
        out = X.money_signal_matches(c, case)
    assert "This amount occurs on 4 of 6" in " ".join(l for lines in out["match_lines"].values() for l in lines)
    assert out["items"][0]["pairings"][0]["base_rate"]["rows"] == 6


# ---- C: a claim from a proposal, confirmed by a person before it is evaluated --------------------------------------

@pytest.fixture
def world(monkeypatch):
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, other = make_case(c), make_case(c)
            ext, _ = phone(c, case, label="C1", contacts={ANA: "Ana Synthetic"}, events=[
                msg(at(2023, 3, 14, 9), OWNER, [ANA], "bring the breakfast tomorrow"),
                msg(at(2023, 3, 20, 10), ANA, [OWNER], "breakfast was short"),
                msg(at(2023, 9, 1, 10), ANA, [OWNER], "no more breakfast this year"),
                msg(at(2023, 3, 14, 11), OWNER, [ANA], "thanks")])
            sam = dossier(c, case, "Sam Synthetic", "ent-sam", [OWNER])
            ana = dossier(c, case, "Ana Synthetic", "ent-ana", [ANA])
            L = Ledger(c, case)
            acct = L.account("Synthetic Bank", "XXXX-XXXX-1234")
            party = str(uuid.uuid4())
            near = L.txn(acct, 500_00, date(2023, 3, 15))
            far = L.txn(acct, 90_00, date(2023, 6, 1))
            for t in (near, far):
                c.execute(text("UPDATE financial_transactions SET metadata = CAST(:m AS jsonb) WHERE id = :i"),
                          {"i": t, "m": '{"investigation_labels": {"counterparty_link": {"kind": "party", "id": "%s", '
                                        '"label": "Ana Synthetic"}}}' % party})
        sides = {"ent-sam": {"parties": set(), "accounts": {str(acct)}}, "ent-ana": {"parties": {party}, "accounts": set()}}
        monkeypatch.setattr(LE, "financial_sides", lambda s, c_, keys: {k: sides.get(k, {"parties": set(),
                                                                                         "accounts": set()})
                                                                        for k in keys if k})
        yield dict(engine=engine, case=case, other=other, ext=ext, sam=sam, near=str(near), far=str(far))


def _rec(c, case, word):
    return "rec://%s" % c.execute(text("SELECT record_uid FROM pv_comm_event WHERE case_id = :c AND body LIKE :w LIMIT 1"),
                                  {"c": case, "w": "%%%s%%" % word}).scalar_one()


def test_a_proposed_claim_is_a_draft_with_citations_and_evaluate_statement_waits_for_a_person(world):
    engine, case = world["engine"], world["case"]
    with Session(engine, expire_on_commit=False) as db:
        cite = _rec(db.connection(), case, "bring")
        item = W.propose_claim(db, case_id=case, kind="no_contact", subject=dict(kind="dossier", dossier_id=world["sam"]),
                               quote="I never spoke to Ana in March", window_text="in March", citations=[cite],
                               origin=_origin())
        assert item["review_status"] == "pending_review"
        assert db.execute(text("SELECT count(*) FROM pol_claim WHERE case_id = :c"), {"c": case}).scalar_one() == 0
        reviewer = db.get(User, Person(db.connection(), case).id)
        done = W.accept(db, case_id=case, output_id=item["id"], reviewer=reviewer)
        claim_id = done["accepted_targets"][0]["target_id"]
        row = db.execute(text("SELECT status, origin, ai_model, window_start, window_text, source_anchor FROM pol_claim "
                              "WHERE id = :i"), {"i": claim_id}).mappings().one()
        assert (row["status"], row["origin"], row["ai_model"]) == ("draft", "ai_draft", "deepseek-v4-pro")
        assert row["window_start"] is None and row["window_text"] == "in March"
        assert row["source_anchor"]["citations"] == [cite]
        out = X.statement_check(db.connection(), case, claim_id)
    assert out["available"] is False and "Only a statement a person has confirmed" in out["reason"]


def test_a_claim_about_someone_outside_the_case_is_refused_in_the_same_words(world):
    engine = world["engine"]
    with Session(engine, expire_on_commit=False) as db:
        with pytest.raises(ProposalError) as refused:
            W.propose_claim(db, case_id=world["other"], kind="active", subject=dict(kind="dossier", dossier_id=world["sam"]),
                            quote="q", citations=["txn://%s" % world["near"]], origin=_origin())
    assert str(refused.value) == "Not in this case." and refused.value.status_code == 404


def test_the_draft_of_a_document_reads_every_page_and_says_when_it_stopped(world):
    from services.pattern_of_life import drafting
    from services.workspace_ai_service import MAX_CHUNK_CHARACTERS, MAX_SOURCE_CHUNKS
    engine, case = world["engine"], world["case"]
    fid = uuid.uuid4()
    pages = MAX_SOURCE_CHUNKS + 4
    content = "".join(("line %d of the timeline. " % i).ljust(100, ".") for i in range(pages))
    locations = [dict(page_number=i + 1, start_char=i * 100, end_char=(i + 1) * 100) for i in range(pages)]
    assert 100 < MAX_CHUNK_CHARACTERS
    from postgres.models.evidence import EvidenceDocumentText, EvidenceFile
    with Session(engine, expire_on_commit=False) as db:
        db.add(EvidenceFile(id=fid, case_id=case, original_filename="their-timeline.pdf", stored_path="/nowhere/t",
                            sha256="c" * 64))
        db.add(EvidenceDocumentText(evidence_file_id=fid, content=content, content_sha256="d" * 64,
                                    character_count=len(content), source_locations=locations))
        db.commit()
        sources, reading = drafting.document_sources(db, case, [fid])
        assert len(sources) == MAX_SOURCE_CHUNKS and reading["clipped"] is True
        assert reading["chunks_available"] == pages and reading["chunks_read"] == MAX_SOURCE_CHUNKS
        with pytest.raises(drafting.DraftingError, match="not in this case"):
            drafting.document_sources(db, world["other"], [fid])


def _document(db, case, content, locations=None, **kw):
    from postgres.models.evidence import EvidenceDocumentText, EvidenceFile
    fid = uuid.uuid4()
    db.add(EvidenceFile(id=fid, case_id=case, original_filename="source.pdf", stored_path="/nowhere/s",
                        sha256=fid.hex + fid.hex, **kw))
    db.add(EvidenceDocumentText(evidence_file_id=fid, content=content, content_sha256="d" * 64,
                                character_count=len(content), source_locations=locations or []))
    db.commit()
    return fid


def test_a_long_page_and_a_long_transcript_are_read_to_the_end_or_stated_as_clipped(world):
    from services.pattern_of_life import drafting
    engine, case = world["engine"], world["case"]
    page = "x" * 3000 + " the last words of the long page " + "y" * 3000
    with Session(engine, expire_on_commit=False) as db:
        fid = _document(db, case, page, [dict(page_number=1, start_char=0, end_char=len(page))])
        sources, reading = drafting.document_sources(db, case, [fid])
        assert "".join(s["text"] for s in sources).replace(" ", "") == page.replace(" ", "")
        assert reading["clipped"] is False and all(s["source_anchor"]["page"] == 1 for s in sources)
        fid = _document(db, case, "a word", transcription_segments=[
            dict(start=i, end=i + 1, text="segment %d" % i) for i in range(60)])
        sources, reading = drafting.document_sources(db, case, [fid])
        assert reading["clipped"] is True and reading["chunks_available"] == 61 and reading["chunks_read"] == 36
        fid = _document(db, case, "a word", transcription="z" * (3500 * 8))
        _, reading = drafting.document_sources(db, case, [fid])
        assert reading["chunks_available"] == 9  # eight parts of the transcript and the word


def test_a_phone_thread_document_is_counted_line_by_line_not_cut_to_six_windows(world):
    from services.pattern_of_life import drafting
    engine, case = world["engine"], world["case"]
    lines = "".join("line %d of the thread\n" % i for i in range(50))
    locations = [dict(kind="phone_record", field_path="Body", record_uid=str(uuid.uuid4()),
                      start_char=i * 22, end_char=(i + 1) * 22) for i in range(50)]
    with Session(engine, expire_on_commit=False) as db:
        fid = _document(db, case, lines, locations, source_type="phone_text")
        _, reading = drafting.document_sources(db, case, [fid])
    assert reading["chunks_available"] == 50 and reading["clipped"] is True


# ---- E: monitoring apps, an indicator with its basis ----------------------------------------------------------------

@pytest.fixture
def apps(directory):  # noqa: F811
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
        p = Phone()
        p.simple("InstalledApplication", Identifier="com.apspy.app", Name="System Service")
        p.simple("InstalledApplication", Identifier="test.harmless.app", Name="Calculator")
        p.simple("InstalledApplication", Identifier="test.case.added", Name="Tracker")
        p.notification("test.synthbank.mobile", "Synthetic Bank: a new payee was added to your account",
                       when=datetime(2023, 5, 1, 9, tzinfo=timezone.utc))
        p.notification("test.other.app", "Your game password was changed",
                       when=datetime(2023, 5, 2, 9, tzinfo=timezone.utc))
        p.notification("test.other.app", "Your weekly report is ready", when=datetime(2023, 5, 3, 9, tzinfo=timezone.utc))
        p.notification("test.other.app", "Your account password was changed", when=datetime(2023, 5, 4, 9, tzinfo=timezone.utc))
        p.notification("test.other.app", "Your discarded password was reset", when=datetime(2023, 5, 5, 9, tzinfo=timezone.utc))
        p.make(engine, case)
        with Session(engine, expire_on_commit=False) as db:
            yield engine, db, case, db.get(User, Person(db.connection(), case).id)


def test_a_listed_app_is_an_indicator_with_its_basis_and_the_limits_of_what_it_shows(apps):
    engine, db, case, person = apps
    out = MA.indicators(db.connection(), db, case)
    found = [i for i in out["items"] if i["kind"] == "monitoring_app"]
    assert [i["identifier"] for i in found] == ["com.apspy.app"]
    item = found[0]
    assert item["listed_as"] == "TheTruthSpy" and item["rec"].startswith("rec://")
    assert "no person has reviewed" in item["basis"] and "stalkerware-indicators" in item["basis"]
    assert item["label"] == "Indicator, not a finding" and "who installed it" in item["limits"]
    assert "not a finding" in out["label"].lower()


def test_a_bank_control_notice_sits_in_the_same_lane_and_others_do_not(apps):
    engine, db, case, person = apps
    out = MA.indicators(db.connection(), db, case)
    notices = [i for i in out["items"] if i["kind"] == "bank_control"]
    assert len(notices) == 1 and notices[0]["notice_kinds"] == ["new_payee"]
    assert notices[0]["rec"].startswith("rec://") and "not a finding" in notices[0]["label"]
    assert out["bank_control_notices"] == 1 and out["monitoring_apps"] == 1


def test_hard_dates_leave_items_out_and_count_them(apps):
    engine, db, case, person = apps
    out = MA.indicators(db.connection(), db, case, start=datetime(2023, 6, 1, tzinfo=timezone.utc))
    assert out["bank_control_notices"] == 0 and out["outside_dates"] == 1
    assert out["monitoring_apps"] == 1  # an app with no time stays listed


def test_a_person_edits_the_list_for_the_case_and_the_indicator_follows_at_once(apps):
    engine, db, case, person = apps
    with pytest.raises(MA.MonitoringError, match="names its source"):
        MA.edit(db, case_id=case, identifier="test.case.added", action="add", reason="seen", reviewer=person)
    added = MA.edit(db, case_id=case, identifier="test.case.added", action="add", reason="seen in the report",
                    source="vendor report p. 3", label="Case tracker", reviewer=person)
    seen = {i["identifier"]: i for i in MA.indicators(db.connection(), db, case)["items"] if i["kind"] == "monitoring_app"}
    assert "vendor report p. 3" in seen["test.case.added"]["basis"] and "Added in this case" in seen["test.case.added"]["basis"]
    MA.edit(db, case_id=case, identifier="com.apspy.app", action="reviewed", reason="checked", reviewer=person)
    seen = {i["identifier"]: i for i in MA.indicators(db.connection(), db, case)["items"] if i["kind"] == "monitoring_app"}
    assert "reviewed in this case" in seen["com.apspy.app"]["basis"] and seen["com.apspy.app"]["reviewed"] is True
    MA.remove(db, case_id=case, edit_id=uuid.UUID(added["id"]), reviewer=person)
    seen = {i["identifier"] for i in MA.indicators(db.connection(), db, case)["items"] if i["kind"] == "monitoring_app"}
    assert seen == {"com.apspy.app"}


def test_setting_an_entry_aside_keeps_it_visible_apart_with_who_and_why(apps):
    engine, db, case, person = apps
    MA.edit(db, case_id=case, identifier="com.apspy.app", action="set_aside", reason="the owner's own employer app",
            reviewer=person)
    out = MA.indicators(db.connection(), db, case)
    assert out["monitoring_apps"] == 0
    assert [i["identifier"] for i in out["set_aside"]] == ["com.apspy.app"]
    assert "the owner's own employer app" in out["set_aside"][0]["basis"]


def test_a_model_cannot_edit_the_list(apps):
    engine, db, case, person = apps
    with pytest.raises(MA.MonitoringError) as refused:
        MA.edit(db, case_id=case, identifier="com.apspy.app", action="reviewed", reason="r",
                reviewer=model_origin(for_name="Alex", model="m", model_id="m", how="x"))
    assert refused.value.status_code == 403


# ---- F: each mention joins its ledger rows ---------------------------------------------------------------------------

def _confirm(db, case, cite):
    reviewer = db.get(User, Person(db.connection(), case).id)
    item = W.propose_term(db, case_id=case, term="breakfast", meaning="a cash payment", citations=[cite], origin=_origin())
    W.accept(db, case_id=case, output_id=item["id"], reviewer=reviewer)


def test_every_mention_of_a_confirmed_term_joins_its_rows_inside_the_stated_window_or_says_why(world):
    engine, case = world["engine"], world["case"]
    with Session(engine, expire_on_commit=False) as db:
        _confirm(db, case, _rec(db.connection(), case, "bring"))
        out = glossary.read(db.connection(), db, case)
    term = out["items"][0]
    assert term["reading_words"].startswith("A person's reading")
    m = term["mentions"]
    assert m["total"] == 3 and m["with_rows"] == 2 and m["without_rows"] == 1
    near = [x for x in m["items"] if x["rows"]]
    assert all(x["rows"][0]["txn"] == "txn://%s" % world["near"] for x in near)
    assert near[0]["rows"][0]["amount"] == "USD 500.00" and near[0]["rows"][0]["paid_by"] == "Sam Synthetic"
    assert near[0]["rows_outside_window"] == 1  # the June row is counted, not lost
    alone = next(x for x in m["items"] if not x["rows"])
    assert alone["join_reason"] == "No ledger row between them within 7 days."
    assert "within 7 days" in m["join_rule"]


def test_the_agent_reads_the_term_with_rows_and_a_withdrawn_one_has_no_mentions(world):
    engine, case = world["engine"], world["case"]
    with Session(engine, expire_on_commit=False) as db:
        _confirm(db, case, _rec(db.connection(), case, "bring"))
        out = X.glossary_terms(db.connection(), case)
        assert out["items"][0]["mentions"]["with_rows"] == 2 and "person's reading" in out["note"]
        reviewer = db.get(User, Person(db.connection(), case).id)
        glossary.withdraw(db, case_id=case, term_id=out["items"][0]["id"], reviewer=reviewer, reason="wrong")
        out = X.glossary_terms(db.connection(), case)
    assert out["items"] == [] and out["confirmed"] == 0 and "1 withdrawn" in out["coverage"]


def _lists(c, case):
    from services.search import keyword_lists as K
    return [x["name"] for x in K.list_for_case(c, case)["items"]]


def test_a_confirmed_term_runs_as_a_keyword_list_until_a_person_withdraws_it(world):
    engine, case = world["engine"], world["case"]
    with Session(engine, expire_on_commit=False) as db:
        _confirm(db, case, _rec(db.connection(), case, "bring"))
        out = glossary.read(db.connection(), db, case)
        assert out["items"][0]["keyword_list_note"] is None and _lists(db.connection(), case) == ["Code word: breakfast"]
        reviewer = db.get(User, Person(db.connection(), case).id)
        glossary.withdraw(db, case_id=case, term_id=out["items"][0]["id"], reviewer=reviewer, reason="wrong")
        assert _lists(db.connection(), case) == []


def test_a_term_too_short_to_search_is_confirmed_and_says_what_was_not_done(world):
    engine, case = world["engine"], world["case"]
    with Session(engine, expire_on_commit=False) as db:
        reviewer = db.get(User, Person(db.connection(), case).id)
        item = W.propose_term(db, case_id=case, term="OG", meaning="a supplier",
                              citations=[_rec(db.connection(), case, "bring")], origin=_origin())
        W.accept(db, case_id=case, output_id=item["id"], reviewer=reviewer)
        term = glossary.read(db.connection(), db, case)["items"][0]
    assert term["status"] == "confirmed" and "too short" in term["keyword_list_note"]
    assert term["mentions"]["total"] == 0 and "not searched" in term["mentions"]["search_limits"][0]
