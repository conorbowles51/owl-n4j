"""Approach 6, other devices and accounts in play (05 section 9.8 tests 1 to 3; cb-gated-spread G). Invented data
only."""
from __future__ import annotations

import pytest

from services.phone_analysis import approaches
from services.phone_analysis import framework as F
from services.phone_analysis import other_devices as O
from tests.phone_analysis_fixture import record
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone


@pytest.fixture
def engine():
    with fresh_engine() as e:
        yield e


def _wifi(c, case, ext, o, bssid, ssid):
    return record(c, case, ext, o, "WirelessNetwork", fields=[("BSSId", "String", bssid), ("SSId", "String", ssid)],
                  times=[("LastConnection", at(2023, 3, 1, 9))])


def test_rules_by_hand():
    assert O.registrable_domain("https://login.example.co.uk/path") == "example.co.uk"
    assert O.registrable_domain(".mail.example.com") == "example.com"
    assert O.registrable_domain("192.168.0.1") is None and O.registrable_domain("not a host") is None
    assert O.norm_bssid("AA-BB-CC-00-11-22") == "aa:bb:cc:00:11:22" and O.norm_bssid("00:00:00:00:00:00") is None
    assert O.user_agent_family("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)") == ("Phone", "iOS")
    lv, match, _, under = O.grade("bluetooth_name", [{"events": 3, "natures": {"Detected"}},
                                                     {"events": 1, "natures": {"Connected"}}], 2)
    assert lv == "faint" and "detected_not_connected" in under and "One level lower" in match[1]
    assert O.grade("account", [{"events": 1, "natures": set()}] * 2, 2)[0] == "moderate"


@needs_template
def test_shared_bssid_strong_ssid_weak_only(engine):
    """9.8.1: one BSSID on two phones is shared, strong; one SSID 'Home' on two phones with different BSSIDs is
    listed under weak name matches only."""
    with engine.begin() as c:
        case = make_case(c)
        x, _ = phone(c, case, label="C1", events=[])
        y, _ = phone(c, case, label="C2", owner="phone:+12025550111", events=[])
        _wifi(c, case, x, 100, "aa:bb:cc:00:11:22", "Office")
        _wifi(c, case, y, 100, "AA-BB-CC-00-11-22", "Office")
        _wifi(c, case, x, 101, "aa:bb:cc:00:00:01", "Home")
        _wifi(c, case, y, 101, "aa:bb:cc:00:00:02", "Home")
    with engine.connect() as c:
        res, counts = O.analyse(c, case, {})
    shared = [r for r in res if r["kind"] == "shared_key"]
    by = {(r["measures"]["key_kind"], r["measures"]["value"]): r for r in shared}
    assert by[("wifi_bssid", "aa:bb:cc:00:11:22")]["strength"] == "strong"
    assert by[("ssid", "Home")]["strength"] == "weak"
    # the network name explained by the shared access point is said in that row, not listed twice
    assert ("ssid", "Office") not in by and counts["ssid_with_shared_bssid"] == 1
    assert not any(r["measures"]["key_kind"] == "wifi_bssid" and r["measures"]["value"] != "aa:bb:cc:00:11:22"
                   for r in shared)
    b = by[("wifi_bssid", "aa:bb:cc:00:11:22")]
    assert b["measures"]["reasons"]["match"] and b["measures"]["reasons"]["substantiation"]
    assert b["measures"]["reasons"]["substantiation"][0].startswith("Records or events behind it on each phone: ")
    assert counts["shared_strong"] == 1 and counts["shared_weak"] == 1


@needs_template
def test_medium_key_is_a_moderate_row(engine):
    """G (fails on the old code, which listed no cross-phone key below strong): the same saved-login account on
    one service on two phones is a moderate cross-phone row; its value is not shown."""
    with engine.begin() as c:
        case = make_case(c)
        x, _ = phone(c, case, label="C1", events=[])
        y, _ = phone(c, case, label="C2", owner="phone:+12025550111", events=[])
        for e in (x, y):
            record(c, case, e, 100, "Password", fields=[("Service", "String", "mail.example.com"),
                                                         ("Account", "String", "someone@example.com")])
    approaches.install()
    with engine.connect() as c:
        res, _ = O.analyse(c, case, {})
    (row,) = [r for r in res if r["kind"] == "shared_key" and r["measures"]["key_kind"] == "saved_login"]
    assert row["strength"] == "moderate" and row["measures"]["value"] is None
    assert "someone" not in str(row)
    # the service domain behind both saved logins is listed too, weak
    (svc,) = [r for r in res if r["kind"] == "shared_key" and r["measures"]["key_kind"] == "service"]
    assert svc["strength"] == "weak" and svc["measures"]["value"] == "example.com"


