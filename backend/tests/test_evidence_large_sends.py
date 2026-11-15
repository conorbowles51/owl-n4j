"""A file Loupe accepts can always be processed: the processing service's size limits are at least the backend's
upload limit, and the backend groups its sends so no request holds more file bytes than the service takes.

Before (12 Nov): the backend accepted one file up to 64 GB, the service refused any over 1 GiB and any request over
5 GiB, so a 1.32 GB body-cam video and a 3.3 GB drone video in CM1 failed after upload."""
import re
from pathlib import Path

from services import evidence_processing_service as processing
from services.evidence_archive import MAX_EXPANDED_BYTES

ROOT = Path(__file__).resolve().parents[2]


def _engine_default(name):
    text = (ROOT / 'evidence-engine' / 'app' / 'config.py').read_text()
    return int(re.search(rf'^\s+{name}: int = ([\d_]+)', text, re.M).group(1).replace('_', ''))


def test_the_processing_service_takes_every_file_the_backend_accepts():
    assert _engine_default('max_upload_file_bytes') >= MAX_EXPANDED_BYTES
    assert _engine_default('max_upload_batch_bytes') >= processing.MAX_FILE_BYTES_PER_SEND >= MAX_EXPANDED_BYTES
    compose = (ROOT / 'docker-compose.yml').read_text()
    for value in re.findall(r'MAX_UPLOAD_(?:FILE|BATCH)_BYTES:-(\d+)', compose):
        assert int(value) >= MAX_EXPANDED_BYTES


def test_sends_are_grouped_by_file_bytes():
    gb = 1024**3
    sizes = [40 * gb, 30 * gb, 64 * gb, 1 * gb, 1 * gb]
    chunks = processing._send_chunks([{}] * len(sizes), sizes)
    assert chunks == [[0], [1], [2], [3, 4]]
    assert all(sum(sizes[i] for i in chunk) <= processing.MAX_FILE_BYTES_PER_SEND for chunk in chunks)


def test_without_sizes_the_grouping_is_unchanged():
    assert processing._send_chunks([{}] * 30) == [list(range(25)), list(range(25, 30))]
