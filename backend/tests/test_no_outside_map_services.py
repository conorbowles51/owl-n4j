"""Nothing about a case goes to an outside map service unless a person asks for it.

Addresses from evidence are sent to the outside address service only when a person clicks Look up (one request per
address clicked); automatic paths send nothing and leave the address flagged; an address looked up before is still
placed from the cache. A looked-up pin is a machine placement (who asked, when) until a person confirms it.
The base map files nginx serves under /basemap/ are behind the app's sign-in: nginx asks /api/auth/check first.
"""

import io
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import auth, graph
from services import geo_rescan_service

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = "https://nominatim.openstreetmap.org/search"
WHITE_HOUSE = [{"lat": "38.8977", "lon": "-77.0365", "display_name": "White House, Washington DC",
                "importance": 0.8, "type": "house", "address": {"house_number": "1600"}}]


def _answer(payload):
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode()
    response.__enter__ = lambda self: self
    response.__exit__ = lambda self, *a: False
    return response


class GeocodingSendsOnlyWhenAPersonAsksTests(unittest.TestCase):
    def setUp(self):
        patches = [
            patch.object(geo_rescan_service, "_rate_limit"),
            patch.object(geo_rescan_service, "_get_cached_geocode", return_value=(False, None)),
            patch.object(geo_rescan_service, "_save_geocode_cache"),
        ]
        self.save = None
        for item in patches:
            started = item.start()
            self.addCleanup(item.stop)
            if item.attribute == "_save_geocode_cache":
                self.save = started

    def test_only_a_geocoder_on_this_server_counts(self):
        held = geo_rescan_service.held_on_this_server
        self.assertTrue(held("http://localhost:8080/search"))
        self.assertTrue(held("http://127.0.0.1:8080/search"))
        self.assertTrue(held("http://nominatim:8080/search"))
        self.assertFalse(held(PUBLIC))
        self.assertFalse(held("http://8.8.8.8/search"))
        self.assertFalse(held(""))

    def test_no_address_is_sent_without_a_person_asking(self):
        with patch.object(geo_rescan_service, "NOMINATIM_URL", PUBLIC), \
                patch.object(geo_rescan_service.urllib.request, "urlopen",
                             side_effect=AssertionError("an address was sent without a click")) as sent:
            self.assertIsNone(geo_rescan_service.geocode_with_cache("1600 Pennsylvania Ave NW, Washington DC"))
        sent.assert_not_called()
        self.save.assert_not_called()  # a lookup never made is not cached as failed

    def test_the_case_rescan_sends_no_address(self):
        """The rescan is automatic (one click finds and places many places); it may not send addresses."""
        source = (ROOT / "backend/services/geo_rescan_service.py").read_text()
        rescan = source[source.index("def rescan_case_locations"):]
        self.assertIn("geocode_with_cache(place)", rescan)
        self.assertNotIn("requested_by", rescan.split("def ", 2)[1])

    def test_one_request_per_click(self):
        with patch.object(geo_rescan_service, "NOMINATIM_URL", PUBLIC), \
                patch.object(geo_rescan_service.urllib.request, "urlopen", return_value=_answer(WHITE_HOUSE)) as sent:
            result = geo_rescan_service.geocode_with_cache("1600 Pennsylvania Ave", requested_by="investigator")
        self.assertEqual(sent.call_count, 1)
        request = sent.call_args.args[0]
        self.assertTrue(request.full_url.startswith(PUBLIC + "?q=1600%20Pennsylvania%20Ave"))
        self.assertNotIn("@", request.get_header("User-agent"))  # no personal contact details
        self.assertEqual(result["latitude"], 38.8977)
        self.assertEqual(self.save.call_args.kwargs["requested_by"], "investigator")

    def test_a_click_asks_again_after_an_earlier_failure_but_uses_a_cached_success(self):
        with patch.object(geo_rescan_service, "_get_cached_geocode", return_value=(True, None)), \
                patch.object(geo_rescan_service.urllib.request, "urlopen", return_value=_answer([])) as sent:
            self.assertIsNone(geo_rescan_service.geocode_with_cache("Nowhere", requested_by="investigator"))
            self.assertIsNone(geo_rescan_service.geocode_with_cache("Nowhere"))
        self.assertEqual(sent.call_count, 1)
        cached = {"provider": "nominatim", "latitude": 51.5, "longitude": -0.12, "formatted_address": "London",
                  "confidence": "high"}
        with patch.object(geo_rescan_service, "_get_cached_geocode", return_value=(True, cached)), \
                patch.object(geo_rescan_service.urllib.request, "urlopen") as sent:
            self.assertEqual(geo_rescan_service.geocode_with_cache("London")["latitude"], 51.5)
            self.assertEqual(geo_rescan_service.geocode_with_cache("London", requested_by="p")["latitude"], 51.5)
        sent.assert_not_called()

    def test_a_service_that_does_not_answer_is_said_and_not_cached_as_no_match(self):
        with patch.object(geo_rescan_service.urllib.request, "urlopen", side_effect=OSError("timed out")):
            with self.assertRaises(geo_rescan_service.GeocoderUnavailable):
                geo_rescan_service.geocode_with_cache("12 Main St", requested_by="investigator")
        self.save.assert_not_called()

    def test_the_address_box_sends_on_its_button_and_says_no_match(self):
        with patch.object(geo_rescan_service.urllib.request, "urlopen", return_value=_answer([])) as sent:
            result = graph.geocode_node("loc-1", graph.GeocodeNodeRequest(case_id="case-1", address="12 Main St"),
                                        apply=False, user={"username": "investigator"})
        self.assertEqual(sent.call_count, 1)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "No match found for this address.")


