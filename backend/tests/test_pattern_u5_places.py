"""04-U5 (cb-pol item F): place observations, the offline cell reference importer and WiFi anchors.

Synthetic phones and a synthetic reference file only. Opt-in PostgreSQL through ``LOUPE_TEST_PHONE_PG_TEMPLATE_URL``.
No test makes a network call: the importer reads a local file and anchors come from the case's own fixes.
"""
from __future__ import annotations

import gzip
import json
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from services.pattern_of_life import activity, availability, places
from services.phone import registry, sweep
from tests.phone_pg import fld, fresh_engine, make_case, needs_template, refs, model
from tests.test_pattern_u4_availability import DAY, Phone, _stamp, setup
from tests.test_phone_mappings import hooks  # noqa: F401 (fixture)

LAT, LON = 38.8977, -77.0365  # synthetic point


class PlacePhone(Phone):
    def location(self, when, lat=LAT, lon=LON, accuracy=20, loc_type=None, affiliation=None):
        top = self.o
        f = [fld("TimeStamp", ("TimeStamp", when.isoformat())), refs("Position", top + 1, kind="modelField")]
        if loc_type:
            f.append(fld("Type", ("String", loc_type)))
        if affiliation:
            f.append(fld("DeviceLocationAffiliation", ("DeviceLocationAffiliation", affiliation)))
        cf = [fld("Latitude", ("Double", str(lat))), fld("Longitude", ("Double", str(lon)))]
        if accuracy is not None:
            cf.append(fld("GpsHorizontalAccuracy", ("Double", str(accuracy))))
        self.records += [(top, None, top, model("Location", f)), (top + 1, top, top, model("Coordinate", cf))]
        self.stamps.append(_stamp(top, "TimeStamp", "Location", when))
        self.o += 2

    def wifi(self, when, bssid=None, ssid=None):
        f = [fld("TimeStamp", ("TimeStamp", when.isoformat()))]
        if bssid:
            f.append(fld("BSSId", ("String", bssid)))
        if ssid:
            f.append(fld("SSId", ("String", ssid)))
        self.records.append((self.o, None, self.o, model("WirelessNetwork", f)))
        self.stamps.append(_stamp(self.o, "TimeStamp", "WirelessNetwork", when))
        self.o += 1

    def tower(self, when, mcc, mnc, lac, cid, radio="GSM"):
        f = [fld("TimeStamp", ("TimeStamp", when.isoformat())), fld("MCC", ("Int32", str(mcc))),
             fld("MNC", ("Int32", str(mnc))), fld("LAC", ("Int32", str(lac))), fld("CID", ("Int32", str(cid))),
             fld("CellTowerType", ("CellTowerType", radio))]
        self.records.append((self.o, None, self.o, model("CellTower", f)))
        self.stamps.append(_stamp(self.o, "TimeStamp", "CellTower", when))
        self.o += 1


def build(engine, ext):
    assert sweep.interpret_one(engine, ext)["status"] == "done"
    with engine.begin() as c:
        activity.build(c, ext)
        availability.compute(c, ext)
        return places.build(c, ext)


def obs(engine, ext):
    with engine.connect() as c:
        return [dict(r._mapping) for r in c.execute(text(
            "SELECT * FROM pol_place_observation WHERE extraction_id = :e ORDER BY start_utc, id"), {"e": ext})]


