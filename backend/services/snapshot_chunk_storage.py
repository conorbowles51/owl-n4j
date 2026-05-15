"""
Snapshot chunking helpers.

The active snapshot source of truth is now Postgres via snapshot_storage.py.
These helpers remain for compatibility with older call sites that split large
payloads before reassembly; they do not persist chunks to JSON files.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional


_CHUNK_CACHE: dict[str, dict[int, str]] = {}


def save_chunk(snapshot_id: str, chunk_index: int, chunk_data: str) -> None:
    """Store a chunk in process memory for immediate reassembly."""
    _CHUNK_CACHE.setdefault(snapshot_id, {})[chunk_index] = chunk_data


def load_chunk(snapshot_id: str, chunk_index: int) -> Optional[str]:
    """Load a chunk from the in-process compatibility cache."""
    return _CHUNK_CACHE.get(snapshot_id, {}).get(chunk_index)


def delete_chunks(snapshot_id: str, num_chunks: int) -> None:
    """Remove cached chunks for a snapshot."""
    _CHUNK_CACHE.pop(snapshot_id, None)


def chunk_data(data: dict, max_chunk_size: int = 50 * 1024 * 1024) -> tuple[List[str], bool]:
    """
    Split large data into JSON string chunks.

    This is serialization only; persistence is handled by Postgres snapshot
    storage after the chunks are reassembled.
    """
    full_json = json.dumps(data, ensure_ascii=False, default=str)
    full_size = len(full_json.encode("utf-8"))
    if full_size <= max_chunk_size:
        return [full_json], False

    chunks: list[str] = []
    metadata = {
        "id": data.get("id"),
        "name": data.get("name"),
        "notes": data.get("notes"),
        "timestamp": data.get("timestamp"),
        "created_at": data.get("created_at"),
        "owner": data.get("owner"),
        "case_id": data.get("case_id"),
        "case_version": data.get("case_version"),
        "case_name": data.get("case_name"),
        "ai_overview": data.get("ai_overview"),
        "citations": data.get("citations", {}),
        "_chunked": True,
    }

    def append_section(section_type: str, payload_key: str, values: list, batch_size: int) -> None:
        nonlocal chunks
        index = 0
        while index < len(values):
            batch = values[index:index + batch_size]
            chunk = {
                "_chunk_index": len(chunks),
                "_chunk_type": section_type,
                payload_key: batch,
            }
            chunks.append(json.dumps(chunk, ensure_ascii=False, default=str))
            index += batch_size

    subgraph = data.get("subgraph", {}) or {}
    nodes = subgraph.get("nodes", []) or []
    links = subgraph.get("links", []) or []
    if nodes:
        for index in range(0, len(nodes), 1000):
            chunk = {
                **metadata,
                "_chunk_index": len(chunks),
                "_chunk_type": "subgraph_nodes",
                "subgraph": {
                    "nodes": nodes[index:index + 1000],
                    "links": links if index == 0 else [],
                },
            }
            chunks.append(json.dumps(chunk, ensure_ascii=False, default=str))
    else:
        chunks.append(
            json.dumps(
                {
                    **metadata,
                    "_chunk_index": 0,
                    "_chunk_type": "subgraph_nodes",
                    "subgraph": {"nodes": [], "links": links},
                },
                ensure_ascii=False,
                default=str,
            )
        )

    timeline = data.get("timeline", []) or []
    if timeline:
        append_section("timeline", "timeline", timeline, 500)

    chat_history = data.get("chat_history", []) or []
    if chat_history:
        append_section("chat_history", "chat_history", chat_history, 100)

    overview = data.get("overview", {}) or {}
    if overview:
        chunks.append(
            json.dumps(
                {
                    "_chunk_index": len(chunks),
                    "_chunk_type": "overview",
                    "overview": overview,
                },
                ensure_ascii=False,
                default=str,
            )
        )

    first_chunk_data = json.loads(chunks[0])
    first_chunk_data["_total_chunks"] = len(chunks)
    chunks[0] = json.dumps(first_chunk_data, ensure_ascii=False, default=str)
    return chunks, True


def reassemble_chunks(snapshot_id: str, num_chunks: int) -> Dict:
    """Reassemble cached chunks into a complete snapshot dictionary."""
    chunks_data = []
    for index in range(num_chunks):
        chunk_json = load_chunk(snapshot_id, index)
        if chunk_json is None:
            raise ValueError(f"Missing chunk {index} for snapshot {snapshot_id}")
        chunks_data.append(json.loads(chunk_json))

    chunks_data.sort(key=lambda item: item.get("_chunk_index", 0))

    metadata = next(
        (chunk for chunk in chunks_data if chunk.get("_chunk_type") == "subgraph_nodes"),
        {},
    )
    result = {
        "id": metadata.get("id", snapshot_id),
        "name": metadata.get("name"),
        "notes": metadata.get("notes"),
        "timestamp": metadata.get("timestamp"),
        "created_at": metadata.get("created_at"),
        "owner": metadata.get("owner"),
        "case_id": metadata.get("case_id"),
        "case_version": metadata.get("case_version"),
        "case_name": metadata.get("case_name"),
        "ai_overview": metadata.get("ai_overview"),
        "citations": metadata.get("citations", {}),
        "subgraph": {"nodes": [], "links": []},
        "timeline": [],
        "overview": {},
        "chat_history": [],
    }

    for chunk in chunks_data:
        chunk_type = chunk.get("_chunk_type")
        if chunk_type == "subgraph_nodes":
            subgraph = chunk.get("subgraph", {})
            result["subgraph"]["nodes"].extend(subgraph.get("nodes", []))
            if subgraph.get("links"):
                result["subgraph"]["links"] = subgraph["links"]
        elif chunk_type == "timeline":
            result["timeline"].extend(chunk.get("timeline", []))
        elif chunk_type == "overview":
            result["overview"] = chunk.get("overview", {})
        elif chunk_type == "chat_history":
            result["chat_history"].extend(chunk.get("chat_history", []))

    return result
