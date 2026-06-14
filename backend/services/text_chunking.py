"""
Chunking module - splits text into processable chunks.

Provides functions for:
- Character-based chunking with overlap
- Sentence-aware boundary detection
- Page number tracking for citation support
"""

import re
from typing import List, Tuple, Optional

from config import CHUNK_SIZE, CHUNK_OVERLAP


# Pattern to match page markers inserted by PDF extraction
PAGE_MARKER_PATTERN = re.compile(r'---\s*Page\s+(\d+)\s*---', re.IGNORECASE)


def extract_page_numbers_from_text(text: str) -> List[Tuple[int, int]]:
    """
    Extract page markers and their positions from text.
    
    Args:
        text: Document text with page markers like '--- Page N ---'
        
    Returns:
        List of (page_number, position) tuples sorted by position
    """
    markers = []
    for match in PAGE_MARKER_PATTERN.finditer(text):
        page_num = int(match.group(1))
        position = match.start()
        markers.append((page_num, position))
    return sorted(markers, key=lambda x: x[1])


def get_page_at_position(position: int, page_markers: List[Tuple[int, int]]) -> Optional[int]:
    """
    Determine which page a given text position falls on.
    
    Args:
        position: Character position in the text
        page_markers: List of (page_number, marker_position) tuples
        
    Returns:
        Page number, or None if no page markers exist
    """
    if not page_markers:
        return None
    
    current_page = page_markers[0][0]  # Default to first page
    
    for page_num, marker_pos in page_markers:
        if marker_pos <= position:
            current_page = page_num
        else:
            break
    
    return current_page


def get_page_range_for_chunk(
    chunk_start: int,
    chunk_end: int,
    page_markers: List[Tuple[int, int]]
) -> Tuple[Optional[int], Optional[int]]:
    """
    Determine the page range covered by a chunk of text.
    
    Args:
        chunk_start: Start position of the chunk
        chunk_end: End position of the chunk
        page_markers: List of (page_number, marker_position) tuples
        
    Returns:
        Tuple of (page_start, page_end), or (None, None) if no markers
    """
    if not page_markers:
        return (None, None)
    
    page_start = get_page_at_position(chunk_start, page_markers)
    page_end = get_page_at_position(chunk_end, page_markers)
    
    return (page_start, page_end)


def find_sentence_boundary(text: str, target_pos: int, search_range: int = 100) -> int:
    """
    Find the nearest sentence boundary to target_pos.

    Looks for sentence-ending punctuation followed by space or newline.

    Args:
        text: The text to search
        target_pos: The target position
        search_range: How far to search in either direction

    Returns:
        Position of the best boundary found, or target_pos if none found
    """
    # Search backwards first (prefer to cut at sentence end before target)
    start_search = max(0, target_pos - search_range)
    search_text = text[start_search:target_pos]

    # Look for sentence endings (. ! ? followed by space/newline)
    sentence_end_pattern = r'[.!?]["\')\]]?\s'

    matches = list(re.finditer(sentence_end_pattern, search_text))

    if matches:
        # Return position after the last sentence end in search range
        last_match = matches[-1]
        return start_search + last_match.end()

    # If no sentence boundary, look for paragraph break
    para_pattern = r'\n\n'
    para_matches = list(re.finditer(para_pattern, search_text))

    if para_matches:
        last_match = para_matches[-1]
        return start_search + last_match.end()

    # Fall back to target position
    return target_pos


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> List[str]:
    """
    Split text into chunks with overlap.

    Attempts to break at sentence boundaries when possible.

    Args:
        text: The text to chunk
        chunk_size: Target size of each chunk in characters
        overlap: Number of characters to overlap between chunks

    Returns:
        List of text chunks
    """
    if not text or not text.strip():
        return []

    text = text.strip()

    # If text is small enough, return as single chunk
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    current_pos = 0

    while current_pos < len(text):
        # Calculate end of this chunk
        chunk_end = current_pos + chunk_size

        if chunk_end >= len(text):
            # Last chunk - take everything remaining
            chunks.append(text[current_pos:].strip())
            break

        # Try to find a sentence boundary near chunk_end
        boundary = find_sentence_boundary(text, chunk_end)

        # Extract chunk
        chunk = text[current_pos:boundary].strip()

        if chunk:
            chunks.append(chunk)

        # Move position, accounting for overlap
        # Start next chunk 'overlap' characters before the boundary
        current_pos = max(current_pos + 1, boundary - overlap)

        # Ensure we're making progress
        if current_pos >= len(text) - 10:
            # Near the end, grab whatever is left
            remaining = text[current_pos:].strip()
            if remaining and remaining != chunks[-1]:
                chunks.append(remaining)
            break

    return chunks


