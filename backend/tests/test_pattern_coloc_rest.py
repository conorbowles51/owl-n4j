"""cb-coloc-rest: Bluetooth and SIM-inferred cells as co-location evidence (04 sections 6.2, 8.4).

Synthetic phones only: every name, address, number and tower key here is invented. Opt-in PostgreSQL through
``LOUPE_TEST_PHONE_PG_TEMPLATE_URL``.
"""
from __future__ import annotations

import random
import time
from datetime import timedelta

from sqlalchemy import text

from services.pattern_of_life import colocation, places
from services.phone import identifiers, identities, registry, sweep
from tests.phone_pg import fld, fresh_engine, make_case, make_extraction, model, needs_template
from tests.test_pattern_u4_availability import DAY, _stamp, setup
from tests.test_pattern_u5_places import PlacePhone, build
from tests.test_phone_mappings import hooks  # noqa: F401 (fixture)

B_ADDRESS = "0A:1B:2C:3D:4E:5F"  # invented; a locally administered address
B_NAME = "Synthetic Handset B"


class ColocPhone(PlacePhone):
    def __init__(self, metadata=None):
        super().__init__()
        self.metadata = dict({"MSISDN": "+12025550100"}, **(metadata or {}))

    def bt_peer(self, when, name, nature="Connected", method="Bluetooth"):
        f = [fld("StartTime", ("TimeStamp", when.isoformat())), fld("DeviceName", ("String", name)),
             fld("ConnectivityMethod", ("ConnectivityMethod", method)),
             fld("ConnectivityNature", ("ConnectivityNature", nature))]
        self.records.append((self.o, None, self.o, model("DeviceConnectivity", f)))
        self.stamps.append(_stamp(self.o, "StartTime", "DeviceConnectivity", when))
        self.o += 1

    def tower_no_mcc(self, when, mnc, lac, cid, radio="GSM"):
        f = [fld("TimeStamp", ("TimeStamp", when.isoformat())), fld("MNC", ("Int32", str(mnc))),
             fld("LAC", ("Int32", str(lac))), fld("CID", ("Int32", str(cid))),
             fld("CellTowerType", ("CellTowerType", radio))]
        self.records.append((self.o, None, self.o, model("CellTower", f)))
        self.stamps.append(_stamp(self.o, "TimeStamp", "CellTower", when))
        self.o += 1

    def make(self, c, case, extraction_start=None):
        return make_extraction(c, case, self.records or [(0, None, 0, model("Note", []))], timestamps=self.stamps,
                               metadata=self.metadata)


# ---- pure rules --------------------------------------------------------------------------------------------------

def test_bluetooth_addresses_and_names_normalise_and_placeholders_are_not_devices():
    for raw in ("0A:1B:2C:3D:4E:5F", "0a-1b-2c-3d-4e-5f", "0A1B2C3D4E5F", "0a1b.2c3d.4e5f"):
        assert identifiers.bluetooth_address(raw) == "0a:1b:2c:3d:4e:5f"
    for raw in ("02:00:00:00:00:00", "00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF", "0A:1B:2C", "Car Kit", ""):
        assert identifiers.bluetooth_address(raw) is None
    assert identifiers.bluetooth_name("  Synthetic   HANDSET b ") == "synthetic handset b"
    assert identifiers.bluetooth_peer("0a1b2c3d4e5f") == ("bluetooth_address", "0a:1b:2c:3d:4e:5f")
    assert identifiers.bluetooth_peer(B_NAME) == ("bluetooth_name", "synthetic handset b")
    ident = identifiers.bluetooth(B_ADDRESS, "bluetooth_address")
    assert (ident.kind, ident.subkind, ident.identity_key) == (
        "other", "bluetooth_address", "other:bluetooth_address:0a:1b:2c:3d:4e:5f")


def test_a_factory_default_bluetooth_name_is_recognised_and_a_personal_one_is_not():
    for name in ("iPhone", "Galaxy A02s", "galaxy s21 ultra", "Pixel 7 Pro", "moto g play - 2023", "iPhone 15 Pro Max",
                 "Samsung Galaxy Note 20", "OnePlus Nord 2"):
        assert identifiers.default_device_name(name), name
    for name in ("Synthetic Handset B", "Sam's iPhone", "iPhone de Sam", "Galaxy of Sam", "Car Kit", "", None):
        assert not identifiers.default_device_name(name), name
    assert identifiers.default_device_name("Model X1", models=["MODEL  x1"])  # the report's own model name
    assert not identifiers.default_device_name("Model X1", models=["Model X2"])


