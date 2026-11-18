"""Who overlaps with whom (lx-overlapviews-a) on an invented case: a copy on both phones counts once (calls too),
group messages are contact, photo places never place two people together, Worth a look lists pairs linked around
each other, the go-between panel finds the order its lines follow, and levels come only from saved leads."""
import json
import sys
import types
from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import corroborate_overlaps
from routers.case_access import require_case_view
from services.corroborate import overlaps as O
from services.corroborate.store import contact_dup_key

UTC = timezone.utc
NIGHTS = [date(2025, 3, 7) + timedelta(days=7 * n) for n in range(4)]
YARD = (51.5, -0.1)


def at(d, h, m=0):
    return datetime(d.year, d.month, d.day, h, m, tzinfo=UTC)


def person(key, label, number, phones, dossier=True):
    return {"key": key, "label": label, "dossier_id": key if dossier else None, "numbers": {number}, "handles": set(),
            "emails": set(), "accounts": [], "phones": list(phones), "names": [label] if dossier else [], "links": []}


PEOPLE = [person("ann", "Ann Arden", "15550001", ["phA"]),
          person("bob", "Bob Brook", "15550002", ["phB"]),
          person("cat", "Cat Crane", "15550003", ["phC"]),
          person("hub", "Hal Hubb", "15550005", ["phH"]),
          person("dan", "Dan Dale", "15550006", ["phD"]),
          person("phone:phP", "the user of Phone P (+15550004)", "15550004", ["phP"], dossier=False)]
NUM = {p["key"]: next(iter(p["numbers"])) for p in PEOPLE}


def msg(ref, owner, other, when, body, *, sender=None, thread=None, kind="message", parties=None):
    ps = parties if parties is not None else [other]
    rec = {"ref": ref, "kind": kind, "at": when, "phone": "ph" + owner[-1].upper() if owner.startswith("phone:") else
           "ph" + owner[0].upper(), "owner": owner, "parties": ps, "counterpart_values": [NUM[p] for p in ps],
           "body": body, "sender": sender or owner, "thread": thread}
    rec["dup_key"] = contact_dup_key(kind, when, body, [owner] + ps)
    return rec


def pos(ref, owner, when, lat, lon, source="gps", radius=20.0):
    return {"ref": ref, "kind": "position", "at": when, "phone": "x", "owner": owner,
            "place": {"lat": lat, "lon": lon, "radius_m": radius, "source": source}}


def world():
    recs = []
    for n, d in enumerate(NIGHTS):
        # the prepaid phone: to Ann, then Bob, then Cat, the same lines each night; Ann answers "ok"
        recs += [msg(f"p1:{d}", "phone:phP", "ann", at(d, 22, 5), "bay is clear"),
                 msg(f"p1c:{d}", "ann", "phone:phP", at(d, 22, 5), "bay is clear", sender="phone:phP"),
                 msg(f"a1:{d}", "ann", "phone:phP", at(d, 22, 7), "ok"),
                 msg(f"p2:{d}", "phone:phP", "bob", at(d, 22, 10), "gate at 11"),
                 msg(f"p3:{d}", "phone:phP", "cat", at(d, 23, 40), "unit open")]
        # Ann pays Bob each night (no contact between them ever), and the call Ann makes to the hub is on both phones
        recs.append({"ref": f"pay:{d}", "kind": "payment", "at": at(d + timedelta(days=1), 0), "day_only": True,
                     "owner": "ann", "parties": ["cat"], "amount_minor": 50000, "body": "to Cat",
                     "dup_key": ("pay", "ann", ("cat",), 50000, d)})
        recs += [msg(f"c1:{d}", "ann", "hub", at(d, 12, 0), None, kind="call"),
                 msg(f"c1c:{d}", "hub", "ann", at(d, 12, 0), None, kind="call"),
                 msg(f"h2:{d}", "hub", "bob", at(d, 13), "hi bob"), msg(f"h3:{d}", "hub", "cat", at(d, 14), "hi cat"),
                 msg(f"h4:{d}", "hub", "dan", at(d, 15), "hi dan")]
        # the prepaid phone beside Ann's phone each night; a photo place puts Bob there too, which must not count
        recs += [pos(f"pa:{d}", "ann", at(d, 23), *YARD), pos(f"pp:{d}", "phone:phP", at(d, 23, 5), *YARD),
                 pos(f"pb:{d}", "bob", at(d, 23, 2), *YARD, source="media_exif", radius=None)]
    # a group chat of Bob and Cat (and the hub) on Bob's phone
    recs.append(msg("g1", "bob", "cat", at(NIGHTS[0], 9), "group hello", thread="T-group", parties=["cat", "hub"]))
    return recs


