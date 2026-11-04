"""07 section 6 (Save this view): a saved phone view is a Workspace note holding one ``phone_view`` link; opening it
re-runs the filter live and states the count then and now. Synthetic phones only."""
from __future__ import annotations

from sqlalchemy import text

from tests.phone_pg import needs_template
from tests.phone_streams_fixture import at, phone
from tests.test_phone_screens_router import ANA, OWNER, api, msg  # noqa: F401 - the shared synthetic fixture

pytestmark = needs_template


def test_save_this_view_makes_a_note_and_reopens_live_with_the_count_then_and_now(api):  # noqa: F811
    cl, case, ext = api["client"], api["case"], api["ext"]
    f = {"case_id": case, "phones": [ext]}
    shown = cl.post("/api/phones/streams/index", json=f).json()
    loc = "/cases/%s/phones/%s/records/conversations?thread=t" % (case, ext)
    r = cl.post("/api/phones/views", json={"filter": f, "location": loc, "words": "Messages on C3"})
    assert r.status_code == 200, r.text
    saved = r.json()
    total = sum(d["count"] for d in shown["items"]) + shown["no_time_count"]
    assert saved["event_count"] == total == 3
    with api["engine"].connect() as c:
        links = c.execute(text(
            "SELECT l.target_type, l.target_id, e.entry_type, e.body FROM workspace_entry_links l JOIN workspace_entries e "
            "ON e.id = l.entry_id WHERE l.entry_id = CAST(:e AS uuid)"), {"e": saved["entry_id"]}).fetchall()
    assert [(x.target_type, x.target_id, x.entry_type) for x in links] == [("phone_view", saved["id"], "note")]
    assert "It listed 3 messages when saved" in links[0].body
    d = cl.get("/api/phones/views/%s" % saved["id"], params={"case_id": case}).json()
    assert (d["event_count_then"], d["event_count_now"], d["location"], d["replaced"]) == (3, 3, loc, None)
    # new phones arrive: a whole-case view is re-run live, the count when saved stays
    with api["engine"].begin() as c:
        phone(c, case, label="C8", events=[msg(at(2023, 3, 16), ANA, [OWNER], thread="t")])
    whole = cl.post("/api/phones/views", json={"filter": {"case_id": case}, "location": "/cases/%s/conversations" % case,
                                               "words": "Every message"}).json()
    with api["engine"].begin() as c:
        phone(c, case, label="C7", events=[msg(at(2023, 3, 17), ANA, [OWNER], thread="t2"), msg(at(2023, 3, 18), ANA, [OWNER])])
    again = cl.get("/api/phones/views/%s" % whole["id"], params={"case_id": case}).json()
    assert again["event_count_now"] == again["event_count_then"] + 2
    assert again["sentence"].startswith('Saved view "Every message": %d messages when saved on ' % again["event_count_then"])
    assert again["sentence"].endswith("; %d now." % again["event_count_now"])
    # another case sees nothing, a screen of another case is refused
    from sqlalchemy.orm import Session
    from services.phone import views
    with Session(api["engine"]) as db:
        assert views.describe(db, api["other_case"], saved["id"]) is None
    assert cl.get("/api/phones/views/%s" % saved["id"], params={"case_id": api["other_case"]}).status_code in (403, 404)
    bad = cl.post("/api/phones/views", json={"filter": f, "location": "/cases/%s/conversations" % api["other_case"]})
    assert bad.status_code == 422
