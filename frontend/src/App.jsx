import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { 
  Network, 
  MessageSquare, 
  RefreshCw, 
  Loader2,
  AlertCircle,
  Calendar,
  Layout,
  X,
  Save,
  Archive,
  ChevronDown,
  GitBranch,
  CheckSquare
} from 'lucide-react';
import { graphAPI, artifactsAPI, timelineAPI, authAPI } from './services/api';
import GraphView from './components/GraphView';
import NodeDetails from './components/NodeDetails';
import ChatPanel from './components/ChatPanel';
import ContextMenu from './components/ContextMenu';
import SearchBar from './components/SearchBar';
import GraphSearchFilter from './components/GraphSearchFilter';
import TimelineView from './components/timeline/TimelineView';
import ArtifactModal from './components/ArtifactModal';
import ArtifactList from './components/ArtifactList';
import DateRangeFilter from './components/DateRangeFilter';
import { exportArtifactToPDF } from './utils/pdfExport';
import { parseSearchQuery, matchesQuery } from './utils/searchParser';  
import LoginPanel from './components/LoginPanel';

/**
 * Main App Component
 */
export default function App() {
  // View mode state
  const [viewMode, setViewMode] = useState('graph'); // 'graph' or 'timeline'
  // Graph state
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [fullGraphData, setFullGraphData] = useState({ nodes: [], links: [] }); // Store unfiltered graph
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dateRange, setDateRange] = useState({ start_date: null, end_date: null });
  const [graphSearchTerm, setGraphSearchTerm] = useState('');
  const [graphSearchMode, setGraphSearchMode] = useState('filter');
  const [pendingGraphSearch, setPendingGraphSearch] = useState('');

  // Selection state - support multiple nodes
  const [selectedNodes, setSelectedNodes] = useState([]); // Array of node objects
  const [selectedNodesDetails, setSelectedNodesDetails] = useState([]); // Array of node details
  
  // Subgraph state - separate from selection so nodes can be selected without being in subgraph
  const [subgraphNodeKeys, setSubgraphNodeKeys] = useState([]); // Keys of nodes that are in the subgraph
  
  // Timeline context - separate from selection so inspecting events doesn't filter timeline
  const [timelineContextKeys, setTimelineContextKeys] = useState([]); // Keys that define what events show on timeline

  // Context menu state
  const [contextMenu, setContextMenu] = useState(null);

  // Chat panel state
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [chatHistory, setChatHistory] = useState([]); // Track chat messages

  // Artifacts state
  const [artifacts, setArtifacts] = useState([]);
  const [showArtifactModal, setShowArtifactModal] = useState(false);
  const [showArtifactList, setShowArtifactList] = useState(false);
  const subgraphGraphRef = useRef(null); // Ref to subgraph GraphView for PDF export
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [authUsername, setAuthUsername] = useState('');
  const [showLoginPanel, setShowLoginPanel] = useState(false);
  const [isAccountDropdownOpen, setIsAccountDropdownOpen] = useState(false);
  const accountDropdownRef = useRef(null);
  const logoButtonRef = useRef(null);

  useEffect(() => {
    async function loadUser() {
      try {
        const current = await authAPI.me();
        setIsAuthenticated(true);
        setAuthUsername(current.username);
      } catch {
        setIsAuthenticated(false);
        setAuthUsername('');
        localStorage.removeItem('authToken');
      }
    }

    loadUser();
  }, []);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (
        isAccountDropdownOpen &&
        accountDropdownRef.current &&
        logoButtonRef.current &&
        !accountDropdownRef.current.contains(event.target) &&
        !logoButtonRef.current.contains(event.target)
      ) {
        setIsAccountDropdownOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isAccountDropdownOpen]);

  const handleLoginSuccess = useCallback((token, username) => {
    localStorage.setItem('authToken', token);
    setIsAuthenticated(true);
    setAuthUsername(username);
    setIsAccountDropdownOpen(false);
  }, []);

  const handleLogout = useCallback(async () => {
    try {
      await authAPI.logout();
    } catch {
      // ignore
    }
    localStorage.removeItem('authToken');
    setIsAuthenticated(false);
    setAuthUsername('');
    setIsAccountDropdownOpen(false);
  }, []);


  // Pane view state (single or split)
  const [paneViewMode, setPaneViewMode] = useState('single'); // 'single' or 'split'
  
  // Subgraph menu state
  const [isSubgraphMenuOpen, setIsSubgraphMenuOpen] = useState(false);
  const subgraphMenuRef = useRef(null);
  
  // Path-based subgraph state (for shortest paths feature)
  const [pathSubgraphData, setPathSubgraphData] = useState(null);

  // Dimensions
  const [dimensions, setDimensions] = useState({
    width: window.innerWidth,
    height: window.innerHeight,
  });

  // Apply search filter to graph data
  const applyGraphFilter = useCallback((data, searchTerm) => {
    if (!searchTerm) {
      setGraphData(data);
      return;
    }

    // Parse the search query
    const queryAST = parseSearchQuery(searchTerm);
    
    // Filter nodes that match the query
    const matchingNodes = data.nodes.filter(node => {
      return matchesQuery(queryAST, node);
    });

    const matchingNodeKeys = new Set(matchingNodes.map(n => n.key));

    // Filter links to only include connections between matching nodes
    const matchingLinks = data.links.filter(link => {
      const sourceKey = typeof link.source === 'string' ? link.source : link.source.key;
      const targetKey = typeof link.target === 'string' ? link.target : link.target.key;
      return matchingNodeKeys.has(sourceKey) && matchingNodeKeys.has(targetKey);
    });

    setGraphData({ nodes: matchingNodes, links: matchingLinks });
  }, []);

  // Load graph data
  const loadGraph = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await graphAPI.getGraph({
        start_date: dateRange.start_date,
        end_date: dateRange.end_date,
      });
      setFullGraphData(data);
      // Apply search filter if exists
      applyGraphFilter(data, graphSearchTerm);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [dateRange, graphSearchTerm, applyGraphFilter]);

  // Initial load - only reload when date range changes
  useEffect(() => {
    loadGraph();
  }, [dateRange]); // Only reload when date range changes, not search term

  // Apply search filter when full graph data or search term changes
  useEffect(() => {
    if (fullGraphData.nodes.length > 0) {
      applyGraphFilter(fullGraphData, graphSearchTerm);
    }
  }, [fullGraphData, graphSearchTerm, applyGraphFilter]);

  // Handle graph search filter change
  const handleGraphFilterChange = useCallback((searchTerm) => {
    setGraphSearchTerm(searchTerm);
  }, []);

  const handleGraphQueryChange = useCallback((searchTerm) => {
    setPendingGraphSearch(searchTerm);
    if (graphSearchMode === 'filter') {
      setGraphSearchTerm(searchTerm);
    }
  }, [graphSearchMode]);

  const handleGraphSearchExecute = useCallback(() => {
    setGraphSearchTerm(pendingGraphSearch);
  }, [pendingGraphSearch]);

  const handleGraphModeChange = useCallback((mode) => {
    setGraphSearchMode(mode);
    if (mode === 'filter') {
      setGraphSearchTerm(pendingGraphSearch);
    }
  }, [pendingGraphSearch]);

  // Handle window resize
  useEffect(() => {
    const handleResize = () => {
      setDimensions({
        width: window.innerWidth,
        height: window.innerHeight,
      });
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Close subgraph menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (subgraphMenuRef.current && !subgraphMenuRef.current.contains(e.target)) {
        setIsSubgraphMenuOpen(false);
      }
    };

    if (isSubgraphMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isSubgraphMenuOpen]);

  // Debounce timer ref for loadNodeDetails
  const loadNodeDetailsTimerRef = useRef(null);

  // Load node details for multiple nodes with throttling and debouncing
  const loadNodeDetails = useCallback(async (keys) => {
    if (!keys || keys.length === 0) {
      setSelectedNodesDetails([]);
      return;
    }

    // Clear any pending debounce timer
    if (loadNodeDetailsTimerRef.current) {
      clearTimeout(loadNodeDetailsTimerRef.current);
    }

    // Debounce: wait 100ms for more updates before fetching
    loadNodeDetailsTimerRef.current = setTimeout(async () => {
      try {
        // Limit concurrent requests to avoid ERR_INSUFFICIENT_RESOURCES
        const BATCH_SIZE = 10; // Process 10 nodes at a time
        const details = [];
        
        for (let i = 0; i < keys.length; i += BATCH_SIZE) {
          const batch = keys.slice(i, i + BATCH_SIZE);
          const batchPromises = batch.map(key => graphAPI.getNodeDetails(key));
          const batchResults = await Promise.all(batchPromises);
          details.push(...batchResults);
          
          // Small delay between batches to avoid overwhelming the browser
          if (i + BATCH_SIZE < keys.length) {
            await new Promise(resolve => setTimeout(resolve, 50));
          }
        }
        
        setSelectedNodesDetails(details);
      } catch (err) {
        console.error('Failed to load node details:', err);
        // Set empty array on error to avoid stale data
        setSelectedNodesDetails([]);
      }
    }, 100);
  }, []);

  // Handle bulk node selection (for drag selection)
  const handleBulkNodeSelect = useCallback((nodes) => {
    setSelectedNodes(nodes);
    const keys = nodes.map(n => n.key);
    loadNodeDetails(keys);
    // Update timeline context when selecting from graph
    setTimelineContextKeys(keys);
    setContextMenu(null);
    // NOTE: This does NOT automatically add to subgraph - user must click "Add to subgraph"
  }, [loadNodeDetails]);

  // Handle add selected nodes to subgraph
  const handleAddToSubgraph = useCallback(() => {
    if (selectedNodes.length === 0) return;
    const selectedKeys = selectedNodes.map(n => n.key);
    setSubgraphNodeKeys(prev => {
      const existingKeys = new Set(prev);
      const newKeys = selectedKeys.filter(key => !existingKeys.has(key));
      return [...prev, ...newKeys];
    });
    // Enable split view if not already enabled
    if (paneViewMode !== 'split') {
      setPaneViewMode('split');
    }
  }, [selectedNodes, paneViewMode]);

  // Handle remove selected nodes from subgraph
  const handleRemoveFromSubgraph = useCallback(() => {
    if (selectedNodes.length === 0) return;
    const selectedKeys = new Set(selectedNodes.map(n => n.key));
    setSubgraphNodeKeys(prev => prev.filter(key => !selectedKeys.has(key)));
  }, [selectedNodes]);

  // Handle select all subgraph nodes
  const handleSelectAllSubgraphNodes = useCallback(() => {
    if (subgraphNodeKeys.length === 0) return;
    
    // Use fullGraphData or graphData to get node objects
    const sourceData = fullGraphData.nodes.length > 0 ? fullGraphData : graphData;
    
    // Get all subgraph nodes from the source data
    const subgraphNodes = sourceData.nodes
      .filter(node => subgraphNodeKeys.includes(node.key))
      .map(node => ({
        key: node.key,
        id: node.id || node.key,
        name: node.name,
        type: node.type,
      }));
    
    const nodeKeys = subgraphNodes.map(n => n.key);
    setSelectedNodes(subgraphNodes);
    loadNodeDetails(nodeKeys);
    setTimelineContextKeys(nodeKeys);
  }, [subgraphNodeKeys, fullGraphData, graphData, loadNodeDetails]);

  // Handle node click - support multi-select with Ctrl/Cmd
  const handleNodeClick = useCallback((node, event) => {
    // Check both the event and tracked state (event might not have modifiers for canvas clicks)
    const isMultiSelect = event?.ctrlKey || event?.metaKey || event?.originalCtrlKey || event?.originalMetaKey;
    
    if (isMultiSelect) {
      // Toggle node in selection
      setSelectedNodes(prev => {
        const isSelected = prev.some(n => n.key === node.key);
        if (isSelected) {
          // Remove from selection
          const newSelection = prev.filter(n => n.key !== node.key);
          const newKeys = newSelection.map(n => n.key);
          if (newKeys.length > 0) {
            loadNodeDetails(newKeys);
          } else {
            setSelectedNodesDetails([]);
          }
          // Update timeline context when selecting from graph
          setTimelineContextKeys(newKeys);
          return newSelection;
        } else {
          // Add to selection
          const newSelection = [...prev, node];
          const newKeys = newSelection.map(n => n.key);
          loadNodeDetails(newKeys);
          // Update timeline context when selecting from graph
          setTimelineContextKeys(newKeys);
          return newSelection;
        }
      });
    } else {
      // Single select - replace selection
      setSelectedNodes([node]);
      loadNodeDetails([node.key]);
      // Update timeline context when selecting from graph
      setTimelineContextKeys([node.key]);
    }
    setContextMenu(null);
  }, [loadNodeDetails]);

  // Handle timeline event selection - show details without changing timeline context
  // This is different from graph selection because we don't want clicking an event
  // to re-filter the timeline to only show that event
  const handleTimelineEventSelect = useCallback((eventNode, event) => {
    // First try to find the node in fullGraphData (unfiltered graph)
    let graphNode = fullGraphData.nodes.find(n => n.key === eventNode.key);
    
    // If not found in fullGraphData, try graphData (filtered graph)
    if (!graphNode) {
      graphNode = graphData.nodes.find(n => n.key === eventNode.key);
    }
    
    const nodeToInspect = graphNode || {
      key: eventNode.key,
      id: eventNode.id || eventNode.key,
      name: eventNode.name,
      type: eventNode.type,
    };
    
    // Check for multi-select
    const isMultiSelect = event?.ctrlKey || event?.metaKey;
    
    if (isMultiSelect) {
      // Toggle node in selection for details only
      setSelectedNodes(prev => {
        const isSelected = prev.some(n => n.key === nodeToInspect.key);
        if (isSelected) {
          const newSelection = prev.filter(n => n.key !== nodeToInspect.key);
          if (newSelection.length > 0) {
            loadNodeDetails(newSelection.map(n => n.key));
          } else {
            setSelectedNodesDetails([]);
          }
          return newSelection;
        } else {
          const newSelection = [...prev, nodeToInspect];
          loadNodeDetails(newSelection.map(n => n.key));
          return newSelection;
        }
      });
    } else {
      // Single select - replace selection for details only
      setSelectedNodes([nodeToInspect]);
      loadNodeDetails([nodeToInspect.key]);
    }
    setContextMenu(null);
    // NOTE: We do NOT update timelineContextKeys here, so timeline stays showing same events
  }, [fullGraphData, graphData, loadNodeDetails]);

  // Handle node right-click
  const handleNodeRightClick = useCallback((node, event) => {
    setContextMenu({
      node,
      position: { x: event.clientX, y: event.clientY },
    });
  }, []);

  // Handle background click - clear selection (only for main graph)
  const handleBackgroundClick = useCallback(() => {
    setSelectedNodes([]);
    setSelectedNodesDetails([]);
    setTimelineContextKeys([]);
    setContextMenu(null);
  }, []);

  // Handle subgraph background click - don't clear selection
  const handleSubgraphBackgroundClick = useCallback(() => {
    // Do nothing - don't clear selection when clicking background in subgraph
    setContextMenu(null);
  }, []);

  // Handle subgraph node click - don't replace selection, preserve all selected nodes
  const handleSubgraphNodeClick = useCallback((node, event) => {
    // In subgraph, nodes are already selected, so clicking should not change the selection
    // Just close context menu if open
    setContextMenu(null);
    // Don't modify selectedNodes - keep all selected nodes intact
  }, []);

  // Handle show details from context menu
  const handleShowDetails = useCallback((node) => {
    setSelectedNodes([node]);
    loadNodeDetails([node.key]);
    setTimelineContextKeys([node.key]);
  }, [loadNodeDetails]);

  // Handle expand from context menu
  const handleExpand = useCallback(async (node) => {
    try {
      const expandedData = await graphAPI.getNodeNeighbours(node.key, 1);
      
      // Merge expanded nodes with existing graph
      setGraphData((prev) => {
        const existingKeys = new Set(prev.nodes.map((n) => n.key));
        const newNodes = expandedData.nodes.filter((n) => !existingKeys.has(n.key));
        
        const existingLinks = new Set(
          prev.links.map((l) => `${l.source.key || l.source}-${l.target.key || l.target}-${l.type}`)
        );
        const newLinks = expandedData.links.filter(
          (l) => !existingLinks.has(`${l.source}-${l.target}-${l.type}`)
        );

        return {
          nodes: [...prev.nodes, ...newNodes],
          links: [...prev.links, ...newLinks],
        };
      });

      // Add expanded node to selection
      setSelectedNodes(prev => {
        const isAlreadySelected = prev.some(n => n.key === node.key);
        if (!isAlreadySelected) {
          return [...prev, node];
        }
        return prev;
      });
      loadNodeDetails([node.key]);
    } catch (err) {
      console.error('Failed to expand node:', err);
    }
  }, [loadNodeDetails]);

  // Handle search select
  const handleSearchSelect = useCallback((key) => {
    const node = graphData.nodes.find((n) => n.key === key);
    if (node) {
      setSelectedNodes([node]);
      loadNodeDetails([key]);
      setTimelineContextKeys([key]);
    }
  }, [graphData.nodes, loadNodeDetails]);

  // Close details panel
  const handleCloseDetails = useCallback(() => {
    setSelectedNodes([]);
    setSelectedNodesDetails([]);
    setTimelineContextKeys([]);
    setPathSubgraphData(null); // Clear path-based subgraph when closing
  }, []);


  // Build subgraph from subgraph node keys (not selected nodes)
  const buildSubgraph = useCallback((nodeKeys) => {
    if (nodeKeys.length === 0) {
      return { nodes: [], links: [] };
    }

    // Use fullGraphData to build subgraph so timeline selections work even when graph is filtered
    // This allows selecting timeline events and creating a subgraph even if those nodes aren't
    // currently visible in the filtered graph view
    const sourceData = fullGraphData.nodes.length > 0 ? fullGraphData : graphData;

    // Get all subgraph nodes from the full graph
    const subgraphNodes = sourceData.nodes.filter(node => 
      nodeKeys.includes(node.key)
    );

    // Get all links between subgraph nodes
    const subgraphLinks = sourceData.links.filter(link => {
      const sourceKey = typeof link.source === 'object' ? link.source.key : link.source;
      const targetKey = typeof link.target === 'object' ? link.target.key : link.target;
      return nodeKeys.includes(sourceKey) && nodeKeys.includes(targetKey);
    });

    return { nodes: subgraphNodes, links: subgraphLinks };
  }, [fullGraphData, graphData]);

  // Calculate graph dimensions
  const sidebarWidth = selectedNodesDetails.length > 0 ? 320 : 0;
  const chatWidth = isChatOpen ? 384 : 0;
  const availableWidth = dimensions.width - sidebarWidth - chatWidth;
  const graphWidth = paneViewMode === 'split' ? availableWidth / 2 : availableWidth;
  const graphHeight = dimensions.height - 64; // Subtract header height

  // Memoize selected node keys to prevent infinite loops
  const selectedNodeKeys = useMemo(() => 
    selectedNodes.map(n => n.key), 
    [selectedNodes]
  );
  
  // Handle create subgraph from selected
  const handleCreateSubgraphFromSelected = useCallback(() => {
    if (selectedNodeKeys.length >= 2) {
      setPathSubgraphData(null); // Clear path subgraph when using regular subgraph
      setPaneViewMode('split');
      setIsSubgraphMenuOpen(false);
    }
  }, [selectedNodeKeys.length]);

  const handleCreateSubgraphFromPaths = useCallback(async () => {
    if (selectedNodeKeys.length >= 2) {
      try {
        setIsLoading(true);
        const pathData = await graphAPI.getShortestPaths(selectedNodeKeys, 10);
        
        // Check if paths were found
        if (!pathData || !pathData.nodes || pathData.nodes.length === 0) {
          alert('No paths found between the selected nodes. They may not be connected.');
          return;
        }
        
        // Set the path subgraph data
        setPathSubgraphData(pathData);
        
        // Update selected nodes to include all nodes from paths for the sidebar
        const pathNodeKeys = pathData.nodes.map(n => n.key);
        const pathNodes = pathData.nodes.map(node => ({
          key: node.key,
          id: node.id || node.key,
          name: node.name,
          type: node.type,
        }));
        setSelectedNodes(pathNodes);
        setTimelineContextKeys(pathNodeKeys);
        
        // Load details for all path nodes
        await loadNodeDetails(pathNodeKeys);
        
        // Enable split view
        setPaneViewMode('split');
        setIsSubgraphMenuOpen(false);
      } catch (err) {
        console.error('Failed to get shortest paths:', err);
        const errorMessage = err?.message || err?.detail || err?.toString() || 'Unknown error';
        alert(`Failed to find paths: ${errorMessage}`);
      } finally {
        setIsLoading(false);
      }
    }
  }, [selectedNodeKeys.length, loadNodeDetails]);
  
  // Build subgraph for subgraph node keys
  // Use path-based subgraph if available, otherwise build from subgraph node keys
  const subgraphData = pathSubgraphData || buildSubgraph(subgraphNodeKeys);

  // Load timeline - from subgraph when nodes are selected, from main graph when not
  const [timelineData, setTimelineData] = useState([]);
  
  // Calculate min/max dates from timeline for DateRangeFilter
  const [dateExtents, setDateExtents] = useState({ min: null, max: null });
  
  useEffect(() => {
    if (timelineData && timelineData.length > 0) {
      const dates = timelineData
        .map(e => e.date)
        .filter(d => d)
        .map(d => new Date(d));
      
      if (dates.length > 0) {
        setDateExtents({
          min: new Date(Math.min(...dates)).toISOString().split('T')[0],
          max: new Date(Math.max(...dates)).toISOString().split('T')[0],
        });
      }
    }
  }, [timelineData]);
  
  useEffect(() => {
    const loadTimeline = async () => {
      try {
        // Pass date range to timeline API if set
        const timelineParams = {};
        if (dateRange.start_date) {
          timelineParams.startDate = dateRange.start_date;
        }
        if (dateRange.end_date) {
          timelineParams.endDate = dateRange.end_date;
        }
        
        const response = await timelineAPI.getEvents(timelineParams);
        // Handle both array response and object with events property
        const events = Array.isArray(response) ? response : (response?.events || []);
        
        // Ensure events is an array
        if (!Array.isArray(events)) {
          console.warn('Timeline API returned non-array data:', response);
          setTimelineData([]);
          return;
        }

        // Use timelineContextKeys for filtering (separate from inspection selection)
        if (timelineContextKeys.length > 0) {
          // Filter events related to context nodes (subgraph timeline)
          // Timeline events have a 'connections' array with connected entity keys
          console.log('🔍 Filtering timeline for context:', {
            timelineContextKeys,
            timelineContextKeysCount: timelineContextKeys.length,
            totalEvents: events.length,
            sampleEvent: events[0]
          });
          
          // Create a Set for faster lookup
          const contextKeysSet = new Set(timelineContextKeys);
          
          const filteredEvents = events.filter(event => {
            // Check if the event itself is in the context nodes
            if (contextKeysSet.has(event.key)) {
              console.log('✅ Event matches by key:', event.key);
              return true;
            }
            
            // Check if event is connected to any context nodes via connections array
            if (event.connections && Array.isArray(event.connections)) {
              const matchingConnections = event.connections.filter(conn => 
                conn.key && contextKeysSet.has(conn.key)
              );
              
              if (matchingConnections.length > 0) {
                console.log('✅ Event connected via:', event.key, '->', matchingConnections.map(c => c.key));
                return true;
              }
            }
            return false;
          });
          
          console.log('📊 Timeline filtering result:', {
            before: events.length,
            after: filteredEvents.length,
            timelineContextKeys: Array.from(contextKeysSet)
          });
          
          setTimelineData(filteredEvents);
        } else {
          // No context set - show all events from main graph
          console.log('📅 Showing all timeline events (no context):', events.length);
          setTimelineData(events);
        }
      } catch (err) {
        console.error('Failed to load timeline:', err);
        setTimelineData([]);
      }
    };
    loadTimeline();
  }, [timelineContextKeys, dateRange]);

  // Load artifacts on mount
  useEffect(() => {
    const loadArtifacts = async () => {
      try {
        const data = await artifactsAPI.list();
        setArtifacts(data);
      } catch (err) {
        console.error('Failed to load artifacts:', err);
      }
    };
    loadArtifacts();
  }, []);

  // Export artifact to PDF
  const handleExportPDF = useCallback(async (name, notes) => {
    if (subgraphNodeKeys.length === 0) {
      alert('Please add nodes to subgraph to export as PDF');
      return;
    }

    try {
      // Get graph canvas from subgraph view
      let graphCanvas = null;
      if (subgraphGraphRef.current) {
        graphCanvas = subgraphGraphRef.current.getGraphCanvas?.();
      }

      // If no canvas from ref, try to find it in the DOM
      if (!graphCanvas) {
        // Look for canvas in the subgraph container
        const subgraphContainer = document.querySelector('[data-subgraph-container]');
        if (subgraphContainer) {
          graphCanvas = subgraphContainer.querySelector('canvas');
        }
      }

      // Small delay to ensure graph is fully rendered
      if (!graphCanvas) {
        await new Promise(resolve => setTimeout(resolve, 100));
        const subgraphContainer = document.querySelector('[data-subgraph-container]');
        if (subgraphContainer) {
          graphCanvas = subgraphContainer.querySelector('canvas');
        }
      }

      // Prepare artifact data for PDF - include both user questions and AI responses
      // Find relevant conversation pairs (user question + AI response)
      const relevantChatHistory = [];
      for (let i = 0; i < chatHistory.length; i++) {
        const msg = chatHistory[i];
        // Check if this is a user message with selected nodes matching our subgraph
        if (msg.role === 'user' && msg.selectedNodes) {
          const isRelevant = msg.selectedNodes.some(key => subgraphNodeKeys.includes(key));
          if (isRelevant) {
            // Include the user message
            relevantChatHistory.push({
              role: msg.role,
              content: msg.content,
              timestamp: msg.timestamp || new Date().toISOString(),
            });
            
            // Include the next assistant response if it exists
            if (i + 1 < chatHistory.length && chatHistory[i + 1].role === 'assistant') {
              const assistantMsg = chatHistory[i + 1];
              relevantChatHistory.push({
                role: assistantMsg.role,
                content: assistantMsg.content,
                contextMode: assistantMsg.contextMode,
                contextDescription: assistantMsg.contextDescription,
                cypherUsed: assistantMsg.cypherUsed,
                timestamp: assistantMsg.timestamp || new Date().toISOString(),
              });
            }
          }
        }
      }

      const artifact = {
        name: name || `Artifact ${new Date().toLocaleString()}`,
        notes: notes || '',
        subgraph: subgraphData,
        timeline: timelineData || [], // Ensure timeline is always an array
        overview: {
          nodes: selectedNodesDetails,
          nodeCount: subgraphData.nodes.length,
          linkCount: subgraphData.links.length,
        },
        chat_history: relevantChatHistory,
        timestamp: new Date().toISOString(),
      };

      console.log('Exporting artifact to PDF:', {
        name: artifact.name,
        timelineCount: artifact.timeline.length,
        timeline: artifact.timeline
      });

      // Export to PDF
      await exportArtifactToPDF(artifact, graphCanvas);
      alert('PDF exported successfully!');
    } catch (err) {
      console.error('Failed to export PDF:', err);
      alert(`Failed to export PDF: ${err.message}`);
    }
  }, [subgraphNodeKeys, subgraphData, timelineData, selectedNodesDetails, chatHistory]);

  // Save artifact
  const handleSaveArtifact = useCallback(async (name, notes) => {
    if (subgraphNodeKeys.length === 0) {
      alert('Please add nodes to subgraph to save as an artifact');
      return;
    }

    try {
      // Filter chat history to include both user questions and AI responses
      // Find relevant conversation pairs (user question + AI response)
      const relevantChatHistory = [];
      for (let i = 0; i < chatHistory.length; i++) {
        const msg = chatHistory[i];
        // Check if this is a user message with selected nodes matching our subgraph
        if (msg.role === 'user' && msg.selectedNodes) {
          const isRelevant = msg.selectedNodes.some(key => subgraphNodeKeys.includes(key));
          if (isRelevant) {
            // Include the user message
            relevantChatHistory.push({
              role: msg.role,
              content: msg.content,
              timestamp: msg.timestamp || new Date().toISOString(),
            });
            
            // Include the next assistant response if it exists
            if (i + 1 < chatHistory.length && chatHistory[i + 1].role === 'assistant') {
              const assistantMsg = chatHistory[i + 1];
              relevantChatHistory.push({
                role: assistantMsg.role,
                content: assistantMsg.content,
                contextMode: assistantMsg.contextMode,
                contextDescription: assistantMsg.contextDescription,
                cypherUsed: assistantMsg.cypherUsed,
                timestamp: assistantMsg.timestamp || new Date().toISOString(),
              });
            }
          }
        }
      }

      const artifact = {
        name: name || `Artifact ${new Date().toLocaleString()}`,
        notes: notes || '',
        subgraph: subgraphData,
        timeline: timelineData || [], // Ensure timeline is always an array
        overview: {
          nodes: selectedNodesDetails,
          nodeCount: subgraphData.nodes.length,
          linkCount: subgraphData.links.length,
        },
        chat_history: relevantChatHistory,
      };

      console.log('Saving artifact:', {
        name: artifact.name,
        timelineCount: artifact.timeline.length,
        timeline: artifact.timeline
      });

      await artifactsAPI.create(artifact);
      setShowArtifactModal(false);
      
      // Reload artifacts list
      const data = await artifactsAPI.list();
      setArtifacts(data);
      
      alert('Artifact saved successfully!');
    } catch (err) {
      console.error('Failed to save artifact:', err);
      alert(`Failed to save artifact: ${err.message}`);
    }
  }, [subgraphNodeKeys, subgraphData, timelineData, selectedNodesDetails, chatHistory]);

  // Handle date range change - memoized to prevent infinite loops
  const handleDateRangeChange = useCallback((range) => {
    setDateRange({
      start_date: range.start_date,
      end_date: range.end_date,
    });
  }, []);

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-dark-950 text-light-100 flex items-center justify-center px-4">
        <div className="w-full max-w-md">
          <LoginPanel
            isOpen={true}
            inline
            onLoginSuccess={handleLoginSuccess}
            onLogout={handleLogout}
            isAuthenticated={isAuthenticated}
            username={authUsername}
            onClose={() => {}}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen w-screen bg-light-50 flex flex-col overflow-hidden">
      {/* Header */}
      <header className="h-16 bg-white border-b border-light-200 flex items-center justify-between px-4 flex-shrink-0 shadow-sm">
        <div className="flex items-center gap-3 relative">
          <button
            ref={logoButtonRef}
            onClick={() => setIsAccountDropdownOpen(prev => !prev)}
            className="group focus:outline-none"
            type="button"
          >
            <img src="/owl-logo.webp" alt="Owl Consultancy Group" className="w-40 h-40 object-contain" />
          </button>

          {isAccountDropdownOpen && (
            <div
              ref={accountDropdownRef}
              className="absolute z-50 mt-2 w-48 rounded-lg bg-white shadow-lg border border-light-200 py-2 right-0"
              style={{ top: '70px', left: '0' }}
            >
              {isAuthenticated ? (
                <div className="px-3 py-1 space-y-1 text-sm text-dark-600">
                  <p className="text-xs uppercase text-dark-400">Signed in as</p>
                  <p className="font-semibold text-dark-800">{authUsername}</p>
                  <button
                    onClick={async () => {
                      await handleLogout();
                      setIsAccountDropdownOpen(false);
                    }}
                    className="w-full text-left px-2 py-1 rounded hover:bg-light-100 transition-colors text-sm text-dark-700"
                  >
                    Logout
                  </button>
                </div>
              ) : (
                <div className="px-3 py-2">
                  <button
                    onClick={() => {
                      setShowLoginPanel(true);
                      setIsAccountDropdownOpen(false);
                    }}
                    className="w-full flex items-center gap-2 px-3 py-2 bg-dark-900 text-light-100 rounded shadow-sm hover:bg-dark-800 transition-colors text-sm"
                  >
                    Login
                  </button>
                </div>
              )}
            </div>
          )}
          
          {viewMode === 'graph' && (
            <span className="text-xs text-light-600 bg-light-100 px-2 py-1 rounded">
              {selectedNodes.length > 0 
                ? `${subgraphData.nodes.length} selected · ${subgraphData.links.length} connections`
                : `${graphData.nodes.length} entities · ${graphData.links.length} relationships`
              }
            </span>
          )}
        </div>

        <div className="flex items-center gap-4">
          {/* Subgraph Menu - Only show in graph view */}
          {viewMode === 'graph' && (
            <div ref={subgraphMenuRef} className="relative">
              <button
                onClick={() => setIsSubgraphMenuOpen(!isSubgraphMenuOpen)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors ${
                  paneViewMode === 'split'
                    ? 'bg-owl-blue-100 text-owl-blue-900'
                    : 'text-light-600 hover:text-light-800 hover:bg-light-100'
                }`}
                title="Subgraph options"
              >
                <GitBranch className="w-4 h-4" />
                Subgraph
                <ChevronDown className={`w-4 h-4 transition-transform ${isSubgraphMenuOpen ? 'rotate-180' : ''}`} />
              </button>

              {/* Dropdown Menu */}
              {isSubgraphMenuOpen && (
                <div className="absolute top-full right-0 mt-1 bg-white rounded-lg shadow-lg border border-light-200 py-1 min-w-[180px] z-50">
                  <button
                    onClick={handleCreateSubgraphFromSelected}
                    disabled={selectedNodeKeys.length < 2}
                    className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                      selectedNodeKeys.length >= 2
                        ? 'text-light-800 hover:bg-light-50 cursor-pointer'
                        : 'text-light-400 cursor-not-allowed opacity-50'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <Layout className="w-4 h-4" />
                      <span>From Selected</span>
                    </div>
                    {selectedNodeKeys.length < 2 && (
                      <div className="text-xs text-light-500 mt-0.5 ml-6">
                        Select 2+ nodes
                      </div>
                    )}
                  </button>

                  <button
                    onClick={handleCreateSubgraphFromPaths}
                    disabled={selectedNodeKeys.length < 2}
                    className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                      selectedNodeKeys.length >= 2
                        ? 'text-light-800 hover:bg-light-50 cursor-pointer'
                        : 'text-light-400 cursor-not-allowed opacity-50'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <Network className="w-4 h-4" />
                      <span>Shortest Paths</span>
                    </div>
                    {selectedNodeKeys.length < 2 && (
                      <div className="text-xs text-light-500 mt-0.5 ml-6">
                        Select 2+ nodes
                      </div>
                    )}
                  </button>
                  
                  {paneViewMode === 'split' && (
                    <div className="border-t border-light-200 mt-1 pt-1">
                  <button
                    onClick={() => {
                      setPaneViewMode('single');
                      setPathSubgraphData(null); // Clear path subgraph when closing
                      setIsSubgraphMenuOpen(false);
                    }}
                    className="w-full text-left px-3 py-2 text-sm text-light-800 hover:bg-light-50 transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <X className="w-4 h-4" />
                      <span>Close Subgraph</span>
                    </div>
                  </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Save Artifact Button */}
          {subgraphNodeKeys.length > 0 && (
            <button
              onClick={() => setShowArtifactModal(true)}
              className="flex items-center gap-2 px-3 py-1.5 bg-owl-orange-500 hover:bg-owl-orange-600 text-white rounded-md text-sm transition-colors"
              title="Save current selection as artifact"
            >
              <Save className="w-4 h-4" />
              Save Artifact
            </button>
          )}

          {/* Artifacts List Button */}
          <button
            onClick={() => setShowArtifactList(!showArtifactList)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors ${
              showArtifactList
                ? 'bg-owl-blue-100 text-owl-blue-900'
                : 'text-light-600 hover:text-light-800'
            }`}
            title="View saved artifacts"
          >
            <Archive className="w-4 h-4" />
            Artifacts
          </button>

          {/* View Toggle */}
          <div className="flex items-center bg-light-100 rounded-lg p-1">
            <button
              onClick={() => setViewMode('graph')}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors ${
                viewMode === 'graph'
                  ? 'bg-white text-owl-blue-900 shadow-sm'
                  : 'text-light-600 hover:text-light-800'
              }`}
            >
              <Network className="w-4 h-4" />
              Graph
            </button>
            <button
              onClick={() => setViewMode('timeline')}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors ${
                viewMode === 'timeline'
                  ? 'bg-white text-owl-blue-900 shadow-sm'
                  : 'text-light-600 hover:text-light-800'
              }`}
            >
              <Calendar className="w-4 h-4" />
              Timeline
            </button>
          </div>

          {/* Date Range Filter */}
          {(viewMode === 'graph' || viewMode === 'timeline') && (
            <DateRangeFilter
              onDateRangeChange={handleDateRangeChange}
              minDate={dateExtents.min}
              maxDate={dateExtents.max}
              timelineEvents={timelineData}
            />
          )}

          {viewMode === 'graph' && (
            <GraphSearchFilter
              mode={graphSearchMode}
              onModeChange={handleGraphModeChange}
              onFilterChange={handleGraphFilterChange}
              onQueryChange={handleGraphQueryChange}
              onSearch={handleGraphSearchExecute}
              placeholder="Filter graph nodes..."
              disabled={isLoading}
            />
          )}
          
          <SearchBar onSelectNode={handleSearchSelect} />
          
          <button
            onClick={loadGraph}
            disabled={isLoading}
            className="p-2 hover:bg-light-100 rounded-lg transition-colors disabled:opacity-50"
            title="Refresh graph"
          >
            <RefreshCw className={`w-5 h-5 text-light-600 ${isLoading ? 'animate-spin' : ''}`} />
          </button>

          <button
            onClick={() => setIsChatOpen(!isChatOpen)}
            className={`p-2 rounded-lg transition-colors ${
              isChatOpen 
                ? 'bg-owl-purple-500 text-white' 
                : 'hover:bg-light-100 text-light-600'
            }`}
            title="Toggle AI Chat"
          >
            <MessageSquare className="w-5 h-5" />
          </button>
        </div>
      </header>

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Main view area - min-w-0 prevents flex item from expanding beyond container */}
        <div className="flex-1 relative overflow-hidden min-w-0">
          {viewMode === 'graph' ? (
            // Graph View
            isLoading && graphData.nodes.length === 0 ? (
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="flex flex-col items-center gap-3">
                  <Loader2 className="w-8 h-8 text-owl-blue-600 animate-spin" />
                  <span className="text-light-600">Loading graph...</span>
                </div>
              </div>
            ) : error ? (
              paneViewMode === 'split' ? (
                // Split panel error view
                <div className="absolute inset-0 flex">
                  {/* Left Panel - Error Details */}
                  <div className="flex-1 flex flex-col items-center justify-center border-r border-light-200 p-8">
                    <div className="flex flex-col items-center gap-4 text-center max-w-md">
                      <AlertCircle className="w-12 h-12 text-red-500" />
                      <div>
                        <h2 className="text-lg font-semibold text-light-800 mb-2">
                          Failed to load graph
                        </h2>
                        <p className="text-light-600 text-sm mb-4">{error}</p>
                      </div>
                      <button
                        onClick={loadGraph}
                        className="px-4 py-2 bg-owl-orange-500 hover:bg-owl-orange-600 rounded-lg text-sm text-white transition-colors"
                      >
                        Retry
                      </button>
                    </div>
                  </div>
                  
                  {/* Right Panel - Fallback/Info */}
                  <div className="flex-1 flex flex-col items-center justify-center p-8 bg-light-50">
                    <div className="flex flex-col items-center gap-4 text-center max-w-md">
                      <Network className="w-12 h-12 text-light-400" />
                      <div>
                        <h3 className="text-md font-medium text-light-700 mb-2">
                          Graph Unavailable
                        </h3>
                        <p className="text-light-600 text-sm">
                          The graph data could not be loaded. Please check your connection
                          and ensure the backend API is running.
                        </p>
                      </div>
                      <div className="mt-4 p-4 bg-light-100 rounded-lg text-left w-full">
                        <h4 className="text-xs font-semibold text-light-600 mb-2 uppercase">
                          Troubleshooting
                        </h4>
                        <ul className="text-xs text-light-700 space-y-1">
                          <li>• Verify backend is running on port 8000</li>
                          <li>• Check Neo4j connection</li>
                          <li>• Review browser console for details</li>
                          <li>• Try refreshing the page</li>
                        </ul>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                // Single pane error view
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="flex flex-col items-center gap-3 text-center">
                    <AlertCircle className="w-8 h-8 text-red-500" />
                    <span className="text-light-800">Failed to load graph</span>
                    <span className="text-light-600 text-sm">{error}</span>
                    <button
                      onClick={loadGraph}
                      className="mt-2 px-4 py-2 bg-owl-orange-500 hover:bg-owl-orange-600 rounded-lg text-sm text-white transition-colors"
                    >
                      Retry
                    </button>
                  </div>
                </div>
              )
            ) : paneViewMode === 'split' ? (
              // Split panel graph view
              <div className="absolute inset-0 flex">
                {/* Left Panel - Graph */}
                <div className="flex-1 relative border-r border-light-200">
                  <GraphView
                    graphData={graphData}
                    selectedNodes={selectedNodes}
                    onNodeClick={handleNodeClick}
                    onBulkNodeSelect={handleBulkNodeSelect}
                    onNodeRightClick={handleNodeRightClick}
                    onBackgroundClick={handleBackgroundClick}
                    width={graphWidth}
                    height={graphHeight}
                    paneViewMode={paneViewMode}
                    onPaneViewModeChange={setPaneViewMode}
                    onAddToSubgraph={handleAddToSubgraph}
                    onRemoveFromSubgraph={handleRemoveFromSubgraph}
                    subgraphNodeKeys={subgraphNodeKeys}
                  />
                </div>
                
                {/* Right Panel - Subgraph View */}
                <div className="flex-1 relative bg-light-50 overflow-hidden" data-subgraph-container>
                  {subgraphNodeKeys.length > 0 ? (
                    // Show subgraph of selected nodes
                    <>
                      <div className="absolute top-4 left-4 right-4 z-10 flex items-center justify-between bg-white/90 backdrop-blur-sm rounded-lg p-2 px-3 shadow-sm border border-light-200">
                        <div className="flex items-center gap-2">
                          <Network className="w-4 h-4 text-owl-blue-700" />
                          <h3 className="text-sm font-semibold text-owl-blue-900">
                            Subgraph ({subgraphData.nodes.length} nodes, {subgraphData.links.length} links)
                          </h3>
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={handleSelectAllSubgraphNodes}
                            className="flex items-center gap-1.5 px-2 py-1 text-xs bg-owl-blue-500 hover:bg-owl-blue-600 text-white rounded transition-colors"
                            title="Select all subgraph nodes"
                          >
                            <CheckSquare className="w-3.5 h-3.5" />
                            Select All
                          </button>
                          <button
                            onClick={handleCloseDetails}
                            className="p-1 hover:bg-light-100 rounded transition-colors"
                            title="Clear selection"
                          >
                            <X className="w-4 h-4 text-light-600" />
                          </button>
                        </div>
                      </div>
                      <GraphView
                        ref={subgraphGraphRef}
                        graphData={subgraphData}
                        selectedNodes={selectedNodes}
                        onNodeClick={handleSubgraphNodeClick}
                        onBulkNodeSelect={handleBulkNodeSelect}
                        onNodeRightClick={handleNodeRightClick}
                        onBackgroundClick={handleSubgraphBackgroundClick}
                        width={graphWidth}
                        height={graphHeight}
                        paneViewMode={paneViewMode}
                        onPaneViewModeChange={setPaneViewMode}
                        isSubgraph={true}
                      />
                    </>
                  ) : (
                    // Show empty state when no nodes are selected
                    <div className="h-full flex flex-col items-center justify-center p-8">
                      <div className="flex flex-col items-center gap-4 text-center max-w-md">
                        <Network className="w-12 h-12 text-owl-blue-300" />
                        <div>
                          <h3 className="text-md font-medium text-light-700 mb-2">
                            Subgraph View
                          </h3>
                          <p className="text-light-600 text-sm">
                            Select nodes in the main graph to view their subgraph here.
                          </p>
                        </div>
                        <div className="mt-4 p-4 bg-light-100 rounded-lg text-left w-full">
                          <p className="text-xs text-light-600 mb-2">
                            Click on nodes in the left graph to select them.
                          </p>
                          <p className="text-xs text-light-700">
                            Hold <kbd className="px-1.5 py-0.5 bg-white border border-light-200 rounded text-xs">Ctrl</kbd> or <kbd className="px-1.5 py-0.5 bg-white border border-light-200 rounded text-xs">Cmd</kbd> to select multiple nodes.
                          </p>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              // Single pane graph view
              <GraphView
                graphData={graphData}
                selectedNodes={selectedNodes}
                onNodeClick={handleNodeClick}
                onBulkNodeSelect={handleBulkNodeSelect}
                onNodeRightClick={handleNodeRightClick}
                onBackgroundClick={handleBackgroundClick}
                width={graphWidth}
                height={graphHeight}
                paneViewMode={paneViewMode}
                onPaneViewModeChange={setPaneViewMode}
                onAddToSubgraph={handleAddToSubgraph}
                onRemoveFromSubgraph={handleRemoveFromSubgraph}
                subgraphNodeKeys={subgraphNodeKeys}
              />
            )
          ) : (
            // Timeline View - only show if there are timeline events
            timelineData.length > 0 ? (
              <TimelineView
                onSelectEvents={handleTimelineEventSelect}
                selectedEvent={selectedNodes.length > 0 ? selectedNodes[0] : null}
                selectedEventKeys={selectedNodeKeys}
                timelineData={timelineData}
                onBackgroundClick={handleBackgroundClick}
              />
            ) : (
              <div className="h-full flex items-center justify-center bg-light-50">
                <div className="flex flex-col items-center gap-3 text-center">
                  <Calendar className="w-12 h-12 text-light-400" />
                  <span className="text-light-800">No timeline events available</span>
                  <span className="text-light-600 text-sm">
                    {selectedNodeKeys.length > 0 
                      ? 'The selected subgraph has no timeline events with date information'
                      : 'No timeline events found in the graph'}
                  </span>
                </div>
              </div>
            )
          )}

        </div>

        {/* Node details sidebar - show all selected nodes */}
        {selectedNodesDetails.length > 0 && (
          <div className="w-80 bg-white border-l border-light-200 h-full flex flex-col overflow-hidden shadow-sm">
            <div className="p-4 border-b border-light-200 flex items-center justify-between flex-shrink-0">
              <h2 className="font-semibold text-owl-blue-900">
                Selected ({selectedNodesDetails.length})
              </h2>
              <button
                onClick={handleCloseDetails}
                className="p-1 hover:bg-light-100 rounded transition-colors"
              >
                <X className="w-5 h-5 text-light-600" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto">
              {selectedNodesDetails.map((node, idx) => (
                <div key={node.key} className={idx > 0 ? "border-t border-light-200" : ""}>
                  <NodeDetails
                    node={node}
                    onClose={() => {
                      const newSelection = selectedNodes.filter(n => n.key !== node.key);
                      const newKeys = newSelection.map(n => n.key);
                      setSelectedNodes(newSelection);
                      // Only update timeline context if we're in graph view
                      // In timeline view, the context should stay stable
                      if (viewMode === 'graph') {
                        setTimelineContextKeys(newKeys);
                      }
                      if (newSelection.length > 0) {
                        loadNodeDetails(newKeys);
                      } else {
                        setSelectedNodesDetails([]);
                      }
                    }}
                    onSelectNode={handleSearchSelect}
                    compact={selectedNodesDetails.length > 1}
                  />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Chat panel */}
        {isChatOpen && (
          <ChatPanel
            isOpen={isChatOpen}
            onToggle={() => setIsChatOpen(!isChatOpen)}
            onClose={() => setIsChatOpen(false)}
            selectedNodes={selectedNodesDetails}
            onMessagesChange={setChatHistory}
          />
        )}
      </div>

      {/* Context menu */}
      {contextMenu && (
        <ContextMenu
          node={contextMenu.node}
          position={contextMenu.position}
          onShowDetails={handleShowDetails}
          onExpand={handleExpand}
          onClose={() => setContextMenu(null)}
        />
      )}

      {/* Artifact Modal */}
      <ArtifactModal
        isOpen={showArtifactModal}
        onClose={() => setShowArtifactModal(false)}
        onSave={handleSaveArtifact}
        onExportPDF={handleExportPDF}
        nodeCount={subgraphData.nodes.length}
        linkCount={subgraphData.links.length}
      />

      {/* Artifact List */}
      <ArtifactList
        isOpen={showArtifactList}
        onClose={() => setShowArtifactList(false)}
        onLoadArtifact={async (artifact) => {
          // Load artifact into subgraph (right pane) by setting subgraph node keys
          // This will automatically build the subgraph in the right pane
          if (artifact.subgraph && artifact.subgraph.nodes) {
            // Ensure split view is enabled to show the subgraph
            if (paneViewMode !== 'split') {
              setPaneViewMode('split');
            }
            
            // Set subgraph node keys to artifact's subgraph nodes
            // The subgraph will be built automatically from these keys
            const artifactNodes = artifact.subgraph.nodes;
            const nodeKeys = artifactNodes.map(n => n.key);
            setSubgraphNodeKeys(nodeKeys);
            setSelectedNodes(artifactNodes);
            setTimelineContextKeys(nodeKeys);
            
            // Load node details for the selected nodes (for the overview panel)
            await loadNodeDetails(nodeKeys);
            
            // Timeline will be loaded automatically by the useEffect when timelineContextKeys changes
            
            setShowArtifactList(false);
          }
        }}
      />
      <LoginPanel
        isOpen={showLoginPanel}
        onClose={() => setShowLoginPanel(false)}
        onLoginSuccess={handleLoginSuccess}
        onLogout={handleLogout}
        isAuthenticated={isAuthenticated}
        username={authUsername}
      />
    </div>
  );
}
