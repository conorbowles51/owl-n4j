"""Every stored failure on live (8 Nov) reads in plain words with no address or HTTP status, and the stored text is
kept unchanged."""
import pytest

from services.evidence_failure_words import plain_failure

LIVE = [
    "Client error '400 Bad Request' for url 'http://localhost:8003/cases/b6fe7c6b-7783-4769-93d7-a8571003a6f2/files'\n"
    "For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/400",
    "Error code: 429 - {'error': {'message': 'You have no credits remaining. Add credits to continue using the API.'}}",
    "Batch task cancelled (worker timeout or shutdown). Safe to retry.",
    "OCR failed on PDF page 3: Tesseract process timeout",
    "Processing failed",
    "Unsupported file type: .dotx",
    "Orphaned: queued 2026-10-01 but never picked up by a worker. Marked failed 2026-10-20.",
    "OCR failed on PDF page 1: page exceeds the configured OCR pixel limit even at 150 dpi",
    "Client error '429 Too Many Requests' for url 'https://api.deepseek.com/chat/completions'",
    "Error code: 400 - {'error': {'message': 'Total number of tokens in instructions exceeds the limit'}}",
    "Error code: 429 - {'error': {'message': 'You exceeded your current quota, please check your plan'}}",
    "All connection attempts failed",
    "Office document is not a valid ZIP-based file",
    "Unsupported image format/type",
    "The processing service refused this file (Part exceeded maximum size of 1024KB.)",
]


@pytest.mark.parametrize('error', LIVE)
def test_live_failures_read_plainly(error):
    words = plain_failure(error)
    assert words and 'http' not in words and 'localhost' not in words and 'Error code' not in words
    assert '400' not in words and '429' not in words


def test_the_sb4_refusal_says_it_can_be_processed_again():
    assert plain_failure(LIVE[0]).endswith('You can process it again.')
    assert 'Part exceeded maximum size' in plain_failure(LIVE[-1])


def test_no_error_no_words_and_unknown_text_kept():
    assert plain_failure(None) is None
    assert plain_failure('Password-protected PDF') == 'Password-protected PDF'


def test_a_batch_that_could_not_reach_the_ai_service_says_so():
    # 11 Nov: httpx.ConnectTimeout has no text; the engine now stores its name.
    assert 'could not be reached' in plain_failure('Batch pipeline failed: ConnectTimeout')
