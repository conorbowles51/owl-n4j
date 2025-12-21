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

    def _build_full_context(self, graph_summary: Dict) -> str:
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

        for entity in graph_summary.get("entities", []):
            lines.append(f"\n[{entity['type']}] {entity['name']} (key: {entity['key']})")
            if entity.get("summary"):
                lines.append(f"  Summary: {entity['summary']}")
            if entity.get("notes"):
                # Truncate notes if too long
                notes = entity["notes"]
                if len(notes) > 500:
                    notes = notes[:500] + "..."
                lines.append(f"  Notes: {notes}")

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
            # Focused context
            context_mode = "focused"
            node_context = self.neo4j.get_context_for_nodes(selected_keys)
            context = self._build_focused_context(node_context)
            context_description = f"Focused on {len(selected_keys)} selected entity(ies)"
        else:
            # Full graph context
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
