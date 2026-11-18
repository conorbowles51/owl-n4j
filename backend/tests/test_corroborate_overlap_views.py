"""lx-overlapviews-b: Map areas compared over a window (A), words that also appear elsewhere in Conversations (B) and
money around chosen events (C), on invented data. Each rule is checked on the plain functions; the routes are checked
for their access rule. All names, numbers and places are invented here."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from services.corroborate import area_compare as AC
from services.corroborate import around_event as AE
from services.corroborate import shared_words as SW
from services.corroborate.store import _read_alert

UTC = timezone.utc
PEOPLE = [
    {"key": "person:ann", "label": "Ann Arden", "names": ["Ann Arden"], "numbers": {"15550001"}, "phones": ["phA"],
     "accounts": ["accA"], "dossier_id": "ann"},
    {"key": "person:bob", "label": "Bob Brook", "names": ["Bob Brook"], "numbers": {"15550002"}, "phones": ["phB"],
     "accounts": [], "dossier_id": "bob"},
    {"key": "phone:phC", "label": "the user of Phone C", "names": [], "numbers": {"15550003"}, "phones": ["phC"],
     "accounts": [], "dossier_id": None},
]


# ---- the alert reading the money view relies on (fails on the old store) ---------------------------------------

def test_received_alert_with_a_first_name_and_initial_is_read_as_that_person():
    got = _read_alert("You received $500.00 from Ann A.", "person:bob", PEOPLE)
    assert got["owner"] == "person:ann" and got["parties"] == ["person:bob"] and got["partial_name"] is True


def test_deposit_posted_to_checking_is_a_cash_deposit_not_a_check():
    got = _read_alert("Bank: a deposit of $9,800.00 posted to checking ending 4471.", "person:ann", PEOPLE)
    assert got == {"owner": "person:ann", "parties": [], "amount_minor": 980000, "cash_deposit": True}


def test_mobile_check_deposit_alert_is_a_check_paid_to_the_phone_owner():
    got = _read_alert("Bank: your mobile check deposit of $3,400.00 was accepted.", "person:ann", PEOPLE)
    assert got == {"owner": None, "parties": ["person:ann"], "amount_minor": 340000, "check_deposit": True}


# ---- A: areas over a window --------------------------------------------------------------------------------------

def sq(lat, lon, d=0.003):
    return [[lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d], [lon - d, lat + d]]


YARD, DEPOT = (40.0, -70.0), (40.2, -69.8)
FRIDAYS = [date(2025, 1, 3) + timedelta(days=7 * n) for n in range(8)]
NIGHTS = [FRIDAYS[1], FRIDAYS[4], FRIDAYS[6]]


def utc(d, h, m=0):
    return datetime(d.year, d.month, d.day, h, m, tzinfo=UTC)


class FakeStore:
    case = "case"

    def __init__(self, rows=None, recs=None):
        self.rows, self.recs = rows or [], recs or []

    def zone(self):
        return "UTC"

    def people(self):
        return PEOPLE

    def document_rows(self, fid):
        return [r for r in self.rows if r["source"] == fid]

    def records(self, people, windows, everyone):
        return [r for r in self.recs if any(lo.date() <= r["at"].date() <= hi.date() for lo, hi in windows)]

    def q(self, *_a, **_k):
        class R(list):
            def fetchall(self):
                return list(self)

            def first(self):
                return None
        return R()


class FakeReader:
    def __init__(self, pts, docs=()):
        self.pts, self.docs = pts, list(docs)

    def phone_names(self):
        return {e: p["label"] for p in PEOPLE for e in p["phones"]}

    def phone_labels(self):
        return {"phA": "Phone A", "phB": "Phone B", "phC": "Phone C"}

    def period(self):
        return FRIDAYS[0], FRIDAYS[-1] + timedelta(days=2)

    def points(self, bbox, lo, hi):
        return self.pts

    def documents_with_rows(self):
        return self.docs


def pt(ext, at, where, what="position"):
    return {"ref": f"phone_record:{ext}-{at.isoformat()}", "phone": ext, "at": at, "lat": where[0], "lon": where[1],
            "radius_m": 10, "what": what, "source_kind": "gps"}


def area_world():
    pts = []
    for d in NIGHTS:
        pts += [pt("phC", utc(d, 23, 40), YARD), pt("phB", utc(d + timedelta(days=1), 1, 30), YARD),
                pt("phC", utc(d + timedelta(days=1), 2, 30), DEPOT), pt("phB", utc(d + timedelta(days=1), 2, 45), DEPOT),
                pt("phA", utc(d + timedelta(days=1), 3, 0), YARD, what="photo_place")]
    pts.append(pt("phA", utc(FRIDAYS[2], 15, 10), YARD))   # a Friday afternoon: outside the window
    rows = [{"index": i, "at": utc(d, 23, 6), "text": f"{d} 23:06 badge B-1 ARDEN, ANN Dock 3 granted",
             "parties": ["person:ann"], "source": "log"} for i, d in enumerate(NIGHTS)]
    docs = [{"id": "log", "name": "yardco-badge-log.csv", "text": "Yardco access log"}]
    return FakeStore(rows), FakeReader(pts, docs)


def compare(**kw):
    store, reader = area_world()
    return AC.compare_areas(store, [{"label": "Area A · Yardco yard", "ring": sq(*YARD)},
                                    {"label": "Area B · depot", "ring": sq(*DEPOT)}],
                            weekday=4, start="22:00", end="12:00", reader=reader, **kw)


def test_nights_asked_about_default_to_nights_with_something_inside_and_the_rest_are_the_baseline():
    r = compare()
    assert r["asked"]["nights"] == [d.isoformat() for d in NIGHTS]
    assert "nights with a position or access row" in r["asked"]["basis"]
    assert len(r["compared_with"]["nights"]) == len(FRIDAYS) - len(NIGHTS)
    a = r["areas"][0]
    assert a["inside"]["positions"] == 6 and a["inside"]["position_phones"] == 2
    assert a["baseline"] == {"positions": 0, "access_rows": 0, "photo_places": 0, "nights_with_any": 0}


def test_a_photo_place_is_listed_but_never_counted_as_being_there():
    a = compare()["areas"][0]
    assert a["inside"]["photo_places"] == 3
    assert all(p["phone"] != "phA" for p in a["phones"])
    assert a["photo_only"] == [{"phone": "phA", "who": "Ann Arden", "nights": [d.isoformat() for d in NIGHTS]}]


def test_access_rows_join_an_area_by_the_document_the_name_suggests_and_say_so():
    a = compare()["areas"][0]
    assert a["inside"]["access_rows"] == 3 and a["inside"]["doors"] == {"Dock 3": 3}
    assert a["documents"][0]["id"] == "log" and "Suggested by Loupe" in a["documents"][0]["why"]
    assert a["access"][0]["who"] == "Ann Arden" and a["access"][0]["times"] == [{"time": "23:06", "door": "Dock 3", "nights": 3}]
    assert compare(documents={0: []})["areas"][0]["inside"]["access_rows"] == 0  # unticked: not counted


def test_who_is_in_both_and_in_what_order_with_recurring_times():
    r = compare()
    b = {p["who"]: p for p in r["areas"][1]["phones"]}
    assert b["the user of Phone C"]["times"][0]["time"] == "02:30" and len(b["Bob Brook"]["nights"]) == 3
    order = {o["who"]: o for o in r["order"]}
    assert order["Bob Brook"]["sequence"] == [0, 1] and order["Bob Brook"]["nights"] == 3


def test_positions_outside_the_window_are_reported_apart():
    a = compare()["areas"][0]
    assert a["outside_window"][0]["who"] == "Ann Arden" and a["outside_window"][0]["usual_hour"] == "15:00 to 16:00"


def test_chosen_nights_replace_the_default_and_a_busy_night_left_out_counts_in_the_baseline():
    r = compare(nights=[NIGHTS[0].isoformat(), NIGHTS[1].isoformat()])
    assert r["asked"]["basis"] == "the nights you chose"
    assert r["areas"][0]["baseline"]["positions"] == 2 and r["areas"][0]["baseline"]["nights_with_any"] == 1


def test_more_areas_than_allowed_are_refused_not_clipped():
    store, reader = area_world()
    with pytest.raises(ValueError, match="at most 6"):
        AC.compare_areas(store, [{"ring": sq(*YARD)}] * 7, weekday=4, start="22:00", end="12:00", reader=reader)


def test_name_words_leave_out_generic_place_words():
    assert AC.name_words("Area A · Yardco warehouse, Dock 3") == ["yardco"]


# ---- B: words that also appear elsewhere -------------------------------------------------------------------------

def agg(words, copies, phones, dates, messages):
    return {"words": words, "text": words, "copies": copies, "phones": phones, "dates": dates, "messages": messages}


def test_one_message_held_on_two_phones_is_one_message_not_words_shared_elsewhere():
    c = SW.classify(agg("bay is clear", 2, ["phA", "phB"], ["2025-01-03"], 1), 6)
    assert c["repeated"] is False and c["stock"] is False


def test_rare_words_on_two_phones_count_once_per_message_and_stock_words_are_set_aside():
    c = SW.classify(agg("bay is clear", 6, ["phA", "phB"], ["2025-01-10", "2025-01-31", "2025-02-14"], 3), 6)
    assert (c["repeated"], c["stock"], c["why"]) == (True, False, None)
    s = SW.classify(agg("see you at 7", 6, [f"ph{i}" for i in range(6)], ["2025-01-03"], 6), 6)
    assert s["stock"] is True and s["why"] == "On all 6 phones."
    many = SW.classify(agg("on the way", 12, ["phA", "phB"], [f"2025-02-{d:02d}" for d in range(1, 13)], 12), 6)
    assert many["why"] == "On 12 dates."
    two_phone_case = SW.classify(agg("on the way", 4, ["phA", "phB"], ["2025-02-01", "2025-02-02"], 2), 2)
    assert two_phone_case["stock"] is False  # with two phones in the case, "on every phone" sets nothing aside


def test_compared_words_ignore_case_spacing_and_end_punctuation():
    assert SW.norm("  Unit's   OPEN. ") == "unit's open"


# ---- C: money around events ----------------------------------------------------------------------------------------

def pay(ref, day, amount, owner, payee=None, alert=False, **kw):
    at = datetime(day.year, day.month, day.day, 13, 15, tzinfo=UTC)
    rec = {"ref": ref, "kind": "payment_alert" if alert else "payment", "at": at, "owner": owner,
           "parties": [payee] if payee else [], "amount_minor": amount, "body": kw.pop("body", ""), **kw,
           "dup_key": ("pay", owner, (payee,) if payee else (), amount, day)}
    if not alert:
        rec["day_only"] = True
    return rec


def money_world(skip_bank_on=()):
    recs = []
    for n, d in enumerate(NIGHTS):
        sat = d + timedelta(days=1)
        if d not in skip_bank_on:
            recs.append(pay(f"financial_transaction:b{n}", sat, 50000, "person:ann", "person:bob"))
        recs.append(pay(f"phone_record:a{n}", sat, 50000, "person:ann", "person:bob", alert=True))
        recs.append(pay(f"financial_transaction:k{n}", d + timedelta(days=7), 300000 + n, None, "person:ann",
                        body=f"MOBILE DEP CHK {1040 + n}"))
    for w in (FRIDAYS[0], FRIDAYS[2], FRIDAYS[3]):
        recs.append(pay(f"financial_transaction:g{w}", w + timedelta(days=2), 4000, "person:ann"))
    for d in NIGHTS:
        recs.append(pay(f"financial_transaction:gg{d}", d + timedelta(days=2), 4000, "person:ann"))
    return FakeStore(recs=recs)


@pytest.fixture(autouse=True)
def _period(monkeypatch):
    monkeypatch.setattr(AC.AreaReader, "period", lambda self: (FRIDAYS[0], FRIDAYS[-1] + timedelta(days=2)))


def test_a_payment_in_a_bank_row_and_on_a_phone_is_one_payment_marked_bank_and_phone():
    r = AE.around_events(money_world(skip_bank_on=(NIGHTS[1],)), [{"date": d.isoformat()} for d in NIGHTS])
    col = next(c for c in r["columns"] if c["payer"] == "Ann Arden" and c["payee"] == "Bob Brook")
    cells = [row["cells"][col["id"]] for row in r["rows"]]
    assert [len(c) for c in cells] == [1, 1, 1]
    assert [c[0]["source"] for c in cells] == ["bank_and_phone", "phone_only", "bank_and_phone"]
    assert col["events"] == 3 and col["ordinary"] is False and col["other_weeks_found"] == 0


def test_checks_are_one_column_with_their_numbers_and_total():
    r = AE.around_events(money_world(), [{"date": d.isoformat()} for d in NIGHTS])
    col = next(c for c in r["columns"] if c["kind"] == "check")
    assert col["title"] == "Checks paid to Ann Arden" and col["checks"] == [1040, 1042]
    assert col["total_minor"] == 900003 and col["usual_day"] == 7


def test_a_payment_on_an_events_last_day_is_not_counted_again_in_every_other_week():
    """A check paid seven days after each event lies on the first day of the next Friday's week too; it belongs to the
    event's row and must not also make "every other week" read as having the same payments."""
    r = AE.around_events(money_world(), [{"date": d.isoformat()} for d in NIGHTS])
    col = next(c for c in r["columns"] if c["kind"] == "check")
    assert r["other_weeks"]["weeks"] >= 1 and col["other_weeks_found"] == 0 and col["ordinary"] is False


