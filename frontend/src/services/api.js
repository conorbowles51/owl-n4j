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

  const response = await fetch(url, config);
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
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
};

/**
 * Chat API
 */
export const chatAPI = {
  /**
   * Send a question to the AI
   */
  ask: (question, selectedKeys = null) => 
    fetchAPI('/chat', {
      method: 'POST',
      body: JSON.stringify({
        question,
        selected_keys: selectedKeys,
      }),
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
   */
  create: (snapshot) => 
    fetchAPI('/snapshots', {
      method: 'POST',
      body: JSON.stringify(snapshot),
    }),

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
  list: () => fetchAPI('/cases'),

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
   * Upload one or more evidence files for a case
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
   * Process selected evidence files synchronously
   */
  process: (caseId, fileIds) =>
    fetchAPI('/evidence/process', {
      method: 'POST',
      body: JSON.stringify({
        case_id: caseId,
        file_ids: fileIds,
      }),
    }),

  /**
   * Process selected evidence files in the background (returns task_id)
   */
  processBackground: (caseId, fileIds) =>
    fetchAPI('/evidence/process/background', {
      method: 'POST',
      body: JSON.stringify({
        case_id: caseId,
        file_ids: fileIds,
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
};

/**
 * Authentication API
 */
export const authAPI = {
  login: ({ username, password }) =>
    fetchAPI('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),

  logout: () =>
    fetchAPI('/auth/logout', {
      method: 'POST',
    }),

  me: () =>
    fetchAPI('/auth/me', {
      method: 'GET',
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