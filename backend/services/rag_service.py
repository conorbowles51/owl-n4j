"""
RAG Service - orchestrates context retrieval and AI question answering.

Handles:
- Hybrid retrieval: chunk search + entity search + graph traversal
- Cypher query generation and execution for structural questions
- Question classification (semantic vs structural vs hybrid)
- Re-ranking of retrieved results
- Answer synthesis with citation support
"""

import json
import time
from typing import Dict, List, Optional, Any

from services.neo4j_service import neo4j_service
from services.llm_service import llm_service
from config import (
    VECTOR_SEARCH_ENABLED, VECTOR_SEARCH_TOP_K, VECTOR_SEARCH_CONFIDENCE_THRESHOLD,
    HYBRID_FILTERING_ENABLED,
    CHUNK_SEARCH_ENABLED, CHUNK_SEARCH_TOP_K,
    ENTITY_SEARCH_ENABLED, ENTITY_SEARCH_TOP_K, GRAPH_TRAVERSAL_DEPTH,
    QUESTION_CLASSIFICATION_ENABLED,
    RERANK_ENABLED, RERANK_METHOD, RERANK_TOP_CHUNKS, RERANK_TOP_ENTITIES, CONTEXT_TOKEN_BUDGET,
    EMBEDDING_PROVIDER, EMBEDDING_MODEL,
)
from utils.prompt_trace import log_section

# Try to import vector DB services (optional)
try:
    from services.vector_db_service import vector_db_service
    from services.embedding_service import embedding_service
    VECTOR_DB_AVAILABLE = embedding_service is not None and VECTOR_SEARCH_ENABLED
except (ImportError, ValueError, AttributeError):
    VECTOR_DB_AVAILABLE = False
    vector_db_service = None
    embedding_service = None


