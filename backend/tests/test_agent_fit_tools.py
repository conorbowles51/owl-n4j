"""lx-agentfit C, D and F: tools that work out on request what waited for a person, question-shaped tools built from
the simple ones, and testing the other side of a factual question. Each test fails on the code before this change.

Measured 11 Nov 2026 on the demo case: get_day_activity refused 4 times ("No phone in this case is linked to this
person yet"); the Q1 answer never compared the glovebox phone with the other phones; Money on the phones' stored run
held 0 readings where its own code on the case's current inputs gives 27."""
import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from services.agent import fit, phone_cross_tools as PC, question_scope as QS, question_tools as QT

CASE = "00000000-0000-0000-0000-0000000000ac"


_ENV = patch.dict(os.environ, {fit.SETTING: "B,C,D,F"})


def setUpModule():
    _ENV.start()


def tearDownModule():
    _ENV.stop()


class SwitchTests(unittest.TestCase):
    def test_items_are_off_by_default_until_measured_and_each_can_be_turned_on(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(fit.SETTING, None)
            self.assertFalse(any(fit.on(i) for i in fit.ITEMS))
            self.assertIn("record_working_notes", fit.hidden_tools())
        with patch.dict(os.environ, {fit.SETTING: "B,F"}):
            self.assertFalse(fit.on("D"))
            self.assertIn("check_statements", fit.hidden_tools())
            self.assertIn("get_phone_company", fit.hidden_tools())
            self.assertNotIn("record_working_notes", fit.hidden_tools())


class OtherSideTests(unittest.TestCase):
    def test_a_factual_question_is_told_to_test_the_other_side(self):
        q = "Where was the phone found in the glovebox between 23 May and 7 June 2024, and whose phone was it with?"
        self.assertIn(QS.TEST_OTHER_SIDE, QS.block(QS.build(q), planning=True, question=q))
        # the final answer's block never carries it (the finalizer has no tools)
        self.assertNotIn(QS.TEST_OTHER_SIDE, QS.block(QS.build(q)))

    def test_build_and_update_requests_are_not(self):
        for q in ("Rebuild the graph at account level and update report", "revise the graph, A and B are the same",
                  "podes crear un diagrama que demuestre el movimiento del dinero?",
                  "What payments did Lena Marsh receive, and from whom?"):
            self.assertNotIn(QS.TEST_OTHER_SIDE, QS.block(QS.build(q), planning=True, question=q), q)

    def test_switched_off_it_is_not_asked(self):
        q = "Did Mateo Ruiz ever call Desmond Okafor?"
        with patch.dict(os.environ, {fit.SETTING: "B"}):
            self.assertNotIn(QS.TEST_OTHER_SIDE, QS.block(QS.build(q), planning=True, question=q))


class CheckStatementsTests(unittest.TestCase):
    def run_check(self, statements, items):
        calls = []

        def search_all(tools, exp, census, files):
            calls.append(exp)
            return list(items), {"ledger": {"reachable": True}, "phones": {"reachable": False, "reason": "No phone."}}
        with patch("services.agent.disconfirm.Tools", lambda case_id: SimpleNamespace(call=lambda *a, **k: {})), \
                patch("services.agent.disconfirm._census", lambda *a: {"phones": 0}), \
                patch("services.agent.disconfirm.case_files", lambda *a: {}), \
                patch("services.agent.disconfirm.search_all", search_all):
            return QT.check_statements(None, CASE, statements), calls

    def test_each_statement_is_searched_on_every_surface_with_ranked_cited_candidates(self):
        items = [dict(cite="txn://t%d" % i, surface="ledger", text="payment %d" % i) for i in range(40)]
        items.insert(20, dict(cite="doc://d/1", surface="documents", text="storage unit 212 rented by Brianna Cole"))
        out, calls = self.run_check([{"claim": "Brianna Cole rented storage unit 212", "people": ["Brianna Cole"],
                                      "terms": ["212"]},
                                     {"claim": "Kell never used the unit", "terms": ["storage"], "start": "2024-05-01"}],
                                    items)
        self.assertEqual([c["id"] for c in calls], ["S1", "S2"])
        self.assertEqual(calls[1]["start"], "2024-05-01")
        first = out["statements"][0]
        self.assertEqual(first["candidates"][0]["cite"], "doc://d/1")  # ranked by the statement's words
        self.assertEqual(first["candidates_found"], 41)
        self.assertEqual(first["candidates_shown"], QT.MAX_CANDIDATES)
        self.assertIn("11 more candidates", first["not_shown"])  # counted, never silently cut
        self.assertFalse(first["coverage"]["phones"]["reachable"])
        self.assertIn("your reading", out["label"])

    def test_a_statement_with_nothing_to_search_is_refused(self):
        with self.assertRaises(ValueError):
            self.run_check([{"claim": "Something happened"}], [])
        with self.assertRaises(ValueError):
            self.run_check([{"claim": "x", "terms": ["a"]}] * (QT.MAX_STATEMENTS + 1), [])

    def test_a_search_past_its_pages_keeps_its_total_and_is_counted(self):
        with patch("services.agent.disconfirm.Tools") as tools:
            tools.return_value.call.side_effect = lambda name, **kw: {"has_more": True, "total_matching": 900}
            bounded = QT._BoundedTools(CASE)
            self.assertTrue(bounded.call("phone_messages", offset=0)["has_more"])
            last = bounded.call("phone_messages", offset=100 * (QT.MAX_PAGES - 1))
        self.assertFalse(last["has_more"])
        self.assertEqual(last["total_matching"], 900)
        self.assertEqual(bounded.cut, 1)


class SuggestedPhoneTests(unittest.TestCase):
    def test_a_person_with_no_linked_phone_is_read_through_a_graded_suggestion(self):
        dossier = SimpleNamespace(id="d1", display_name="Mateo Ruiz")
        suggestion = [{"extraction_ids": ["e1"], "phones": ["Phone 1"], "strength": "moderate",
                       "reasons": ["a contact detail on this person's dossier", "the same name"]}]
        with patch.object(PC, "_dossier", lambda *a: dossier), \
                patch("services.pattern_of_life.subjects.resolve",
                      lambda *a: {"subject": {"kind": "dossier", "dossier_id": "d1"}, "extraction_ids": [],
                                  "name": None}), \
                patch.object(PC, "suggested_phones", lambda *a: suggestion):
            r = PC._subject(None, CASE, person="Mateo Ruiz")
        self.assertEqual(r["extraction_ids"], ["e1"])
        link = r["subject"]["link"]
        self.assertEqual(link["strength"], "moderate")
        self.assertIn("No person has linked a phone to Mateo Ruiz", link["words"])
        self.assertIn("a person decides on People", link["words"])

    def test_without_a_suggestion_it_still_says_why_it_cannot_read(self):
        with patch.object(PC, "_dossier", lambda *a: SimpleNamespace(id="d1", display_name="Ann")), \
                patch("services.pattern_of_life.subjects.resolve",
                      lambda *a: {"subject": {"kind": "dossier", "dossier_id": "d1"}, "extraction_ids": []}), \
                patch.object(PC, "suggested_phones", lambda *a: []):
            with self.assertRaises(ValueError) as caught:
                PC._subject(None, CASE, person="Ann")
        self.assertIn("no identity suggestion", str(caught.exception))


class PhoneCompanyTests(unittest.TestCase):
    def test_nights_run_from_six_in_the_evening_and_take_the_evening_date(self):
        z = ZoneInfo("America/New_York")
        at = lambda h, d=12: datetime(2024, 4, d, h, 30, tzinfo=z).astimezone(timezone.utc)  # noqa: E731
        self.assertEqual(PC._night_or_day(at(23), z), ("night", datetime(2024, 4, 12).date()))
        self.assertEqual(PC._night_or_day(at(2, 13), z), ("night", datetime(2024, 4, 12).date()))
        self.assertEqual(PC._night_or_day(at(12), z), ("day", datetime(2024, 4, 12).date()))


class ComputedResultsTests(unittest.TestCase):
    def test_a_computation_past_its_bound_returns_nothing_partial(self):
        class Slow:
            PARAMETERS = {}

            @staticmethod
            def run(conn, case_id, params, ctx):
                ctx.until = 0  # the bound has passed
                return [{"kind": "co_location"}] if not ctx.cancelled() else [{"kind": "partial"}]

        class Conn:
            def begin_nested(self):
                return self

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, *a, **k):
                return None
        with patch("services.phone_analysis.framework.approach", lambda code: Slow), \
                patch("services.phone_analysis.approaches.install", lambda: None):
            results, reason = PC.computed_results(Conn(), CASE, "device_users")
        self.assertIsNone(results)
        self.assertIn("nothing partial is shown", reason)


if __name__ == "__main__":
    unittest.main()
