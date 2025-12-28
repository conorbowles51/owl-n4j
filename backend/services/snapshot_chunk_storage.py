"""
Snapshot Chunk Storage Service

Handles storage of large snapshots by splitting them into chunks.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional
import hashlib

# Storage directory for chunks
BASE_DIR = Path(__file__).resolve().parent.parent.parent
CHUNK_STORAGE_DIR = BASE_DIR / "data" / "snapshot_chunks"


def ensure_chunk_storage_dir():
    """Ensure the chunk storage directory exists."""
    CHUNK_STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def get_chunk_file_path(snapshot_id: str, chunk_index: int) -> Path:
    """Get the file path for a specific chunk."""
    ensure_chunk_storage_dir()
    return CHUNK_STORAGE_DIR / f"{snapshot_id}_chunk_{chunk_index}.json"


def save_chunk(snapshot_id: str, chunk_index: int, chunk_data: str):
    """Save a chunk to disk."""
    chunk_path = get_chunk_file_path(snapshot_id, chunk_index)
    with open(chunk_path, 'w', encoding='utf-8') as f:
        f.write(chunk_data)


def load_chunk(snapshot_id: str, chunk_index: int) -> Optional[str]:
    """Load a chunk from disk."""
    chunk_path = get_chunk_file_path(snapshot_id, chunk_index)
    if not chunk_path.exists():
        return None
    with open(chunk_path, 'r', encoding='utf-8') as f:
        return f.read()


def delete_chunks(snapshot_id: str, num_chunks: int):
    """Delete all chunks for a snapshot."""
    for i in range(num_chunks):
        chunk_path = get_chunk_file_path(snapshot_id, i)
        if chunk_path.exists():
            chunk_path.unlink()


def chunk_data(data: dict, max_chunk_size: int = 50 * 1024 * 1024) -> tuple[List[str], bool]:
    """
    Split large data into chunks.
    
    Args:
        data: The data dictionary to chunk
        max_chunk_size: Maximum size of each chunk in bytes (default 50MB)
    
    Returns:
        Tuple of (list of JSON strings, is_chunked)
        If data fits in one chunk, returns ([json_string], False)
        If chunked, returns ([chunk1, chunk2, ...], True)
    """
    # Try to stringify the whole thing first
    try:
        full_json = json.dumps(data, ensure_ascii=False)
        full_size = len(full_json.encode('utf-8'))
        if full_size <= max_chunk_size:
            # Fits in one chunk
            return [full_json], False
    except (ValueError, TypeError, OverflowError) as e:
        error_msg = str(e).lower()
        if 'invalid string length' in error_msg or 'string length' in error_msg or 'overflow' in error_msg:
            # Too large, need to chunk
            pass
        else:
            raise
    
    # Need to split into chunks
    # Strategy: Split by data sections (subgraph nodes, timeline, chat_history)
    chunks = []
    
    # Extract metadata and large sections
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
    
    subgraph = data.get("subgraph", {})
    nodes = subgraph.get("nodes", [])
    links = subgraph.get("links", [])
    timeline = data.get("timeline", [])
    overview = data.get("overview", {})
    chat_history = data.get("chat_history", [])
    
    # Chunk 0: Metadata + subgraph links + first batch of nodes
    # Calculate nodes per chunk by testing
    nodes_per_chunk = 1000  # Start with a reasonable estimate
    chunk_index = 0
    node_index = 0
    
    while node_index < len(nodes):
        chunk_metadata = metadata.copy()
        chunk_metadata["_chunk_index"] = chunk_index
        chunk_metadata["_chunk_type"] = "subgraph_nodes"
        # Ensure ai_overview and citations are in the first chunk
        if "ai_overview" not in chunk_metadata:
            chunk_metadata["ai_overview"] = data.get("ai_overview")
        if "citations" not in chunk_metadata:
            chunk_metadata["citations"] = data.get("citations", {})
        
        # Try with current nodes_per_chunk
        chunk_nodes = nodes[node_index:node_index + nodes_per_chunk]
        chunk_data = {
            **chunk_metadata,
            "subgraph": {
                "nodes": chunk_nodes,
                "links": links if chunk_index == 0 else [],  # Links only in first chunk
            },
        }
        
        try:
            chunk_json = json.dumps(chunk_data, ensure_ascii=False)
            chunk_size = len(chunk_json.encode('utf-8'))
            
            # If too large, reduce and retry
            if chunk_size > max_chunk_size:
                nodes_per_chunk = max(1, nodes_per_chunk // 2)
                continue  # Retry with smaller chunk
            
            chunks.append(chunk_json)
            node_index += len(chunk_nodes)
            chunk_index += 1
        except (ValueError, TypeError, OverflowError):
            # Still too large even as JSON, reduce further
            nodes_per_chunk = max(1, nodes_per_chunk // 2)
            continue
    
    # Chunk timeline if present
    if timeline:
        events_per_chunk = 500  # Start estimate
        event_index = 0
        
        while event_index < len(timeline):
            chunk_data = {
                "_chunk_index": chunk_index,
                "_chunk_type": "timeline",
                "timeline": timeline[event_index:event_index + events_per_chunk],
            }
            
            try:
                chunk_json = json.dumps(chunk_data, ensure_ascii=False)
                chunk_size = len(chunk_json.encode('utf-8'))
                
                if chunk_size > max_chunk_size:
                    events_per_chunk = max(1, events_per_chunk // 2)
                    continue
                
                chunks.append(chunk_json)
                event_index += events_per_chunk
                chunk_index += 1
            except (ValueError, TypeError, OverflowError):
                events_per_chunk = max(1, events_per_chunk // 2)
                continue
    
    # Chunk overview if present (usually small, but check anyway)
    if overview:
        chunk_data = {
            "_chunk_index": chunk_index,
            "_chunk_type": "overview",
            "overview": overview,
        }
        try:
            chunk_json = json.dumps(chunk_data, ensure_ascii=False)
            chunks.append(chunk_json)
            chunk_index += 1
        except (ValueError, TypeError, OverflowError):
            # Overview itself is too large - split it
            # This is rare, but handle it
            overview_nodes = overview.get("nodes", [])
            if overview_nodes:
                nodes_per_chunk = 100
                node_idx = 0
                while node_idx < len(overview_nodes):
                    chunk_data = {
                        "_chunk_index": chunk_index,
                        "_chunk_type": "overview_nodes",
                        "overview": {
                            "nodes": overview_nodes[node_idx:node_idx + nodes_per_chunk],
                            "nodeCount": overview.get("nodeCount"),
                            "linkCount": overview.get("linkCount"),
                        },
                    }
                    chunk_json = json.dumps(chunk_data, ensure_ascii=False)
                    chunks.append(chunk_json)
                    node_idx += nodes_per_chunk
                    chunk_index += 1
    
    # Chunk chat_history if present
    if chat_history:
        messages_per_chunk = 100  # Start estimate
        msg_index = 0
        
        while msg_index < len(chat_history):
            chunk_data = {
                "_chunk_index": chunk_index,
                "_chunk_type": "chat_history",
                "chat_history": chat_history[msg_index:msg_index + messages_per_chunk],
            }
            
            try:
                chunk_json = json.dumps(chunk_data, ensure_ascii=False)
                chunk_size = len(chunk_json.encode('utf-8'))
                
                if chunk_size > max_chunk_size:
                    messages_per_chunk = max(1, messages_per_chunk // 2)
                    continue
                
                chunks.append(chunk_json)
                msg_index += messages_per_chunk
                chunk_index += 1
            except (ValueError, TypeError, OverflowError):
                messages_per_chunk = max(1, messages_per_chunk // 2)
                continue
    
    # Update total chunks in first chunk
    if chunks:
        first_chunk_data = json.loads(chunks[0])
        first_chunk_data["_total_chunks"] = len(chunks)
        chunks[0] = json.dumps(first_chunk_data, ensure_ascii=False)
    
    return chunks, True


def reassemble_chunks(snapshot_id: str, num_chunks: int) -> dict:
    """
    Reassemble chunks into a complete snapshot.
    
    Args:
        snapshot_id: The snapshot ID
        num_chunks: Number of chunks to load
    
    Returns:
        Complete snapshot dictionary
    """
    chunks_data = []
    for i in range(num_chunks):
        chunk_json = load_chunk(snapshot_id, i)
        if chunk_json is None:
            raise ValueError(f"Missing chunk {i} for snapshot {snapshot_id}")
        chunks_data.append(json.loads(chunk_json))
    
    # Sort chunks by index
    chunks_data.sort(key=lambda x: x.get("_chunk_index", 0))
    
    # Find chunks by type
    subgraph_node_chunks = []
    timeline_chunks = []
    overview_chunks = []
    chat_history_chunks = []
    metadata = None
    
    for chunk in chunks_data:
        chunk_type = chunk.get("_chunk_type")
        if chunk_type == "subgraph_nodes":
            subgraph_node_chunks.append(chunk)
            if metadata is None:
                # Extract metadata from first subgraph chunk
                metadata = {
                    "id": chunk.get("id"),
                    "name": chunk.get("name"),
                    "notes": chunk.get("notes"),
                    "timestamp": chunk.get("timestamp"),
                    "created_at": chunk.get("created_at"),
                    "owner": chunk.get("owner"),
                    "case_id": chunk.get("case_id"),
                    "case_version": chunk.get("case_version"),
                    "case_name": chunk.get("case_name"),
                    "ai_overview": chunk.get("ai_overview"),
                    "citations": chunk.get("citations", {}),
                }
        elif chunk_type == "timeline":
            timeline_chunks.append(chunk)
        elif chunk_type == "overview":
            overview_chunks.append(chunk)
        elif chunk_type == "overview_nodes":
            overview_chunks.append(chunk)
        elif chunk_type == "chat_history":
            chat_history_chunks.append(chunk)
    
    if not metadata:
        raise ValueError(f"No metadata found for snapshot {snapshot_id}")
    
    # Reassemble
    result = metadata.copy()
    
    # Reassemble subgraph (nodes from all subgraph chunks, links from first)
    all_nodes = []
    links = []
    for chunk in subgraph_node_chunks:
        subgraph = chunk.get("subgraph", {})
        all_nodes.extend(subgraph.get("nodes", []))
        if subgraph.get("links"):
            links = subgraph.get("links", [])
    
    result["subgraph"] = {
        "nodes": all_nodes,
        "links": links,
    }
    
    # Reassemble timeline
    all_timeline = []
    for chunk in timeline_chunks:
        all_timeline.extend(chunk.get("timeline", []))
    result["timeline"] = all_timeline
    
    # Reassemble overview
    if overview_chunks:
        if len(overview_chunks) == 1 and "overview" in overview_chunks[0]:
            # Single overview chunk
            result["overview"] = overview_chunks[0].get("overview", {})
        else:
            # Multiple overview chunks (nodes split)
            all_overview_nodes = []
            node_count = None
            link_count = None
            for chunk in overview_chunks:
                overview = chunk.get("overview", {})
                all_overview_nodes.extend(overview.get("nodes", []))
                if node_count is None:
                    node_count = overview.get("nodeCount")
                    link_count = overview.get("linkCount")
            result["overview"] = {
                "nodes": all_overview_nodes,
                "nodeCount": node_count,
                "linkCount": link_count,
            }
    else:
        result["overview"] = {}
    
    # Reassemble chat_history
    all_chat_history = []
    for chunk in chat_history_chunks:
        all_chat_history.extend(chunk.get("chat_history", []))
    result["chat_history"] = all_chat_history
    
    # Ensure ai_overview and citations are included (from metadata or first chunk)
    if "ai_overview" not in result:
        result["ai_overview"] = metadata.get("ai_overview")
    if "citations" not in result:
        result["citations"] = metadata.get("citations", {})
    
    return result