class RAGService:
    """Service for RAG-based question answering over the graph."""

    def __init__(self):
        self.neo4j = neo4j_service
        self.llm = llm_service

    # =====================
    # Schema & Context Builders (preserved from original)
    # =====================

    def _build_schema_info(self, graph_summary: Dict) -> str:
        """Build schema description for Cypher generation."""
        entity_types = list(graph_summary.get("entity_types", {}).keys())
        rel_types = list(graph_summary.get("relationship_types", {}).keys())

        # Build list of available entities with their keys
        entities_by_type = {}
        for entity in graph_summary.get("entities", []):
            etype = entity.get("type", "Unknown")
            if etype not in entities_by_type:
                entities_by_type[etype] = []
            entities_by_type[etype].append({
                "name": entity.get("name"),
                "key": entity.get("key")
            })

        # Format entities list
        entities_list = []
        for etype, entities in entities_by_type.items():
            entities_list.append(f"\n{etype}:")
            for e in entities[:30]:  # Limit per type to avoid token explosion
                entities_list.append(f"  - name: '{e['name']}', key: '{e['key']}'")
            if len(entities) > 30:
                entities_list.append(f"  ... and {len(entities) - 30} more")

        entities_str = "\n".join(entities_list)
        rel_types_str = ", ".join(rel_types) if rel_types else "None"

        return f"""=== GRAPH SCHEMA ===

ENTITY TYPES: {', '.join(entity_types)}

RELATIONSHIP TYPES (use ONLY these exact types): {rel_types_str}

ENTITY PROPERTIES: key, name, summary, notes
RELATIONSHIP PROPERTIES: (relationships have no custom properties, only use type())

=== AVAILABLE ENTITIES ===
{entities_str}

=== RULES ===
1. Use ONLY the relationship types listed above - do not invent types like PAYMENT, TRANSACTION, etc.
2. Use ONLY the exact 'key' values from the entities list
3. For relationship info, use type(r) to get the relationship type name
4. Entity properties are: key, name, summary, notes (no 'type' property - use labels(n)[0] instead)

=== EXAMPLE QUERIES ===
- Find a person: MATCH (p:Person {{key: 'john-smith'}}) RETURN p.name, p.summary
- Find connections: MATCH (a {{key: 'some-key'}})-[r]-(b) RETURN a.name, type(r), b.name
- Find specific relationship: MATCH (a)-[r:TRANSFERRED_TO]->(b) RETURN a.name, b.name
- Get entity type: MATCH (n {{key: 'some-key'}}) RETURN n.name, labels(n)[0] AS type
"""

    def _build_full_context(self, graph_summary: Dict, max_entities: int = 200) -> str:
        """Build context string from full graph summary."""
        lines = [
            "=== INVESTIGATION GRAPH OVERVIEW ===",
            f"Total Entities: {graph_summary.get('total_nodes', 0)}",
            f"Total Relationships: {graph_summary.get('total_relationships', 0)}",
            "",
            "Entity Types:",
        ]

        for etype, count in graph_summary.get("entity_types", {}).items():
            lines.append(f"  - {etype}: {count}")

        lines.append("")
        lines.append("Relationship Types:")
        for rtype, count in graph_summary.get("relationship_types", {}).items():
            lines.append(f"  - {rtype}: {count}")

        lines.append("")
        lines.append("=== ENTITIES ===")

        entities = graph_summary.get("entities", [])
        total_entities = len(entities)

        if total_entities > max_entities:
            lines.append(f"Showing {max_entities} of {total_entities} entities (most relevant):")
            entities_with_content = [e for e in entities if e.get("summary") or e.get("notes")]
            entities_without_content = [e for e in entities if not (e.get("summary") or e.get("notes"))]
            entities_with_content.sort(key=lambda e: len(e.get("summary", "") + e.get("notes", "")), reverse=True)
            entities_to_show = entities_with_content[:max_entities]
            if len(entities_to_show) < max_entities:
                remaining = max_entities - len(entities_to_show)
                entities_to_show.extend(entities_without_content[:remaining])
            entities = entities_to_show
        else:
            entities.sort(key=lambda e: len(e.get("summary", "") + e.get("notes", "")), reverse=True)
            entities = entities[:max_entities]

        for entity in entities:
            lines.append(f"\n[{entity['type']}] {entity['name']} (key: {entity['key']})")
            if entity.get("summary"):
                summary = entity["summary"]
                if len(summary) > 1000:
                    summary = summary[:1000] + "..."
                lines.append(f"  Summary: {summary}")
            if entity.get("notes"):
                notes = entity["notes"]
                if len(notes) > 800:
                    notes = notes[:800] + "..."
                lines.append(f"  Notes: {notes}")

        if total_entities > max_entities:
            lines.append(f"\n... and {total_entities - max_entities} more entities")

        return "\n".join(lines)

    def _build_focused_context(self, node_context: Dict) -> str:
        """Build context string from selected nodes."""
        lines = [
            "=== SELECTED ENTITIES AND CONNECTIONS ===",
        ]

        for entity in node_context.get("selected_entities", []):
            lines.append(f"\n[{entity['type']}] {entity['name']} (key: {entity['key']})")

            if entity.get("summary"):
                lines.append(f"  Summary: {entity['summary']}")

            if entity.get("notes"):
                notes = entity["notes"]
                if len(notes) > 500:
                    notes = notes[:500] + "..."
                lines.append(f"  Notes: {notes}")

            if entity.get("connections"):
                lines.append("  Connections:")
                for conn in entity["connections"]:
                    direction = "\u2192" if conn["direction"] == "outgoing" else "\u2190"
                    lines.append(
                        f"    {direction} [{conn['relationship']}] {conn['name']} ({conn['type']})"
                    )
                    if conn.get("summary"):
                        lines.append(f"       Summary: {conn['summary'][:200]}")

        return "\n".join(lines)

    def _format_document_summary(self, doc_results: List[Dict]) -> str:
        """Format a summary of document search results for display in the answer."""
        if not doc_results:
            return ""

        lines = [
            "**\U0001f4c4 Relevant Documents Found:**",
            ""
        ]

        for i, doc in enumerate(doc_results, 1):
            metadata = doc.get("metadata", {})
            filename = metadata.get("filename", metadata.get("doc_name", doc.get("id", "Unknown")))
            distance = doc.get("distance")

            relevance_score = (1 - distance) * 100 if distance is not None else None

            line = f"{i}. **{filename}**"
            if relevance_score is not None:
                line += f" (Relevance: {relevance_score:.1f}%)"
            lines.append(line)

        lines.append("")
        lines.append("These sources were analyzed to answer your question.")
        lines.append("")

        return "\n".join(lines)

    # =====================
    # Neo4j Helpers (preserved from original)
    # =====================

    def _get_document_nodes_from_neo4j(self, doc_ids: List[str]) -> List[Dict]:
        """Get Document nodes from Neo4j by vector_db_id."""
        if not doc_ids:
            return []

        try:
            cypher = """
            MATCH (d:Document)
            WHERE d.vector_db_id IN $doc_ids
            RETURN
                id(d) AS neo4j_id,
                d.id AS id,
                d.key AS key,
                d.name AS name,
                labels(d)[0] AS type,
                d.summary AS summary,
                d.notes AS notes,
                properties(d) AS properties
            """
            results = self.neo4j.run_cypher(cypher, params={"doc_ids": doc_ids})

            nodes = []
            for record in results:
                props = record.get("properties") or {}
                node = {
                    "neo4j_id": record.get("neo4j_id"),
                    "id": record.get("id") or record.get("key"),
                    "key": record.get("key"),
                    "name": record.get("name") or record.get("key"),
                    "type": record.get("type") or "Document",
                    "summary": record.get("summary"),
                    "notes": record.get("notes"),
                    "properties": props,
                }
                nodes.append(node)

            return nodes
        except Exception as e:
            print(f"[RAG] Error getting document nodes: {e}")
            return []

    def _get_entity_nodes_from_neo4j(self, entity_keys: List[str]) -> List[Dict]:
        """Get entity nodes from Neo4j by keys."""
        if not entity_keys:
            return []

        try:
            with self.neo4j._driver.session() as session:
                query = """
                MATCH (n)
                WHERE n.key IN $keys AND NOT n:Document
                RETURN
                    id(n) AS neo4j_id,
                    n.id AS id,
                    n.key AS key,
                    n.name AS name,
                    labels(n)[0] AS type,
                    n.summary AS summary,
                    n.notes AS notes,
                    properties(n) AS properties
                """
                results = session.run(query, keys=entity_keys)

                nodes = []
                from services.neo4j_service import parse_json_field
                for record in results:
                    props = record.get("properties") or {}
                    node = {
                        "neo4j_id": record.get("neo4j_id"),
                        "id": record.get("id") or record.get("key"),
                        "key": record.get("key"),
                        "name": record.get("name") or record.get("key"),
                        "type": record.get("type"),
                        "summary": record.get("summary"),
                        "notes": record.get("notes"),
                        "verified_facts": parse_json_field(props.get("verified_facts")),
                        "ai_insights": parse_json_field(props.get("ai_insights")),
                        "properties": props,
                    }
                    nodes.append(node)

                return nodes
        except Exception as e:
            print(f"[RAG] Error getting entity nodes: {e}")
            return []

    def _get_relationships_between_nodes(self, node_keys: List[str]) -> List[Dict]:
        """Get relationships between given nodes."""
        if not node_keys or len(node_keys) < 2:
            return []

        try:
            with self.neo4j._driver.session() as session:
                query = """
                MATCH (a)-[r]->(b)
                WHERE a.key IN $keys AND b.key IN $keys
                RETURN
                    a.key AS source,
                    b.key AS target,
                    type(r) AS type,
                    properties(r) AS properties
                """
                results = session.run(query, keys=node_keys)

                links = []
                for record in results:
                    link = {
                        "source": record["source"],
                        "target": record["target"],
                        "type": record["type"],
                        "properties": record.get("properties") or {},
                    }
                    links.append(link)

                return links
        except Exception as e:
            print(f"[RAG] Error getting relationships: {e}")
            return []

    # =====================
    # Cypher Query (preserved from original)
    # =====================

    def _try_cypher_query(
        self,
        question: str,
        graph_summary: Dict,
        debug_log: Optional[Dict] = None,
    ) -> Optional[str]:
        """
        Try to generate and execute a Cypher query for specific questions.
        Returns query results as formatted string, or None if not applicable.
        """
        schema_info = self._build_schema_info(graph_summary)
        cypher = self.llm.generate_cypher(question, schema_info)
        print("Cypher: ", cypher)
        if not cypher:
            return None

        try:
            cypher_upper = cypher.upper()
            if any(
                dangerous in cypher_upper
                for dangerous in ["DELETE", "REMOVE", "SET", "CREATE", "MERGE", "DROP"]
            ):
                print(f"Blocked potentially dangerous query: {cypher}")
                return None

            if debug_log is not None:
                debug_log["cypher_answer_query"] = {
                    "generated_cypher": cypher,
                }

            results = self.neo4j.run_cypher(cypher)

            if not results:
                if debug_log is not None:
                    debug_log["cypher_answer_query"]["results"] = "No results"
                return None

            lines = [f"Query executed: {cypher}", "", "Results:"]
            for i, row in enumerate(results[:20]):
                lines.append(f"  {i + 1}. {row}")

            if len(results) > 20:
                lines.append(f"  ... and {len(results) - 20} more results")

            if debug_log is not None:
                debug_log["cypher_answer_query"]["results"] = {
                    "rows_returned": len(results),
                    "sample_results": results[:10],
                }

            return "\n".join(lines)

        except Exception as e:
            print(f"Cypher execution error: {e}")
            return None

    # =====================
    # NEW: Hybrid Retrieval Helpers
    # =====================

    def _retrieve_chunks(
        self,
        question: str,
        case_id: Optional[str] = None,
        confidence_threshold: Optional[float] = None,
        debug_log: Optional[Dict] = None,
    ) -> List[Dict]:
        """
        Retrieve relevant text chunks via vector search.
        Falls back to document-level search if chunks collection is empty.

        Returns:
            List of result dicts with: id, text, metadata, distance
        """
        if not VECTOR_DB_AVAILABLE:
            if debug_log is not None:
                debug_log["chunk_search"] = {"enabled": False, "reason": "Vector DB not available"}
            return []

        try:
            query_embedding = embedding_service.generate_embedding(question)
            vector_filter = {"case_id": case_id} if case_id else None
            threshold = confidence_threshold if confidence_threshold is not None else VECTOR_SEARCH_CONFIDENCE_THRESHOLD

            # Try chunk-level search first
            chunk_count = vector_db_service.count_chunks()
            if CHUNK_SEARCH_ENABLED and chunk_count > 0:
                all_results = vector_db_service.search_chunks(
                    query_embedding=query_embedding,
                    top_k=CHUNK_SEARCH_TOP_K,
                    filter_metadata=vector_filter,
                )
                # Fallback: if case_id filter yielded nothing but chunks exist, retry without filter
                if not all_results and case_id and chunk_count > 0:
                    all_results = vector_db_service.search_chunks(
                        query_embedding=query_embedding,
                        top_k=CHUNK_SEARCH_TOP_K,
                    )
                source = "chunks"
            else:
                # Fallback to document-level search
                all_results = vector_db_service.search(
                    query_embedding=query_embedding,
                    top_k=VECTOR_SEARCH_TOP_K,
                    filter_metadata=vector_filter,
                )
                # Fallback without filter
                if not all_results and case_id:
                    all_results = vector_db_service.search(
                        query_embedding=query_embedding,
                        top_k=VECTOR_SEARCH_TOP_K,
                    )
                source = "documents"

            # Apply confidence threshold
            filtered = []
            for r in all_results:
                distance = r.get("distance")
                if distance is not None and distance <= threshold:
                    filtered.append(r)
                elif distance is None:
                    filtered.append(r)

            print(f"[RAG] Chunk search ({source}): {len(all_results)} total, {len(filtered)} after threshold ({threshold})")

            if debug_log is not None:
                debug_log["chunk_search"] = {
                    "enabled": True,
                    "source": source,
                    "chunks_in_db": chunk_count,
                    "top_k": CHUNK_SEARCH_TOP_K if source == "chunks" else VECTOR_SEARCH_TOP_K,
                    "confidence_threshold": threshold,
                    "total_results": len(all_results),
                    "filtered_results": len(filtered),
                    "results": [
                        {
                            "id": r["id"],
                            "doc_name": r.get("metadata", {}).get("doc_name", r.get("metadata", {}).get("filename", "Unknown")),
                            "distance": r.get("distance"),
                            "text_preview": r.get("text", "")[:200] + "..." if len(r.get("text", "")) > 200 else r.get("text", ""),
                        }
                        for r in filtered[:10]
                    ],
                }

            return filtered

        except Exception as e:
            print(f"[RAG] Chunk search error: {e}")
            import traceback
            traceback.print_exc()
            if debug_log is not None:
                debug_log["chunk_search"] = {"enabled": True, "error": str(e)}
            return []

    def _retrieve_entities(
        self,
        question: str,
        case_id: Optional[str] = None,
        top_k: Optional[int] = None,
        debug_log: Optional[Dict] = None,
    ) -> List[Dict]:
        """
        Retrieve relevant entities via vector search, then enrich from Neo4j.

        Returns:
            List of entity dicts from Neo4j with verified_facts, ai_insights, and distance scores.
        """
        if not VECTOR_DB_AVAILABLE or not ENTITY_SEARCH_ENABLED:
            if debug_log is not None:
                debug_log["entity_search"] = {"enabled": False, "reason": "Disabled or unavailable"}
            return []

        top_k = top_k or ENTITY_SEARCH_TOP_K

        try:
            query_embedding = embedding_service.generate_embedding(question)
            vector_filter = {"case_id": case_id} if case_id else None

            entity_results = vector_db_service.search_entities(
                query_embedding=query_embedding,
                top_k=top_k,
                filter_metadata=vector_filter,
            )

            # Fallback for old data without case_id metadata
            if not entity_results and case_id:
                entity_results = vector_db_service.search_entities(
                    query_embedding=query_embedding,
                    top_k=top_k,
                )

            # Get full entity details from Neo4j (including verified_facts, connections)
            entity_keys = [r["id"] for r in entity_results if r.get("id")]
            if not entity_keys:
                if debug_log is not None:
                    debug_log["entity_search"] = {"enabled": True, "vector_results": 0, "enriched_entities": 0}
                return []

            enriched_entities = self._get_entity_nodes_from_neo4j(entity_keys)

            # Attach distance scores from vector search
            distance_map = {r["id"]: r.get("distance", 1.0) for r in entity_results}
            for entity in enriched_entities:
                entity["distance"] = distance_map.get(entity.get("key"), 1.0)

            print(f"[RAG] Entity search: {len(entity_results)} vector matches, {len(enriched_entities)} enriched from Neo4j")

            if debug_log is not None:
                debug_log["entity_search"] = {
                    "enabled": True,
                    "vector_results": len(entity_results),
                    "enriched_entities": len(enriched_entities),
                    "entity_keys": [e.get("key") for e in enriched_entities[:20]],
                }

            return enriched_entities

        except Exception as e:
            print(f"[RAG] Entity search error: {e}")
            import traceback
            traceback.print_exc()
            if debug_log is not None:
                debug_log["entity_search"] = {"enabled": True, "error": str(e)}
            return []

    def _traverse_graph(
        self,
        entity_keys: List[str],
        case_id: Optional[str] = None,
        debug_log: Optional[Dict] = None,
    ) -> Dict:
        """
        Traverse the graph from matched entities to pull connected context.
        Uses existing neo4j_service.get_context_for_nodes() for 1-hop neighbors.

        Returns:
            Dict with 'selected_entities' list (same format as get_context_for_nodes)
        """
        if not entity_keys or not case_id:
            return {"selected_entities": []}

        try:
            context = self.neo4j.get_context_for_nodes(entity_keys, case_id)

            if debug_log is not None:
                debug_log["graph_traversal"] = {
                    "input_keys": entity_keys[:20],
                    "depth": GRAPH_TRAVERSAL_DEPTH,
                    "entities_returned": len(context.get("selected_entities", [])),
                }

            print(f"[RAG] Graph traversal: {len(entity_keys)} input keys -> {len(context.get('selected_entities', []))} entities with connections")
            return context

        except Exception as e:
            print(f"[RAG] Graph traversal error: {e}")
            if debug_log is not None:
                debug_log["graph_traversal"] = {"error": str(e)}
            return {"selected_entities": []}

    # =====================
    # NEW: Hybrid Context Builder
    # =====================

    def _build_hybrid_context(
        self,
        chunk_results: List[Dict],
        entity_results: List[Dict],
        graph_context: Dict,
        cypher_context: Optional[str] = None,
    ) -> str:
        """
        Build a structured context string with multiple sections:
        - RELEVANT TEXT PASSAGES (from chunk/document search)
        - RELEVANT ENTITIES (from entity vector search with verified facts)
        - GRAPH CONNECTIONS (from graph traversal)
        - GRAPH QUERY RESULTS (from Cypher, if applicable)
        """
        sections = []

        # Section 1: Relevant Text Passages
        if chunk_results:
            lines = ["=== RELEVANT TEXT PASSAGES ===", ""]
            for i, chunk in enumerate(chunk_results, 1):
                metadata = chunk.get("metadata", {})
                doc_name = metadata.get("doc_name", metadata.get("filename", "Unknown"))
                page_start = metadata.get("page_start")
                page_end = metadata.get("page_end")
                page_info = ""
                if page_start and page_start != -1 and page_start != "-1":
                    page_start = int(page_start) if isinstance(page_start, str) else page_start
                    if page_end and page_end != -1 and page_end != "-1":
                        page_end = int(page_end) if isinstance(page_end, str) else page_end
                        if page_end != page_start:
                            page_info = f" (pages {page_start}-{page_end})"
                        else:
                            page_info = f" (page {page_start})"
                    else:
                        page_info = f" (page {page_start})"
                distance = chunk.get("distance")
                lines.append(f"--- Passage {i}: {doc_name}{page_info} ---")
                if distance is not None:
                    lines.append(f"Relevance: {1 - distance:.4f}")
                lines.append(chunk.get("text", ""))
                lines.append("")
            sections.append("\n".join(lines))

        # Section 2: Relevant Entities (with verified facts for citations)
        if entity_results:
            lines = ["=== RELEVANT ENTITIES ===", ""]
            for entity in entity_results:
                name = entity.get("name", "Unknown")
                etype = entity.get("type", "Unknown")
                lines.append(f"[{etype}] {name} (key: {entity.get('key', '')})")
                if entity.get("summary"):
                    lines.append(f"  Summary: {entity['summary']}")

                # Include verified facts with citations
                verified_facts = entity.get("verified_facts")
                if verified_facts:
                    lines.append("  Verified Facts:")
                    for fact in verified_facts[:10]:  # Limit to top 10 facts per entity
                        fact_text = fact.get("text", "")
                        source = fact.get("source_doc", "")
                        quote = fact.get("quote", "")
                        page = fact.get("page", "")
                        citation = []
                        if source:
                            citation.append(source)
                        if page:
                            citation.append(f"p.{page}")
                        citation_str = f" [{', '.join(citation)}]" if citation else ""
                        lines.append(f"    - {fact_text}{citation_str}")
                        if quote:
                            lines.append(f'      Quote: "{quote}"')

                # Include AI insights
                ai_insights = entity.get("ai_insights")
                if ai_insights:
                    lines.append("  AI Insights:")
                    for insight in ai_insights[:5]:
                        insight_text = insight.get("text", "")
                        confidence = insight.get("confidence", "")
                        conf_str = f" (confidence: {confidence})" if confidence else ""
                        lines.append(f"    - {insight_text}{conf_str}")

                lines.append("")
            sections.append("\n".join(lines))

        # Section 3: Graph Connections
        graph_entities = graph_context.get("selected_entities", [])
        if graph_entities:
            lines = ["=== GRAPH CONNECTIONS ===", ""]
            for entity in graph_entities:
                connections = entity.get("connections", [])
                if connections:
                    lines.append(f"[{entity.get('type', '?')}] {entity.get('name', '?')}:")
                    for conn in connections[:15]:
                        direction = "->" if conn.get("direction") == "outgoing" else "<-"
                        lines.append(
                            f"  {direction} [{conn.get('relationship', '?')}] "
                            f"{conn.get('name', '?')} ({conn.get('type', '?')})"
                        )
                        if conn.get("summary"):
                            lines.append(f"     Summary: {conn['summary'][:200]}")
                    lines.append("")
            sections.append("\n".join(lines))

        # Section 4: Cypher Query Results (if available)
        if cypher_context:
            sections.append(f"=== GRAPH QUERY RESULTS ===\n\n{cypher_context}")

        if not sections:
            return "No relevant context found."

        return "\n\n".join(sections)

    # =====================
    # NEW: Re-ranking
    # =====================

    def _rerank_results(
        self,
        question: str,
        chunk_results: List[Dict],
        entity_results: List[Dict],
        debug_log: Optional[Dict] = None,
    ) -> tuple:
        """
        Re-rank and filter retrieval results before sending to LLM.

        Returns:
            Tuple of (filtered_chunks, filtered_entities)
        """
        if not RERANK_ENABLED:
            return chunk_results, entity_results

        if RERANK_METHOD == "llm":
            return self._rerank_by_llm(
                question, chunk_results, entity_results,
                RERANK_TOP_CHUNKS, RERANK_TOP_ENTITIES, debug_log,
            )
        else:
            # Default: score-based (fast, no LLM call)
            return self._rerank_by_score(
                chunk_results, entity_results,
                RERANK_TOP_CHUNKS, RERANK_TOP_ENTITIES, CONTEXT_TOKEN_BUDGET,
                debug_log,
            )

    def _rerank_by_score(
        self,
        chunk_results: List[Dict],
        entity_results: List[Dict],
        top_chunks: int,
        top_entities: int,
        token_budget: int,
        debug_log: Optional[Dict] = None,
    ) -> tuple:
        """Fast re-ranking: sort by distance, apply top-k and token budget."""
        # Sort chunks by distance (ascending = more relevant)
        sorted_chunks = sorted(
            chunk_results,
            key=lambda r: r.get("distance", float("inf"))
        )[:top_chunks]

        # Sort entities by distance
        sorted_entities = sorted(
            entity_results,
            key=lambda r: r.get("distance", float("inf"))
        )[:top_entities]

        # Apply token budget (approximate 1 token ~ 4 chars)
        total_chars = 0
        budget_chunks = []
        for chunk in sorted_chunks:
            chunk_len = len(chunk.get("text", ""))
            if total_chars + chunk_len > token_budget:
                break
            budget_chunks.append(chunk)
            total_chars += chunk_len

        # Entities are smaller, include within remaining budget (with 20% overflow allowance)
        budget_entities = []
        for entity in sorted_entities:
            entity_len = len(str(entity.get("summary", ""))) + len(str(entity.get("verified_facts", "")))
            if total_chars + entity_len > token_budget * 1.2:
                break
            budget_entities.append(entity)
            total_chars += entity_len

        if debug_log is not None:
            debug_log["rerank"] = {
                "method": "score",
                "input_chunks": len(chunk_results),
                "input_entities": len(entity_results),
                "output_chunks": len(budget_chunks),
                "output_entities": len(budget_entities),
                "total_chars": total_chars,
                "token_budget": token_budget,
            }

        print(f"[RAG] Re-rank (score): chunks {len(chunk_results)}->{len(budget_chunks)}, entities {len(entity_results)}->{len(budget_entities)}, chars={total_chars}")
        return budget_chunks, budget_entities

    def _rerank_by_llm(
        self,
        question: str,
        chunk_results: List[Dict],
        entity_results: List[Dict],
        top_chunks: int,
        top_entities: int,
        debug_log: Optional[Dict] = None,
    ) -> tuple:
        """LLM-based re-ranking: score each result for relevance."""
        candidates = []
        for i, chunk in enumerate(chunk_results):
            preview = chunk.get("text", "")[:300]
            candidates.append(f"CHUNK-{i}: {preview}")
        for i, entity in enumerate(entity_results):
            name = entity.get("name", "Unknown")
            summary = (entity.get("summary") or "")[:200]
            candidates.append(f"ENTITY-{i}: {name} - {summary}")

        if not candidates:
            return chunk_results, entity_results

        prompt = f"""Rate each candidate's relevance to the question on a scale of 0-10.

Question: "{question}"

Candidates:
{chr(10).join(candidates)}

Return JSON array of objects: [{{"id": "CHUNK-0", "score": 8}}, ...]
Only include candidates with score >= 5."""

        try:
            response = self.llm.call(prompt, temperature=0.1, json_mode=True)
            scores = json.loads(response)
            if not isinstance(scores, list):
                scores = scores.get("results", scores.get("candidates", []))

            score_map = {s["id"]: s["score"] for s in scores if isinstance(s, dict)}

            scored_chunks = [
                (chunk, score_map.get(f"CHUNK-{i}", 0))
                for i, chunk in enumerate(chunk_results)
            ]
            filtered_chunks = [
                c for c, s in sorted(scored_chunks, key=lambda x: -x[1])
                if s >= 5
            ][:top_chunks]

            scored_entities = [
                (entity, score_map.get(f"ENTITY-{i}", 0))
                for i, entity in enumerate(entity_results)
            ]
            filtered_entities = [
                e for e, s in sorted(scored_entities, key=lambda x: -x[1])
                if s >= 5
            ][:top_entities]

            if debug_log is not None:
                debug_log["rerank"] = {
                    "method": "llm",
                    "input_chunks": len(chunk_results),
                    "input_entities": len(entity_results),
                    "output_chunks": len(filtered_chunks),
                    "output_entities": len(filtered_entities),
                    "scores": score_map,
                }

            print(f"[RAG] Re-rank (llm): chunks {len(chunk_results)}->{len(filtered_chunks)}, entities {len(entity_results)}->{len(filtered_entities)}")
            return filtered_chunks, filtered_entities

        except Exception as e:
            print(f"[RAG] LLM re-ranking failed, falling back to score: {e}")
            return self._rerank_by_score(
                chunk_results, entity_results,
                top_chunks, top_entities, CONTEXT_TOKEN_BUDGET,
                debug_log,
            )

    # =====================
    # NEW: Result Graph Builder
    # =====================

    def _build_result_graph(
        self,
        doc_results: List[Dict],
        answer_text: str,
        top_k_entities: int = 50,
        top_k_documents: int = 50,
    ) -> Dict[str, List]:
        """
        Build a result graph containing semantically relevant entities.
        Searches the answer text against entities and includes relevance scores.
        """
        nodes = []
        node_keys = set()
        links = []

        if not VECTOR_DB_AVAILABLE:
            return {"nodes": nodes, "links": links}

        try:
            if not answer_text or not answer_text.strip():
                return {"nodes": nodes, "links": links}

            answer_embedding = embedding_service.generate_embedding(answer_text)
            print(f"[RAG] Building result graph from answer text ({len(answer_text)} chars)")

            all_entity_results = []
            try:
                all_entity_results = vector_db_service.search_entities(
                    query_embedding=answer_embedding,
                    top_k=top_k_entities
                )
                print(f"[RAG] Found {len(all_entity_results)} entities via answer text search")
            except Exception as e:
                print(f"[RAG] Error searching entities: {e}")

            entity_distance_map = {r["id"]: r.get("distance", 1.0) for r in all_entity_results if r.get("id")}

            entity_keys = list(entity_distance_map.keys())
            if entity_keys:
                entity_nodes = self._get_entity_nodes_from_neo4j(entity_keys)
                for node in entity_nodes:
                    if node["key"] and node["key"] not in node_keys:
                        node_keys.add(node["key"])
                        distance = entity_distance_map.get(node.get("key"), 1.0)
                        confidence = 1.0 - distance if distance is not None else 0.0
                        node["confidence"] = max(0.0, min(1.0, confidence))
                        node["distance"] = distance
                        nodes.append(node)

            if len(node_keys) > 1:
                all_keys = list(node_keys)
                entity_links = self._get_relationships_between_nodes(all_keys)
                links.extend(entity_links)

            print(f"[RAG] Result graph: {len(nodes)} entities, {len(links)} links")

        except Exception as e:
            print(f"[RAG] Error building result graph: {e}")
            import traceback
            traceback.print_exc()

        return {"nodes": nodes, "links": links}

    # =====================
    # MAIN: answer_question (unified hybrid pipeline)
    # =====================

    def answer_question(
        self,
        question: str,
        selected_keys: Optional[List[str]] = None,
        confidence_threshold: Optional[float] = None,
        case_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Answer a question using hybrid retrieval:
        1. Classify question type (semantic/structural/hybrid)
        2. Retrieve relevant text chunks via vector search
        3. Retrieve relevant entities via vector search + Neo4j enrichment
        4. Merge user-selected entities (if any)
        5. Traverse graph for connected context
        6. Optionally run Cypher for structural questions
        7. Re-rank results
        8. Build combined context and generate answer

        Args:
            question: User's question
            selected_keys: Optional list of selected node keys for focused context
            confidence_threshold: Optional confidence threshold for vector search
            case_id: Optional case ID for scoping search and graph traversal

        Returns:
            Dict with answer and metadata including debug_log
        """
        from datetime import datetime

        pipeline_start = time.time()

        debug_log = {
            "timestamp": datetime.now().isoformat(),
            "question": question,
            "selected_keys": selected_keys,
            "case_id": case_id,
            "question_type": None,
            "chunk_search": None,
            "entity_search": None,
            "graph_traversal": None,
            "cypher_answer_query": None,
            "rerank": None,
            "context_mode": None,
            "context_preview": None,
            "final_prompt": None,
            "stages": [],
        }

        def _add_stage(stage_name, step, t_start, **kwargs):
            """Helper to record a pipeline stage with timing."""
            duration_ms = int((time.time() - t_start) * 1000)
            stage_entry = {
                "stage": stage_name,
                "step": step,
                "started_at": datetime.fromtimestamp(t_start).isoformat(),
                "duration_ms": duration_ms,
            }
            stage_entry.update(kwargs)
            debug_log["stages"].append(stage_entry)
            return duration_ms

        context_mode = "hybrid"
        context_description = ""
        cypher_context = None

        # ── Stage 0: Classify question type ──────────────────────────────
        t0 = time.time()
        question_type = "hybrid"
        stage0_details = {}
        if QUESTION_CLASSIFICATION_ENABLED and case_id:
            try:
                question_type = self.llm.classify_question(question)
                stage0_details["llm_prompt"] = self.llm._last_prompt
                stage0_details["llm_response"] = self.llm._last_raw_response
                print(f"[RAG] Question classified as: {question_type}")
            except Exception as e:
                print(f"[RAG] Question classification failed: {e}")
                question_type = "hybrid"
                stage0_details["error"] = str(e)
        debug_log["question_type"] = question_type
        _add_stage(
            "Question Classification", 0, t0,
            input={"question": question, "enabled": QUESTION_CLASSIFICATION_ENABLED, "case_id": case_id},
            output={"classification": question_type},
            details=stage0_details,
        )

        # ── Stage 0b: Cypher query generation ────────────────────────────
        t0b = time.time()
        graph_summary = None
        stage0b_details = {}
        if question_type in ("structural", "hybrid") and case_id:
            try:
                graph_summary = self.neo4j.get_graph_summary(case_id)
                if graph_summary:
                    stage0b_details["graph_summary"] = {
                        "total_nodes": graph_summary.get("total_nodes", 0),
                        "total_relationships": graph_summary.get("total_relationships", 0),
                        "entity_types": graph_summary.get("entity_types", []),
                        "relationship_types": graph_summary.get("relationship_types", []),
                        "entities_count": len(graph_summary.get("entities", [])),
                    }
                    schema_info = self._build_schema_info(graph_summary)
                    stage0b_details["schema_info"] = schema_info
                    cypher_context = self._try_cypher_query(question, graph_summary, debug_log)
                    stage0b_details["llm_prompt"] = self.llm._last_prompt
                    stage0b_details["llm_response"] = self.llm._last_raw_response
                    if cypher_context:
                        print(f"[RAG] Cypher query returned results")
                else:
                    stage0b_details["error"] = "get_graph_summary returned None"
            except Exception as e:
                print(f"[RAG] Cypher query failed: {e}")
                stage0b_details["error"] = str(e)

        cypher_query_info = debug_log.get("cypher_answer_query") or {}
        _add_stage(
            "Cypher Query Generation", "0b", t0b,
            input={"question": question, "question_type": question_type, "case_id": case_id},
            output={
                "cypher_generated": bool(cypher_query_info.get("generated_cypher")),
                "cypher_query": cypher_query_info.get("generated_cypher"),
                "result_rows": cypher_query_info.get("results", {}).get("rows_returned") if isinstance(cypher_query_info.get("results"), dict) else None,
                "results_preview": cypher_query_info.get("results", {}).get("sample_results", [])[:5] if isinstance(cypher_query_info.get("results"), dict) else None,
            },
            details=stage0b_details,
        )

        # ── Stage 1: Retrieve chunks (or documents) ─────────────────────
        t1 = time.time()
        chunk_results = []
        if question_type != "structural" or not cypher_context:
            chunk_results = self._retrieve_chunks(
                question, case_id,
                confidence_threshold=confidence_threshold,
                debug_log=debug_log,
            )
        chunk_search_info = debug_log.get("chunk_search") or {}
        _add_stage(
            "Chunk/Document Retrieval", 1, t1,
            input={
                "question": question[:200],
                "case_id": case_id,
                "confidence_threshold": confidence_threshold or VECTOR_SEARCH_CONFIDENCE_THRESHOLD,
                "skipped": question_type == "structural" and bool(cypher_context),
            },
            output={
                "source": chunk_search_info.get("source", "skipped"),
                "total_results": chunk_search_info.get("total_results", 0),
                "after_threshold": chunk_search_info.get("filtered_results", 0),
            },
            details={
                "top_k": chunk_search_info.get("top_k"),
                "chunks_in_db": chunk_search_info.get("chunks_in_db"),
                "embedding_provider": EMBEDDING_PROVIDER if VECTOR_DB_AVAILABLE else None,
                "embedding_model": EMBEDDING_MODEL if VECTOR_DB_AVAILABLE else None,
                "results": chunk_search_info.get("results", []),
            },
        )

        # ── Stage 2: Retrieve entities ───────────────────────────────────
        t2 = time.time()
        entity_results = self._retrieve_entities(question, case_id, debug_log=debug_log)
        entity_search_info = debug_log.get("entity_search") or {}
        _add_stage(
            "Entity Retrieval", 2, t2,
            input={"question": question[:200], "case_id": case_id, "top_k": ENTITY_SEARCH_TOP_K},
            output={
                "vector_results": entity_search_info.get("vector_results", 0),
                "enriched_from_neo4j": entity_search_info.get("enriched_entities", 0),
            },
            details={
                "entity_keys": entity_search_info.get("entity_keys", []),
                "results": [
                    {
                        "key": e.get("key"),
                        "name": e.get("name"),
                        "type": e.get("type"),
                        "distance": e.get("distance"),
                        "has_verified_facts": bool(e.get("verified_facts")),
                        "has_ai_insights": bool(e.get("ai_insights")),
                    }
                    for e in entity_results[:20]
                ],
            },
        )

        # ── Stage 3: Merge selected entities ─────────────────────────────
        t3 = time.time()
        merged_count = 0
        if selected_keys:
            try:
                selected_entities = self._get_entity_nodes_from_neo4j(selected_keys)
                existing_keys = {e.get("key") for e in entity_results}
                for se in selected_entities:
                    if se.get("key") not in existing_keys:
                        se["distance"] = 0.0
                        entity_results.append(se)
                        existing_keys.add(se.get("key"))
                        merged_count += 1
                print(f"[RAG] Merged {len(selected_entities)} selected entities")
            except Exception as e:
                print(f"[RAG] Error getting selected entities: {e}")
        _add_stage(
            "Selected Entity Merge", 3, t3,
            input={"selected_keys": selected_keys or []},
            output={"merged_count": merged_count, "total_entities": len(entity_results)},
        )

        # ── Stage 4: Graph traversal ─────────────────────────────────────
        t4 = time.time()
        all_entity_keys = [e.get("key") for e in entity_results if e.get("key")]
        graph_context = self._traverse_graph(all_entity_keys, case_id, debug_log=debug_log)
        graph_traversal_info = debug_log.get("graph_traversal") or {}
        total_connections = 0
        connection_list = []
        for ge in graph_context.get("selected_entities", []):
            conns = ge.get("connections", [])
            total_connections += len(conns)
            for conn in conns[:5]:
                connection_list.append({
                    "from": ge.get("name"),
                    "relationship": conn.get("relationship"),
                    "to": conn.get("name"),
                    "to_type": conn.get("type"),
                    "direction": conn.get("direction"),
                })
        _add_stage(
            "Graph Traversal", 4, t4,
            input={"entity_keys": all_entity_keys[:20], "case_id": case_id, "depth": GRAPH_TRAVERSAL_DEPTH},
            output={
                "entities_with_connections": graph_traversal_info.get("entities_returned", 0),
                "total_connections": total_connections,
            },
            details={
                "connections": connection_list[:30],
            },
        )

        # ── Stage 5: Re-ranking ──────────────────────────────────────────
        t5 = time.time()
        chunk_results, entity_results = self._rerank_results(
            question, chunk_results, entity_results, debug_log
        )
        rerank_info = debug_log.get("rerank") or {}
        stage5_details = {
            "method": rerank_info.get("method", "disabled"),
            "token_budget": rerank_info.get("token_budget"),
        }
        if rerank_info.get("scores"):
            stage5_details["scores"] = rerank_info["scores"]
        if rerank_info.get("method") == "llm":
            stage5_details["llm_prompt"] = self.llm._last_prompt
        _add_stage(
            "Re-ranking", 5, t5,
            input={
                "method": RERANK_METHOD if RERANK_ENABLED else "disabled",
                "input_chunks": rerank_info.get("input_chunks", len(chunk_results)),
                "input_entities": rerank_info.get("input_entities", len(entity_results)),
            },
            output={
                "output_chunks": rerank_info.get("output_chunks", len(chunk_results)),
                "output_entities": rerank_info.get("output_entities", len(entity_results)),
                "total_chars": rerank_info.get("total_chars"),
            },
            details=stage5_details,
        )

        # ── Stage 6: Context building ────────────────────────────────────
        t6 = time.time()
        context = self._build_hybrid_context(
            chunk_results, entity_results, graph_context, cypher_context
        )

        # Build context description
        parts = []
        if chunk_results:
            source = debug_log.get("chunk_search", {}).get("source", "unknown")
            parts.append(f"{len(chunk_results)} text passages ({source})")
        if entity_results:
            parts.append(f"{len(entity_results)} entities")
        graph_entity_count = len(graph_context.get("selected_entities", []))
        if graph_entity_count:
            parts.append(f"{graph_entity_count} graph connections")
        if cypher_context:
            parts.append("Cypher query results")
        context_description = "Hybrid retrieval: " + ", ".join(parts) if parts else "No relevant context found"

        debug_log["context_mode"] = context_mode
        debug_log["context_preview"] = context[:1000] + "..." if len(context) > 1000 else context

        context_sections = []
        if chunk_results:
            context_sections.append("TEXT PASSAGES")
        if entity_results:
            context_sections.append("ENTITIES")
        if graph_context.get("selected_entities"):
            context_sections.append("GRAPH CONNECTIONS")
        if cypher_context:
            context_sections.append("CYPHER RESULTS")

        _add_stage(
            "Context Building", 6, t6,
            input={
                "chunks": len(chunk_results),
                "entities": len(entity_results),
                "graph_entities": graph_entity_count,
                "has_cypher": cypher_context is not None,
            },
            output={
                "context_length_chars": len(context),
                "sections": context_sections,
            },
            details={
                "full_context": context,
            },
        )

        log_section(
            source_file=__file__,
            source_func="answer_question",
            title="Context: hybrid retrieval",
            content={
                "question_type": question_type,
                "chunks": len(chunk_results),
                "entities": len(entity_results),
                "graph_entities": graph_entity_count,
                "cypher_used": cypher_context is not None,
                "context_length": len(context),
            },
            as_json=True,
        )

        # ── Stage 7: Answer generation ───────────────────────────────────
        t7 = time.time()
        answer, final_prompt = self.llm.answer_question_with_prompt(
            question=question,
            context=context,
        )
        debug_log["final_prompt"] = final_prompt
        _add_stage(
            "Answer Generation", 7, t7,
            input={"question": question[:200], "context_length": len(context)},
            output={"answer_length": len(answer)},
            details={
                "full_prompt": final_prompt,
                "model": {"provider": self.llm.provider, "model_id": self.llm.model_id},
                "temperature": 0.3,
            },
        )

        # Store clean answer text for entity search (before prepending document summary)
        clean_answer_text = answer

        # Prepend document/chunk summary to answer
        if chunk_results:
            doc_summary = self._format_document_summary(chunk_results)
            answer = doc_summary + "\n\n" + answer

        # ── Stage 8: Result graph building ───────────────────────────────
        t8 = time.time()
        result_graph = {"nodes": [], "links": []}
        if clean_answer_text:
            try:
                result_graph = self._build_result_graph(
                    doc_results=[],
                    answer_text=clean_answer_text,
                    top_k_entities=50,
                    top_k_documents=50,
                )
                print(f"[RAG] Result graph: {len(result_graph['nodes'])} nodes, {len(result_graph['links'])} links")
            except Exception as e:
                print(f"[RAG] Error building result graph: {e}")
                import traceback
                traceback.print_exc()
        _add_stage(
            "Result Graph Building", 8, t8,
            input={"answer_length": len(clean_answer_text)},
            output={"nodes": len(result_graph.get("nodes", [])), "links": len(result_graph.get("links", []))},
        )

        # ── Pipeline summary ─────────────────────────────────────────────
        total_duration_ms = int((time.time() - pipeline_start) * 1000)
        debug_log["total_duration_ms"] = total_duration_ms
        debug_log["pipeline_summary"] = (
            f"{question_type} query → {len(chunk_results)} chunks, {len(entity_results)} entities, "
            f"{graph_entity_count} graph connections"
            f"{', Cypher' if cypher_context else ''}"
            f" → {len(answer)} char answer in {total_duration_ms}ms"
        )

        # Store debug log in system logs
        try:
            from services.system_log_service import system_log_service, LogType, LogOrigin
            system_log_service.log(
                log_type=LogType.AI_ASSISTANT,
                origin=LogOrigin.BACKEND,
                action="AI Assistant Response Generated",
                details={
                    "question": question,
                    "question_type": question_type,
                    "context_mode": context_mode,
                    "context_description": context_description,
                    "cypher_used": cypher_context is not None,
                    "answer_length": len(answer),
                    "chunks_used": len(chunk_results),
                    "entities_used": len(entity_results),
                    "total_duration_ms": total_duration_ms,
                    "pipeline_summary": debug_log["pipeline_summary"],
                },
                success=True,
            )
        except Exception as e:
            print(f"[RAG] Failed to log to system logs: {e}")

        used_node_keys = [e.get("key") for e in entity_results if e.get("key")]

        return {
            "answer": answer,
            "context_mode": context_mode,
            "context_description": context_description,
            "cypher_used": cypher_context is not None,
            "debug_log": debug_log,
            "used_node_keys": used_node_keys,
            "result_graph": result_graph,
        }

    # =====================
    # Extract Nodes from Answer (preserved from original)
    # =====================

    def extract_nodes_from_answer(
        self,
        answer: str,
        graph_summary: Optional[Dict] = None,
    ) -> List[str]:
        """
        Generate a Cypher query from the answer to extract relevant nodes.
        """
        if not answer or not answer.strip():
            return []

        if graph_summary is None:
            graph_summary = self.neo4j.get_graph_summary()

        entity_types = list(graph_summary.get("entity_types", {}).keys())
        relationship_types = list(graph_summary.get("relationship_types", {}).keys())

        prompt = f"""Given this AI assistant answer about an investigation:

"{answer}"

Generate a Cypher query that will retrieve all nodes and relationships discussed or mentioned in this answer. The query should:

1. Match nodes that are relevant to the answer's content
2. Include relationships between those nodes
3. Return node keys (n.key) for all relevant nodes
4. Use appropriate labels and relationship types from the schema

Available entity types: {', '.join(entity_types[:20])}
Available relationship types: {', '.join(relationship_types[:20])}

The query should return distinct node keys. Use patterns like:
- MATCH (n:EntityType) WHERE ... RETURN DISTINCT n.key AS key
- MATCH (n)-[r:RELATIONSHIP_TYPE]-(m) WHERE ... RETURN DISTINCT n.key AS key, m.key AS key
- Or combine multiple patterns with UNION

Return ONLY the Cypher query, nothing else. Do not include markdown code blocks."""

        log_section(
            source_file=__file__,
            source_func="extract_nodes_from_answer",
            title="Prompt: extract nodes from answer",
            content={
                "answer_length": len(answer),
                "prompt": prompt,
            },
            as_json=True,
        )

        try:
            cypher = self.llm.call(
                prompt=prompt,
                temperature=0.2,
                json_mode=False,
            )

            if not cypher:
                print("[RAG] No Cypher query generated from answer")
                return []

            cypher = cypher.strip()
            if cypher.startswith("```"):
                lines = cypher.split("\n")
                cypher = "\n".join([l for l in lines if not l.strip().startswith("```")])
                cypher = cypher.strip()

            if "RETURN" not in cypher.upper():
                if "MATCH" in cypher.upper():
                    import re
                    node_vars = re.findall(r'\((\w+)[:\)]', cypher)
                    if node_vars:
                        unique_vars = list(set(node_vars))
                        return_clause = "RETURN DISTINCT " + ", ".join([f"{v}.key AS key" for v in unique_vars])
                        cypher = f"{cypher}\n{return_clause}"

            print(f"[RAG] Generated Cypher query from answer:\n{cypher}")

            try:
                results = self.neo4j.run_cypher(cypher)
                node_keys = []
                for row in results:
                    key = row.get("key") or row.get("node_key") or row.get("n.key") or row.get("m.key")
                    if key:
                        node_keys.append(key)
                    for value in row.values():
                        if isinstance(value, str) and value:
                            node_keys.append(value)

                node_keys = list(set(node_keys))
                print(f"[RAG] Extracted {len(node_keys)} node keys from Cypher query results")
                return node_keys

            except Exception as query_error:
                print(f"[RAG] Error executing Cypher query: {query_error}")
                return []

        except Exception as e:
            print(f"[RAG] Error generating Cypher query from answer: {e}")
            import traceback
            traceback.print_exc()
            return []

    def get_suggested_questions(
        self,
        case_id: str,
        selected_keys: Optional[List[str]] = None,
    ) -> List[str]:
        """Generate suggested questions based on current context."""
        if selected_keys and len(selected_keys) > 0:
            node_context = self.neo4j.get_context_for_nodes(selected_keys, case_id)
            entities = node_context.get("selected_entities", [])

            if entities:
                entity_names = [e["name"] for e in entities[:3]]
                return [
                    f"What is suspicious about {entity_names[0]}?",
                    f"What transactions involve {entity_names[0]}?",
                    f"Who is connected to {entity_names[0]}?",
                    "Are there any unusual patterns here?",
                    "Summarize the relationships between these entities.",
                ]

        return [
            "Summarize the key findings in this investigation.",
            "Who are the main suspects?",
            "What suspicious transactions have been identified?",
            "Are there any shell companies involved?",
            "What is the timeline of events?",
            "Which accounts show unusual activity?",
        ]


# Singleton instance
rag_service = RAGService()
