"""
Snapshot Storage Service

Handles persistent storage of snapshots in a JSON file.
"""

import json
import os
import copy
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from datetime import datetime
from services.snapshot_chunk_storage import (
    chunk_data, save_chunk, load_chunk, delete_chunks, reassemble_chunks
)

# Storage file location
BASE_DIR = Path(__file__).resolve().parent.parent.parent
STORAGE_DIR = BASE_DIR / "data"
STORAGE_FILE = STORAGE_DIR / "snapshots.json"


def ensure_storage_dir():
    """Ensure the storage directory exists."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def load_snapshots() -> Dict:
    """Load snapshots from the JSON file."""
    ensure_storage_dir()
    
    if not STORAGE_FILE.exists():
        return {}
    
    try:
        with open(STORAGE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading snapshots: {e}")
        return {}


def save_snapshots(snapshots: Dict):
    """Save snapshots to the JSON file."""
    ensure_storage_dir()
    
    print(f"[SAVE_SNAPSHOTS] Saving {len(snapshots)} snapshots to disk")
    # Log each snapshot's data before saving
    for snap_id, snap_data in snapshots.items():
        snap_nodes = len(snap_data.get("subgraph", {}).get("nodes", [])) if isinstance(snap_data.get("subgraph", {}).get("nodes"), list) else 0
        snap_timeline = len(snap_data.get("timeline", [])) if isinstance(snap_data.get("timeline"), list) else 0
        snap_citations = len(snap_data.get("citations", {})) if isinstance(snap_data.get("citations"), dict) else 0
        snap_chat = len(snap_data.get("chat_history", [])) if isinstance(snap_data.get("chat_history"), list) else 0
        print(f"[SAVE_SNAPSHOTS] Snapshot {snap_id}: nodes={snap_nodes}, timeline={snap_timeline}, citations={snap_citations}, chat={snap_chat}, chunked={snap_data.get('_chunked', False)}")
    
    try:
        # Instead of serializing the entire dictionary at once (which can corrupt nested data),
        # verify each snapshot has its nested structures before saving
        # We'll still serialize the whole dict for saving, but we've already validated each snapshot individually
        # Create a temporary file first, then rename for atomic writes
        temp_file = STORAGE_FILE.with_suffix('.tmp')
        print(f"[SAVE_SNAPSHOTS] Writing to temp file: {temp_file}")
        
        # Before writing, verify each snapshot's data structure
        for snap_id, snap_data in snapshots.items():
            if 'subgraph' in snap_data:
                subgraph = snap_data['subgraph']
                if isinstance(subgraph, dict) and 'nodes' in subgraph:
                    nodes = subgraph['nodes']
                    nodes_count = len(nodes) if isinstance(nodes, list) else 0
                    print(f"[SAVE_SNAPSHOTS] Before json.dump: {snap_id} has {nodes_count} nodes")
                    if nodes_count > 0:
                        # Verify first node structure
                        first_node = nodes[0] if isinstance(nodes, list) and len(nodes) > 0 else None
                        if first_node:
                            print(f"[SAVE_SNAPSHOTS] First node keys: {list(first_node.keys())[:5] if isinstance(first_node, dict) else 'N/A'}")
        
        # Try to serialize to a string first to catch any issues
        try:
            test_json = json.dumps(snapshots, ensure_ascii=False)
            print(f"[SAVE_SNAPSHOTS] Successfully serialized to JSON, length: {len(test_json)}")
            # Parse it back to verify
            test_parsed = json.loads(test_json)
            print(f"[SAVE_SNAPSHOTS] Successfully parsed back, {len(test_parsed)} snapshots")
            for snap_id, snap_data in test_parsed.items():
                if 'subgraph' in snap_data:
                    nodes = snap_data.get('subgraph', {}).get('nodes', [])
                    nodes_count = len(nodes) if isinstance(nodes, list) else 0
                    print(f"[SAVE_SNAPSHOTS] After json.loads: {snap_id} has {nodes_count} nodes")
        except Exception as test_error:
            print(f"[SAVE_SNAPSHOTS] ERROR during test serialization: {test_error}")
            import traceback
            traceback.print_exc()
        
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(snapshots, f, indent=2, ensure_ascii=False)
        
        # Atomic rename
        print(f"[SAVE_SNAPSHOTS] Renaming temp file to {STORAGE_FILE}")
        temp_file.replace(STORAGE_FILE)
        print(f"[SAVE_SNAPSHOTS] Successfully saved snapshots to disk")
        
        # Verify what was actually written
        try:
            with open(STORAGE_FILE, 'r', encoding='utf-8') as f:
                saved_data = json.load(f)
            print(f"[SAVE_SNAPSHOTS] Verification: Read back {len(saved_data)} snapshots from disk")
            for snap_id, snap_data in saved_data.items():
                snap_nodes = len(snap_data.get("subgraph", {}).get("nodes", [])) if isinstance(snap_data.get("subgraph", {}).get("nodes"), list) else 0
                snap_timeline = len(snap_data.get("timeline", [])) if isinstance(snap_data.get("timeline"), list) else 0
                print(f"[SAVE_SNAPSHOTS] Verification: Snapshot {snap_id} on disk: nodes={snap_nodes}, timeline={snap_timeline}, chunked={snap_data.get('_chunked', False)}")
        except Exception as verify_error:
            print(f"[SAVE_SNAPSHOTS] WARNING: Could not verify saved data: {verify_error}")
            
    except IOError as e:
        print(f"[SAVE_SNAPSHOTS] ERROR: IOError saving snapshots: {e}")
        raise
    except (ValueError, TypeError, OverflowError) as e:
        print(f"[SAVE_SNAPSHOTS] ERROR: Serialization error: {e}")
        # If serialization fails, try to identify which snapshot is causing the issue
        for snapshot_id, snapshot_data in snapshots.items():
            try:
                json.dumps(snapshot_data, ensure_ascii=False)
            except Exception as snapshot_error:
                print(f"[SAVE_SNAPSHOTS]   Snapshot {snapshot_id} failed to serialize: {snapshot_error}")
        raise


class SnapshotStorage:
    """Service for managing snapshot storage."""
    
    def __init__(self):
        self._snapshots = load_snapshots()
    
    def get_all(self) -> Dict:
        """Get all snapshots."""
        # Reload from disk to ensure we have the latest data
        self.reload()
        # Return a deep copy to prevent mutations from affecting stored data
        return copy.deepcopy(self._snapshots)
    
    def get(self, snapshot_id: str) -> Optional[Dict]:
        """Get a specific snapshot by ID. Reassembles chunks if needed."""
        print(f"[SNAPSHOT GET] Getting snapshot {snapshot_id}")
        # Reload from disk to ensure we have the latest data
        self.reload()
        
        snapshot = self._snapshots.get(snapshot_id)
        if snapshot is None:
            print(f"[SNAPSHOT GET] Snapshot {snapshot_id} not found")
            return None
        
        print(f"[SNAPSHOT GET] Found snapshot, keys: {list(snapshot.keys())}")
        print(f"[SNAPSHOT GET] Has subgraph: {'subgraph' in snapshot}, chunked: {snapshot.get('_chunked', False)}")
        
        # Check if this is a chunked snapshot
        if snapshot.get("_chunked") and snapshot.get("_num_chunks"):
            # Reassemble from chunks
            try:
                print(f"[SNAPSHOT GET] Reassembling {snapshot['_num_chunks']} chunks")
                reassembled = reassemble_chunks(snapshot_id, snapshot["_num_chunks"])
                print(f"[SNAPSHOT GET] Reassembled, keys: {list(reassembled.keys())}")
                print(f"[SNAPSHOT GET] Reassembled has subgraph: {'subgraph' in reassembled}")
                if 'subgraph' in reassembled:
                    nodes = reassembled['subgraph'].get('nodes', [])
                    print(f"[SNAPSHOT GET] Reassembled nodes count: {len(nodes) if isinstance(nodes, list) else 'N/A'}")
                # Return a deep copy to prevent mutations from affecting stored data
                result = copy.deepcopy(reassembled)
                nodes = result.get('subgraph', {}).get('nodes', [])
                nodes_count = len(nodes) if isinstance(nodes, list) else 'N/A'
                print(f"[SNAPSHOT GET] After deepcopy, nodes count: {nodes_count}")
                return result
            except Exception as e:
                print(f"[SNAPSHOT GET] Error reassembling chunks for snapshot {snapshot_id}: {e}")
                import traceback
                traceback.print_exc()
                raise
        
        # Not chunked, return a deep copy to prevent mutations from affecting stored data
        if 'subgraph' in snapshot:
            nodes = snapshot['subgraph'].get('nodes', [])
            nodes_count = len(nodes) if isinstance(nodes, list) else 'N/A'
            print(f"[SNAPSHOT GET] Before deepcopy, nodes count: {nodes_count}")
        result = copy.deepcopy(snapshot)
        if 'subgraph' in result:
            nodes = result['subgraph'].get('nodes', [])
            nodes_count = len(nodes) if isinstance(nodes, list) else 'N/A'
            print(f"[SNAPSHOT GET] After deepcopy, nodes count: {nodes_count}")
        print(f"[SNAPSHOT GET] Returning snapshot with keys: {list(result.keys())}")
        return result
    
    def save(self, snapshot_id: str, snapshot_data: Dict):
        """Save a snapshot. Automatically chunks if too large."""
        print(f"[SNAPSHOT SAVE] Starting save for snapshot {snapshot_id}")
        print(f"[SNAPSHOT SAVE] New snapshot has: nodes={len(snapshot_data.get('subgraph', {}).get('nodes', []))}, timeline={len(snapshot_data.get('timeline', []))}, citations={len(snapshot_data.get('citations', {}))}, chat={len(snapshot_data.get('chat_history', []))}")
        
        # Make a deep copy FIRST before reloading to ensure we have a clean copy
        # This prevents any mutations that might happen during reload from affecting our data
        snapshot_data_copy = copy.deepcopy(snapshot_data)
        
        # Serialize and deserialize the snapshot data to ensure complete isolation
        # This removes any potential shared references that deepcopy might miss
        try:
            snapshot_json = json.dumps(snapshot_data_copy, ensure_ascii=False)
            snapshot_data_copy = json.loads(snapshot_json)
        except (ValueError, TypeError, OverflowError):
            # If serialization fails, use the deep copy as-is
            pass
        
        # Reload from disk to get the latest state of all snapshots
        # This ensures we don't overwrite changes made to other snapshots
        self.reload()
        print(f"[SNAPSHOT SAVE] After reload, found {len(self._snapshots)} existing snapshots")
        for existing_id, existing_data in self._snapshots.items():
            if existing_id != snapshot_id:
                existing_nodes = len(existing_data.get("subgraph", {}).get("nodes", [])) if isinstance(existing_data.get("subgraph", {}).get("nodes"), list) else 0
                existing_timeline = len(existing_data.get("timeline", [])) if isinstance(existing_data.get("timeline"), list) else 0
                print(f"[SNAPSHOT SAVE] Existing snapshot {existing_id}: nodes={existing_nodes}, timeline={existing_timeline}, chunked={existing_data.get('_chunked', False)}")
        
        # Store a backup of existing snapshots before modifying
        # Serialize/deserialize to ensure complete isolation
        existing_snapshots_backup = {}
        try:
            backup_json = json.dumps(self._snapshots, ensure_ascii=False)
            existing_snapshots_backup = json.loads(backup_json)
        except (ValueError, TypeError, OverflowError):
            # Fallback to deep copy if serialization fails
            existing_snapshots_backup = copy.deepcopy(self._snapshots)
        
        # Try to save normally first
        try:
            # Test if we can stringify it
            test_json = json.dumps(snapshot_data_copy, ensure_ascii=False)
            # If successful and not too large, save normally
            if len(test_json.encode('utf-8')) < 50 * 1024 * 1024:  # 50MB threshold
                # Only update the specific snapshot, preserving all others
                # DON'T serialize existing snapshots - just use deepcopy to preserve them exactly as they are
                # Serialization can corrupt nested data, so we avoid it for existing snapshots
                updated_snapshots = {}
                print(f"[SNAPSHOT SAVE] Processing {len(self._snapshots)} existing snapshots to preserve")
                for existing_id, existing_data in self._snapshots.items():
                    if existing_id == snapshot_id:
                        # Skip the one we're updating - will add it separately
                        print(f"[SNAPSHOT SAVE] Skipping {existing_id} (being updated)")
                        continue
                    
                    # Skip corrupted snapshots that look like response objects
                    if 'node_count' in existing_data and 'subgraph' not in existing_data:
                        print(f"[SNAPSHOT SAVE] WARNING: Skipping corrupted snapshot {existing_id} (response object, not full data)")
                        continue
                    
                    # Use deepcopy to preserve existing snapshots exactly as they are
                    # This avoids any potential corruption from JSON serialization
                    before_copy_nodes = len(existing_data.get("subgraph", {}).get("nodes", [])) if isinstance(existing_data.get("subgraph", {}).get("nodes"), list) else 0
                    copied = copy.deepcopy(existing_data)
                    after_copy_nodes = len(copied.get("subgraph", {}).get("nodes", [])) if isinstance(copied.get("subgraph", {}).get("nodes"), list) else 0
                    if before_copy_nodes != after_copy_nodes:
                        print(f"[SNAPSHOT SAVE] ERROR: Deepcopy lost data for {existing_id}! Before: {before_copy_nodes}, After: {after_copy_nodes}")
                    updated_snapshots[existing_id] = copied
                    print(f"[SNAPSHOT SAVE] Preserved existing snapshot {existing_id}: nodes={after_copy_nodes}")
                
                print(f"[SNAPSHOT SAVE] After processing existing snapshots, updated_snapshots has {len(updated_snapshots)} snapshots")
                
                # Verify snapshot_data_copy BEFORE serialization
                print(f"[SNAPSHOT SAVE] snapshot_data_copy keys: {list(snapshot_data_copy.keys())}")
                print(f"[SNAPSHOT SAVE] snapshot_data_copy has subgraph: {'subgraph' in snapshot_data_copy}")
                if 'subgraph' in snapshot_data_copy:
                    subgraph = snapshot_data_copy['subgraph']
                    print(f"[SNAPSHOT SAVE] snapshot_data_copy.subgraph type: {type(subgraph)}, keys: {list(subgraph.keys()) if isinstance(subgraph, dict) else 'N/A'}")
                    if isinstance(subgraph, dict) and 'nodes' in subgraph:
                        print(f"[SNAPSHOT SAVE] snapshot_data_copy.subgraph.nodes count: {len(subgraph['nodes']) if isinstance(subgraph['nodes'], list) else 'N/A'}")
                
                # Serialize and deserialize the new snapshot data individually
                try:
                    new_snapshot_json = json.dumps(snapshot_data_copy, ensure_ascii=False)
                    print(f"[SNAPSHOT SAVE] Serialized new snapshot, JSON length: {len(new_snapshot_json)}")
                    new_snapshot_deserialized = json.loads(new_snapshot_json)
                    print(f"[SNAPSHOT SAVE] Deserialized new snapshot, keys: {list(new_snapshot_deserialized.keys())}")
                    # Verify the deserialized data has nested structures
                    has_nodes = bool(new_snapshot_deserialized.get("subgraph", {}).get("nodes"))
                    has_timeline = bool(new_snapshot_deserialized.get("timeline"))
                    has_citations = bool(new_snapshot_deserialized.get("citations"))
                    has_chat = bool(new_snapshot_deserialized.get("chat_history"))
                    node_count = len(new_snapshot_deserialized.get("subgraph", {}).get("nodes", [])) if isinstance(new_snapshot_deserialized.get("subgraph", {}).get("nodes"), list) else 0
                    print(f"[SNAPSHOT SAVE] New snapshot {snapshot_id} after serialization: nodes={node_count}, has_timeline={has_timeline}, citations={has_citations}, chat={has_chat}")
                    updated_snapshots[snapshot_id] = new_snapshot_deserialized
                except (ValueError, TypeError, OverflowError) as e:
                    print(f"[SNAPSHOT SAVE] ERROR: Failed to serialize new snapshot, using deepcopy: {e}")
                    import traceback
                    traceback.print_exc()
                    updated_snapshots[snapshot_id] = copy.deepcopy(snapshot_data_copy)
                
                # Verify that existing snapshots weren't corrupted
                for existing_id, existing_data in existing_snapshots_backup.items():
                    if existing_id != snapshot_id and existing_id in updated_snapshots:
                        # Verify the existing snapshot still has its data
                        existing_backup = existing_snapshots_backup[existing_id]
                        existing_current = updated_snapshots[existing_id]
                        
                        # Check if key fields are still present (basic sanity check)
                        backup_has_data = (
                            existing_backup.get("name") and 
                            (existing_backup.get("subgraph") or existing_backup.get("_chunked"))
                        )
                        current_has_data = (
                            existing_current.get("name") and 
                            (existing_current.get("subgraph") or existing_current.get("_chunked"))
                        )
                        
                        # Also check if subgraph data was lost (nodes/links empty when they shouldn't be)
                        backup_subgraph = existing_backup.get("subgraph", {})
                        current_subgraph = existing_current.get("subgraph", {})
                        backup_has_nodes = bool(backup_subgraph.get("nodes"))
                        current_has_nodes = bool(current_subgraph.get("nodes"))
                        backup_node_count = len(backup_subgraph.get("nodes", [])) if isinstance(backup_subgraph.get("nodes"), list) else 0
                        current_node_count = len(current_subgraph.get("nodes", [])) if isinstance(current_subgraph.get("nodes"), list) else 0
                        
                        # Check timeline, citations, and chat_history
                        backup_timeline = existing_backup.get("timeline", [])
                        current_timeline = existing_current.get("timeline", [])
                        backup_timeline_count = len(backup_timeline) if isinstance(backup_timeline, list) else 0
                        current_timeline_count = len(current_timeline) if isinstance(current_timeline, list) else 0
                        
                        backup_citations = existing_backup.get("citations", {})
                        current_citations = existing_current.get("citations", {})
                        backup_citations_count = len(backup_citations) if isinstance(backup_citations, dict) else 0
                        current_citations_count = len(current_citations) if isinstance(current_citations, dict) else 0
                        
                        backup_chat = existing_backup.get("chat_history", [])
                        current_chat = existing_current.get("chat_history", [])
                        backup_chat_count = len(backup_chat) if isinstance(backup_chat, list) else 0
                        current_chat_count = len(current_chat) if isinstance(current_chat, list) else 0
                        
                        # Check if any nested data was lost
                        data_lost = (
                            (backup_has_data and not current_has_data) or 
                            (backup_has_nodes and not current_has_nodes) or
                            (backup_node_count > 0 and current_node_count == 0) or
                            (backup_timeline_count > 0 and current_timeline_count == 0) or
                            (backup_citations_count > 0 and current_citations_count == 0) or
                            (backup_chat_count > 0 and current_chat_count == 0)
                        )
                        
                        if data_lost:
                            print(f"ERROR: Existing snapshot {existing_id} appears to have lost data during save!")
                            print(f"  Backup: name={existing_backup.get('name')}, nodes={backup_node_count}, timeline={backup_timeline_count}, citations={backup_citations_count}, chat={backup_chat_count}, chunked={existing_backup.get('_chunked')}")
                            print(f"  Current: name={existing_current.get('name')}, nodes={current_node_count}, timeline={current_timeline_count}, citations={current_citations_count}, chat={current_chat_count}, chunked={existing_current.get('_chunked')}")
                            # Restore from backup - serialize/deserialize to ensure isolation
                            try:
                                restore_json = json.dumps(existing_backup, ensure_ascii=False)
                                restored = json.loads(restore_json)
                                # Verify restored data has the nested structures
                                restored_nodes = len(restored.get("subgraph", {}).get("nodes", [])) if isinstance(restored.get("subgraph", {}).get("nodes"), list) else 0
                                restored_timeline = len(restored.get("timeline", [])) if isinstance(restored.get("timeline"), list) else 0
                                print(f"  Restored: nodes={restored_nodes}, timeline={restored_timeline}")
                                updated_snapshots[existing_id] = restored
                                print(f"  Restored snapshot {existing_id} from backup")
                            except (ValueError, TypeError, OverflowError) as e:
                                print(f"  Failed to restore via JSON, using deepcopy: {e}")
                                updated_snapshots[existing_id] = copy.deepcopy(existing_backup)
                # Verify before saving
                print(f"[SNAPSHOT SAVE] About to save {len(updated_snapshots)} snapshots")
                for snap_id, snap_data in updated_snapshots.items():
                    snap_nodes = len(snap_data.get("subgraph", {}).get("nodes", [])) if isinstance(snap_data.get("subgraph", {}).get("nodes"), list) else 0
                    snap_timeline = len(snap_data.get("timeline", [])) if isinstance(snap_data.get("timeline"), list) else 0
                    has_subgraph_key = 'subgraph' in snap_data
                    subgraph_type = type(snap_data.get("subgraph")).__name__ if 'subgraph' in snap_data else 'N/A'
                    print(f"[SNAPSHOT SAVE] Snapshot {snap_id} before save: has_subgraph={has_subgraph_key}, subgraph_type={subgraph_type}, nodes={snap_nodes}, timeline={snap_timeline}")
                    # Check if this looks like a response object (has node_count but no subgraph)
                    if 'node_count' in snap_data and 'subgraph' not in snap_data:
                        print(f"[SNAPSHOT SAVE] ERROR: Snapshot {snap_id} looks like a response object (has node_count but no subgraph)!")
                        print(f"[SNAPSHOT SAVE]   Keys: {list(snap_data.keys())}")
                
                save_snapshots(updated_snapshots)
                
                # Verify IMMEDIATELY after saving by reading from disk
                import time
                time.sleep(0.1)  # Small delay to ensure file is written
                try:
                    with open(STORAGE_FILE, 'r', encoding='utf-8') as f:
                        verify_data = json.load(f)
                    print(f"[SNAPSHOT SAVE] Immediate verification: Read {len(verify_data)} snapshots from disk")
                    for snap_id, snap_data in verify_data.items():
                        if snap_id in updated_snapshots:
                            snap_nodes = len(snap_data.get("subgraph", {}).get("nodes", [])) if isinstance(snap_data.get("subgraph", {}).get("nodes"), list) else 0
                            has_subgraph = 'subgraph' in snap_data
                            print(f"[SNAPSHOT SAVE] Immediate verification: {snap_id}: has_subgraph={has_subgraph}, nodes={snap_nodes}")
                except Exception as e:
                    print(f"[SNAPSHOT SAVE] Could not verify immediately: {e}")
                
                print(f"[SNAPSHOT SAVE] Successfully saved snapshots")
                return
        except (ValueError, TypeError, OverflowError) as e:
            error_msg = str(e).lower()
            if 'invalid string length' not in error_msg and 'string length' not in error_msg and 'overflow' not in error_msg:
                # Different error, re-raise
                raise
        
        # Too large or failed to stringify - use chunking
        chunks, is_chunked = chunk_data(snapshot_data_copy)
        
        # DON'T serialize existing snapshots - just use deepcopy to preserve them exactly as they are
        # Serialization can corrupt nested data, so we avoid it for existing snapshots
        updated_snapshots = {}
        for existing_id, existing_data in self._snapshots.items():
            if existing_id == snapshot_id:
                # Skip the one we're updating - will add it separately
                continue
            
            # Skip corrupted snapshots that look like response objects
            if 'node_count' in existing_data and 'subgraph' not in existing_data:
                print(f"[SNAPSHOT SAVE] WARNING: Skipping corrupted snapshot {existing_id} (response object, not full data)")
                continue
            
            # Use deepcopy to preserve existing snapshots exactly as they are
            # This avoids any potential corruption from JSON serialization
            updated_snapshots[existing_id] = copy.deepcopy(existing_data)
        
        if is_chunked:
            # Save chunks to disk
            for i, chunk_json in enumerate(chunks):
                save_chunk(snapshot_id, i, chunk_json)
            
            # Save metadata in main storage pointing to chunks
            chunk_metadata_raw = {
                "id": snapshot_id,
                "name": snapshot_data_copy.get("name"),
                "notes": snapshot_data_copy.get("notes"),
                "timestamp": snapshot_data_copy.get("timestamp"),
                "created_at": snapshot_data_copy.get("created_at"),
                "owner": snapshot_data_copy.get("owner"),
                "case_id": snapshot_data_copy.get("case_id"),
                "case_version": snapshot_data_copy.get("case_version"),
                "case_name": snapshot_data_copy.get("case_name"),
                "_chunked": True,
                "_num_chunks": len(chunks),
            }
            # Serialize/deserialize metadata to ensure isolation
            try:
                metadata_json = json.dumps(chunk_metadata_raw, ensure_ascii=False)
                chunk_metadata = json.loads(metadata_json)
            except (ValueError, TypeError, OverflowError):
                chunk_metadata = copy.deepcopy(chunk_metadata_raw)
            updated_snapshots[snapshot_id] = chunk_metadata
        else:
            # Single chunk, save normally - serialize/deserialize one more time for safety
            try:
                new_snapshot_json = json.dumps(snapshot_data_copy, ensure_ascii=False)
                updated_snapshots[snapshot_id] = json.loads(new_snapshot_json)
            except (ValueError, TypeError, OverflowError):
                # Fallback to deep copy if serialization fails
                updated_snapshots[snapshot_id] = copy.deepcopy(snapshot_data_copy)
        
        # Verify that existing snapshots weren't corrupted
        for existing_id, existing_data in existing_snapshots_backup.items():
            if existing_id != snapshot_id and existing_id in updated_snapshots:
                # Verify the existing snapshot still has its data
                existing_backup = existing_snapshots_backup[existing_id]
                existing_current = updated_snapshots[existing_id]
                
                # Check if key fields are still present
                backup_has_data = (
                    existing_backup.get("name") and 
                    (existing_backup.get("subgraph") or existing_backup.get("_chunked"))
                )
                current_has_data = (
                    existing_current.get("name") and 
                    (existing_current.get("subgraph") or existing_current.get("_chunked"))
                )
                
                # Also check if subgraph data was lost (nodes/links empty when they shouldn't be)
                backup_subgraph = existing_backup.get("subgraph", {})
                current_subgraph = existing_current.get("subgraph", {})
                backup_has_nodes = bool(backup_subgraph.get("nodes"))
                current_has_nodes = bool(current_subgraph.get("nodes"))
                
                if (backup_has_data and not current_has_data) or (backup_has_nodes and not current_has_nodes):
                    print(f"ERROR: Existing snapshot {existing_id} appears to have lost data during save!")
                    print(f"  Backup: name={existing_backup.get('name')}, has_subgraph={bool(existing_backup.get('subgraph'))}, has_nodes={backup_has_nodes}, chunked={existing_backup.get('_chunked')}")
                    print(f"  Current: name={existing_current.get('name')}, has_subgraph={bool(existing_current.get('subgraph'))}, has_nodes={current_has_nodes}, chunked={existing_current.get('_chunked')}")
                    # Restore from backup - serialize/deserialize to ensure isolation
                    try:
                        restore_json = json.dumps(existing_backup, ensure_ascii=False)
                        updated_snapshots[existing_id] = json.loads(restore_json)
                        print(f"  Restored snapshot {existing_id} from backup")
                    except (ValueError, TypeError, OverflowError) as e:
                        print(f"  Failed to restore via JSON, using deepcopy: {e}")
                        updated_snapshots[existing_id] = copy.deepcopy(existing_backup)
        
        # Update in-memory cache after successful validation
        self._snapshots = updated_snapshots
        
        save_snapshots(updated_snapshots)
    
    def delete(self, snapshot_id: str) -> bool:
        """Delete a snapshot. Returns True if deleted, False if not found."""
        # Reload from disk first to ensure we have the latest data
        self.reload()
        
        if snapshot_id in self._snapshots:
            snapshot = self._snapshots[snapshot_id]
            # If chunked, delete chunks too
            if snapshot.get("_chunked") and snapshot.get("_num_chunks"):
                delete_chunks(snapshot_id, snapshot["_num_chunks"])
            
            del self._snapshots[snapshot_id]
            # Make a deep copy of the entire dictionary before saving to prevent any reference issues
            save_snapshots(copy.deepcopy(self._snapshots))
            return True
        return False
    
    def reload(self):
        """Reload snapshots from disk."""
        self._snapshots = load_snapshots()
        # Log what was loaded
        print(f"[RELOAD] Loaded {len(self._snapshots)} snapshots from disk")
        for snap_id, snap_data in self._snapshots.items():
            has_subgraph = 'subgraph' in snap_data
            if has_subgraph:
                nodes = snap_data['subgraph'].get('nodes', [])
                nodes_count = len(nodes) if isinstance(nodes, list) else 0
                print(f"[RELOAD] Snapshot {snap_id}: has_subgraph={has_subgraph}, nodes={nodes_count}")
            else:
                print(f"[RELOAD] Snapshot {snap_id}: has_subgraph={has_subgraph}, keys={list(snap_data.keys())[:5]}")


# Singleton instance
snapshot_storage = SnapshotStorage()



