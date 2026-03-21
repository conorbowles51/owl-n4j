"""
Entity Service — CRUD operations on entity nodes, fact/insight management,
similarity detection, merge, soft-delete / recycle-bin, and batch helpers.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from services.neo4j.driver import driver, parse_json_field

logger = logging.getLogger(__name__)


class EntityService:

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

    def merge_entities(
        self,
        source_key: str,
        target_key: str,
        merged_data: Dict[str, Any],
        case_id: str = None,
    ) -> Dict[str, Any]:
        """
        Merge two entities into one.

        Args:
            source_key: Key of the source entity (will be deleted)
            target_key: Key of the target entity (will be kept and updated)
            merged_data: Dict with merged properties:
                - name: Merged name
                - summary: Merged summary (can be None to keep existing)
                - notes: Merged notes (can be None to keep existing)
                - type: Merged type (label)
                - properties: Dict of additional properties to set
            case_id: REQUIRED - Verify both entities belong to this case

        Returns:
            Dict with result info including merged_node and relationships_updated count
        """
        import re

        # Validate merged_data
        if merged_data is None:
            raise ValueError("merged_data cannot be None")
        if not isinstance(merged_data, dict):
            raise ValueError(f"merged_data must be a dict, got {type(merged_data)}")

        with driver.session() as session:
            # Get both entities - verify they belong to the case
            source_result = session.run(
                """
                MATCH (s {key: $key, case_id: $case_id})
                RETURN
                    id(s) AS neo4j_id,
                    s.id AS id,
                    s.key AS key,
                    s.name AS name,
                    labels(s)[0] AS type,
                    s.summary AS summary,
                    s.notes AS notes,
                    properties(s) AS properties
                """,
                key=source_key,
                case_id=case_id,
            )
            source_record = source_result.single()
            if not source_record:
                raise ValueError(f"Source entity not found: {source_key} in case {case_id}")

            target_result = session.run(
                """
                MATCH (t {key: $key, case_id: $case_id})
                RETURN
                    id(t) AS neo4j_id,
                    t.id AS id,
                    t.key AS key,
                    t.name AS name,
                    labels(t)[0] AS type,
                    t.summary AS summary,
                    t.notes AS notes,
                    properties(t) AS properties
                """,
                key=target_key,
                case_id=case_id,
            )
            target_record = target_result.single()
            if not target_record:
                raise ValueError(f"Target entity not found: {target_key} in case {case_id}")

            # Get all relationships from source
            source_rels_result = session.run(
                """
                MATCH (s {key: $key})-[r]->(target)
                RETURN
                    type(r) AS rel_type,
                    target.key AS other_key,
                    properties(r) AS rel_properties,
                    'outgoing' AS direction
                UNION
                MATCH (source)-[r]->(s {key: $key})
                RETURN
                    type(r) AS rel_type,
                    source.key AS other_key,
                    properties(r) AS rel_properties,
                    'incoming' AS direction
                """,
                key=source_key,
            )
            source_rels = [dict(record) for record in source_rels_result]

            # Update target entity with merged data
            # Build SET clause for properties
            set_clauses = []
            params = {"target_key": target_key}

            if "name" in merged_data:
                set_clauses.append("t.name = $merged_name")
                params["merged_name"] = merged_data["name"]

            if "summary" in merged_data and merged_data["summary"] is not None:
                set_clauses.append("t.summary = $merged_summary")
                params["merged_summary"] = merged_data["summary"]

            if "verified_facts" in merged_data and merged_data["verified_facts"] is not None:
                set_clauses.append("t.verified_facts = $merged_verified_facts")
                params["merged_verified_facts"] = json.dumps(merged_data["verified_facts"])

            if "ai_insights" in merged_data and merged_data["ai_insights"] is not None:
                set_clauses.append("t.ai_insights = $merged_ai_insights")
                params["merged_ai_insights"] = json.dumps(merged_data["ai_insights"])

            # Handle type (label) change if needed
            new_type = merged_data.get("type")
            if new_type and isinstance(new_type, str) and new_type.strip():
                # Remove old label and add new one
                old_type = target_record["type"]
                if old_type != new_type:
                    # Sanitize type for Cypher label
                    sanitized_new_type = re.sub(r'[^a-zA-Z0-9_]', '_', new_type.strip())
                    sanitized_new_type = re.sub(r'_+', '_', sanitized_new_type).strip('_')
                    if not sanitized_new_type:
                        sanitized_new_type = "Other"

                    session.run(
                        f"""
                        MATCH (t {{key: $target_key}})
                        REMOVE t:`{old_type}`
                        SET t:`{sanitized_new_type}`
                        """,
                        target_key=target_key,
                    )

            # Add additional properties
            if "properties" in merged_data and merged_data["properties"] is not None:
                properties = merged_data["properties"]
                if isinstance(properties, dict):
                    for prop_key, prop_val in properties.items():
                        param_name = f"prop_{prop_key}"
                        set_clauses.append(f"t.{prop_key} = ${param_name}")
                        params[param_name] = prop_val

            # Update target entity
            if set_clauses:
                set_clause = ", ".join(set_clauses)
                session.run(
                    f"""
                    MATCH (t {{key: $target_key}})
                    SET {set_clause}
                    """,
                    **params,
                )

            # Migrate relationships from source to target
            relationships_updated = 0
            for rel in source_rels:
                rel_type = rel["rel_type"]
                rel_props = rel["rel_properties"] or {}
                direction = rel["direction"]
                other_key = rel["other_key"]  # Use the unified column name from UNION

                # Don't create self-loops
                if other_key == target_key:
                    continue

                if direction == "outgoing":
                    # Create relationship from target to other
                    if rel_props:
                        session.run(
                            f"""
                            MATCH (t {{key: $target_key}}), (o {{key: $other_key}})
                            MERGE (t)-[r:`{rel_type}`]->(o)
                            SET r += $rel_props
                            """,
                            target_key=target_key,
                            other_key=other_key,
                            rel_props=rel_props,
                        )
                    else:
                        session.run(
                            f"""
                            MATCH (t {{key: $target_key}}), (o {{key: $other_key}})
                            MERGE (t)-[r:`{rel_type}`]->(o)
                            """,
                            target_key=target_key,
                            other_key=other_key,
                        )
                    relationships_updated += 1
                else:  # incoming
                    # Create relationship from other to target
                    if rel_props:
                        session.run(
                            f"""
                            MATCH (o {{key: $other_key}}), (t {{key: $target_key}})
                            MERGE (o)-[r:`{rel_type}`]->(t)
                            SET r += $rel_props
                            """,
                            target_key=target_key,
                            other_key=other_key,
                            rel_props=rel_props,
                        )
                    else:
                        session.run(
                            f"""
                            MATCH (o {{key: $other_key}}), (t {{key: $target_key}})
                            MERGE (o)-[r:`{rel_type}`]->(t)
                            """,
                            target_key=target_key,
                            other_key=other_key,
                        )
                    relationships_updated += 1

            # Soft-delete source entity to recycling bin (so it can be recovered)
            try:
                self.soft_delete_entity(
                    node_key=source_key,
                    case_id=case_id,
                    deleted_by="system",
                    reason=f"merge_into:{target_key}",
                )
            except Exception:
                # Fallback: hard-delete if soft-delete fails (e.g., entity already gone)
                session.run(
                    """
                    MATCH (s {key: $key})
                    DETACH DELETE s
                    """,
                    key=source_key,
                )

            # Get the merged node (target node after merge) for return value
            merged_node_result = session.run(
                """
                MATCH (t {key: $key})
                RETURN
                    t.id AS id,
                    t.key AS key,
                    t.name AS name,
                    labels(t)[0] AS type
                """,
                key=target_key,
            )
            merged_node_record = merged_node_result.single()
            merged_node = dict(merged_node_record) if merged_node_record else None

            # Return result
            return {
                "merged_node": merged_node,
                "relationships_updated": relationships_updated,
            }

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

    def soft_delete_entity(
        self, node_key: str, case_id: str, deleted_by: str, reason: str = "manual_delete"
    ) -> Dict[str, Any]:
        """
        Soft-delete an entity by moving it to the recycling bin.
        Stores full entity state (properties + relationships) as JSON on the node,
        then removes it from the active graph.

        Args:
            node_key: Key of the entity to soft-delete
            case_id: Case ID for scoping
            deleted_by: Username of who performed the deletion
            reason: Reason for deletion (e.g., 'manual_delete', 'merge_discard', 'file_delete')

        Returns:
            Dict with recycled entity info
        """
        import json as json_mod
        from datetime import datetime as dt

        with driver.session() as session:
            # 1. Fetch full entity properties
            entity_result = session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                WHERE NOT n:Document
                RETURN n.key AS key, n.name AS name, labels(n) AS labels,
                       properties(n) AS props, id(n) AS neo4j_id
                """,
                key=node_key,
                case_id=case_id,
            )
            entity_record = entity_result.single()
            if not entity_record:
                raise ValueError(f"Entity not found: {node_key} in case {case_id}")

            # 2. Fetch all relationships
            rels_result = session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})-[r]-(other)
                RETURN type(r) AS rel_type, properties(r) AS rel_props,
                       other.key AS other_key, other.name AS other_name,
                       labels(other)[0] AS other_type,
                       CASE WHEN startNode(r) = n THEN 'outgoing' ELSE 'incoming' END AS direction
                """,
                key=node_key,
                case_id=case_id,
            )
            relationships = [dict(r) for r in rels_result]

            # 3. Build the recycling bin record
            entity_props = dict(entity_record["props"])
            recycle_record = {
                "key": entity_record["key"],
                "name": entity_record["name"],
                "labels": list(entity_record["labels"]),
                "properties": entity_props,
                "relationships": relationships,
                "deleted_at": dt.now().isoformat(),
                "deleted_by": deleted_by,
                "reason": reason,
                "case_id": case_id,
            }

            # 4. Store in RecycleBin node
            session.run(
                """
                CREATE (rb:RecycleBin {
                    key: $key,
                    original_key: $original_key,
                    original_name: $original_name,
                    case_id: $case_id,
                    deleted_at: $deleted_at,
                    deleted_by: $deleted_by,
                    reason: $reason,
                    entity_data: $entity_data
                })
                """,
                key=f"recycled_{node_key}_{dt.now().strftime('%Y%m%d%H%M%S')}",
                original_key=node_key,
                original_name=entity_record["name"],
                case_id=case_id,
                deleted_at=recycle_record["deleted_at"],
                deleted_by=deleted_by,
                reason=reason,
                entity_data=json_mod.dumps(recycle_record, default=str),
            )

            # 5. Delete the original entity from graph
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
                "recycled_entity": {
                    "key": entity_record["key"],
                    "name": entity_record["name"],
                    "type": entity_record["labels"][0] if entity_record["labels"] else "Unknown",
                },
                "relationships_stored": len(relationships),
                "reason": reason,
            }

    def list_recycled_entities(self, case_id: str) -> List[Dict[str, Any]]:
        """
        List all entities in the recycling bin for a case.

        Returns:
            List of recycled entity summaries.
        """
        with driver.session() as session:
            result = session.run(
                """
                MATCH (rb:RecycleBin {case_id: $case_id})
                RETURN rb.key AS key, rb.original_key AS original_key,
                       rb.original_name AS original_name,
                       rb.deleted_at AS deleted_at,
                       rb.deleted_by AS deleted_by,
                       rb.reason AS reason
                ORDER BY rb.deleted_at DESC
                """,
                case_id=case_id,
            )
            return [dict(r) for r in result]

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
                MATCH (rb:RecycleBin {key: $key, case_id: $case_id})
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
                MATCH (rb:RecycleBin {key: $key, case_id: $case_id})
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
                MATCH (rb:RecycleBin {key: $key, case_id: $case_id})
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
                MATCH (rb:RecycleBin {key: $key, case_id: $case_id})
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

    def get_case_entity_summary(self, case_id: str) -> list:
        """Get a structured summary of all key entities in a case."""
        with driver.session() as session:
            query = """
                MATCH (n {case_id: $case_id})
                WHERE (n:Person OR n:Company OR n:Organisation OR n:Bank OR n:BankAccount)
                  AND n.name IS NOT NULL
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
                OPTIONAL MATCH (n)-[r]-(related)
                WHERE NOT related:Document AND related.case_id = $case_id
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
