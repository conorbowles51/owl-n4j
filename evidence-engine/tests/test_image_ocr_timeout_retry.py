"""A picture whose OCR times out under load is tried once more, not failed outright.

Before: two Thomas Keyes camera photos (case 80d1f81e, DSCF0034.JPG and DSCF0028.JPG) failed "Tesseract process
timeout" on 12 Nov 22:51 at host load 23-35 with no second try; sent again at load 13 they read without error.
"""

import pytest
from PIL import Image

from app.pipeline import extract_text as module


@pytest.fixture
def photo(tmp_path, monkeypatch):
    monkeypatch.setattr(module.settings, "image_ocr_retry_wait_seconds", 0)
    path = tmp_path / "DSCF0034.JPG"
    Image.new("RGB", (40, 30), (255, 255, 255)).save(path, format="JPEG")
    return str(path)


def _ocr(results, calls):
    def fake(image, **kwargs):
        calls.append(kwargs["timeout"])
        result = results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result
    return fake


def test_a_timeout_is_tried_once_more_and_the_text_kept(photo, monkeypatch):
    calls = []
    monkeypatch.setattr("pytesseract.image_to_string", _ocr([RuntimeError("Tesseract process timeout"), " PLATE "], calls))
    assert module._extract_text_tesseract(photo) == "PLATE"
    assert len(calls) == 2


def test_two_timeouts_fail_with_the_busy_server_reason(photo, monkeypatch):
    calls = []
    monkeypatch.setattr("pytesseract.image_to_string", _ocr([RuntimeError("Tesseract process timeout")] * 2, calls))
    with pytest.raises(RuntimeError, match="^Tesseract process timeout on both tries"):
        module._extract_text_tesseract(photo)
    assert len(calls) == 2


def test_any_other_error_is_not_tried_again(photo, monkeypatch):
    calls = []
    monkeypatch.setattr("pytesseract.image_to_string", _ocr([RuntimeError("Tesseract failed to load language")], calls))
    with pytest.raises(RuntimeError, match="load language"):
        module._extract_text_tesseract(photo)
    assert len(calls) == 1