def chunk_text_with_positions(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> List[Tuple[str, int, int]]:
    """
    Split text into chunks with overlap, tracking positions.

    Attempts to break at sentence boundaries when possible.

    Args:
        text: The text to chunk
        chunk_size: Target size of each chunk in characters
        overlap: Number of characters to overlap between chunks

    Returns:
        List of tuples: (chunk_text, start_position, end_position)
    """
    if not text or not text.strip():
        return []

    # Don't strip text here - we need to preserve positions
    original_text = text
    text = text.strip()
    
    # Calculate offset from stripping
    start_offset = len(original_text) - len(original_text.lstrip())

    # If text is small enough, return as single chunk
    if len(text) <= chunk_size:
        return [(text, start_offset, start_offset + len(text))]

    chunks = []
    current_pos = 0

    while current_pos < len(text):
        # Calculate end of this chunk
        chunk_end = current_pos + chunk_size

        if chunk_end >= len(text):
            # Last chunk - take everything remaining
            chunk_text = text[current_pos:].strip()
            if chunk_text:
                chunks.append((
                    chunk_text,
                    start_offset + current_pos,
                    start_offset + len(text)
                ))
            break

        # Try to find a sentence boundary near chunk_end
        boundary = find_sentence_boundary(text, chunk_end)

        # Extract chunk
        chunk_text = text[current_pos:boundary].strip()

        if chunk_text:
            chunks.append((
                chunk_text,
                start_offset + current_pos,
                start_offset + boundary
            ))

        # Move position, accounting for overlap
        current_pos = max(current_pos + 1, boundary - overlap)

        # Ensure we're making progress
        if current_pos >= len(text) - 10:
            remaining = text[current_pos:].strip()
            if remaining and (not chunks or remaining != chunks[-1][0]):
                chunks.append((
                    remaining,
                    start_offset + current_pos,
                    start_offset + len(text)
                ))
            break

    return chunks


def chunk_document(
    text: str,
    doc_name: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> List[dict]:
    """
    Chunk a document and return chunks with metadata including page numbers.

    Args:
        text: The document text (may contain page markers like '--- Page N ---')
        doc_name: Name of the document
        chunk_size: Target chunk size
        overlap: Overlap between chunks

    Returns:
        List of dicts with:
        - 'text': The chunk text
        - 'doc_name': Source document name
        - 'chunk_index': Index of this chunk (0-based)
        - 'total_chunks': Total number of chunks
        - 'page_start': First page this chunk covers (or None)
        - 'page_end': Last page this chunk covers (or None)
    """
    # Extract page markers from the document
    page_markers = extract_page_numbers_from_text(text)
    
    # Get chunks with position tracking
    chunks_with_positions = chunk_text_with_positions(text, chunk_size, overlap)
    
    result = []
    for i, (chunk_text, start_pos, end_pos) in enumerate(chunks_with_positions):
        # Determine page range for this chunk
        page_start, page_end = get_page_range_for_chunk(start_pos, end_pos, page_markers)
        
        result.append({
            "text": chunk_text,
            "doc_name": doc_name,
            "chunk_index": i,
            "total_chunks": len(chunks_with_positions),
            "page_start": page_start,
            "page_end": page_end,
        })
    
    return result