def test_money_as_common_in_ordinary_weeks_is_folded_with_its_count_not_dropped():
    r = AE.around_events(money_world(), [{"date": d.isoformat()} for d in NIGHTS])
    col = next(c for c in r["columns"] if c["payer"] == "Ann Arden" and c["payee"] is None)
    assert col["ordinary"] is True and col["other_weeks_found"] >= 1


def test_no_events_is_refused():
    with pytest.raises(ValueError):
        AE.around_events(money_world(), [])


# ---- routes ------------------------------------------------------------------------------------------------------

def test_overlap_view_routes_need_case_view():
    from routers import corroborate
    from routers.case_access import require_case_view
    got = {(sorted(r.methods)[0], r.path): r for r in corroborate.router.routes}
    for key in [("POST", "/api/cases/{case_id}/corroborate/area-compare"),
                ("GET", "/api/cases/{case_id}/corroborate/shared-words"),
                ("GET", "/api/cases/{case_id}/corroborate/shared-words/thread"),
                ("GET", "/api/cases/{case_id}/corroborate/shared-words/files"),
                ("POST", "/api/cases/{case_id}/corroborate/around-event"),
                ("GET", "/api/cases/{case_id}/corroborate/around-event/choices")]:
        assert require_case_view in {d.dependency for d in got[key].dependencies}, key


