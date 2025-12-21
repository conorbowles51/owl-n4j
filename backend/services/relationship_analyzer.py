"""
Relationship Analyzer Service

Analyzes a newly created node to find potential relationships with existing nodes in the graph.
"""

from typing import Dict, List, Optional
import os
import json
from pathlib import Path
import sys

# Add ingestion scripts to path for imports
INGESTION_SCRIPTS_PATH = Path(__file__).parent.parent.parent / "ingestion" / "scripts"
if str(INGESTION_SCRIPTS_PATH) not in sys.path:
    sys.path.insert(0, str(INGESTION_SCRIPTS_PATH))

try:
    from llm_client import call_llm, parse_json_response
    from profile_loader import get_ingestion_config
    _llm_available = True
except ImportError as e:
    print(f"Warning: Could not import LLM client: {e}")
    _llm_available = False
    # Fallback functions if imports fail
    def call_llm(*args, **kwargs):
        return '{"relationships": []}'
    def parse_json_response(response):
        return {"relationships": []}
    def get_ingestion_config():
        return {}


def analyze_node_relationships(
    node_name: str,
    node_type: str,
    node_key: str,
    node_description: Optional[str] = None,
    node_summary: Optional[str] = None,
    existing_nodes: List[Dict] = None,
) -> List[Dict]:
    """
    Use LLM to analyze a new node and find potential relationships with existing nodes.
    
    Args:
        node_name: Name of the new node
        node_type: Type of the new node
        node_key: Key of the new node
        node_description: Description/notes of the new node
        node_summary: Summary of the new node
        existing_nodes: List of existing nodes with their keys, names, and types
        
    Returns:
        List of relationship dictionaries with from_key, to_key, type, and notes
    """
    if not existing_nodes or len(existing_nodes) == 0:
        return []
    
    if not _llm_available:
        return []
    
    # Get profile configuration
    config = get_ingestion_config()
    system_context = config.get("system_context", "You are an assistant helping with investigations.")
    relationship_examples = config.get("relationship_examples", [])
    relationship_types = config.get("relationship_types", [])
    temperature = config.get("temperature", 1.0)
    
    # Build relationship guidance
    if relationship_examples:
        relationship_guidance = f"""
For relationships, identify connections between the new node and existing nodes. Use descriptive relationship types. Examples:
{chr(10).join(f"- {example}" for example in relationship_examples)}

You are not limited to these examples - create appropriate relationship types that accurately describe the connections.
"""
    elif relationship_types:
        relationship_guidance = f"""
For relationships, you may use one of these types: [{", ".join(relationship_types)}], or create new descriptive types.
"""
    else:
        relationship_guidance = """
For relationships, use descriptive relationship types like "OWNS", "WORKS_FOR", "RELATED_TO", "MET_WITH", etc.
"""
    
    # Build list of existing nodes for context
    existing_nodes_list = []
    for node in existing_nodes[:100]:  # Limit to 100 to avoid prompt bloat
        node_info = f"{node.get('name', '')} ({node.get('type', '')}) - key: {node.get('key', '')}"
        if node.get('summary'):
            node_info += f" - {node.get('summary', '')[:100]}"
        existing_nodes_list.append(node_info)
    
    existing_nodes_text = "\n".join(existing_nodes_list)
    
    # Build node information text
    node_info_text = f"Name: {node_name}\nType: {node_type}"
    if node_summary:
        node_info_text += f"\nSummary: {node_summary}"
    if node_description:
        node_info_text += f"\nDescription: {node_description}"
    
    prompt = f"""{system_context}

Analyze the following new node and identify potential relationships with existing nodes in the graph.

NEW NODE:
{node_info_text}
Key: {node_key}

EXISTING NODES IN GRAPH:
{existing_nodes_text}

Based on the new node's information, identify relationships it might have with existing nodes. Consider:
- Direct connections mentioned in the description/summary
- Logical relationships based on entity types
- Similar names or entities that might be related
- Contextual connections based on the investigation

{relationship_guidance}

Return ONLY valid JSON with this exact structure (no markdown, no explanation):

{{
  "relationships": [
    {{
      "from_key": "source_node_key",
      "to_key": "target_node_key",
      "type": "RELATIONSHIP_TYPE",
      "notes": "Brief explanation of the relationship"
    }}
  ]
}}

IMPORTANT:
- Use the exact keys from the existing nodes list above
- The from_key should be the new node's key ({node_key}) or an existing node's key
- The to_key should be an existing node's key or the new node's key
- Only suggest relationships that make logical sense
- If no relationships are found, return an empty relationships array
"""
    
    try:
        response = call_llm(prompt, json_mode=True, temperature=temperature)
        result = parse_json_response(response)
        relationships = result.get("relationships", [])
        
        # Validate relationships - ensure keys exist
        valid_relationships = []
        existing_keys = {node.get('key') for node in existing_nodes}
        existing_keys.add(node_key)  # Include the new node's key
        
        for rel in relationships:
            from_key = rel.get("from_key", "").strip()
            to_key = rel.get("to_key", "").strip()
            
            # Validate that both keys exist (either in existing nodes or is the new node)
            if from_key in existing_keys and to_key in existing_keys:
                valid_relationships.append({
                    "from_key": from_key,
                    "to_key": to_key,
                    "type": rel.get("type", "RELATED_TO"),
                    "notes": rel.get("notes", "")
                })
        
        return valid_relationships
    except Exception as e:
        print(f"Error analyzing relationships: {e}")
        return []

