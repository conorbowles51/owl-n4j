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

  // If the caller passed their own AbortSignal (e.g. a useEffect cleanup
  // aborts superseded requests), link it to our internal controller so
  // the fetch is actually cancelled at the network layer. Without this
  // the caller's signal would be silently dropped by the spread below.
  const callerSignal = options.signal;
  let onCallerAbort = null;
  if (callerSignal) {
    if (callerSignal.aborted) {
      clearTimeout(timeoutId);
      const ae = new DOMException('Aborted', 'AbortError');
      throw ae;
    }
    onCallerAbort = () => controller.abort();
    callerSignal.addEventListener('abort', onCallerAbort);
  }

  try {
    const response = await fetch(url, {
      ...config,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);
    if (callerSignal && onCallerAbort) callerSignal.removeEventListener('abort', onCallerAbort);

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
        const ve = new Error(`Validation error: ${validationErrors}`);
        ve.status = 422;
        ve.detail = error.detail;
        throw ve;
      }
      // FastAPI lets routes raise HTTPException(detail={...}) — when detail
      // is a dict we want callers to be able to inspect it directly (e.g.
      // duplicate-phone-report dialog needs the `existing` payload).
      const detailIsDict = error && typeof error.detail === 'object' && error.detail !== null;
      const errorMessage = detailIsDict
        ? (error.detail.message || error.detail.reason || `HTTP ${response.status}`)
        : (error.detail || error.message || error.error ||
            (typeof error === 'string' ? error : JSON.stringify(error)) ||
            `HTTP ${response.status}`);
      const apiErr = new Error(errorMessage);
      apiErr.status = response.status;
      apiErr.detail = error?.detail;
      throw apiErr;
    }

    // Handle 204 No Content responses (e.g., DELETE operations)
    if (response.status === 204) {
      return null;
    }

    return response.json();
  } catch (err) {
    clearTimeout(timeoutId);
    if (callerSignal && onCallerAbort) callerSignal.removeEventListener('abort', onCallerAbort);
    // Caller-initiated abort — propagate as a real AbortError so call
    // sites can distinguish a "we cancelled this on purpose" from a
    // genuine network/timeout failure (and skip user-facing error toasts).
    if (callerSignal?.aborted) {
      const ae = new DOMException('Aborted', 'AbortError');
      throw ae;
    }
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
 * XHR-based upload helper. Used instead of fetch() when we need byte-level
 * upload progress events (fetch's standard API doesn't expose them).
 *
 * Mirrors fetchAPI for the bits that matter: bearer auth header, JSON body
 * parsing, error shape ({detail} / 422 validation arrays), AbortController-
 * style timeout. Always assumes a FormData body (lets the browser set the
 * multipart Content-Type with the boundary).
 *
 * Returns a Promise<json>. `onProgress` is called with
 * { loaded, total, lengthComputable } as bytes are sent.
 */
function xhrUpload(endpoint, formData, { onProgress, timeout } = {}) {
  return new Promise((resolve, reject) => {
    const url = `${API_BASE}${endpoint}`;
    const token = localStorage.getItem('authToken');
    const effectiveTimeout = timeout || 300000;

    const xhr = new XMLHttpRequest();
    xhr.open('POST', url, true);
    xhr.withCredentials = true;
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    xhr.timeout = effectiveTimeout;

    if (onProgress) {
      xhr.upload.addEventListener('progress', (evt) => {
        try {
          onProgress({
            loaded: evt.loaded,
            total: evt.lengthComputable ? evt.total : 0,
            lengthComputable: evt.lengthComputable,
          });
        } catch (_) {
          // Don't let a UI bug abort the upload.
        }
      });
    }

    xhr.addEventListener('load', () => {
      const status = xhr.status;
      let parsed = null;
      try {
        parsed = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch (_) {
        parsed = null;
      }
      if (status >= 200 && status < 300) {
        if (status === 204) return resolve(null);
        return resolve(parsed);
      }
      if (status === 422 && parsed && Array.isArray(parsed.detail)) {
        const validationErrors = parsed.detail.map(err => {
          const field = err.loc ? err.loc.join('.') : 'unknown';
          const msg = err.msg || 'validation error';
          return `${field}: ${msg}`;
        }).join(', ');
        return reject(new Error(`Validation error: ${validationErrors}`));
      }
      // Surface the HTTP status so non-JSON error pages (413 from a proxy,
      // 502 from a dead backend, etc.) don't collapse to "Unknown error".
      const detail = parsed && (parsed.detail || parsed.message || parsed.error);
      const statusText = xhr.statusText || `HTTP ${status}`;
      const snippet = !parsed && xhr.responseText
        ? ` — ${xhr.responseText.slice(0, 200).replace(/\s+/g, ' ').trim()}`
        : '';
      reject(new Error(detail ? `${statusText}: ${detail}` : `${statusText}${snippet}`));
    });

    xhr.addEventListener('error', () => {
      // Fires on network-level failure (connection reset, DNS, CORS).
      // For uploads this most often means the server (or a proxy in front
      // of it) closed the socket mid-stream — e.g. a body-size or request
      // timeout cap was hit. Hint at that rather than blaming the backend
      // being down.
      reject(new Error(
        'Upload connection dropped before the server could respond. ' +
        'This usually means a proxy or dev-server timeout closed the socket ' +
        'mid-upload. Check the dev server / nginx request limits.'
      ));
    });

    xhr.addEventListener('timeout', () => {
      reject(new Error(`Request timed out after ${effectiveTimeout}ms. Please check that the backend server is running on port 8000 and try again.`));
    });

    xhr.addEventListener('abort', () => {
      reject(new Error('Upload aborted.'));
    });

    xhr.send(formData);
  });
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
  getGraph: ({ case_id, start_date, end_date, lightweight, limit, sort_by } = {}) => {
    const params = new URLSearchParams();
    params.append('case_id', case_id);
    if (start_date) params.append('start_date', start_date);
    if (end_date) params.append('end_date', end_date);
    if (lightweight) params.append('lightweight', 'true');
    if (limit) params.append('limit', String(limit));
    if (sort_by) params.append('sort_by', sort_by);

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
   * Get details for multiple nodes in a single request
   * @param {string[]} keys - Array of node keys
   * @param {string} caseId - REQUIRED: Case ID
   */
  getNodeDetailsBulk: (keys, caseId) => {
    return fetchAPI('/graph/nodes/bulk', {
      method: 'POST',
      body: JSON.stringify({ keys, case_id: caseId }),
    });
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

  bulkMergeEntities: (caseId, targetKey, sourceKeys, mergedData) =>
    fetchAPI('/graph/bulk-merge-entities', {
      method: 'POST',
      body: JSON.stringify({
        case_id: caseId,
        target_key: targetKey,
        source_keys: sourceKeys,
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
   * Delete a node (soft-delete to recycling bin by default)
   * @param {string} nodeKey - Node key to delete
   * @param {string} caseId - REQUIRED: Case ID for case-specific data
   * @param {boolean} permanent - If true, permanently delete (no recycling bin)
   */
  deleteNode: (nodeKey, caseId, permanent = false) =>
    fetchAPI(`/graph/node/${encodeURIComponent(nodeKey)}?case_id=${encodeURIComponent(caseId)}&permanent=${permanent}`, {
      method: 'DELETE',
    }),

  /**
   * List all entities in the recycling bin for a case
   * @param {string} caseId - Case ID
   */
  listRecycledEntities: (caseId) =>
    fetchAPI(`/graph/recycle-bin?case_id=${encodeURIComponent(caseId)}`),

  /**
   * Restore an entity from the recycling bin
   * @param {string} recycleKey - Recycling bin record key
   * @param {string} caseId - Case ID
   */
  restoreRecycledEntity: (recycleKey, caseId) =>
    fetchAPI(`/graph/recycle-bin/${encodeURIComponent(recycleKey)}/restore?case_id=${encodeURIComponent(caseId)}`, {
      method: 'POST',
    }),

  /**
   * Permanently delete an entity from the recycling bin
   * @param {string} recycleKey - Recycling bin record key
   * @param {string} caseId - Case ID
   */
  permanentlyDeleteRecycled: (recycleKey, caseId) =>
    fetchAPI(`/graph/recycle-bin/${encodeURIComponent(recycleKey)}?case_id=${encodeURIComponent(caseId)}`, {
      method: 'DELETE',
    }),

  geocodeNode: (nodeKey, caseId, address) =>
    fetchAPI(`/graph/nodes/${encodeURIComponent(nodeKey)}/geocode`, {
      method: 'POST',
      body: JSON.stringify({ case_id: caseId, address }),
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

  getNodesByType: (caseId, entityType) => {
    const params = `?case_id=${encodeURIComponent(caseId)}&entity_type=${encodeURIComponent(entityType)}`;
    return fetchAPI(`/graph/nodes-by-type${params}`);
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

  updateLocation: (nodeKey, { caseId, locationName, latitude, longitude }) =>
    fetchAPI(`/graph/node/${encodeURIComponent(nodeKey)}/location`, {
      method: 'PUT',
      body: { case_id: caseId, location_name: locationName, latitude, longitude },
    }),

  removeLocation: (nodeKey, caseId) =>
    fetchAPI(`/graph/node/${encodeURIComponent(nodeKey)}/location?case_id=${encodeURIComponent(caseId)}`, {
      method: 'DELETE',
    }),

  rescanLocations: (caseId, { forceRegeocode = false } = {}) =>
    fetchAPI(`/graph/cases/${encodeURIComponent(caseId)}/rescan-locations?force_regeocode=${forceRegeocode}`, {
      method: 'POST',
      timeout: 300000,
    }),

  getEntitySummary: (caseId) =>
    fetchAPI(`/graph/cases/${encodeURIComponent(caseId)}/entity-summary`),

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

  batchUpdate: (caseId, updates) =>
    fetchAPI('/graph/batch-update', {
      method: 'PUT',
      body: JSON.stringify({ case_id: caseId, updates }),
    }),

  generateInsights: (caseId, maxEntities = 10) =>
    fetchAPI(`/graph/cases/${encodeURIComponent(caseId)}/generate-insights?max_entities=${maxEntities}`, {
      method: 'POST',
    }),

  rejectInsight: (nodeKey, insightIndex, caseId) =>
    fetchAPI(`/graph/node/${encodeURIComponent(nodeKey)}/insights/${insightIndex}?case_id=${encodeURIComponent(caseId)}`, {
      method: 'DELETE',
    }),

  getCaseInsights: (caseId) =>
    fetchAPI(`/graph/cases/${encodeURIComponent(caseId)}/insights`),
};

/**
 * Chat API
 */
export const chatAPI = {
  /**
   * Send a question to the AI
   */
  ask: (question, selectedKeys = null, model, provider, confidenceThreshold = null, caseId = null, viewContext = null) =>
    fetchAPI('/chat', {
      method: 'POST',
      body: JSON.stringify({
        question,
        selected_keys: selectedKeys,
        model,
        provider,
        confidence_threshold: confidenceThreshold,
        case_id: caseId,
        view_context: viewContext,
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
  extractNodesFromAnswer: (answer, caseId) =>
    fetchAPI('/chat/extract-nodes', {
      method: 'POST',
      body: JSON.stringify({
        answer: answer,
        case_id: caseId,
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
   * Get timeline events.
   *
   * Pagination is opt-in: pass `limit` to engage server-side keyset
   * pagination, then loop calling again with the response's
   * `next_cursor` until it comes back null. Without `limit` the
   * server returns the entire matching set (legacy behaviour, can
   * be tens of MB on busy cases — avoid for new code).
   *
   * @param {Object} options
   * @param {string} options.caseId - REQUIRED: Filter to events in this case
   * @param {string} [options.types] - Comma-separated event types
   * @param {string} [options.startDate] - Filter start date (YYYY-MM-DD)
   * @param {string} [options.endDate] - Filter end date (YYYY-MM-DD)
   * @param {number} [options.limit]  - Page size (1-5000)
   * @param {string} [options.cursor] - Continuation token from a prior response
   * @returns {Promise<{events:Array, total:number, next_cursor:string|null}>}
   */
  getEvents: async ({ caseId, types, startDate, endDate, limit, cursor } = {}) => {
    const params = new URLSearchParams();
    params.append('case_id', caseId);
    if (types) params.append('types', types);
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    if (limit) params.append('limit', String(limit));
    if (cursor) params.append('cursor', cursor);

    return fetchAPI(`/timeline?${params.toString()}`);
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
  getTransactions: async ({ caseId, types, startDate, endDate, categories, dataVersion } = {}) => {
    const params = new URLSearchParams();
    params.append('case_id', caseId);
    if (types) params.append('types', types);
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    if (categories) params.append('categories', categories);
    if (dataVersion) params.append('data_version', dataVersion);
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

  updateAmount: (nodeKey, { caseId, newAmount, correctionReason }) =>
    fetchAPI(`/financial/transactions/${encodeURIComponent(nodeKey)}/amount`, {
      method: 'PUT',
      body: JSON.stringify({
        case_id: caseId,
        new_amount: newAmount,
        correction_reason: correctionReason,
      }),
    }),

  bulkCorrect: (caseId, corrections) =>
    fetchAPI('/financial/transactions/bulk-correct', {
      method: 'POST',
      body: JSON.stringify({
        case_id: caseId,
        corrections,
      }),
    }),

  linkSubTransaction: (parentKey, childKey, caseId) =>
    fetchAPI(`/financial/transactions/${encodeURIComponent(parentKey)}/sub-transactions`, {
      method: 'POST',
      body: JSON.stringify({ case_id: caseId, child_key: childKey }),
    }),

  unlinkSubTransaction: (childKey, caseId) =>
    fetchAPI(`/financial/transactions/${encodeURIComponent(childKey)}/parent?case_id=${encodeURIComponent(caseId)}`, {
      method: 'DELETE',
    }),

  getSubTransactions: (parentKey, caseId) =>
    fetchAPI(`/financial/transactions/${encodeURIComponent(parentKey)}/sub-transactions?case_id=${encodeURIComponent(caseId)}`),

  /**
   * Auto-extract from/to entities from transaction fields using heuristics + LLM.
   * @param {string} caseId - REQUIRED: Case ID
   * @param {Object} options
   * @param {boolean} [options.dryRun=true] - Preview only (true) or apply (false)
   */
  autoExtractFromTo: (caseId, { dryRun = true } = {}) =>
    fetchAPI('/financial/auto-extract-from-to', {
      method: 'POST',
      body: JSON.stringify({ case_id: caseId, dry_run: dryRun }),
      timeout: 600000, // 10 minutes — LLM batches can take a while
    }),

  /**
   * Upload a CSV of investigator notes keyed by transaction ref_id
   * @param {string} caseId - REQUIRED: Case ID
   * @param {File} file - CSV file
   */
  uploadNotes: (caseId, file) => {
    const formData = new FormData();
    formData.append('case_id', caseId);
    formData.append('file', file);
    return fetchAPI('/financial/upload-notes', {
      method: 'POST',
      body: formData,
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
   * Archive a case
   */
  archive: (caseId) =>
    fetchAPI(`/cases/${encodeURIComponent(caseId)}/archive`, {
      method: 'PATCH',
    }),

  /**
   * Unarchive a case
   */
  unarchive: (caseId) =>
    fetchAPI(`/cases/${encodeURIComponent(caseId)}/unarchive`, {
      method: 'PATCH',
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
   * Sync filesystem with evidence records.
   * Creates evidence records for files on disk that don't have records yet.
   * @param {string} caseId - Case ID to sync
   * @returns {{created: number, message: string}}
   */
  syncFilesystem: (caseId) =>
    fetchAPI(`/evidence/sync-filesystem?case_id=${encodeURIComponent(caseId)}`, {
      method: 'POST',
    }),

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
   * Check if a folder contains a Cellebrite UFED report
   */
  checkCellebriteFolder: (caseId, folderPath) => {
    const params = new URLSearchParams();
    params.append('case_id', caseId);
    params.append('folder_path', folderPath);
    return fetchAPI(`/evidence/cellebrite/check?${params.toString()}`);
  },

  /**
   * Process a Cellebrite UFED report folder.
   *
   * Without `force`, the server returns HTTP 409 with the existing
   * report's summary if a PhoneReport with the same key/IMEI already
   * exists in the case. The frontend should surface that to the user
   * and re-call with `force=true` only after explicit confirmation.
   */
  processCellebriteFolder: (caseId, folderPath, opts = {}) =>
    fetchAPI('/evidence/cellebrite/process', {
      method: 'POST',
      body: JSON.stringify({
        case_id: caseId,
        folder_path: folderPath,
        force: !!opts.force,
        // Investigator-supplied device-owner identity. Required when the
        // report has no extractable phone number; optional otherwise.
        device_identifier: opts.deviceIdentifier || null,
      }),
      timeout: 60000,
    }),

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
  upload: (caseId, files, onProgress) => {
    const formData = new FormData();
    formData.append('case_id', caseId);
    Array.from(files).forEach((file) => {
      formData.append('files', file);
    });
    // Network transfer for evidence files (e.g. multi-GB Cellebrite folders)
    // can take much longer than the default 5 minute timeout. The backend
    // streams bytes to disk and returns as soon as the request body lands,
    // so this only needs to cover the upload itself. Routed through XHR
    // so the caller can observe byte-level upload progress.
    return xhrUpload('/evidence/upload', formData, {
      onProgress,
      timeout: 60 * 60 * 1000, // 60 minutes
    });
  },

  /**
   * Upload a folder of files (or folder of folders) for a case
   * Uses webkitdirectory to preserve folder structure
   */
  uploadFolder: (caseId, files, onProgress) => {
    const formData = new FormData();
    formData.append('case_id', caseId);
    formData.append('is_folder', 'true');
    Array.from(files).forEach((file) => {
      // Third arg becomes UploadFile.filename on the backend, which is
      // where the route reads the relative path from. No separate
      // file_path_<index> field — that doubled the form-field count and
      // tripped Starlette's max_fields cap mid-stream on large folders.
      const relativePath = file.webkitRelativePath || file.name;
      formData.append('files', file, relativePath);
    });
    return xhrUpload('/evidence/upload', formData, {
      onProgress,
      timeout: 60 * 60 * 1000, // 60 minutes — see comment on upload() above
    });
  },

  /**
   * Upload a single .zip archive that the server unpacks into a folder
   * upload. Preferred for large Cellebrite reports because the request is
   * a single multipart part — webkitdirectory uploads of thousands of
   * files crash the dev proxy mid-stream.
   */
  uploadArchive: (caseId, file, onProgress) => {
    const formData = new FormData();
    formData.append('case_id', caseId);
    formData.append('is_folder', 'true');
    formData.append('is_archive', 'true');
    formData.append('files', file, file.name);
    return xhrUpload('/evidence/upload', formData, {
      onProgress,
      timeout: 60 * 60 * 1000,
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
   * @param {string} [imageProvider] - Image processing provider: "tesseract" (local OCR) or "openai" (GPT-4 Vision)
   */
  processBackground: (caseId, fileIds, profile = null, maxWorkers = 4, imageProvider = null) =>
    fetchAPI('/evidence/process/background', {
      method: 'POST',
      body: JSON.stringify({
        case_id: caseId,
        file_ids: fileIds,
        profile: profile,
        max_workers: maxWorkers,
        image_provider: imageProvider,
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

  getVideoFrames: (evidenceId, { interval = 30, maxFrames = 50 } = {}) =>
    fetchAPI(`/evidence/${encodeURIComponent(evidenceId)}/frames?interval=${interval}&max_frames=${maxFrames}`, {
      timeout: 120000,
    }),

  getVideoFrameUrl: (evidenceId, filename) =>
    `/api/evidence/${encodeURIComponent(evidenceId)}/frames/${encodeURIComponent(filename)}`,

  /**
   * Delete an evidence file and optionally its exclusive entities
   * @param {string} evidenceId - Evidence ID to delete
   * @param {string} caseId - Case ID for scoping
   * @param {boolean} deleteExclusiveEntities - Also delete entities only in this file
   */
  delete: (evidenceId, caseId, deleteExclusiveEntities = true) => {
    const params = new URLSearchParams();
    params.append('case_id', caseId);
    params.append('delete_exclusive_entities', String(deleteExclusiveEntities));
    return fetchAPI(`/evidence/${encodeURIComponent(evidenceId)}?${params.toString()}`, {
      method: 'DELETE',
    });
  },

  setRelevance: (evidenceIds, isRelevant) =>
    fetchAPI('/evidence/relevance', {
      method: 'PUT',
      body: JSON.stringify({ evidence_ids: evidenceIds, is_relevant: isRelevant }),
    }),

  setRelevanceFromTheory: (caseId, theoryId) =>
    fetchAPI(`/evidence/relevance/from-theory?case_id=${encodeURIComponent(caseId)}&theory_id=${encodeURIComponent(theoryId)}`, {
      method: 'PUT',
    }),
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
   * Recursively list every file under a folder in one HTTP call.
   * Returns { files: string[], count: number, ... } with relative paths.
   * Avoids the N-round-trip pattern of recursing /filesystem/list per
   * directory; for a 93k-file Cellebrite phone the old approach made ~414
   * sequential requests and the user's browser timed out partway through.
   */
  listRecursive: (caseId, path = null) => {
    const params = new URLSearchParams();
    params.append('case_id', caseId);
    if (path) params.append('path', path);
    return fetchAPI(`/filesystem/list_recursive?${params.toString()}`);
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
      timeout: 5000,
    }),

  changePassword: (currentPassword, newPassword) =>
    fetchAPI('/auth/change-password', {
      method: 'PUT',
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
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

  /**
   * Mark an active task as failed. Used for stalled tasks whose worker
   * thread died (e.g. backend restart) — flipping to `failed` clears it
   * from the active list in the UI.
   */
  markFailed: (taskId) =>
    fetchAPI(`/background-tasks/${encodeURIComponent(taskId)}/mark-failed`, {
      method: 'POST',
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
   * Backfill case_id for documents and entities in Neo4j and ChromaDB
   * @param {Object} options - Case ID backfill options
   * @param {boolean} [options.include_entities=true] - Also backfill entities via relationship traversal
   * @param {boolean} [options.include_vector_db=true] - Also backfill ChromaDB metadata
   * @param {boolean} [options.dry_run=false] - If true, only report what would be done
   */
  backfillCaseIds: (options = {}) =>
    fetchAPI('/backfill/case-ids', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        include_entities: options.include_entities !== false,
        include_vector_db: options.include_vector_db !== false,
        dry_run: options.dry_run || false,
      }),
      timeout: 600000, // 10 minutes for case_id backfill
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
  /**
   * Attach Profile (CaseEntity) ids to an investigative note. Additive.
   */
  linkNoteProfiles: (caseId, noteId, profileIds) =>
    fetchAPI(`/workspace/${caseId}/notes/${noteId}/link-profiles`, {
      method: 'POST',
      body: { profile_ids: profileIds },
    }),
  /**
   * Detach Profile ids from an investigative note.
   */
  unlinkNoteProfiles: (caseId, noteId, profileIds) =>
    fetchAPI(`/workspace/${caseId}/notes/${noteId}/unlink-profiles`, {
      method: 'POST',
      body: { profile_ids: profileIds },
    }),

  // Findings
  getFindings: (caseId) => fetchAPI(`/workspace/${caseId}/findings`),
  createFinding: (caseId, finding) => fetchAPI(`/workspace/${caseId}/findings`, {
    method: 'POST',
    body: JSON.stringify(finding),
  }),
  updateFinding: (caseId, findingId, finding) => fetchAPI(`/workspace/${caseId}/findings/${findingId}`, {
    method: 'PUT',
    body: JSON.stringify(finding),
  }),
  deleteFinding: (caseId, findingId) => fetchAPI(`/workspace/${caseId}/findings/${findingId}`, {
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
  buildGraphFromText: (caseId, options) => fetchAPI(`/workspace/${caseId}/build-graph-from-text`, {
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

/**
 * Cellebrite Multi-Phone Analytics API
 */
// Single-flight cache for /cellebrite/reports keyed by caseId.
// Each entry holds either an `inflight` promise (concurrent callers
// share it) or a resolved `value` (recent callers reuse it for
// REPORTS_CACHE_TTL_MS). Cleared on errors and on every mutating
// endpoint via cellebriteAPI.invalidateReports.
const _reportsCache = new Map();
const REPORTS_CACHE_TTL_MS = 1500;

export const cellebriteAPI = {
  /**
   * List all ingested PhoneReport nodes for a case.
   *
   * Single-flighted: concurrent calls for the same caseId share a
   * single in-flight HTTP request. Result is cached for a short TTL
   * (1.5s) so independent components mounting at roughly the same
   * time on case open don't each trigger their own round-trip — we
   * observed 6 separate /reports calls per case open before this.
   *
   * Mutating endpoints (deleteReport, patchReport) call invalidateReports
   * to bust the cache so subsequent reads see fresh data.
   *
   * @param {string} caseId - REQUIRED: Case ID
   */
  getReports: (caseId) => {
    const now = Date.now();
    const entry = _reportsCache.get(caseId);
    if (entry) {
      // Coalesce concurrent callers onto one in-flight promise.
      if (entry.inflight) return entry.inflight;
      // Reuse a recent successful response.
      if (now - entry.cachedAt < REPORTS_CACHE_TTL_MS) {
        return Promise.resolve(entry.value);
      }
    }
    const promise = fetchAPI(`/cellebrite/reports?case_id=${encodeURIComponent(caseId)}`)
      .then((value) => {
        _reportsCache.set(caseId, { value, cachedAt: Date.now(), inflight: null });
        return value;
      })
      .catch((err) => {
        // Don't poison the cache on failure — let the next caller
        // retry. Clearing inflight is enough.
        _reportsCache.delete(caseId);
        throw err;
      });
    _reportsCache.set(caseId, { value: null, cachedAt: 0, inflight: promise });
    return promise;
  },

  /**
   * Drop the cached /reports response for a case so the next
   * getReports() will re-fetch. Called by the mutating endpoints
   * automatically; expose for callers that update reports out of
   * band (e.g. an ingestion completion handler).
   */
  invalidateReports: (caseId) => {
    _reportsCache.delete(caseId);
  },

  /**
   * Delete a phone report and every node tagged with its key.
   * Used by the Overview's per-card "Delete phone report" action.
   *
   * @param {string} caseId
   * @param {string} reportKey - e.g. "cellebrite-220049582-06308586"
   * @returns {Promise<{status, deleted_nodes, deleted_phone_report, deleted_evidence_records}>}
   */
  deleteReport: (caseId, reportKey) =>
    fetchAPI(
      `/cellebrite/reports/${encodeURIComponent(reportKey)}?case_id=${encodeURIComponent(caseId)}`,
      { method: 'DELETE' },
    ).then((res) => {
      // Bust the single-flight cache so subsequent getReports() sees
      // the deleted phone disappear instead of replaying a stale list.
      _reportsCache.delete(caseId);
      return res;
    }),

  /**
   * Update mutable fields on a phone report. Currently supports only
   * `device_name_override`: pass a non-empty string to override the
   * detected name, or null/empty to clear and revert to the parser's
   * detected name.
   *
   * @param {string} caseId
   * @param {string} reportKey
   * @param {{device_name_override?: string|null}} body
   */
  patchReport: (caseId, reportKey, body) =>
    fetchAPI(
      `/cellebrite/reports/${encodeURIComponent(reportKey)}?case_id=${encodeURIComponent(caseId)}`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body || {}),
      },
    ).then((res) => {
      // Bust the single-flight cache so the next getReports() picks
      // up renamed devices / new override values.
      _reportsCache.delete(caseId);
      return res;
    }),

  /**
   * Get cross-phone graph (shared contacts across devices)
   * @param {string} caseId - REQUIRED: Case ID
   */
  getCrossPhoneGraph: (caseId, opts = {}) => {
    // Backwards-compatible: callers passing only caseId get the legacy
    // shape. The new optional params power the perspective rebuild and
    // the event-type chip strip on the Cross-Phone Graph tab.
    const params = new URLSearchParams();
    params.set('case_id', caseId);
    if (Array.isArray(opts.personKeys) && opts.personKeys.length > 0) {
      params.set('person_keys', opts.personKeys.join(','));
    }
    if (Array.isArray(opts.eventTypes) && opts.eventTypes.length > 0) {
      params.set('event_types', opts.eventTypes.join(','));
    }
    if (opts.depth && Number.isFinite(opts.depth)) {
      params.set('depth', String(opts.depth));
    }
    return fetchAPI(`/cellebrite/cross-phone-graph?${params.toString()}`);
  },

  /**
   * Get multi-device event timeline
   * @param {string} caseId - REQUIRED: Case ID
   * @param {string[]} reportKeys - Optional report keys to filter
   * @param {Object} options - Optional filters (startDate, endDate, eventTypes, limit, offset)
   */
  getTimeline: (caseId, reportKeys = null, options = {}) => {
    const params = new URLSearchParams({ case_id: caseId });
    if (reportKeys?.length) params.append('report_keys', reportKeys.join(','));
    if (options.startDate) params.append('start_date', options.startDate);
    if (options.endDate) params.append('end_date', options.endDate);
    if (options.eventTypes?.length) params.append('event_types', options.eventTypes.join(','));
    params.append('limit', String(options.limit || 200));
    params.append('offset', String(options.offset || 0));
    return fetchAPI(`/cellebrite/timeline?${params.toString()}`);
  },

  /**
   * Get communication network analysis
   * @param {string} caseId - REQUIRED: Case ID
   */
  getCommunicationNetwork: (caseId) =>
    fetchAPI(`/cellebrite/communication-network?case_id=${encodeURIComponent(caseId)}`),
};


/**
 * Cellebrite Communication Center API
 *
 * All endpoints accept an optional `reportKeys` array for multi-device filtering.
 * Passing null / undefined means "all devices on the case".
 */
export const cellebriteCommsAPI = {
  /**
   * List all comms participants (Person entities) with device membership.
   *
   * `withCounts` (default false) toggles per-entity call/message/email
   * count aggregation. On busy cases the counts add ~10s + 10s of MB
   * to the response, so default-off keeps the entity filter snappy.
   * Opt in only when the caller actually needs activity-based sorting.
   */
  getEntities: (caseId, reportKeys = null, { withCounts = false } = {}) => {
    const params = new URLSearchParams({ case_id: caseId });
    if (reportKeys?.length) params.append('report_keys', reportKeys.join(','));
    if (withCounts) params.append('with_counts', 'true');
    return fetchAPI(`/cellebrite/comms/entities?${params.toString()}`);
  },

  /**
   * List distinct source apps (WhatsApp, Facebook Messenger, SMS, Gmail, ...) for the
   * current device filter, with counts and thread_type.
   */
  getSourceApps: (caseId, reportKeys = null) => {
    const params = new URLSearchParams({ case_id: caseId });
    if (reportKeys?.length) params.append('report_keys', reportKeys.join(','));
    return fetchAPI(`/cellebrite/comms/source-apps?${params.toString()}`);
  },

  /**
   * List threads (chats + synthetic call/email threads per participant pair).
   */
  getThreads: (caseId, {
    reportKeys = null,
    fromKeys = null,
    toKeys = null,
    // Direction-agnostic involvement filter — when set, threads
    // qualify if any participant is in the set. OR-combined with
    // from_keys/to_keys server-side. Used by Filter Comms intents
    // and the Participants picker's "Any direction" mode.
    participantKeys = null,
    threadTypes = null,
    sourceApps = null,
    startDate = null,
    endDate = null,
    search = null,
    limit = 200,
    offset = 0,
    signal = null,
  } = {}) => {
    const params = new URLSearchParams({ case_id: caseId });
    if (reportKeys?.length) params.append('report_keys', reportKeys.join(','));
    if (fromKeys?.length) params.append('from_keys', fromKeys.join(','));
    if (toKeys?.length) params.append('to_keys', toKeys.join(','));
    if (participantKeys?.length) params.append('participant_keys', participantKeys.join(','));
    if (threadTypes?.length) params.append('thread_types', threadTypes.join(','));
    if (sourceApps?.length) params.append('source_apps', sourceApps.join(','));
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    if (search) params.append('search', search);
    params.append('limit', String(limit));
    params.append('offset', String(offset));
    return fetchAPI(`/cellebrite/comms/threads?${params.toString()}`, signal ? { signal } : undefined);
  },

  /**
   * Get chronological detail for a single thread (messages + calls + emails items).
   */
  getThreadDetail: (caseId, threadId, threadType, { limit = 500, offset = 0, anchorKey = null } = {}) => {
    const params = new URLSearchParams({ case_id: caseId, thread_type: threadType });
    params.append('limit', String(limit));
    params.append('offset', String(offset));
    // Anchor key shifts the server-side window so it straddles the
    // selected message — without this the default oldest-first slice
    // misses any anchor that lives past the limit in a long chat.
    if (anchorKey) params.append('anchor_key', anchorKey);
    return fetchAPI(
      `/cellebrite/comms/threads/${encodeURIComponent(threadId)}?${params.toString()}`
    );
  },

  /**
   * Cross-type chronological feed between selected participant sets (AND semantics).
   */
  getBetween: (caseId, {
    fromKeys = null,
    toKeys = null,
    // Direction-agnostic involvement filter — see getThreads().
    participantKeys = null,
    types = null,
    reportKeys = null,
    sourceApps = null,
    startDate = null,
    endDate = null,
    limit = 500,
    offset = 0,
    sort = 'desc',
    cursor = null,
  } = {}) => {
    const params = new URLSearchParams({ case_id: caseId });
    if (fromKeys?.length) params.append('from_keys', fromKeys.join(','));
    if (toKeys?.length) params.append('to_keys', toKeys.join(','));
    if (participantKeys?.length) params.append('participant_keys', participantKeys.join(','));
    if (types?.length) params.append('types', types.join(','));
    if (reportKeys?.length) params.append('report_keys', reportKeys.join(','));
    if (sourceApps?.length) params.append('source_apps', sourceApps.join(','));
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    params.append('limit', String(limit));
    // When a cursor is supplied, omit `offset` — the server engages
    // keyset pagination and offset becomes a no-op. Send it only for
    // legacy callers that don't yet pass cursor.
    if (cursor) {
      params.append('cursor', cursor);
    } else {
      params.append('offset', String(offset));
    }
    if (sort) params.append('sort', sort);
    return fetchAPI(`/cellebrite/comms/between?${params.toString()}`);
  },

  /**
   * Full-text search across message bodies, email subjects/bodies and
   * call notes for the case. Returns:
   *   { query, thread_ids: [...], matches: [{message_id, thread_id,
   *     timestamp, source_app, report_key, snippet}], total }
   *
   * Used by Comms Center to narrow the thread list to threads-that-
   * mention the term and auto-open the first matching thread scrolled
   * to the matched message. Distinct from getThreads({search}) which
   * only matches thread metadata.
   */
  /**
   * Cheap aggregation across the comms feed shape — total count, per-type
   * counts, min/max date, per-day histogram. No item rows. Same filter
   * contract as getBetween() so the scrubber + tab counts can render
   * before any feed page returns.
   *
   * Returns { total, type_counts: {message, call, email}, min_date,
   *           max_date, histogram: [{date, count}] }
   */
  getEnvelope: (caseId, {
    fromKeys = null,
    toKeys = null,
    // Direction-agnostic involvement filter — see getThreads().
    participantKeys = null,
    types = null,
    reportKeys = null,
    sourceApps = null,
    startDate = null,
    endDate = null,
    signal = null,
  } = {}) => {
    const params = new URLSearchParams({ case_id: caseId });
    if (fromKeys?.length) params.append('from_keys', fromKeys.join(','));
    if (toKeys?.length) params.append('to_keys', toKeys.join(','));
    if (participantKeys?.length) params.append('participant_keys', participantKeys.join(','));
    if (types?.length) params.append('types', types.join(','));
    if (reportKeys?.length) params.append('report_keys', reportKeys.join(','));
    if (sourceApps?.length) params.append('source_apps', sourceApps.join(','));
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    return fetchAPI(`/cellebrite/comms/envelope?${params.toString()}`, signal ? { signal } : undefined);
  },

  searchMessages: (caseId, { q, reportKeys = null, limit = 200 } = {}) => {
    const params = new URLSearchParams({ case_id: caseId, q });
    if (reportKeys?.length) params.append('report_keys', reportKeys.join(','));
    params.append('limit', String(limit));
    return fetchAPI(`/cellebrite/comms/messages/search?${params.toString()}`);
  },

  /**
   * Resolve a Cellebrite file UUID to its evidence record.
   */
  resolveAttachment: (caseId, fileId) =>
    fetchAPI(
      `/cellebrite/comms/attachment/${encodeURIComponent(fileId)}?case_id=${encodeURIComponent(caseId)}`
    ),

  /**
   * Phase 9: All comms (calls + messages + emails) involving one contact,
   * across all (or selected) devices, sorted chronologically.
   */
  getContactFeed: (caseId, contactKey, {
    reportKeys = null,
    types = null,
    limit = 1000,
    offset = 0,
  } = {}) => {
    const params = new URLSearchParams({ case_id: caseId });
    if (reportKeys?.length) params.append('report_keys', reportKeys.join(','));
    if (types?.length) params.append('types', types.join(','));
    params.append('limit', String(limit));
    params.append('offset', String(offset));
    return fetchAPI(
      `/cellebrite/comms/contact-feed/${encodeURIComponent(contactKey)}?${params.toString()}`
    );
  },
};


/**
 * Cellebrite Location & Event Center API (Phase 4)
 */
export const cellebriteEventsAPI = {
  /**
   * Fetch per-event-type counts for the filter UI.
   */
  getEventTypes: (caseId, reportKeys = null) => {
    const params = new URLSearchParams({ case_id: caseId });
    if (reportKeys?.length) params.append('report_keys', reportKeys.join(','));
    return fetchAPI(`/cellebrite/events/types?${params.toString()}`);
  },

  /**
   * Fetch unified event feed for the map + timeline.
   */
  getEvents: (caseId, {
    reportKeys = null,
    eventTypes = null,
    sourceApps = null,
    startDate = null,
    endDate = null,
    onlyGeolocated = false,
    limit = 5000,
    offset = 0,
  } = {}) => {
    const params = new URLSearchParams({ case_id: caseId });
    if (reportKeys?.length) params.append('report_keys', reportKeys.join(','));
    if (eventTypes?.length) params.append('event_types', eventTypes.join(','));
    if (sourceApps?.length) params.append('source_apps', sourceApps.join(','));
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    if (onlyGeolocated) params.append('only_geolocated', 'true');
    params.append('limit', String(limit));
    params.append('offset', String(offset));
    return fetchAPI(`/cellebrite/events?${params.toString()}`);
  },

  /**
   * Tile-aggregated locations for the map at the requested zoom.
   * Returns per-cell counts + top source apps so 100K+ raw points
   * don't ship just to be clustered client-side. Use for zoom < 15.
   */
  getLocationTiles: (caseId, {
    zoom = 6,
    reportKeys = null,
    startDate = null,
    endDate = null,
    bbox = null,
  } = {}) => {
    const params = new URLSearchParams({ case_id: caseId, zoom: String(zoom) });
    if (reportKeys?.length) params.append('report_keys', reportKeys.join(','));
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    if (bbox && bbox.length === 4) {
      params.append('bbox', bbox.join(','));
    }
    return fetchAPI(`/cellebrite/locations/tiles?${params.toString()}`);
  },

  /**
   * Raw rows inside a single aggregated tile — used by the rail's
   * tile-contents view. cell_x/cell_y/cell_deg come straight from
   * a tiles response.
   */
  getLocationsInTile: (caseId, {
    cellX,
    cellY,
    cellDeg,
    reportKeys = null,
    startDate = null,
    endDate = null,
    limit = 200,
  } = {}) => {
    const params = new URLSearchParams({
      case_id: caseId,
      cell_x: String(cellX),
      cell_y: String(cellY),
      cell_deg: String(cellDeg),
      limit: String(limit),
    });
    if (reportKeys?.length) params.append('report_keys', reportKeys.join(','));
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    return fetchAPI(`/cellebrite/locations/in-tile?${params.toString()}`);
  },

  /**
   * Distinct value sets per searchable Location field for the search
   * typeahead. Returns one array per field (location_type, source_app,
   * country, admin1, place_name), each element {value, count}, sorted
   * by frequency. Covers the whole case rather than a 500-row sample.
   */
  getLocationSuggestionValues: (caseId, { reportKeys = null } = {}) => {
    const params = new URLSearchParams({ case_id: caseId });
    if (reportKeys?.length) params.append('report_keys', reportKeys.join(','));
    return fetchAPI(`/cellebrite/locations/suggestion-values?${params.toString()}`);
  },

  /**
   * Devices that visited a given (lat, lon) within `radiusM` metres.
   * Used by the location rail to show "this place was visited by N
   * devices" instead of just the one selected row's device.
   */
  getLocationVisitors: (caseId, { lat, lon, radiusM = 150 } = {}) => {
    const params = new URLSearchParams({
      case_id: caseId,
      lat: String(lat),
      lon: String(lon),
      radius_m: String(radiusM),
    });
    return fetchAPI(`/cellebrite/locations/visitors?${params.toString()}`);
  },

  /**
   * Per-device polyline tracks.
   */
  getTracks: (caseId, {
    reportKeys = null,
    startDate = null,
    endDate = null,
    simplify = true,
  } = {}) => {
    const params = new URLSearchParams({ case_id: caseId });
    if (reportKeys?.length) params.append('report_keys', reportKeys.join(','));
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    params.append('simplify', simplify ? 'true' : 'false');
    return fetchAPI(`/cellebrite/events/tracks?${params.toString()}`);
  },

  /**
   * Fetch full event detail (for the drawer).
   */
  getEventDetail: (caseId, nodeKey) =>
    fetchAPI(
      `/cellebrite/events/detail/${encodeURIComponent(nodeKey)}?case_id=${encodeURIComponent(caseId)}`
    ),

  /**
   * Fetch related comms for a clicked event — surrounding thread
   * messages + cross-channel pair window. Used by the rail accordion
   * to give the user one-click drill-in to the conversation context
   * and any nearby calls/emails between the same parties.
   *
   * Returns { anchor, thread: [...], around: [...] }. Both lists are
   * empty for non-comms anchors (Location, CellTower, etc.) — caller
   * should hide their sub-sections in that case.
   */
  getEventRelated: (caseId, nodeKey, { windowH = 24, limit = 50 } = {}) =>
    fetchAPI(
      `/cellebrite/events/${encodeURIComponent(nodeKey)}/related`
        + `?case_id=${encodeURIComponent(caseId)}`
        + `&window_h=${windowH}`
        + `&limit=${limit}`
    ),

  /**
   * Roll up all Person nodes by canonical (E.164) phone number — so
   * the same human across multiple phones, even with different alias
   * names, surfaces as one row with the alias list attached. Used by
   * the Contacts (unified) tab and the Comms entity filter's
   * "Group by number" toggle.
   *
   * reportKeys, when provided, scopes the rollup to those phones; the
   * counts and aliases reflect only what those phones see. When
   * omitted, rolls up across the whole case.
   */
  getUnifiedContacts: (caseId, {
    reportKeys = null,
    search = null,
    limit = 500,
    offset = 0,
  } = {}) => {
    const qs = new URLSearchParams({
      case_id: caseId,
      limit: String(limit),
      offset: String(offset),
    });
    if (reportKeys && reportKeys.length) {
      qs.set('report_keys', reportKeys.join(','));
    }
    if (search) qs.set('search', search);
    return fetchAPI(`/cellebrite/contacts/unified?${qs.toString()}`);
  },

  /**
   * Run one or more intersection detection methods on demand.
   * methods: array of "spatial"|"cell_tower"|"wifi"|"comm_hub"|"convoy"
   * params: optional per-method param object
   */
  runIntersections: (caseId, {
    methods,
    reportKeys = null,
    startDate = null,
    endDate = null,
    params = null,
  }) =>
    fetchAPI(`/cellebrite/intersections/run?case_id=${encodeURIComponent(caseId)}`, {
      method: 'POST',
      body: {
        methods,
        report_keys: reportKeys,
        start_date: startDate,
        end_date: endDate,
        params,
      },
    }),
};


/**
 * Cellebrite Overview drill-down API (Phase 8)
 *
 * Six per-category endpoints scoped to a single (caseId, reportKey) pair so
 * the Overview tab can drill into Contacts / Calls / Messages / Locations /
 * Emails for one device at a time.
 */
function _buildOverviewParams(caseId, reportKey, { search = null, limit = 500, offset = 0 } = {}) {
  const p = new URLSearchParams({ case_id: caseId, report_key: reportKey });
  if (search) p.append('search', search);
  p.append('limit', String(limit));
  p.append('offset', String(offset));
  return p;
}

export const cellebriteOverviewAPI = {
  getContacts: (caseId, reportKey, opts = {}) =>
    fetchAPI(`/cellebrite/overview/contacts?${_buildOverviewParams(caseId, reportKey, opts).toString()}`),
  getCalls: (caseId, reportKey, opts = {}) =>
    fetchAPI(`/cellebrite/overview/calls?${_buildOverviewParams(caseId, reportKey, opts).toString()}`),
  getMessages: (caseId, reportKey, opts = {}) =>
    fetchAPI(`/cellebrite/overview/messages?${_buildOverviewParams(caseId, reportKey, opts).toString()}`),
  getLocations: (caseId, reportKey, opts = {}) =>
    fetchAPI(`/cellebrite/overview/locations?${_buildOverviewParams(caseId, reportKey, opts).toString()}`),
  getEmails: (caseId, reportKey, opts = {}) =>
    fetchAPI(`/cellebrite/overview/emails?${_buildOverviewParams(caseId, reportKey, opts).toString()}`),
  getContactDetail: (caseId, reportKey, contactKey) => {
    const p = new URLSearchParams({ case_id: caseId, report_key: reportKey });
    return fetchAPI(`/cellebrite/overview/contact/${encodeURIComponent(contactKey)}?${p.toString()}`);
  },
  // Investigator-asserted identity merge: fold secondaryKeys (a contact's other
  // numbers/handles) into primaryKey. The system never auto-merges different
  // numbers, so this is a deliberate human action (recorded on the survivor).
  mergePersons: (caseId, primaryKey, secondaryKeys) => {
    const p = new URLSearchParams({ case_id: caseId });
    return fetchAPI(`/cellebrite/persons/merge?${p.toString()}`, {
      method: 'POST',
      body: JSON.stringify({ primary_key: primaryKey, secondary_keys: secondaryKeys }),
    });
  },
  // Search persons by name / number / key for the merge picker — returns
  // candidates with their activity + device span so the investigator selects
  // a real entity rather than typing a key.
  searchPersons: (caseId, q, { excludeKey = null, limit = 20 } = {}) => {
    const p = new URLSearchParams({ case_id: caseId, q });
    if (excludeKey) p.append('exclude_key', excludeKey);
    p.append('limit', String(limit));
    return fetchAPI(`/cellebrite/persons/search?${p.toString()}`);
  },
};


/**
 * Cellebrite Files Explorer API (Phase 5)
 */
export const cellebriteFilesAPI = {
  list: (caseId, {
    reportKeys = null,
    category = null,
    parentLabel = null,
    sourceApp = null,
    devicePath = null,
    tag = null,
    entityId = null,
    search = null,
    onlyRelevant = false,
    // EXIF / geotag filters. captureAfter/Before are YYYY-MM-DD strings;
    // hasGeotag is tri-state (null = no filter, true / false explicit).
    // Server applies these against capture_time (EXIF DateTimeOriginal)
    // and falls back to creation_time when capture_time is absent.
    captureAfter = null,
    captureBefore = null,
    hasGeotag = null,
    limit = 500,
    offset = 0,
  } = {}) => {
    const params = new URLSearchParams({ case_id: caseId });
    if (reportKeys?.length) params.append('report_keys', reportKeys.join(','));
    if (category) params.append('category', category);
    if (parentLabel) params.append('parent_label', parentLabel);
    if (sourceApp) params.append('source_app', sourceApp);
    if (devicePath) params.append('device_path', devicePath);
    if (tag) params.append('tag', tag);
    if (entityId) params.append('entity_id', entityId);
    if (search) params.append('search', search);
    if (onlyRelevant) params.append('only_relevant', 'true');
    if (captureAfter) params.append('capture_after', captureAfter);
    if (captureBefore) params.append('capture_before', captureBefore);
    if (hasGeotag === true) params.append('has_geotag', 'true');
    else if (hasGeotag === false) params.append('has_geotag', 'false');
    params.append('limit', String(limit));
    params.append('offset', String(offset));
    return fetchAPI(`/cellebrite/files?${params.toString()}`);
  },

  tree: (caseId, {
    reportKeys = null,
    groupBy = 'category',
  } = {}) => {
    const params = new URLSearchParams({ case_id: caseId, group_by: groupBy });
    if (reportKeys?.length) params.append('report_keys', reportKeys.join(','));
    return fetchAPI(`/cellebrite/files/tree?${params.toString()}`);
  },
};


/**
 * Evidence tag + entity-link extensions (Phase 5)
 */
export const evidenceTagsAPI = {
  addTags: (caseId, evidenceIds, tags) =>
    fetchAPI('/evidence/tags/add', {
      method: 'POST',
      body: { case_id: caseId, evidence_ids: evidenceIds, tags },
    }),
  removeTags: (caseId, evidenceIds, tags) =>
    fetchAPI('/evidence/tags/remove', {
      method: 'POST',
      body: { case_id: caseId, evidence_ids: evidenceIds, tags },
    }),
  setTags: (caseId, evidenceId, tags) =>
    fetchAPI('/evidence/tags/set', {
      method: 'POST',
      body: { case_id: caseId, evidence_id: evidenceId, tags },
    }),
  getCaseTags: (caseId) =>
    fetchAPI(`/evidence/tags?case_id=${encodeURIComponent(caseId)}`),
  linkEntities: (caseId, evidenceIds, entityIds) =>
    fetchAPI('/evidence/entity-links/add', {
      method: 'POST',
      body: { case_id: caseId, evidence_ids: evidenceIds, entity_ids: entityIds },
    }),
  unlinkEntities: (caseId, evidenceIds, entityIds) =>
    fetchAPI('/evidence/entity-links/remove', {
      method: 'POST',
      body: { case_id: caseId, evidence_ids: evidenceIds, entity_ids: entityIds },
    }),
  listByEntity: (caseId, entityId) =>
    fetchAPI(`/evidence/by-entity?case_id=${encodeURIComponent(caseId)}&entity_id=${encodeURIComponent(entityId)}`),
};


/**
 * Case Entity Profiles API (Phase 5)
 */
export const entitiesAPI = {
  list: (caseId, { entityType = null, search = null, status = 'active', limit = 500 } = {}) => {
    const params = new URLSearchParams({ case_id: caseId, status, limit: String(limit) });
    if (entityType) params.append('entity_type', entityType);
    if (search) params.append('search', search);
    return fetchAPI(`/entities?${params.toString()}`);
  },
  get: (caseId, entityId) =>
    fetchAPI(`/entities/${encodeURIComponent(entityId)}?case_id=${encodeURIComponent(caseId)}`),
  create: (caseId, data) =>
    fetchAPI('/entities', {
      method: 'POST',
      body: { case_id: caseId, ...data },
    }),
  update: (caseId, entityId, data) =>
    fetchAPI(`/entities/${encodeURIComponent(entityId)}`, {
      method: 'PATCH',
      body: { case_id: caseId, ...data },
    }),
  archive: (caseId, entityId) =>
    fetchAPI(
      `/entities/${encodeURIComponent(entityId)}/archive?case_id=${encodeURIComponent(caseId)}`,
      { method: 'POST' }
    ),
  delete: (caseId, entityId) =>
    fetchAPI(
      `/entities/${encodeURIComponent(entityId)}?case_id=${encodeURIComponent(caseId)}`,
      { method: 'DELETE' }
    ),
  linkNode: (caseId, entityId, nodeKey) =>
    fetchAPI(`/entities/${encodeURIComponent(entityId)}/link/node`, {
      method: 'POST',
      body: { case_id: caseId, node_key: nodeKey },
    }),
  unlinkNode: (caseId, entityId, nodeKey) =>
    fetchAPI(`/entities/${encodeURIComponent(entityId)}/unlink/node`, {
      method: 'POST',
      body: { case_id: caseId, node_key: nodeKey },
    }),
  linkEvidence: (caseId, entityId, evidenceIds) =>
    fetchAPI(`/entities/${encodeURIComponent(entityId)}/link/evidence`, {
      method: 'POST',
      body: { case_id: caseId, evidence_ids: evidenceIds },
    }),
  unlinkEvidence: (caseId, entityId, evidenceIds) =>
    fetchAPI(`/entities/${encodeURIComponent(entityId)}/unlink/evidence`, {
      method: 'POST',
      body: { case_id: caseId, evidence_ids: evidenceIds },
    }),
  getContext: (caseId, entityId) =>
    fetchAPI(`/entities/${encodeURIComponent(entityId)}/context?case_id=${encodeURIComponent(caseId)}`),
};

/**
 * Case Profiles API — user-facing alias for entitiesAPI.
 *
 * "Profile" is the new investigator-facing name for what the backend
 * still stores as `:CaseEntity`. Same routes, same payloads — this is
 * here so new code can `import { caseProfilesAPI }` without leaking
 * the legacy name into call-sites. Old `entitiesAPI` consumers keep
 * working unchanged.
 *
 * Note: not just `profilesAPI` because that name is already taken by
 * the LLM-ingestion profiles API earlier in this file. Hence the
 * `case` qualifier — matches the backend route /api/case-profiles.
 */
export const caseProfilesAPI = entitiesAPI;


/**
 * Triage API
 */
export const triageAPI = {
  // Filesystem browse
  browseDirectory: (path = '/') =>
    fetchAPI(`/triage/browse?path=${encodeURIComponent(path)}`),
  // Case CRUD
  createCase: (data) =>
    fetchAPI('/triage/cases', { method: 'POST', body: data }),
  listCases: () =>
    fetchAPI('/triage/cases'),
  getCase: (caseId) =>
    fetchAPI(`/triage/cases/${encodeURIComponent(caseId)}`),
  deleteCase: (caseId) =>
    fetchAPI(`/triage/cases/${encodeURIComponent(caseId)}`, { method: 'DELETE' }),

  // Scan
  startScan: (caseId, resume = false) =>
    fetchAPI(`/triage/cases/${encodeURIComponent(caseId)}/scan`, {
      method: 'POST', body: { resume },
    }),
  getStats: (caseId) =>
    fetchAPI(`/triage/cases/${encodeURIComponent(caseId)}/stats`),
  getFiles: (caseId, params = {}) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== null && v !== undefined && v !== '') qs.append(k, String(v));
    });
    return fetchAPI(`/triage/cases/${encodeURIComponent(caseId)}/files?${qs.toString()}`);
  },

  // Classification (Phase 2)
  startClassification: (caseId) =>
    fetchAPI(`/triage/cases/${encodeURIComponent(caseId)}/classify`, { method: 'POST' }),
  getClassification: (caseId) =>
    fetchAPI(`/triage/cases/${encodeURIComponent(caseId)}/classification`),
  uploadHashSet: (caseId, data) =>
    fetchAPI(`/triage/cases/${encodeURIComponent(caseId)}/hash-sets`, { method: 'POST', body: data }),
  uploadYaraRules: (caseId, formData) =>
    fetchAPI(`/triage/cases/${encodeURIComponent(caseId)}/yara-rules`, {
      method: 'POST', body: formData, headers: {},
    }),

  // Profile (Phase 3)
  generateProfile: (caseId) =>
    fetchAPI(`/triage/cases/${encodeURIComponent(caseId)}/profile`, { method: 'POST' }),
  getProfile: (caseId) =>
    fetchAPI(`/triage/cases/${encodeURIComponent(caseId)}/profile`),
  getTimeline: (caseId) =>
    fetchAPI(`/triage/cases/${encodeURIComponent(caseId)}/timeline`),
  getArtifacts: (caseId) =>
    fetchAPI(`/triage/cases/${encodeURIComponent(caseId)}/artifacts`),
  getMismatches: (caseId) =>
    fetchAPI(`/triage/cases/${encodeURIComponent(caseId)}/mismatches`),

  // Processors (Phase 4)
  listProcessors: () =>
    fetchAPI('/triage/processors'),
  createStage: (caseId, data) =>
    fetchAPI(`/triage/cases/${encodeURIComponent(caseId)}/stages`, { method: 'POST', body: data }),
  executeStage: (caseId, stageId, data = {}) =>
    fetchAPI(`/triage/cases/${encodeURIComponent(caseId)}/stages/${encodeURIComponent(stageId)}/execute`, {
      method: 'POST', body: data,
    }),
  getStageResults: (caseId, stageId, params = {}) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== null && v !== undefined) qs.append(k, String(v));
    });
    return fetchAPI(`/triage/cases/${encodeURIComponent(caseId)}/stages/${encodeURIComponent(stageId)}/results?${qs.toString()}`);
  },
  getFileProvenance: (caseId, fileId) =>
    fetchAPI(`/triage/cases/${encodeURIComponent(caseId)}/files/${encodeURIComponent(fileId)}/provenance`),
  getFileArtifacts: (caseId, fileId) =>
    fetchAPI(`/triage/cases/${encodeURIComponent(caseId)}/files/${encodeURIComponent(fileId)}/artifacts`),

  // Advisor (Phase 5)
  advisorChat: (caseId, data) =>
    fetchAPI(`/triage/cases/${encodeURIComponent(caseId)}/advisor/chat`, { method: 'POST', body: data }),
  advisorSuggest: (caseId) =>
    fetchAPI(`/triage/cases/${encodeURIComponent(caseId)}/advisor/suggest`),

  // Templates (Phase 5)
  listTemplates: () =>
    fetchAPI('/triage/templates'),
  createTemplate: (caseId, data) =>
    fetchAPI(`/triage/cases/${encodeURIComponent(caseId)}/templates`, { method: 'POST', body: data }),
  applyTemplate: (caseId, data) =>
    fetchAPI(`/triage/cases/${encodeURIComponent(caseId)}/apply-template`, { method: 'POST', body: data }),
  deleteTemplate: (templateId) =>
    fetchAPI(`/triage/templates/${encodeURIComponent(templateId)}`, { method: 'DELETE' }),

  // Ingest (Phase 6)
  ingestPreview: (caseId, data) =>
    fetchAPI(`/triage/cases/${encodeURIComponent(caseId)}/ingest-preview`, { method: 'POST', body: data }),
  ingest: (caseId, data) =>
    fetchAPI(`/triage/cases/${encodeURIComponent(caseId)}/ingest`, { method: 'POST', body: data }),
};