def test_a_tower_without_mcc_takes_the_sims_only_when_exactly_one_is_known():
    body = model("CellTower", [fld("MNC", ("Int32", "7")), fld("LAC", ("Int32", "100")), fld("CID", ("Int32", "9"))])
    k, flags, reason = places.resolve_tower_key(body, {999})
    assert (k["mcc"], flags, reason) == (999, ["mcc_inferred"], None)
    assert places.resolve_tower_key(body, set())[1:] == ([], "mcc_unknown_no_sim")
    assert places.resolve_tower_key(body, {998, 999})[1:] == ([], "mcc_unknown_several_sims")
    full = model("CellTower", [fld("MCC", ("Int32", "998")), fld("MNC", ("Int32", "7")), fld("LAC", ("Int32", "100")),
                               fld("CID", ("Int32", "9"))])
    assert places.resolve_tower_key(full, {999}) == (dict(k, mcc=998), [], None)  # a stated MCC is never replaced
    no_cid = model("CellTower", [fld("MNC", ("Int32", "7")), fld("LAC", ("Int32", "100"))])
    assert places.resolve_tower_key(no_cid, {999})[2] == "key_incomplete"
    for w in ("mcc_unknown_no_sim", "mcc_unknown_several_sims"):
        assert places.TOWER_WORDS[w]


def _nested(A, B, window_s):
    """The comparison the keyed join replaced (colocation._cell_pairs before cb-coloc-rest E)."""
    w = timedelta(seconds=window_s)
    return [(x, y) for x in A for y in B if x[0] == y[0] and abs(x[1] - y[1]) <= w]


def test_the_keyed_cell_join_returns_exactly_the_nested_loops_pairs_and_is_faster():
    rnd = random.Random(7)
    keys = [("GSM", 999, 7, 100 + i, i) for i in range(40)]

    def side(n, tag):
        return [(rnd.choice(keys), DAY + timedelta(seconds=rnd.randrange(0, 6 * 3600)), "%s%d" % (tag, i), [])
                for i in range(n)]
    A, B = side(3000, "a"), side(3000, "b")
    t0 = time.perf_counter()
    want = _nested(A, B, 900)
    t_nested = time.perf_counter() - t0
    t0 = time.perf_counter()
    got = colocation.cell_matches(A, B, 900)
    t_join = time.perf_counter() - t0
    key = lambda p: (p[0][2], p[1][2])  # noqa: E731
    assert sorted(got, key=key) == sorted(want, key=key) and len(want) > 1000
    assert t_join < t_nested


# ---- through the real pipeline --------------------------------------------------------------------------------

def _run(engine, case, ea, eb, start=DAY - timedelta(hours=1), end=DAY + timedelta(hours=3)):
    with engine.begin() as c:
        items, counts, eps = colocation.compute(c, str(case), [str(ea)], [str(eb)], start, end, {})
    return items, counts, eps


