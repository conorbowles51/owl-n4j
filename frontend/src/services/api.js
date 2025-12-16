/**
 * API Service - handles all backend communication
 */

const API_BASE = '/api';

/**
 * Fetch wrapper with error handling
 */
async function fetchAPI(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  
  const defaultHeaders = {
    'Content-Type': 'application/json',
  };

  const token = localStorage.getItem('authToken');
  if (token) {
    defaultHeaders.Authorization = `Bearer ${token}`;
  }

  const config = {
    credentials: options.credentials || 'include',
    ...options,
    headers: {
      ...defaultHeaders,
      ...options.headers,
    },
  };

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
 * Artifacts API
 */
export const artifactsAPI = {
  /**
   * Create a new artifact
   */
  create: (artifact) => 
    fetchAPI('/artifacts', {
      method: 'POST',
      body: JSON.stringify(artifact),
    }),

  /**
   * List all artifacts
   */
  list: () => fetchAPI('/artifacts'),

  /**
   * Get a specific artifact
   */
  get: (artifactId) => fetchAPI(`/artifacts/${encodeURIComponent(artifactId)}`),

  /**
   * Delete an artifact
   */
  delete: (artifactId) => 
    fetchAPI(`/artifacts/${encodeURIComponent(artifactId)}`, {
      method: 'DELETE',
    }),
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