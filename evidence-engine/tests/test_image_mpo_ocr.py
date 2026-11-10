"""Camera photos saved as MPO (a JPEG with extra preview frames) are read, not refused.

Before: Tesseract refused them as "Unsupported image format/type"; 95 search photos in OPDMD63 and one in MH1
failed this way although each is an ordinary JPEG picture.
"""

from PIL import Image

from app.pipeline import extract_text as module


def _mpo(path):
    frames = [Image.new("RGB", (64, 48), (255, 255, 255)), Image.new("RGB", (32, 24), (0, 0, 0))]
    frames[0].save(path, format="MPO", save_all=True, append_images=frames[1:])
    assert Image.open(path).format == "MPO"


def test_mpo_photo_is_read_as_its_main_frame(monkeypatch, tmp_path):
    path = tmp_path / "DSCN0809.JPG"
    _mpo(path)
    seen = {}

    def fake_ocr(image, **kwargs):
        from pytesseract.pytesseract import prepare

        prepare(image)  # raises TypeError('Unsupported image format/type') for an MPO image
        seen["size"] = image.size
        return " PLATE ABC123 \n"

    monkeypatch.setattr("pytesseract.image_to_string", fake_ocr)
    assert module._extract_text_tesseract(str(path)) == "PLATE ABC123"
    assert seen["size"] == (64, 48)


def test_plain_jpeg_is_passed_unchanged(monkeypatch, tmp_path):
    path = tmp_path / "photo.jpg"
    Image.new("RGB", (20, 10)).save(path, format="JPEG")
    seen = {}

    def fake_ocr(image, **kwargs):
        seen["format"] = image.format
        return "x"

    monkeypatch.setattr("pytesseract.image_to_string", fake_ocr)
    assert module._extract_text_tesseract(str(path)) == "x"
    assert seen["format"] == "JPEG"
