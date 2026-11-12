"""A photo's own data (date taken, place, camera) is kept by processing, not dropped.

Before: processing kept width, height, format and only four EXIF text tags; the place the photo was taken was lost.
"""
from PIL import Image

from services import photo_metadata as pm


def _jpeg(path, *, date=None, offset=None, gps=None, make=None, model=None, altitude=None, below=False):
    exif = Image.Exif()
    if make:
        exif[0x010F] = make
    if model:
        exif[0x0110] = model
    sub = {}
    if date:
        sub[0x9003] = date
    if offset:
        sub[0x9011] = offset
    if sub:
        exif.get_ifd(0x8769).update(sub)
    if gps:
        g = exif.get_ifd(0x8825)
        g[1], g[2], g[3], g[4] = gps[0], gps[1], gps[2], gps[3]
        if altitude is not None:
            g[5], g[6] = (1 if below else 0), altitude
    Image.new("RGB", (40, 30), "white").save(path, format="JPEG", exif=exif)
    return str(path)


def test_date_place_camera_and_size_are_read(tmp_path):
    path = _jpeg(tmp_path / "a.jpg", date="2024:05:01 12:30:15", offset="+01:00", make="FUJIFILM", model="X-T3",
                 gps=("N", (51.0, 30.0, 0.0), "W", (0.0, 7.0, 30.0)), altitude=35.5)
    got = pm.read_photo_metadata(path)
    assert got["date_taken"] == {"local": "2024-05-01T12:30:15", "offset": "+01:00", "field": "DateTimeOriginal"}
    assert got["gps"] == {"latitude": 51.5, "longitude": -0.125, "altitude_m": 35.5}
    assert got["camera"] == {"make": "FUJIFILM", "model": "X-T3"}
    assert (got["width"], got["height"]) == (40, 30)


def test_south_west_and_below_sea_level(tmp_path):
    path = _jpeg(tmp_path / "b.jpg", gps=("S", (10.0, 0.0, 0.0), "W", (20.0, 0.0, 0.0)), altitude=3.0, below=True)
    gps = pm.read_photo_metadata(path)["gps"]
    assert (gps["latitude"], gps["longitude"], gps["altitude_m"]) == (-10.0, -20.0, -3.0)


def test_nothing_is_invented_when_the_file_holds_nothing(tmp_path):
    path = _jpeg(tmp_path / "c.jpg")
    got = pm.read_photo_metadata(path)
    assert set(got) == {"width", "height"}


def test_date_only_has_no_place_and_no_offset(tmp_path):
    got = pm.read_photo_metadata(_jpeg(tmp_path / "d.jpg", date="2023:12:31 23:59:59"))
    assert got["date_taken"]["offset"] is None and "gps" not in got


def test_unset_camera_clock_is_not_a_date(tmp_path):
    got = pm.read_photo_metadata(_jpeg(tmp_path / "e.jpg", date="0000:00:00 00:00:00"))
    assert "date_taken" not in got


def test_zero_zero_place_is_not_a_place(tmp_path):
    got = pm.read_photo_metadata(_jpeg(tmp_path / "f.jpg", gps=("N", (0.0, 0.0, 0.0), "E", (0.0, 0.0, 0.0))))
    assert "gps" not in got


def test_not_a_picture_reads_as_empty(tmp_path):
    path = tmp_path / "g.jpg"
    path.write_bytes(b"not an image")
    assert pm.read_photo_metadata(str(path)) == {}


def test_record_is_labelled_as_read_by_the_system(tmp_path):
    record = pm.photo_data_record(_jpeg(tmp_path / "h.jpg", date="2024:01:02 03:04:05"), read_by="backfill")
    assert record["confirmed_by"] is None and record["read_by"] == "backfill" and record["source"] == "photo_data"
