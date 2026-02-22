"""
Image Processor module - extracts text and descriptions from images.

Supports two modes (selectable via IMAGE_PROVIDER config or per-call):
- Local: Tesseract OCR (free, no API calls, text extraction only)
- Online: GPT-4 Vision (API calls, richer scene descriptions + OCR)

Dependencies:
- Tesseract mode: pytesseract + Pillow + tesseract binary (brew install tesseract)
- Vision mode: openai Python package (already installed in project)
"""

import base64
import sys
from pathlib import Path
from typing import Dict, Optional, Callable

from logging_utils import log_progress, log_error, log_warning
from config import (
    IMAGE_PROVIDER,
    TESSERACT_LANG,
    OPENAI_VISION_MODEL,
    OPENAI_API_KEY,
)

# Tesseract imports (optional)
try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

# Pillow for image loading
try:
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

# OpenAI imports (already available in project)
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


def extract_image_metadata(image_path: Path) -> Dict:
    """
    Extract metadata from an image file using Pillow.

    Returns dimensions, format, and EXIF data (GPS, date taken, camera) if available.

    Args:
        image_path: Path to image file

    Returns:
        Dict with metadata keys: width, height, format, and optional exif fields
    """
    metadata = {}

    if not PILLOW_AVAILABLE:
        return metadata

    try:
        with Image.open(image_path) as img:
            metadata["width"] = img.width
            metadata["height"] = img.height
            metadata["format"] = img.format or image_path.suffix.upper().lstrip(".")
            metadata["mode"] = img.mode

            # Try to extract EXIF data
            exif_data = img.getexif()
            if exif_data:
                for tag_id, value in exif_data.items():
                    tag_name = TAGS.get(tag_id, tag_id)
                    if tag_name == "DateTime":
                        metadata["date_taken"] = str(value)
                    elif tag_name == "Make":
                        metadata["camera_make"] = str(value)
                    elif tag_name == "Model":
                        metadata["camera_model"] = str(value)
                    elif tag_name == "ImageDescription":
                        metadata["image_description"] = str(value)

                # GPS data
                gps_info = exif_data.get_ifd(0x8825)  # GPSInfo tag
                if gps_info:
                    try:
                        lat = _convert_gps_to_decimal(
                            gps_info.get(2), gps_info.get(1)  # GPSLatitude, GPSLatitudeRef
                        )
                        lng = _convert_gps_to_decimal(
                            gps_info.get(4), gps_info.get(3)  # GPSLongitude, GPSLongitudeRef
                        )
                        if lat is not None and lng is not None:
                            metadata["gps_latitude"] = lat
                            metadata["gps_longitude"] = lng
                    except Exception:
                        pass
    except Exception:
        pass

    return metadata


def _convert_gps_to_decimal(coords, ref) -> Optional[float]:
    """Convert GPS coordinates from EXIF format to decimal degrees."""
    if coords is None or ref is None:
        return None
    try:
        degrees = float(coords[0])
        minutes = float(coords[1])
        seconds = float(coords[2])
        decimal = degrees + minutes / 60 + seconds / 3600
        if ref in ("S", "W"):
            decimal = -decimal
        return round(decimal, 6)
    except (IndexError, TypeError, ValueError):
        return None


def extract_text_tesseract(
    image_path: Path,
    lang: str = None,
    log_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """
    Extract text from image using Tesseract OCR.

    Args:
        image_path: Path to image file
        lang: Tesseract language code(s), e.g. "eng" or "eng+spa"
        log_callback: Optional logging callback

    Returns:
        Extracted text string
    """
    if not TESSERACT_AVAILABLE:
        raise ImportError(
            "pytesseract not installed. Install with: pip install pytesseract\n"
            "Also install Tesseract binary: brew install tesseract (macOS) or apt install tesseract-ocr (Linux)"
        )

    if not PILLOW_AVAILABLE:
        raise ImportError("Pillow not installed. Install with: pip install Pillow")

    ocr_lang = lang or TESSERACT_LANG
    log_progress(f"Running Tesseract OCR (language: {ocr_lang}): {image_path.name}", log_callback)

    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, lang=ocr_lang)
        log_progress(f"Tesseract OCR extracted {len(text)} characters", log_callback)
        return text.strip()
    except Exception as e:
        log_error(f"Tesseract OCR failed: {e}", log_callback)
        raise