class LookUpFlaggedAddressesTests(unittest.TestCase):
    """The map's Look up / Look up all actions."""

    def _node(self, **props):
        base = {"location_raw": "1600 Pennsylvania Ave", "geocoding_status": "failed"}
        base.update(props)
        return {"labels": ["Location"], "category": "Location", "properties": base}

    def _run(self, keys, nodes, answer):
        neo = MagicMock()
        from services.neo4j.graph_edit_service import GraphEditService
        real = GraphEditService.__new__(GraphEditService)
        real._fetch_node = lambda key, case_id: nodes.get(key)
        neo.flagged_address.side_effect = real.flagged_address
        neo.apply_looked_up_location.side_effect = lambda key, **kw: {
            "latitude": kw["result"]["latitude"], "longitude": kw["result"]["longitude"],
            "geocoding_formatted_address": kw["result"]["formatted_address"], "geocoding_requested_at": "now"}
        with patch.object(graph, "neo4j_service", neo), \
                patch.object(graph, "system_log_service"), \
                patch.object(geo_rescan_service, "_rate_limit"), \
                patch.object(geo_rescan_service, "_get_cached_geocode", return_value=(False, None)), \
                patch.object(geo_rescan_service, "_save_geocode_cache"), \
                patch.object(geo_rescan_service.urllib.request, "urlopen", return_value=_answer(answer)) as sent:
            out = graph.look_up_flagged_addresses(graph.LookupFlaggedRequest(case_id="c", node_keys=keys),
                                                  user={"username": "investigator", "name": "Ann Investigator"})
        return out, sent, neo

    def test_each_flagged_address_clicked_is_sent_once_and_kept_as_a_machine_placement(self):
        nodes = {"a": self._node(), "b": self._node(location_raw="10 Downing St", geocoding_status="ambiguous")}
        out, sent, neo = self._run(["a", "b", "a"], nodes, WHITE_HOUSE)
        self.assertEqual(sent.call_count, 2)
        self.assertEqual(out["counts"], {"placed": 2})
        kwargs = neo.apply_looked_up_location.call_args_list[0].kwargs
        self.assertEqual(kwargs["requested_by"], "investigator")
        self.assertEqual(kwargs["requested_by_name"], "Ann Investigator")
        self.assertIn("nominatim.openstreetmap.org", kwargs["service"])

    def test_nothing_is_sent_for_a_pin_a_person_placed_or_an_unflagged_node(self):
        nodes = {
            "manual": self._node(manual_fields=["latitude", "longitude"]),
            "pinned": self._node(latitude=1.0, longitude=2.0),
            "fine": self._node(geocoding_status="success"),
            "empty": self._node(location_raw=" "),
        }
        out, sent, neo = self._run(list(nodes) + ["missing"], nodes, WHITE_HOUSE)
        sent.assert_not_called()
        self.assertEqual(out["counts"], {"skipped": 5})
        neo.apply_looked_up_location.assert_not_called()

    def test_no_match_is_said_and_recorded(self):
        out, sent, neo = self._run(["a"], {"a": self._node()}, [])
        self.assertEqual(out["results"][0]["outcome"], "no_match")
        self.assertEqual(out["results"][0]["message"], "No match found for this address.")
        self.assertEqual(neo.record_lookup_outcome.call_args.kwargs["outcome"], "no_match")
        neo.apply_looked_up_location.assert_not_called()

    def test_at_most_ten_addresses_per_request(self):
        with self.assertRaises(Exception):
            graph.LookupFlaggedRequest(case_id="c", node_keys=[str(i) for i in range(11)])

    def test_the_machine_placement_keeps_the_evidence_address_and_no_manual_field(self):
        source = (ROOT / "backend/services/neo4j/graph_edit_service.py").read_text()
        body = source[source.index("def apply_looked_up_location"):source.index("def record_lookup_outcome")]
        self.assertNotIn("manual_fields =", body.replace("NONE(field IN coalesce(n.manual_fields", ""))
        self.assertNotIn('"location_raw"', body)
        self.assertNotIn('"location_formatted"', body)
        self.assertIn('"geocoding_requested_by"', body)

class BasemapSignInCheckTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(auth.router)
        self.client = TestClient(self.app)

    def test_signed_out_is_refused(self):
        self.assertEqual(self.client.get("/api/auth/check").status_code, 401)

    def test_signed_in_gets_an_empty_yes(self):
        self.app.dependency_overrides[auth.get_current_user] = lambda: {"username": "p@example.com"}
        response = self.client.get("/api/auth/check")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")

    def test_nginx_serves_the_base_map_only_after_the_sign_in_check(self):
        site = (ROOT / "deploy/nginx-loupe-frontend.conf").read_text()
        block = site[site.index("location /basemap/"):]
        block = block[:block.index("}")]
        self.assertIn("auth_request /basemap-sign-in;", block)
        self.assertIn("alias @BASEMAP@/;", block)
        self.assertIn("gzip off;", block)
        check = site[site.index("location = /basemap-sign-in"):]
        check = check[:check.index("}")]
        self.assertIn("internal;", check)
        self.assertIn("proxy_pass http://@API@/api/auth/check;", check)


if __name__ == "__main__":
    unittest.main()
