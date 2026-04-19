"""Shared OCR helpers: render PDF pages to PNG at 300 DPI and run Tesseract."""
from __future__ import annotations

import subprocess
import tempfile
import os
from pathlib import Path
from typing import List, Optional

from PIL import Image
import pytesseract


def ocr_pdf_pages(pdf_path: Path, first_page: int = 1, last_page: Optional[int] = None,
                   dpi: int = 300, psm: int = 6, lang: str = "eng",
                   rotate: int = 0) -> List[str]:
    """Render pages of a PDF to PNG and OCR each.  Returns one string per page.

    Args:
      pdf_path: source PDF
      first_page, last_page: 1-indexed inclusive page range (default: all pages)
      dpi: resolution for rendering (300 dpi is the sweet-spot for bank statements)
      psm: Tesseract page segmentation mode (6 = assume uniform block of text;
           4 = column of text; 3 = auto with OSD)
      lang: Tesseract language
      rotate: rotation angle in degrees (0, 90, 180, 270) — apply before OCR
    """
    if last_page is None:
        # Determine total page count via pdfinfo
        r = subprocess.run(["pdfinfo", str(pdf_path)], capture_output=True, text=True, check=True)
        for line in r.stdout.splitlines():
            if line.startswith("Pages:"):
                last_page = int(line.split(":", 1)[1].strip())
                break

    tmp = Path(tempfile.mkdtemp(prefix="ocr_"))
    try:
        # pdftoppm emits <prefix>-NNN.png
        subprocess.run([
            "pdftoppm", "-f", str(first_page), "-l", str(last_page),
            "-r", str(dpi), "-png", str(pdf_path), str(tmp / "p"),
        ], check=True, capture_output=True)

        texts: List[str] = []
        for pg in range(first_page, last_page + 1):
            # pdftoppm uses zero-padded page numbers matching total page digits
            # e.g. 83 pages → p-04.png; 130 pages → p-004.png
            width = len(str(last_page))
            img_path = tmp / f"p-{str(pg).zfill(width)}.png"
            if not img_path.exists():
                # Try other pad widths
                for w in (1, 2, 3, 4):
                    alt = tmp / f"p-{str(pg).zfill(w)}.png"
                    if alt.exists():
                        img_path = alt
                        break
                else:
                    texts.append("")
                    continue
            img = Image.open(img_path)
            if rotate:
                img = img.rotate(rotate, expand=True)
            text = pytesseract.image_to_string(img, lang=lang, config=f"--psm {psm}")
            texts.append(text)
        return texts
    finally:
        # Clean up temporary images
        for f in tmp.iterdir():
            try: f.unlink()
            except OSError: pass
        try: tmp.rmdir()
        except OSError: pass
