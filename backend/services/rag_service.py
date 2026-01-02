"""
RAG Service - orchestrates context retrieval and AI question answering.

Handles:
- Context-aware responses (full graph vs. selected nodes)
- Cypher query generation and execution
- Vector-based semantic document search
- Hybrid filtering (vector search + Cypher filtering)
- Answer synthesis
"""

from typing import Dict, List, Optional, Any

from services.neo4j_service import neo4j_service
from services.llm_service import llm_service
from config import VECTOR_SEARCH_ENABLED, VECTOR_SEARCH_TOP_K, HYBRID_FILTERING_ENABLED

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
        """
        Build context string from full graph summary.
        
        Args:
            graph_summary: Graph summary dictionary
            max_entities: Maximum number of entities to include (to prevent context bloat)
        """
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
        
        # Limit entities to prevent context bloat
        if total_entities > max_entities:
            lines.append(f"Showing {max_entities} of {total_entities} entities (most relevant):")
            # Prioritize entities with summaries and notes
            entities_with_content = [e for e in entities if e.get("summary") or e.get("notes")]
            entities_without_content = [e for e in entities if not (e.get("summary") or e.get("notes"))]
            
            # Prioritize entities with more detailed information (longer summaries/notes)
            entities_with_content.sort(key=lambda e: len(e.get("summary", "") + e.get("notes", "")), reverse=True)
            
            # Take entities with content first, then fill remaining slots
            entities_to_show = entities_with_content[:max_entities]
            if len(entities_to_show) < max_entities:
                remaining = max_entities - len(entities_to_show)
                entities_to_show.extend(entities_without_content[:remaining])
            
            entities = entities_to_show
        else:
            # Even if under limit, prioritize entities with more content
            entities.sort(key=lambda e: len(e.get("summary", "") + e.get("notes", "")), reverse=True)
            entities = entities[:max_entities]

        for entity in entities:
            lines.append(f"\n[{entity['type']}] {entity['name']} (key: {entity['key']})")
            if entity.get("summary"):
                # Include full summary, but truncate if extremely long
                summary = entity["summary"]
                if len(summary) > 1000:
                    summary = summary[:1000] + "..."
                lines.append(f"  Summary: {summary}")
            if entity.get("notes"):
                # Include more notes content for better context
                notes = entity["notes"]
                if len(notes) > 800:
                    notes = notes[:800] + "..."
                lines.append(f"  Notes: {notes}")

        if total_entities > max_entities:
            lines.append(f"\n... and {total_entities - max_entities} more entities (use specific questions or select nodes for focused context)")

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
                # Truncate notes if too long
                notes = entity["notes"]
                if len(notes) > 500:
                    notes = notes[:500] + "..."
                lines.append(f"  Notes: {notes}")

            if entity.get("connections"):
                lines.append("  Connections:")
                for conn in entity["connections"]:
                    direction = "→" if conn["direction"] == "outgoing" else "←"
                    lines.append(
                        f"    {direction} [{conn['relationship']}] {conn['name']} ({conn['type']})"
                    )
                    if conn.get("summary"):
                        lines.append(f"       Summary: {conn['summary'][:200]}")

        return "\n".join(lines)

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
        # Build schema info
        schema_info = self._build_schema_info(graph_summary)

        # Try to generate Cypher
        cypher = self.llm.generate_cypher(question, schema_info)
        print("Cypher: ", cypher)
        if not cypher:
            return None

        # Validate and execute
        try:
            # Basic safety check
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

            # Format results
            lines = [f"Query executed: {cypher}", "", "Results:"]
            for i, row in enumerate(results[:20]):  # Limit to 20 rows
                lines.append(f"  {i + 1}. {row}")

            if len(results) > 20:
                lines.append(f"  ... and {len(results) - 20} more results")
            
            if debug_log is not None:
                debug_log["cypher_answer_query"]["results"] = {
                    "rows_returned": len(results),
                    "sample_results": results[:10],  # First 10 for debug log
                }

            return "\n".join(lines)

        except Exception as e:
            print(f"Cypher execution error: {e}")
            return None

    def _find_relevant_documents(
        self,
        question: str,
        top_k: Optional[int] = None,
        debug_log: Optional[Dict] = None,
    ) -> List[str]:
        """
        Use vector search to find documents relevant to the question.
        
        Args:
            question: User's question
            top_k: Number of documents to retrieve (defaults to config value)
            debug_log: Optional dict to store debug information
            
        Returns:
            List of document IDs (Neo4j Document.id values)
        """
        if not VECTOR_DB_AVAILABLE:
            if debug_log is not None:
                debug_log["vector_search"] = {
                    "enabled": False,
                    "reason": "Vector DB not available"
                }
            return []
        
        if top_k is None:
            top_k = VECTOR_SEARCH_TOP_K
        
        try:
            # Generate embedding for question
            query_embedding = embedding_service.generate_embedding(question)
            
            if debug_log is not None:
                debug_log["vector_search"] = {
                    "enabled": True,
                    "question": question,
                    "embedding_dimensions": len(query_embedding),
                    "top_k": top_k,
                }
            
            # Search for similar documents
            results = vector_db_service.search(
                query_embedding=query_embedding,
                top_k=top_k
            )
            
            # Extract document IDs
            doc_ids = [r["id"] for r in results]
            
            if debug_log is not None:
                debug_log["vector_search"]["results"] = [
                    {
                        "document_id": r["id"],
                        "filename": r.get("metadata", {}).get("filename", "Unknown"),
                        "distance": r.get("distance"),
                        "text_preview": r.get("text", "")[:200] + "..." if len(r.get("text", "")) > 200 else r.get("text", ""),
                    }
                    for r in results
                ]
                debug_log["vector_search"]["documents_found"] = len(doc_ids)
            
            return doc_ids
        
        except Exception as e:
            print(f"[RAG] Vector search error: {e}")
            if debug_log is not None:
                debug_log["vector_search"] = {
                    "enabled": True,
                    "error": str(e),
                }
            return []
    
    def _get_nodes_from_documents(
        self,
        doc_ids: List[str],
        debug_log: Optional[Dict] = None,
    ) -> List[str]:
        """
        Query Neo4j to find nodes cited by the given documents.
        
        Args:
            doc_ids: List of document IDs from vector search
            debug_log: Optional dict to store debug information
            
        Returns:
            List of node keys
        """
        if not doc_ids:
            return []
        
        try:
            # Query Neo4j for nodes related to these documents
            # Documents can be linked via MENTIONED_IN or CITED_IN relationships
            # Also check vector_db_id field for compatibility
            cypher = """
            MATCH (n)-[:MENTIONED_IN|CITED_IN]->(d:Document)
            WHERE d.id IN $doc_ids OR d.vector_db_id IN $doc_ids
            RETURN DISTINCT n.key AS key, n.name AS name, labels(n)[0] AS type
            """
            
            if debug_log is not None:
                debug_log["neo4j_document_query"] = {
                    "cypher": cypher,
                    "parameters": {"doc_ids": doc_ids},
                }
            
            results = self.neo4j.run_cypher(cypher, params={"doc_ids": doc_ids})
            node_keys = []
            nodes_info = []
            for row in results:
                if isinstance(row, dict):
                    key = row.get('key')
                    name = row.get('name', 'Unknown')
                    node_type = row.get('type', 'Unknown')
                else:
                    key = row[0] if len(row) > 0 else None
                    name = row[1] if len(row) > 1 else 'Unknown'
                    node_type = row[2] if len(row) > 2 else 'Unknown'
                if key:
                    node_keys.append(key)
                    nodes_info.append({
                        "key": key,
                        "name": name,
                        "type": node_type,
                    })
            
            if debug_log is not None:
                debug_log["neo4j_document_query"]["results"] = {
                    "nodes_found": len(node_keys),
                    "nodes": nodes_info,
                }
            
            return node_keys
        except Exception as e:
            print(f"[RAG] Error querying nodes from documents: {e}")
            if debug_log is not None:
                debug_log["neo4j_document_query"] = {
                    "error": str(e),
                }
            return []

    def _generate_relevance_filter_query(
        self,
        question: str,
        graph_summary: Dict,
        max_nodes: int = 100,
        debug_log: Optional[Dict] = None,
    ) -> Optional[List[str]]:
        """
        Generate a Cypher query to find nodes relevant to the question.
        This reduces context size by filtering to only relevant entities.
        
        Args:
            question: User's question
            graph_summary: Graph summary for schema info
            max_nodes: Maximum number of nodes to return
            
        Returns:
            List of relevant node keys, or None if filtering not applicable
        """
        # Skip filtering if graph is small
        total_nodes = graph_summary.get('total_nodes', 0)
        if total_nodes < 50:
            return None
        
        schema_info = self._build_schema_info(graph_summary)
        
        # Generate a Cypher query to find relevant nodes
        prompt = f"""Based on this question: "{question}"

Generate a Cypher query that finds nodes most relevant to answering this question.
The query should:
1. Match nodes that are likely to contain information needed to answer the question
2. Use WHERE clauses to filter by:
   - Node names containing relevant keywords
   - Summaries containing relevant concepts
   - Notes containing relevant information
   - Entity types that are relevant to the question
3. Return DISTINCT node keys
4. Limit results to {max_nodes} nodes

{schema_info}

Return ONLY a Cypher query in this format:
MATCH (n)
WHERE [relevant conditions]
RETURN DISTINCT n.key AS key
LIMIT {max_nodes}

Example for question "Who are the suspects?":
MATCH (n)
WHERE (n.name CONTAINS 'suspect' OR n.summary CONTAINS 'suspect' OR 
       labels(n)[0] IN ['Person', 'Entity'] AND n.summary IS NOT NULL)
RETURN DISTINCT n.key AS key
LIMIT {max_nodes}
"""
        
        try:
            # Use LLM to generate the filtering query
            # For filtering queries, we want a simpler, more focused approach
            # Use a direct prompt instead of the full Cypher generation method
            cypher = self.llm.call(
                prompt=prompt,
                temperature=0.2,  # Lower temperature for more consistent queries
                json_mode=False,
            )
            
            # Extract Cypher query from response (might be wrapped in markdown or text)
            if not cypher:
                return None
            
            # Clean up the response - remove markdown code blocks if present
            cypher = cypher.strip()
            if cypher.startswith("```"):
                # Remove markdown code blocks
                lines = cypher.split("\n")
                cypher = "\n".join([l for l in lines if not l.strip().startswith("```")])
            cypher = cypher.strip()
            
            # Basic validation - ensure it looks like a Cypher query
            if not cypher.upper().startswith("MATCH"):
                return None
            
            # Safety check - ensure it's a read-only query
            cypher_upper = cypher.upper()
            if any(
                dangerous in cypher_upper
                for dangerous in ["DELETE", "REMOVE", "SET", "CREATE", "MERGE", "DROP"]
            ):
                print(f"Blocked potentially dangerous relevance filter query: {cypher}")
                return None
            
            if debug_log is not None:
                debug_log["cypher_filter_query"] = {
                    "generated_cypher": cypher,
                    "max_nodes": max_nodes,
                }
            
            # Execute the query to get relevant node keys
            results = self.neo4j.run_cypher(cypher)
            if not results:
                if debug_log is not None:
                    debug_log["cypher_filter_query"]["results"] = "No results"
                return None
            
            # Extract node keys from results
            node_keys = []
            nodes_info = []
            for row in results:
                if isinstance(row, dict):
                    key = row.get('key') or row.get('n.key')
                else:
                    # Handle tuple results
                    key = row[0] if len(row) > 0 else None
                
                if key:
                    node_keys.append(key)
                    nodes_info.append({"key": key})
            
            if debug_log is not None:
                debug_log["cypher_filter_query"]["results"] = {
                    "nodes_found": len(node_keys),
                    "node_keys": node_keys[:20],  # Limit to first 20 for readability
                }
            
            # Only use filtered results if they're significantly smaller than full graph
            if len(node_keys) < total_nodes * 0.7 and len(node_keys) > 0:
                print(f"[RAG] Filtered graph from {total_nodes} to {len(node_keys)} relevant nodes")
                return node_keys[:max_nodes]
            
            return None
            
        except Exception as e:
            print(f"[RAG] Error generating relevance filter: {e}")
            return None

    def answer_question(
        self,
        question: str,
        selected_keys: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Answer a question using the appropriate context.

        Args:
            question: User's question
            selected_keys: Optional list of selected node keys for focused context

        Returns:
            Dict with answer and metadata including debug_log
        """
        # Initialize debug log
        debug_log = {
            "timestamp": None,
            "question": question,
            "selected_keys": selected_keys,
            "graph_summary": None,
            "vector_search": None,
            "neo4j_document_query": None,
            "cypher_filter_query": None,
            "cypher_answer_query": None,
            "context_mode": None,
            "context_preview": None,
            "final_prompt": None,
        }
        
        from datetime import datetime
        debug_log["timestamp"] = datetime.now().isoformat()
        
        # Get graph summary (needed for schema info regardless)
        graph_summary = self.neo4j.get_graph_summary()
        debug_log["graph_summary"] = {
            "total_nodes": graph_summary.get('total_nodes', 0),
            "total_relationships": graph_summary.get('total_relationships', 0),
            "entity_types": list(graph_summary.get('entity_types', {}).keys()),
            "relationship_types": list(graph_summary.get('relationship_types', {}).keys()),
        }

        # Track which node keys were actually used to generate the answer
        used_node_keys = []
        
        # Determine context mode
        if selected_keys and len(selected_keys) > 0:
            # Focused context (user-selected nodes)
            context_mode = "focused"
            used_node_keys = selected_keys.copy()
            
            if debug_log is not None:
                # Document the query pattern used (actual query is in neo4j_service)
                debug_log["focused_context_query"] = {
                    "cypher": f"MATCH (n) WHERE n.key IN $keys OPTIONAL MATCH (n)-[r]-(connected) RETURN n.key, n.name, labels(n)[0] AS type, n.summary, n.notes, collect(DISTINCT {{key: connected.key, name: connected.name, type: labels(connected)[0], summary: connected.summary, relationship: type(r), direction: CASE WHEN startNode(r) = n THEN 'outgoing' ELSE 'incoming' END}}) AS connections",
                    "parameters": {"keys": selected_keys},
                    "selected_node_keys": selected_keys,
                }
            
            node_context = self.neo4j.get_context_for_nodes(selected_keys)
            context = self._build_focused_context(node_context)
            context_description = f"Focused on {len(selected_keys)} selected entity(ies)"
            
            if debug_log is not None:
                debug_log["context_mode"] = context_mode
                debug_log["context_preview"] = context[:1000] + "..." if len(context) > 1000 else context
                debug_log["focused_context"] = {
                    "selected_node_keys": selected_keys,
                    "entities_count": len(node_context.get("selected_entities", [])),
                    "entities": [
                        {
                            "key": e.get("key"),
                            "name": e.get("name"),
                            "type": e.get("type"),
                        }
                        for e in node_context.get("selected_entities", [])[:20]
                    ],
                }
        else:
            # Hybrid filtering: Vector search + Cypher filtering
            all_relevant_keys = set()
            doc_ids = []
            cypher_node_keys = []
            
            # 1. Vector search for relevant documents (if enabled)
            if VECTOR_DB_AVAILABLE and HYBRID_FILTERING_ENABLED:
                try:
                    doc_ids = self._find_relevant_documents(question, debug_log=debug_log)
                    if doc_ids:
                        doc_node_keys = self._get_nodes_from_documents(doc_ids, debug_log=debug_log)
                        all_relevant_keys.update(doc_node_keys)
                        print(f"[RAG] Vector search found {len(doc_ids)} documents, {len(doc_node_keys)} related nodes")
                except Exception as e:
                    print(f"[RAG] Vector search failed, continuing with Cypher filtering: {e}")
                    if debug_log is not None:
                        debug_log["vector_search"] = {"error": str(e)}
            
            # 2. LLM-generated Cypher filtering (existing)
            try:
                cypher_node_keys = self._generate_relevance_filter_query(question, graph_summary, debug_log=debug_log) or []
                all_relevant_keys.update(cypher_node_keys)
            except Exception as e:
                print(f"[RAG] Cypher filtering failed: {e}")
                if debug_log is not None:
                    debug_log["cypher_filter_query"] = {"error": str(e)}
            
            # 3. Determine which context to use
            total_nodes = graph_summary.get('total_nodes', 0)
            relevant_keys_list = list(all_relevant_keys)
            
            if relevant_keys_list and len(relevant_keys_list) < total_nodes * 0.7:
                # Use hybrid filtered context
                context_mode = "hybrid-filtered"
                used_node_keys = relevant_keys_list.copy()
                node_context = self.neo4j.get_context_for_nodes(relevant_keys_list)
                context = self._build_focused_context(node_context)
                
                # Build description
                desc_parts = [f"{len(relevant_keys_list)} relevant entities from {total_nodes} total"]
                if doc_ids:
                    desc_parts.append(f"{len(doc_ids)} documents matched")
                if cypher_node_keys:
                    desc_parts.append(f"{len(cypher_node_keys)} from Cypher filter")
                
                context_description = f"Hybrid-filtered graph ({', '.join(desc_parts)})"
                
                # Store context info in debug log
                if debug_log is not None:
                    debug_log["context_mode"] = context_mode
                    debug_log["context_preview"] = context[:1000] + "..." if len(context) > 1000 else context
                    debug_log["hybrid_filtering"] = {
                        "vector_doc_ids": doc_ids,
                        "vector_node_keys": list(set(doc_node_keys)) if doc_ids else [],
                        "cypher_node_keys": cypher_node_keys,
                        "combined_node_keys": relevant_keys_list[:50],  # First 50 for readability
                        "total_combined": len(relevant_keys_list),
                    }
            elif relevant_keys_list:
                # We have relevant keys but they're >= 70% of total nodes
                # Still use them for used_node_keys, but use full context for answer
                context_mode = "question-filtered"
                used_node_keys = relevant_keys_list.copy()
                # Use full context but track which nodes were filtered
                context = self._build_full_context(graph_summary)
                context_description = f"Question-filtered graph ({len(relevant_keys_list)} of {total_nodes} entities)"
                
                if debug_log is not None:
                    debug_log["context_mode"] = context_mode
                    debug_log["context_preview"] = context[:1000] + "..." if len(context) > 1000 else context
                    debug_log["hybrid_filtering"] = {
                        "vector_doc_ids": doc_ids,
                        "vector_node_keys": list(set(doc_node_keys)) if doc_ids else [],
                        "cypher_node_keys": cypher_node_keys,
                        "combined_node_keys": relevant_keys_list[:50],
                        "total_combined": len(relevant_keys_list),
                        "note": "Filtered nodes >= 70% of total, using full context but tracking filtered nodes",
                    }
            else:
                # Fallback to full graph context - no filtering worked
                context_mode = "full"
                # For full graph, we don't track specific nodes (too many)
                # The answer is based on the entire graph, so we leave used_node_keys empty
                # Users can still use "Show on Graph" but it will fall back to text extraction
                used_node_keys = []
                
                context = self._build_full_context(graph_summary)
                context_description = f"Full graph ({total_nodes} entities)"
                
                if debug_log is not None:
                    debug_log["context_mode"] = context_mode
                    debug_log["context_preview"] = context[:1000] + "..." if len(context) > 1000 else context

        # Try Cypher query for specific questions
        query_results = self._try_cypher_query(question, graph_summary, debug_log=debug_log)

        # Generate answer - capture the prompt
        # We need to get the prompt that will be sent to LLM
        # Let's modify the LLM service to return the prompt, or capture it here
        answer, final_prompt = self.llm.answer_question_with_prompt(
            question=question,
            context=context,
            query_results=query_results,
        )
        
        if debug_log is not None:
            debug_log["final_prompt"] = final_prompt
            debug_log["context_mode"] = context_mode

        # Store debug log in system logs (instead of downloading)
        try:
            from services.system_log_service import system_log_service, LogType, LogOrigin
            system_log_service.log(
                log_type=LogType.AI_ASSISTANT,
                origin=LogOrigin.BACKEND,
                action="AI Assistant Response Generated",
                details={
                    "question": question,
                    "context_mode": context_mode,
                    "context_description": context_description,
                    "cypher_used": query_results is not None,
                    "answer_length": len(answer),
                    "used_node_keys_count": len(used_node_keys),
                    "debug_log": debug_log,  # Include full debug log in system logs
                },
                success=True,
            )
        except Exception as e:
            print(f"[RAG] Failed to log to system logs: {e}")

        return {
            "answer": answer,
            "context_mode": context_mode,
            "context_description": context_description,
            "cypher_used": query_results is not None,
            "debug_log": debug_log,
            "used_node_keys": used_node_keys,  # Node keys actually used to generate the answer
        }

    def extract_nodes_from_answer(
        self,
        answer: str,
        graph_summary: Optional[Dict] = None,
    ) -> List[str]:
        """
        Generate a Cypher query from the answer summary to extract relevant nodes and relationships.
        
        Uses the LLM to analyze the answer and generate a Cypher query that will retrieve
        the nodes and relationships discussed in the answer.
        
        Args:
            answer: AI-generated answer text
            graph_summary: Optional graph summary (will fetch if not provided)
            
        Returns:
            List of node keys from the generated Cypher query
        """
        if not answer or not answer.strip():
            return []
        
        if graph_summary is None:
            graph_summary = self.neo4j.get_graph_summary()
        
        # Get schema information
        entity_types = list(graph_summary.get("entity_types", {}).keys())
        relationship_types = list(graph_summary.get("relationship_types", {}).keys())
        
        # Create prompt for LLM to generate Cypher query
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

        try:
            cypher = self.llm.call(
                prompt=prompt,
                temperature=0.2,  # Low temperature for consistent queries
                json_mode=False,
            )
            
            if not cypher:
                print("[RAG] No Cypher query generated from answer")
                return []
            
            # Clean up the response - remove markdown code blocks if present
            cypher = cypher.strip()
            if cypher.startswith("```"):
                # Remove markdown code blocks
                lines = cypher.split("\n")
                cypher = "\n".join([l for l in lines if not l.strip().startswith("```")])
                cypher = cypher.strip()
            
            # Remove leading/trailing whitespace
            cypher = cypher.strip()
            
            # If the query doesn't return keys, modify it to return keys
            if "RETURN" not in cypher.upper():
                # Try to add RETURN clause
                if "MATCH" in cypher.upper():
                    # Find all node variables
                    import re
                    node_vars = re.findall(r'\((\w+)[:\)]', cypher)
                    if node_vars:
                        unique_vars = list(set(node_vars))
                        return_clause = "RETURN DISTINCT " + ", ".join([f"{v}.key AS key" for v in unique_vars])
                        cypher = f"{cypher}\n{return_clause}"
            
            # Ensure we're returning keys
            if "RETURN" in cypher.upper() and ".key" not in cypher:
                # Modify RETURN to include keys
                cypher = cypher.replace("RETURN", "RETURN DISTINCT").replace("return", "RETURN DISTINCT")
                # Try to add .key to node variables
                import re
                # Find RETURN clause and add .key
                return_match = re.search(r'RETURN\s+(.+?)(?:\s|$)', cypher, re.IGNORECASE)
                if return_match:
                    return_vars = return_match.group(1).split(",")
                    new_return = "RETURN DISTINCT " + ", ".join([
                        f"{v.strip()}.key AS key" if "." not in v.strip() else v.strip()
                        for v in return_vars
                    ])
                    cypher = re.sub(r'RETURN\s+.+?(?:\s|$)', new_return + " ", cypher, flags=re.IGNORECASE)
            
            print(f"[RAG] Generated Cypher query from answer:\n{cypher}")
            
            # Execute the query
            try:
                results = self.neo4j.run_cypher(cypher)
                
                # Extract node keys from results
                node_keys = []
                for row in results:
                    # Try different possible key field names
                    key = row.get("key") or row.get("node_key") or row.get("n.key") or row.get("m.key")
                    if key:
                        node_keys.append(key)
                    # If no key field, try to get all values that look like keys
                    for value in row.values():
                        if isinstance(value, str) and value:
                            node_keys.append(value)
                
                # Remove duplicates
                node_keys = list(set(node_keys))
                
                print(f"[RAG] Extracted {len(node_keys)} node keys from Cypher query results")
                return node_keys
                
            except Exception as query_error:
                print(f"[RAG] Error executing Cypher query: {query_error}")
                print(f"[RAG] Query was: {cypher}")
                return []
            
        except Exception as e:
            print(f"[RAG] Error generating Cypher query from answer: {e}")
            import traceback
            traceback.print_exc()
            return []

    def get_suggested_questions(
        self,
        selected_keys: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Generate suggested questions based on current context.

        Args:
            selected_keys: Optional selected node keys

        Returns:
            List of suggested question strings
        """
        if selected_keys and len(selected_keys) > 0:
            # Get details for selected nodes
            node_context = self.neo4j.get_context_for_nodes(selected_keys)
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

        # Full graph suggestions
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
