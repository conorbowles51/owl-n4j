"""Key dates and case terms as Workspace entries (04 section 8.6). Opt-in PostgreSQL."""
from __future__ import annotations

from sqlalchemy import text

from tests.phone_pg import fresh_engine, make_case, needs_template


@needs_template
def test_a_key_date_is_one_workspace_note_with_its_instant_and_zone_and_goes_with_the_note():
    from tests.pattern_pg import api_client
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
        with api_client(engine, case) as client:
            r = client.post("/api/pattern/%s/key-dates" % case, json={
                "kind": "date", "label": "Synthetic incident", "instant": "2024-05-03T01:52:00-04:00",
                "zone": "America/New_York"})
            assert r.status_code == 200, r.text
            k = r.json()
            assert k["instant_utc"].startswith("2024-05-03T05:52:00") and k["local"].startswith("2024-05-03T01:52:00-04:00")
            term = client.post("/api/pattern/%s/key-dates" % case, json={
                "kind": "term", "label": "Meeting word", "term": "the usual place"}).json()
            assert term["term"] == "the usual place" and term["instant_utc"] is None
            # refused shapes leave nothing behind
            assert client.post("/api/pattern/%s/key-dates" % case, json={
                "kind": "date", "label": "No zone", "instant": "2024-05-03T01:52:00Z"}).status_code == 400
            assert client.post("/api/pattern/%s/key-dates" % case, json={
                "kind": "date", "label": "Bad zone", "instant": "2024-05-03T01:52:00Z", "zone": "Mars/Base"}).status_code == 400
            with engine.connect() as c:
                notes = c.execute(text("SELECT entry_type, title, tags FROM workspace_entries WHERE case_id = :c "
                                       "ORDER BY title"), {"c": case}).fetchall()
            assert [(n[0], n[1]) for n in notes] == [("note", "Case term: Meeting word"),
                                                      ("note", "Key date: Synthetic incident")]
            listed = client.get("/api/pattern/%s/key-dates" % case).json()
            assert listed["total"] == 2 and [i["kind"] for i in listed["items"]] == ["date", "term"]
            with engine.begin() as c:
                c.execute(text("UPDATE workspace_entries SET deleted_at = now() WHERE id = :e"), {"e": k["entry_id"]})
            after = client.get("/api/pattern/%s/key-dates" % case, params={"kind": "date"}).json()
            assert after["total"] == 0
