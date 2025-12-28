/**
 * Utility functions for calculating and applying Cypher query deltas
 */

/**
 * Extract CREATE/MERGE statements from Cypher queries
 * Returns an array of complete statements (including SET clauses)
 */
export function extractCreateStatements(cypher) {
  if (!cypher) return [];
  
  const queries = cypher.split('\n\n').map(q => q.trim()).filter(q => q);
  const createStatements = [];
  
  for (const query of queries) {
    // Match MERGE statements (the codebase uses MERGE, not CREATE)
    // Include the full statement including SET clauses
    if (query.includes('MERGE') || query.includes('CREATE')) {
      // Take the entire query as one statement (they're separated by \n\n)
      createStatements.push(query);
    }
  }
  
  return createStatements;
}

/**
 * Extract DELETE/DETACH DELETE statements from Cypher queries
 */
export function extractDeleteStatements(cypher) {
  if (!cypher) return [];
  
  const queries = cypher.split('\n\n').map(q => q.trim()).filter(q => q);
  const deleteStatements = [];
  
  for (const query of queries) {
    // Match DELETE and DETACH DELETE statements
    const deletePattern = /(DETACH\s+)?DELETE\s+[^;]+/gi;
    let match;
    
    while ((match = deletePattern.exec(query)) !== null) {
      deleteStatements.push(match[0].trim());
    }
  }
  
  return deleteStatements;
}

/**
 * Extract node identifiers from a CREATE/MERGE statement
 * Returns a set of node keys/identifiers that would be created
 * Based on the pattern: MERGE (n:`Label` {key: 'value'})
 */
export function extractNodeIdentifiers(createStatement) {
  const identifiers = new Set();
  
  // Match patterns like: MERGE (n:`Label` {key: 'value'})
  // The key is in the properties: {key: 'value'}
  const keyPattern = /\{key\s*:\s*['"]([^'"]+)['"]/i;
  const keyMatch = createStatement.match(keyPattern);
  if (keyMatch) {
    identifiers.add(keyMatch[1]);
  }
  
  // Also try to match in SET clauses: SET n = {key: 'value', ...}
  const setPattern = /SET\s+\w+\s*=\s*\{[^}]*key\s*:\s*['"]([^'"]+)['"]/i;
  const setMatch = createStatement.match(setPattern);
  if (setMatch) {
    identifiers.add(setMatch[1]);
  }
  
  return identifiers;
}

/**
 * Calculate delta between two Cypher query sets
 * Returns { toAdd: [...], toRemove: [...], newDeletes: [...] }
 */
export function calculateCypherDelta(oldCypher, newCypher) {
  if (!oldCypher || !newCypher) {
    return {
      toAdd: newCypher ? extractCreateStatements(newCypher) : [],
      toRemove: [],
      newDeletes: [],
      isFullReload: true, // If we don't have old Cypher, need full reload
    };
  }
  
  const oldCreates = extractCreateStatements(oldCypher);
  const newCreates = extractCreateStatements(newCypher);
  const newDeletes = extractDeleteStatements(newCypher);
  
  // Extract node keys from old and new statements
  const oldNodeKeys = new Set();
  oldCreates.forEach(stmt => {
    const ids = extractNodeIdentifiers(stmt);
    ids.forEach(id => oldNodeKeys.add(id));
  });
  
  const newNodeKeys = new Set();
  newCreates.forEach(stmt => {
    const ids = extractNodeIdentifiers(stmt);
    ids.forEach(id => newNodeKeys.add(id));
  });
  
  // Find what's new (statements that create nodes not in old graph)
  const toAdd = newCreates.filter(stmt => {
    const stmtKeys = extractNodeIdentifiers(stmt);
    // If any node key in this statement is new, include it
    return Array.from(stmtKeys).some(key => !oldNodeKeys.has(key));
  });
  
  // Find what's removed (node keys in old but not in new)
  const toRemove = Array.from(oldNodeKeys).filter(key => !newNodeKeys.has(key));
  
  // Also check for relationship changes by comparing full statements
  // If a statement has the same node keys but different structure, it might be updated
  const oldStmtMap = new Map();
  oldCreates.forEach(stmt => {
    const keys = extractNodeIdentifiers(stmt);
    keys.forEach(key => {
      if (!oldStmtMap.has(key)) {
        oldStmtMap.set(key, stmt);
      }
    });
  });
  
  // Find statements that might have been updated (same keys but different content)
  const updated = newCreates.filter(stmt => {
    const stmtKeys = extractNodeIdentifiers(stmt);
    return Array.from(stmtKeys).some(key => {
      const oldStmt = oldStmtMap.get(key);
      return oldStmt && oldStmt !== stmt && oldStmt.trim() !== stmt.trim();
    });
  });
  
  // Include updated statements in toAdd (they'll be re-executed with MERGE, which updates)
  toAdd.push(...updated);
  
  return {
    toAdd: [...new Set(toAdd)], // Remove duplicates
    toRemove,
    newDeletes,
    isFullReload: false,
  };
}

/**
 * Build incremental Cypher queries from delta
 * Returns an array of queries to execute
 */
export function buildIncrementalQueries(delta) {
  const queries = [];
  
  // Add new nodes/relationships
  if (delta.toAdd.length > 0) {
    // Group CREATE statements into batches
    const batchSize = 10;
    for (let i = 0; i < delta.toAdd.length; i += batchSize) {
      const batch = delta.toAdd.slice(i, i + batchSize);
      queries.push(batch.join('\n'));
    }
  }
  
  // Add delete statements
  if (delta.newDeletes && delta.newDeletes.length > 0) {
    queries.push(...delta.newDeletes);
  }
  
  // Remove nodes that are no longer in the new version
  if (delta.toRemove.length > 0) {
    // Build DELETE queries for removed nodes
    // Use DETACH DELETE to remove nodes and their relationships
    // Escape keys to prevent injection
    const deleteQueries = delta.toRemove.map(id => {
      const escapedId = id.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
      return `MATCH (n {key: '${escapedId}'}) DETACH DELETE n`;
    });
    queries.push(...deleteQueries);
  }
  
  return queries;
}

