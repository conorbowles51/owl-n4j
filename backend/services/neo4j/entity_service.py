"""
Entity Service — CRUD operations on entity nodes, fact/insight management,
similarity detection, merge, soft-delete / recycle-bin, and batch helpers.
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from services.neo4j.driver import driver, parse_json_field
from postgres.models.graph_recycle_bin import GraphRecycleBinItem

logger = logging.getLogger(__name__)


class EntityService:
    INTERNAL_LABELS = {"Document", "Case", "RecycleBin", "RecycleBinItem"}

    @staticmethod
    def _case_uuid(case_id: str) -> uuid.UUID:
        return uuid.UUID(str(case_id))

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (list, tuple)):
            return [EntityService._json_safe(v) for v in value]
        if isinstance(value, dict):
            return {str(k): EntityService._json_safe(v) for k, v in value.items()}
        if hasattr(value, "iso_format"):
            return value.iso_format()
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    @staticmethod
    def _neo4j_property_value(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, list):
            cleaned = [EntityService._neo4j_property_value(v) for v in value]
            return [v for v in cleaned if v is not None]
        return json.dumps(value, default=str)

    @staticmethod
    def _escape_cypher_identifier(value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", (value or "").strip())
        cleaned = re.sub(r"_+", "_", cleaned).strip("_")
        return cleaned or "Entity"

    @staticmethod
    def _recycle_key(original_key: str) -> str:
        return f"recycled_{original_key}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"

    def _snapshot_entity(self, session, node_key: str, case_id: str) -> Dict[str, Any]:
        """Capture a complete restorable Neo4j entity snapshot for this case."""
        entity_result = session.run(
            """
            MATCH (n {key: $key, case_id: $case_id})
            WHERE NONE(label IN labels(n) WHERE label IN ['Document', 'Case', 'RecycleBin', 'RecycleBinItem'])
              AND coalesce(properties(n)['system_node'], false) <> true
            RETURN n.key AS key, n.name AS name, labels(n) AS labels,
                   properties(n) AS props
            """,
            key=node_key,
            case_id=case_id,
        )
        entity_record = entity_result.single()
        if not entity_record:
            raise ValueError(f"Entity not found: {node_key} in case {case_id}")

        labels = [label for label in list(entity_record["labels"] or []) if label not in self.INTERNAL_LABELS]
        if not labels:
            raise ValueError(f"Entity {node_key} has no restorable labels")

        rels_result = session.run(
            """
            MATCH (n {key: $key, case_id: $case_id})-[r]-(other {case_id: $case_id})
            WHERE coalesce(properties(other)['system_node'], false) <> true
              AND NONE(label IN labels(other) WHERE label IN ['RecycleBin', 'RecycleBinItem'])
              AND r.case_id = $case_id
            RETURN type(r) AS rel_type, properties(r) AS rel_props,
                   other.key AS other_key, other.name AS other_name,
                   labels(other)[0] AS other_type,
                   CASE WHEN startNode(r) = n THEN 'outgoing' ELSE 'incoming' END AS direction
            """,
            key=node_key,
            case_id=case_id,
        )

        return {
            "original_key": entity_record["key"],
            "name": entity_record["name"],
            "labels": labels,
            "properties": self._json_safe(dict(entity_record["props"] or {})),
            "relationships": [self._json_safe(dict(r)) for r in rels_result],
        }

    def _props_for_snapshot(self, snapshot: Dict[str, Any], case_id: str, key_override: str = None) -> Dict[str, Any]:
        props = {}
        for key, value in (snapshot.get("properties") or {}).items():
            prop_value = self._neo4j_property_value(value)
            if prop_value is not None:
                props[key] = prop_value
        props["key"] = key_override or snapshot.get("original_key")
        props["case_id"] = case_id
        return props

    def _label_clause_for_snapshot(self, snapshot: Dict[str, Any]) -> str:
        labels = [self._escape_cypher_identifier(label) for label in (snapshot.get("labels") or ["Entity"])]
        labels = [label for label in labels if label not in self.INTERNAL_LABELS] or ["Entity"]
        return "".join(f":`{label}`" for label in labels)

    def _restore_snapshot_node(self, tx, snapshot: Dict[str, Any], case_id: str, key_override: str = None) -> Dict[str, Any]:
        props = self._props_for_snapshot(snapshot, case_id, key_override=key_override)
        labels = [self._escape_cypher_identifier(label) for label in (snapshot.get("labels") or ["Entity"])]
        labels = [label for label in labels if label not in self.INTERNAL_LABELS] or ["Entity"]
        tx.run(
            f"""
            CREATE (n{''.join(f':`{label}`' for label in labels)})
            SET n = $props
            """,
            props=props,
        )
        return {
            "key": props.get("key"),
            "name": props.get("name") or snapshot.get("name") or "",
            "type": labels[0],
            "properties": props,
        }

    def _restore_snapshot_relationships(self, tx, snapshot: Dict[str, Any], case_id: str, key_override: str = None) -> int:
        node_key = key_override or snapshot.get("original_key")
        restored = 0
        for rel in snapshot.get("relationships") or []:
            other_key = rel.get("other_key")
            raw_rel_type = rel.get("rel_type")
            direction = rel.get("direction")
            if not node_key or not other_key or not raw_rel_type or node_key == other_key:
                continue

            rel_props = {}
            for prop_key, prop_value in (rel.get("rel_props") or {}).items():
                restored_value = self._neo4j_property_value(prop_value)
                if restored_value is not None:
                    rel_props[prop_key] = restored_value
            rel_props["case_id"] = case_id

            if direction == "outgoing":
                a_key, b_key = node_key, other_key
            else:
                a_key, b_key = other_key, node_key

            result = tx.run(
                f"""
                MATCH (a {{key: $a_key, case_id: $case_id}})
                MATCH (b {{key: $b_key, case_id: $case_id}})
                WHERE NONE(label IN labels(a) WHERE label IN ['RecycleBin', 'RecycleBinItem'])
                  AND NONE(label IN labels(b) WHERE label IN ['RecycleBin', 'RecycleBinItem'])
                  AND coalesce(properties(a)['system_node'], false) <> true
                  AND coalesce(properties(b)['system_node'], false) <> true
                MERGE (a)-[r:`{self._escape_cypher_identifier(raw_rel_type)}`]->(b)
                SET r += $props
                RETURN count(r) AS cnt
                """,
                a_key=a_key,
                b_key=b_key,
                case_id=case_id,
                props=rel_props,
            )
            restored += result.single()["cnt"]
        return restored

    @staticmethod
    def _delete_entity_embedding(entity_key: str) -> None:
        try:
            from services.vector_db_service import get_vector_db_service

            vector_db = get_vector_db_service()
            if vector_db:
                vector_db.delete_entity(entity_key)
        except Exception as e:
            logger.warning("Failed to delete entity embedding for %s: %s", entity_key, e)

    @staticmethod
    def _rebuild_entity_embedding(entity: Dict[str, Any], case_id: str) -> None:
        try:
            from services.embedding_service import EmbeddingService
            from services.vector_db_service import get_vector_db_service

            vector_db = get_vector_db_service()
            if not vector_db:
                return

            props = entity.get("properties") or {}
            text_parts = [
                str(props.get("name") or entity.get("name") or entity.get("key") or ""),
                str(props.get("summary") or ""),
                str(props.get("notes") or ""),
                str(props.get("verified_facts") or ""),
            ]
            text = "\n".join(part for part in text_parts if part.strip()).strip()
            if not text:
                return

            embedding = EmbeddingService().generate_embedding(text)
            vector_db.add_entity(
                entity_key=entity["key"],
                text=text,
                embedding=embedding,
                metadata={
                    "case_id": case_id,
                    "entity_type": entity.get("type"),
                    "name": entity.get("name"),
                },
            )
        except Exception as e:
            logger.warning("Failed to rebuild entity embedding for %s: %s", entity.get("key"), e)

    def get_node_details(self, key: str, case_id: str = None) -> Optional[Dict]:
        """
        Get detailed information about a single node.

        Args:
            key: The node key
            case_id: REQUIRED - Filter to only include nodes/relationships belonging to this case

        Returns:
            Node details dict or None, including parsed verified_facts and ai_insights
        """
        with driver.session() as session:
            # case_id is always required - always filter by it
            params = {"key": key, "case_id": case_id}

            result = session.run(
                """
                MATCH (n {key: $key})
                OPTIONAL MATCH (n)-[r]-(connected)
                WHERE connected.case_id = $case_id
                RETURN
                    n.id AS id,
                    n.key AS key,
                    n.name AS name,
                    labels(n)[0] AS type,
                    n.summary AS summary,
                    n.notes AS notes,
                    n.verified_facts AS verified_facts,
                    n.ai_insights AS ai_insights,
                    properties(n) AS properties,
                    collect(DISTINCT {
                        key: connected.key,
                        name: connected.name,
                        type: labels(connected)[0],
                        relationship: type(r),
                        direction: CASE WHEN startNode(r) = n THEN 'outgoing' ELSE 'incoming' END
                    }) AS connections
                """,
                **params,
            )
            record = result.single()
            if record:
                # Parse JSON fields for verified_facts and ai_insights
                verified_facts = parse_json_field(record["verified_facts"])
                ai_insights = parse_json_field(record["ai_insights"])

                return {
                    "id": record["id"],
                    "key": record["key"],
                    "name": record["name"],
                    "type": record["type"],
                    "summary": record["summary"],
                    "notes": record["notes"],
                    "verified_facts": verified_facts,
                    "ai_insights": ai_insights,
                    "properties": record["properties"],
                    "connections": [c for c in record["connections"] if c["key"]],
                }
        return None

    # -------------------------------------------------------------------------
    # Fact and Insight Management
    # -------------------------------------------------------------------------

    def pin_fact(self, node_key: str, fact_index: int, pinned: bool, case_id: str = None) -> Dict:
        """
        Toggle the pinned status of a verified fact.

        Args:
            node_key: The node's key
            fact_index: Index of the fact in the verified_facts array
            pinned: True to pin, False to unpin
            case_id: REQUIRED - Verify node belongs to this case

        Returns:
            Updated verified_facts array
        """
        with driver.session() as session:
            # Get current verified_facts - verify node belongs to case
            result = session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                RETURN n.verified_facts AS verified_facts
                """,
                key=node_key,
                case_id=case_id,
            )
            record = result.single()
            if not record:
                raise ValueError(f"Node not found: {node_key} in case {case_id}")

            verified_facts = parse_json_field(record["verified_facts"]) or []

            if fact_index < 0 or fact_index >= len(verified_facts):
                raise ValueError(f"Invalid fact index: {fact_index}")

            # Update the pinned status
            verified_facts[fact_index]["pinned"] = pinned

            # Save back to Neo4j
            session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                SET n.verified_facts = $verified_facts
                """,
                key=node_key,
                case_id=case_id,
                verified_facts=json.dumps(verified_facts),
            )

            return verified_facts

    def verify_insight(
        self,
        node_key: str,
        insight_index: int,
        username: str,
        source_doc: Optional[str] = None,
        page: Optional[int] = None,
        case_id: str = None
    ) -> Dict:
        """
        Convert an AI insight to a verified fact with user attribution.

        Args:
            node_key: The node's key
            insight_index: Index of the insight in the ai_insights array
            username: Username of the verifying investigator
            source_doc: Optional source document for the verification
            page: Optional page number in the source document
            case_id: REQUIRED - Verify node belongs to this case

        Returns:
            Dict with updated verified_facts and ai_insights arrays
        """
        from datetime import datetime

        with driver.session() as session:
            # Get current facts and insights - verify node belongs to case
            result = session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                RETURN n.verified_facts AS verified_facts, n.ai_insights AS ai_insights
                """,
                key=node_key,
                case_id=case_id,
            )
            record = result.single()
            if not record:
                raise ValueError(f"Node not found: {node_key} in case {case_id}")

            verified_facts = parse_json_field(record["verified_facts"]) or []
            ai_insights = parse_json_field(record["ai_insights"]) or []

            if insight_index < 0 or insight_index >= len(ai_insights):
                raise ValueError(f"Invalid insight index: {insight_index}")

            # Get the insight to convert
            insight = ai_insights[insight_index]

            # Create a new verified fact from the insight
            new_fact = {
                "text": insight.get("text", ""),
                "quote": None,  # No direct quote since it was an inference
                "page": page,
                "source_doc": source_doc,
                "importance": 3,  # Default to medium importance for user-verified insights
                "pinned": False,
                "verified_by": username,
                "verified_at": datetime.utcnow().isoformat(),
                "original_confidence": insight.get("confidence"),
                "original_reasoning": insight.get("reasoning"),
            }

            # Add to verified facts
            verified_facts.append(new_fact)

            # Remove from ai_insights
            ai_insights.pop(insight_index)

            # Save back to Neo4j - verify node belongs to case
            session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                SET n.verified_facts = $verified_facts, n.ai_insights = $ai_insights
                """,
                key=node_key,
                case_id=case_id,
                verified_facts=json.dumps(verified_facts),
                ai_insights=json.dumps(ai_insights),
            )

            return {
                "verified_facts": verified_facts,
                "ai_insights": ai_insights,
            }

    def find_similar_entities(
        self,
        case_id: str,
        entity_types: Optional[List[str]] = None,
        name_similarity_threshold: float = 0.88,
        max_results: int = 50,
    ) -> List[Dict]:
        """
        Find entities that might be duplicates based on name similarity and type.

        Args:
            case_id: The case ID to filter by
            entity_types: Optional list of entity types to filter by
            name_similarity_threshold: Minimum similarity score (0-1) for name matching
            max_results: Maximum number of pairs to return

        Returns:
            List of dicts with 'entity1' and 'entity2' entries, each containing node info
        """
        from difflib import SequenceMatcher

        with driver.session() as session:
            # Build type filter
            type_filter = ""
            params = {"case_id": case_id}
            if entity_types:
                type_filter = "AND labels(n)[0] IN $types"
                params["types"] = entity_types

            # Get all entities (excluding Documents) for this case
            query = f"""
                MATCH (n)
                WHERE n.key IS NOT NULL
                  AND n.name IS NOT NULL
                  AND NOT n:Document
                  AND NONE(label IN labels(n) WHERE label IN ['RecycleBin', 'RecycleBinItem'])
                  AND coalesce(properties(n)['system_node'], false) <> true
                  AND n.case_id = $case_id
                  {type_filter}
                RETURN
                    n.key AS key,
                    n.id AS id,
                    n.name AS name,
                    labels(n)[0] AS type,
                    n.summary AS summary,
                    n.notes AS notes,
                    n.verified_facts AS verified_facts,
                    n.ai_insights AS ai_insights,
                    properties(n) AS properties
                ORDER BY n.name
            """

            result = session.run(query, **params)
            entities = [dict(record) for record in result]

            # Compare entities pairwise
            similar_pairs = []
            for i, e1 in enumerate(entities):
                for e2 in entities[i+1:]:
                    # Same type required
                    if e1["type"] != e2["type"]:
                        continue

                    # Calculate name similarity
                    name1 = (e1["name"] or "").lower().strip()
                    name2 = (e2["name"] or "").lower().strip()

                    if not name1 or not name2:
                        continue

                    similarity = SequenceMatcher(None, name1, name2).ratio()

                    if similarity >= name_similarity_threshold:
                        similar_pairs.append({
                            "entity1": {
                                "key": e1["key"],
                                "id": e1["id"],
                                "name": e1["name"],
                                "type": e1["type"],
                                "summary": e1["summary"],
                                "notes": e1["notes"],
                                "verified_facts": parse_json_field(e1.get("verified_facts")),
                                "ai_insights": parse_json_field(e1.get("ai_insights")),
                                "properties": e1["properties"] or {},
                            },
                            "entity2": {
                                "key": e2["key"],
                                "id": e2["id"],
                                "name": e2["name"],
                                "type": e2["type"],
                                "summary": e2["summary"],
                                "notes": e2["notes"],
                                "verified_facts": parse_json_field(e2.get("verified_facts")),
                                "ai_insights": parse_json_field(e2.get("ai_insights")),
                                "properties": e2["properties"] or {},
                            },
                            "similarity": similarity,
                        })

            # Sort by similarity (highest first) and limit results
            similar_pairs.sort(key=lambda x: x["similarity"], reverse=True)
            return similar_pairs[:max_results]

    async def find_similar_entities_streaming(
        self,
        case_id: str,
        entity_types: Optional[List[str]] = None,
        name_similarity_threshold: float = 0.88,
        max_results: int = 1000,
        rejected_pairs: Optional[Set[Tuple[str, str]]] = None,
    ):
        """
        Async generator that yields similar entity pairs with progress updates.

        Yields SSE events for streaming progress to the client.

        Args:
            case_id: The case ID to filter by
            entity_types: Optional list of entity types to filter by
            name_similarity_threshold: Minimum similarity score (0-1) for name matching
            max_results: Maximum number of pairs to return
            rejected_pairs: Set of (key1, key2) tuples to skip (already normalized/sorted)

        Yields:
            dict: SSE event data with 'event' type and 'data' payload
        """
        import asyncio
        from difflib import SequenceMatcher
        from collections import defaultdict

        # Initialize rejected_pairs to empty set if None
        if rejected_pairs is None:
            rejected_pairs = set()

        # Fetch data and close session immediately - we don't need the session
        # held open during comparison loop, which can cause hanging issues
        with driver.session() as session:
            # Build type filter
            type_filter = ""
            params = {"case_id": case_id}
            if entity_types:
                type_filter = "AND labels(n)[0] IN $types"
                params["types"] = entity_types

            # Get all entities (excluding Documents) for this case
            query = f"""
                MATCH (n)
                WHERE n.key IS NOT NULL
                  AND n.name IS NOT NULL
                  AND NOT n:Document
                  AND NONE(label IN labels(n) WHERE label IN ['RecycleBin', 'RecycleBinItem'])
                  AND coalesce(properties(n)['system_node'], false) <> true
                  AND n.case_id = $case_id
                  {type_filter}
                RETURN
                    n.key AS key,
                    n.id AS id,
                    n.name AS name,
                    labels(n)[0] AS type,
                    n.summary AS summary,
                    n.notes AS notes,
                    n.verified_facts AS verified_facts,
                    n.ai_insights AS ai_insights,
                    properties(n) AS properties
                ORDER BY labels(n)[0], n.name
            """

            result = session.run(query, **params)
            all_entities = [dict(record) for record in result]
        # Session is now closed - all data fetched

        # Group entities by type (backend already only compares same-type entities)
        entities_by_type = defaultdict(list)
        for entity in all_entities:
            entities_by_type[entity["type"]].append(entity)

        entity_types_list = sorted(entities_by_type.keys())

        # Calculate total comparisons needed (for progress)
        total_comparisons = 0
        for entities in entities_by_type.values():
            n = len(entities)
            # n*(n-1)/2 pairs for same-type comparison
            total_comparisons += n * (n - 1) // 2

        # Yield start event
        yield {
            "event": "start",
            "data": {
                "total_entities": len(all_entities),
                "entity_types": entity_types_list,
                "total_types": len(entity_types_list),
                "total_comparisons": total_comparisons,
            }
        }
        await asyncio.sleep(0)  # Yield control for cancellation check

        similar_pairs = []
        comparisons_done = 0
        pairs_found = 0
        last_progress_update = 0

        for type_index, type_name in enumerate(entity_types_list):
            entities = entities_by_type[type_name]
            n = len(entities)
            type_comparisons = n * (n - 1) // 2

            # Yield type_start event
            yield {
                "event": "type_start",
                "data": {
                    "type_name": type_name,
                    "type_count": len(entities),
                    "type_index": type_index,
                    "total_types": len(entity_types_list),
                    "total_comparisons": type_comparisons,
                }
            }
            await asyncio.sleep(0)

            type_pairs_found = 0

            # Compare entities within this type
            for i, e1 in enumerate(entities):
                for e2 in entities[i+1:]:
                    comparisons_done += 1

                    # Calculate name similarity
                    name1 = (e1["name"] or "").lower().strip()
                    name2 = (e2["name"] or "").lower().strip()

                    if not name1 or not name2:
                        continue

                    # Skip rejected pairs (normalize keys for lookup)
                    key1, key2 = e1["key"], e2["key"]
                    normalized_pair = (key1, key2) if key1 <= key2 else (key2, key1)
                    if normalized_pair in rejected_pairs:
                        continue

                    similarity = SequenceMatcher(None, name1, name2).ratio()

                    if similarity >= name_similarity_threshold:
                        pair = {
                            "entity1": {
                                "key": e1["key"],
                                "id": e1["id"],
                                "name": e1["name"],
                                "type": e1["type"],
                                "summary": e1["summary"],
                                "notes": e1["notes"],
                                "verified_facts": parse_json_field(e1.get("verified_facts")),
                                "ai_insights": parse_json_field(e1.get("ai_insights")),
                                "properties": e1["properties"] or {},
                            },
                            "entity2": {
                                "key": e2["key"],
                                "id": e2["id"],
                                "name": e2["name"],
                                "type": e2["type"],
                                "summary": e2["summary"],
                                "notes": e2["notes"],
                                "verified_facts": parse_json_field(e2.get("verified_facts")),
                                "ai_insights": parse_json_field(e2.get("ai_insights")),
                                "properties": e2["properties"] or {},
                            },
                            "similarity": similarity,
                        }
                        similar_pairs.append(pair)
                        pairs_found += 1
                        type_pairs_found += 1

                        # NOTE: Removed individual "result" event emission to prevent
                        # UI freezing with large numbers of pairs (93k+ causes 93k React updates).
                        # Results are now only sent in the "complete" event at the end.

                    # Emit progress every ~100 comparisons
                    if comparisons_done - last_progress_update >= 100:
                        yield {
                            "event": "progress",
                            "data": {
                                "comparisons_done": comparisons_done,
                                "total_comparisons": total_comparisons,
                                "pairs_found": pairs_found,
                                "current_type": type_name,
                                "type_index": type_index,
                            }
                        }
                        last_progress_update = comparisons_done
                        await asyncio.sleep(0)  # Yield control for cancellation check

            # Yield type_complete event
            yield {
                "event": "type_complete",
                "data": {
                    "type_name": type_name,
                    "pairs_found": type_pairs_found,
                    "type_index": type_index,
                }
            }
            await asyncio.sleep(0)

        # Emit final progress update if not already at 100%
        # This ensures the UI shows 100% before the complete event
        if comparisons_done != last_progress_update:
            yield {
                "event": "progress",
                "data": {
                    "comparisons_done": comparisons_done,
                    "total_comparisons": total_comparisons,
                    "pairs_found": pairs_found,
                    "current_type": "Finalizing...",
                    "type_index": len(entity_types_list) - 1,
                }
            }
            await asyncio.sleep(0)

        # Sort final results by similarity
        similar_pairs.sort(key=lambda x: x["similarity"], reverse=True)

        # Yield complete event
        yield {
            "event": "complete",
            "data": {
                "total_pairs": len(similar_pairs),
                "total_comparisons": comparisons_done,
                "limited_results": similar_pairs[:max_results] if len(similar_pairs) > max_results else similar_pairs,
            }
        }
        await asyncio.sleep(0)  # Ensure event is flushed before generator ends

    # NOTE: merge_entities logic has been moved to the evidence engine.
    # Entity merging is now handled as an AI-powered job via
    # POST /api/graph/merge-entities → evidence engine merge pipeline.


    def delete_node(self, node_key: str, case_id: str = None) -> Dict[str, Any]:
        """
        Delete a node and all its relationships.

        Args:
            node_key: Key of the node to delete
            case_id: REQUIRED - Verify node belongs to this case

        Returns:
            Dict with success status and deleted node info
        """
        with driver.session() as session:
            # First get node info before deletion for return value - verify node belongs to case
            node_result = session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                RETURN
                    n.key AS key,
                    n.name AS name,
                    labels(n)[0] AS type,
                    id(n) AS neo4j_id
                """,
                key=node_key,
                case_id=case_id,
            )
            node_record = node_result.single()

            if not node_record:
                raise ValueError(f"Node not found: {node_key} in case {case_id}")

            # Count relationships before deletion
            rel_count_result = session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})-[r]-()
                RETURN count(r) AS count
                """,
                key=node_key,
                case_id=case_id,
            )
            rel_count = rel_count_result.single()["count"]

            # Delete the node and all its relationships - verify node belongs to case
            session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                DETACH DELETE n
                """,
                key=node_key,
                case_id=case_id,
            )

            return {
                "success": True,
                "deleted_node": {
                    "key": node_record["key"],
                    "name": node_record["name"],
                    "type": node_record["type"],
                },
                "relationships_deleted": rel_count,
            }

    # -------------------------------------------------------------------------
    # Recycling Bin (Soft Delete)
    # -------------------------------------------------------------------------

    def restore_recycled_entity(self, recycle_key: str, case_id: str) -> Dict[str, Any]:
        """
        Restore an entity from the recycling bin back into the graph.

        Args:
            recycle_key: Key of the RecycleBin node
            case_id: Case ID for scoping

        Returns:
            Dict with restored entity info
        """
        import json as json_mod

        with driver.session() as session:
            # 1. Get the recycle bin record
            rb_result = session.run(
                """
                MATCH (rb {key: $key, case_id: $case_id})
                WHERE 'RecycleBin' IN labels(rb)
                RETURN rb.entity_data AS entity_data, rb.original_key AS original_key,
                       rb.original_name AS original_name
                """,
                key=recycle_key,
                case_id=case_id,
            )
            rb_record = rb_result.single()
            if not rb_record:
                raise ValueError(f"Recycled entity not found: {recycle_key}")

            entity_data = json_mod.loads(rb_record["entity_data"])

            # 2. Check that original key doesn't already exist
            existing = session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                RETURN count(n) AS cnt
                """,
                key=entity_data["key"],
                case_id=case_id,
            )
            if existing.single()["cnt"] > 0:
                raise ValueError(
                    f"Entity with key '{entity_data['key']}' already exists in the graph. "
                    "Cannot restore — resolve the conflict first."
                )

            # 3. Recreate entity node with stored properties
            props = entity_data.get("properties", {})
            label = entity_data["labels"][0] if entity_data.get("labels") else "Entity"

            # Build safe property SET
            safe_props = {}
            for k, v in props.items():
                if v is not None and isinstance(v, (str, int, float, bool)):
                    safe_props[k] = v

            session.run(
                f"""
                CREATE (n:`{label}`)
                SET n = $props
                """,
                props=safe_props,
            )

            # 4. Restore relationships where the other node still exists
            restored_rels = 0
            for rel in entity_data.get("relationships", []):
                other_key = rel.get("other_key")
                rel_type = rel.get("rel_type")
                direction = rel.get("direction")
                rel_props = rel.get("rel_props", {})

                if not other_key or not rel_type:
                    continue

                # Check if the other node still exists
                exists_check = session.run(
                    "MATCH (n {key: $key}) RETURN count(n) AS cnt",
                    key=other_key,
                )
                if exists_check.single()["cnt"] == 0:
                    continue

                # Filter rel props
                safe_rel_props = {}
                for k, v in (rel_props or {}).items():
                    if v is not None and isinstance(v, (str, int, float, bool)):
                        safe_rel_props[k] = v

                if direction == "outgoing":
                    if safe_rel_props:
                        session.run(
                            f"""
                            MATCH (a {{key: $a_key}}), (b {{key: $b_key}})
                            CREATE (a)-[r:`{rel_type}`]->(b)
                            SET r = $props
                            """,
                            a_key=entity_data["key"],
                            b_key=other_key,
                            props=safe_rel_props,
                        )
                    else:
                        session.run(
                            f"""
                            MATCH (a {{key: $a_key}}), (b {{key: $b_key}})
                            CREATE (a)-[r:`{rel_type}`]->(b)
                            """,
                            a_key=entity_data["key"],
                            b_key=other_key,
                        )
                else:
                    if safe_rel_props:
                        session.run(
                            f"""
                            MATCH (a {{key: $a_key}}), (b {{key: $b_key}})
                            CREATE (a)-[r:`{rel_type}`]->(b)
                            SET r = $props
                            """,
                            a_key=other_key,
                            b_key=entity_data["key"],
                            props=safe_rel_props,
                        )
                    else:
                        session.run(
                            f"""
                            MATCH (a {{key: $a_key}}), (b {{key: $b_key}})
                            CREATE (a)-[r:`{rel_type}`]->(b)
                            """,
                            a_key=other_key,
                            b_key=entity_data["key"],
                        )
                restored_rels += 1

            # 5. Delete recycle bin record
            session.run(
                """
                MATCH (rb {key: $key, case_id: $case_id})
                WHERE 'RecycleBin' IN labels(rb)
                DELETE rb
                """,
                key=recycle_key,
                case_id=case_id,
            )

            return {
                "success": True,
                "restored_entity": {
                    "key": entity_data["key"],
                    "name": entity_data.get("name", ""),
                    "type": label,
                },
                "relationships_restored": restored_rels,
            }

    def permanently_delete_recycled(self, recycle_key: str, case_id: str) -> Dict[str, Any]:
        """
        Permanently delete a recycled entity (remove from recycle bin).

        Args:
            recycle_key: Key of the RecycleBin node
            case_id: Case ID for scoping

        Returns:
            Dict with deletion info
        """
        with driver.session() as session:
            result = session.run(
                """
                MATCH (rb {key: $key, case_id: $case_id})
                WHERE 'RecycleBin' IN labels(rb)
                RETURN rb.original_name AS name, rb.original_key AS original_key
                """,
                key=recycle_key,
                case_id=case_id,
            )
            record = result.single()
            if not record:
                raise ValueError(f"Recycled entity not found: {recycle_key}")

            session.run(
                """
                MATCH (rb {key: $key, case_id: $case_id})
                WHERE 'RecycleBin' IN labels(rb)
                DELETE rb
                """,
                key=recycle_key,
                case_id=case_id,
            )

            return {
                "success": True,
                "permanently_deleted": {
                    "recycle_key": recycle_key,
                    "original_key": record["original_key"],
                    "name": record["name"],
                },
            }

    def soft_delete_entity(
        self,
        node_key: str,
        case_id: str,
        deleted_by: str,
        reason: str = "manual_delete",
        db: Session = None,
    ) -> Dict[str, Any]:
        """Archive an entity in Postgres, then remove it from the active Neo4j graph."""
        if db is None:
            raise ValueError("db session is required for recycle-bin operations")

        deleted_at = datetime.now(timezone.utc)
        case_uuid = self._case_uuid(case_id)

        with driver.session() as session:
            entity_result = session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                WHERE NONE(label IN labels(n) WHERE label IN ['Document', 'Case', 'RecycleBin', 'RecycleBinItem'])
                  AND coalesce(properties(n)['system_node'], false) <> true
                RETURN n.key AS key, n.name AS name, labels(n) AS labels,
                       properties(n) AS props
                """,
                key=node_key,
                case_id=case_id,
            )
            entity_record = entity_result.single()
            if not entity_record:
                logger.info(
                    "Entity %s already deleted from case %s; treating as success",
                    node_key, case_id,
                )
                return {
                    "success": True,
                    "already_deleted": True,
                    "recycled_entity": {"key": node_key, "name": None, "type": None},
                    "recycle_key": None,
                    "relationships_stored": 0,
                    "reason": reason,
                }

            labels = [label for label in list(entity_record["labels"] or []) if label not in self.INTERNAL_LABELS]
            if not labels:
                raise ValueError(f"Entity {node_key} has no restorable labels")

            rels_result = session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})-[r]-(other {case_id: $case_id})
                WHERE coalesce(properties(other)['system_node'], false) <> true
                  AND NONE(label IN labels(other) WHERE label IN ['RecycleBin', 'RecycleBinItem'])
                  AND r.case_id = $case_id
                RETURN type(r) AS rel_type, properties(r) AS rel_props,
                       other.key AS other_key, other.name AS other_name,
                       labels(other)[0] AS other_type,
                       CASE WHEN startNode(r) = n THEN 'outgoing' ELSE 'incoming' END AS direction
                """,
                key=node_key,
                case_id=case_id,
            )
            relationships = [self._json_safe(dict(r)) for r in rels_result]

        entity_props = self._json_safe(dict(entity_record["props"] or {}))
        recycle_key = self._recycle_key(node_key)
        snapshot = {
            "schema_version": 1,
            "case_id": case_id,
            "original_key": entity_record["key"],
            "labels": labels,
            "properties": entity_props,
            "relationships": relationships,
            "deleted_at": deleted_at.isoformat(),
            "deleted_by": deleted_by,
            "reason": reason,
        }

        item = GraphRecycleBinItem(
            case_id=case_uuid,
            recycle_key=recycle_key,
            item_type="entity_delete",
            original_key=node_key,
            original_name=entity_record["name"],
            original_type=labels[0],
            reason=reason,
            deleted_by=deleted_by,
            deleted_at=deleted_at,
            relationship_count=len(relationships),
            status="pending_delete",
            snapshot=snapshot,
        )
        db.add(item)
        db.commit()
        db.refresh(item)

        try:
            with driver.session() as session:
                def delete_work(tx):
                    result = tx.run(
                        """
                        MATCH (n {key: $key, case_id: $case_id})
                        WHERE NONE(label IN labels(n) WHERE label IN ['Document', 'Case', 'RecycleBin', 'RecycleBinItem'])
                          AND coalesce(properties(n)['system_node'], false) <> true
                        WITH n
                        DETACH DELETE n
                        RETURN count(*) AS deleted_count
                        """,
                        key=node_key,
                        case_id=case_id,
                    )
                    return result.single()["deleted_count"]

                deleted_count = session.execute_write(delete_work)
                if deleted_count == 0:
                    raise ValueError(f"Entity not found during delete: {node_key} in case {case_id}")
        except Exception:
            db.refresh(item)
            item.status = "pending_delete"
            db.commit()
            raise

        item.status = "active"
        db.commit()
        self._delete_entity_embedding(node_key)

        return {
            "success": True,
            "recycled_entity": {
                "key": item.original_key,
                "name": item.original_name,
                "type": item.original_type,
            },
            "recycle_key": item.recycle_key,
            "relationships_stored": item.relationship_count,
            "reason": item.reason,
        }

    def list_recycled_entities(self, case_id: str, db: Session = None) -> List[Dict[str, Any]]:
        """List active recycled entities for a case."""
        if db is None:
            raise ValueError("db session is required for recycle-bin operations")

        rows = (
            db.query(GraphRecycleBinItem)
            .filter(
                GraphRecycleBinItem.case_id == self._case_uuid(case_id),
                GraphRecycleBinItem.status == "active",
            )
            .order_by(GraphRecycleBinItem.deleted_at.desc())
            .all()
        )
        return [
            {
                "key": row.recycle_key,
                "item_type": row.item_type,
                "original_key": row.original_key,
                "original_name": row.original_name,
                "type": row.original_type,
                "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
                "deleted_by": row.deleted_by,
                "reason": row.reason,
                "relationship_count": row.relationship_count,
                "title": row.original_name,
                "target_key": (row.snapshot or {}).get("target_key") if row.item_type == "merge_undo" else None,
                "target_name": (row.snapshot or {}).get("target_name_before") if row.item_type == "merge_undo" else None,
                "source_names": (row.snapshot or {}).get("source_names") if row.item_type == "merge_undo" else None,
                "source_count": len((row.snapshot or {}).get("source_keys") or []) if row.item_type == "merge_undo" else None,
                "merged_name": (row.snapshot or {}).get("merged_name_at_merge") if row.item_type == "merge_undo" else None,
            }
            for row in rows
        ]

    def restore_recycled_entity(
        self,
        recycle_key: str,
        case_id: str,
        db: Session = None,
        restored_by: str = None,
    ) -> Dict[str, Any]:
        """Restore an entity from the Postgres recycle bin into Neo4j."""
        if db is None:
            raise ValueError("db session is required for recycle-bin operations")

        item = (
            db.query(GraphRecycleBinItem)
            .filter(
                GraphRecycleBinItem.recycle_key == recycle_key,
                GraphRecycleBinItem.case_id == self._case_uuid(case_id),
                GraphRecycleBinItem.item_type == "entity_delete",
                GraphRecycleBinItem.status == "active",
            )
            .with_for_update()
            .one_or_none()
        )
        if not item:
            raise ValueError(f"Recycled entity not found: {recycle_key}")

        item.status = "restoring"
        db.commit()
        snapshot = item.snapshot or {}
        original_key = snapshot.get("original_key") or item.original_key
        labels = [self._escape_cypher_identifier(label) for label in (snapshot.get("labels") or [item.original_type or "Entity"])]
        labels = [label for label in labels if label not in self.INTERNAL_LABELS] or ["Entity"]
        label_clause = "".join(f":`{label}`" for label in labels)

        props = {}
        for key, value in (snapshot.get("properties") or {}).items():
            prop_value = self._neo4j_property_value(value)
            if prop_value is not None:
                props[key] = prop_value
        props["key"] = original_key
        props["case_id"] = case_id

        restored_rels = 0
        try:
            with driver.session() as session:
                def restore_work(tx):
                    existing = tx.run(
                        """
                        MATCH (n {key: $key, case_id: $case_id})
                        WHERE NONE(label IN labels(n) WHERE label IN ['RecycleBin', 'RecycleBinItem'])
                          AND coalesce(properties(n)['system_node'], false) <> true
                        RETURN count(n) AS cnt
                        """,
                        key=original_key,
                        case_id=case_id,
                    ).single()["cnt"]
                    if existing > 0:
                        raise ValueError(
                            f"Entity with key '{original_key}' already exists in the graph. "
                            "Cannot restore - resolve the conflict first."
                        )

                    tx.run(
                        f"""
                        CREATE (n{label_clause})
                        SET n = $props
                        """,
                        props=props,
                    )

                    count = 0
                    for rel in snapshot.get("relationships") or []:
                        other_key = rel.get("other_key")
                        raw_rel_type = rel.get("rel_type")
                        direction = rel.get("direction")
                        if not other_key or not raw_rel_type:
                            continue
                        rel_type = self._escape_cypher_identifier(raw_rel_type)

                        rel_props = {}
                        for prop_key, prop_value in (rel.get("rel_props") or {}).items():
                            restored_value = self._neo4j_property_value(prop_value)
                            if restored_value is not None:
                                rel_props[prop_key] = restored_value
                        rel_props["case_id"] = case_id

                        if direction == "outgoing":
                            result = tx.run(
                                f"""
                                MATCH (a {{key: $a_key, case_id: $case_id}})
                                MATCH (b {{key: $b_key, case_id: $case_id}})
                                WHERE NONE(label IN labels(b) WHERE label IN ['RecycleBin', 'RecycleBinItem'])
                                  AND coalesce(properties(b)['system_node'], false) <> true
                                MERGE (a)-[r:`{rel_type}`]->(b)
                                SET r += $props
                                RETURN count(r) AS cnt
                                """,
                                a_key=original_key,
                                b_key=other_key,
                                case_id=case_id,
                                props=rel_props,
                            )
                        else:
                            result = tx.run(
                                f"""
                                MATCH (a {{key: $a_key, case_id: $case_id}})
                                MATCH (b {{key: $b_key, case_id: $case_id}})
                                WHERE NONE(label IN labels(a) WHERE label IN ['RecycleBin', 'RecycleBinItem'])
                                  AND coalesce(properties(a)['system_node'], false) <> true
                                MERGE (a)-[r:`{rel_type}`]->(b)
                                SET r += $props
                                RETURN count(r) AS cnt
                                """,
                                a_key=other_key,
                                b_key=original_key,
                                case_id=case_id,
                                props=rel_props,
                            )
                        count += result.single()["cnt"]
                    return count

                restored_rels = session.execute_write(restore_work)
        except Exception:
            db.refresh(item)
            item.status = "active"
            db.commit()
            raise

        item.status = "restored"
        db.commit()

        restored_entity = {
            "key": original_key,
            "name": props.get("name") or item.original_name or "",
            "type": labels[0],
            "properties": props,
        }
        self._rebuild_entity_embedding(restored_entity, case_id)

        return {
            "success": True,
            "restored_entity": {
                "key": restored_entity["key"],
                "name": restored_entity["name"],
                "type": restored_entity["type"],
            },
            "relationships_restored": restored_rels,
        }

    def permanently_delete_recycled(
        self,
        recycle_key: str,
        case_id: str,
        db: Session = None,
        purged_by: str = None,
    ) -> Dict[str, Any]:
        """Permanently purge an active recycle-bin item."""
        if db is None:
            raise ValueError("db session is required for recycle-bin operations")

        item = (
            db.query(GraphRecycleBinItem)
            .filter(
                GraphRecycleBinItem.recycle_key == recycle_key,
                GraphRecycleBinItem.case_id == self._case_uuid(case_id),
                GraphRecycleBinItem.status == "active",
            )
            .one_or_none()
        )
        if not item:
            raise ValueError(f"Recycled entity not found: {recycle_key}")

        original_key = item.original_key
        original_name = item.original_name
        item.status = "purged"
        item.snapshot = None
        db.commit()

        return {
            "success": True,
            "permanently_deleted": {
                "recycle_key": recycle_key,
                "original_key": original_key,
                "name": original_name,
            },
        }

    def get_case_entity_summary(self, case_id: str) -> list:
        """Get a structured summary of all key entities in a case."""
        with driver.session() as session:
            query = """
                MATCH (n {case_id: $case_id})
                WHERE (n:Person OR n:Company OR n:Organisation OR n:Bank OR n:BankAccount)
                  AND n.name IS NOT NULL
                  AND NONE(label IN labels(n) WHERE label IN ['RecycleBin', 'RecycleBinItem'])
                  AND coalesce(properties(n)['system_node'], false) <> true
                RETURN n.key AS key, n.name AS name, labels(n)[0] AS type,
                       n.summary AS summary,
                       n.verified_facts AS verified_facts,
                       n.ai_insights AS ai_insights
                ORDER BY labels(n)[0], n.name
            """
            result = session.run(query, case_id=case_id)
            entities = []
            for record in result:
                vf = record["verified_facts"]
                ai = record["ai_insights"]
                if isinstance(vf, str):
                    try:
                        import json
                        vf = json.loads(vf)
                    except Exception:
                        vf = []
                if isinstance(ai, str):
                    try:
                        import json
                        ai = json.loads(ai)
                    except Exception:
                        ai = []
                entities.append({
                    "key": record["key"],
                    "name": record["name"],
                    "type": record["type"],
                    "summary": record["summary"],
                    "facts_count": len(vf) if isinstance(vf, list) else 0,
                    "insights_count": len(ai) if isinstance(ai, list) else 0,
                })
            return entities

    def batch_update_entities(self, updates: list, case_id: str) -> int:
        """Batch update properties on multiple entity nodes.

        Args:
            updates: List of dicts with {key, property, value}
            case_id: Case ID for security validation
        Returns:
            Number of successfully updated entities
        """
        allowed_properties = {"name", "summary", "notes", "type", "description"}
        with driver.session() as session:
            count = 0
            for update in updates[:500]:
                prop = update.get("property")
                if prop not in allowed_properties:
                    continue
                result = session.run(
                    f"MATCH (n {{key: $key, case_id: $case_id}}) SET n.`{prop}` = $value RETURN n.key AS key",
                    key=update["key"],
                    case_id=case_id,
                    value=update["value"],
                )
                if result.single():
                    count += 1
            return count

    def get_entities_for_insights(self, case_id: str, max_entities: int = 10) -> list:
        """Get top entities with verified facts for insight generation."""
        with driver.session() as session:
            result = session.run(
                """
                MATCH (n {case_id: $case_id})
                WHERE (n:Person OR n:Company OR n:Organisation OR n:Bank OR n:BankAccount)
                  AND n.name IS NOT NULL
                  AND n.verified_facts IS NOT NULL
                  AND NONE(label IN labels(n) WHERE label IN ['RecycleBin', 'RecycleBinItem'])
                  AND coalesce(properties(n)['system_node'], false) <> true
                OPTIONAL MATCH (n)-[r]-(related)
                WHERE NOT related:Document
                  AND NONE(label IN labels(related) WHERE label IN ['RecycleBin', 'RecycleBinItem'])
                  AND coalesce(properties(related)['system_node'], false) <> true
                  AND related.case_id = $case_id
                WITH n, collect(DISTINCT {
                    name: related.name,
                    type: labels(related)[0],
                    relationship: type(r)
                })[..15] AS related_entities
                RETURN n.key AS key, n.name AS name, labels(n)[0] AS type,
                       n.summary AS summary, n.verified_facts AS verified_facts,
                       n.ai_insights AS ai_insights, related_entities
                ORDER BY size(COALESCE(n.verified_facts, '[]')) DESC
                LIMIT $max_entities
                """,
                case_id=case_id, max_entities=max_entities,
            )
            entities = []
            for record in result:
                entities.append({
                    "key": record["key"],
                    "name": record["name"],
                    "type": record["type"],
                    "summary": record["summary"],
                    "verified_facts": parse_json_field(record["verified_facts"]) or [],
                    "ai_insights": parse_json_field(record["ai_insights"]) or [],
                    "related_entities": [r for r in record["related_entities"] if r.get("name")],
                })
            return entities

    def save_entity_insights(self, node_key: str, case_id: str, new_insights: list) -> Dict:
        """Append new insights to an entity's ai_insights array."""
        with driver.session() as session:
            result = session.run(
                "MATCH (n {key: $key, case_id: $case_id}) RETURN n.ai_insights AS ai_insights",
                key=node_key, case_id=case_id,
            )
            record = result.single()
            if not record:
                raise ValueError(f"Node not found: {node_key}")
            existing = parse_json_field(record["ai_insights"]) or []
            existing.extend(new_insights)
            session.run(
                "MATCH (n {key: $key, case_id: $case_id}) SET n.ai_insights = $insights",
                key=node_key, case_id=case_id, insights=json.dumps(existing),
            )
            return {"success": True, "total_insights": len(existing)}

    def reject_entity_insight(self, node_key: str, case_id: str, insight_index: int) -> Dict:
        """Remove an insight from the ai_insights array."""
        with driver.session() as session:
            result = session.run(
                "MATCH (n {key: $key, case_id: $case_id}) RETURN n.ai_insights AS ai_insights",
                key=node_key, case_id=case_id,
            )
            record = result.single()
            if not record:
                raise ValueError(f"Node not found: {node_key}")
            insights = parse_json_field(record["ai_insights"]) or []
            if insight_index < 0 or insight_index >= len(insights):
                raise ValueError(f"Invalid insight index: {insight_index}")
            removed = insights.pop(insight_index)
            session.run(
                "MATCH (n {key: $key, case_id: $case_id}) SET n.ai_insights = $insights",
                key=node_key, case_id=case_id, insights=json.dumps(insights),
            )
            return {"success": True, "removed": removed, "remaining": len(insights)}

    def get_all_pending_insights(self, case_id: str) -> list:
        """Get all pending insights across all entities in a case."""
        with driver.session() as session:
            result = session.run(
                """
                MATCH (n {case_id: $case_id})
                WHERE n.ai_insights IS NOT NULL AND n.name IS NOT NULL
                  AND NONE(label IN labels(n) WHERE label IN ['RecycleBin', 'RecycleBinItem'])
                  AND coalesce(properties(n)['system_node'], false) <> true
                RETURN n.key AS key, n.name AS name, labels(n)[0] AS type,
                       n.ai_insights AS ai_insights
                ORDER BY n.name
                """,
                case_id=case_id,
            )
            all_insights = []
            for record in result:
                insights = parse_json_field(record["ai_insights"]) or []
                for idx, insight in enumerate(insights):
                    if isinstance(insight, dict) and insight.get("status", "pending") == "pending":
                        all_insights.append({
                            "entity_key": record["key"],
                            "entity_name": record["name"],
                            "entity_type": record["type"],
                            "insight_index": idx,
                            **insight,
                        })
            return all_insights


entity_service = EntityService()