@needs_template
def test_the_phones_own_bluetooth_identity_is_a_cited_header_sighting(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            eb = ColocPhone({"Bluetooth MAC Address": B_ADDRESS, "DeviceInfoBluetoothDeviceName": B_NAME}).make(c, case)
        assert sweep.interpret_one(engine, eb)["status"] == "done"
        with engine.connect() as c:
            own = identities.own_bluetooth(c, [eb])[str(eb)]
            rows = c.execute(text(
                "SELECT x.field_path, x.context, x.identifier_raw, i.kind, i.subkind FROM phone_identity_sightings x "
                "JOIN phone_identities i ON i.id = x.identity_id WHERE x.extraction_id = :e AND i.subkind LIKE "
                "'bluetooth%' ORDER BY 1"), {"e": eb}).fetchall()
            owners = c.execute(text("SELECT count(*) FROM phone_owner_candidates WHERE extraction_id = :e AND "
                                    "identity_key LIKE 'other:bluetooth%'"), {"e": eb}).scalar()
        assert [tuple(r) for r in rows] == [
            ("metadata:Bluetooth MAC Address", "header", B_ADDRESS, "other", "bluetooth_address"),
            ("metadata:DeviceInfoBluetoothDeviceName", "header", B_NAME, "other", "bluetooth_name")]
        assert set(own) == {("bluetooth_address", "0a:1b:2c:3d:4e:5f"), ("bluetooth_name", "synthetic handset b")}
        assert owners == 0  # an identifier of the device, never an owner candidate
        with engine.begin() as c:  # an Android report stating both: the device name is not a second Bluetooth name
            both = ColocPhone({"DeviceInfoBluetoothDeviceName": B_NAME, "DeviceInfoDeviceName": "Model X1"}).make(c, case)
        assert sweep.interpret_one(engine, both)["status"] == "done"
        with engine.connect() as c:
            assert set(identities.own_bluetooth(c, [both])[str(both)]) == {("bluetooth_name", "synthetic handset b")}
        # the stage's version is part of the interpreter version, so every phone read before is read again
        now = sweep.interpreter_version()
        try:
            del identities.build.stage_version
            assert sweep.interpreter_version() != now
        finally:
            identities.build.stage_version = 2
        assert sweep.interpreter_version() == now


@needs_template
def test_a_peer_record_naming_the_other_phone_is_bluetooth_evidence(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            a = ColocPhone()
            a.bt_peer(DAY, B_ADDRESS.replace(":", "").lower(), nature="Connected")  # by address
            a.bt_peer(DAY + timedelta(hours=1), B_NAME.upper(), nature="Detected")  # by name, a scan
            a.bt_peer(DAY + timedelta(hours=2), "Some Car Kit", nature="Connected")  # names neither phone
            a.bt_peer(DAY + timedelta(minutes=30), B_NAME, nature="Connected", method="WiFi")  # not Bluetooth
            ea = a.make(c, case)
            eb = ColocPhone({"Bluetooth MAC Address": B_ADDRESS, "DeviceInfoBluetoothDeviceName": B_NAME}).make(c, case)
        build(engine, ea)
        build(engine, eb)
        items, counts, eps = _run(engine, case, ea, eb)
        bt = [i for i in items if i["basis"] == "bluetooth"]
        assert counts["basis:bluetooth"] == 2 and counts["analysis_version"] == colocation.ANALYSIS_VERSION
        by_addr, by_name = bt
        assert (by_addr["verdict"], by_addr["r"], by_addr["tight"], by_addr["at_utc"]) == ("compatible", 30.0, True, DAY)
        assert "name_match" not in by_addr["flags"] and by_addr["ar"].startswith("rec:")
        assert by_addr["br"].startswith("ident:")  # cites the other phone's header sighting
        assert by_name["tight"] is False and {"name_match", "nearby_not_connected"} <= set(by_name["flags"])
        # the same detection read from the other side: the record is on A, so it stays the A side of the pair
        items2, counts2, _ = _run(engine, case, eb, ea)
        assert counts2["basis:bluetooth"] == 2
        assert all(i["ar"].startswith("ident:") and i["br"].startswith("rec:") for i in items2
                   if i["basis"] == "bluetooth")
        # an hour apart, so two episodes: the address match is tight, the name match only broad
        assert [(e["kind"], e["breadth"]) for e in eps] == [("together", "tight"), ("together", "broad")]


@needs_template
def test_a_tower_without_mcc_is_compared_with_the_sims_mcc_and_flagged(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            a = ColocPhone({"IMSI": "999070123456789"})  # invented test network 999
            a.tower_no_mcc(DAY, 7, 100, 9)
            a.tower_no_mcc(DAY + timedelta(hours=1), 7, 100, 10)
            ea = a.make(c, case)
            b = ColocPhone()
            b.tower(DAY + timedelta(minutes=10), 999, 7, 100, 9)
            eb = b.make(c, case)
            n = ColocPhone()  # no SIM data: its towers stay unresolved with the reason
            n.tower_no_mcc(DAY, 7, 100, 9)
            en = n.make(c, case)
        for e in (ea, eb, en):
            build(engine, e)
        items, counts, _ = _run(engine, case, ea, eb)
        cells = [i for i in items if i["basis"] == "shared_cell"]
        assert len(cells) == 1 and set(cells[0]["flags"]) == {"broad", "mcc_inferred"}
        assert cells[0]["dt"] == 600.0
        assert _run(engine, case, en, eb)[1].get("basis:shared_cell", 0) == 0
        with engine.connect() as c:
            ua = places.unplaced_towers(c, [ea])
            un = places.unplaced_towers(c, [en])
        assert [(t["mcc"], t["mcc_inferred"], t["reason"]) for t in ua] == [(999, True, "no_reference_dataset")] * 2
        assert [(t["mcc"], t["mcc_inferred"], t["reason"]) for t in un] == [(None, False, "mcc_unknown_no_sim")]


@needs_template
def test_a_phone_whose_bluetooth_name_is_its_factory_default_is_not_compared_by_name_and_is_counted(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            a = ColocPhone()
            a.bt_peer(DAY, "Galaxy A02s", nature="Detected")  # any phone of that model would be seen so
            a.bt_peer(DAY + timedelta(minutes=10), "Model X1", nature="Detected")  # the report's own model name
            a.bt_peer(DAY + timedelta(minutes=20), B_ADDRESS, nature="Connected")  # the address still matches
            ea = a.make(c, case)
            eb = ColocPhone({"Bluetooth MAC Address": B_ADDRESS, "DeviceInfoBluetoothDeviceName": "Galaxy A02s"}
                            ).make(c, case)
            ec = ColocPhone({"DeviceInfoBluetoothDeviceName": "Model X1", "DeviceInfoSelectedDeviceName": "Model X1"}
                            ).make(c, case)
        for e in (ea, eb, ec):
            build(engine, e)
        items, counts, _ = _run(engine, case, ea, eb)
        bt = [i for i in items if i["basis"] == "bluetooth"]
        assert len(bt) == 1 and "name_match" not in bt[0]["flags"]  # only the address
        assert counts["not_compared:default_device_name"] == 1 and counts["analysis_version"] == 3
        items, counts, _ = _run(engine, case, ea, ec)
        assert [i for i in items if i["basis"] == "bluetooth"] == []
        assert counts["not_compared:default_device_name"] == 1
