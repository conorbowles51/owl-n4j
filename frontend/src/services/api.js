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
      throw new Error(error.detail || `HTTP ${response.status}`);
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
   * @param {string} options.start_date - Filter start date (YYYY-MM-DD)
   * @param {string} options.end_date - Filter end date (YYYY-MM-DD)
   */
  getGraph: ({ start_date, end_date } = {}) => {
    const params = new URLSearchParams();
    if (start_date) params.append('start_date', start_date);
    if (end_date) params.append('end_date', end_date);
    
    const queryString = params.toString();
    return fetchAPI(`/graph${queryString ? `?${queryString}` : ''}`);
  },

  /**
   * Get details for a specific node
   */
  getNodeDetails: (key) => fetchAPI(`/graph/node/${encodeURIComponent(key)}`),

  /**
   * Get a node and its neighbours
   */
  getNodeNeighbours: (key, depth = 1) => 
    fetchAPI(`/graph/node/${encodeURIComponent(key)}/neighbours?depth=${depth}`),

  /**
   * Search nodes
   */
  search: (query, limit = 20) => 
    fetchAPI(`/graph/search?q=${encodeURIComponent(query)}&limit=${limit}`),

  /**
   * Get graph summary
   */
  getSummary: () => fetchAPI('/graph/summary'),

  /**
   * Get subgraph with shortest paths between selected nodes
   */
  getShortestPaths: (nodeKeys, maxDepth = 10) =>
    fetchAPI('/graph/shortest-paths', {
      method: 'POST',
      body: JSON.stringify({
        node_keys: nodeKeys,
        max_depth: maxDepth,
      }),
    }),

  /**
   * Expand multiple nodes by N hops
   */
  expandNodes: (nodeKeys, depth = 1) =>
    fetchAPI('/graph/expand-nodes', {
      method: 'POST',
      body: JSON.stringify({
        node_keys: nodeKeys,
        depth: depth,
      }),
    }),

  /**
   * Find similar entities for resolution
   */
  findSimilarEntities: (entityTypes = null, similarityThreshold = 0.7, maxResults = 50) =>
    fetchAPI('/graph/find-similar-entities', {
      method: 'POST',
      body: JSON.stringify({
        entity_types: entityTypes,
        name_similarity_threshold: similarityThreshold,
        max_results: maxResults,
      }),
    }),

  /**
   * Merge two entities
   */
  mergeEntities: (sourceKey, targetKey, mergedData) =>
    fetchAPI('/graph/merge-entities', {
      method: 'POST',
      body: JSON.stringify({
        source_key: sourceKey,
        target_key: targetKey,
        merged_data: mergedData,
      }),
    }),

  /**
   * Delete a node and all its relationships
   */
  deleteNode: (nodeKey) =>
    fetchAPI(`/graph/node/${encodeURIComponent(nodeKey)}`, {
      method: 'DELETE',
    }),

  /**
   * Get influential nodes using PageRank algorithm
   */
  getPageRank: (nodeKeys = null, topN = 20, iterations = 20, dampingFactor = 0.85) =>
    fetchAPI('/graph/pagerank', {
      method: 'POST',
      body: JSON.stringify({
        node_keys: nodeKeys,
        top_n: topN,
        iterations: iterations,
        damping_factor: dampingFactor,
      }),
    }),

  /**
   * Get communities using Louvain modularity algorithm
   */
  getLouvainCommunities: (nodeKeys = null, resolution = 1.0, maxIterations = 10) =>
    fetchAPI('/graph/louvain', {
      method: 'POST',
      body: JSON.stringify({
        node_keys: nodeKeys,
        resolution: resolution,
        max_iterations: maxIterations,
      }),
    }),

  /**
   * Get nodes with highest betweenness centrality
   */
  getBetweennessCentrality: (nodeKeys = null, topN = 20, normalized = true) =>
    fetchAPI('/graph/betweenness-centrality', {
      method: 'POST',
      body: JSON.stringify({
        node_keys: nodeKeys,
        top_n: topN,
        normalized: normalized,
      }),
    }),

  /**
   * Load a case by executing Cypher queries
   */
  loadCase: (cypherQueries) =>
    fetchAPI('/graph/load-case', {
      method: 'POST',
      body: JSON.stringify({
        cypher_queries: cypherQueries,
      }),
    }),

  /**
   * Execute a single Cypher query (for case loading with progress)
   */
  executeSingleQuery: (query) =>
    fetchAPI('/graph/execute-single-query', {
      method: 'POST',
      body: JSON.stringify({
        query: query,
      }),
    }),

  /**
   * Execute multiple Cypher queries in batches (faster for large cases)
   * @param {string[]} queries - Array of Cypher query strings
   * @param {number} batchSize - Number of queries per batch (default: 50)
   */
  executeBatchQueries: (queries, batchSize = 50) =>
    fetchAPI('/graph/execute-batch-queries', {
      method: 'POST',
      body: JSON.stringify({
        queries: queries,
        batch_size: batchSize,
      }),
    }),

  /**
   * Clear the current graph, saving its Cypher as the "last graph"
   */
  clearGraph: () =>
    fetchAPI('/graph/clear-graph', {
      method: 'POST',
    }),

  /**
   * Get the last-cleared graph's Cypher (if any)
   */
  getLastGraph: () => fetchAPI('/graph/last-graph'),

  /**
   * Get all entity types in the graph with their counts
   */
  getEntityTypes: () => fetchAPI('/graph/entity-types'),

  /**
   * Create a new node in the graph
   */
  createNode: (nodeData) =>
    fetchAPI('/graph/create-node', {
      method: 'POST',
      body: JSON.stringify({
        name: nodeData.name,
        type: nodeData.type,
        description: nodeData.description,
        summary: nodeData.summary,
      }),
    }),

  /**
   * Create relationships between nodes
   */
  createRelationships: (relationships) =>
    fetchAPI('/graph/relationships', {
      method: 'POST',
      body: JSON.stringify({ relationships }),
    }),

  /**
   * Analyze relationships for a node
   */
  analyzeNodeRelationships: (nodeKey) =>
    fetchAPI(`/graph/analyze-relationships/${encodeURIComponent(nodeKey)}`, {
      method: 'POST',
    }),

  /**
   * Update node properties (name, summary, and/or notes)
   */
  updateNode: (nodeKey, updates) =>
    fetchAPI(`/graph/node/${encodeURIComponent(nodeKey)}`, {
      method: 'PUT',
      body: JSON.stringify({
        name: updates.name,
        summary: updates.summary,
        notes: updates.notes,
      }),
    }),

  /**
   * Get entities with geocoded locations for map display
   * @param {Object} options - Filter options
   * @param {string} options.types - Comma-separated entity types to filter
   */
  getLocations: ({ types } = {}) => {
    const params = new URLSearchParams();
    if (types) params.append('types', types);

    const queryString = params.toString();
    return fetchAPI(`/graph/locations${queryString ? `?${queryString}` : ''}`);
  },

  /**
   * Toggle pin status for a verified fact
   * @param {string} nodeKey - Node key
   * @param {number} factIndex - Index of the fact in verified_facts array
   * @param {boolean} pinned - Whether to pin (true) or unpin (false)
   */
  pinFact: (nodeKey, factIndex, pinned) =>
    fetchAPI(`/graph/node/${encodeURIComponent(nodeKey)}/pin-fact`, {
      method: 'PUT',
      body: JSON.stringify({
        fact_index: factIndex,
        pinned: pinned,
      }),
    }),

  /**
   * Convert an AI insight to a verified fact
   * @param {string} nodeKey - Node key
   * @param {number} insightIndex - Index of the insight in ai_insights array
   * @param {string} username - Username of the verifying investigator
   * @param {string} [sourceDoc] - Optional source document reference
   * @param {number} [page] - Optional page number
   */
  verifyInsight: (nodeKey, insightIndex, username, sourceDoc = null, page = null) =>
    fetchAPI(`/graph/node/${encodeURIComponent(nodeKey)}/verify-insight`, {
      method: 'POST',
      body: JSON.stringify({
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
  getSuggestions: (selectedKeys = null) => 
    fetchAPI('/chat/suggestions', {
      method: 'POST',
      body: JSON.stringify({
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
   * @param {string} options.types - Comma-separated event types
   * @param {string} options.startDate - Filter start date (YYYY-MM-DD)
   * @param {string} options.endDate - Filter end date (YYYY-MM-DD)
   */
  getEvents: async ({ types, startDate, endDate } = {}) => {
    const params = new URLSearchParams();
    if (types) params.append('types', types);
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    
    const queryString = params.toString();
    const response = await fetchAPI(`/timeline${queryString ? `?${queryString}` : ''}`);
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
 */
export const casesAPI = {
  /**
   * Save a new version of a case
   */
  save: (caseData) => 
    fetchAPI('/cases', {
      method: 'POST',
      body: JSON.stringify(caseData),
    }),

  /**
   * List all cases
   */
  list: () => fetchAPI('/cases', {
    timeout: 60000, // 60 seconds for cases (may have large snapshot data)
  }),

  /**
   * Get a specific case with all versions
   */
  get: (caseId) => fetchAPI(`/cases/${encodeURIComponent(caseId)}`),

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