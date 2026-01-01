"""
Utility to format debug logs as markdown.
"""

from typing import Dict, Any
from datetime import datetime


def format_debug_log_as_markdown(debug_log: Dict[str, Any]) -> str:
    """
    Format a debug log dictionary as a markdown document.
    
    Args:
        debug_log: Debug log dictionary from RAG service
        
    Returns:
        Formatted markdown string
    """
    lines = []
    
    # Header
    lines.append("# AI Assistant Debug Log")
    lines.append("")
    
    # Timestamp
    timestamp = debug_log.get("timestamp", datetime.now().isoformat())
    lines.append(f"**Timestamp:** {timestamp}")
    lines.append("")
    
    # Question
    question = debug_log.get("question", "Unknown")
    lines.append(f"## Question")
    lines.append(f"{question}")
    lines.append("")
    
    # Selected Keys
    selected_keys = debug_log.get("selected_keys")
    if selected_keys:
        lines.append(f"**Selected Node Keys:** {', '.join(selected_keys)}")
        lines.append("")
    
    # Graph Summary
    graph_summary = debug_log.get("graph_summary")
    if graph_summary:
        lines.append("## Graph Summary")
        lines.append(f"- **Total Nodes:** {graph_summary.get('total_nodes', 0)}")
        lines.append(f"- **Total Relationships:** {graph_summary.get('total_relationships', 0)}")
        lines.append(f"- **Entity Types:** {', '.join(graph_summary.get('entity_types', []))}")
        lines.append(f"- **Relationship Types:** {', '.join(graph_summary.get('relationship_types', []))}")
        lines.append("")
    
    # Vector Search
    vector_search = debug_log.get("vector_search")
    if vector_search:
        lines.append("## Vector Search (Semantic Document Search)")
        if vector_search.get("enabled"):
            lines.append(f"- **Status:** Enabled")
            lines.append(f"- **Question:** {vector_search.get('question', 'N/A')}")
            lines.append(f"- **Embedding Dimensions:** {vector_search.get('embedding_dimensions', 'N/A')}")
            lines.append(f"- **Top K:** {vector_search.get('top_k', 'N/A')}")
            
            results = vector_search.get("results", [])
            if results:
                lines.append(f"- **Documents Found:** {len(results)}")
                lines.append("")
                lines.append("### Vector Search Results")
                for i, result in enumerate(results, 1):
                    lines.append(f"\n#### Document {i}")
                    lines.append(f"- **Document ID:** `{result.get('document_id', 'N/A')}`")
                    lines.append(f"- **Filename:** {result.get('filename', 'N/A')}")
                    lines.append(f"- **Distance:** {result.get('distance', 'N/A')}")
                    lines.append(f"- **Text Preview:** {result.get('text_preview', 'N/A')}")
            else:
                lines.append("- **Documents Found:** 0")
        else:
            lines.append(f"- **Status:** Disabled")
            lines.append(f"- **Reason:** {vector_search.get('reason', 'Unknown')}")
        
        if vector_search.get("error"):
            lines.append(f"- **Error:** {vector_search.get('error')}")
        
        lines.append("")
    
    # Neo4j Document Query
    neo4j_doc_query = debug_log.get("neo4j_document_query")
    if neo4j_doc_query:
        lines.append("## Neo4j Query: Nodes from Documents")
        lines.append("")
        lines.append("### Cypher Query")
        lines.append("```cypher")
        lines.append(neo4j_doc_query.get("cypher", "N/A"))
        lines.append("```")
        lines.append("")
        
        params = neo4j_doc_query.get("parameters", {})
        if params:
            lines.append("### Parameters")
            for key, value in params.items():
                if isinstance(value, list):
                    lines.append(f"- **{key}:** `{value}` ({len(value)} items)")
                else:
                    lines.append(f"- **{key}:** `{value}`")
            lines.append("")
        
        results = neo4j_doc_query.get("results")
        if results:
            lines.append("### Query Results")
            lines.append(f"- **Nodes Found:** {results.get('nodes_found', 0)}")
            nodes = results.get("nodes", [])
            if nodes:
                lines.append("")
                lines.append("#### Nodes")
                for node in nodes[:20]:  # Limit to first 20
                    lines.append(f"- **{node.get('name', 'Unknown')}** (`{node.get('key', 'N/A')}`) - {node.get('type', 'Unknown')}")
                if len(nodes) > 20:
                    lines.append(f"\n... and {len(nodes) - 20} more nodes")
        
        if neo4j_doc_query.get("error"):
            lines.append(f"**Error:** {neo4j_doc_query.get('error')}")
        
        lines.append("")
    
    # Cypher Filter Query
    cypher_filter = debug_log.get("cypher_filter_query")
    if cypher_filter:
        lines.append("## Cypher Filter Query (LLM-Generated)")
        lines.append("")
        lines.append("### Generated Cypher Query")
        lines.append("```cypher")
        lines.append(cypher_filter.get("generated_cypher", "N/A"))
        lines.append("```")
        lines.append("")
        
        results = cypher_filter.get("results")
        if results:
            if isinstance(results, dict):
                lines.append("### Query Results")
                lines.append(f"- **Nodes Found:** {results.get('nodes_found', 0)}")
                node_keys = results.get("node_keys", [])
                if node_keys:
                    lines.append(f"- **Node Keys:** {', '.join(node_keys)}")
            else:
                lines.append(f"### Query Results: {results}")
        
        if cypher_filter.get("error"):
            lines.append(f"**Error:** {cypher_filter.get('error')}")
        
        lines.append("")
    
    # Cypher Answer Query
    cypher_answer = debug_log.get("cypher_answer_query")
    if cypher_answer:
        lines.append("## Cypher Answer Query (Direct Question Query)")
        lines.append("")
        lines.append("### Generated Cypher Query")
        lines.append("```cypher")
        lines.append(cypher_answer.get("generated_cypher", "N/A"))
        lines.append("```")
        lines.append("")
        
        results = cypher_answer.get("results")
        if results:
            if isinstance(results, dict):
                lines.append("### Query Results")
                lines.append(f"- **Rows Returned:** {results.get('rows_returned', 0)}")
                sample = results.get("sample_results", [])
                if sample:
                    lines.append("")
                    lines.append("#### Sample Results")
                    for i, row in enumerate(sample[:10], 1):
                        lines.append(f"{i}. {row}")
            else:
                lines.append(f"### Query Results: {results}")
        
        lines.append("")
    
    # Hybrid Filtering
    hybrid = debug_log.get("hybrid_filtering")
    if hybrid:
        lines.append("## Hybrid Filtering Summary")
        lines.append("")
        lines.append(f"- **Vector Document IDs:** {hybrid.get('vector_doc_ids', [])}")
        lines.append(f"- **Vector Node Keys:** {len(hybrid.get('vector_node_keys', []))} nodes")
        lines.append(f"- **Cypher Node Keys:** {len(hybrid.get('cypher_node_keys', []))} nodes")
        lines.append(f"- **Combined Node Keys:** {hybrid.get('total_combined', 0)} nodes")
        lines.append("")
        combined = hybrid.get("combined_node_keys", [])
        if combined:
            lines.append("### Combined Node Keys (First 50)")
            lines.append(", ".join(combined))
            lines.append("")
    
    # Context Mode
    context_mode = debug_log.get("context_mode")
    if context_mode:
        lines.append("## Context Mode")
        lines.append(f"**Mode:** `{context_mode}`")
        lines.append("")
    
    # Context Preview
    context_preview = debug_log.get("context_preview")
    if context_preview:
        lines.append("## Context Preview")
        lines.append("")
        lines.append("```")
        lines.append(context_preview)
        lines.append("```")
        lines.append("")
    
    # Final Prompt
    final_prompt = debug_log.get("final_prompt")
    if final_prompt:
        lines.append("## Final Prompt Sent to LLM")
        lines.append("")
        lines.append("```")
        lines.append(final_prompt)
        lines.append("```")
        lines.append("")
    
    return "\n".join(lines)

