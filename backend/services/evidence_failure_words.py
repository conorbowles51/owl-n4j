"""A failed file's reason in words a user understands, read from its stored error; the stored error is not changed.

Every failed file can be sent for processing again, so each sentence says what happened, not how to read an HTTP
status. The stored text stays as it is (and is still served as ``last_error``) for anyone who needs the original.
"""
import re

AGAIN = 'You can process it again.'

_RULES = [
    # 28 Oct, SB4: a request too large for the processing service was refused whole, with only this left of the reason.
    (re.compile(r"^Client error '4\d\d [^']*' for url 'https?://[^']*/cases/[^']*/files'"),
     'The processing service refused the request this file was sent in, so it was not processed. ' + AGAIN),
    (re.compile(r'^The processing service refused this file \((.*)\)$', re.S),
     'The processing service refused this file: {0}. ' + AGAIN),
    (re.compile(r'no credits remaining|exceeded your current quota|insufficient_quota', re.I),
     'The AI service account had run out of credit when this file was read. ' + AGAIN),
    (re.compile(r"429 Too Many Requests|Error code: 429", re.I),
     'The AI service was busy and turned this file away. ' + AGAIN),
    (re.compile(r'Total number of tokens|maximum context length|context_length_exceeded', re.I),
     'This file is too long for the AI service to read in one go, so it was not processed. ' + AGAIN),
    (re.compile(r'^Batch task cancelled|worker timeout or shutdown', re.I),
     'Processing was interrupted by a restart before this file finished. ' + AGAIN),
    (re.compile(r'^Orphaned:', re.I),
     'This file waited in the queue and was never picked up. ' + AGAIN),
    (re.compile(r'Tesseract process timeout', re.I),
     'Reading the text of a scanned page took too long, so the file was not finished. ' + AGAIN),
    (re.compile(r'OCR pixel limit', re.I),
     'A scanned page is too large to read as an image, so the file was not finished. ' + AGAIN),
    (re.compile(r'Unsupported image format', re.I),
     'This image format cannot be read, so the file was not processed.'),
    (re.compile(r'Unsupported file type: (\S+)', re.I),
     'Files of type {0} cannot be processed.'),
    (re.compile(r'not a valid ZIP-based file', re.I),
     'This Office document is damaged or not what its name says, so it could not be opened.'),
    (re.compile(r'All connection attempts failed|ConnectError|timed out', re.I),
     'The processing service could not be reached when this file was sent. ' + AGAIN),
    (re.compile(r'^Processing failed$'),
     'Processing stopped without giving a reason. ' + AGAIN),
]


def plain_failure(error):
    """Plain words for a stored failure; None when there is none."""
    if not error:
        return None
    text = str(error).strip()
    if text.startswith('Cancelled on request.'):
        return text
    for pattern, words in _RULES:
        match = pattern.search(text)
        if match:
            return words.format(*match.groups())
    if re.search(r'https?://|Error code: \d{3}|Traceback|\{\'error\'', text):
        return 'Processing failed. ' + AGAIN
    return text
