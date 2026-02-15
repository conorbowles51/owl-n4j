/**
 * API Service - handles all backend communication
 */

const API_BASE = '/api';

/**
 * Fetch wrapper with error handling
 */
async function fetchAPI(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
 
  const token = localStorage.getItem('authToken');

  const headers = {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };

  const config = {
    credentials: options.credentials || 'include',
    ...options,
    headers,
  };

  // Automatically set JSON content type unless a FormData body is provided
  if (!(config.body instanceof FormData) && !('Content-Type' in config.headers)) {
    config.headers['Content-Type'] = 'application/json';
  }

  // Stringify body if it's an object (backend will handle chunking for large snapshots)
  if (config.body && typeof config.body === 'object' && !(config.body instanceof FormData) && !(config.body instanceof String)) {
    try {
      config.body = JSON.stringify(config.body);
    } catch (err) {
      // If stringify fails due to size, let the backend handle it via chunking
      // For snapshots, the backend will automatically chunk large data
      if (err.message && (err.message.includes('Invalid string length') || err.message.includes('string length'))) {
        // For snapshot endpoints, we'll send the data in a way that allows backend chunking
        // For now, re-throw and let backend handle it
        throw new Error('Data is too large. The backend will attempt to chunk it automatically.');
      }
      throw err;
    }
  }

  // Add timeout to prevent hanging (5 minutes default, 10 seconds for login, 30 seconds for auth/me)
  const timeout = options.timeout || (endpoint.includes('/auth/login') ? 10000 : endpoint.includes('/auth/me') ? 30000 : 300000);
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);
  
  try {
    const response = await fetch(url, {
      ...config,
      signal: controller.signal,
    });
    
    clearTimeout(timeoutId);
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      // Handle FastAPI validation errors (422) - they have a specific format
      if (response.status === 422 && Array.isArray(error.detail)) {
        // Pydantic validation errors
        const validationErrors = error.detail.map(err => {
          const field = err.loc ? err.loc.join('.') : 'unknown';
          const msg = err.msg || 'validation error';
          return `${field}: ${msg}`;
        }).join(', ');
        throw new Error(`Validation error: ${validationErrors}`);
      }
      // Handle various error response formats
      const errorMessage = error.detail || error.message || error.error ||
        (typeof error === 'string' ? error : JSON.stringify(error)) ||
        `HTTP ${response.status}`;
      throw new Error(errorMessage);
    }

    // Handle 204 No Content responses (e.g., DELETE operations)
    if (response.status === 204) {
      return null;
    }

    return response.json();
  } catch (err) {
    clearTimeout(timeoutId);
    if (err.name === 'AbortError') {
      throw new Error(`Request timed out after ${timeout}ms. Please check that the backend server is running on port 8000 and try again.`);
    }
    if (err.message && (err.message.includes('Failed to fetch') || err.message.includes('NetworkError'))) {
      throw new Error('Cannot connect to the server. Please ensure the backend is running on port 8000.');
    }
    throw err;
  }
}

/**
 * Graph API
 */
