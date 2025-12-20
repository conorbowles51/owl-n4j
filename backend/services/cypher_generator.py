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
        
        # Escape node type label if it contains special characters
        escaped_type = node_type.replace("`", "``") if "`" in node_type else node_type
        
        # Escape node key for use in Cypher string
        escaped_key = node_key.replace("\\", "\\\\").replace("'", "\\'")
        
        # Create MERGE statement
        cypher_queries.append(
            f"MERGE (n:`{escaped_type}` {{key: '{escaped_key}'}})\n"
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
        
        # Escape relationship type if it contains special characters
        escaped_rel_type = rel_type.replace("`", "``") if "`" in rel_type else rel_type
        
        # Escape keys for use in Cypher strings
        escaped_source_key = source_key.replace("\\", "\\\\").replace("'", "\\'")
        escaped_target_key = target_key.replace("\\", "\\\\").replace("'", "\\'")
        
        # Format properties for Cypher
        if rel_properties:
            props_str = format_properties(rel_properties)
            cypher_queries.append(
                f"MATCH (a {{key: '{escaped_source_key}'}}), (b {{key: '{escaped_target_key}'}})\n"
                f"MERGE (a)-[r:`{escaped_rel_type}`]->(b)\n"
                f"SET r = {props_str}"
            )
        else:
            cypher_queries.append(
                f"MATCH (a {{key: '{escaped_source_key}'}}), (b {{key: '{escaped_target_key}'}})\n"
                f"MERGE (a)-[:`{escaped_rel_type}`]->(b)"
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
        # Escape property key if it contains special characters or is not a valid identifier
        # Cypher property keys should be valid identifiers or quoted
        if not key or not isinstance(key, str):
            continue  # Skip invalid keys
        
        # Quote key if it contains special characters or starts with a number
        if not key.replace("_", "").replace("-", "").isalnum() or key[0].isdigit():
            escaped_key = f"`{key.replace('`', '``')}`"  # Escape backticks in key
        else:
            escaped_key = key
        
        # Escape problematic characters in string values so generated Cypher
        # is always syntactically valid, even when the text contains quotes
        # or newlines.
        if isinstance(value, str):
            # More aggressive escaping for strings
            escaped_value = (
                value.replace("\\", "\\\\")   # escape backslashes first
                     .replace("'", "\\'")     # escape single quotes
                     .replace("\n", "\\n")    # normalise newlines
                     .replace("\r", "")       # drop CRs to avoid '\r' issues
                     .replace("\t", "\\t")    # escape tabs
                     .replace("\0", "")       # remove null bytes
            )
            formatted_props.append(f"{escaped_key}: '{escaped_value}'")
        elif isinstance(value, (int, float)):
            # For numeric values, ensure they're properly formatted
            # Handle special float values
            if isinstance(value, float):
                if value != value:  # NaN
                    formatted_props.append(f"{escaped_key}: null")
                elif value == float('inf'):
                    formatted_props.append(f"{escaped_key}: null")
                elif value == float('-inf'):
                    formatted_props.append(f"{escaped_key}: null")
                else:
                    formatted_props.append(f"{escaped_key}: {value}")
            else:
                formatted_props.append(f"{escaped_key}: {value}")
        elif isinstance(value, bool):
            formatted_props.append(f"{escaped_key}: {str(value).lower()}")
        elif value is None:
            formatted_props.append(f"{escaped_key}: null")
        elif isinstance(value, (list, dict)):
            # For complex types, convert to JSON string with proper escaping
            import json
            try:
                json_str = json.dumps(value, ensure_ascii=False)
                # Escape for Cypher string
                escaped_json = (
                    json_str.replace("\\", "\\\\")
                           .replace("'", "\\'")
                           .replace("\n", "\\n")
                           .replace("\r", "")
                )
                formatted_props.append(f"{escaped_key}: '{escaped_json}'")
            except (TypeError, ValueError):
                # If JSON serialization fails, skip this property
                continue
        else:
            # Fallback: convert to string with aggressive escaping
            str_value = str(value)
            escaped_value = (
                str_value.replace("\\", "\\\\")
                        .replace("'", "\\'")
                        .replace("\n", "\\n")
                        .replace("\r", "")
                        .replace("\t", "\\t")
                        .replace("\0", "")
            )
            formatted_props.append(f"{escaped_key}: '{escaped_value}'")
    
    return "{" + ", ".join(formatted_props) + "}"

