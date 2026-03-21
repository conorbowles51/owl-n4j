from dataclasses import dataclass, field
from typing import Any

from app.pipeline.extract_text import ExtractedDocument
from app.services.chroma_client import add_embeddings, get_or_create_collection
from app.services.openai_client import embed_texts

CHUNK_SIZE = 6000  # ~1500 tokens
CHUNK_OVERLAP = 800  # ~200 tokens


@dataclass
class TextChunk:
    text: str
    index: int
    start_char: int
    end_char: int
    is_table: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


def _find_break_point(text: str, start: int, end: int) -> int:
    """Find best break point using hierarchical separators."""
    search_start = start + (end - start) // 2
    for sep in ["\n\n", "\n", ". ", " "]:
        idx = text.rfind(sep, search_start, end)
        if idx != -1:
            return idx + len(sep)
    return end


def split_text(
    text: str,
    max_chars: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[tuple[int, int]]:
    """Split text into overlapping chunks. Returns (start, end) offsets."""
    if len(text) <= max_chars:
        return [(0, len(text))]

    chunks: list[tuple[int, int]] = []
    start = 0

    while start < len(text):
        end = min(start + max_chars, len(text))

        if end < len(text):
            end = _find_break_point(text, start, end)

        chunks.append((start, end))

        next_start = end - overlap
        if next_start <= start:
            next_start = end
        start = next_start

    return chunks


def _extract_sheet_name(table_text: str) -> str:
    if table_text.startswith("[Sheet: "):
        bracket_end = table_text.find("]")
        if bracket_end != -1:
            return table_text[8:bracket_end]
    return ""


def chunk_document(
    doc: ExtractedDocument, file_name: str, job_id: str
) -> list[TextChunk]:
    """Split extracted document into chunks."""
    chunks: list[TextChunk] = []
    index = 0

    # Chunk main text
    if doc.text.strip():
        for start, end in split_text(doc.text):
            chunks.append(
                TextChunk(
                    text=doc.text[start:end],
                    index=index,
                    start_char=start,
                    end_char=end,
                    is_table=False,
                    metadata={"file_name": file_name, "job_id": job_id},
                )
            )
            index += 1

    # Table chunks
    for table_text in doc.tables:
        sheet_name = _extract_sheet_name(table_text)
        meta = {"file_name": file_name, "job_id": job_id, "sheet_name": sheet_name}

        if len(table_text) > CHUNK_SIZE:
            for start, end in split_text(table_text):
                chunks.append(
                    TextChunk(
                        text=table_text[start:end],
                        index=index,
                        start_char=start,
                        end_char=end,
                        is_table=True,
                        metadata=dict(meta),
                    )
                )
                index += 1
        else:
            chunks.append(
                TextChunk(
                    text=table_text,
                    index=index,
                    start_char=0,
                    end_char=len(table_text),
                    is_table=True,
                    metadata=dict(meta),
                )
            )
            index += 1

    return chunks


async def chunk_and_embed(
    doc: ExtractedDocument,
    case_id: str,
    job_id: str,
    file_name: str,
) -> list[TextChunk]:
    """Chunk document and store embeddings in ChromaDB."""
    chunks = chunk_document(doc, file_name, job_id)
    if not chunks:
        return chunks

    texts = [c.text for c in chunks]
    embeddings = await embed_texts(texts)

    collection = get_or_create_collection("chunks")

    add_embeddings(
        collection=collection,
        ids=[f"{job_id}_chunk_{c.index}" for c in chunks],
        embeddings=embeddings,
        documents=texts,
        metadatas=[
            {
                "case_id": case_id,
                "doc_id": file_name,
                "doc_name": file_name,
                "job_id": job_id,
                "file_name": file_name,
                "chunk_index": c.index,
                "start_char": c.start_char,
                "end_char": c.end_char,
                "is_table": c.is_table,
            }
            for c in chunks
        ],
    )

    return chunks