export const graphAPI = {
  /**
   * Get full graph data for visualization
   * @param {Object} options - Filter options
   * @param {string} options.case_id - REQUIRED: Filter by case ID
   * @param {string} [options.start_date] - Filter start date (YYYY-MM-DD)
   * @param {string} [options.end_date] - Filter end date (YYYY-MM-DD)
   */
  getGraph: ({ case_id, start_date, end_date } = {}) => {
    const params = new URLSearchParams();
    params.append('case_id', case_id);
    if (start_date) params.append('start_date', start_date);
    if (end_date) params.append('end_date', end_date);

    return fetchAPI(`/graph?${params.toString()}`);
  },

  /**
   * Get details for a specific node
   * @param {string} key - Node key
   * @param {string} caseId - REQUIRED: Case ID for case-specific data
   */
  getNodeDetails: (key, caseId) => {
    const params = `?case_id=${encodeURIComponent(caseId)}`;
    return fetchAPI(`/graph/node/${encodeURIComponent(key)}${params}`);
  },

  /**
   * Get a node and its neighbours
   * @param {string} key - Node key
   * @param {number} [depth=1] - Depth of neighbourhood
   * @param {string} caseId - REQUIRED: Case ID for case-specific data
   */
  getNodeNeighbours: (key, depth = 1, caseId) => {
    const params = new URLSearchParams();
    params.append('depth', depth);
    params.append('case_id', caseId);
    return fetchAPI(`/graph/node/${encodeURIComponent(key)}/neighbours?${params.toString()}`);
  },

  /**
   * Search nodes
   * @param {string} query - Search query
   * @param {number} [limit=20] - Max results
   * @param {string} caseId - REQUIRED: Case ID for case-specific search
   */
  search: (query, limit = 20, caseId) => {
    const params = new URLSearchParams();
    params.append('q', query);
    params.append('limit', limit);
    params.append('case_id', caseId);
    return fetchAPI(`/graph/search?${params.toString()}`);
  },

  /**
   * Get graph summary
   * @param {string} caseId - REQUIRED: Case ID for case-specific summary
   */
  getSummary: (caseId) => {
    const params = `?case_id=${encodeURIComponent(caseId)}`;
    return fetchAPI(`/graph/summary${params}`);
  },

  /**
   * Get subgraph with shortest paths between selected nodes
   * @param {string} caseId - REQUIRED: Case ID for case-specific data
   * @param {string[]} nodeKeys - Array of node keys
   * @param {number} [maxDepth=10] - Maximum path depth
   */
  getShortestPaths: (caseId, nodeKeys, maxDepth = 10) =>
    fetchAPI('/graph/shortest-paths', {
      method: 'POST',
      body: JSON.stringify({
        case_id: caseId,
        node_keys: nodeKeys,
        max_depth: maxDepth,
      }),
    }),

  /**
   * Expand multiple nodes by N hops
   * @param {string} caseId - REQUIRED: Case ID for case-specific data
   * @param {string[]} nodeKeys - Array of node keys
   * @param {number} [depth=1] - Depth to expand
   */
  expandNodes: (caseId, nodeKeys, depth = 1) =>
    fetchAPI('/graph/expand-nodes', {
      method: 'POST',
      body: JSON.stringify({
        case_id: caseId,
        node_keys: nodeKeys,
        depth: depth,
      }),
    }),

  /**
   * Find similar entities for resolution
   */
  findSimilarEntities: (caseId, entityTypes = null, similarityThreshold = 0.7, maxResults = 1000) =>
    fetchAPI('/graph/find-similar-entities', {
      method: 'POST',
      body: JSON.stringify({
        case_id: caseId,
        entity_types: entityTypes,
        name_similarity_threshold: similarityThreshold,
        max_results: maxResults,
      }),
    }),

  /**
   * Find similar entities with streaming progress updates via SSE.
   * Use this for large cases that would otherwise timeout.
   *
   * @param {string} caseId - REQUIRED: Case ID to scan
   * @param {Object} options - Options object
   * @param {string[]|null} options.entityTypes - Entity types to filter (null for all)
   * @param {number} options.similarityThreshold - Minimum name similarity threshold (0-1)
   * @param {number} options.maxResults - Maximum number of results to return
   * @param {Object} callbacks - Callback functions for SSE events
   * @param {Function} callbacks.onStart - Called when scan starts with metadata
   * @param {Function} callbacks.onTypeStart - Called when starting a new entity type
   * @param {Function} callbacks.onProgress - Called with progress updates
   * @param {Function} callbacks.onTypeComplete - Called when an entity type is done
   * @param {Function} callbacks.onComplete - Called when scan finishes with all results
   * @param {Function} callbacks.onError - Called on error
   * @param {Function} callbacks.onCancelled - Called if request was cancelled
   * @returns {Function} Cancel function to abort the stream
   */
  findSimilarEntitiesStream: (caseId, options = {}, callbacks = {}) => {
    const {
      entityTypes = null,
      similarityThreshold = 0.7,
      maxResults = 1000,
    } = options;

    const {
      onStart,
      onTypeStart,
      onProgress,
      onTypeComplete,
      onComplete,
      onError,
      onCancelled,
    } = callbacks;

    const abortController = new AbortController();
    const token = localStorage.getItem('authToken');

    // Build query params
    const params = new URLSearchParams();
    params.append('case_id', caseId);
    if (entityTypes && entityTypes.length > 0) {
      params.append('entity_types', entityTypes.join(','));
    }
    params.append('name_similarity_threshold', similarityThreshold.toString());
    params.append('max_results', maxResults.toString());

    const url = `${API_BASE}/graph/find-similar-entities/stream?${params.toString()}`;

    // Start the fetch
    (async () => {
      try {
        const response = await fetch(url, {
          method: 'GET',
          headers: {
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          credentials: 'include',
          signal: abortController.signal,
        });

        if (!response.ok) {
          const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
          throw new Error(error.detail || `HTTP ${response.status}`);
        }

        // Read the stream
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        // IMPORTANT: Keep currentEvent and currentData outside the loop
        // so they persist across network chunks (SSE events may span multiple chunks)
        let currentEvent = null;
        let currentData = '';

        // Helper function to dispatch SSE events
        const dispatchEvent = (eventType, eventData) => {
          try {
            const data = JSON.parse(eventData);

            switch (eventType) {
              case 'start':
                onStart?.(data);
                break;
              case 'type_start':
                onTypeStart?.(data);
                break;
              case 'progress':
                onProgress?.(data);
                break;
              case 'type_complete':
                onTypeComplete?.(data);
                break;
              case 'complete':
                onComplete?.(data);
                break;
              case 'cancelled':
                onCancelled?.(data);
                break;
              case 'error':
                onError?.(new Error(data.message || 'Unknown error'));
                break;
            }
          } catch (parseError) {
            console.error('Failed to parse SSE data:', parseError);
          }
        };

        while (true) {
          const { done, value } = await reader.read();

          // Decode the chunk (even if done, there may be final data)
          buffer += decoder.decode(value, { stream: !done });

          // Parse SSE events from buffer
          const lines = buffer.split('\n');
          buffer = lines.pop() || ''; // Keep incomplete line in buffer

          for (const line of lines) {
            if (line.startsWith('event: ')) {
              currentEvent = line.slice(7).trim();
            } else if (line.startsWith('data: ')) {
              currentData = line.slice(6);
            } else if (line === '') {
              // Empty line signals end of event
              if (currentEvent && currentData) {
                dispatchEvent(currentEvent, currentData);
              }
              currentEvent = null;
              currentData = '';
            }
          }

          if (done) {
            // Process any remaining complete event in buffer before breaking
            if (buffer.trim()) {
              const finalLines = buffer.split('\n');
              for (const line of finalLines) {
                if (line.startsWith('event: ')) {
                  currentEvent = line.slice(7).trim();
                } else if (line.startsWith('data: ')) {
                  currentData = line.slice(6);
                }
              }
              // If we have a complete event, dispatch it
              if (currentEvent && currentData) {
                dispatchEvent(currentEvent, currentData);
              }
            }
            break;
          }
        }
      } catch (err) {
        if (err.name === 'AbortError') {
          onCancelled?.({ message: 'Request aborted' });
        } else {
          onError?.(err);
        }
      }
    })();

    // Return cancel function
    return () => {
      abortController.abort();
    };
  },

  /**
   * Merge two entities
   * @param {string} caseId - REQUIRED: Case ID for case-specific data
   * @param {string} sourceKey - Source node key
   * @param {string} targetKey - Target node key
   * @param {Object} mergedData - Merged data for the resulting entity
   */
  mergeEntities: (caseId, sourceKey, targetKey, mergedData) =>
    fetchAPI('/graph/merge-entities', {
      method: 'POST',
      body: JSON.stringify({
        case_id: caseId,
        source_key: sourceKey,
        target_key: targetKey,
        merged_data: mergedData,
      }),
    }),

  /**
   * Reject a merge pair as a false positive (not actually duplicates).
   * The pair will be filtered out from future similar-entities scans.
   * @param {string} caseId - REQUIRED: Case ID
   * @param {string} entityKey1 - First entity key
   * @param {string} entityKey2 - Second entity key
   */
  rejectMergePair: (caseId, entityKey1, entityKey2) =>
    fetchAPI('/graph/reject-merge', {
      method: 'POST',
      body: JSON.stringify({
        case_id: caseId,
        entity_key_1: entityKey1,
        entity_key_2: entityKey2,
      }),
    }),

  /**
   * Get all rejected merge pairs for a case
   * @param {string} caseId - REQUIRED: Case ID
   * @returns {Promise<{rejected_pairs: Array, total: number}>}
   */
  getRejectedMergePairs: (caseId) => {
    const params = `?case_id=${encodeURIComponent(caseId)}`;
    return fetchAPI(`/graph/rejected-merges${params}`);
  },

  /**
   * Undo a rejection (allow the pair to appear in future scans)
   * @param {string} rejectionId - ID of the rejection to undo
   */
  undoRejection: (rejectionId) =>
    fetchAPI(`/graph/rejected-merges/${encodeURIComponent(rejectionId)}`, {
      method: 'DELETE',
    }),

  /**
   * Delete a node and all its relationships
   * @param {string} nodeKey - Node key to delete
   * @param {string} caseId - REQUIRED: Case ID for case-specific data
   */
  deleteNode: (nodeKey, caseId) =>
    fetchAPI(`/graph/node/${encodeURIComponent(nodeKey)}?case_id=${encodeURIComponent(caseId)}`, {
      method: 'DELETE',
    }),

  /**
   * Get influential nodes using PageRank algorithm
   * @param {string} caseId - REQUIRED: Case ID for case-specific data
   * @param {string[]|null} [nodeKeys=null] - Node keys to include (null for all)
   * @param {number} [topN=20] - Number of top nodes to return
   * @param {number} [iterations=20] - PageRank iterations
   * @param {number} [dampingFactor=0.85] - PageRank damping factor
   */
  getPageRank: (caseId, nodeKeys = null, topN = 20, iterations = 20, dampingFactor = 0.85) =>
    fetchAPI('/graph/pagerank', {
      method: 'POST',
      body: JSON.stringify({
        case_id: caseId,
        node_keys: nodeKeys,
        top_n: topN,
        iterations: iterations,
        damping_factor: dampingFactor,
      }),
    }),

  /**
   * Get communities using Louvain modularity algorithm
   * @param {string} caseId - REQUIRED: Case ID for case-specific data
   * @param {string[]|null} [nodeKeys=null] - Node keys to include (null for all)
   * @param {number} [resolution=1.0] - Louvain resolution parameter
   * @param {number} [maxIterations=10] - Maximum iterations
   */
  getLouvainCommunities: (caseId, nodeKeys = null, resolution = 1.0, maxIterations = 10) =>
    fetchAPI('/graph/louvain', {
      method: 'POST',
      body: JSON.stringify({
        case_id: caseId,
        node_keys: nodeKeys,
        resolution: resolution,
        max_iterations: maxIterations,
      }),
    }),

  /**
   * Get nodes with highest betweenness centrality
   * @param {string} caseId - REQUIRED: Case ID for case-specific data
   * @param {string[]|null} [nodeKeys=null] - Node keys to include (null for all)
   * @param {number} [topN=20] - Number of top nodes to return
   * @param {boolean} [normalized=true] - Whether to normalize centrality values
   */
  getBetweennessCentrality: (caseId, nodeKeys = null, topN = 20, normalized = true) =>
    fetchAPI('/graph/betweenness-centrality', {
      method: 'POST',
      body: JSON.stringify({
        case_id: caseId,
        node_keys: nodeKeys,
        top_n: topN,
        normalized: normalized,
      }),
    }),

  // NOTE: loadCase, executeSingleQuery, executeBatchQueries, clearGraph, getLastGraph
  // have been removed as they're no longer needed with case_id-based graph isolation.
  // Data persists in Neo4j and is filtered by case_id instead of being cleared and reloaded.

  /**
   * Get all entity types in the graph with their counts
   * @param {string} caseId - REQUIRED: Case ID for case-specific data
   */
  getEntityTypes: (caseId) => {
    const params = `?case_id=${encodeURIComponent(caseId)}`;
    return fetchAPI(`/graph/entity-types${params}`);
  },

  /**
   * Create a new node in the graph
   * @param {Object} nodeData - Node data including name, type, description, summary, properties
   * @param {string} caseId - REQUIRED: Case ID to associate with the node
   */
  createNode: (nodeData, caseId) =>
    fetchAPI('/graph/create-node', {
      method: 'POST',
      body: JSON.stringify({
        name: nodeData.name,
        type: nodeData.type,
        description: nodeData.description,
        summary: nodeData.summary,
        properties: nodeData.properties,
        case_id: caseId,
      }),
    }),

  /**
   * Create relationships between nodes
   * @param {Array} relationships - Array of relationship data
   * @param {string} caseId - REQUIRED: Case ID to associate with the relationships
   */
  createRelationships: (relationships, caseId) =>
    fetchAPI('/graph/relationships', {
      method: 'POST',
      body: JSON.stringify({ relationships, case_id: caseId }),
    }),

  /**
   * Analyze relationships for a node
   */
  analyzeNodeRelationships: (nodeKey) =>
    fetchAPI(`/graph/analyze-relationships/${encodeURIComponent(nodeKey)}`, {
      method: 'POST',
    }),

  /**
   * Update node properties (name, summary, notes, and/or type-specific properties)
   */
  updateNode: (nodeKey, updates) => {
    // Separate standard fields from type-specific properties
    const standardFields = ['name', 'summary', 'notes'];
    const requestBody = {};
    const properties = {};
    
    // If updates has a nested 'properties' object, extract it first
    if (updates.properties && typeof updates.properties === 'object') {
      Object.assign(properties, updates.properties);
    }
    
    // Process top-level keys
    Object.keys(updates).forEach(key => {
      if (key === 'properties') {
        // Already handled above, skip
        return;
      }
      if (standardFields.includes(key)) {
        requestBody[key] = updates[key];
      } else {
        // Other top-level keys go into properties
        properties[key] = updates[key];
      }
    });
    
    // Add properties if there are any
    if (Object.keys(properties).length > 0) {
      requestBody.properties = properties;
    }
    
    return fetchAPI(`/graph/node/${encodeURIComponent(nodeKey)}`, {
      method: 'PUT',
      body: JSON.stringify(requestBody),
    });
  },

  /**
   * Get entities with geocoded locations for map display
   * @param {string} caseId - REQUIRED: Case ID for case-specific data
   * @param {Object} [options] - Filter options
   * @param {string} [options.types] - Comma-separated entity types to filter
   */
  getLocations: (caseId, { types } = {}) => {
    const params = new URLSearchParams();
    params.append('case_id', caseId);
    if (types) params.append('types', types);

    return fetchAPI(`/graph/locations?${params.toString()}`);
  },

  /**
   * Toggle pin status for a verified fact
   * @param {string} nodeKey - Node key
   * @param {number} factIndex - Index of the fact in verified_facts array
   * @param {boolean} pinned - Whether to pin (true) or unpin (false)
   * @param {string} caseId - REQUIRED: Case ID for case-specific data
   */
  pinFact: (nodeKey, factIndex, pinned, caseId) =>
    fetchAPI(`/graph/node/${encodeURIComponent(nodeKey)}/pin-fact?case_id=${encodeURIComponent(caseId)}`, {
      method: 'PUT',
      body: JSON.stringify({
        case_id: caseId,
        fact_index: factIndex,
        pinned: pinned,
      }),
    }),

  /**
   * Convert an AI insight to a verified fact
   * @param {string} nodeKey - Node key
   * @param {number} insightIndex - Index of the insight in ai_insights array
   * @param {string} username - Username of the verifying investigator
   * @param {string} caseId - REQUIRED: Case ID for case-specific data
   * @param {string} [sourceDoc] - Optional source document reference
   * @param {number} [page] - Optional page number
   */
  verifyInsight: (nodeKey, insightIndex, username, caseId, sourceDoc = null, page = null) =>
    fetchAPI(`/graph/node/${encodeURIComponent(nodeKey)}/verify-insight?case_id=${encodeURIComponent(caseId)}`, {
      method: 'POST',
      body: JSON.stringify({
        case_id: caseId,
        insight_index: insightIndex,
        username: username,
        source_doc: sourceDoc,
        page: page,
      }),
    }),
};

/**
 * Chat API
 */
export const chatAPI = {
  /**
   * Send a question to the AI
   */
  ask: (question, selectedKeys = null, model, provider, confidenceThreshold = null) => 
    fetchAPI('/chat', {
      method: 'POST',
      body: JSON.stringify({
        question,
        selected_keys: selectedKeys,
        model,
        provider,
        confidence_threshold: confidenceThreshold
      }),
      timeout: 600000, // 10 minutes for AI queries (large models may take time)
    }),

  /**
   * Get suggested questions
   */
  getSuggestions: (caseId, selectedKeys = null) =>
    fetchAPI('/chat/suggestions', {
      method: 'POST',
      body: JSON.stringify({
        case_id: caseId,
        selected_keys: selectedKeys,
      }),
    }),

  /**
   * Extract node keys from an AI answer
   */
  extractNodesFromAnswer: (answer) =>
    fetchAPI('/chat/extract-nodes', {
      method: 'POST',
      body: JSON.stringify({
        answer: answer,
      }),
      timeout: 300000, // 5 minutes for node extraction (uses LLM)
    }),
};

/**
 * Query API (advanced Cypher)
 */
export const queryAPI = {
  /**
   * Execute a Cypher query
   */
  execute: (query, params = null) => 
    fetchAPI('/query', {
      method: 'POST',
      body: JSON.stringify({
        query,
        params,
      }),
    }),
};

/**
 * Timeline API
 */
export const timelineAPI = {
  /**
   * Get timeline events
   * @param {Object} options - Filter options
   * @param {string} options.caseId - REQUIRED: Filter to events in this case
   * @param {string} [options.types] - Comma-separated event types
   * @param {string} [options.startDate] - Filter start date (YYYY-MM-DD)
   * @param {string} [options.endDate] - Filter end date (YYYY-MM-DD)
   */
  getEvents: async ({ caseId, types, startDate, endDate } = {}) => {
    const params = new URLSearchParams();
    params.append('case_id', caseId);
    if (types) params.append('types', types);
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);

    const response = await fetchAPI(`/timeline?${params.toString()}`);
    // The API returns { events: [...], total: ... }
    // Return the full response object so TimelineView can access both events and total
    return response;
  },

  /**
   * Get available event types
   */
  getEventTypes: () => fetchAPI('/timeline/types'),
};

