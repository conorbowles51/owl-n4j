"""A photo's place is not the phone's position (followups m111723091510458, Neil rule 1).

A Location record a photos app wrote ("Media Locations", "Media Probably Captured") says where a photo was taken. A
received photo keeps the sender's place: on the demo case Phone 5 got two warehouse "positions" from photos she
received. The point is stored as ``media_place``; the area, together and place readers keep it apart from positions.
Each test fails on the old code, which stored it as ``device_location``.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import text

from services.pattern_of_life import places
from services.phone import generic
from tests.test_phone_mappings import hooks  # noqa: F401 (fixture)


def test_a_photo_category_is_a_media_place_and_a_device_fix_stays_a_device_location():
    assert generic.source_kind("Location", "Device", "Media Locations") == "media_place"
    assert generic.source_kind("Location", None, "Media Probably Captured") == "media_place"
    assert generic.source_kind("Location", "Account", "Media Probably Captured") == "media_place"
    assert generic.source_kind("Location", "Device", "Locations") == "device_location"
    assert generic.source_kind("Location", None, None) == "device_location"
    assert generic.source_kind("Location", "Device", "Snapchat Gallery Upload") == "device_location"
    assert generic.source_kind("WirelessNetwork", None, "Media Locations") == "wifi"


def test_pattern_of_life_reads_any_media_place_as_media_not_presence():
    facts = {"fields": {"Category": ["Media Probably Captured"], "Type": ["Visited"]}}
    kind, source, basis, extra = places.classify_point("Location", "media_place", "unknown", facts, [])
    assert (kind, source) == ("media", "media_exif") and "media_device_not_established" in extra


def _setup():
    from tests.test_pattern_u4_availability import DAY
    from tests.test_places_rest import MediaPhone
    p = MediaPhone()
    p.location(DAY, lat=40.0, lon=-74.0)  # a fix of the phone itself
    received = p.photo(DAY + timedelta(hours=1), lat=41.0, lon=-73.0)  # a photo received, taken elsewhere
    return p, received


def test_a_received_photo_does_not_put_the_phone_in_the_area_or_together(hooks):
    import pytest
    from services.phone import map as M
    from services.relations import together
    from tests.phone_pg import TEMPLATE_URL, fresh_engine, make_case, make_extraction
    from tests.test_pattern_u4_availability import DAY, setup
    from tests.test_pattern_u5_places import build
    from services.phone import registry
    if not TEMPLATE_URL:
        pytest.skip("Requires LOUPE_TEST_PHONE_PG_TEMPLATE_URL")
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            p, _ = _setup()
            ext = make_extraction(c, case, p.records, timestamps=p.stamps)
            q, _ = _setup()  # a second phone with a real fix at the photo's place and time
            q.location(DAY + timedelta(hours=1), lat=41.0, lon=-73.0)
            other = make_extraction(c, case, q.records, timestamps=q.stamps)
        build(engine, ext)
        build(engine, other)
        with engine.connect() as c:
            kinds = sorted(r[0] for r in c.execute(text(
                "SELECT source_kind FROM phone_location_points WHERE extraction_id = :e"), {"e": ext}))
            assert kinds == ["device_location", "media_place"]
            square = [[-73.01, 40.99], [-72.99, 40.99], [-72.99, 41.01], [-73.01, 41.01]]
            out = M.area(c, case, square, {})
            assert [d["extraction_id"] for d in out["phones"]] == [str(other)]
            assert out["photo_places_total"] == 2 and out["points_total"] == 1
            cells, read = together.cells(c, str(case), [str(ext), str(other)], None, None)
            # both phones' own fixes meet at the first place; the photo's place meets nothing
            assert [round(x["lat"]) for x in cells] == [40] and read["positions"] == 3
        # a point written by the old code is re-derived through the same rule, and the phone's places are rebuilt
        with engine.begin() as c:
            c.execute(text("UPDATE phone_location_points SET source_kind = 'device_location' WHERE extraction_id = :e"),
                      {"e": ext})
            dry = generic.reclassify_media_places(c, str(case))
            assert dry["points"] == 1 and dry["by_case"] == {str(case): {"device_location": 1}} and not dry["rebuilt"]
            done = generic.reclassify_media_places(c, str(case), apply=True)
            assert done["points"] == 1 and str(ext) in done["rebuilt"]
        with engine.connect() as c:
            assert sorted(r[0] for r in c.execute(text(
                "SELECT source_kind FROM phone_location_points WHERE extraction_id = :e"), {"e": ext})) == [
                "device_location", "media_place"]
            assert generic.reclassify_media_places(c, str(case))["points"] == 0