@needs_template
def test_detected_only_peer_is_nearby_not_connected(engine):
    """9.8.2."""
    with engine.begin() as c:
        case = make_case(c)
        x, _ = phone(c, case, label="C1", events=[])
        y, _ = phone(c, case, label="C2", owner="phone:+12025550111", events=[])
        record(c, case, x, 100, "DeviceConnectivity", fields=[("DeviceName", "String", "Car Kit"),
                                                               ("ConnectivityMethod", "ConnectivityMethod", "Bluetooth"),
                                                               ("ConnectivityNature", "ConnectivityNature", "Detected")],
               times=[("StartTime", at(2023, 3, 2, 8))])
        record(c, case, y, 100, "DeviceConnectivity", fields=[("DeviceName", "String", "car kit"),
                                                               ("ConnectivityMethod", "ConnectivityMethod", "Bluetooth"),
                                                               ("ConnectivityNature", "ConnectivityNature", "Connected")])
    with engine.connect() as c:
        res, _ = O.analyse(c, case, {})
    (row,) = [r for r in res if r["kind"] == "shared_key"]
    assert row["strength"] == "faint"
    p1 = next(p for p in row["measures"]["phones"] if p["phone_label"] == "C1")
    assert p1["nearby_only"] and p1["natures"] == ["Detected"]
    assert any(u["code"] == "detected_not_connected" for u in row["directions"]["undercuts"])
    inv = next(r for r in res if r["kind"] == "phone_inventory" and r["measures"]["phone_label"] == "C1")
    assert inv["measures"]["bluetooth_nearby_only"] == 1


@needs_template
def test_service_without_app_and_no_comparison_without_apps(engine):
    """9.8.3: a cookie for a domain with no installed app on a phone that has InstalledApplication data is "service
    without app"; on a phone without that type the comparison is not made, and that is stated."""
    with engine.begin() as c:
        case = make_case(c)
        x, _ = phone(c, case, label="C1", events=[])
        y, _ = phone(c, case, label="C2", owner="phone:+12025550111", events=[])
        record(c, case, x, 100, "InstalledApplication", fields=[("Identifier", "String", "com.example.chat")])
        record(c, case, x, 101, "Cookie", fields=[("Domain", "String", ".shop.invented-bank.com")])
        record(c, case, x, 102, "Cookie", fields=[("Domain", "String", "www.example.com")])
        record(c, case, y, 101, "Cookie", fields=[("Domain", "String", "invented-bank.com")])
    with engine.connect() as c:
        res, _ = O.analyse(c, case, {})
    swa = [r for r in res if r["kind"] == "service_without_app"]
    assert [(r["measures"]["phone_label"], r["measures"]["service"], r["strength"]) for r in swa] == [
        ("C1", "invented-bank.com", "weak")]
    inv = {r["measures"]["phone_label"]: r for r in res if r["kind"] == "phone_inventory"}
    assert inv["C1"]["measures"]["apps_compared"] is True
    assert inv["C2"]["measures"]["apps_compared"] is False and inv["C2"]["measures"]["no_app_words"]
    assert any(u["code"] == "no_app_data" for u in inv["C2"]["directions"]["undercuts"])


@needs_template
def test_runs_through_the_framework(engine):
    """The approach is registered, runs on a case with any data (no count gate) and writes its results."""
    approaches.install()
    with engine.begin() as c:
        case = make_case(c)
        x, _ = phone(c, case, label="C1", events=[])
        y, _ = phone(c, case, label="C2", owner="phone:+12025550111", events=[])
        _wifi(c, case, x, 100, "aa:bb:cc:00:11:22", "Office")
        _wifi(c, case, y, 100, "aa:bb:cc:00:11:22", "Office")
        run, created = F.request_run(c, case, "other_devices", {}, "tester@example.com")
    assert created
    out = F.execute(engine, run["id"])
    assert out["status"] == "completed", out
    with engine.connect() as c:
        page = F.results(c, case, run["id"], kind="shared_key")
        done = F.get_run(c, case, run["id"])
    assert page["total"] == 1 and page["items"][0]["strength"] == "strong"
    assert done["counts"]["shared_strong"] == 1
