"""Nothing about a case goes to an outside map service.

Addresses from evidence are looked up only by a geocoder held on this server; with none configured nothing is sent,
an address looked up before is still placed from the cache, and the person is told the address was not placed.
The base map files nginx serves under /basemap/ are behind the app's sign-in: nginx asks /api/auth/check first.
"""

import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import auth, graph
from services import geo_rescan_service

ROOT = Path(__file__).resolve().parents[2]


class GeocodingStaysOnThisServerTests(unittest.TestCase):
    def test_only_a_geocoder_on_this_server_counts(self):
        held = geo_rescan_service.held_on_this_server
        self.assertTrue(held("http://localhost:8080/search"))
        self.assertTrue(held("http://127.0.0.1:8080/search"))
        self.assertTrue(held("http://nominatim:8080/search"))
        self.assertFalse(held("https://nominatim.openstreetmap.org/search"))
        self.assertFalse(held("http://8.8.8.8/search"))
        self.assertFalse(held(""))

    def test_no_address_is_sent_with_no_geocoder_here(self):
        for url in ("", "https://nominatim.openstreetmap.org/search"):
            with self.subTest(url=url), \
                    patch.object(geo_rescan_service, "NOMINATIM_URL", url), \
                    patch.object(geo_rescan_service, "_get_cached_geocode", return_value=(False, None)), \
                    patch.object(geo_rescan_service, "_save_geocode_cache") as save, \
                    patch.object(geo_rescan_service.urllib.request, "urlopen",
                                 side_effect=AssertionError("an address was sent off this server")) as sent:
                self.assertIsNone(geo_rescan_service.geocode_with_cache("1600 Pennsylvania Ave NW, Washington DC"))
                sent.assert_not_called()
                save.assert_not_called()  # a lookup never made is not cached as failed

    def test_an_address_looked_up_before_is_still_placed_from_the_cache(self):
        cached = {"provider": "nominatim", "latitude": 51.5, "longitude": -0.12, "formatted_address": "London",
                  "confidence": "high"}
        with patch.object(geo_rescan_service, "NOMINATIM_URL", ""), \
                patch.object(geo_rescan_service, "_get_cached_geocode", return_value=(True, cached)), \
                patch.object(geo_rescan_service.urllib.request, "urlopen") as sent:
            self.assertEqual(geo_rescan_service.geocode_with_cache("London")["latitude"], 51.5)
            sent.assert_not_called()

    def test_the_address_box_says_the_address_was_not_placed(self):
        with patch.object(geo_rescan_service, "NOMINATIM_URL", ""), \
                patch.object(geo_rescan_service, "_get_cached_geocode", return_value=(False, None)), \
                patch.object(geo_rescan_service.urllib.request, "urlopen") as sent:
            result = graph.geocode_node("loc-1", graph.GeocodeNodeRequest(case_id="case-1", address="12 Main St"),
                                        apply=True, user={"username": "investigator"})
        sent.assert_not_called()
        self.assertFalse(result["success"])
        self.assertTrue(result["not_run"])
        self.assertEqual(result["error"], "Address not placed: geocoding is not run on this server.")

    def test_no_public_geocoder_is_named_as_a_default(self):
        for path in ("backend/services/geo_rescan_service.py", "evidence-engine/app/config.py"):
            with self.subTest(path=path):
                self.assertNotIn("nominatim.openstreetmap.org", (ROOT / path).read_text())


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
