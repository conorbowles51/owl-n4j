"""A person's stream density (07 section 4.4): Comfortable until they choose, kept for them, refused when unknown."""
from __future__ import annotations

from tests.phone_pg import needs_template
from tests.test_phone_screens_router import api  # noqa: F401 - the shared synthetic fixture

pytestmark = needs_template


def test_density_defaults_saves_and_reads_back(api):  # noqa: F811
    cl = api["client"]
    assert cl.get("/api/phones/reader-settings").json() == {"stream_density": "comfortable"}
    assert cl.put("/api/phones/reader-settings", json={"stream_density": "compact"}).json() == {"stream_density": "compact"}
    assert cl.get("/api/phones/reader-settings").json() == {"stream_density": "compact"}
    assert cl.put("/api/phones/reader-settings", json={"stream_density": "tiny"}).status_code == 422


def test_the_apps_route_counts_in_scope(api):  # noqa: F811
    r = api["client"].post("/api/phones/streams/apps", json={"case_id": api["case"]})
    assert r.status_code == 200, r.text
    got = r.json()
    assert sum(i["count"] for i in got["items"]) == got["counts"]["events"] > 0
