"""Processing an image keeps the photo's date, place and camera under ``photo_data`` (it dropped the place before)."""
from PIL import Image

from app.pipeline import extract_text as module


def test_extract_image_metadata_keeps_photo_data(tmp_path):
    exif = Image.Exif()
    exif[0x010F] = "Apple"
    exif.get_ifd(0x8769)[0x9003] = "2024:05:01 12:30:15"
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2], gps[3], gps[4] = "N", (51.0, 30.0, 0.0), "W", (0.0, 7.0, 30.0)
    path = tmp_path / "p.jpg"
    Image.new("RGB", (10, 10)).save(path, format="JPEG", exif=exif)
    metadata = module._extract_image_metadata(str(path))
    photo = metadata["photo_data"]
    assert photo["gps"]["latitude"] == 51.5 and photo["date_taken"]["local"] == "2024-05-01T12:30:15"
    assert photo["camera"] == {"make": "Apple"} and photo["confirmed_by"] is None
    assert metadata["width"] == 10


def test_image_without_data_is_recorded_as_read_and_empty(tmp_path):
    path = tmp_path / "q.png"
    Image.new("RGB", (10, 10)).save(path, format="PNG")
    photo = module._extract_image_metadata(str(path))["photo_data"]
    # read, and the file holds none of it: absent keys, so a screen can say which values the file lacked
    assert not {"date_taken", "gps", "camera"} & set(photo)
