"""04 section 6.5 (cb-textplaces): written places a person places on the map, and offline GeoNames suggestions.

Synthetic phones and a synthetic place list only. Opt-in PostgreSQL through ``LOUPE_TEST_PHONE_PG_TEMPLATE_URL``
for the database tests; the place-list tests need nothing. No test makes a network call.
"""
from __future__ import annotations

import socket
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from services import geocoder
from services.financial.decisions import Actor
from services.pattern_of_life import places, text_places
from services.phone import registry
from tests.phone_pg import fld, fresh_engine, make_case, model, needs_template
from tests.test_pattern_u4_availability import DAY, _stamp, setup
from tests.test_pattern_u5_places import PlacePhone, build, obs
from tests.test_phone_mappings import hooks  # noqa: F401 (fixture)

ACTOR = Actor(name="Test Person", email="t@x.test")
PIN = (38.8895, -77.0353)  # synthetic point


class TextPhone(PlacePhone):
    def calendar(self, when, where, hours=2):
        end = when + timedelta(hours=hours)
        f = [fld("StartDate", ("TimeStamp", when.isoformat())), fld("EndDate", ("TimeStamp", end.isoformat())),
             fld("Subject", ("String", "Synthetic meeting")), fld("Location", ("String", where))]
        self.records.append((self.o, None, self.o, model("CalendarEntry", f)))
        self.stamps += [_stamp(self.o, "StartDate", "CalendarEntry", when, "0.0"),
                        _stamp(self.o, "EndDate", "CalendarEntry", end, "1.0")]
        self.o += 1

    def written_location(self, when, description, category=None):
        f = [fld("TimeStamp", ("TimeStamp", when.isoformat())), fld("Description", ("String", description))]
        if category:
            f.append(fld("Category", ("String", category)))
        self.records.append((self.o, None, self.o, model("Location", f)))
        self.stamps.append(_stamp(self.o, "TimeStamp", "Location", when))
        self.o += 1

    def social(self, when, title, activity_type):
        f = [fld("TimeStamp", ("TimeStamp", when.isoformat())), fld("Title", ("String", title)),
             fld("SocialActivityType", ("SocialActivityType", activity_type))]
        self.records.append((self.o, None, self.o, model("SocialMediaActivity", f)))
        self.stamps.append(_stamp(self.o, "TimeStamp", "SocialMediaActivity", when))
        self.o += 1


@pytest.fixture(autouse=True)
def _no_network(monkeypatch, tmp_path):
    from services import manual_changes
    monkeypatch.setattr(manual_changes, "INBOX", tmp_path / "inbox.jsonl")  # never the real feed inbox

    def refuse(*a, **k):
        raise AssertionError("a text place path tried to reach the network")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(geocoder, "_PRIMARY", None)
    monkeypatch.setattr(geocoder, "_FALLBACK", None)


CITIES = [
    # geonameid, name, asciiname, alternatenames, lat, lon, class, code, cc, cc2, admin1, admin2..4, population
    ("1", "Springfield", "39.80172", "-89.64371", "US", "IL", "114394"),
    ("2", "Springfield", "37.21533", "-93.29824", "US", "MO", "170188"),
    ("3", "Dublin", "53.33306", "-6.24889", "IE", "L", "1024027"),
    ("4", "Il", "-1.8", "36.8", "KE", "34", "7812"),
    ("5", "Sant Julià de Lòria", "42.46372", "1.49129", "AD", "06", "8022"),
]


def _place_list(d):
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "cities1000.txt", "w", encoding="utf-8") as fh:
        for gid, name, lat, lon, cc, a1, pop in CITIES:
            fh.write("\t".join([gid, name, name, "", lat, lon, "P", "PPL", cc, "", a1, "", "", "", pop, "", "0",
                                "UTC", "2024-01-01"]) + "\n")
    (d / "admin1CodesASCII.txt").write_text("US.IL\tIllinois\tIllinois\t1\nUS.MO\tMissouri\tMissouri\t2\n"
                                            "IE.L\tLeinster\tLeinster\t3\n", encoding="utf-8")
    (d / "countryInfo.txt").write_text("#ISO\tISO3\tnum\tfips\tCountry\nIE\tIRL\t372\tEI\tIreland\n"
                                       "US\tUSA\t840\tUS\tUnited States\n", encoding="utf-8")
    return geocoder.build_forward_index(str(d))