class Store:
    def __init__(self, recs, threads=(), claims=(), texts=(), theories=()):
        self.recs, self.threads, self.claims, self.texts, self.theories = recs, threads, claims, texts, theories
        self.db = types.SimpleNamespace(rollback=lambda: None)

    def people(self):
        return PEOPLE

    def zone(self):
        return "UTC"

    def records(self, people, windows, everyone):
        return [dict(r) for r in self.recs]

    def q(self, sql, **_):
        if "phone_threads" in sql:
            return list(self.threads)
        if "evidence_claims" in sql:
            return list(self.claims)
        if "evidence_document_texts" in sql:
            return list(self.texts)
        if "workspace_entries" in sql:
            return _Rows(self.theories)
        raise AssertionError(sql)


class _Rows(list):
    def mappings(self):
        return self


def _grid(**kw):
    g = O.build(Store(world(), **kw), None)
    json.dumps(g)  # served as JSON: nothing else may be in it
    return g


def _pair(g, a, b):
    a, b = sorted((a, b))
    return next(p for p in g["pairs"] if (p["a"], p["b"]) == (a, b))


def test_a_call_held_on_both_phones_is_one_call_but_calls_to_unknown_numbers_stay_apart():
    when = at(NIGHTS[0], 12, 0)
    assert contact_dup_key("call", when, None, ["ann", "hub"]) == contact_dup_key("call", when.replace(second=40), "", ["hub", "ann"])
    assert contact_dup_key("call", when, None, ["ann", None]) is None
    g = _grid()
    c = _pair(g, "ann", "hub")["kinds"]["contact"]
    assert c["count"] == 4  # four calls, each held on both phones
    assert "4 held on both phones, counted once" in c["words"]


def test_a_message_on_both_phones_counts_once_and_a_group_message_is_contact():
    g = _grid(threads=[("phB", "T-group", "Signal", "night shift", 1, ["phone:+15550002", "phone:+15550003", "phone:+15550005"])])
    ann_pre = _pair(g, "ann", "phone:phP")["kinds"]["contact"]
    assert ann_pre["count"] == 8  # 4 nights x ("bay is clear" held twice, counted once, + "ok")
    bc = _pair(g, "bob", "cat")
    assert bc["kinds"]["contact"]["count"] == 1 and bc["direct"]
    assert bc["kinds"]["groups"]["count"] == 1 and "“night shift” on Signal" in bc["kinds"]["groups"]["words"]


def test_photo_places_never_place_two_people_together():
    g = _grid()
    assert _pair(g, "ann", "phone:phP")["kinds"]["place"]["count"] == 4
    assert _pair(g, "bob", "phone:phP")["kinds"]["place"]["count"] == 0
    assert any("places read from photos" in n for n in g["notes"])


def test_worth_a_look_lists_money_without_contact_and_a_narrow_go_between_but_not_a_hub():
    g = _grid()
    look = {(w["a"], w["b"]): w for w in g["worth_a_look"]}
    ac = look[("ann", "cat")]
    assert "money" in ac["reasons"] and "$2,000.00" in " ".join(ac["words"])
    ab = look[("ann", "bob")]
    assert ab["reasons"] == ["go_between"] and "the user of Phone P" in ab["words"][0]
    # the hub reaches four people: never the route Worth a look names
    assert all("but Hal Hubb contacts" not in w for x in look.values() for w in x["words"])
    # beside a phone with no owner name on 4 nights, never in contact: one phone may be the other person's
    assert "beside" not in look.get(("ann", "phone:phP"), {"reasons": []})["reasons"]  # they are in contact


def test_a_theory_naming_a_person_and_a_phone_is_worth_a_look_with_what_the_records_hold():
    g = _grid(theories=[{"id": "t1", "entry_type": "theory", "title": "T1 Hal Hubb kept the phone", "body": "his phone"}])
    w = next(x for x in g["worth_a_look"] if (x["a"], x["b"]) == ("hub", "phone:phP"))
    i = w["reasons"].index("theory")
    assert "“T1 Hal Hubb kept the phone” names Hal Hubb" in w["words"][i] and "no contact, no shared place" in w["words"][i]


def test_the_go_between_panel_reaches_three_people_never_the_hub_and_finds_the_order_every_night():
    g = _grid()
    panel = g["go_betweens"]["phone:phP"]
    assert sorted(panel["reaches"]) == ["Ann Arden", "Bob Brook", "Cat Crane"]
    hub = next(p for p in panel["people"] if p["key"] == "hub")
    assert hub["contacts"] == 0
    pat = panel["pattern"]
    assert pat["times"] == 4 and pat["days"] == [d.isoformat() for d in NIGHTS]
    assert [(s["with"], s["body"]) for s in pat["steps"]] == [("Ann Arden", "bay is clear"), ("Bob Brook", "gate at 11"),
                                                              ("Cat Crane", "unit open")]
    assert pat["steps"][0]["reply"]["body"] == "ok"