/**
 * Financial API
 */
export const financialAPI = {
  /**
   * Get financial transactions with from/to entity resolution
   * @param {Object} options - Filter options
   * @param {string} options.caseId - REQUIRED: Case ID
   * @param {string} [options.types] - Comma-separated transaction types
   * @param {string} [options.startDate] - Filter start date (YYYY-MM-DD)
   * @param {string} [options.endDate] - Filter end date (YYYY-MM-DD)
   * @param {string} [options.categories] - Comma-separated categories
   */
  getTransactions: async ({ caseId, types, startDate, endDate, categories } = {}) => {
    const params = new URLSearchParams();
    params.append('case_id', caseId);
    if (types) params.append('types', types);
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    if (categories) params.append('categories', categories);
    return fetchAPI(`/financial?${params.toString()}`);
  },

  /**
   * Get financial summary statistics
   * @param {string} caseId - REQUIRED: Case ID
   */
  getSummary: (caseId) => {
    const params = new URLSearchParams();
    params.append('case_id', caseId);
    return fetchAPI(`/financial/summary?${params.toString()}`);
  },

  /**
   * Get transaction volume over time for chart data
   * @param {string} caseId - REQUIRED: Case ID
   */
  getVolume: (caseId) => {
    const params = new URLSearchParams();
    params.append('case_id', caseId);
    return fetchAPI(`/financial/volume?${params.toString()}`);
  },

  /**
   * Set financial category on a transaction
   * @param {string} nodeKey - Node key
   * @param {string} category - Category string
   * @param {string} caseId - REQUIRED: Case ID
   */
  categorize: (nodeKey, category, caseId) => {
    return fetchAPI(`/financial/categorize/${encodeURIComponent(nodeKey)}`, {
      method: 'PUT',
      body: JSON.stringify({ category, case_id: caseId }),
    });
  },

  /**
   * Batch categorize multiple transactions
   * @param {string[]} nodeKeys - Node keys
   * @param {string} category - Category string
   * @param {string} caseId - REQUIRED: Case ID
   */
  batchCategorize: (nodeKeys, category, caseId) => {
    return fetchAPI('/financial/batch-categorize', {
      method: 'PUT',
      body: JSON.stringify({ node_keys: nodeKeys, category, case_id: caseId }),
    });
  },

  /**
   * Set manual from/to entity override on a transaction
   * @param {string} nodeKey - Node key
   * @param {Object} data - From/to data
   * @param {string} data.caseId - REQUIRED: Case ID
   * @param {string} [data.fromKey] - From entity key
   * @param {string} [data.fromName] - From entity name
   * @param {string} [data.toKey] - To entity key
   * @param {string} [data.toName] - To entity name
   */
  setFromTo: (nodeKey, { caseId, fromKey, fromName, toKey, toName }) => {
    return fetchAPI(`/financial/from-to/${encodeURIComponent(nodeKey)}`, {
      method: 'PUT',
      body: JSON.stringify({
        case_id: caseId,
        from_key: fromKey,
        from_name: fromName,
        to_key: toKey,
        to_name: toName,
      }),
    });
  },

  /**
   * Update purpose, counterparty details, and/or notes on a transaction
   * @param {string} nodeKey - Node key
   * @param {Object} data - { caseId, purpose?, counterpartyDetails?, notes? }
   */
  updateDetails: (nodeKey, { caseId, purpose, counterpartyDetails, notes }) => {
    return fetchAPI(`/financial/details/${encodeURIComponent(nodeKey)}`, {
      method: 'PUT',
      body: JSON.stringify({
        case_id: caseId,
        purpose: purpose,
        counterparty_details: counterpartyDetails,
        notes: notes,
      }),
    });
  },

  /**
   * Batch set from or to entity on multiple transactions
   * @param {string[]} nodeKeys - Array of node keys
   * @param {Object} data - { caseId, fromKey?, fromName?, toKey?, toName? }
   */
  batchSetFromTo: (nodeKeys, { caseId, fromKey, fromName, toKey, toName }) => {
    return fetchAPI('/financial/batch-from-to', {
      method: 'PUT',
      body: JSON.stringify({
        node_keys: nodeKeys,
        case_id: caseId,
        from_key: fromKey,
        from_name: fromName,
        to_key: toKey,
        to_name: toName,
      }),
    });
  },

  /**
   * Get predefined + custom categories for a case
   * @param {string} caseId - REQUIRED: Case ID
   */
  getCategories: (caseId) => {
    const params = new URLSearchParams();
    params.append('case_id', caseId);
    return fetchAPI(`/financial/categories?${params.toString()}`);
  },

  /**
   * Create a custom financial category for a case
   * @param {string} name - Category name
   * @param {string} color - Hex color string
   * @param {string} caseId - REQUIRED: Case ID
   */
  createCategory: (name, color, caseId) => {
    return fetchAPI('/financial/categories', {
      method: 'POST',
      body: { name, color, case_id: caseId },
    });
  },
};

