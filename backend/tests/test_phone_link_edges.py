"""02-U16 / 05 section 17.8: combined communication and money edges (``services/phone/link_edges.py``).

Done when (06 row 54): edge counts equal Conversations' Between totals under the same ``group_scope``; money sums
p0 to p2 only, p3 stated separately, currencies never summed together, p4 counted only. Invented data only.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from postgres.base import Base
from postgres.models.case_profile import CaseProfile
from postgres.models.enums import ProofClass, TransactionDirection
from services.phone import link_edges as LE
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.test_financial_duplicates import DuplicateTestCase

OWNER, ANA, ANA2, BEN = "phone:+12025550100", "phone:+12025550143", "phone:+12025550144", "phone:+12025550188"


def _m(instant, sender, recips, thread="t", dup=None, app="WhatsApp"):
    parties = [(sender, "sender", sender == OWNER, None, None)] + [(r, "recipient", r == OWNER, None, None)
                                                                    for r in recips]
    return dict(kind="message", instant=instant, body="synthetic", thread=thread, parties=parties, dup=dup, app=app,
                direction="outgoing" if sender == OWNER else "incoming")


def _call(instant, caller, callee):
    return dict(kind="call", instant=instant, thread=None, call_duration_s=30,
                direction="outgoing" if caller == OWNER else "incoming",
                parties=[(caller, "caller", caller == OWNER, None, None), (callee, "callee", callee == OWNER, None, None)])


def _events():
    from tests.phone_streams_fixture import at
    return [
        _m(at(2023, 3, 2, 9), ANA, [OWNER], dup="g1", app="Native Messages"),
        _m(at(2023, 3, 2, 9), ANA, [OWNER], dup="g1", app="IMS Service"),      # a copy of the one above
        _m(at(2023, 3, 3, 9), OWNER, [ANA]),
        _m(at(2023, 4, 3, 9), OWNER, [ANA2], thread="t2"),
        _call(at(2023, 3, 4, 9), ANA, OWNER),
        _call(at(2023, 5, 4, 9), OWNER, ANA),
        _m(at(2023, 3, 6, 9), BEN, [OWNER], thread="t3"),                    # someone else
        _m(at(2023, 3, 7, 9), ANA, [OWNER, BEN], thread="grp"),              # a group message
    ]


def _conversations(c, case, a, b, kind, group_scope, collapse, expand=False, window=(None, None)):
    from services.phone import streams as S
    from services.phone.filters import StreamFilter
    f = StreamFilter.model_validate({
        "case_id": str(case), "participants": [a, b], "participant_mode": "between", "kinds": [kind],
        "group_scope": group_scope, "collapse_copies": collapse, "expand_person_identities": expand,
        "from_instant": window[0], "to_instant": window[1], "include_no_time": window == (None, None)})
    return S.shown_count(c, f)


def _setup(engine):
    from tests.phone_streams_fixture import phone
    with engine.begin() as c:
        case = make_case(c)
        phone(c, case, label="C1", events=_events(),
              threads={"grp": {"chat_type": "Group", "title": "Synthetic group", "members": [OWNER, ANA, BEN]}})
    return case


@needs_template
def test_edge_counts_equal_conversations_between_under_every_scope_and_copy_setting():
    with fresh_engine() as engine:
        case = _setup(engine)
        with engine.connect() as c:
            for scope in ("direct", "include_groups"):
                for collapse in (True, False):
                    for window in ((None, None), ("2023-03-01T00:00:00+00:00", "2023-04-01T00:00:00+00:00")):
                        e = LE.edges(c, case, [{"identity_key": ANA}, {"identity_key": OWNER}], group_scope=scope,
                                     collapse_copies=collapse, from_instant=window[0], to_instant=window[1])["edges"][0]
                        comm = e["communication"]
                        for kind, prefix in LE.KIND_PREFIX.items():
                            assert LE.comm_total(comm, prefix) == _conversations(c, case, ANA, OWNER, kind, scope,
                                                                                 collapse, window=window), \
                                (scope, collapse, window, kind)
                            rec = LE.edge_records(c, case, {"identity_key": ANA}, {"identity_key": OWNER}, prefix,
                                                  group_scope=scope, collapse_copies=collapse,
                                                  from_instant=window[0], to_instant=window[1])
                            assert rec["total"] == LE.comm_total(comm, prefix) == len(rec["items"])
            e = LE.edges(c, case, [{"identity_key": ANA}, {"identity_key": OWNER}])["edges"][0]["communication"]
            # direction: Ana to the owner is one message (the copy collapsed) and one call
            assert (e["messages_ab"], e["messages_ba"], e["calls_ab"], e["calls_ba"]) == (1, 1, 1, 1)
            g = LE.edges(c, case, [{"identity_key": ANA}, {"identity_key": OWNER}],
                         group_scope="include_groups")["edges"][0]["communication"]
            assert g["messages_ab"] == 2  # the group message Ana sent is counted only with include_groups
            sliced = LE.edges(c, case, [{"identity_key": ANA}, {"identity_key": OWNER}], slice_by="month")["edges"][0]
            assert [(s["from"], s["messages"], s["calls"]) for s in sliced["slices"]] == [
                ("2023-03-01", 2, 1), ("2023-05-01", 0, 1)]
            assert sum(s["messages"] for s in sliced["slices"]) == LE.comm_total(sliced["communication"], "messages")


@needs_template
def test_a_person_side_is_every_identity_linked_to_the_dossier_and_equals_conversations_expanded():
    with fresh_engine() as engine:
        case = _setup(engine)
        from tests.phone_streams_fixture import ensure_identity
        dossier = uuid.uuid4()
        with engine.begin() as c:
            c.execute(text("INSERT INTO case_profiles (id, case_id, profile_type, display_name, contacts, linkage_state, "
                           "status, needs_link_review, graph_entity_deleted, created_at, updated_at) VALUES (:d, :c, "
                           "'person', 'Synthetic Ana', '[]', 'unlinked', 'active', false, false, now(), now())"),
                      {"d": dossier, "c": case})
            for key in (ANA, ANA2):
                c.execute(text("INSERT INTO phone_identity_links (case_id, identity_id, dossier_id, decision_id) VALUES "
                               "(:c, :i, :d, :x)"), {"c": case, "i": ensure_identity(c, case, key), "d": dossier,
                                                     "x": uuid.uuid4()})
        with engine.connect() as c:
            e = LE.edges(c, case, [{"dossier_id": str(dossier)}, {"identity_key": OWNER}])["edges"][0]
            assert e["a"] == {"dossier_id": str(dossier), "label": "Synthetic Ana"}
            assert LE.comm_total(e["communication"], "messages") == \
                _conversations(c, case, ANA, OWNER, "message", "direct", True, expand=True) == 3
            assert e["money"] == [] and e["money_mentioned_on_phones"] == 0 and e["money_readings_available"] is False


@needs_template
def test_a_subject_from_another_case_is_not_in_this_case():
    with fresh_engine() as engine:
        case = _setup(engine)
        with engine.begin() as c:
            other = make_case(c)
        with engine.connect() as c:
            with pytest.raises(LE.NotInCase):
                LE.edges(c, other, [{"identity_key": ANA}, {"identity_key": OWNER}])
            with pytest.raises(LE.NotInCase):
                LE.edges(c, case, [{"identity_key": ANA}, {"dossier_id": str(uuid.uuid4())}])


class MoneyTests(DuplicateTestCase):
    """Money between two financial sides, on the ledger harness of the financial suite."""

    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.engine, tables=[CaseProfile.__table__])
        self.doc = self.make_document()
        self.period = self.make_period(self.doc)
        self.party_b = str(uuid.uuid4())

    def row(self, amount, currency="USD", direction=TransactionDirection.debit, proof=ProofClass.p2, link=True,
            day=date(2026, 1, 15)):
        r = self.add_row(self.period, self.doc, amount=amount, direction=direction)
        r.currency, r.proof_class, r.ordering_date = currency, proof.value, day
        if link:
            r.metadata_ = {**(r.metadata_ or {}), "investigation_labels": {"counterparty_link": {
                "kind": "party", "id": self.party_b, "label": "Synthetic B"}}}
        self.db.commit()
        return r

    def sides(self):
        return {"parties": set(), "accounts": {str(self.account.id)}}, {"parties": {self.party_b}, "accounts": set()}

    def test_two_currencies_are_two_totals_and_p3_is_stated_apart(self):
        self.row(100_00)
        self.row(50_00)
        self.row(700_00, currency="MXN")
        self.row(20_00, direction=TransactionDirection.credit)
        self.row(11_00, proof=ProofClass.p3)
        self.row(99_00, link=False)                             # no reviewed payment identity: not between them
        a, b = self.sides()
        rows = LE.payments(self.db, self.case.id, a, b)["rows"]
        money = LE.money_totals(rows)
        assert [m["currency"] for m in money] == ["MXN", "USD"]
        usd = money[1]
        assert (usd["paid_ab_minor"], usd["payments_ab"], usd["paid_ba_minor"], usd["payments_ba"]) == (150_00, 2, 20_00, 1)
        assert usd["p3"] == {"paid_ab_minor": 11_00, "payments_ab": 1, "paid_ba_minor": 0, "payments_ba": 0}
        assert money[0]["paid_ab_minor"] == 700_00
        label = LE.edge_label({"%s_%s" % (p, d): 0 for p in ("messages", "calls", "emails") for d in ("ab", "ba")}, money)
        assert label == ("1 payment totalling MXN 700.00 (p0 to p2); 3 payments totalling USD 170.00 (p0 to p2); "
                         "1 more payment USD 11.00 (p3)")
        assert "—" not in label

    def test_a_corrected_row_counts_by_its_correction_and_quarantined_rows_never(self):
        old = self.row(100_00)
        new = self.row(120_00)
        old.superseded_by_id = new.id
        from postgres.models.enums import LedgerStatus
        q = self.row(500_00)
        q.ledger_status, q.quarantine_reason = LedgerStatus.quarantined.value, "unreadable_row"
        self.db.commit()
        a, b = self.sides()
        assert [r["amount_minor"] for r in LE.payments(self.db, self.case.id, a, b)["rows"]] == [120_00]

    def test_the_window_is_the_ordering_date_and_reversed_sides_reverse_direction(self):
        self.row(100_00, day=date(2026, 1, 15))
        self.row(200_00, day=date(2026, 2, 15))
        a, b = self.sides()
        jan = LE.payments(self.db, self.case.id, a, b, from_date=date(2026, 1, 1), to_date=date(2026, 1, 31))["rows"]
        assert [r["amount_minor"] for r in jan] == [100_00]
        # the same rows with the sides given the other way round: A's debits to B are paid from the second side
        ba = LE.payments(self.db, self.case.id, b, a)["rows"]
        assert [(r["amount_minor"], r["direction"]) for r in ba] == [(100_00, "ba"), (200_00, "ba")]
        assert {r["direction"] for r in LE.payments(self.db, self.case.id, a, b)["rows"]} == {"ab"}

    def test_format_minor_uses_the_currency_exponent(self):
        assert LE.format_minor(840000, "USD") == "USD 8,400.00"
        assert LE.format_minor(1500, "JPY") == "JPY 1,500"
        assert LE.format_minor(5, "USD") == "USD 0.05"

    def test_a_dossier_side_holds_the_accounts_its_linked_holder_party_holds(self):
        from services.financial.account_identity import IdentityRequest, identity_state, save_identity
        from services.financial.account_parties import AccountPartyRequest, account_parties, set_account_party

        def party(role):
            d = account_parties(self.db, case_id=self.case.id)
            d = set_account_party(self.db, case_id=self.case.id, request=AccountPartyRequest(
                expected_revision=d['revision'], account_ids=[self.account.id], new_party_name='Synthetic ' + role,
                relationship={'role': role}, reason='Reviewed ownership'), actor=self.actor)
            return next(p['id'] for p in d['parties'] if p['name'] == 'Synthetic ' + role)

        def link(pid):
            save_identity(self.db, case_id=self.case.id, actor=self.actor, entity_lookup=lambda k, c: {'key': k},
                          request=IdentityRequest(account_id=self.account.id,
                                                  expected_revision=identity_state(self.db, self.case.id)['revision'],
                                                  entity_links=[{'party_id': pid, 'entity_key': 'ent-a'}],
                                                  basis={'basis': 'investigator_knowledge'}, reason='Reviewed'))

        controller = party('controller')
        link(controller)
        assert LE.financial_sides(self.db, self.case.id, ['ent-a'])['ent-a'] == {'parties': {controller}, 'accounts': set()}
        holder = party('holder')
        link(holder)
        assert LE.financial_sides(self.db, self.case.id, ['ent-a'])['ent-a'] == {
            'parties': {holder}, 'accounts': {str(self.account.id)}}
        assert LE.financial_sides(self.db, self.case.id, [None]) == {}

    def test_one_payment_on_both_sides_statements_is_one_payment(self):
        account_b = self._account(self.case.id, identity_key="gb-other-99887766")
        self.db.add(account_b)
        self.db.commit()
        party_a = str(uuid.uuid4())
        self.row(500_00, day=date(2026, 1, 15))                                  # A's debit, linked to B
        credit = self.add_row(self.period, self.doc, amount=500_00, direction=TransactionDirection.credit,
                              account=account_b)                                 # B's credit, linked to A
        credit.currency, credit.ordering_date = "USD", date(2026, 1, 16)
        credit.metadata_ = {"investigation_labels": {"counterparty_link": {"kind": "party", "id": party_a,
                                                                            "label": "Synthetic A"}}}
        self.row(70_00, day=date(2026, 1, 20))                                   # a second payment, one side only
        self.db.commit()
        a = {"parties": {party_a}, "accounts": {str(self.account.id)}}
        b = {"parties": {self.party_b}, "accounts": {str(account_b.id)}}
        rows = LE.payments(self.db, self.case.id, a, b)["rows"]
        assert sorted(r["amount_minor"] for r in rows) == [70_00, 500_00]
        kept = [r for r in rows if r["amount_minor"] == 500_00][0]
        assert kept["direction"] == "ab" and kept["mirrored_by"]["id"] == str(credit.id)
        usd = LE.money_totals(rows)[0]
        assert (usd["paid_ab_minor"], usd["payments_ab"]) == (570_00, 2)

    def test_a_window_ending_at_midnight_closes_the_day_before(self):
        self.row(100_00, day=date(2026, 1, 31))
        self.row(200_00, day=date(2026, 2, 1))
        a, b = self.sides()
        end = LE._date_in_zone("2026-02-01T00:00:00Z", "UTC", end=True)
        rows = LE.payments(self.db, self.case.id, a, b, from_date=date(2026, 1, 1), to_date=end)["rows"]
        assert [r["amount_minor"] for r in rows] == [100_00]
        last = LE._date_in_zone("2026-02-01T23:59:59Z", "UTC", end=True)
        assert len(LE.payments(self.db, self.case.id, a, b, to_date=last)["rows"]) == 2


@needs_template
def test_a_forwarded_message_is_counted_once_in_the_direction_of_its_actual_sender():
    """The owner forwards to Ana a message Ana wrote: Ana is its original sender, the owner its sender. It is one
    message between them, sent owner to Ana; the original sender does not make it also Ana to owner."""
    from tests.phone_streams_fixture import at, phone
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            fwd = dict(kind="message", instant=at(2023, 3, 9, 9), body="synthetic forwarded", thread="t", app="WhatsApp",
                       direction="outgoing", dup=None,
                       parties=[(OWNER, "sender", True, None, None), (ANA, "recipient", False, None, None),
                                (ANA, "original_sender", False, None, None)])
            phone(c, case, label="C1", events=[_m(at(2023, 3, 2, 9), ANA, [OWNER]), fwd])
        with engine.connect() as c:
            comm = LE.edges(c, case, [{"identity_key": ANA}, {"identity_key": OWNER}])["edges"][0]["communication"]
            assert (comm["messages_ab"], comm["messages_ba"]) == (1, 1)
            assert LE.comm_total(comm, "messages") == _conversations(c, case, ANA, OWNER, "message", "direct", True) == 2


@needs_template
def test_no_time_count_is_not_applicable_when_a_window_is_set():
    from tests.phone_streams_fixture import at, phone
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            phone(c, case, label="C1", events=[_m(at(2023, 3, 2, 9), ANA, [OWNER]), _m(None, ANA, [OWNER])])
        with engine.connect() as c:
            whole = LE.edges(c, case, [{"identity_key": ANA}, {"identity_key": OWNER}])["edges"][0]["communication"]
            assert whole["no_time_count"] == 1 and whole["messages_ab"] == 2
            win = LE.edges(c, case, [{"identity_key": ANA}, {"identity_key": OWNER}],
                           from_instant="2023-03-01T00:00:00+00:00", to_instant="2023-04-01T00:00:00+00:00")
            comm = win["edges"][0]["communication"]
            assert comm["no_time_count"] is None and comm["messages_ab"] == 1