@pytest.fixture
def place_list(monkeypatch, tmp_path):
    monkeypatch.setenv("LOUPE_REFERENCE_DATA_DIR", str(tmp_path / "ref"))
    return _place_list(tmp_path / "ref" / "geonames")


# ---- the offline place list (no database) --------------------------------------------------------------------------

def test_a_written_place_finds_its_town_with_region_and_population_and_says_how_many_matched(place_list):
    assert place_list["places"] == len(CITIES)
    out = geocoder.forward_candidates("10 Main St., Springfield, IL 62701")
    assert out["total"] == 2 and out["returned"] == 2
    first = out["candidates"][0]
    assert (first["name"], first["admin1"], first["population"], first["country"]) == (
        "Springfield", "Illinois", 114394, "United States")  # the region the text names comes first
    assert all(c["name"] != "Il" for c in out["candidates"])  # a region code is never read as a town
    assert "GeoNames" in out["attribution"]
    assert geocoder.forward_candidates("Springfield", limit=1)["total"] == 2  # a clipped list keeps its total
    assert geocoder.forward_candidates("sant julia de loria")["candidates"][0]["geonameid"] == 5
    assert geocoder.forward_candidates("Dublin 8, Ireland")["candidates"][0]["country_code"] == "IE"
    assert geocoder.forward_candidates("Ireland")["total"] == 0  # a country alone is not a place to stand at


def test_suggestions_are_off_with_the_reason_unless_the_lookup_stays_on_this_server(place_list, monkeypatch, tmp_path):
    assert text_places.suggestion_status()["enabled"] is True

    class B:
        def __init__(self, name, url=""):
            self.name, self._base_url = name, url
    off = text_places.suggestion_status(B("nominatim", "https://nominatim.openstreetmap.org"))
    assert off["enabled"] is False and "not on this server" in off["reason"]
    assert text_places.suggestion_status(B("nominatim", "http://localhost:8080"))["enabled"] is True
    assert text_places.suggestion_status(B("geonames"))["enabled"] is True
    monkeypatch.setenv("LOUPE_REFERENCE_DATA_DIR", str(tmp_path / "nothing"))
    missing = text_places.suggestion_status()
    assert missing["enabled"] is False and "not installed" in missing["reason"]
    with pytest.raises(LookupError):
        geocoder.forward_candidates("Springfield")


# ---- placing, removing and the projection ---------------------------------------------------------------------------

def _phone(c):
    registry.apply_seed(c)
    case = make_case(c)
    p = TextPhone()
    p.calendar(DAY + timedelta(hours=9), "Synthetic Hall, Springfield, IL 62701")
    p.written_location(DAY + timedelta(hours=11), "1 Synthetic Road, Dublin 8")
    p.written_location(DAY + timedelta(hours=12), "photo_0001.jpg", category="Media Locations")
    p.location(DAY + timedelta(hours=13))  # a Location with a coordinate is placed already, never listed
    p.social(DAY + timedelta(hours=14), "Synthetic Cafe", "CheckIn")
    p.social(DAY + timedelta(hours=15), "Synthetic post", "Post")
    return case, p.make(c, case)


def _items(engine, case, **kw):
    with engine.connect() as c:
        return text_places.list_places(c, case, **kw)