/**
 * Snapshots API
 */
export const snapshotsAPI = {
  /**
   * Create a new snapshot
   * Backend will automatically chunk large snapshots
   * If stringify fails due to size, uses chunked upload
   */
  create: async (snapshot) => {
    const snapshot_id = `snapshot_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    try {
      // Try normal upload first
      const bodyString = JSON.stringify(snapshot);
      return fetchAPI('/snapshots', {
        method: 'POST',
        body: bodyString,
      });
    } catch (err) {
      // If stringify fails due to size, use chunked upload
      if (err.message && (err.message.includes('Invalid string length') || err.message.includes('string length'))) {
        const timestamp = new Date().toISOString();
        const chunks = [];
        let chunkIndex = 0;
        
        // Chunk 0: Metadata + subgraph links + first batch of nodes
        const nodesPerChunk = 1000; // Start with reasonable size
        const nodes = snapshot.subgraph.nodes || [];
        const links = snapshot.subgraph.links || [];
        
        let nodeIndex = 0;
        let currentNodesPerChunk = nodesPerChunk;
        let retryCount = 0;
        const maxRetries = 20; // Prevent infinite loops
        
        while (nodeIndex < nodes.length && retryCount < maxRetries) {
          const chunkNodes = nodes.slice(nodeIndex, nodeIndex + currentNodesPerChunk);
          
          if (chunkNodes.length === 0) {
            // No more nodes to process
            break;
          }
          
          const chunkData = {
            name: snapshot.name,
            notes: snapshot.notes,
            subgraph: {
              nodes: chunkNodes,
              links: nodeIndex === 0 ? links : [], // Links only in first chunk
            },
            timestamp: timestamp,
            created_at: timestamp,
            // Include metadata in first chunk only
            ...(nodeIndex === 0 ? {
              ai_overview: snapshot.ai_overview,
              citations: snapshot.citations,
              case_id: snapshot.case_id,
              case_version: snapshot.case_version,
              case_name: snapshot.case_name,
            } : {}),
          };
          
          // Try to stringify this chunk
          try {
            JSON.stringify(chunkData);
            chunks.push(chunkData);
            nodeIndex += chunkNodes.length;
            chunkIndex++;
            // Reset chunk size and retry count for next iteration
            currentNodesPerChunk = nodesPerChunk;
            retryCount = 0;
          } catch {
            // This chunk is still too large, reduce size and retry
            currentNodesPerChunk = Math.max(1, Math.floor(currentNodesPerChunk / 2));
            retryCount++;
            // Don't increment nodeIndex, will retry with smaller chunk
          }
        }
        
        if (retryCount >= maxRetries) {
          throw new Error('Unable to chunk snapshot data. Individual nodes may be too large.');
        }
        
        // Add timeline in chunks if needed
        if (snapshot.timeline && snapshot.timeline.length > 0) {
          const eventsPerChunk = 500;
          for (let i = 0; i < snapshot.timeline.length; i += eventsPerChunk) {
            chunks.push({
              timeline: snapshot.timeline.slice(i, i + eventsPerChunk),
            });
            chunkIndex++;
          }
        }
        
        // Add overview
        if (snapshot.overview) {
          chunks.push({ overview: snapshot.overview });
          chunkIndex++;
        }
        
        // Add chat_history in chunks if needed
        if (snapshot.chat_history && snapshot.chat_history.length > 0) {
          const messagesPerChunk = 100;
          for (let i = 0; i < snapshot.chat_history.length; i += messagesPerChunk) {
            chunks.push({
              chat_history: snapshot.chat_history.slice(i, i + messagesPerChunk),
            });
            chunkIndex++;
          }
        }
        
        // Upload chunks sequentially
        for (let i = 0; i < chunks.length; i++) {
          const isLast = i === chunks.length - 1;
          try {
            await fetchAPI('/snapshots/upload-chunk', {
              method: 'POST',
              body: JSON.stringify({
                snapshot_id: snapshot_id,
                chunk_index: i,
                chunk_data: chunks[i],
                is_last_chunk: isLast,
              }),
            });
          } catch (chunkErr) {
            // If individual chunk is still too large, split it further
            if (chunkErr.message && chunkErr.message.includes('string length')) {
              // This shouldn't happen if we chunked properly, but handle it
              throw new Error('Snapshot data is extremely large. Please reduce the amount of data.');
            }
            throw chunkErr;
          }
        }
        
        // Return response similar to normal create
        return {
          id: snapshot_id,
          name: snapshot.name,
          notes: snapshot.notes,
          timestamp: timestamp,
          node_count: snapshot.subgraph.nodes.length,
          link_count: snapshot.subgraph.links.length,
          timeline_count: snapshot.timeline?.length || 0,
          created_at: timestamp,
          ai_overview: snapshot.ai_overview, // Include AI overview
          case_id: snapshot.case_id,
          case_version: snapshot.case_version,
          case_name: snapshot.case_name,
        };
      }
      throw err;
    }
  },

  /**
   * List all snapshots
   */
  list: () => fetchAPI('/snapshots'),

  /**
   * Get a specific snapshot
   */
  get: (snapshotId) => fetchAPI(`/snapshots/${encodeURIComponent(snapshotId)}`),

  /**
   * Delete a snapshot
   */
  delete: (snapshotId) => 
    fetchAPI(`/snapshots/${encodeURIComponent(snapshotId)}`, {
      method: 'DELETE',
    }),

  /**
   * Delete all snapshots for the current user
   */
  deleteAll: () =>
    fetchAPI('/snapshots', {
      method: 'DELETE',
    }),

  /**
   * Restore a snapshot from case data
   */
  restore: (snapshotData) =>
    fetchAPI('/snapshots/restore', {
      method: 'POST',
      body: JSON.stringify(snapshotData),
    }),
};

/**
 * Cases API
 *
 * Note: The new PostgreSQL backend returns cases with different field names:
 * - 'title' instead of 'name'
 * - 'description' field added
 * - 'created_by_user_id' and 'owner_user_id' fields added
 */
export const casesAPI = {
  /**
   * Create a new case (new PostgreSQL endpoint)
   * @param {Object} data - Case data
   * @param {string} data.title - Case title
   * @param {string} [data.description] - Optional case description
   */
  create: (data) =>
    fetchAPI('/cases', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /**
   * Save a new version of a case (legacy endpoint)
   */
  save: (caseData) =>
    fetchAPI('/cases', {
      method: 'POST',
      body: JSON.stringify(caseData),
    }),

  /**
   * List all cases
   * Returns { cases: [...], total: number } from new endpoint
   * @param {string} viewMode - 'my_cases' (default) or 'all_cases' (super admins only)
   */
  list: (viewMode = 'my_cases') => fetchAPI(`/cases?view_mode=${viewMode}`, {
    timeout: 60000, // 60 seconds for cases (may have large snapshot data)
  }),

  /**
   * Get a specific case with all versions
   */
  get: (caseId) => fetchAPI(`/cases/${encodeURIComponent(caseId)}`),

  /**
   * Update case metadata (new PostgreSQL endpoint)
   * @param {string} caseId - Case ID
   * @param {Object} data - Update data
   * @param {string} [data.title] - New title
   * @param {string} [data.description] - New description
   */
  update: (caseId, data) =>
    fetchAPI(`/cases/${encodeURIComponent(caseId)}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  /**
   * Get a specific version of a case
   */
  getVersion: (caseId, version) =>
    fetchAPI(`/cases/${encodeURIComponent(caseId)}/versions/${version}`),

  /**
   * Delete a case
   */
  delete: (caseId) =>
    fetchAPI(`/cases/${encodeURIComponent(caseId)}`, {
      method: 'DELETE',
    }),

  /**
   * Backup a case - returns a blob URL for download
   * @param {string} caseId - Case ID to backup
   * @param {boolean} includeFiles - Whether to include file contents
   * @returns {Promise<Blob>} - Backup ZIP file as blob
   */
  backup: async (caseId, includeFiles = false) => {
    const url = `/api/cases/${encodeURIComponent(caseId)}/backup?include_files=${includeFiles}`;
    const token = localStorage.getItem('authToken');
    
    const headers = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    
    const response = await fetch(`${API_BASE}${url}`, {
      method: 'GET',
      headers,
      credentials: 'include',
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Failed to create backup' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    
    return await response.blob();
  },

  /**
   * Restore a case from backup file
   * @param {string} caseId - Case ID to restore to
   * @param {File} backupFile - Backup ZIP file
   * @param {boolean} overwrite - Whether to overwrite existing case
   * @returns {Promise<Object>} - Restore results
   */
  restore: async (caseId, backupFile, overwrite = false) => {
    const formData = new FormData();
    formData.append('backup_file', backupFile);
    
    const url = `/api/cases/${encodeURIComponent(caseId)}/restore?overwrite=${overwrite}`;
    return fetchAPI(url, {
      method: 'POST',
      body: formData,
    });
  },
};

/**
 * Chat History API
 */
export const chatHistoryAPI = {
  /**
   * Create a new chat history
   */
  create: (chatData) =>
    fetchAPI('/chat-history', {
      method: 'POST',
      body: JSON.stringify(chatData),
    }),

  /**
   * List all chat histories for the current user
   */
  list: () => fetchAPI('/chat-history'),

  /**
   * Get a specific chat history
   */
  get: (chatId) => fetchAPI(`/chat-history/${encodeURIComponent(chatId)}`),

  /**
   * Delete a chat history
   */
  delete: (chatId) =>
    fetchAPI(`/chat-history/${encodeURIComponent(chatId)}`, {
      method: 'DELETE',
    }),

  /**
   * Get chat histories by snapshot ID
   */
  getBySnapshot: (snapshotId) =>
    fetchAPI(`/chat-history/by-snapshot/${encodeURIComponent(snapshotId)}`),
};

/**
 * Evidence API
 */
export const evidenceAPI = {
  /**
   * Get document summary by filename
   * @param {string} filename - Document filename
   * @param {string} caseId - Case ID
   */
  getSummary: (filename, caseId) => {
    return fetchAPI(`/evidence/summary/${encodeURIComponent(filename)}?case_id=${encodeURIComponent(caseId)}`);
  },
  /**
   * Get folder summary by folder name
   * @param {string} folderName - Folder name (e.g., "00000128")
   * @param {string} caseId - Case ID
   */
  getFolderSummary: (folderName, caseId) => {
    return fetchAPI(`/evidence/folder-summary/${encodeURIComponent(folderName)}?case_id=${encodeURIComponent(caseId)}`);
  },

  /**
   * Get wiretap Spanish transcription and English translation for a folder, when available.
   * @param {string} folderName - Wiretap folder name (e.g., "00000128")
   * @param {string} caseId - Case ID
   */
  getTranscriptionTranslation: (folderName, caseId) => {
    const params = new URLSearchParams();
    params.append('case_id', caseId);
    params.append('folder_name', folderName);
    return fetchAPI(`/evidence/transcription-translation?${params.toString()}`);
  },
  /**
   * List evidence files for a case
   */
  list: (caseId, status = null) => {
    const params = new URLSearchParams();
    if (caseId) params.append('case_id', caseId);
    if (status) params.append('status', status);
    const qs = params.toString();
    return fetchAPI(`/evidence${qs ? `?${qs}` : ''}`);
  },

  /**
   * Find all duplicate files by SHA256 hash
   */
  findDuplicates: (sha256) =>
    fetchAPI(`/evidence/duplicates/${encodeURIComponent(sha256)}`),

  /**
   * Check if a folder is suitable for wiretap processing
   */
  checkWiretapFolder: (caseId, folderPath) => {
    const params = new URLSearchParams();
    params.append('case_id', caseId);
    params.append('folder_path', folderPath);
    return fetchAPI(`/evidence/wiretap/check?${params.toString()}`);
  },

  /**
   * Process wiretap folders
   */
  processWiretapFolders: (caseId, folderPaths, whisperModel = 'base') =>
    fetchAPI('/evidence/wiretap/process', {
      method: 'POST',
      body: JSON.stringify({
        case_id: caseId,
        folder_paths: folderPaths,
        whisper_model: whisperModel,
      }),
      timeout: 60000, // 60 seconds for wiretap processing (folder validation may take time)
    }),

  /**
   * List all processed wiretap folders
   */
  listProcessedWiretaps: (caseId = null) => {
    const params = new URLSearchParams();
    if (caseId) params.append('case_id', caseId);
    const qs = params.toString();
    return fetchAPI(`/evidence/wiretap/processed${qs ? `?${qs}` : ''}`);
  },

  /**
   * List files in a folder for profile creation
   */
  listFolderFiles: (caseId, folderPath) => {
    const params = new URLSearchParams();
    params.append('case_id', caseId);
    params.append('folder_path', folderPath);
    return fetchAPI(`/evidence/folder/files?${params.toString()}`);
  },

  /**
   * Generate a folder processing profile from natural language instructions
   */
  generateFolderProfile: (request) =>
    fetchAPI('/evidence/folder/profile/generate', {
      method: 'POST',
      body: JSON.stringify(request),
      timeout: 100000, // 100 seconds - slightly longer than backend 90s timeout
    }),

  /**
   * Test a folder processing profile on a folder
   */
  testFolderProfile: (request) =>
    fetchAPI('/evidence/folder/profile/test', {
      method: 'POST',
      body: JSON.stringify(request),
      timeout: 60000,
    }),

  /**
   * Upload one or more evidence files for a case
   * Returns either {files: [...]} for synchronous uploads or {task_id: "...", message: "..."} for background uploads
   */
  upload: (caseId, files) => {
    const formData = new FormData();
    formData.append('case_id', caseId);
    Array.from(files).forEach((file) => {
      formData.append('files', file);
    });
    return fetchAPI('/evidence/upload', {
      method: 'POST',
      body: formData,
    });
  },

  /**
   * Upload a folder of files (or folder of folders) for a case
   * Uses webkitdirectory to preserve folder structure
   */
  uploadFolder: (caseId, files) => {
    const formData = new FormData();
    formData.append('case_id', caseId);
    formData.append('is_folder', 'true');
    Array.from(files).forEach((file, index) => {
      // Append file with relative path as third parameter to FormData
      const relativePath = file.webkitRelativePath || file.name;
      formData.append('files', file, relativePath);
      // Also send relative path as separate field for easier parsing
      formData.append(`file_path_${index}`, relativePath);
    });
    return fetchAPI('/evidence/upload', {
      method: 'POST',
      body: formData,
    });
  },

  /**
   * Process selected evidence files synchronously
   * @param {string} caseId - Case ID
   * @param {string[]} fileIds - Array of file IDs to process
   * @param {string} [profile] - Optional LLM profile name (e.g., "fraud", "generic")
   */
  process: (caseId, fileIds, profile = null) =>
    fetchAPI('/evidence/process', {
      method: 'POST',
      body: JSON.stringify({
        case_id: caseId,
        file_ids: fileIds,
        profile: profile,
      }),
    }),

  /**
   * Process selected evidence files in the background (returns task_id)
   * @param {string} caseId - Case ID
   * @param {string[]} fileIds - Array of file IDs to process
   * @param {string} [profile] - Optional LLM profile name (e.g., "fraud", "generic")
   * @param {number} [maxWorkers] - Maximum parallel files to process (default: 4)
   */
  processBackground: (caseId, fileIds, profile = null, maxWorkers = 4) =>
    fetchAPI('/evidence/process/background', {
      method: 'POST',
      body: JSON.stringify({
        case_id: caseId,
        file_ids: fileIds,
        profile: profile,
        max_workers: maxWorkers,
      }),
    }),

  /**
   * Fetch recent ingestion logs for a case.
   */
  logs: (caseId, limit = 200) => {
    const params = new URLSearchParams();
    if (caseId) params.append('case_id', caseId);
    if (limit) params.append('limit', String(limit));
    const qs = params.toString();
    return fetchAPI(`/evidence/logs${qs ? `?${qs}` : ''}`);
  },

  /**
   * Get the file URL for viewing a document
   * Returns the URL that can be used to fetch/display the file
   * @param {string} evidenceId - Evidence ID
   */
  getFileUrl: (evidenceId) => {
    const token = localStorage.getItem('authToken');
    // Return the API URL - the DocumentViewer will use this directly
    return `${API_BASE}/evidence/${encodeURIComponent(evidenceId)}/file`;
  },

  /**
   * Find evidence by filename
   * @param {string} filename - Original filename to search for
   * @param {string} [caseId] - Optional case ID to filter by
   */
  findByFilename: (filename, caseId = null) => {
    const params = new URLSearchParams();
    if (caseId) params.append('case_id', caseId);
    const qs = params.toString();
    return fetchAPI(`/evidence/by-filename/${encodeURIComponent(filename)}${qs ? `?${qs}` : ''}`);
  },
};

/**
 * Profiles API
 */
export const profilesAPI = {
  /**
   * List all available LLM profiles
   */
  list: () => fetchAPI('/profiles'),

  /**
   * Get detailed information about a specific profile
   * @param {string} profileName - Profile name (e.g., "fraud", "generic")
   */
  get: (profileName) => fetchAPI(`/profiles/${encodeURIComponent(profileName)}`),

  /**
   * Create or update a profile
   * @param {Object} profileData - Profile data
   */
  save: (profileData) =>
    fetchAPI('/profiles', {
      method: 'POST',
      body: JSON.stringify(profileData),
    }),

  /**
   * Delete a profile
   * @param {string} profileName - Profile name to delete
   */
  delete: (profileName) =>
    fetchAPI(`/profiles/${encodeURIComponent(profileName)}`, {
      method: 'DELETE',
    }),
};

/**
 * File System API
 */
export const filesystemAPI = {
  /**
   * List files and directories in a given path for a case
   * @param {string} caseId - Case ID
   * @param {string} [path] - Relative path from case root (e.g., "subfolder" or "subfolder/nested")
   * @returns {Promise<{items: Array, current_path: string, root_path: string}>}
   */
  list: (caseId, path = null) => {
    const params = new URLSearchParams();
    params.append('case_id', caseId);
    if (path) params.append('path', path);
    return fetchAPI(`/filesystem/list?${params.toString()}`);
  },

  /**
   * Read a text file's contents
   * @param {string} caseId - Case ID
   * @param {string} path - Relative path from case root (e.g., "file.txt" or "subfolder/file.txt")
   * @returns {Promise<{path: string, content: string, size: number}>}
   */
  readFile: (caseId, path) => {
    const params = new URLSearchParams();
    params.append('case_id', caseId);
    params.append('path', path);
    return fetchAPI(`/filesystem/read?${params.toString()}`);
  },
};

/**
 * Authentication API
 */
export const authAPI = {
  login: ({ username, password }) =>
    fetchAPI('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
      timeout: 10000, // 10 second timeout for login
    }),

  logout: () =>
    fetchAPI('/auth/logout', {
      method: 'POST',
      timeout: 5000, // 5 second timeout for logout
    }),

  me: () =>
    fetchAPI('/auth/me', {
      method: 'GET',
      timeout: 5000, // 5 second timeout for me
    }),
};

/**
 * Setup API - for first-time application setup
 */
export const setupAPI = {
  /**
   * Check if the application needs initial setup
   * Returns { needs_setup: boolean }
   */
  getStatus: () =>
    fetchAPI('/setup/status', {
      method: 'GET',
      timeout: 5000,
    }),

  /**
   * Create the initial super_admin user
   * Only works when no users exist in the database
   * @param {Object} userData - User data
   * @param {string} userData.email - User email
   * @param {string} userData.name - User name
   * @param {string} userData.password - User password (min 8 chars)
   */
  createInitialUser: ({ email, name, password }) =>
    fetchAPI('/setup/initial-user', {
      method: 'POST',
      body: JSON.stringify({ email, name, password }),
      timeout: 10000,
    }),
};

/**
 * Background Tasks API
 */
export const backgroundTasksAPI = {
  /**
   * List background tasks
   */
  list: (owner = null, caseId = null, status = null, limit = 100) => {
    const params = new URLSearchParams();
    if (owner) params.append('owner', owner);
    if (caseId) params.append('case_id', caseId);
    if (status) params.append('status', status);
    if (limit) params.append('limit', String(limit));
    const qs = params.toString();
    return fetchAPI(`/background-tasks${qs ? `?${qs}` : ''}`);
  },

  /**
   * Get a specific task by ID
   */
  get: (taskId) => fetchAPI(`/background-tasks/${encodeURIComponent(taskId)}`),

  /**
   * Delete a task
   */
  delete: (taskId) =>
    fetchAPI(`/background-tasks/${encodeURIComponent(taskId)}`, {
      method: 'DELETE',
    }),
};

/**
 * Cost Ledger API
 */
export const costLedgerAPI = {
  /**
   * Get cost ledger records
   */
  getLedger: (params = {}) => {
    const queryParams = new URLSearchParams();
    Object.keys(params).forEach(key => {
      if (params[key] !== null && params[key] !== undefined && params[key] !== '') {
        queryParams.append(key, params[key]);
      }
    });
    return fetchAPI(`/cost-ledger?${queryParams.toString()}`);
  },

  /**
   * Get cost summary
   */
  getSummary: (params = {}) => {
    const queryParams = new URLSearchParams();
    Object.keys(params).forEach(key => {
      if (params[key] !== null && params[key] !== undefined && params[key] !== '') {
        queryParams.append(key, params[key]);
      }
    });
    return fetchAPI(`/cost-ledger/summary?${queryParams.toString()}`);
  },
};

/**
 * System Logs API
 */
export const systemLogsAPI = {
  /**
   * Get system logs with filtering
   * @param {Object} filters - Filter options
   * @param {string} [filters.log_type] - Filter by log type
   * @param {string} [filters.origin] - Filter by origin
   * @param {string} [filters.start_time] - Start time (ISO format)
   * @param {string} [filters.end_time] - End time (ISO format)
   * @param {number} [filters.limit=100] - Maximum number of logs
   * @param {number} [filters.offset=0] - Offset for pagination
   * @param {string} [filters.user] - Filter by user
   * @param {boolean} [filters.success_only] - Filter by success status
   */
  getLogs: (filters = {}) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== null && value !== undefined && value !== '') {
        params.append(key, value.toString());
      }
    });
    return fetchAPI(`/system-logs?${params.toString()}`);
  },

  /**
   * Get log statistics
   */
  getStatistics: () => fetchAPI('/system-logs/statistics'),

  /**
   * Clear all logs
   */
  clearLogs: () =>
    fetchAPI('/system-logs', {
      method: 'DELETE',
    }),
};

