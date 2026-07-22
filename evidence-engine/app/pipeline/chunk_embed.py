import asyncio
from dataclasses import dataclass, field
import logging
from typing import Any
import re

from app.pipeline.extract_text import ExtractedDocument
from app.services.chroma_client import get_or_create_collection, upsert_embeddings
from app.services.evidence_document_text import build_canonical_document_text
from app.services.openai_client import embed_texts

CHUNK_SIZE = 6000  # ~1500 tokens
CHUNK_OVERLAP = 800  # ~200 tokens
logger = logging.getLogger(__name__)


def normalize_document_key(file_name: str) -> str:
    """Return the document key format used by the case graph."""
    key = file_name.strip().lower()
    key = re.sub(r"[\s_]+", "-", key)
    key = re.sub(r"[^a-z0-9\-]", "", key)
    key = re.sub(r"-+", "-", key)
    return key.strip("-")


def get_document_revision_id(doc: ExtractedDocument) -> str:
    """Return the stable hash of the canonical extracted document content."""
    return build_canonical_document_text(doc).content_sha256


@dataclass
class TextChunk:
    text: str
    index: int
    start_char: int
    end_char: int
    is_table: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChunkActivationResult:
    activated_count: int
    retired_count: int


@dataclass(frozen=True)
class StagedChunkRevision:
    """Identity required to publish a document's staged chunk revision."""

    evidence_file_id: str
    revision_id: str
    file_name: str
    has_chunks: bool
    job_id: str | None = None


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


def _page_range_for_span(
    start_char: int,
    end_char: int,
    page_map: list[dict[str, int]],
) -> tuple[int | None, int | None]:
    if not page_map:
        return None, None

    covered_pages: list[int] = []
    for page_info in page_map:
        page_start = page_info["start_char"]
        page_end = page_info["end_char"]
        page_number = page_info["page"]
        if start_char < page_end and end_char > page_start:
            covered_pages.append(page_number)

    if not covered_pages:
        return None, None

    return covered_pages[0], covered_pages[-1]