def describe_image_vision(
    image_path: Path,
    model: str = None,
    log_callback: Optional[Callable[[str], None]] = None,
    doc_name: Optional[str] = None,
) -> str:
    """
    Analyze image using OpenAI GPT-4 Vision API.

    Sends image as base64 to the OpenAI Vision endpoint.
    Returns a structured description including:
    - Scene description
    - Any text visible in the image (OCR)
    - People, objects, locations identified
    - Any investigatively-relevant details

    Args:
        image_path: Path to image file
        model: Vision model to use (default: from config)
        log_callback: Optional logging callback
        doc_name: Document name for cost tracking

    Returns:
        Descriptive text suitable for entity extraction
    """
    if not OPENAI_AVAILABLE:
        raise ImportError("OpenAI package not installed. Install with: pip install openai")

    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not set in environment variables")

    vision_model = model or OPENAI_VISION_MODEL
    log_progress(f"Analyzing image with {vision_model}: {image_path.name}", log_callback)

    # Read and base64-encode the image
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    # Determine MIME type
    suffix = image_path.suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".webp": "image/webp",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
    }
    mime_type = mime_map.get(suffix, "image/jpeg")

    client = OpenAI(api_key=OPENAI_API_KEY)

    response = client.chat.completions.create(
        model=vision_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an investigation analyst examining evidence images. "
                    "Provide a detailed, structured analysis of the image. Include:\n"
                    "1. SCENE DESCRIPTION: What the image shows overall\n"
                    "2. TEXT CONTENT: Any visible text, documents, signs, labels (transcribe exactly)\n"
                    "3. PEOPLE: Descriptions of any people visible (appearance, clothing, actions)\n"
                    "4. OBJECTS: Notable objects, vehicles, equipment, evidence items\n"
                    "5. LOCATIONS: Any identifiable locations, addresses, landmarks\n"
                    "6. TIMESTAMPS: Any visible dates, times, or temporal indicators\n"
                    "7. INVESTIGATIVE NOTES: Anything potentially relevant to an investigation\n\n"
                    "Be thorough and factual. Report what you see, not assumptions."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Analyze this evidence image ({image_path.name}). "
                            "Provide a comprehensive description covering all relevant details."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{image_data}",
                            "detail": "high",
                        },
                    },
                ],
            },
        ],
        max_tokens=2000,
    )

    description = response.choices[0].message.content or ""

    # Track cost via the existing cost tracking service
    usage = response.usage
    if usage:
        log_progress(
            f"[Cost Tracking] Vision API usage - prompt: {usage.prompt_tokens}, "
            f"completion: {usage.completion_tokens}, total: {usage.total_tokens}",
            log_callback,
        )
        _record_vision_cost(
            usage=usage,
            model_id=vision_model,
            doc_name=doc_name or image_path.name,
            media_type="image",
            log_callback=log_callback,
        )

    log_progress(f"Vision analysis complete: {len(description)} characters", log_callback)
    return description.strip()


def _record_vision_cost(
    usage,
    model_id: str,
    doc_name: str,
    media_type: str,
    log_callback: Optional[Callable[[str], None]] = None,
):
    """
    Record Vision API cost using the existing cost tracking service.
    Follows the same pattern as llm_client.py lines 213-270.
    """
    try:
        backend_dir = Path(__file__).parent.parent.parent / "backend"
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))

        from services.cost_tracking_service import record_cost, CostJobType
        from postgres.session import get_db

        db = next(get_db())
        try:
            record_cost(
                job_type=CostJobType.INGESTION,
                provider="openai",
                model_id=model_id,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                description=f"Image analysis: {doc_name}",
                extra_metadata={"doc_name": doc_name, "media_type": media_type},
                db=db,
            )
            log_progress("[Cost Tracking] Successfully recorded Vision API cost", log_callback)
        except Exception as e:
            log_error(f"[Cost Tracking] Failed to record cost: {e}", log_callback)
        finally:
            db.close()
    except ImportError as e:
        log_error(f"[Cost Tracking] Not available (ImportError): {e}", log_callback)
    except Exception as e:
        log_error(f"[Cost Tracking] Error: {e}", log_callback)


def process_image(
    image_path: Path,
    provider: str = None,
    log_callback: Optional[Callable[[str], None]] = None,
    doc_name: Optional[str] = None,
) -> Dict:
    """
    Process an image file and extract text content.

    Routes to either Tesseract (local OCR) or GPT-4 Vision (online) based on provider.

    Args:
        image_path: Path to image file
        provider: "tesseract" or "openai" (default: from IMAGE_PROVIDER config)
        log_callback: Optional logging callback
        doc_name: Document name for cost tracking

    Returns:
        Dict with keys:
        - text: Extracted text content
        - provider: Which provider was used
        - metadata: Image metadata (dimensions, format, EXIF, etc.)
    """
    active_provider = provider or IMAGE_PROVIDER

    # Extract metadata regardless of provider
    metadata = extract_image_metadata(image_path)

    log_progress(f"Processing image with provider: {active_provider}", log_callback)

    if active_provider == "openai":
        if not OPENAI_AVAILABLE or not OPENAI_API_KEY:
            log_warning(
                "OpenAI Vision not available, falling back to Tesseract",
                log_callback,
            )
            active_provider = "tesseract"

    if active_provider == "tesseract":
        if not TESSERACT_AVAILABLE:
            # If tesseract not available, try OpenAI as fallback
            if OPENAI_AVAILABLE and OPENAI_API_KEY:
                log_warning(
                    "Tesseract not available, falling back to OpenAI Vision",
                    log_callback,
                )
                active_provider = "openai"
            else:
                raise ImportError(
                    "Neither Tesseract nor OpenAI Vision is available. "
                    "Install pytesseract or set OPENAI_API_KEY."
                )

    if active_provider == "openai":
        text = describe_image_vision(
            image_path,
            log_callback=log_callback,
            doc_name=doc_name or image_path.name,
        )
    else:
        text = extract_text_tesseract(image_path, log_callback=log_callback)

    # Prepend metadata context to the text
    metadata_text = ""
    if metadata.get("gps_latitude") and metadata.get("gps_longitude"):
        metadata_text += f"GPS Location: {metadata['gps_latitude']}, {metadata['gps_longitude']}\n"
    if metadata.get("date_taken"):
        metadata_text += f"Date Taken: {metadata['date_taken']}\n"
    if metadata.get("camera_make") or metadata.get("camera_model"):
        camera = f"{metadata.get('camera_make', '')} {metadata.get('camera_model', '')}".strip()
        metadata_text += f"Camera: {camera}\n"

    if metadata_text:
        text = f"=== IMAGE METADATA ===\n{metadata_text}\n=== IMAGE CONTENT ===\n{text}"

    return {
        "text": text,
        "provider": active_provider,
        "metadata": metadata,
    }
