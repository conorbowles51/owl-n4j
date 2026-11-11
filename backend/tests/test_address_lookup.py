"""Address lookup per case: 'flag' sends nothing without a click, 'auto' sends one request per new address and stops
as soon as the case is switched to 'flag'; every placement is a machine placement marked automatic."""

import json
import os
import unittest
from threading import Event
from unittest.mock import MagicMock, patch

from services import address_lookup, geo_rescan_service

WAITING = [{"key": "a", "address": "1600 Pennsylvania Ave, Washington, DC 20500"},
           {"key": "b", "address": "10 Downing St, London"}, {"key": "c", "address": "Nowhere 99, Atlantis"}]
FOUND = [{"lat": "38.8977", "lon": "-77.0365", "importance": 0.8, "type": "house",
          "display_name": "White House, 1600, Pennsylvania Avenue Northwest, Washington, District of Columbia, 20500, "
                          "United States"}]


def _answer(payload):
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode()
    response.__enter__ = lambda self: self
    response.__exit__ = lambda self, *a: False
    return response


class AddressLookupModeTests(unittest.TestCase):
    def setUp(self):
        self.neo = MagicMock()
        self.neo.addresses_waiting.return_value = (len(WAITING), WAITING)
        self.neo.case_address_texts.return_value = [w["address"] for w in WAITING]
        for item in (
            patch("services.neo4j_service.neo4j_service", self.neo),
            patch.object(geo_rescan_service, "_rate_limit"),
            patch.object(geo_rescan_service, "_get_cached_geocode", return_value=(False, None)),
            patch.object(geo_rescan_service, "_save_geocode_cache"),
        ):
            item.start()
            self.addCleanup(item.stop)

    def _run(self, modes, answers):
        with patch.object(address_lookup, "case_mode", side_effect=[(m, m) for m in modes]), \
                patch.object(geo_rescan_service.urllib.request, "urlopen",
                             side_effect=[_answer(a) for a in answers]) as sent:
            counts = address_lookup.look_up_waiting("case-1")
        return counts, sent

    def test_flag_sends_nothing_without_a_click(self):
        counts, sent = self._run(["flag"], [])
        sent.assert_not_called()
        self.assertEqual(counts, {"stopped": 1})
        self.neo.apply_looked_up_location.assert_not_called()

    def test_auto_sends_one_request_per_new_address_and_keeps_machine_placements(self):
        counts, sent = self._run(["auto"] * 3, [FOUND, FOUND, []])
        self.assertEqual(sent.call_count, 3)
        self.assertEqual(counts, {"placed": 2, "no_match": 1})
        kwargs = self.neo.apply_looked_up_location.call_args.kwargs
        self.assertEqual(kwargs["mode"], "auto")
        self.assertEqual(kwargs["requested_by"], geo_rescan_service.AUTOMATIC)
        self.assertEqual(self.neo.record_lookup_outcome.call_args.kwargs["status"], "failed")

    def test_auto_sends_a_fragment_nowhere_and_pins_only_inside_the_cases_state(self):
        # lx-demo 10 Nov 2026: 'gate house' pinned in Norwich; 'Calder County' in Idaho for a Maryland case
        self.neo.addresses_waiting.return_value = (2, [{"key": "g", "address": "gate house"},
                                                       {"key": "k", "address": "Calder County"}])
        self.neo.case_address_texts.return_value = ["Rockville, MD 20850", "Bethesda, Maryland", "Laurel, MD"]
        idaho = [{"lat": "47.2", "lon": "-116.2", "importance": 0.5, "type": "county",
                  "display_name": "Calder, Shoshone County, Idaho, United States", "address": {"state": "Idaho"}}]
        counts, sent = self._run(["auto"] * 2, [idaho])
        self.assertEqual(sent.call_count, 1)
        self.assertIn("Calder%20County%2C%20Maryland%2C%20United%20States", sent.call_args.args[0].full_url)
        self.assertEqual(counts, {"not_a_place": 1, "outside_case_region": 1})
        self.neo.apply_looked_up_location.assert_not_called()
        self.assertEqual([c.kwargs["outcome"] for c in self.neo.record_lookup_outcome.call_args_list],
                         ["not_a_place", "outside_case_region"])

    def test_switching_to_flag_stops_at_once(self):
        counts, sent = self._run(["auto", "flag"], [FOUND])
        self.assertEqual(sent.call_count, 1)
        self.assertEqual(counts, {"placed": 1, "stopped": 1})

    def test_an_address_answered_before_is_not_sent_again_automatically(self):
        with patch.object(geo_rescan_service, "_get_cached_geocode", return_value=(True, None)), \
                patch.object(geo_rescan_service.urllib.request, "urlopen") as sent:
            self.assertIsNone(geo_rescan_service.geocode_with_cache("Nowhere", requested_by="automatic"))
        sent.assert_not_called()

    def test_a_service_that_does_not_answer_leaves_the_rest_waiting(self):
        with patch.object(address_lookup, "case_mode", return_value=("auto", "auto")), \
                patch.object(geo_rescan_service.urllib.request, "urlopen", side_effect=OSError("down")) as sent:
            counts = address_lookup.look_up_waiting("case-1")
        self.assertEqual(sent.call_count, 1)
        self.assertEqual(counts, {"unavailable": 1})
        self.neo.record_lookup_outcome.assert_not_called()

    def test_the_default_is_auto_unless_set_to_flag(self):
        with patch.dict(os.environ, {"ADDRESS_LOOKUP_DEFAULT": ""}):
            self.assertEqual(address_lookup.default_mode(), "auto")
        with patch.dict(os.environ, {"ADDRESS_LOOKUP_DEFAULT": "flag"}):
            self.assertEqual(address_lookup.default_mode(), "flag")
        with patch.dict(os.environ, {"ADDRESS_LOOKUP_DEFAULT": "nonsense"}):
            self.assertEqual(address_lookup.default_mode(), "auto")

    def test_only_one_worker_per_host_takes_the_lock(self):
        with patch.object(address_lookup, "_LOCK_PATH", os.path.join(os.environ.get("TMPDIR", "/tmp"),
                                                                     f"addr-lock-test-{os.getpid()}")):
            first = address_lookup._take_host_lock()
            try:
                self.assertIsNotNone(first)
                self.assertIsNone(address_lookup._take_host_lock())
            finally:
                first.close()
                os.unlink(address_lookup._LOCK_PATH)

    def test_a_pass_stops_when_asked(self):
        stop = Event()
        stop.set()
        with patch.object(address_lookup, "auto_case_ids", return_value=["c1", "c2"]), \
                patch.object(address_lookup, "look_up_waiting") as look:
            address_lookup.run_pass(stop)
        look.assert_not_called()


