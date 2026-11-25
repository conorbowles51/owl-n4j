"""Elsewhere in the case (services.elsewhere): the rules that decide each relation, on a stand-in connection.

The parts' SQL is PostgreSQL's (regular expressions, uuid arrays); here each query is answered by the fake below
from the words in it, so the tests pin the rules: what agrees, what disagrees, what is missing here, what is only
a possible match, and that nothing found says what was searched. A photo's place is never the phone's position.
"""
import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace as NS

from services.elsewhere import documents, financial, phones, service, subject as S, timeline
from services.elsewhere import words as W

CASE = "11111111-2222-3333-4444-555555555555"
T0 = datetime(2024, 3, 8, 22, 40, tzinfo=timezone.utc)


class Result:
    def __init__(self, rows):
        self.rows = list(rows)

    def fetchall(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None

    def scalar(self):
        return self.rows[0][0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class FakeConn:
    """``handlers``: ``[(words that must all be in the SQL, fn(params) -> rows)]``; the first that fits answers."""

    def __init__(self, handlers):
        self.handlers = handlers
        self.sql = []

    def execute(self, clause, params=None):
        sql = str(clause)
        self.sql.append((sql, params))
        for need, fn in self.handlers:
            if all(n in sql for n in need):
                return Result(fn(params or {}))
        return Result([])

    def rollback(self):
        pass


def row(**kw):
    base = dict(id="t1", ordering_date=date(2024, 3, 15), amount_minor=246000, currency="USD", direction="credit",
                description="MOBILE DEP CHK 2204 CORWEN STREET DENTAL", counterparty_raw=None, labels=None,
                holder_name="DORIAN PELL", identifier_as_printed="5502097302", institution_name=None,
                original_filename="pell-2024-03.pdf", file_id="f1", page="1")
    base.update(kw)
    return NS(**base)


class WordsTest(unittest.TestCase):
    def test_check_numbers_and_endings_are_read(self):
        self.assertEqual(W.references_in("done, check 2209 goes out today"), ["2209"])
        self.assertEqual(W.references_in("MOBILE DEP CHK 2204"), ["2204"])
        self.assertEqual(W.endings_in("for deposit only, acct ending 7302"), ["7302"])

    def test_name_phrases_skip_months_and_common_words(self):
        got = W.name_phrases("made it to Lake Orrin! no signal at the dock, back on the 22nd. See you in March")
        self.assertIn("Lake Orrin", got)
        self.assertNotIn("March", got)
        self.assertNotIn("See", got)

    def test_a_single_first_name_is_not_a_full_name(self):
        self.assertFalse(W.strong_name("Dorian (office)"))
        self.assertTrue(W.strong_name("Priya Halloran"))
        self.assertTrue(W.name_in("Priya Halloran", "PRIYA HALLORAN"))
        self.assertFalse(W.name_in("Paul Halloran", "PRIYA HALLORAN"))

    def test_possible_matches_are_never_counted_as_agreement(self):
        items = [W.item(W.POSSIBLE, "a", "b"), W.item(W.POSSIBLE, "a", "b"), W.item(W.AGREES, "a", "b"),
                 W.item(W.NOTHING, "a", "b")]
        self.assertEqual(W.counts(items), {"agrees": 1, "disagrees": 0, "missing_here": 0, "possible_match": 2})

    def test_amount_forms(self):
        self.assertEqual(W.money_forms(246000), ["2,460.00", "2460.00", "2,460"])
        self.assertEqual(W.money_text(277500), "$2,775")
        self.assertEqual(W.money_text(6890), "$68.90")


def statement(**kw):
    s = S.Subject(kind="statement", case_id=CASE)
    for k, v in kw.items():
        setattr(s, k, v)
    return s


class FinancialTest(unittest.TestCase):
    def conn(self, rows):
        return FakeConn([(("financial_transactions",), lambda p: rows),
                         (("financial_accounts a LEFT JOIN financial_statement_periods",), lambda p: [])])

    def test_same_check_number_agrees(self):
        out = financial.part(self.conn([row()]), CASE, statement(references=["2204"]), "UTC")
        self.assertEqual([i["relation"] for i in out["items"]], [W.AGREES])
        self.assertEqual(out["items"][0]["citation"]["href"], "txn://t1")
        self.assertEqual(out["items"][0]["citation"]["label"], "pell-2024-03.pdf p.1")

    def test_same_check_number_with_another_amount_disagrees(self):
        out = financial.part(self.conn([row()]), CASE, statement(references=["2204"], amounts=[(264000, "USD")]),
                             "UTC")
        rels = [i["relation"] for i in out["items"]]
        self.assertEqual(rels[0], W.DISAGREES)
        self.assertIn("$2,460, not $2,640", out["items"][0]["reason"])

    def test_same_amount_without_the_people_is_only_possible(self):
        s = statement(amounts=[(246000, "USD")], start=date(2024, 3, 14), end=date(2024, 3, 14),
                      people=[S.Person(name="Marisol Teague")])
        out = financial.part(self.conn([row(description="MOBILE DEPOSIT")]), CASE, s, "UTC")
        self.assertEqual(out["items"][0]["relation"], W.POSSIBLE)
        s.people = [S.Person(name="Dorian Pell")]
        out = financial.part(self.conn([row(description="MOBILE DEPOSIT")]), CASE, s, "UTC")
        self.assertEqual(out["items"][0]["relation"], W.AGREES)

    def test_a_payment_on_the_persons_own_account_is_not_listed_for_the_name_alone(self):
        s = statement(people=[S.Person(name="Dorian Pell")], start=date(2024, 3, 14), end=date(2024, 3, 14))
        out = financial.part(self.conn([row(description="TAMSWORTH GROCERY")]), CASE, s, "UTC")
        self.assertEqual([i["relation"] for i in out["items"]], [W.NOTHING])
        self.assertIn("Dorian Pell", out["searched"])

    def test_nothing_found_says_what_was_searched(self):
        out = financial.part(self.conn([]), CASE, statement(references=["2299"]), "UTC")
        self.assertEqual(out["items"][0]["relation"], W.NOTHING)
        self.assertIn("check number 2299", out["items"][0]["text"])

    def test_holder_names_keep_abbreviations(self):
        self.assertEqual(financial.holder_words("CORWEN STREET DENTAL PC"), "Corwen Street Dental PC")


class DocumentsTest(unittest.TestCase):
    COPIES = ("Check 2203, 20 February 2024, pay to Tobin Ellery, $1,890.00. Endorsed on the back: for deposit "
              "only, Nettlefield Savings acct ending 7302, mobile deposit.\nCheck 2204, 13 March 2024, pay to Ada "
              "Wrenfield, $2,460.00. Endorsed on the back: for deposit only.")

    def conn(self, content):
        doc = NS(id="d1", original_filename="check-copies-2201-2207.pdf", content=content, content_sha256="s1",
                 source_locations=None, content_folded=None)
        return FakeConn([(("evidence_document_texts",), lambda p: [doc])])

    def test_check_number_with_the_ledger_amount_beside_it_agrees(self):
        out = documents.part(self.conn(self.COPIES), CASE, statement(references=["2204"]), "UTC", {"2204": 246000})
        self.assertEqual(out["items"][0]["relation"], W.AGREES)
        self.assertIn("$2,460", out["items"][0]["reason"])
        self.assertIn("Check 2204", out["items"][0]["citation"]["quote"])

    def test_check_number_beside_another_amount_only_disagrees(self):
        text = "Check 2204, 13 March 2024, pay to Ada Wrenfield, $2,640.00."
        out = documents.part(self.conn(text), CASE, statement(references=["2204"]), "UTC", {"2204": 246000})
        self.assertEqual(out["items"][0]["relation"], W.DISAGREES)

    def test_a_name_alone_is_a_possible_match(self):
        out = documents.part(self.conn("Ada Wrenfield was refunded."), CASE,
                             statement(people=[S.Person(name="Ada Wrenfield")]), "UTC")
        self.assertEqual(out["items"][0]["relation"], W.POSSIBLE)
        self.assertEqual(out["items"][0]["text"], "Ada Wrenfield is named in 1 file: check-copies-2201-2207.pdf.")

    def test_statement_copies_the_ledger_was_built_from_are_left_out(self):
        self.assertIn("dt.content_sha256 = t.content_sha256", documents.DOC_FROM)
        self.assertIn("'phone_text'", documents.DOC_FROM)


def rec(**kw):
    base = dict(record_uid="r1", extraction_id="e1", kind="message", model_type="InstantMessage", instant=T0,
                body="leave me your login", deleted_state=None,
                people=[S.Person(name="Dorian (office)", numbers=["7175550221"]),
                        S.Person(name="Priya Halloran", numbers=["7175550211"])], owner_key="7175550211")
    base.update(kw)
    return S.Record(**base)


class PhonesTest(unittest.TestCase):
    PHONES = [("e1", "Phone 1"), ("e2", "Phone 2"), ("e3", "Phone 3")]
    OWNERS = {"e1": ("7175550211", "Priya Halloran"), "e2": ("7175550231", "Marisol Teague"),
              "e3": ("7175550221", "Dorian Pell")}

    def test_copy_agrees_party_phone_without_it_is_missing_here(self):
        def copies(p):
            if p["e"] == "e3":
                return [NS(ev="v3", uid="r3", body="leave me your login", subject=None, sort_instant=T0,
                           deleted_state="Deleted")]
            return []

        def around(p):
            if p["e"] == "e2":
                return []
            return []

        conn = FakeConn([(("pv_comm_event WHERE extraction_id", "kind = :k"), copies),
                         (("pv_comm_party WHERE event_uid",), lambda p: []),
                         (("JOIN pv_comm_party p",), around)])
        items = phones.record_items(conn, CASE, rec(), self.PHONES, self.OWNERS, "UTC")
        by_phone = {i["citation"]["phone"] if i["citation"] else i["text"]: i for i in items}
        self.assertEqual(by_phone["Phone 3"]["relation"], W.AGREES)
        self.assertIn("deleted on Phone 3 and intact on Phone 1", by_phone["Phone 3"]["text"])
        nothing = [i for i in items if i["relation"] == W.NOTHING]
        self.assertEqual(len(nothing), 1)
        self.assertIn("Phone 2", nothing[0]["text"])

    def test_a_partys_phone_that_holds_the_conversation_either_side_is_missing_here(self):
        before = NS(ev="b", uid="rb", kind="message", sort_instant=T0 - timedelta(hours=2), deleted_state=None)
        after = NS(ev="a", uid="ra", kind="message", sort_instant=T0 + timedelta(hours=3), deleted_state=None)
        conn = FakeConn([(("pv_comm_event WHERE extraction_id", "kind = :k"), lambda p: []),
                         (("JOIN pv_comm_party p",), lambda p: [before, after] if p["e"] == "e3" else [])])
        record = rec(extraction_id="e1")
        items = phones.record_items(conn, CASE, record, [("e1", "Phone 1"), ("e3", "Phone 3")], self.OWNERS, "UTC")
        self.assertEqual(items[0]["relation"], W.MISSING)
        self.assertIn("either side", items[0]["text"])
        self.assertEqual(items[0]["also"][0]["id"], "ra")

    def test_a_photo_place_is_never_the_phones_position(self):
        here = (51.5, -0.12)
        points = [NS(uid="p1", lat=here[0], lon=here[1], accuracy_m=5, source_kind="media_place", instant=T0)]
        conn = FakeConn([(("pv_location_point",), lambda p: points)])
        s = statement(start=date(2024, 3, 8), end=date(2024, 3, 8),
                      places=[{"name": "the flat", "lat": here[0], "lon": here[1], "radius_m": 200}])
        items = phones.place_items(conn, CASE, s, [("e1", "Phone 1")], {}, "UTC")
        self.assertEqual([i["relation"] for i in items], [W.POSSIBLE])
        self.assertTrue(items[0]["photo_place"])
        self.assertIn("not where the phone was", items[0]["reason"])

    def test_positions_agree_near_and_disagree_far_and_towers_are_near_not_at(self):
        here = (51.5, -0.12)
        near = [NS(uid="p1", lat=51.5005, lon=-0.12, accuracy_m=10, source_kind="device_location", instant=T0)]
        far = [NS(uid="p2", lat=52.9, lon=-1.2, accuracy_m=10, source_kind="device_location", instant=T0),
               NS(uid="p3", lat=51.505, lon=-0.12, accuracy_m=None, source_kind="other:CellTower", instant=T0)]
        s = statement(start=date(2024, 3, 8), end=date(2024, 3, 8),
                      places=[{"name": "the flat", "lat": here[0], "lon": here[1], "radius_m": 200}])
        got = phones.place_items(FakeConn([(("pv_location_point",), lambda p: near)]), CASE, s,
                                 [("e1", "Phone 1")], {}, "UTC")
        self.assertEqual(got[0]["relation"], W.AGREES)
        got = phones.place_items(FakeConn([(("pv_location_point",), lambda p: far)]), CASE, s,
                                 [("e1", "Phone 1")], {}, "UTC")
        self.assertEqual([i["relation"] for i in got], [W.DISAGREES, W.POSSIBLE])
        self.assertIn("near a place, not at it", got[1]["reason"])


class TimelineTest(unittest.TestCase):
    def test_payments_are_left_to_financial_and_reading_is_labelled(self):
        events = [{"key": "k1", "name": "Priya Halloran annual leave", "type": "Event", "date": "2024-03-11"},
                  {"key": "k2", "name": "TAMSWORTH GROCERY", "type": "Transaction", "date": "2024-03-11",
                   "summary": "PRIYA HALLORAN"}]
        s = statement(people=[S.Person(name="Priya Halloran")], start=date(2024, 3, 11), end=date(2024, 3, 11))
        out = timeline.part(FakeConn([]), CASE, s, "UTC", graph_events=lambda c, lo, hi: (events, False))
        self.assertEqual(len(out["items"]), 1)
        self.assertEqual(out["items"][0]["relation"], W.POSSIBLE)
        self.assertEqual(out["items"][0]["machine_label"], "Read by Loupe · not confirmed")
        self.assertIn("1 payment in these dates is read under Financial", out["searched"])

    def test_nothing_found_names_the_dates(self):
        s = statement(people=[S.Person(name="Nell Ashgrove")], start=date(2024, 1, 5), end=date(2024, 1, 5))
        out = timeline.part(FakeConn([]), CASE, s, "UTC", graph_events=lambda c, lo, hi: ([], False))
        self.assertEqual(out["items"][0]["relation"], W.NOTHING)
        self.assertIn("Fri 5 Jan 2024", out["items"][0]["text"])

    def test_no_date_is_said(self):
        out = timeline.part(FakeConn([]), CASE, statement(references=["2204"]), "UTC",
                            graph_events=lambda c, lo, hi: self.fail("no dates, no graph read"))
        self.assertIn("no date was given", out["searched"])


class ServiceTest(unittest.TestCase):
    def test_a_failing_part_is_said_and_the_others_still_answer(self):
        conn = FakeConn([(("financial_transactions",), lambda p: [row()])])
        orig = service.phones.part
        service.phones.part = lambda *a: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            out = service.run(conn, CASE, statement(references=["2204"]), ("phones", "financial"))
        finally:
            service.phones.part = orig
        states = {p["source"]: p["state"] for p in out["parts"]}
        self.assertEqual(states, {"phones": "failed", "financial": "done"})
        self.assertIn("could not be checked", out["parts"][0]["searched"])
        self.assertFalse(out["complete"])
        self.assertEqual(out["counts"]["agrees"], 1)

    def test_statement_needs_something_to_check(self):
        with self.assertRaises(S.BadSubject):
            S.from_statement(FakeConn([]), CASE, {})

    def test_statement_reads_amounts_and_check_numbers_from_its_text(self):
        s = S.from_statement(FakeConn([]), CASE, {"text": "Pell deposited check 2204 for $2,460.00 on 15 March"})
        self.assertEqual(s.references, ["2204"])
        self.assertEqual(s.amounts, [(246000, "USD")])


if __name__ == "__main__":
    unittest.main()