/**
 * Backfill API
 */
export const backfillAPI = {
  /**
   * Backfill embeddings for documents
   * @param {Object} options - Backfill options
   * @param {string} [options.username] - Username to filter by (optional, defaults to current user)
   * @param {string[]} [options.document_ids] - Specific document IDs to backfill
   * @param {boolean} [options.skip_existing=true] - Skip documents that already have embeddings
   * @param {boolean} [options.dry_run=false] - If true, only report what would be done
   */
  backfill: (options = {}) =>
    fetchAPI('/backfill', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        username: options.username || null,
        document_ids: options.document_ids || null,
        skip_existing: options.skip_existing !== false,
        dry_run: options.dry_run || false,
      }),
      timeout: 600000, // 10 minutes for backfill operations (can process many documents)
    }),

  /**
   * Backfill chunk-level embeddings for existing documents
   * @param {Object} options - Chunk backfill options
   * @param {string} [options.case_id] - Optional case_id to filter documents
   * @param {boolean} [options.skip_existing=true] - Skip documents that already have chunk embeddings
   * @param {boolean} [options.dry_run=false] - If true, only report what would be done
   */
  backfillChunks: (options = {}) =>
    fetchAPI('/backfill/chunks', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        case_id: options.case_id || null,
        skip_existing: options.skip_existing !== false,
        dry_run: options.dry_run || false,
      }),
      timeout: 600000, // 10 minutes for chunk backfill
    }),

  /**
   * Backfill entity metadata (case_id) in ChromaDB
   * @param {Object} options - Entity metadata backfill options
   * @param {boolean} [options.dry_run=false] - If true, only report what would be done
   */
  backfillEntityMetadata: (options = {}) =>
    fetchAPI('/backfill/entity-metadata', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        dry_run: options.dry_run || false,
      }),
      timeout: 600000, // 10 minutes for entity metadata backfill
    }),

  /**
   * Backfill AI summaries for documents that don't have one
   * @param {Object} options - Document summary backfill options
   * @param {string} [options.case_id] - Optional case_id to filter documents
   * @param {boolean} [options.skip_existing=true] - Skip documents that already have summaries
   * @param {boolean} [options.dry_run=false] - If true, only report what would be done
   */
  backfillDocumentSummaries: (options = {}) =>
    fetchAPI('/backfill/document-summaries', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        case_id: options.case_id || null,
        skip_existing: options.skip_existing !== false,
        dry_run: options.dry_run || false,
      }),
      timeout: 600000, // 10 minutes for document summary backfill (uses LLM)
    }),

  /**
   * Get gap analysis / backfill status
   * Returns counts of what needs backfilling
   */
  getStatus: () => fetchAPI('/backfill/status'),
};

