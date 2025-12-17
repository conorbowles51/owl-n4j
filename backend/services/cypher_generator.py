"""
Cypher Generator Service

Generates Cypher queries to recreate a graph from node and relationship data.
"""

from typing import Dict, List


def generate_cypher_from_graph(graph_data: Dict) -> str:
    """
    Generate Cypher queries to recreate a graph.
    
    Args:
        graph_data: Dict with 'nodes' and 'links' arrays
        
    Returns:
        String containing Cypher queries
    """
    nodes = graph_data.get("nodes", [])
    links = graph_data.get("links", [])
    
    cypher_queries = []
    
    # Generate node creation queries
    # Use MERGE to avoid duplicates if nodes already exist
    for node in nodes:
        node_key = node.get("key")
        if not node_key:
            continue
            
        node_type = node.get("type", "Node")
        node_name = node.get("name", node_key)
        node_id = node.get("id", node_key)
        
        # Get all properties
        properties = node.get("properties", {})
        if not isinstance(properties, dict):
            properties = {}
        
        # Ensure required properties are set
        properties["key"] = node_key
        properties["id"] = node_id
        properties["name"] = node_name
        
        # Add optional properties if they exist
        if node.get("summary"):
            properties["summary"] = node.get("summary")
        if node.get("notes"):
            properties["notes"] = node.get("notes")
        
        # Format properties for Cypher
        props_str = format_properties(properties)
        
        # Create MERGE statement
        cypher_queries.append(
            f"MERGE (n:{node_type} {{key: '{node_key}'}})\n"
            f"SET n = {props_str}"
        )
    
    # Generate relationship creation queries
    for link in links:
        source_key = link.get("source")
        target_key = link.get("target")
        rel_type = link.get("type", "RELATED_TO")
        
        if not source_key or not target_key:
            continue
        
        # Get relationship properties
        rel_properties = link.get("properties", {})
        if not isinstance(rel_properties, dict):
            rel_properties = {}
        
        # Format properties for Cypher
        if rel_properties:
            props_str = format_properties(rel_properties)
            cypher_queries.append(
                f"MATCH (a {{key: '{source_key}'}}), (b {{key: '{target_key}'}})\n"
                f"MERGE (a)-[r:{rel_type}]->(b)\n"
                f"SET r = {props_str}"
            )
        else:
            cypher_queries.append(
                f"MATCH (a {{key: '{source_key}'}}), (b {{key: '{target_key}'}})\n"
                f"MERGE (a)-[:{rel_type}]->(b)"
            )
    
    return "\n\n".join(cypher_queries)


def format_properties(properties: Dict) -> str:
    """
    Format a dictionary of properties as a Cypher property map.
    
    Args:
        properties: Dictionary of property key-value pairs
        
    Returns:
        String like "{key: 'value', num: 123}"
    """
    if not properties:
        return "{}"
    
    formatted_props = []
    for key, value in properties.items():
        # Escape single quotes in string values
        if isinstance(value, str):
            escaped_value = value.replace("'", "\\'").replace("\\", "\\\\")
            formatted_props.append(f"{key}: '{escaped_value}'")
        elif isinstance(value, (int, float)):
            formatted_props.append(f"{key}: {value}")
        elif isinstance(value, bool):
            formatted_props.append(f"{key}: {str(value).lower()}")
        elif value is None:
            formatted_props.append(f"{key}: null")
        elif isinstance(value, (list, dict)):
            # For complex types, convert to JSON string
            import json
            json_str = json.dumps(value).replace("'", "\\'")
            formatted_props.append(f"{key}: '{json_str}'")
        else:
            # Fallback: convert to string
            escaped_value = str(value).replace("'", "\\'").replace("\\", "\\\\")
            formatted_props.append(f"{key}: '{escaped_value}'")
    
    return "{" + ", ".join(formatted_props) + "}"