@needs_template
def test_gps_accuracy_doubles_and_a_searched_place_is_not_a_presence(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            p = PlacePhone()
            p.location(DAY)
            p.location(DAY + timedelta(hours=1), loc_type="Searched")
            p.location(DAY + timedelta(hours=2), accuracy=None, affiliation="Synced")
            ext = p.make(c, case)
        build(engine, ext)
        o = obs(engine, ext)
        assert len(o) == 3
        gps = o[0]
        assert (gps["kind"], gps["source_kind"], gps["radius_m"], gps["radius_reported"], gps["radius_basis"]) == (
            "presence", "gps", 40.0, 20.0, "gps_accuracy_x2")
        assert gps["presence_basis"] == "location_record"
        assert gps["time_semantics"] == "unknown"  # 2.3: a Location time is not established per source yet
        searched = o[1]
        assert searched["kind"] == "searched" and "searched" not in places.ROUTINE_KINDS
        synced = o[2]
        assert synced["source_kind"] == "account_location" and synced["radius_m"] is None
        assert synced["radius_basis"] == "unknown" and "synced_from_account" in synced["attribution_flags"]


@needs_template
def test_towers_are_placed_only_from_the_cases_reference_data_and_the_rest_are_listed(hooks, tmp_path, monkeypatch):
    setup(hooks)
    monkeypatch.setattr(places, "REFERENCE_DIR", str(tmp_path))
    ref = tmp_path / "cells.csv.gz"
    with gzip.open(ref, "wt") as fh:
        fh.write("radio,mcc,net,area,cell,unit,lon,lat,range,samples,changeable,created,updated,averageSignal\n")
        fh.write("GSM,310,260,1001,5001,,%s,%s,120,9,1,1600000000,1650000000,0\n" % (LON, LAT))
        fh.write("GSM,310,260,1001,5002,,%s,%s,4000,1,1,1600000000,1650000000,0\n" % (LON, LAT))
        fh.write("GSM,310,260,1001,5001,,%s,%s,120,9,1,1600000000,1650000000,0\n" % (LON, LAT))  # duplicate key
        fh.write("not,a,row\n")
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            p = PlacePhone()
            p.tower(DAY, 310, 260, 1001, 5001)
            p.tower(DAY + timedelta(minutes=5), 310, 260, 1001, 5002)
            p.tower(DAY + timedelta(minutes=10), 310, 260, 1001, 9999)
            ext = p.make(c, case)
        build(engine, ext)  # no dataset chosen for the case yet: nothing placed
        with engine.connect() as c:
            assert {t["reason"] for t in places.unplaced_towers(c, [ext])} == {"no_reference_dataset"}
        assert obs(engine, ext) == []
        with pytest.raises(places.ImportRefused):
            with engine.begin() as c:
                places.import_cell_file(c, "/etc/passwd", name="x", licence="x", attribution="x",
                                        retrieved_on=date(2026, 10, 29), by_name="t", by_email="t@x.test")
        with engine.begin() as c:
            out = places.import_cell_file(c, str(ref), name="synthetic cells", licence="CC BY-SA 4.0",
                                          attribution="synthetic", retrieved_on=date(2026, 10, 29), by_name="Test",
                                          by_email="t@x.test")
            assert (out["row_count"], out["duplicate_rows"], out["rejected_rows"]) == (2, 1, 1)
            c.execute(text("INSERT INTO pol_case_cell_dataset (case_id, dataset_id, chosen_by) VALUES (:c, :d, 'Test')"),
                      {"c": case, "d": out["dataset_id"]})
            assert places.coverage(c, case, out["dataset_id"]) == {"tower_keys": 3, "resolved": 2}
            places.build(c, ext)
        placed = obs(engine, ext)
        assert [(o["source_kind"], o["radius_m"], o["radius_basis"]) for o in placed] == [
            ("cell_reference", 300.0, "cell_reference"), ("cell_reference", 4000.0, "cell_reference")]
        assert "reference_sparse" in placed[1]["attribution_flags"]  # 1 sample: at least 2,000 m, flagged
        with engine.connect() as c:
            missing = places.unplaced_towers(c, [ext])
        assert [(t["cid"], t["reason"]) for t in missing] == [(9999, "tower_not_in_reference_data")]
        assert places.TOWER_WORDS["tower_not_in_reference_data"] == "Tower not in reference data."


@needs_template
def test_a_bssid_anchors_on_two_days_of_nearby_gps_and_an_ssid_never_does(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            p = PlacePhone()
            for d in (0, 1):  # two days at the same place
                t = DAY + timedelta(days=d, hours=9)
                p.location(t)
                p.location(t + timedelta(minutes=2), lat=LAT + 0.0002)
                p.wifi(t + timedelta(minutes=1), bssid="AA-BB-CC-00-11-22")
                p.wifi(t + timedelta(minutes=1), ssid="SyntheticNet")  # SSID only
            t = DAY + timedelta(days=2, hours=9)
            p.location(t, lat=LAT + 0.1)
            p.wifi(t, bssid="aa:bb:cc:00:11:33")  # one day only
            ext = p.make(c, case)
        out = build(engine, ext)
        assert out["anchors:anchored"] == 1 and out["anchors:tentative"] == 1
        with engine.connect() as c:
            anchors = {r.bssid_norm: r for r in c.execute(text("SELECT * FROM pol_wifi_anchor WHERE case_id = :c"),
                                                           {"c": case})}
        assert set(anchors) == {"aa:bb:cc:00:11:22", "aa:bb:cc:00:11:33"}
        a = anchors["aa:bb:cc:00:11:22"]
        assert a.status == "anchored" and a.support_days == 2 and a.radius_m >= 75
        assert anchors["aa:bb:cc:00:11:33"].status == "tentative"
        wifi_obs = [o for o in obs(engine, ext) if o["source_kind"] == "wifi_case_anchor"]
        assert len(wifi_obs) == 2 and all(o["wifi_anchor_id"] == a.id for o in wifi_obs)  # never the tentative one


def test_reverse_geocoding_runs_only_on_an_in_house_backend():
    class B:
        def __init__(self, name, url=None):
            self.name, self._base_url = name, url
    assert places.reverse_geocoding_status(B("geonames"))["enabled"] is True
    assert places.reverse_geocoding_status(B("nominatim", "http://localhost:8080"))["enabled"] is True
    assert places.reverse_geocoding_status(B("nominatim", "http://10.1.2.3:8080"))["enabled"] is True
    assert places.reverse_geocoding_status(B("nominatim", "http://nominatim:8080"))["enabled"] is True
    off = places.reverse_geocoding_status(B("nominatim", "https://nominatim.openstreetmap.org"))
    assert off["enabled"] is False and "not in house" in off["reason"]
    assert places.reverse_geocoding_status(B("geonames"), B("nominatim", "https://geo.example.com"))["enabled"] is False


@needs_template
def test_places_over_http_with_totals_and_the_towers_not_placed(hooks):
    from tests.pattern_pg import api_client
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            p = PlacePhone()
            p.location(DAY)
            p.tower(DAY, 310, 260, 1, 2)
            ext = p.make(c, case)
        build(engine, ext)
        subj = json.dumps({"kind": "extraction", "extraction_id": str(ext)})
        with api_client(engine, case) as client:
            r = client.get("/api/pattern/%s/places" % case, params={
                "subject": subj, "start": (DAY - timedelta(hours=1)).isoformat(),
                "end": (DAY + timedelta(hours=1)).isoformat()})
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 1 and body["returned"] == 1 and body["next_cursor"] is None
            assert body["towers_not_placed"][0]["words"] == "Not placed: this case uses no cell tower reference data."
            assert client.post("/api/pattern/%s/reference/cell" % case, json={
                "file_path_on_server": "/etc/passwd", "name": "x", "licence": "x", "attribution": "x",
                "retrieved_on": "2026-10-29"}).status_code == 403  # admins only
