"""Ordinary camera photos pass the image pixel guard; decompression bombs are still refused.

Before: the guard sat at 25,000,000 pixels, and 369 Fujifilm photos (6240x4160 = 25,958,400 pixels) in one case
failed with "Image has 25958400 pixels; the configured limit is 25000000 pixels".
"""

import re
from pathlib import Path

import pytest
from PIL import Image

from app.config import Settings
from app.pipeline import extract_text as module


def _fake_metadata(width, height):
    return lambda _path: {"file_type": "image", "width": width, "height": height, "format": "JPEG"}


@pytest.mark.asyncio
@pytest.mark.parametrize("width,height", [(6240, 4160), (9504, 6336), (11648, 8736)])  # 26, 61, 102 MP
async def test_camera_photo_sizes_are_read(monkeypatch, tmp_path, width, height):
    path = tmp_path / "DSCF0069.JPG"
    Image.new("RGB", (8, 8)).save(path, format="JPEG")
    monkeypatch.setattr(module.settings, "max_image_pixels", Settings.model_fields["max_image_pixels"].default)
    monkeypatch.setattr(module.settings, "image_provider", "tesseract")
    monkeypatch.setattr(module, "_extract_image_metadata", _fake_metadata(width, height))
    monkeypatch.setattr(module, "_extract_text_tesseract", lambda _path: "read")
    document = await module._extract_image(str(path), path.name)
    assert document.text == "read"


@pytest.mark.asyncio
async def test_decompression_bomb_is_still_refused(monkeypatch, tmp_path):
    path = tmp_path / "bomb.png"
    Image.new("RGB", (8, 8)).save(path, format="PNG")
    monkeypatch.setattr(module.settings, "max_image_pixels", Settings.model_fields["max_image_pixels"].default)
    monkeypatch.setattr(module, "_extract_image_metadata", _fake_metadata(20000, 20000))
    with pytest.raises(ValueError, match="Image has 400000000 pixels"):
        await module._extract_image(str(path), path.name)


def test_guard_stays_below_pillows_own_refusal():
    default = Settings.model_fields["max_image_pixels"].default
    assert 102_000_000 <= default < 2 * Image.MAX_IMAGE_PIXELS


def test_large_photo_is_scaled_down_before_ocr(monkeypatch, tmp_path):
    path = tmp_path / "big.jpg"
    Image.new("RGB", (400, 300), (255, 255, 255)).save(path, format="JPEG")
    monkeypatch.setattr(module.settings, "image_ocr_max_pixels", 30_000)
    seen = {}

    def fake_ocr(image, **kwargs):
        seen["size"] = image.size
        return "x"

    monkeypatch.setattr("pytesseract.image_to_string", fake_ocr)
    assert module._extract_text_tesseract(str(path)) == "x"
    width, height = seen["size"]
    assert width * height <= 30_000 and abs(width / height - 4 / 3) < 0.02


def test_compose_default_matches_the_engine_default():
    compose = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text()
    defaults = set(re.findall(r"MAX_IMAGE_PIXELS: \$\{MAX_IMAGE_PIXELS:-(\d+)\}", compose))
    assert defaults == {str(Settings.model_fields["max_image_pixels"].default)}