def chunk_document(
    doc: ExtractedDocument, file_name: str, job_id: str
) -> list[TextChunk]:
    """Split extracted document into chunks."""
    chunks: list[TextChunk] = []
    index = 0
    page_map = doc.metadata.get("page_spans", []) if doc.metadata.get("file_type") == "pdf" else []

    # Chunk main text
    if doc.text.strip():
        for start, end in split_text(doc.text):
            page_start, page_end = _page_range_for_span(start, end, page_map)
            chunks.append(
                TextChunk(
                    text=doc.text[start:end],
                    index=index,
                    start_char=start,
                    end_char=end,
                    is_table=False,
                    metadata={
                        "file_name": file_name,
                        "job_id": job_id,
                        "file_type": doc.metadata.get("file_type"),
                        "page_start": page_start,
                        "page_end": page_end,
                    },
                )
            )
            index += 1

    # Table chunks
    for table_text in doc.tables:
        sheet_name = _extract_sheet_name(table_text)
        inferred_page = None
        page_match = re.search(r"\[Page:\s*(\d+)\]", table_text)
        if page_match:
            inferred_page = int(page_match.group(1))
        meta = {
            "file_name": file_name,
            "job_id": job_id,
            "file_type": doc.metadata.get("file_type"),
            "sheet_name": sheet_name,
            "page_start": inferred_page,
            "page_end": inferred_page,
        }

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
    *,
    evidence_file_id: str | None = None,
    revision_id: str | None = None,
) -> list[TextChunk]:
    """Chunk a document and stage its versioned embeddings in ChromaDB.

    Staged chunks are invisible to retrieval until the owning ingestion run
    explicitly activates the revision after successful publication.
    """
    chunks = chunk_document(doc, file_name, job_id)
    if not chunks:
        return chunks

    texts = [c.text for c in chunks]
    embeddings = await embed_texts(texts)

    document_identity = evidence_file_id or job_id
    resolved_revision_id = revision_id or get_document_revision_id(doc)
    document_key = normalize_document_key(file_name)
    for chunk in chunks:
        chunk.metadata.update(
            {
                "evidence_file_id": document_identity,
                "revision_id": resolved_revision_id,
                "doc_key": document_key,
            }
        )

    ids = [
        f"{document_identity}:{resolved_revision_id}:chunk:{c.index}"
        for c in chunks
    ]
    metadatas = [
            # ChromaDB rejects None metadata values (only int/float/bool/string allowed),
            # so strip Nones — relevant for non-paginated formats (xlsx, csv) where
            # page_start/page_end are unset.
            {
                k: v
                for k, v in {
                    "case_id": case_id,
                    "doc_id": document_identity,
                    "doc_name": file_name,
                    "doc_key": document_key,
                    "job_id": job_id,
                    "evidence_file_id": evidence_file_id,
                    "revision_id": resolved_revision_id,
                    "ingestion_state": "draft",
                    "file_name": file_name,
                    "chunk_index": c.index,
                    "start_char": c.start_char,
                    "end_char": c.end_char,
                    "is_table": c.is_table,
                    "page_start": c.metadata.get("page_start"),
                    "page_end": c.metadata.get("page_end"),
                }.items()
                if v is not None
            }
        for c in chunks
    ]

    def stage_embeddings() -> None:
        collection = get_or_create_collection("chunks")
        upsert_embeddings(
            collection=collection,
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

    await asyncio.to_thread(stage_embeddings)

    return chunks


def _chunk_records(
    collection: Any,
    *,
    case_id: str,
    evidence_file_id: str,
    file_name: str,
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    filters = [
        {
            "$and": [
                {"case_id": case_id},
                {"evidence_file_id": evidence_file_id},
            ]
        },
        {
            "$and": [
                {"case_id": case_id},
                {"doc_id": file_name},
            ]
        },
    ]
    for where in filters:
        result = collection.get(where=where, include=["metadatas"])
        ids = result.get("ids") or []
        metadatas = result.get("metadatas") or []
        for chunk_id, metadata in zip(ids, metadatas):
            records[str(chunk_id)] = dict(metadata or {})
    return records


def _activate_chunk_revision_sync(
    *,
    case_id: str,
    evidence_file_id: str,
    revision_id: str,
    file_name: str,
) -> ChunkActivationResult:
    collection = get_or_create_collection("chunks")
    records = _chunk_records(
        collection,
        case_id=case_id,
        evidence_file_id=evidence_file_id,
        file_name=file_name,
    )
    updated_ids: list[str] = []
    updated_metadatas: list[dict[str, Any]] = []
    activated_count = 0
    retired_count = 0

    for chunk_id, metadata in records.items():
        is_current = (
            metadata.get("evidence_file_id") == evidence_file_id
            and metadata.get("revision_id") == revision_id
        )
        target_state = "active" if is_current else "inactive"
        if is_current:
            activated_count += 1
        elif metadata.get("ingestion_state") != "inactive":
            retired_count += 1
        if metadata.get("ingestion_state") == target_state:
            continue
        updated_ids.append(chunk_id)
        updated_metadatas.append({**metadata, "ingestion_state": target_state})

    if activated_count == 0:
        raise RuntimeError(
            "Cannot activate chunk revision because no staged chunks were found "
            f"for evidence_file_id={evidence_file_id} revision_id={revision_id}."
        )

    batch_size = 500
    for index in range(0, len(updated_ids), batch_size):
        end = index + batch_size
        collection.update(
            ids=updated_ids[index:end],
            metadatas=updated_metadatas[index:end],
        )

    logger.info(
        "chunk-revision-activated case_id=%s evidence_file_id=%s revision_id=%s "
        "activated=%d retired=%d",
        case_id,
        evidence_file_id,
        revision_id,
        activated_count,
        retired_count,
    )
    return ChunkActivationResult(
        activated_count=activated_count,
        retired_count=retired_count,
    )


async def activate_chunk_revision(
    *,
    case_id: str,
    evidence_file_id: str,
    revision_id: str,
    file_name: str,
) -> ChunkActivationResult:
    """Atomically expose one evidence revision and retire its older chunks."""
    return await asyncio.to_thread(
        _activate_chunk_revision_sync,
        case_id=case_id,
        evidence_file_id=evidence_file_id,
        revision_id=revision_id,
        file_name=file_name,
    )