class AddressLookupPassTests(unittest.TestCase):
    def test_one_case_failing_does_not_starve_the_cases_after_it(self):
        with patch.object(address_lookup, "auto_case_ids", return_value=["bad", "good"]), \
                patch.object(address_lookup, "look_up_waiting",
                             side_effect=[RuntimeError("bad node"), {"placed": 2}]) as look:
            totals = address_lookup.run_pass(Event())
        self.assertEqual(look.call_count, 2)
        self.assertEqual(totals, {"case_failed": 1, "placed": 2})

    def test_waiting_addresses_are_the_ones_needs_review_lists(self):
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / "services/neo4j/graph_edit_service.py").read_text()
        body = source[source.index("def addresses_waiting"):source.index("def apply_looked_up_location")]
        self.assertIn("'Document', 'RecycleBin', 'RecycleBinItem'", body)
        self.assertIn("system_node", body)
        self.assertIn("WHEN trim(coalesce(n.location_raw, '')) <> '' THEN n.location_raw", body)

    def test_the_address_sent_falls_back_from_a_blank_evidence_address(self):
        from services.neo4j.graph_edit_service import GraphEditService

        self.assertEqual(GraphEditService.lookup_address({"location_raw": " ", "geocoding_query": "10 Downing St"}),
                         "10 Downing St")
        self.assertEqual(GraphEditService.lookup_address({"location_raw": "1 Main St", "geocoding_query": "x"}),
                         "1 Main St")


class AddressLookupSettingTests(unittest.TestCase):
    def test_only_known_modes_are_accepted(self):
        from routers.cases import AddressLookupModeRequest

        self.assertEqual(AddressLookupModeRequest(mode="flag").mode, "flag")
        self.assertIsNone(AddressLookupModeRequest(mode=None).mode)
        with self.assertRaises(Exception):
            AddressLookupModeRequest(mode="sometimes")

    def test_changing_the_mode_needs_the_owners_permission(self):
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / "routers/cases.py").read_text()
        body = source[source.index("def set_address_lookup_mode"):]
        self.assertIn('required_permission=("case", "delete")', body.split("def ", 2)[1])


if __name__ == "__main__":
    unittest.main()
