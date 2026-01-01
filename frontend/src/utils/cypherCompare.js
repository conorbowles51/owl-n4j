/**
 * Utility functions for comparing Cypher queries
 */

/**
 * Normalize a Cypher query string for comparison
 * - Removes extra whitespace
 * - Normalizes line endings
 * - Sorts CREATE statements (if possible)
 */
export function normalizeCypher(cypher) {
  if (!cypher) return '';
  
  // Split by double newlines (query separator)
  const queries = cypher.split('\n\n').map(q => q.trim()).filter(q => q);
  
  // Normalize each query
  const normalized = queries.map(query => {
    // Remove extra whitespace
    let normalized = query.replace(/\s+/g, ' ').trim();
    
    // Remove comments
    normalized = normalized.replace(/\/\/.*$/gm, '');
    
    // Normalize quotes
    normalized = normalized.replace(/'/g, "'");
    
    return normalized;
  });
  
  // Sort queries for comparison (optional - might break if queries have dependencies)
  // For now, keep order but normalize each query
  return normalized.join('\n\n');
}

/**
 * Compare two Cypher query strings
 * Returns true if they are equivalent (after normalization)
 */
export function compareCypherQueries(cypher1, cypher2) {
  if (!cypher1 && !cypher2) return true;
  if (!cypher1 || !cypher2) return false;
  
  const normalized1 = normalizeCypher(cypher1);
  const normalized2 = normalizeCypher(cypher2);
  
  return normalized1 === normalized2;
}

/**
 * Extract unique identifiers from Cypher queries
 * This helps identify what nodes/relationships are being created
 */
export function extractCypherIdentifiers(cypher) {
  if (!cypher) return { nodes: new Set(), relationships: new Set() };
  
  const nodes = new Set();
  const relationships = new Set();
  
  // Match CREATE (n:Label {key: 'value'}) patterns
  const nodePattern = /CREATE\s*\(([^)]+)\)/gi;
  const relPattern = /CREATE\s*\([^)]+\)\s*-\[([^\]]+)\]\s*->\s*\([^)]+\)/gi;
  
  let match;
  while ((match = nodePattern.exec(cypher)) !== null) {
    // Extract node variable name (e.g., 'n' in (n:Label))
    const nodeVar = match[1].match(/^(\w+)/);
    if (nodeVar) {
      nodes.add(nodeVar[1]);
    }
  }
  
  while ((match = relPattern.exec(cypher)) !== null) {
    // Extract relationship variable name
    const relVar = match[1].match(/^(\w+)/);
    if (relVar) {
      relationships.add(relVar[1]);
    }
  }
  
  return { nodes, relationships };
}