/**
 * Database API
 */
export const databaseAPI = {
  /**
   * List all documents in the vector database
   */
  listDocuments: () => fetchAPI('/database/documents'),

  /**
   * List all documents with their backfill status
   */
  listDocumentsStatus: () => fetchAPI('/database/documents/status'),

  /**
   * Get a specific document by ID
   * @param {string} docId - Document ID
   */
  getDocument: (docId) => fetchAPI(`/database/documents/${encodeURIComponent(docId)}`),

  /**
   * Get retrieval history for a document
   * @param {string} docId - Document ID
   */
  getRetrievalHistory: (docId) =>
    fetchAPI(`/database/documents/${encodeURIComponent(docId)}/retrieval-history`),

  /**
   * List all entities in the vector database
   */
  listEntities: () => fetchAPI('/database/entities'),

  /**
   * List all entities with their embedding status
   */
  listEntitiesStatus: () => fetchAPI('/database/entities/status'),

  /**
   * Get a specific entity by key
   * @param {string} entityKey - Entity key
   */
  getEntity: (entityKey) => fetchAPI(`/database/entities/${encodeURIComponent(entityKey)}`),
};

/**
 * LLM Configuration API
 */
export const workspaceAPI = {
  // Case Context
  getCaseContext: (caseId) => fetchAPI(`/workspace/${caseId}/context`),
  updateCaseContext: (caseId, context) => fetchAPI(`/workspace/${caseId}/context`, {
    method: 'PUT',
    body: context,
  }),

  // Witnesses
  getWitnesses: (caseId) => fetchAPI(`/workspace/${caseId}/witnesses`),
  createWitness: (caseId, witness) => fetchAPI(`/workspace/${caseId}/witnesses`, {
    method: 'POST',
    body: witness,
  }),
  updateWitness: (caseId, witnessId, witness) => fetchAPI(`/workspace/${caseId}/witnesses/${witnessId}`, {
    method: 'PUT',
    body: witness,
  }),
  deleteWitness: (caseId, witnessId) => fetchAPI(`/workspace/${caseId}/witnesses/${witnessId}`, {
    method: 'DELETE',
  }),

  // Investigative Notes
  getNotes: (caseId) => fetchAPI(`/workspace/${caseId}/notes`),
  createNote: (caseId, note) => fetchAPI(`/workspace/${caseId}/notes`, {
    method: 'POST',
    body: note,
  }),
  updateNote: (caseId, noteId, note) => fetchAPI(`/workspace/${caseId}/notes/${noteId}`, {
    method: 'PUT',
    body: note,
  }),
  deleteNote: (caseId, noteId) => fetchAPI(`/workspace/${caseId}/notes/${noteId}`, {
    method: 'DELETE',
  }),

  // Theories
  getTheories: (caseId) => fetchAPI(`/workspace/${caseId}/theories`),
  createTheory: (caseId, theory) => fetchAPI(`/workspace/${caseId}/theories`, {
    method: 'POST',
    body: theory,
  }),
  updateTheory: (caseId, theoryId, theory) => fetchAPI(`/workspace/${caseId}/theories/${theoryId}`, {
    method: 'PUT',
    body: theory,
  }),
  deleteTheory: (caseId, theoryId) => fetchAPI(`/workspace/${caseId}/theories/${theoryId}`, {
    method: 'DELETE',
  }),
  buildTheoryGraph: (caseId, theoryId, options) => fetchAPI(`/workspace/${caseId}/theories/${theoryId}/build-graph`, {
    method: 'POST',
    body: options,
  }),

  // Tasks
  getTasks: (caseId) => fetchAPI(`/workspace/${caseId}/tasks`),
  createTask: (caseId, task) => fetchAPI(`/workspace/${caseId}/tasks`, {
    method: 'POST',
    body: task,
  }),
  updateTask: (caseId, taskId, task) => fetchAPI(`/workspace/${caseId}/tasks/${taskId}`, {
    method: 'PUT',
    body: task,
  }),
  deleteTask: (caseId, taskId) => fetchAPI(`/workspace/${caseId}/tasks/${taskId}`, {
    method: 'DELETE',
  }),

  // Deadlines
  getDeadlines: (caseId) => fetchAPI(`/workspace/${caseId}/deadlines`),
  updateDeadlines: (caseId, deadlineConfig) => fetchAPI(`/workspace/${caseId}/deadlines`, {
    method: 'PUT',
    body: deadlineConfig,
  }),

  // Pinned Items
  getPinnedItems: (caseId) => fetchAPI(`/workspace/${caseId}/pinned`),
  pinItem: (caseId, itemType, itemId, annotationsCount = 0) => {
    const params = new URLSearchParams({ item_type: itemType, item_id: itemId });
    if (annotationsCount > 0) params.append('annotations_count', annotationsCount);
    return fetchAPI(`/workspace/${caseId}/pinned?${params.toString()}`, {
      method: 'POST',
    });
  },
  unpinItem: (caseId, pinId) => fetchAPI(`/workspace/${caseId}/pinned/${pinId}`, {
    method: 'DELETE',
  }),

  // Presence
  getPresence: (caseId) => fetchAPI(`/workspace/${caseId}/presence`),
  updatePresence: (caseId, status) => fetchAPI(`/workspace/${caseId}/presence`, {
    method: 'PUT',
    body: { status },
  }),

  // Investigation Timeline
  getInvestigationTimeline: (caseId) => fetchAPI(`/workspace/${caseId}/investigation-timeline`),
  getTheoryTimeline: (caseId, theoryId) => fetchAPI(`/workspace/${caseId}/theories/${theoryId}/timeline`),
};