# ---- same-bytes files ----------------------------------------------------------------------------------------------

class FileStore:
    """Three active phones; 250 files on two of them and one file on all three."""
    def q(self, sql, **_k):
        if "pv_file" in sql:
            return [("all", 3, ["e1", "e2", "e3"], "x/IMG_0.jpg")] + [(f"m{i}", 2, ["e1", "e2"], f"a\\IMG_{i}.jpg") for i in range(250)]
        raise AssertionError(sql)


def test_same_files_lists_up_to_the_cap_with_full_counts_and_all_when_asked(monkeypatch):
    monkeypatch.setattr(SW, "_labels", lambda store: {"e1": "Ann's phone", "e2": "Bob's phone", "e3": "Cy's phone"})
    monkeypatch.setattr(SW, "_active_phones", lambda store: ["e1", "e2", "e3"])
    capped = SW.same_files(FileStore())
    assert len(capped["files_shared"]) == SW.LISTED and capped["counts"] == {"files_common": 1, "files_shared": 250}
    assert capped["files_common"][0]["name"] == "IMG_0.jpg" and capped["files_shared"][0]["name"] == "IMG_0.jpg"
    every = SW.same_files(FileStore(), listed=None)
    assert len(every["files_shared"]) == 250 and every["files_shared"][0]["phones"] == ["Ann's phone", "Bob's phone"]


def test_who_overlaps_still_reads_every_shared_file(monkeypatch):
    """shared_content no longer carries the files (they are slow on a big case); Who overlaps with whom must still see
    each one, or a file on both people's phones silently stops counting."""
    from services.corroborate import overlaps
    monkeypatch.setattr(SW, "shared_content", lambda store: {"also": [], "stock": [], "deletions": []})
    monkeypatch.setattr(SW, "_labels", lambda store: {"e1": "Ann's phone", "e2": "Bob's phone", "e3": "Cy's phone"})
    monkeypatch.setattr(SW, "_active_phones", lambda store: ["e1", "e2", "e3"])
    out = overlaps.shared_content(FileStore())
    assert len(out["files_shared"]) == 250 and len(out["files_common"]) == 1
