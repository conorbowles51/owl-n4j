"""
Backup Service for Case Data

Handles exporting and importing complete case backups including:
- Neo4j nodes and relationships
- Vector DB documents and embeddings
- Case metadata and versions
- Evidence file records
"""

import json
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from io import BytesIO

from services.neo4j_service import neo4j_service
from services.vector_db_service import vector_db_service
from services.case_storage import case_storage
from services.evidence_storage import evidence_storage


class BackupService:
    """Service for creating and restoring case backups."""
    
    def export_case(
        self,
        case_id: str,
        include_files: bool = False
    ) -> Dict[str, Any]:
        """
        Export all data for a case into a structured backup format.
        
        Args:
            case_id: Case ID to export
            include_files: If True, include actual file contents (can be large)
        
        Returns:
            Dict containing all case data ready for serialization
        """
        backup_data = {
            "version": "1.0",
            "exported_at": datetime.now().isoformat(),
            "case_id": case_id,
            "case_metadata": None,
            "neo4j_data": {
                "nodes": [],
                "relationships": []
            },
            "vector_db_data": {
                "documents": [],
                "entities": []
            },
            "evidence_records": [],
            "files": [] if include_files else None
        }
        
        # 1. Export case metadata
        case = case_storage.get_case(case_id)
        if case:
            backup_data["case_metadata"] = case
        
        # 2. Export Neo4j data
        graph_data = neo4j_service.get_full_graph(case_id=case_id)
        backup_data["neo4j_data"]["nodes"] = graph_data.get("nodes", [])
        backup_data["neo4j_data"]["relationships"] = graph_data.get("links", [])
        
        # 3. Export Vector DB data
        if vector_db_service is None:
            print("[Backup] Warning: VectorDBService unavailable, skipping vector DB export")
        else:
            try:
                # Get all documents and filter by case_id
                # ChromaDB's get() doesn't reliably support where filters, so we get all and filter
                try:
                    all_docs = vector_db_service.collection.get()
                    if all_docs and all_docs.get("ids"):
                        for i, doc_id in enumerate(all_docs["ids"]):
                            metadata = all_docs.get("metadatas", [{}])[i] if all_docs.get("metadatas") else {}
                            # Filter by case_id
                            if metadata.get("case_id") == case_id:
                                embedding = all_docs.get("embeddings", [[]])[i] if all_docs.get("embeddings") else []
                                text = all_docs.get("documents", [""])[i] if all_docs.get("documents") else ""
                                
                                doc_data = {
                                    "id": doc_id,
                                    "text": text,
                                    "embedding": embedding,
                                    "metadata": metadata
                                }
                                backup_data["vector_db_data"]["documents"].append(doc_data)
                except Exception as e:
                    print(f"[Backup] Failed to export documents: {e}")
                
                # Get all entities and filter by case_id
                try:
                    all_entities = vector_db_service.entity_collection.get()
                    if all_entities and all_entities.get("ids"):
                        for i, entity_id in enumerate(all_entities["ids"]):
                            metadata = all_entities.get("metadatas", [{}])[i] if all_entities.get("metadatas") else {}
                            # Filter by case_id
                            if metadata.get("case_id") == case_id:
                                embedding = all_entities.get("embeddings", [[]])[i] if all_entities.get("embeddings") else []
                                text = all_entities.get("documents", [""])[i] if all_entities.get("documents") else ""
                                
                                entity_data = {
                                    "id": entity_id,
                                    "text": text,
                                    "embedding": embedding,
                                    "metadata": metadata
                                }
                                backup_data["vector_db_data"]["entities"].append(entity_data)
                except Exception as e:
                    print(f"[Backup] Failed to export entities: {e}")
            except Exception as e:
                print(f"[Backup] Warning: Failed to export vector DB data: {e}")
        
        # 4. Export evidence records
        evidence_files = evidence_storage.list_files(case_id=case_id)
        backup_data["evidence_records"] = evidence_files
        
        # 5. Export file contents if requested
        if include_files:
            for evidence in evidence_files:
                stored_path = evidence.get("stored_path")
                if stored_path:
                    file_path = Path(stored_path)
                    if file_path.exists() and file_path.is_file():
                        try:
                            with open(file_path, 'rb') as f:
                                file_data = f.read()
                                backup_data["files"].append({
                                    "evidence_id": evidence.get("id"),
                                    "path": stored_path,
                                    "content": file_data.hex()  # Store as hex string for JSON serialization
                                })
                        except Exception as e:
                            print(f"[Backup] Warning: Failed to read file {stored_path}: {e}")
        
        return backup_data
    
    def create_backup_file(
        self,
        case_id: str,
        include_files: bool = False
    ) -> BytesIO:
        """
        Create a ZIP file containing the case backup.
        
        Args:
            case_id: Case ID to backup
            include_files: If True, include actual file contents
        
        Returns:
            BytesIO object containing the ZIP file
        """
        # Export case data
        backup_data = self.export_case(case_id, include_files=include_files)
        
        # Create ZIP file in memory
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Add backup data as JSON
            backup_json = json.dumps(backup_data, indent=2, ensure_ascii=False, default=str)
            zip_file.writestr("backup.json", backup_json.encode('utf-8'))
            
            # Add files if included
            if include_files and backup_data.get("files"):
                for file_info in backup_data["files"]:
                    file_name = Path(file_info["path"]).name
                    file_content = bytes.fromhex(file_info["content"])
                    zip_file.writestr(f"files/{file_name}", file_content)
        
        zip_buffer.seek(0)
        return zip_buffer
    
    def import_case(
        self,
        backup_data: Dict[str, Any],
        new_case_id: Optional[str] = None,
        overwrite: bool = False
    ) -> Dict[str, Any]:
        """
        Import a case backup into the system.
        
        Args:
            backup_data: Backup data dict from export_case
            new_case_id: Optional new case ID (if None, uses original)
            overwrite: If True, overwrite existing case data
        
        Returns:
            Dict with import results
        """
        original_case_id = backup_data.get("case_id")
        target_case_id = new_case_id or original_case_id
        
        if not target_case_id:
            raise ValueError("Case ID is required for import")
        
        # Check if case exists
        existing_case = case_storage.get_case(target_case_id)
        if existing_case and not overwrite:
            raise ValueError(f"Case {target_case_id} already exists. Use overwrite=True to replace it.")
        
        results = {
            "case_id": target_case_id,
            "nodes_imported": 0,
            "relationships_imported": 0,
            "documents_imported": 0,
            "entities_imported": 0,
            "evidence_records_imported": 0,
            "errors": []
        }
        
        try:
            # 1. Import case metadata
            if backup_data.get("case_metadata"):
                case_meta = backup_data["case_metadata"].copy()
                case_meta["id"] = target_case_id
                
                # Use case_storage to properly save the case
                # Get all versions from backup
                versions = case_meta.get("versions", [])
                
                # If overwriting, delete existing case first
                if overwrite:
                    existing = case_storage.get_case(target_case_id)
                    if existing:
                        case_storage.delete_case(target_case_id)
                
                # Create case with first version if versions exist
                if versions:
                    first_version = versions[0]
                    case_storage.save_case_version(
                        case_id=target_case_id,
                        case_name=case_meta.get("name", "Restored Case"),
                        snapshots=first_version.get("snapshots", []),
                        save_notes=first_version.get("save_notes", "Restored from backup"),
                        owner=case_meta.get("owner")
                    )
                    
                    # Save additional versions
                    for version in versions[1:]:
                        case_storage.save_case_version(
                            case_id=target_case_id,
                            case_name=case_meta.get("name", "Restored Case"),
                            snapshots=version.get("snapshots", []),
                            save_notes=version.get("save_notes", ""),
                            owner=case_meta.get("owner")
                        )
                else:
                    # Create case without versions
                    case_storage.save_case_version(
                        case_id=target_case_id,
                        case_name=case_meta.get("name", "Restored Case"),
                        snapshots=[],
                        save_notes="Restored from backup",
                        owner=case_meta.get("owner")
                    )
                
                results["case_metadata_imported"] = True
            else:
                results["errors"].append("No case metadata in backup")
            
            # 2. Import Neo4j data
            neo4j_data = backup_data.get("neo4j_data", {})
            nodes = neo4j_data.get("nodes", [])
            relationships = neo4j_data.get("relationships", [])
            
            # Import nodes
            with neo4j_service._driver.session() as session:
                for node in nodes:
                    try:
                        # Update case_id to target_case_id
                        node_props = node.get("properties", {})
                        node_props["case_id"] = target_case_id
                        
                        # Get node type
                        node_type = node.get("type", "Node")
                        node_key = node.get("key")
                        node_id = node.get("id")
                        
                        if not node_key:
                            continue
                        
                        # Create or update node
                        query = f"""
                        MERGE (n:{node_type} {{key: $key, case_id: $case_id}})
                        SET n = $props
                        RETURN n
                        """
                        session.run(query, key=node_key, case_id=target_case_id, props=node_props)
                        results["nodes_imported"] += 1
                    except Exception as e:
                        results["errors"].append(f"Failed to import node {node.get('key')}: {e}")
                
                # Import relationships
                # Relationships from get_full_graph are in format: {source: key, target: key, type: "RELATED_TO"}
                for rel in relationships:
                    try:
                        # Handle different relationship formats
                        if isinstance(rel.get("source"), dict):
                            source_key = rel.get("source", {}).get("key")
                        else:
                            source_key = rel.get("source")
                        
                        if isinstance(rel.get("target"), dict):
                            target_key = rel.get("target", {}).get("key")
                        else:
                            target_key = rel.get("target")
                        
                        rel_type = rel.get("type", "RELATED_TO")
                        
                        if not source_key or not target_key:
                            continue
                        
                        # Sanitize relationship type for Cypher (similar to entity types)
                        import re
                        sanitized_type = rel_type.strip()
                        sanitized_type = re.sub(r'[^a-zA-Z0-9_]', '_', sanitized_type)
                        sanitized_type = re.sub(r'_+', '_', sanitized_type)
                        sanitized_type = sanitized_type.strip('_')
                        if not sanitized_type:
                            sanitized_type = "RELATED_TO"
                        
                        # Create relationship
                        query = f"""
                        MATCH (a), (b)
                        WHERE a.key = $source_key AND a.case_id = $case_id
                          AND b.key = $target_key AND b.case_id = $case_id
                        MERGE (a)-[r:`{sanitized_type}`]->(b)
                        RETURN r
                        """
                        session.run(query, source_key=source_key, target_key=target_key, case_id=target_case_id)
                        results["relationships_imported"] += 1
                    except Exception as e:
                        results["errors"].append(f"Failed to import relationship: {e}")
            
            # 3. Import Vector DB data
            if vector_db_service is None:
                print("[Backup] Warning: VectorDBService unavailable, skipping vector DB import")
            else:
                vector_data = backup_data.get("vector_db_data", {})
                
                # Import documents
                for doc in vector_data.get("documents", []):
                    try:
                        doc_id = doc.get("id")
                        text = doc.get("text", "")
                        embedding = doc.get("embedding", [])
                        metadata = doc.get("metadata", {})
                        metadata["case_id"] = target_case_id
                        
                        if doc_id and embedding:
                            vector_db_service.collection.upsert(
                                ids=[doc_id],
                                embeddings=[embedding],
                                documents=[text],
                                metadatas=[metadata]
                            )
                            results["documents_imported"] += 1
                    except Exception as e:
                        results["errors"].append(f"Failed to import document {doc.get('id')}: {e}")
                
                # Import entities
                for entity in vector_data.get("entities", []):
                    try:
                        entity_id = entity.get("id")
                        text = entity.get("text", "")
                        embedding = entity.get("embedding", [])
                        metadata = entity.get("metadata", {})
                        metadata["case_id"] = target_case_id
                        
                        if entity_id and embedding:
                            vector_db_service.entity_collection.upsert(
                                ids=[entity_id],
                                embeddings=[embedding],
                                documents=[text],
                                metadatas=[metadata]
                            )
                            results["entities_imported"] += 1
                    except Exception as e:
                        results["errors"].append(f"Failed to import entity {entity.get('id')}: {e}")
            
            # 4. Import evidence records
            # Note: Evidence records are stored in JSON file, but restoring them properly
            # would require writing to evidence_storage. For now, we'll just count them.
            # In a full implementation, you'd use evidence_storage.add_files() or similar
            evidence_records = backup_data.get("evidence_records", [])
            results["evidence_records_imported"] = len(evidence_records)
            if evidence_records:
                results["errors"].append(f"Note: {len(evidence_records)} evidence records found in backup but not automatically restored. Evidence files should be re-uploaded if needed.")
        
        except Exception as e:
            results["errors"].append(f"Import failed: {e}")
            raise
        
        return results
    
    def import_from_file(
        self,
        backup_file: BytesIO,
        new_case_id: Optional[str] = None,
        overwrite: bool = False
    ) -> Dict[str, Any]:
        """
        Import a backup from a ZIP file.
        
        Args:
            backup_file: BytesIO containing the backup ZIP file
            new_case_id: Optional new case ID
            overwrite: If True, overwrite existing case
        
        Returns:
            Import results
        """
        with zipfile.ZipFile(backup_file, 'r') as zip_file:
            # Read backup.json
            backup_json = zip_file.read("backup.json").decode('utf-8')
            backup_data = json.loads(backup_json)
            
            # Extract files if present
            if "files" in backup_data and backup_data["files"]:
                # Note: File restoration would need to write files to disk
                # This is a simplified version
                pass
        
        return self.import_case(backup_data, new_case_id=new_case_id, overwrite=overwrite)


# Singleton instance
backup_service = BackupService()
