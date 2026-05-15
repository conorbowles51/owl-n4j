import unittest

from routers.cellebrite import router


class CellebriteRouterTests(unittest.TestCase):
    def test_expected_route_surface_is_registered(self):
        routes = {
            (next(iter(route.methods - {"HEAD", "OPTIONS"})), route.path)
            for route in router.routes
            if getattr(route, "methods", None)
        }
        paths = {path for _, path in routes}

        expected_paths = {
            "/api/cellebrite/reports",
            "/api/cellebrite/geocoder/status",
            "/api/cellebrite/reports/{report_key}",
            "/api/cellebrite/cross-phone-graph",
            "/api/cellebrite/timeline",
            "/api/cellebrite/communication-network",
            "/api/cellebrite/comms/entities",
            "/api/cellebrite/comms/source-apps",
            "/api/cellebrite/comms/threads",
            "/api/cellebrite/comms/threads/{thread_id:path}",
            "/api/cellebrite/comms/between",
            "/api/cellebrite/comms/envelope",
            "/api/cellebrite/comms/messages/search",
            "/api/cellebrite/comms/attachment/{file_id}",
            "/api/cellebrite/events",
            "/api/cellebrite/events/types",
            "/api/cellebrite/events/tracks",
            "/api/cellebrite/locations/tiles",
            "/api/cellebrite/locations/in-tile",
            "/api/cellebrite/events/detail/{node_key}",
            "/api/cellebrite/events/{node_key}/related",
            "/api/cellebrite/intersections/run",
            "/api/cellebrite/files",
            "/api/cellebrite/files/tree",
            "/api/cellebrite/overview/contacts",
            "/api/cellebrite/contacts/unified",
            "/api/cellebrite/overview/calls",
            "/api/cellebrite/overview/messages",
            "/api/cellebrite/overview/locations",
            "/api/cellebrite/overview/emails",
            "/api/cellebrite/overview/contact/{contact_key}",
            "/api/cellebrite/comms/contact-feed/{contact_key}",
        }

        self.assertTrue(expected_paths.issubset(paths))
        self.assertIn(("DELETE", "/api/cellebrite/reports/{report_key}"), routes)
        self.assertIn(("PATCH", "/api/cellebrite/reports/{report_key}"), routes)


if __name__ == "__main__":
    unittest.main()