def test_documents_name_both_from_the_model_with_its_page_or_a_full_name_in_the_text():
    claims = [("f1", "lease.pdf", {"category": "Person", "name": "Ann Arden"}, "Ann Arden, tenant", {"page_start": 2}),
              ("f1", "lease.pdf", {"category": "Organization", "name": "Bob Brook Ltd"}, "q", {"page_start": 1}),
              ("f2", "memo.pdf", {"category": "Person", "name": "Cat Crane"}, "q", {"page_start": 1})]
    texts = [("f1", "lease.pdf", "Landlord BROOK, BOB; tenant Ann Arden"), ("f2", "memo.pdf", "Cat Crane only"),
             ("f9", "phone-report.txt", "Ann Arden Bob Brook Cat Crane")]
    g = _grid(claims=claims, texts=texts)
    docs = _pair(g, "ann", "bob")["kinds"]["documents"]
    assert docs["count"] == 1 and docs["model_reading"]
    d = docs["documents"][0]
    assert d["pages"] == {"ann": [2], "bob": []} and d["by"] == {"ann": "model", "bob": "name in the text"}
    assert g["documents"] == {"read": 2, "naming_two_phone_owners": 1}  # the phone report is not a document read
    square = g["graph"]["squares"][0]
    assert square["people"] == ["ann", "bob"]


def test_the_graph_draws_direct_lines_by_records_and_dashes_a_route_through_a_narrow_go_between():
    g = _grid()
    lines = {(x["a"], x["b"]): x["records"] for x in g["graph"]["lines"]}
    assert lines[("ann", "hub")] == 4
    dashed = {(x["a"], x["b"]): x for x in g["graph"]["dashed"]}
    assert dashed[("ann", "cat")]["via"] == "phone:phP" and dashed[("ann", "cat")]["money"] == 4


def test_levels_come_only_from_saved_leads_naming_both(monkeypatch):
    g = _grid()
    assert {p["state"] for p in g["pairs"]} <= {"not_weighed", "nothing"} and not any("level" in p for p in g["pairs"])
    leads = [{"id": "l1", "people": ["ann", "cat", "bob"], "level": {"key": "possible", "name": "Possible link"}},
             {"id": "l2", "people": ["ann", "cat"], "level": {"key": "strong", "name": "Strong link"}},
             {"id": "l3", "people": ["bob", "hub"], "level": {"key": "no_link_found", "name": "No link found"},
              "searched": ["calls"]}]
    mod = types.ModuleType("services.leads.store")
    mod.list_leads = lambda db, case_id, **kw: leads
    monkeypatch.setitem(sys.modules, "services.leads", types.ModuleType("services.leads"))
    monkeypatch.setitem(sys.modules, "services.leads.store", mod)
    out = O.attach_levels(None, "c", g)
    ac = _pair(out, "ann", "cat")
    assert ac["level"]["key"] == "strong" and [l["id"] for l in ac["leads"]] == ["l2", "l1"]
    assert _pair(out, "bob", "hub")["state"] == "no_link"
    assert "level" not in _pair(out, "ann", "hub")


def test_a_pair_with_nothing_says_so_and_what_was_searched():
    g = _grid()
    p = _pair(g, "bob", "hub")
    assert p["kinds"]["contact"]["count"] == 5 and p["state"] == "not_weighed"  # 4 messages and the group's
    nothing = [p for p in g["pairs"] if p["state"] == "nothing"]
    assert all(not p["kinds_found"] for p in nothing)
    assert {k["key"] for k in g["kinds"]} == set(O.KINDS) and all(k["searched"] for k in g["kinds"])


def test_the_route_needs_case_view():
    got = {(sorted(r.methods)[0], r.path): r for r in corroborate_overlaps.router.routes}
    route = got[("GET", "/api/cases/{case_id}/corroborate/overlaps")]
    assert require_case_view in {d.dependency for d in route.dependencies}
    app = FastAPI()
    app.include_router(corroborate_overlaps.router)
    app.dependency_overrides[require_case_view] = lambda: None
    app.dependency_overrides[corroborate_overlaps.get_db] = lambda: None
    called = {}
    orig = O.cached_build
    try:
        O.cached_build = lambda db, case_id, fresh=False: called.setdefault("fresh", fresh) and {} or {"ok": True}
        r = TestClient(app).get("/api/cases/11111111-2222-3333-4444-555555555555/corroborate/overlaps?fresh=true")
    finally:
        O.cached_build = orig
    assert r.status_code == 200 and called["fresh"] is True
