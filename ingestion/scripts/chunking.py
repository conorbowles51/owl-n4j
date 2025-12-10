"""
Chunking module - splits text into processable chunks.

Provides functions for:
- Character-based chunking with overlap
- Sentence-aware boundary detection
"""

import re
from typing import List

from config import CHUNK_SIZE, CHUNK_OVERLAP


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


def chunk_document(
    text: str,
    doc_name: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> List[dict]:
    """
    Chunk a document and return chunks with metadata.

    Args:
        text: The document text
        doc_name: Name of the document
        chunk_size: Target chunk size
        overlap: Overlap between chunks

    Returns:
        List of dicts with 'text', 'doc_name', 'chunk_index', 'total_chunks'
    """
    raw_chunks = chunk_text(text, chunk_size, overlap)

    return [
        {
            "text": chunk,
            "doc_name": doc_name,
            "chunk_index": i,
            "total_chunks": len(raw_chunks),
        }
        for i, chunk in enumerate(raw_chunks)
    ]
