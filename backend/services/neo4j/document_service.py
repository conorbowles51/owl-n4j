"""
Document Service — document summary retrieval, folder summaries,
transcription/translation lookup, and evidence file deletion.
"""

import logging
from typing import Any, Dict, List, Optional

from services.neo4j.driver import driver

logger = logging.getLogger(__name__)


class DocumentService:

    def get_document_summary(self, doc_name: str, case_id: str) -> Optional[str]:
        """
        Get the summary for a document by its name.

        Args:
            doc_name: Document filename/name
            case_id: Case ID to filter by

        Returns:
            Document summary if found, None otherwise
        """
        # Normalise the document name to match the key format used during ingestion
        # This matches the normalise_key function from ingestion/scripts/entity_resolution.py
        import re
        doc_key = doc_name.strip().lower()
        doc_key = re.sub(r"[\s_]+", "-", doc_key)
        doc_key = re.sub(r"[^a-z0-9\-]", "", doc_key)
        doc_key = re.sub(r"-+", "-", doc_key)
        doc_key = doc_key.strip("-")

        with driver.session() as session:
            result = session.run(
                """
                MATCH (d:Document {key: $doc_key, case_id: $case_id})
                RETURN d.summary AS summary
                """,
                doc_key=doc_key,
                case_id=case_id,
            )
            record = result.single()
            if record and record["summary"]:
                return record["summary"]
            return None

    def get_document_summaries_batch(self, doc_names: List[str], case_id: str) -> Dict[str, Optional[str]]:
        """
        Get summaries for multiple documents by their names.

        Args:
            doc_names: List of document filenames/names
            case_id: Case ID to filter by

        Returns:
            Dict mapping doc_name -> summary (None if not found)
        """
        # Normalise all document names
        import re
        summaries = {}

        # Build normalized keys map
        doc_key_map = {}  # doc_key -> doc_name
        for doc_name in doc_names:
            doc_key = doc_name.strip().lower()
            doc_key = re.sub(r"[\s_]+", "-", doc_key)
            doc_key = re.sub(r"[^a-z0-9\-]", "", doc_key)
            doc_key = re.sub(r"-+", "-", doc_key)
            doc_key = doc_key.strip("-")
            doc_key_map[doc_key] = doc_name

        if not doc_key_map:
            return summaries

        with driver.session() as session:
            result = session.run(
                """
                MATCH (d:Document)
                WHERE d.key IN $doc_keys AND d.case_id = $case_id
                RETURN d.key AS key, d.summary AS summary
                """,
                doc_keys=list(doc_key_map.keys()),
                case_id=case_id,
            )

            for record in result:
                doc_key = record["key"]
                summary = record["summary"]
                doc_name = doc_key_map.get(doc_key)
                if doc_name:
                    summaries[doc_name] = summary if summary else None

        # Fill in None for docs that weren't found
        for doc_name in doc_names:
            if doc_name not in summaries:
                summaries[doc_name] = None

        return summaries

    def get_folder_summary(self, folder_name: str, case_id: str) -> Optional[str]:
        """
        Get the summary for a folder by its folder name.

        This looks for documents that were created from folder processing,
        identified by having 'folder_name' in their metadata.

        Args:
            folder_name: Name of the folder (e.g., "00000128")
            case_id: Case ID to filter by

        Returns:
            Folder summary if found, None otherwise
        """
        with driver.session() as session:
            # Look for documents with folder_name in metadata
            # Folder documents are created with metadata containing folder_name
            result = session.run(
                """
                MATCH (d:Document {case_id: $case_id})
                WHERE d.folder_name = $folder_name
                   OR (d.metadata IS NOT NULL AND d.metadata.folder_name = $folder_name)
                RETURN d.summary AS summary
                ORDER BY d.created_at DESC
                LIMIT 1
                """,
                folder_name=folder_name,
                case_id=case_id,
            )
            record = result.single()
            if record and record["summary"]:
                return record["summary"]

            # Fallback: Try to find by document name pattern {profile}_{folder_name}
            # This matches the naming convention used in folder_ingestion.py
            result = session.run(
                """
                MATCH (d:Document {case_id: $case_id})
                WHERE d.name CONTAINS $folder_name
                   OR d.key CONTAINS $folder_name_normalized
                RETURN d.summary AS summary
                ORDER BY d.created_at DESC
                LIMIT 1
                """,
                folder_name=folder_name,
                folder_name_normalized=folder_name.lower().replace("_", "-"),
                case_id=case_id,
            )
            record = result.single()
            if record and record["summary"]:
                return record["summary"]

            return None

    def get_transcription_translation(self, folder_name: str, case_id: str) -> dict:
        """
        Get wiretap Spanish transcription and English translation for a folder, when available.
        Looks for Neo4j Document nodes: wiretap_{folder}_transcription_spanish,
        wiretap_{folder}_translation_english.

        Args:
            folder_name: Folder name (e.g. "00000128")
            case_id: Case ID

        Returns:
            {"spanish_transcription": str or None, "english_translation": str or None}
        """
        out = {"spanish_transcription": None, "english_translation": None}
        spanish_doc = f"wiretap_{folder_name}_transcription_spanish"
        english_doc = f"wiretap_{folder_name}_translation_english"
        s = self.get_document_summary(spanish_doc, case_id)
        e = self.get_document_summary(english_doc, case_id)
        if s and s.strip():
            out["spanish_transcription"] = s.strip()
        if e and e.strip():
            out["english_translation"] = e.strip()
        return out

    # -------------------------------------------------------------------------
    # Evidence File Deletion
    # -------------------------------------------------------------------------

    def find_document_node(self, filename: str, case_id: str) -> Optional[Dict[str, Any]]:
        """
        Find a Document node by filename and case_id.

        Returns:
            Dict with document node info, or None if not found.
        """
        with driver.session() as session:
            result = session.run(
                """
                MATCH (d:Document {case_id: $case_id})
                WHERE d.name = $filename OR d.key = $filename
                RETURN d.key AS key, d.name AS name, d.case_id AS case_id,
                       id(d) AS neo4j_id
                """,
                filename=filename,
                case_id=case_id,
            )
            record = result.single()
            if record:
                return dict(record)
            return None

    def find_exclusive_entities(self, doc_key: str, case_id: str) -> List[Dict[str, Any]]:
        """
        Find entities that are ONLY mentioned in the given document
        (i.e. they have no MENTIONED_IN relationship to any other Document).

        Args:
            doc_key: Key of the Document node
            case_id: Case ID for scoping

        Returns:
            List of entity dicts with key, name, type
        """
        with driver.session() as session:
            result = session.run(
                """
                MATCH (entity)-[:MENTIONED_IN]->(doc:Document {key: $doc_key, case_id: $case_id})
                WHERE entity.case_id = $case_id
                WITH entity
                OPTIONAL MATCH (entity)-[:MENTIONED_IN]->(other:Document {case_id: $case_id})
                  WHERE other.key <> $doc_key
                WITH entity, count(other) AS other_doc_count
                WHERE other_doc_count = 0
                RETURN DISTINCT entity.key AS key, entity.name AS name,
                       labels(entity)[0] AS type
                """,
                doc_key=doc_key,
                case_id=case_id,
            )
            return [dict(record) for record in result]

    def delete_document_and_exclusive_entities(
        self, doc_key: str, case_id: str
    ) -> Dict[str, Any]:
        """
        Delete a Document node from the graph, along with any entities
        exclusively mentioned in that document (not shared with other docs).

        Args:
            doc_key: Key of the Document node to delete
            case_id: Case ID for scoping

        Returns:
            Dict with deleted_document, exclusive_entities_deleted, shared_entities_unlinked
        """
        with driver.session() as session:
            # 1. Verify document exists
            doc_result = session.run(
                """
                MATCH (d:Document {key: $doc_key, case_id: $case_id})
                RETURN d.key AS key, d.name AS name
                """,
                doc_key=doc_key,
                case_id=case_id,
            )
            doc_record = doc_result.single()
            if not doc_record:
                raise ValueError(f"Document not found: {doc_key} in case {case_id}")

            # 2. Find exclusive entities (only linked to this document)
            #    An entity is "exclusive" if its only MENTIONED_IN target is this doc.
            exclusive_result = session.run(
                """
                MATCH (entity)-[:MENTIONED_IN]->(doc:Document {key: $doc_key, case_id: $case_id})
                WHERE entity.case_id = $case_id
                WITH entity
                OPTIONAL MATCH (entity)-[:MENTIONED_IN]->(other:Document {case_id: $case_id})
                  WHERE other.key <> $doc_key
                WITH entity, count(other) AS other_doc_count
                WHERE other_doc_count = 0
                RETURN entity.key AS key, entity.name AS name,
                       labels(entity)[0] AS type
                """,
                doc_key=doc_key,
                case_id=case_id,
            )
            exclusive_entities = [dict(r) for r in exclusive_result]

            # 3. Find shared entities (linked to this doc AND other docs)
            shared_result = session.run(
                """
                MATCH (entity)-[:MENTIONED_IN]->(doc:Document {key: $doc_key, case_id: $case_id})
                WHERE entity.case_id = $case_id
                WITH entity
                OPTIONAL MATCH (entity)-[:MENTIONED_IN]->(other:Document {case_id: $case_id})
                  WHERE other.key <> $doc_key
                WITH entity, count(other) AS other_doc_count
                WHERE other_doc_count > 0
                RETURN entity.key AS key, entity.name AS name,
                       labels(entity)[0] AS type
                """,
                doc_key=doc_key,
                case_id=case_id,
            )
            shared_entities = [dict(r) for r in shared_result]

            # 4. Delete exclusive entities (DETACH DELETE removes all their rels)
            exclusive_keys = [e["key"] for e in exclusive_entities]
            if exclusive_keys:
                session.run(
                    """
                    MATCH (entity {case_id: $case_id})
                    WHERE entity.key IN $keys
                    DETACH DELETE entity
                    """,
                    case_id=case_id,
                    keys=exclusive_keys,
                )

            # 5. Remove MENTIONED_IN rels from shared entities to this doc
            if shared_entities:
                session.run(
                    """
                    MATCH (entity)-[r:MENTIONED_IN]->(doc:Document {key: $doc_key, case_id: $case_id})
                    WHERE entity.case_id = $case_id
                    DELETE r
                    """,
                    doc_key=doc_key,
                    case_id=case_id,
                )

            # 6. Delete the Document node itself (and all remaining rels)
            session.run(
                """
                MATCH (d:Document {key: $doc_key, case_id: $case_id})
                DETACH DELETE d
                """,
                doc_key=doc_key,
                case_id=case_id,
            )

            return {
                "success": True,
                "deleted_document": {"key": doc_record["key"], "name": doc_record["name"]},
                "exclusive_entities_deleted": exclusive_entities,
                "shared_entities_unlinked": [e["key"] for e in shared_entities],
            }


document_service = DocumentService()
