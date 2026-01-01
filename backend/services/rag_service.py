"""
RAG Service - orchestrates context retrieval and AI question answering.

Handles:
- Context-aware responses (full graph vs. selected nodes)
- Cypher query generation and execution
- Answer synthesis
"""

from typing import Dict, List, Optional, Any

from services.neo4j_service import neo4j_service
from services.llm_service import llm_service


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
            
            # Take entities with content first, then fill remaining slots
            entities_to_show = entities_with_content[:max_entities]
            if len(entities_to_show) < max_entities:
                remaining = max_entities - len(entities_to_show)
                entities_to_show.extend(entities_without_content[:remaining])
            
            entities = entities_to_show
        else:
            entities = entities[:max_entities]

        for entity in entities:
            lines.append(f"\n[{entity['type']}] {entity['name']} (key: {entity['key']})")
            if entity.get("summary"):
                lines.append(f"  Summary: {entity['summary']}")
            if entity.get("notes"):
                # Truncate notes if too long
                notes = entity["notes"]
                if len(notes) > 500:
                    notes = notes[:500] + "..."
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

            results = self.neo4j.run_cypher(cypher)

            if not results:
                return None

            # Format results
            lines = [f"Query executed: {cypher}", "", "Results:"]
            for i, row in enumerate(results[:20]):  # Limit to 20 rows
                lines.append(f"  {i + 1}. {row}")

            if len(results) > 20:
                lines.append(f"  ... and {len(results) - 20} more results")

            return "\n".join(lines)

        except Exception as e:
            print(f"Cypher execution error: {e}")
            return None

    def _generate_relevance_filter_query(
        self,
        question: str,
        graph_summary: Dict,
        max_nodes: int = 100,
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
            
            # Execute the query to get relevant node keys
            results = self.neo4j.run_cypher(cypher)
            if not results:
                return None
            
            # Extract node keys from results
            node_keys = []
            for row in results:
                if isinstance(row, dict):
                    key = row.get('key') or row.get('n.key')
                else:
                    # Handle tuple results
                    key = row[0] if len(row) > 0 else None
                
                if key:
                    node_keys.append(key)
            
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
            Dict with answer and metadata
        """
        # Get graph summary (needed for schema info regardless)
        graph_summary = self.neo4j.get_graph_summary()

        # Determine context mode
        if selected_keys and len(selected_keys) > 0:
            # Focused context (user-selected nodes)
            context_mode = "focused"
            node_context = self.neo4j.get_context_for_nodes(selected_keys)
            context = self._build_focused_context(node_context)
            context_description = f"Focused on {len(selected_keys)} selected entity(ies)"
        else:
            # Try to filter graph based on question relevance
            # This reduces context size for large graphs
            relevant_keys = self._generate_relevance_filter_query(question, graph_summary)
            
            if relevant_keys and len(relevant_keys) > 0:
                # Use filtered context (question-relevant nodes)
                context_mode = "question-filtered"
                node_context = self.neo4j.get_context_for_nodes(relevant_keys)
                context = self._build_focused_context(node_context)
                context_description = f"Question-filtered graph ({len(relevant_keys)} relevant entities from {graph_summary.get('total_nodes', 0)} total)"
            else:
                # Fallback to full graph context
                context_mode = "full"
                context = self._build_full_context(graph_summary)
                context_description = f"Full graph ({graph_summary.get('total_nodes', 0)} entities)"

        # Try Cypher query for specific questions
        query_results = self._try_cypher_query(question, graph_summary)

        # Generate answer
        answer = self.llm.answer_question(
            question=question,
            context=context,
            query_results=query_results,
        )

        return {
            "answer": answer,
            "context_mode": context_mode,
            "context_description": context_description,
            "cypher_used": query_results is not None,
        }

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