export const llmConfigAPI = {
  /**
   * Get all available models
   * @param {string} [provider] - Optional provider filter ("openai" or "ollama")
   */
  getModels: (provider) => {
    const params = provider ? `?provider=${encodeURIComponent(provider)}` : '';
    return fetchAPI(`/llm-config/models${params}`);
  },

  /**
   * Get current LLM configuration
   */
  getCurrentConfig: () => fetchAPI('/llm-config/current'),

  /**
   * Set LLM configuration
   * @param {Object} config - Configuration object
   * @param {string} config.provider - Provider ("openai" or "ollama")
   * @param {string} config.model_id - Model ID
   */
  setConfig: (config) =>
    fetchAPI('/llm-config/set', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(config),
    }),

  /**
   * Get confidence threshold for vector search
   */
  getConfidenceThreshold: () => fetchAPI('/llm-config/confidence-threshold'),

  /**
   * Set confidence threshold for vector search
   * @param {number} threshold - Confidence threshold (0.0-1.0)
   */
  setConfidenceThreshold: (threshold) =>
    fetchAPI('/llm-config/confidence-threshold', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ threshold }),
    }),
};

/**
 * Case Members API
 *
 * Manages collaborators/members for cases with permission presets
 */
export const caseMembersAPI = {
  /**
   * List all members of a case
   * @param {string} caseId - Case ID
   * @returns {Promise<Array>} - Array of case members with permissions
   */
  list: (caseId) =>
    fetchAPI(`/cases/${encodeURIComponent(caseId)}/members`),

  /**
   * Add a member to a case
   * @param {string} caseId - Case ID
   * @param {string} userId - User ID to add
   * @param {string} preset - Permission preset ('viewer', 'editor')
   */
  add: (caseId, userId, preset) =>
    fetchAPI(`/cases/${encodeURIComponent(caseId)}/members`, {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, preset }),
    }),

  /**
   * Update a member's permissions
   * @param {string} caseId - Case ID
   * @param {string} userId - User ID to update
   * @param {string} preset - New permission preset ('viewer', 'editor')
   */
  update: (caseId, userId, preset) =>
    fetchAPI(`/cases/${encodeURIComponent(caseId)}/members/${encodeURIComponent(userId)}`, {
      method: 'PATCH',
      body: JSON.stringify({ preset }),
    }),

  /**
   * Remove a member from a case
   * @param {string} caseId - Case ID
   * @param {string} userId - User ID to remove
   */
  remove: (caseId, userId) =>
    fetchAPI(`/cases/${encodeURIComponent(caseId)}/members/${encodeURIComponent(userId)}`, {
      method: 'DELETE',
    }),

  /**
   * Get current user's membership/permissions for a case
   * @param {string} caseId - Case ID
   * @returns {Promise<Object>} - Membership info with permissions
   */
  getMyMembership: (caseId) =>
    fetchAPI(`/cases/${encodeURIComponent(caseId)}/members/me`),
};

/**
 * Users API
 *
 * For listing users (used in collaborator invite dropdown)
 */
export const usersAPI = {
  /**
   * List all users
   * @returns {Promise<Array>} - Array of users
   */
  list: () => fetchAPI('/users'),

  /**
   * Get a specific user by ID
   * @param {string} userId - User ID
   */
  get: (userId) => fetchAPI(`/users/${encodeURIComponent(userId)}`),

  /**
   * Create a new user (admin/super_admin only)
   * @param {Object} userData - User data
   * @param {string} userData.email - User email
   * @param {string} userData.name - User name
   * @param {string} userData.password - User password (min 8 chars)
   * @param {string} userData.role - User role ('user', 'admin', 'super_admin')
   */
  create: (userData) =>
    fetchAPI('/users', {
      method: 'POST',
      body: JSON.stringify(userData),
    }),
};