"""Where phones were together (lx-phonetogether B, D): merging, wording, validation. Pure; no database."""
import unittest
from unittest import mock

from services.relations import together as T

A, B = "a" * 8 + "-0000-0000-0000-000000000000", "b" * 8 + "-0000-0000-0000-000000000000"


def cell(bin_, sq=(1, 2), readings=2, acc=(6.0,), src=("device_location",), ua=("u1",), ub=("u2",)):
    return {"a": A, "b": B, "bin": bin_, "sq": sq, "lat": 39.1, "lon": -76.1, "readings": readings,
            "acc": list(acc), "src": list(src), "uids_a": list(ua), "uids_b": list(ub)}


class Merge(unittest.TestCase):
    def test_cells_in_one_evening_are_one_meeting(self):
        base = 1_700_000_000 // T.SLOT_S
        m = T._merge([cell(base), cell(base + 4), cell(base + 8)])  # an hour apart each
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0]["cells"], 3)
        self.assertEqual(m[0]["readings"], 6)

    def test_a_long_gap_or_another_square_is_another_meeting(self):
        base = 1_700_000_000 // T.SLOT_S
        m = T._merge([cell(base), cell(base + 100), cell(base, sq=(9, 9))])
        self.assertEqual(len(m), 3)

    def test_record_ids_are_each_listed_once_with_totals(self):
        base = 1_700_000_000 // T.SLOT_S
        m = T._merge([cell(base, ua=("u1", "u2")), cell(base + 1, ua=("u2", "u3"))])[0]
        self.assertEqual(m["records"][A], ["u1", "u2", "u3"])
        self.assertEqual(m["records_total"][A], 3)

    def test_precision_says_when_no_accuracy_is_stated(self):
        m = T._merge([cell(1_700_000_000 // T.SLOT_S, acc=())])[0]
        self.assertFalse(m["precision"]["accuracy_stated"])
        self.assertEqual(m["precision"]["level"], "coarse")

    def test_meeting_ids_are_stable(self):
        c = [cell(1_700_000_000 // T.SLOT_S)]
        self.assertEqual(T._merge(c)[0]["id"], T._merge(c)[0]["id"])


class FakeDb:
    def connection(self):
        return object()


class Read(unittest.TestCase):
    def run_read(self, phones, meetings=(), raw=(), **kw):
        with mock.patch("services.phone_analysis.fields.active_phones", return_value={A: "Phone 1", B: "Phone 2"}), \
             mock.patch.object(T, "cells", return_value=(list(raw), {"positions": 10, "with_time": 8})), \
             mock.patch.object(T, "_merge", return_value=list(meetings)), \
             mock.patch.object(T, "shared_contacts", return_value=([], {"records": 5})) as sc, \
             mock.patch.object(T, "relay_chains", return_value=([], {"events": 7})) as rc, \
             mock.patch.object(T, "pair_days", return_value={"days_together": 0, "days_both_active": 3}):
            self.calls = (sc, rc)
            return T.read(FakeDb(), "c", phones, **kw)

    def test_no_meeting_is_a_sentence_with_what_was_searched(self):
        out = self.run_read([A, B])
        self.assertTrue(out["message"].startswith("No meeting found in 8 timed positions"))
        self.assertIn("same 15-minute slot", out["message"])
        self.assertIn("No relay chain found in 7 contacts", out["relay_message"])
        self.assertEqual(out["pairs"][0]["days_both_active"], 3)
        self.assertTrue(out["searched"])
        self.assertTrue(any("no time" in x for x in out["out_of_reach"]))

    def test_one_phone_unknown_phone_and_bad_dates_are_refused(self):
        with self.assertRaises(T.TogetherError):
            self.run_read([A])
        with self.assertRaises(T.TogetherError):
            self.run_read([A, "zzzzzzzz-0000-0000-0000-000000000000"])
        with self.assertRaises(T.TogetherError):
            self.run_read([A, B], start="2024-02-01", end="2024-01-01")
        with self.assertRaises(T.TogetherError):
            self.run_read([A, B], start="not a date")

    def test_a_part_not_asked_for_is_not_read_and_not_reported_as_none(self):
        out = self.run_read([A, B], parts=["places"])
        self.assertEqual([c.call_count for c in self.calls], [0, 0])
        self.assertIsNone(out["contacts_message"])
        self.assertEqual(out["parts"], ["places"])
        with self.assertRaises(T.TogetherError):
            self.run_read([A, B], parts=["places", "nonsense"])

    def test_a_last_day_given_as_a_date_is_the_whole_day(self):
        end = T._parse("2024-06-08", "to")
        self.assertEqual((end.hour, end.minute), (23, 59))
        self.assertEqual(T._parse("2024-06-08", "from").hour, 0)

    def test_route_is_registered(self):
        from routers import relation_queries
        self.assertIn("/api/cases/{case_id}/relation-overlaps", [r.path for r in relation_queries.router.routes])


if __name__ == "__main__":
    unittest.main()
