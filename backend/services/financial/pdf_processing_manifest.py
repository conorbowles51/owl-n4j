"""Check the bounded runtime record captured during PDF preparation."""
import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field

Text = Annotated[str, Field(strict=True,min_length=1,max_length=2048)]
Digest = Annotated[str, Field(strict=True,pattern=r'^[a-f0-9]{64}$')]

class _Settings(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    pdf_ocr_dpi:int
    pdf_ocr_max_pixels:int
    pdf_ocr_page_timeout_seconds:int
    pdf_ocr_max_concurrency:int
    tesseract_lang:Text
    max_pdf_pages:int

class _Tesseract(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    status:Literal['reported','unavailable','not_used']
    version:Text|None

class _Content(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    schema_version:Literal['loupe.pdf_processing_manifest/1']
    recorded_at:Text
    python_version:Text
    packages:dict[Literal['PyMuPDF','pytesseract','Pillow'],Text|None]
    source_files_sha256:dict[Literal['pdf_extraction.py','ocr_geometry.py','pdf_processing_manifest.py'],Digest|None]
    tesseract:_Tesseract
    settings:_Settings
    limitation:Text


def validate_pdf_processing_manifest(value):
    if value is None:return None
    if not isinstance(value,dict) or set(value)!={'content','sha256'}:
        raise ValueError('Malformed PDF processing record.')
    content=_Content.model_validate(value['content'])
    if set(content.packages)!={'PyMuPDF','pytesseract','Pillow'} or set(content.source_files_sha256)!={'pdf_extraction.py','ocr_geometry.py','pdf_processing_manifest.py'}:
        raise ValueError('Incomplete PDF processing record inventory.')
    if (content.tesseract.status=='reported') != (content.tesseract.version is not None):
        raise ValueError('Inconsistent OCR version record.')
    if datetime.fromisoformat(content.recorded_at).tzinfo is None:
        raise ValueError('Processing capture time must have a timezone.')
    raw=json.dumps(value['content'],sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
    if len(raw)>16384 or hashlib.sha256(raw).hexdigest()!=value['sha256']:
        raise ValueError('PDF processing record digest or size is inconsistent.')
    return json.loads(json.dumps(value,allow_nan=False))