@needs_template
def test_text_places_are_listed_with_their_kind_and_true_totals(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, ext = _phone(c)
        build(engine, ext)
        out = _items(engine, case)
        assert out["total"] == 3 and out["counts"]["by_group"] == {"calendar": 1, "checkin": 1, "other": 1}
        by = {i["group"]: i for i in out["items"]}
        assert by["calendar"]["kind"] == "planned" and by["checkin"]["kind"] == "declared"
        assert by["other"]["kind"] == "declared"  # a written address on a Location is never a presence
        assert by["calendar"]["start_utc"] == DAY + timedelta(hours=9)
        assert by["calendar"]["end_utc"] == DAY + timedelta(hours=11)
        assert all(i["placement"] is None for i in out["items"])
        page = _items(engine, case, cursor=1, limit=1)
        assert (page["total"], page["returned"], page["next_cursor"]) == (3, 1, 2)
        assert _items(engine, case, status="placed")["total"] == 0


@needs_template
def test_a_person_places_a_calendar_location_and_it_becomes_a_planned_observation_that_survives_a_rebuild(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, ext = _phone(c)
        build(engine, ext)
        cal = [i for i in _items(engine, case)["items"] if i["group"] == "calendar"][0]
        before = sum(1 for o in obs(engine, ext) if o["source_kind"] == "person_placed")
        assert before == 0
        with Session(engine) as s:
            out = text_places.place(s, case, cal["record_uid"], cal["field_path"], lat=PIN[0], lon=PIN[1],
                                    radius_m=150, reason="The hall named in the entry", actor=ACTOR)
            s.commit()
        mine = [o for o in obs(engine, ext) if o["source_kind"] == "person_placed"]
        assert len(mine) == 1
        o = mine[0]
        assert (o["kind"], o["radius_m"], o["radius_basis"], o["record_type"]) == ("planned", 150.0, "manual",
                                                                                  "CalendarEntry")
        assert str(o["decision_id"]) == out["decision_id"] and o["start_utc"] == DAY + timedelta(hours=9)
        assert o["kind"] not in places.ROUTINE_KINDS
        with engine.connect() as c:
            d = c.execute(text("SELECT decision, actor_name, subject_type, after FROM adjudications WHERE id = :i"),
                          {"i": out["decision_id"]}).one()
            assert (d.decision, d.actor_name, d.subject_type) == ("place_text_place", "Test Person", "phone_record")
            assert d.after["place"] == {"lat": "38.8895000", "lon": "-77.0353000", "radius_m": 150}
            assert c.execute(text("SELECT text_places_version FROM pol_projection_state WHERE extraction_id = :e"),
                             {"e": ext}).scalar() == 1
            assert c.execute(text("SELECT count(*) FROM manual_changes WHERE kind = 'pattern_text_place'")).scalar() == 1
        listed = [i for i in _items(engine, case)["items"] if i["group"] == "calendar"][0]
        assert listed["placement"]["actor_name"] == "Test Person"
        assert listed["placement"]["place_text"] == "Synthetic Hall, Springfield, IL 62701"
        with engine.begin() as c:
            places.build(c, ext)  # the projection rebuilds from the decisions
        assert sum(1 for o in obs(engine, ext) if o["source_kind"] == "person_placed") == 1


@needs_template
def test_replacing_and_removing_keep_every_earlier_placement_and_the_original_text(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, ext = _phone(c)
        build(engine, ext)
        loc = [i for i in _items(engine, case)["items"] if i["group"] == "other"][0]
        key = (loc["record_uid"], loc["field_path"])
        with Session(engine) as s:
            text_places.place(s, case, *key, lat=53.3, lon=-6.2, radius_m=2000, reason="first", actor=ACTOR)
            text_places.place(s, case, *key, lat=53.31, lon=-6.21, radius_m=500, reason="closer", actor=ACTOR)
            s.commit()
        mine = [o for o in obs(engine, ext) if o["source_kind"] == "person_placed"]
        assert [(o["lat"], o["radius_m"], o["kind"]) for o in mine] == [(53.31, 500.0, "declared")]
        with Session(engine) as s:
            text_places.remove(s, case, *key, reason="wrong road", actor=ACTOR)
            s.commit()
        assert [o for o in obs(engine, ext) if o["source_kind"] == "person_placed"] == []
        with engine.connect() as c:
            h = text_places.history(c, case, *key)
            assert [r["reason"] for r in h] == ["first", "closer"] and all(r["removed_decision_id"] for r in h)
            assert all(r["place_text"] == "1 Synthetic Road, Dublin 8" for r in h)
            assert c.execute(text("SELECT text_places_version FROM pol_projection_state WHERE extraction_id = :e"),
                             {"e": ext}).scalar() == 3
        with Session(engine) as s:
            with pytest.raises(text_places.TextPlaceError) as e:
                text_places.remove(s, case, *key, reason="again", actor=ACTOR)
            assert e.value.status == 409


@needs_template
def test_a_suggestion_is_never_saved_and_a_chosen_one_is_kept_beside_the_persons_point(hooks, place_list):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, ext = _phone(c)
        build(engine, ext)
        cal = [i for i in _items(engine, case)["items"] if i["group"] == "calendar"][0]
        with engine.connect() as c:
            sug = text_places.suggest(c, case, cal["record_uid"], cal["field_path"])
            assert sug["enabled"] and sug["label"] == "Suggested, not confirmed"
            assert sug["candidates"][0]["admin1"] == "Illinois"
            assert c.execute(text("SELECT count(*) FROM pol_text_place")).scalar() == 0
            assert c.execute(text("SELECT count(*) FROM adjudications")).scalar() == 0
        assert [o for o in obs(engine, ext) if o["source_kind"] == "person_placed"] == []
        chosen = sug["candidates"][0]
        with Session(engine) as s:
            text_places.place(s, case, cal["record_uid"], cal["field_path"], lat=39.8, lon=-89.65, radius_m=5000,
                              reason="The town in the entry", actor=ACTOR, suggestion=chosen)
            s.commit()
        with engine.connect() as c:
            row = c.execute(text("SELECT lat, radius_m, suggestion FROM pol_text_place")).one()
            assert (row.lat, row.radius_m) == (39.8, 5000.0)  # the person's point, not the candidate's
            assert row.suggestion["geonameid"] == 1 and row.suggestion["source"] == "GeoNames (offline)"


@needs_template
def test_refused_placements_record_nothing(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, ext = _phone(c)
            other = make_case(c)
        build(engine, ext)
        cal = [i for i in _items(engine, case)["items"] if i["group"] == "calendar"][0]
        bad = [dict(lat=91, lon=0, radius_m=10, reason="x"), dict(lat=0, lon=0, radius_m=0, reason="x"),
               dict(lat=0, lon=0, radius_m=10, reason="  ")]
        with Session(engine) as s:
            for kw in bad:
                with pytest.raises(text_places.TextPlaceError):
                    text_places.place(s, case, cal["record_uid"], cal["field_path"], actor=ACTOR, **kw)
            with pytest.raises(text_places.TextPlaceError) as e:  # another case's record is not this case's
                text_places.place(s, other, cal["record_uid"], cal["field_path"], lat=0, lon=0, radius_m=10,
                                  reason="x", actor=ACTOR)
            assert e.value.status == 404
            s.rollback()
        with engine.connect() as c:
            for t in ("pol_text_place", "adjudications", "manual_changes"):
                assert c.execute(text("SELECT count(*) FROM %s" % t)).scalar() == 0


@needs_template
def test_saving_the_same_place_again_is_refused_and_counts_and_staleness_follow_the_decisions(hooks):
    from services.pattern_of_life import snapshots
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, ext = _phone(c)
        build(engine, ext)
        with engine.connect() as c:
            frozen = snapshots.mapping_versions(c, case, [ext], text_places=True)
            assert "text_places_version" not in frozen["extractions"][str(ext)]["projection"]  # old results unchanged
        cal = [i for i in _items(engine, case)["items"] if i["group"] == "calendar"][0]
        key = (cal["record_uid"], cal["field_path"])
        with Session(engine) as s:
            text_places.place(s, case, *key, lat=PIN[0], lon=PIN[1], radius_m=150, reason="first", actor=ACTOR)
            s.commit()
        with Session(engine) as s:
            with pytest.raises(text_places.TextPlaceError) as e:  # same point, radius and text: nothing to decide
                text_places.place(s, case, *key, lat=PIN[0], lon=PIN[1], radius_m=150, reason="again", actor=ACTOR)
            assert e.value.status == 409
            s.rollback()
        with engine.connect() as c:
            assert c.execute(text("SELECT count(*) FROM adjudications")).scalar() == 1
            assert snapshots.mapping_versions(c, case, [ext], text_places=True) != frozen  # a saved result goes stale
            assert snapshots.mapping_versions(c, case, [ext]) == frozen  # analysis results do not read text places
        with Session(engine) as s:
            text_places.remove(s, case, *key, reason="wrong hall", actor=ACTOR)
            s.commit()
        listed = [i for i in _items(engine, case)["items"] if i["group"] == "calendar"][0]
        assert listed["decisions"] == 2 and listed["placement"] is None
        with engine.connect() as c:
            h = text_places.history(c, case, *key)
            assert (h[0]["ended_by"], h[0]["ended_reason"], h[0]["ended_actor_name"]) == (
                "remove_text_place", "wrong hall", "Test Person")


# ---- followups m110415512326577: the cb-textplaces review's minor items ---------------------------------------------

def test_a_two_letter_region_ranks_its_own_region_before_a_country_with_that_code(monkeypatch, tmp_path):
    monkeypatch.setenv("LOUPE_REFERENCE_DATA_DIR", str(tmp_path / "ref"))
    big = CITIES + [("7", "Springfield", "31.9", "35.2", "IL", "01", "900000")]  # synthetic, larger than Illinois'
    monkeypatch.setitem(globals(), "CITIES", big)  # undone after the test
    _place_list(tmp_path / "ref" / "geonames")
    out = geocoder.forward_candidates("Synthetic Hall, Springfield, IL 62701")
    assert [c["geonameid"] for c in out["candidates"]][:2] == [1, 7]  # Illinois, then the country code IL


def test_the_place_list_opens_from_a_directory_whose_name_has_uri_characters(monkeypatch, tmp_path):
    ref = tmp_path / "ref?a#b%20c"
    monkeypatch.setenv("LOUPE_REFERENCE_DATA_DIR", str(ref))
    _place_list(ref / "geonames")
    src = geocoder.forward_source()
    assert src["available"] is True and src["places"] == len(CITIES)
    assert geocoder.forward_candidates("Dublin")["total"] == 1


@needs_template
def test_a_placement_that_no_longer_applies_is_listed_with_why_and_can_be_removed(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, ext = _phone(c)
        build(engine, ext)
        cal = [i for i in _items(engine, case)["items"] if i["group"] == "calendar"][0]
        key = (cal["record_uid"], cal["field_path"])
        with Session(engine) as s:
            text_places.place(s, case, *key, lat=PIN[0], lon=PIN[1], radius_m=150, reason="first", actor=ACTOR)
            s.commit()
        assert _items(engine, case)["no_longer_applies"] == []
        with engine.begin() as c:  # the text is corrected to blank: it is no longer a written place
            c.execute(text("UPDATE phone_texts SET effective_value = '' WHERE record_uid = :u AND field_path = :f"),
                      {"u": key[0], "f": key[1]})
        out = _items(engine, case)
        assert out["total"] == 2 and out["counts"]["no_longer_applies"] == 1
        stale = out["no_longer_applies"][0]
        assert (stale["record_uid"], stale["field_path"], stale["reason"]) == (key[0], key[1], "first")
        assert "no longer applies" in stale["reason_words"]
        assert _items(engine, case, extraction_id=ext)["counts"]["no_longer_applies"] == 1
        with Session(engine) as s:
            text_places.remove(s, case, *key, reason="text is blank now", actor=ACTOR)
            s.commit()
        assert _items(engine, case)["no_longer_applies"] == []


@needs_template
def test_a_list_reads_record_bodies_once_per_phone_not_once_per_record(hooks):
    from sqlalchemy import event
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            p = TextPhone()
            for h in range(4):
                p.written_location(DAY + timedelta(hours=h), "%d Synthetic Road, Dublin 8" % h)
                p.social(DAY + timedelta(hours=h, minutes=30), "Synthetic Cafe %d" % h, "CheckIn")
            ext = p.make(c, case)
        build(engine, ext)
        reads = []

        def count(conn, cursor, statement, *a):
            if "FROM phone_records" in statement:
                reads.append(statement)
        event.listen(engine, "before_cursor_execute", count)
        try:
            out = _items(engine, case)
        finally:
            event.remove(engine, "before_cursor_execute", count)
        assert out["total"] == 8
        assert len(reads) <= 2, len(reads)  # check-ins once, Location kinds once


@needs_template
def test_a_suggestion_not_offered_for_the_text_is_refused_and_an_offered_one_is_kept_as_the_list_has_it(
        hooks, place_list):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, ext = _phone(c)
        build(engine, ext)
        cal = [i for i in _items(engine, case)["items"] if i["group"] == "calendar"][0]
        forged = {"geonameid": 3, "name": "Dublin", "lat": 53.33306, "lon": -6.24889}  # not offered for Springfield
        with Session(engine) as s:
            with pytest.raises(text_places.TextPlaceError) as e:
                text_places.place(s, case, cal["record_uid"], cal["field_path"], lat=39.8, lon=-89.65,
                                  radius_m=5000, reason="x", actor=ACTOR, suggestion=forged)
            assert "not one the list offered" in str(e.value)
            s.rollback()
        renamed = {"geonameid": 1, "name": "Somewhere Else", "lat": 1.0, "lon": 2.0}
        with Session(engine) as s:
            text_places.place(s, case, cal["record_uid"], cal["field_path"], lat=39.8, lon=-89.65, radius_m=5000,
                              reason="The town in the entry", actor=ACTOR, suggestion=renamed)
            s.commit()
        with engine.connect() as c:
            sug = c.execute(text("SELECT suggestion FROM pol_text_place")).scalar()
            assert (sug["name"], sug["lat"], sug["lon"]) == ("Springfield", "39.80172", "-89.64371")


@needs_template
def test_with_no_event_time_a_records_start_field_is_its_time_not_its_earliest_time(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, ext = _phone(c)
        build(engine, ext)
        cal = [i for i in _items(engine, case)["items"] if i["group"] == "calendar"][0]
        with engine.begin() as c:
            c.execute(text("UPDATE phone_time_values SET is_event_time = false WHERE record_uid = :u"),
                      {"u": cal["record_uid"]})
            c.execute(text(
                "CREATE TEMP TABLE tv AS SELECT * FROM phone_time_values WHERE record_uid = :u AND "
                "field_name = 'StartDate'"), {"u": cal["record_uid"]})
            for name, shift in (("CreationTime", "-3 days"), ("RepeatUntil", "-1 day")):  # both before the start
                c.execute(text(
                    "UPDATE tv SET time_uid = gen_random_uuid(), field_name = CAST(:n AS text), field_path = field_path || CAST(:n AS text), "
                    "instant = instant + CAST(:s AS interval), "
                    "effective_instant = effective_instant + CAST(:s AS interval)"), {"n": name, "s": shift})
                c.execute(text("INSERT INTO phone_time_values SELECT * FROM tv"))
        again = [i for i in _items(engine, case)["items"] if i["group"] == "calendar"][0]
        assert again["start_utc"] == DAY + timedelta(hours=9)
        assert again["end_utc"] == DAY + timedelta(hours=11)


# ---- a payment's written payee (04 8.5; the same offline list) -------------------------------------------------------

@pytest.mark.parametrize("written,ids", [
    ("Withdrawal Debit Card\n01/02 3 1234567890 4 SYNTHETIC SHOP #1234 SPRINGFIELD IL", [1]),   # the last line, the town
    ("SYNTHETIC SHOP SPRINGFIELD MO", [2]),                                                      # the region decides
    ("SYNTHETIC SHOP 555-555-0100 DC", []),                                                      # no town after the number
    ("PAGO SPEI SPRINGFIELD", []),                                                               # no region code: nothing
    ("SYNTHETIC SHOP SPRINGFIELD ZZ", []),                                                       # not in that region
    ("", []),
])
def test_a_payee_line_offers_its_town_only_in_the_region_that_closes_it(place_list, written, ids):
    out = geocoder.payee_candidates(written)
    assert [c["geonameid"] for c in out["candidates"]] == ids and out["total"] == len(ids)


def test_a_payee_line_tries_the_longest_name_and_stops_at_a_store_number():
    assert geocoder.payee_tail("SHOP #12 NEW SALEM IL") == (["new salem", "salem"], "IL")
    assert geocoder.payee_tail("BIG SYNTHETIC SHOP NEW SALEM IL")[0][0] == "shop new salem"
    assert geocoder.payee_tail("SHOP SALEM") == ([], None)
