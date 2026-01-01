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
  ChevronUp,
  GitBranch,
  CheckSquare,
  FolderOpen,
  TrendingUp,
  HardDrive,
  Users,
  FileText,
  Target,
  MapPin,
  Plus,
  Link2,
  Edit,
  Focus,
  Camera
} from 'lucide-react';
import { graphAPI, snapshotsAPI, timelineAPI, casesAPI, authAPI, evidenceAPI, chatHistoryAPI, chatAPI } from './services/api';
import { compareCypherQueries } from './utils/cypherCompare';
import { calculateCypherDelta, buildIncrementalQueries } from './utils/cypherDelta';
import GraphView from './components/GraphView';
import NodeDetails from './components/NodeDetails';
import ChatPanel from './components/ChatPanel';
import ContextMenu from './components/ContextMenu';
import SearchBar from './components/SearchBar';
import GraphSearchFilter from './components/GraphSearchFilter';
import TimelineView from './components/timeline/TimelineView';
import MapView from './components/MapView';
import SnapshotModal from './components/SnapshotModal';
import SaveSnapshotProgressDialog from './components/SaveSnapshotProgressDialog';
import CaseModal from './components/CaseModal';
import DateRangeFilter from './components/DateRangeFilter';
import FileManagementPanel from './components/FileManagementPanel';
import BackgroundTasksPanel from './components/BackgroundTasksPanel';
import CaseManagementView from './components/CaseManagementView';
import EvidenceProcessingView from './components/EvidenceProcessingView';
import { exportSnapshotToPDF } from './utils/pdfExport';
import { parseSearchQuery, matchesQuery } from './utils/searchParser';  
import LoginPanel from './components/LoginPanel';
import DocumentationViewer from './components/DocumentationViewer';
import DocumentViewer from './components/DocumentViewer';
import LoadCaseProgressDialog from './components/LoadCaseProgressDialog';
import LoadSnapshotProgressDialog from './components/LoadSnapshotProgressDialog';
import NodeSelectionProgressDialog from './components/NodeSelectionProgressDialog';
import AddNodeModal from './components/AddNodeModal';
import CreateRelationshipModal from './components/CreateRelationshipModal';
import RelationshipAnalysisModal from './components/RelationshipAnalysisModal';
import EditNodeModal from './components/EditNodeModal';

/**
 * Main App Component
 */
export default function App() {
  // Main app view state - 'caseManagement' or 'graph'
  const [appView, setAppView] = useState('caseManagement'); // Start with case management after login
  // View mode state (for graph view)
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
  const [subgraphAnalysis, setSubgraphAnalysis] = useState(null); // Analysis text for PageRank/Louvain
  const [subgraphCommunityData, setSubgraphCommunityData] = useState(null); // Community data for Louvain analysis
  const [isAnalysisExpanded, setIsAnalysisExpanded] = useState(false); // Whether analysis panel is expanded
  
  // Timeline context - separate from selection so inspecting events doesn't filter timeline
  const [timelineContextKeys, setTimelineContextKeys] = useState([]); // Keys that define what events show on timeline

  // Context menu state
  const [contextMenu, setContextMenu] = useState(null);

  // Chat panel state
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [chatHistory, setChatHistory] = useState([]); // Track chat messages

  // Snapshots state
  const [snapshots, setSnapshots] = useState([]);
  const [showSnapshotModal, setShowSnapshotModal] = useState(false);
  const [saveSnapshotProgress, setSaveSnapshotProgress] = useState({
    isOpen: false,
    message: '',
    stage: null,
    stageProgress: 0,
    stageTotal: 0,
    current: 0,
    total: 0,
  });
  const mainGraphRef = useRef(null); // Ref to main GraphView for centering
  const subgraphGraphRef = useRef(null); // Ref to subgraph GraphView for PDF export
  
  // Cases state
  const [currentCaseId, setCurrentCaseId] = useState(null);
  const [currentCaseName, setCurrentCaseName] = useState(null);
  const [currentCaseVersion, setCurrentCaseVersion] = useState(0);
  const [loadedCypherQueries, setLoadedCypherQueries] = useState(null); // Track loaded Cypher queries for comparison
  const [showCaseModal, setShowCaseModal] = useState(false);
  
  // File management panel state
  const [showFilePanel, setShowFilePanel] = useState(false);
  // Background tasks panel state
  const [showBackgroundTasksPanel, setShowBackgroundTasksPanel] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [authUsername, setAuthUsername] = useState('');
  const [showLoginPanel, setShowLoginPanel] = useState(false);
  const [isAccountDropdownOpen, setIsAccountDropdownOpen] = useState(false);
  const [showDocumentation, setShowDocumentation] = useState(false);
  const [showAddNodeModal, setShowAddNodeModal] = useState(false);
  const [caseToSelect, setCaseToSelect] = useState(null); // Case ID to select when navigating to case management
  
  // Relationship creation state
  const [isRelationshipMode, setIsRelationshipMode] = useState(false);
  const [relationshipSourceNodes, setRelationshipSourceNodes] = useState([]);
  const [showCreateRelationshipModal, setShowCreateRelationshipModal] = useState(false);
  
  // Relationship analysis state
  const [showRelationshipAnalysisModal, setShowRelationshipAnalysisModal] = useState(false);
  const [nodeForAnalysis, setNodeForAnalysis] = useState(null);
  
  // Edit node modal state
  const [showEditNodeModal, setShowEditNodeModal] = useState(false);
  
  // Document viewer state
  const [documentViewerState, setDocumentViewerState] = useState({
    isOpen: false,
    documentUrl: null,
    documentName: null,
    page: 1,
    highlightText: null,
  });
  
  // Load case progress state
  const [loadCaseProgress, setLoadCaseProgress] = useState({
    isOpen: false,
    current: 0,
    total: 0,
    caseName: null,
    version: null,
  });
  
  // Load snapshot progress state
  const [loadSnapshotProgress, setLoadSnapshotProgress] = useState({
    isOpen: false,
    current: 0,
    total: 4, // Fetching snapshot, loading nodes, restoring chat, setting up timeline
    snapshotName: null,
    stage: null,
    message: null,
  });
  
  // Node selection progress state
  const [nodeSelectionProgress, setNodeSelectionProgress] = useState({
    isOpen: false,
    current: 0,
    total: 0,
    message: null,
  });
  
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
  const loadNodeDetails = useCallback(async (keys, onProgress) => {
    if (!keys || keys.length === 0) {
      setSelectedNodesDetails([]);
      return;
    }

    // Clear any pending debounce timer
    if (loadNodeDetailsTimerRef.current) {
      clearTimeout(loadNodeDetailsTimerRef.current);
    }

    // Debounce: wait 100ms for more updates before fetching (unless progress callback is provided)
    const debounceDelay = onProgress ? 0 : 100;
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
          
          // Update progress if callback provided
          if (onProgress) {
            const current = Math.min(i + BATCH_SIZE, keys.length);
            onProgress(current, keys.length);
          }
          
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
    }, debounceDelay);
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

  // Handle show nodes on graph from AI answer
  const handleShowNodesOnGraph = useCallback((nodeKeys) => {
    if (!nodeKeys || nodeKeys.length === 0) {
      alert('No nodes found to show on graph');
      return;
    }
    
    // Set the subgraph node keys
    setSubgraphNodeKeys(nodeKeys);
    setPathSubgraphData(null); // Clear path subgraph data
    
    // Enable split view if not already enabled
    if (paneViewMode !== 'split') {
      setPaneViewMode('split');
    }
    
    // Show a brief message
    console.log(`Showing ${nodeKeys.length} nodes on graph from AI answer`);
  }, [paneViewMode]);

  // Handle add selected nodes to subgraph
  const handleAddToSubgraph = useCallback(() => {
    if (selectedNodes.length === 0) return;
    const selectedKeys = selectedNodes.map(n => n.key);
    setSubgraphNodeKeys(prev => {
      const existingKeys = new Set(prev);
      const newKeys = selectedKeys.filter(key => !existingKeys.has(key));
      return [...prev, ...newKeys];
    });
    // Clear path subgraph data so subgraph rebuilds from subgraphNodeKeys
    setPathSubgraphData(null);
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
    // Clear path subgraph data so subgraph rebuilds from subgraphNodeKeys
    setPathSubgraphData(null);
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
    setTimelineContextKeys(nodeKeys);
    
    // Show progress dialog if there are many nodes (>50)
    const showProgress = nodeKeys.length > 50;
    if (showProgress) {
      setNodeSelectionProgress({
        isOpen: true,
        current: 0,
        total: nodeKeys.length,
        message: `Loading details for ${nodeKeys.length} nodes...`,
      });
    }
    
    // Load node details with progress tracking
    loadNodeDetails(nodeKeys, showProgress ? (current, total) => {
      setNodeSelectionProgress(prev => ({
        ...prev,
        current,
        message: `Loading details for ${nodeKeys.length} nodes...`,
      }));
      
      // Close dialog when complete
      if (current >= total) {
        setTimeout(() => {
          setNodeSelectionProgress(prev => ({ ...prev, isOpen: false }));
        }, 500);
      }
    } : undefined);
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

  // Handle node double-click - open edit modal for name editing
  const handleNodeDoubleClick = useCallback(async (node, event) => {
    // Load node details if not already loaded
    if (!selectedNodesDetails.find(n => n.key === node.key)) {
      await loadNodeDetails([node.key]);
    }
    
    // Find the node in selectedNodesDetails or use the node from graph
    const nodeDetails = selectedNodesDetails.find(n => n.key === node.key) || {
      key: node.key,
      name: node.name,
      type: node.type,
      summary: node.summary,
      notes: node.notes,
    };
    
    // Set this node as selected and open edit modal
    setSelectedNodes([node]);
    setSelectedNodesDetails([nodeDetails]);
    setShowEditNodeModal(true);
  }, [selectedNodesDetails, loadNodeDetails]);

  // Handle start relationship creation
  const handleStartRelationshipCreation = useCallback(() => {
    // Use currently selected nodes as source, or the right-clicked node
    const sourceNodes = selectedNodes.length > 0 ? selectedNodes : 
      (contextMenu?.node ? [contextMenu.node] : []);
    
    if (sourceNodes.length > 0) {
      setRelationshipSourceNodes(sourceNodes);
      setIsRelationshipMode(true);
      setContextMenu(null);
    }
  }, [selectedNodes, contextMenu]);

  // Handle create relationship (when target nodes are selected)
  const handleCreateRelationship = useCallback(() => {
    // Target nodes are the currently selected nodes
    if (selectedNodes.length > 0 && relationshipSourceNodes.length > 0) {
      // Filter out source nodes from target nodes to avoid self-relationships
      const targetNodes = selectedNodes.filter(
        target => !relationshipSourceNodes.some(source => source.key === target.key)
      );
      
      if (targetNodes.length > 0) {
        setShowCreateRelationshipModal(true);
        setContextMenu(null);
      } else {
        alert('Please select different nodes as targets (cannot create relationships to the same source nodes).');
      }
    }
  }, [selectedNodes, relationshipSourceNodes]);

  // Handle relationship created
  const handleRelationshipCreated = useCallback(async (cypher) => {
    // Reset relationship mode
    setIsRelationshipMode(false);
    setRelationshipSourceNodes([]);
    
    // Refresh the graph to show new relationships
    await loadGraph();
  }, [loadGraph]);

  // Handle Escape key to cancel relationship mode
  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape' && isRelationshipMode) {
        setIsRelationshipMode(false);
        setRelationshipSourceNodes([]);
        setShowCreateRelationshipModal(false);
      }
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isRelationshipMode]);

  // Cancel relationship creation
  const handleCancelRelationshipCreation = useCallback(() => {
    setIsRelationshipMode(false);
    setRelationshipSourceNodes([]);
    setShowCreateRelationshipModal(false);
  }, []);

  // Handle relationship analysis
  const handleAnalyzeRelationships = useCallback(() => {
    // Use the right-clicked node or first selected node
    const nodeToAnalyze = contextMenu?.node || (selectedNodes.length > 0 ? selectedNodes[0] : null);
    if (nodeToAnalyze) {
      setNodeForAnalysis(nodeToAnalyze);
      setShowRelationshipAnalysisModal(true);
    }
  }, [contextMenu, selectedNodes]);

  // Handle relationships added from analysis
  const handleRelationshipsAddedFromAnalysis = useCallback(async (cypher) => {
    // Refresh the graph to show new relationships
    await loadGraph();
    setShowRelationshipAnalysisModal(false);
    setNodeForAnalysis(null);
  }, [loadGraph]);

  // Handle updating node information
  const handleUpdateNode = useCallback(async (nodeKey, updates) => {
    try {
      const result = await graphAPI.updateNode(nodeKey, updates);
      if (!result.success) {
        throw new Error(result.error || 'Failed to update node');
      }
      // Refresh node details to show updated information
      const selectedKeys = selectedNodesDetails.map(n => n.key);
      await loadNodeDetails(selectedKeys);
      // Refresh graph to ensure changes are visible
      await loadGraph();
    } catch (err) {
      throw err;
    }
  }, [selectedNodesDetails, loadNodeDetails, loadGraph]);

  // Auto-save chat history after significant queries
  const handleAutoSaveChat = useCallback(async (messages) => {
    if (!currentCaseId || !messages || messages.length === 0) {
      return; // Don't save if no case or no messages
    }

    try {
      // Generate a name for this chat session
      const chatName = currentCaseName 
        ? `${currentCaseName} - Chat ${new Date().toLocaleString()}`
        : `Chat ${new Date().toLocaleString()}`;

      await chatHistoryAPI.create({
        name: chatName,
        messages: messages,
        snapshot_id: null, // Not associated with a snapshot yet
        case_id: currentCaseId,
        case_version: currentCaseVersion,
      });
      
      console.log('Chat history auto-saved');
    } catch (err) {
      console.warn('Failed to auto-save chat history:', err);
      // Don't show error to user - auto-save failures should be silent
    }
  }, [currentCaseId, currentCaseName, currentCaseVersion]);

  // Handle background click - clear selection (only for main graph)
  const handleBackgroundClick = useCallback(() => {
    setSelectedNodes([]);
    setSelectedNodesDetails([]);
    setTimelineContextKeys([]);
    setContextMenu(null);
    // Cancel relationship mode if active
    if (isRelationshipMode) {
      setIsRelationshipMode(false);
      setRelationshipSourceNodes([]);
    }
  }, [isRelationshipMode]);

  // Handle subgraph background click - clear selection in subgraph
  const handleSubgraphBackgroundClick = useCallback(() => {
    // Clear selection when clicking background in subgraph
    setSelectedNodes([]);
    setSelectedNodesDetails([]);
    setContextMenu(null);
    // Cancel relationship mode if active
    if (isRelationshipMode) {
      setIsRelationshipMode(false);
      setRelationshipSourceNodes([]);
    }
  }, [isRelationshipMode]);

  // Handle subgraph node click - allow selection in subgraph
  const handleSubgraphNodeClick = useCallback((node, event) => {
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
          return newSelection;
        } else {
          // Add to selection
          const newSelection = [...prev, node];
          const newKeys = newSelection.map(n => n.key);
          loadNodeDetails(newKeys);
          return newSelection;
        }
      });
    } else {
      // Single select - replace selection
      setSelectedNodes([node]);
      loadNodeDetails([node.key]);
    }
    setContextMenu(null);
  }, [loadNodeDetails]);

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

  // Handle viewing a source document from a citation
  const handleViewDocument = useCallback(async (sourceDoc, page = 1, caseId = null) => {
    try {
      // Use provided caseId or fall back to currentCaseId
      const targetCaseId = caseId || currentCaseId;
      
      if (!targetCaseId) {
        console.warn('No case ID available for viewing document:', sourceDoc);
        // Still try to open the viewer, it might work without a case ID
        setDocumentViewerState({
          isOpen: true,
          documentUrl: null,
          documentName: sourceDoc,
          page: page || 1,
          highlightText: null,
        });
        return;
      }
      
      // First, find the evidence file by filename
      const result = await evidenceAPI.findByFilename(sourceDoc, targetCaseId);
      
      if (result.found && result.evidence_id) {
        // Get the file URL
        const fileUrl = evidenceAPI.getFileUrl(result.evidence_id);
        
        setDocumentViewerState({
          isOpen: true,
          documentUrl: fileUrl,
          documentName: sourceDoc,
          page: page || 1,
          highlightText: null,
        });
      } else {
        console.warn(`Document not found: ${sourceDoc}`);
        // Still try to show a message in the viewer
        setDocumentViewerState({
          isOpen: true,
          documentUrl: null,
          documentName: sourceDoc,
          page: 1,
          highlightText: null,
        });
      }
    } catch (err) {
      console.error('Failed to load document:', err);
      // Show viewer with error state
      setDocumentViewerState({
        isOpen: true,
        documentUrl: null,
        documentName: sourceDoc,
        page: 1,
        highlightText: null,
      });
    }
  }, [currentCaseId]);

  // Close document viewer
  const handleCloseDocumentViewer = useCallback(() => {
    setDocumentViewerState({
      isOpen: false,
      documentUrl: null,
      documentName: null,
      page: 1,
      highlightText: null,
    });
  }, []);

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
        
        // Also update subgraphNodeKeys so add/remove buttons work
        setSubgraphNodeKeys(pathNodeKeys);
        
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

  const handleCreateSubgraphFromPageRank = useCallback(async () => {
    try {
      setIsLoading(true);
      // Use selected nodes if available, otherwise analyze full graph
      const nodeKeysToAnalyze = selectedNodeKeys.length > 0 ? selectedNodeKeys : null;
      const pagerankData = await graphAPI.getPageRank(nodeKeysToAnalyze, 20, 20, 0.85);
      
      // Check if nodes were found
      if (!pagerankData || !pagerankData.nodes || pagerankData.nodes.length === 0) {
        alert('No influential nodes found. The graph may be too small or disconnected.');
        return;
      }
      
      // Set the path subgraph data (reusing same mechanism)
      setPathSubgraphData(pagerankData);
      
      // Update selected nodes to include top influential nodes
      const pagerankNodeKeys = pagerankData.nodes.map(n => n.key);
      const pagerankNodes = pagerankData.nodes.map(node => ({
        key: node.key,
        id: node.id || node.key,
        name: node.name,
        type: node.type,
      }));
      setSelectedNodes(pagerankNodes);
      setTimelineContextKeys(pagerankNodeKeys);
      
      // Also update subgraphNodeKeys so add/remove buttons work
      setSubgraphNodeKeys(pagerankNodeKeys);
      
      // Generate analysis text for PageRank
      const topNodes = pagerankData.nodes.slice(0, 10); // Top 10 nodes
      const topScore = pagerankData.nodes[0]?.pagerank_score || 0;
      const avgScore = pagerankData.nodes.reduce((sum, n) => sum + (n.pagerank_score || 0), 0) / pagerankData.nodes.length;
      
      let analysisText = `## PageRank Analysis: Influential Nodes\n\n`;
      analysisText += `**Analysis Scope:** ${nodeKeysToAnalyze ? `${nodeKeysToAnalyze.length} selected nodes` : 'Full graph'}\n\n`;
      analysisText += `**Summary:**\n`;
      analysisText += `- Total influential nodes identified: **${pagerankData.nodes.length}**\n`;
      analysisText += `- Highest PageRank score: **${topScore.toFixed(6)}**\n`;
      analysisText += `- Average PageRank score: **${avgScore.toFixed(6)}**\n\n`;
      analysisText += `**Top Influential Nodes:**\n\n`;
      
      topNodes.forEach((node, idx) => {
        analysisText += `${idx + 1}. **${node.name || node.key}** (${node.type || 'Unknown'})\n`;
        analysisText += `   - PageRank Score: ${(node.pagerank_score || 0).toFixed(6)}\n`;
        if (node.summary) {
          analysisText += `   - Summary: ${node.summary}\n`;
        }
        analysisText += `\n`;
      });
      
      analysisText += `\n**Interpretation:**\n`;
      analysisText += `Nodes with higher PageRank scores are more influential in the network. `;
      analysisText += `These nodes have more connections or are connected to other highly influential nodes. `;
      analysisText += `Focusing on these nodes can help identify key entities in the investigation.`;
      
      setSubgraphAnalysis(analysisText);
      setSubgraphCommunityData(null); // Clear community data (not applicable for PageRank)
      
      // Load details for all influential nodes
      await loadNodeDetails(pagerankNodeKeys);
      
      // Enable split view
      setPaneViewMode('split');
      setIsSubgraphMenuOpen(false);
      
      console.log(`PageRank analysis complete. Top node score: ${topScore.toFixed(6)}`);
    } catch (err) {
      console.error('Failed to get PageRank:', err);
      const errorMessage = err?.message || err?.detail || err?.toString() || 'Unknown error';
      alert(`Failed to calculate PageRank: ${errorMessage}`);
    } finally {
      setIsLoading(false);
    }
  }, [selectedNodeKeys, loadNodeDetails]);

  const handleCreateSubgraphFromLouvain = useCallback(async () => {
    try {
      setIsLoading(true);
      // Priority: subgraph > selected nodes > full graph
      let nodeKeysToAnalyze = null;
      let analysisScope = 'full graph';
      
      if (subgraphNodeKeys.length > 0) {
        // Use subgraph nodes if available
        nodeKeysToAnalyze = subgraphNodeKeys;
        analysisScope = `subgraph (${subgraphNodeKeys.length} nodes)`;
      } else if (selectedNodeKeys.length > 0) {
        // Use selected nodes if available
        nodeKeysToAnalyze = selectedNodeKeys;
        analysisScope = `${selectedNodeKeys.length} selected nodes`;
      }
      
      const louvainData = await graphAPI.getLouvainCommunities(nodeKeysToAnalyze, 1.0, 10);
      
      // Check if nodes were found
      if (!louvainData || !louvainData.nodes || louvainData.nodes.length === 0) {
        alert('No communities found. The graph may be too small or disconnected.');
        return;
      }
      
      // Set the path subgraph data (reusing same mechanism)
      setPathSubgraphData(louvainData);
      
      // Update selected nodes to include all nodes from communities
      const louvainNodeKeys = louvainData.nodes.map(n => n.key);
      const louvainNodes = louvainData.nodes.map(node => ({
        key: node.key,
        id: node.id || node.key,
        name: node.name,
        type: node.type,
      }));
      setSelectedNodes(louvainNodes);
      setTimelineContextKeys(louvainNodeKeys);
      
      // Also update subgraphNodeKeys so add/remove buttons work
      setSubgraphNodeKeys(louvainNodeKeys);
      
      // Generate analysis text for Louvain communities
      const communityCount = louvainData.communities ? Object.keys(louvainData.communities).length : 0;
      const communities = louvainData.communities || {};
      
      // Group nodes by community
      const nodesByCommunity = {};
      louvainData.nodes.forEach(node => {
        const commId = node.community_id;
        if (commId !== null && commId !== undefined) {
          if (!nodesByCommunity[commId]) {
            nodesByCommunity[commId] = [];
          }
          nodesByCommunity[commId].push(node);
        }
      });
      
      let analysisText = `## Louvain Community Detection Analysis\n\n`;
      analysisText += `**Analysis Scope:** ${analysisScope}\n\n`;
      analysisText += `**Summary:**\n`;
      analysisText += `- Total communities detected: **${communityCount}**\n`;
      analysisText += `- Total nodes analyzed: **${louvainData.nodes.length}**\n`;
      analysisText += `- Average community size: **${(louvainData.nodes.length / communityCount).toFixed(1)}** nodes\n\n`;
      
      // Sort communities by size (largest first)
      const sortedCommunities = Object.entries(communities)
        .map(([id, info]) => ({ id: parseInt(id), size: info.size || 0 }))
        .sort((a, b) => b.size - a.size);
      
      analysisText += `**Community Breakdown:**\n\n`;
      sortedCommunities.slice(0, 10).forEach((comm, idx) => {
        const commNodes = nodesByCommunity[comm.id] || [];
        const nodeTypes = {};
        commNodes.forEach(node => {
          const type = node.type || 'Unknown';
          nodeTypes[type] = (nodeTypes[type] || 0) + 1;
        });
        const typeBreakdown = Object.entries(nodeTypes)
          .sort((a, b) => b[1] - a[1])
          .slice(0, 3)
          .map(([type, count]) => `${type} (${count})`)
          .join(', ');
        
        analysisText += `${idx + 1}. **Community ${comm.id}** - ${comm.size} nodes\n`;
        analysisText += `   - Top entity types: ${typeBreakdown || 'N/A'}\n`;
        if (commNodes.length > 0) {
          const allNodes = commNodes.map(n => n.name || n.key).join(', ');
          analysisText += `   - Nodes: ${allNodes}\n`;
        }
        analysisText += `\n`;
      });
      
      if (sortedCommunities.length > 10) {
        analysisText += `*... and ${sortedCommunities.length - 10} more communities*\n\n`;
      }
      
      analysisText += `\n**Interpretation:**\n`;
      analysisText += `Communities represent groups of nodes that are more densely connected to each other than to the rest of the network. `;
      analysisText += `Larger communities may indicate clusters of related entities, while smaller communities might represent isolated groups. `;
      analysisText += `Nodes within the same community are colored identically in the visualization.`;
      
      setSubgraphAnalysis(analysisText);
      setSubgraphCommunityData(nodesByCommunity); // Store community data for click handling
      
      // Load details for all community nodes
      await loadNodeDetails(louvainNodeKeys);
      
      // Enable split view
      setPaneViewMode('split');
      setIsSubgraphMenuOpen(false);
      
      console.log(`Louvain analysis complete on ${analysisScope}. Found ${communityCount} communities.`);
    } catch (err) {
      console.error('Failed to get Louvain communities:', err);
      const errorMessage = err?.message || err?.detail || err?.toString() || 'Unknown error';
      alert(`Failed to calculate communities: ${errorMessage}`);
    } finally {
      setIsLoading(false);
    }
  }, [selectedNodeKeys, subgraphNodeKeys, loadNodeDetails]);

  const handleCreateSubgraphFromBetweenness = useCallback(async () => {
    try {
      setIsLoading(true);
      // Priority: subgraph > selected nodes > full graph
      let nodeKeysToAnalyze = null;
      let analysisScope = 'full graph';
      
      if (subgraphNodeKeys.length > 0) {
        // Use subgraph nodes if available
        nodeKeysToAnalyze = subgraphNodeKeys;
        analysisScope = `subgraph (${subgraphNodeKeys.length} nodes)`;
      } else if (selectedNodeKeys.length > 0) {
        // Use selected nodes if available
        nodeKeysToAnalyze = selectedNodeKeys;
        analysisScope = `${selectedNodeKeys.length} selected nodes`;
      }
      
      const betweennessData = await graphAPI.getBetweennessCentrality(nodeKeysToAnalyze, 20, true);
      
      // Check if nodes were found
      if (!betweennessData || !betweennessData.nodes || betweennessData.nodes.length === 0) {
        alert('No nodes found with betweenness centrality. The graph may be too small or disconnected.');
        return;
      }
      
      // Set the path subgraph data (reusing same mechanism)
      setPathSubgraphData(betweennessData);
      
      // Update selected nodes to include all nodes from betweenness analysis
      const betweennessNodeKeys = betweennessData.nodes.map(n => n.key);
      const betweennessNodes = betweennessData.nodes.map(node => ({
        key: node.key,
        id: node.id || node.key,
        name: node.name,
        type: node.type,
      }));
      setSelectedNodes(betweennessNodes);
      setTimelineContextKeys(betweennessNodeKeys);
      
      // Also update subgraphNodeKeys so add/remove buttons work
      setSubgraphNodeKeys(betweennessNodeKeys);
      
      // Generate analysis text for Betweenness Centrality
      const topNodes = betweennessData.nodes.slice(0, 10); // Top 10 nodes
      const topScore = betweennessData.nodes[0]?.betweenness_centrality || 0;
      const avgScore = betweennessData.nodes.reduce((sum, n) => sum + (n.betweenness_centrality || 0), 0) / betweennessData.nodes.length;
      
      let analysisText = `## Betweenness Centrality Analysis: Bridge Nodes\n\n`;
      analysisText += `**Analysis Scope:** ${analysisScope}\n\n`;
      analysisText += `**Summary:**\n`;
      analysisText += `- Total bridge nodes identified: **${betweennessData.nodes.length}**\n`;
      analysisText += `- Highest betweenness centrality: **${topScore.toFixed(6)}**\n`;
      analysisText += `- Average betweenness centrality: **${avgScore.toFixed(6)}**\n\n`;
      analysisText += `**Top Bridge Nodes:**\n\n`;
      
      topNodes.forEach((node, idx) => {
        analysisText += `${idx + 1}. **${node.name || node.key}** (${node.type || 'Unknown'})\n`;
        analysisText += `   - Betweenness Centrality: ${(node.betweenness_centrality || 0).toFixed(6)}\n`;
        if (node.summary) {
          analysisText += `   - Summary: ${node.summary}\n`;
        }
        analysisText += `\n`;
      });
      
      analysisText += `\n**Interpretation:**\n`;
      analysisText += `Betweenness centrality measures how often a node appears on the shortest path between other nodes. `;
      analysisText += `Nodes with high betweenness centrality are critical bridges or connectors in the network. `;
      analysisText += `These nodes control the flow of information or connections between different parts of the graph. `;
      analysisText += `Removing or disrupting these nodes could significantly impact network connectivity.`;
      
      setSubgraphAnalysis(analysisText);
      setSubgraphCommunityData(null); // Clear community data (not applicable for Betweenness)
      
      // Load details for all bridge nodes
      await loadNodeDetails(betweennessNodeKeys);
      
      // Enable split view
      setPaneViewMode('split');
      setIsSubgraphMenuOpen(false);
      
      console.log(`Betweenness centrality analysis complete on ${analysisScope}. Top node score: ${topScore.toFixed(6)}`);
    } catch (err) {
      console.error('Failed to get betweenness centrality:', err);
      const errorMessage = err?.message || err?.detail || err?.toString() || 'Unknown error';
      alert(`Failed to calculate betweenness centrality: ${errorMessage}`);
    } finally {
      setIsLoading(false);
    }
  }, [selectedNodeKeys, subgraphNodeKeys, loadNodeDetails]);
  
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
        .map(d => new Date(d))
        .filter(d => !isNaN(d.getTime())); // Filter out invalid dates
      
      if (dates.length > 0) {
        const minTimestamp = Math.min(...dates.map(d => d.getTime()));
        const maxTimestamp = Math.max(...dates.map(d => d.getTime()));
        
        // Validate timestamps before creating Date objects
        if (!isNaN(minTimestamp) && !isNaN(maxTimestamp)) {
          setDateExtents({
            min: new Date(minTimestamp).toISOString().split('T')[0],
            max: new Date(maxTimestamp).toISOString().split('T')[0],
          });
        }
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

  // Load snapshots on mount and when case changes
  useEffect(() => {
    const loadSnapshots = async () => {
      try {
        // If we have a current case, load snapshots from the case version
        if (currentCaseId && currentCaseVersion) {
          try {
            const caseData = await casesAPI.get(currentCaseId);
            if (caseData.versions && caseData.versions.length > 0) {
              // Find the current version
              const currentVersion = caseData.versions.find(v => v.version === currentCaseVersion) || caseData.versions[0];
              if (currentVersion && currentVersion.snapshots && currentVersion.snapshots.length > 0) {
                // Load full snapshot data for all snapshots in this version
                const snapshotList = [];
                for (const snap of currentVersion.snapshots) {
                  try {
                    // If it's already a full snapshot object, use it; otherwise fetch it
                    if (snap.subgraph || snap._chunked) {
                      snapshotList.push(snap);
                    } else if (snap.id) {
                      const fullSnapshot = await snapshotsAPI.get(snap.id);
                      snapshotList.push(fullSnapshot);
                    }
                  } catch (err) {
                    console.warn(`Failed to load snapshot ${snap.id}:`, err);
                    // If we can't load it, try to use the metadata we have
                    if (snap.id) {
                      snapshotList.push(snap);
                    }
                  }
                }
                // Sort by timestamp (most recent first)
                snapshotList.sort((a, b) => {
                  const dateA = new Date(a.timestamp || a.created_at || 0);
                  const dateB = new Date(b.timestamp || b.created_at || 0);
                  return dateB - dateA;
                });
                setSnapshots(snapshotList);
                return;
              }
            }
          } catch (err) {
            console.warn('Failed to load snapshots from case, falling back to global list:', err);
          }
        }
        
        // Fallback to global snapshot list
        const data = await snapshotsAPI.list();
        setSnapshots(data);
      } catch (err) {
        console.error('Failed to load snapshots:', err);
      }
    };
    loadSnapshots();
  }, [currentCaseId, currentCaseVersion]);

  // Export snapshot to PDF
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

      // Prepare snapshot data for PDF - include both user questions and AI responses
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

      const snapshot = {
        name: name || `Snapshot ${new Date().toLocaleString()}`,
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

      console.log('Exporting snapshot to PDF:', {
        name: snapshot.name,
        timelineCount: snapshot.timeline.length,
        timeline: snapshot.timeline
      });

      // Export to PDF
      await exportSnapshotToPDF(snapshot, graphCanvas);
      alert('PDF exported successfully!');
    } catch (err) {
      console.error('Failed to export PDF:', err);
      alert(`Failed to export PDF: ${err.message}`);
    }
  }, [subgraphNodeKeys, subgraphData, timelineData, selectedNodesDetails, chatHistory]);

  // Save snapshot
  const handleSaveSnapshot = useCallback(async (name, notes) => {
    if (subgraphNodeKeys.length === 0) {
      alert('Please add nodes to subgraph to save as a snapshot');
      return;
    }

    // Show progress dialog
    setSaveSnapshotProgress({
      isOpen: true,
      message: 'Preparing snapshot...',
      stage: null,
      stageProgress: 0,
      stageTotal: 0,
      current: 0,
      total: 5, // Loading nodes, extracting citations, filtering chat, generating AI overview, saving
    });

    try {
      // Stage 1: Load full node details for all subgraph nodes to get citations
      setSaveSnapshotProgress(prev => ({
        ...prev,
        stage: 'Loading node details',
        stageProgress: 0,
        stageTotal: subgraphNodeKeys.length,
        current: 1,
        message: `Loading details for ${subgraphNodeKeys.length} nodes...`,
      }));

      const BATCH_SIZE = 10;
      const allSubgraphNodeDetails = [];
      
      for (let i = 0; i < subgraphNodeKeys.length; i += BATCH_SIZE) {
        const batch = subgraphNodeKeys.slice(i, i + BATCH_SIZE);
        const batchPromises = batch.map(key => graphAPI.getNodeDetails(key));
        const batchResults = await Promise.all(batchPromises);
        allSubgraphNodeDetails.push(...batchResults);
        
        setSaveSnapshotProgress(prev => ({
          ...prev,
          stageProgress: Math.min(i + BATCH_SIZE, subgraphNodeKeys.length),
        }));
        
        // Small delay between batches
        if (i + BATCH_SIZE < subgraphNodeKeys.length) {
          await new Promise(resolve => setTimeout(resolve, 50));
        }
      }
      
      // Stage 2: Extract citations from all subgraph nodes
      setSaveSnapshotProgress(prev => ({
        ...prev,
        stage: 'Extracting citations',
        stageProgress: 0,
        stageTotal: allSubgraphNodeDetails.length,
        current: 2,
        message: 'Extracting source document citations...',
      }));

      const citations = {};
      for (let idx = 0; idx < allSubgraphNodeDetails.length; idx++) {
        const nodeDetail = allSubgraphNodeDetails[idx];
        if (!nodeDetail || !nodeDetail.key) continue;
        
        const nodeCitations = [];
        
        // Extract citations from verified_facts
        if (nodeDetail.verified_facts && Array.isArray(nodeDetail.verified_facts)) {
          for (const fact of nodeDetail.verified_facts) {
            if (fact.source_doc) {
              nodeCitations.push({
                source_doc: fact.source_doc,
                page: fact.page || null,
                type: 'verified_fact',
                fact_text: fact.text || null,
                verified_by: fact.verified_by || null,
              });
            }
          }
        }
        
        // Extract citations from ai_insights (if they have source info)
        if (nodeDetail.ai_insights && Array.isArray(nodeDetail.ai_insights)) {
          for (const insight of nodeDetail.ai_insights) {
            if (insight.source_doc) {
              nodeCitations.push({
                source_doc: insight.source_doc,
                page: insight.page || null,
                type: 'ai_insight',
                insight_text: insight.text || null,
                confidence: insight.confidence || null,
              });
            }
          }
        }
        
        // Also check node properties for source_doc
        if (nodeDetail.properties) {
          const props = nodeDetail.properties;
          if (props.source_doc) {
            nodeCitations.push({
              source_doc: props.source_doc,
              page: props.page || props.page_number || null,
              type: 'node_property',
            });
          }
        }
        
        if (nodeCitations.length > 0) {
          citations[nodeDetail.key] = {
            node_key: nodeDetail.key,
            node_name: nodeDetail.name,
            node_type: nodeDetail.type,
            citations: nodeCitations,
          };
        }

        if (idx % 10 === 0) {
          setSaveSnapshotProgress(prev => ({
            ...prev,
            stageProgress: idx + 1,
          }));
        }
      }
      
      // Stage 3: Filter chat history
      setSaveSnapshotProgress(prev => ({
        ...prev,
        stage: 'Processing chat history',
        stageProgress: 0,
        stageTotal: chatHistory.length,
        current: 3,
        message: 'Filtering relevant chat history...',
      }));

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

        if (i % 5 === 0) {
          setSaveSnapshotProgress(prev => ({
            ...prev,
            stageProgress: i + 1,
          }));
        }
      }

      // Stage 4: Generate AI overview of the snapshot
      setSaveSnapshotProgress(prev => ({
        ...prev,
        stage: 'Generating AI overview',
        stageProgress: 0,
        stageTotal: 1,
        current: 4,
        message: 'Generating AI overview...',
      }));

      let aiOverview = null;
      try {
        // Create a prompt for the AI to generate an overview
        const nodeNames = allSubgraphNodeDetails
          .slice(0, 20) // Limit to first 20 nodes to avoid token limits
          .map(n => n.name || n.key)
          .join(', ');
        
        const overviewPrompt = `Provide a brief, readable overview (2-3 sentences) of this investigation snapshot. The snapshot contains ${subgraphData.nodes.length} nodes and ${subgraphData.links.length} relationships. Key entities include: ${nodeNames}. Focus on the main connections and insights.`;
        
        console.log('Generating AI overview for snapshot:', {
          nodeCount: subgraphData.nodes.length,
          linkCount: subgraphData.links.length,
          nodeNames: nodeNames.substring(0, 100) + '...',
          promptLength: overviewPrompt.length
        });
        
        const aiResponse = await chatAPI.ask(overviewPrompt, subgraphNodeKeys.slice(0, 10)); // Limit to 10 nodes for context
        
        console.log('Raw AI response:', aiResponse);
        
        // Extract answer from response - check multiple possible fields
        aiOverview = aiResponse?.answer || aiResponse?.response || aiResponse?.content || null;
        
        // Clean up the answer if it exists
        if (aiOverview && typeof aiOverview === 'string') {
          aiOverview = aiOverview.trim();
          // If empty after trimming, set to null
          if (aiOverview.length === 0) {
            aiOverview = null;
          }
        }
        
        console.log('AI overview generation result:', {
          hasResponse: !!aiResponse,
          responseType: typeof aiResponse,
          responseKeys: aiResponse ? Object.keys(aiResponse) : [],
          answer: aiResponse?.answer,
          response: aiResponse?.response,
          content: aiResponse?.content,
          aiOverview: aiOverview,
          success: !!aiOverview,
          length: aiOverview?.length || 0,
          preview: aiOverview?.substring(0, 100) || 'null'
        });
        
        if (!aiOverview) {
          console.warn('AI overview is null or empty. Full response:', JSON.stringify(aiResponse, null, 2));
        }
        
        setSaveSnapshotProgress(prev => ({
          ...prev,
          stageProgress: 1,
        }));
      } catch (err) {
        console.error('Failed to generate AI overview:', err);
        console.error('Error details:', {
          message: err.message,
          stack: err.stack,
          name: err.name
        });
        // Continue without AI overview if generation fails
        setSaveSnapshotProgress(prev => ({
          ...prev,
          stageProgress: 1,
        }));
      }

      // Create a deep copy of all snapshot data to prevent reference issues
      // This ensures that if the original state is modified later, it won't affect the saved snapshot
      const snapshot = {
        name: name || `Snapshot ${new Date().toLocaleString()}`,
        notes: notes || '',
        subgraph: JSON.parse(JSON.stringify(subgraphData)), // Deep copy subgraph
        timeline: JSON.parse(JSON.stringify(timelineData || [])), // Deep copy timeline
        overview: {
          nodes: JSON.parse(JSON.stringify(allSubgraphNodeDetails)), // Deep copy node details
          nodeCount: subgraphData.nodes.length,
          linkCount: subgraphData.links.length,
        },
        citations: JSON.parse(JSON.stringify(citations)), // Deep copy citations
        chat_history: JSON.parse(JSON.stringify(relevantChatHistory)), // Deep copy chat history
        ai_overview: aiOverview ? String(aiOverview) : null, // Ensure string, not reference
      };

      // Stage 5: Save snapshot
      setSaveSnapshotProgress(prev => ({
        ...prev,
        stage: 'Saving snapshot',
        stageProgress: 0,
        stageTotal: 1,
        current: 5,
        message: 'Saving snapshot to database...',
      }));

      console.log('Saving snapshot:', {
        name: snapshot.name,
        timelineCount: snapshot.timeline.length,
        nodeCount: snapshot.subgraph.nodes.length,
        linkCount: snapshot.subgraph.links.length,
        chatHistoryCount: snapshot.chat_history.length,
        hasAIOverview: !!aiOverview,
      });

      // Backend will automatically chunk large snapshots
      const savedSnapshot = await snapshotsAPI.create(snapshot);
      
      setSaveSnapshotProgress(prev => ({
        ...prev,
        stageProgress: 1,
      }));
      
      // Auto-save the case if there's a current case
      if (currentCaseId && currentCaseName) {
        setSaveSnapshotProgress(prev => ({
          ...prev,
          stage: 'Auto-saving case',
          stageProgress: 0,
          stageTotal: 1,
          current: 5,
          message: 'Auto-saving case...',
        }));

        try {
          // Get the current case to find all existing snapshots from the current version
          const currentCase = await casesAPI.get(currentCaseId);
          const snapshotData = [];
          
          // Get all snapshots from the current version (most recent version)
          if (currentCase.versions && currentCase.versions.length > 0) {
            const latestVersion = currentCase.versions[0];
            if (latestVersion.snapshots && latestVersion.snapshots.length > 0) {
              // Load full snapshot data for all existing snapshots in this version
              for (const snap of latestVersion.snapshots) {
                try {
                  // If it's already a full snapshot object, use it; otherwise fetch it
                  if (snap.subgraph || snap._chunked) {
                    snapshotData.push(snap);
                  } else {
                    const fullSnapshot = await snapshotsAPI.get(snap.id);
                    snapshotData.push(fullSnapshot);
                  }
                } catch (err) {
                  console.warn(`Failed to load snapshot ${snap.id}:`, err);
                  // If we can't load it, try to use the metadata we have
                  if (snap.id) {
                    snapshotData.push(snap);
                  }
                }
              }
            }
          }
          
          // Add the newly saved snapshot (avoid duplicates)
          const existingIds = new Set(snapshotData.map(s => s.id));
          if (!existingIds.has(savedSnapshot.id)) {
            snapshotData.push(savedSnapshot);
          }
          
          console.log(`Auto-saving case with ${snapshotData.length} snapshots (including new one)`);
          
          // Save case with updated snapshots
          await casesAPI.save({
            case_id: currentCaseId,
            case_name: currentCaseName,
            graph_data: fullGraphData,
            snapshots: snapshotData,
            save_notes: `Auto-saved after snapshot: ${snapshot.name}`,
          });
          
          // Update case version
          const updatedCase = await casesAPI.get(currentCaseId);
          if (updatedCase.versions && updatedCase.versions.length > 0) {
            setCurrentCaseVersion(updatedCase.versions[0].version);
          }
          
          console.log('Case auto-saved after snapshot creation');
        } catch (err) {
          console.warn('Failed to auto-save case after snapshot:', err);
          // Don't fail the snapshot save if case save fails
        }
      }
      
      // Close progress dialog and snapshot modal
      setSaveSnapshotProgress(prev => ({ ...prev, isOpen: false }));
      setShowSnapshotModal(false);
      
      // Also save chat history separately for easy reloading
      // Use the full chat history, not just relevant, to preserve complete context
      if (chatHistory.length > 0) {
        try {
          await chatHistoryAPI.create({
            name: `${snapshot.name} - Chat`,
            messages: chatHistory, // Save full chat history, not just relevant
            snapshot_id: savedSnapshot.id,
            case_id: currentCaseId,
            case_version: currentCaseVersion,
          });
        } catch (err) {
          console.warn('Failed to save chat history separately:', err);
          // Don't fail the snapshot save if chat history save fails
        }
      }
      
      // Reload snapshots list from current case version if available
      if (currentCaseId && currentCaseVersion) {
        try {
          const caseData = await casesAPI.get(currentCaseId);
          if (caseData.versions && caseData.versions.length > 0) {
            const currentVersion = caseData.versions.find(v => v.version === currentCaseVersion) || caseData.versions[0];
            if (currentVersion && currentVersion.snapshots && currentVersion.snapshots.length > 0) {
              // Load full snapshot data for all snapshots in this version
              const snapshotList = [];
              for (const snap of currentVersion.snapshots) {
                try {
                  if (snap.subgraph || snap._chunked) {
                    snapshotList.push(snap);
                  } else if (snap.id) {
                    const fullSnapshot = await snapshotsAPI.get(snap.id);
                    snapshotList.push(fullSnapshot);
                  }
                } catch (err) {
                  console.warn(`Failed to load snapshot ${snap.id}:`, err);
                  if (snap.id) {
                    snapshotList.push(snap);
                  }
                }
              }
              // Sort by timestamp (most recent first)
              snapshotList.sort((a, b) => {
                const dateA = new Date(a.timestamp || a.created_at || 0);
                const dateB = new Date(b.timestamp || b.created_at || 0);
                return dateB - dateA;
              });
              setSnapshots(snapshotList);
              alert('Snapshot saved successfully!');
              return;
            }
          }
        } catch (err) {
          console.warn('Failed to load snapshots from case, falling back to global list:', err);
        }
      }
      
      // Fallback to global snapshot list
      const data = await snapshotsAPI.list();
      setSnapshots(data);
      
      alert('Snapshot saved successfully!');
    } catch (err) {
      console.error('Failed to save snapshot:', err);
      setSaveSnapshotProgress(prev => ({ ...prev, isOpen: false }));
      alert(`Failed to save snapshot: ${err.message}`);
    }
  }, [subgraphNodeKeys, subgraphData, timelineData, selectedNodesDetails, chatHistory, currentCaseId, currentCaseName, currentCaseVersion, fullGraphData, snapshots]);

  const [lastGraphInfo, setLastGraphInfo] = useState(null);

  // Create a new (empty) case from the case management view and go to evidence processing.
  // Before creating the new case, capture the current graph as Cypher and clear it
  // so the user starts with a fresh canvas. The Cypher is stored as "last graph"
  // and can be reloaded from the case management top bar.
  const handleCreateCase = useCallback(
    async (caseName, saveNotes) => {
      try {
        // Ask backend to snapshot the current graph and then clear it
        try {
          const last = await graphAPI.clearGraph();
          if (last && last.cypher) {
            setLastGraphInfo(last);
          }

          // Clear frontend graph-related state so the canvas is visually empty
          setGraphData({ nodes: [], links: [] });
          setFullGraphData({ nodes: [], links: [] });
          setSelectedNodes([]);
          setSubgraphNodeKeys([]);
          setTimelineContextKeys([]);
        } catch (err) {
          console.warn('Failed to snapshot & clear existing graph before creating case:', err);
          // Continue with case creation even if snapshot/clear fails
        }

        const emptyGraph = { nodes: [], links: [] };
        const result = await casesAPI.save({
          case_id: null,
          case_name: caseName,
          graph_data: emptyGraph,
          snapshots: [],
          save_notes: saveNotes,
        });

        // Set current case context
        setCurrentCaseId(result.case_id);
        setCurrentCaseName(caseName);
        setCurrentCaseVersion(result.version);
        setLoadedCypherQueries(null); // Clear loaded Cypher queries for new case

        // Switch to evidence processing view for this new case
        setAppView('evidence');
      } catch (err) {
        console.error('Failed to create case:', err);
        alert(`Failed to create case: ${err.message}`);
      }
    },
    []
  );

  // Save case
  const handleSaveCase = useCallback(async (caseName, saveNotes) => {
    try {
      // Get full snapshot data for all snapshots
      // First, try to get snapshots from the current case version if it exists
      const snapshotData = [];
      
      if (currentCaseId) {
        try {
          const currentCase = await casesAPI.get(currentCaseId);
          if (currentCase.versions && currentCase.versions.length > 0) {
            const latestVersion = currentCase.versions[0];
            if (latestVersion.snapshots && latestVersion.snapshots.length > 0) {
              // Load full snapshot data for all existing snapshots in this version
              for (const snap of latestVersion.snapshots) {
                try {
                  // If it's already a full snapshot object, use it; otherwise fetch it
                  if (snap.subgraph || snap._chunked) {
                    snapshotData.push(snap);
                  } else {
                    const fullSnapshot = await snapshotsAPI.get(snap.id);
                    snapshotData.push(fullSnapshot);
                  }
                } catch (err) {
                  console.warn(`Failed to load snapshot ${snap.id}:`, err);
                  // If we can't load it, try to use the metadata we have
                  if (snap.id) {
                    snapshotData.push(snap);
                  }
                }
              }
            }
          }
        } catch (err) {
          console.warn('Failed to load current case for snapshots:', err);
        }
      }
      
      // Also include any snapshots from the snapshots state that aren't already included
      const existingIds = new Set(snapshotData.map(s => s.id));
      for (const snapshot of snapshots) {
        if (!existingIds.has(snapshot.id)) {
          try {
            const fullSnapshot = await snapshotsAPI.get(snapshot.id);
            snapshotData.push(fullSnapshot);
          } catch (err) {
            console.warn(`Failed to load snapshot ${snapshot.id}:`, err);
            // Continue with other snapshots
          }
        }
      }
      
      // Save case with current graph data and full snapshot data
      const result = await casesAPI.save({
        case_id: currentCaseId, // Will be null for new case
        case_name: caseName,
        graph_data: fullGraphData, // Use full graph data (unfiltered)
        snapshots: snapshotData, // Full snapshot data
        save_notes: saveNotes,
      });
      
      // Update current case info
      setCurrentCaseId(result.case_id);
      setCurrentCaseName(caseName);
      setCurrentCaseVersion(result.version);
      setShowCaseModal(false);
      
      alert(`Case saved successfully! Version ${result.version} saved.`);
    } catch (err) {
      console.error('Failed to save case:', err);
      alert(`Failed to save case: ${err.message}`);
    }
  }, [fullGraphData, snapshots, currentCaseId]);

  // Load case version
  const handleLoadCase = useCallback(async (caseData, versionData) => {
    // Check if this case/version is already loaded - if so, just switch to graph view
    if (currentCaseId === caseData.id && currentCaseVersion === versionData.version) {
      console.log('Case/version already loaded, switching to graph view without reloading');
      setAppView('graph');
      return;
    }
    
    // Get Cypher queries for the new version
    const newCypherQueries = versionData.cypher_queries;
    
    if (!newCypherQueries) {
      alert('No Cypher queries found in this case version');
      return;
    }
    
    // Check if switching to a different case
    const isSwitchingCase = currentCaseId !== caseData.id;
    
    // Check if switching to a different version (same case)
    const isSwitchingVersion = !isSwitchingCase && currentCaseVersion !== versionData.version;
    
    // Quick diff: Compare with last loaded Cypher queries
    // If Cypher queries are identical, skip graph reload and just open graph view
    const cypherQueriesAreSame = loadedCypherQueries && 
                                  compareCypherQueries(loadedCypherQueries, newCypherQueries);
    
    if (cypherQueriesAreSame && !isSwitchingCase && !isSwitchingVersion) {
      console.log('Cypher queries identical to last loaded version - skipping graph reload, opening graph view');
      // Skip graph reload - just update case info and switch to graph view
      setCurrentCaseId(caseData.id);
      setCurrentCaseName(caseData.name);
      setCurrentCaseVersion(versionData.version);
      
      // Load snapshots and chats for this version (see below)
      // This will be handled in the common section after the if/else
    } else if (isSwitchingCase) {
      // ALWAYS do full reload when switching to a different case
      console.log('Switching to different case - performing full graph reload');
      
      // Split queries by double newlines
      const queries = newCypherQueries.split('\n\n').map(q => q.trim()).filter(q => q);
      
      if (queries.length === 0) {
        alert('No valid Cypher queries found in this case version');
        return;
      }
      
      // Show progress dialog
      setLoadCaseProgress(prev => ({
        ...prev,
        isOpen: true,
        current: 0,
        total: queries.length,
        caseName: caseData.name,
        version: versionData.version,
      }));
      
      await new Promise(resolve => setTimeout(resolve, 300));
      
      try {
        setIsLoading(true);
        
        // Always clear graph when switching to different case
        try {
          await graphAPI.clearGraph();
          setLoadedCypherQueries(null);
        } catch (err) {
          console.warn('Failed to clear existing graph before loading case:', err);
        }
        
        // Execute queries with optimized batching strategy:
        // - Under 50: one by one
        // - 50-500: batches of 50
        // - Over 500: batches of 200
        const errors = [];
        if (queries.length < 50) {
          // Execute one at a time for small query sets
          console.log(`Using single-query execution for ${queries.length} queries`);
          for (let i = 0; i < queries.length; i++) {
            try {
              const result = await graphAPI.executeSingleQuery(queries[i]);
              if (!result.success) {
                errors.push(result.error || `Query ${i + 1} failed`);
              }
              
              setLoadCaseProgress(prev => ({
                ...prev,
                current: i + 1,
              }));
            } catch (err) {
              errors.push(`Query ${i + 1} failed: ${err.message}`);
              setLoadCaseProgress(prev => ({
                ...prev,
                current: i + 1,
              }));
            }
          }
        } else {
          // Use batch execution for larger query sets
          const BATCH_SIZE = queries.length > 500 ? 200 : 50;
          console.log(`Using batch execution for ${queries.length} queries with batch size ${BATCH_SIZE}`);
          const numBatches = Math.ceil(queries.length / BATCH_SIZE);
          
          for (let batchIdx = 0; batchIdx < numBatches; batchIdx++) {
            const batchStart = batchIdx * BATCH_SIZE;
            const batchEnd = Math.min(batchStart + BATCH_SIZE, queries.length);
            const batch = queries.slice(batchStart, batchEnd);
            
            try {
              const result = await graphAPI.executeBatchQueries(batch, BATCH_SIZE);
              if (!result.success && result.errors) {
                errors.push(...result.errors);
              }
              
              // Update progress after each batch
              setLoadCaseProgress(prev => ({
                ...prev,
                current: batchEnd,
              }));
            } catch (err) {
              errors.push(`Batch ${batchIdx + 1} failed: ${err.message}`);
              setLoadCaseProgress(prev => ({
                ...prev,
                current: batchEnd,
              }));
            }
          }
        }
        
        setLoadCaseProgress(prev => ({ ...prev, isOpen: false }));
        
        if (errors.length > 0) {
          console.error('Some queries failed during case load:', errors);
          const details = errors.join('\n');
          alert(
            `Case loaded with ${errors.length} error(s) out of ${queries.length} queries.\n\n` +
            (details ? `Details:\n${details}` : '')
          );
        }

        await loadGraph();
        setLoadedCypherQueries(newCypherQueries);
        setCurrentCaseId(caseData.id);
        setCurrentCaseName(caseData.name);
        setCurrentCaseVersion(versionData.version);
      } catch (err) {
        console.error('Failed to load case:', err);
        setLoadCaseProgress(prev => ({ ...prev, isOpen: false }));
        alert(`Failed to load case: ${err.message}`);
        setIsLoading(false);
        return;
      } finally {
        setIsLoading(false);
        setLoadCaseProgress(prev => ({ ...prev, isOpen: false }));
      }
    } else if (isSwitchingVersion) {
      // Same case, different version - use delta/incremental updates if Cypher differs
      console.log('Switching to different version in same case - calculating delta for incremental updates');
      
      // Calculate delta between old and new Cypher queries
      const delta = calculateCypherDelta(loadedCypherQueries, newCypherQueries);
      
      console.log('Delta calculation:', {
        toAdd: delta.toAdd.length,
        toRemove: delta.toRemove.length,
        deletes: delta.newDeletes?.length || 0,
        isFullReload: delta.isFullReload
      });
      
      // If delta suggests full reload or no changes, do full reload
      if (delta.isFullReload || (!delta.toAdd.length && !delta.toRemove.length && !delta.newDeletes?.length)) {
        console.log('Delta suggests full reload - performing full graph reload');
        
        // Split queries by double newlines
        const queries = newCypherQueries.split('\n\n').map(q => q.trim()).filter(q => q);
        
        if (queries.length === 0) {
          alert('No valid Cypher queries found in this case version');
          return;
        }
        
        // Show progress dialog
        setLoadCaseProgress(prev => ({
          ...prev,
          isOpen: true,
          current: 0,
          total: queries.length,
          caseName: caseData.name,
          version: versionData.version,
        }));
        
        await new Promise(resolve => setTimeout(resolve, 300));
        
        try {
          setIsLoading(true);
          
          // Execute queries with optimized batching strategy
          const errors = [];
          if (queries.length < 50) {
            console.log(`Using single-query execution for ${queries.length} queries`);
            for (let i = 0; i < queries.length; i++) {
              try {
                const result = await graphAPI.executeSingleQuery(queries[i]);
                if (!result.success) {
                  errors.push(result.error || `Query ${i + 1} failed`);
                }
                
                setLoadCaseProgress(prev => ({
                  ...prev,
                  current: i + 1,
                }));
              } catch (err) {
                errors.push(`Query ${i + 1} failed: ${err.message}`);
                setLoadCaseProgress(prev => ({
                  ...prev,
                  current: i + 1,
                }));
              }
            }
          } else {
            const BATCH_SIZE = queries.length > 500 ? 200 : 50;
            console.log(`Using batch execution for ${queries.length} queries with batch size ${BATCH_SIZE}`);
            const numBatches = Math.ceil(queries.length / BATCH_SIZE);
            
            for (let batchIdx = 0; batchIdx < numBatches; batchIdx++) {
              const batchStart = batchIdx * BATCH_SIZE;
              const batchEnd = Math.min(batchStart + BATCH_SIZE, queries.length);
              const batch = queries.slice(batchStart, batchEnd);
              
              try {
                const result = await graphAPI.executeBatchQueries(batch, BATCH_SIZE);
                if (!result.success && result.errors) {
                  errors.push(...result.errors);
                }
                
                setLoadCaseProgress(prev => ({
                  ...prev,
                  current: batchEnd,
                }));
              } catch (err) {
                errors.push(`Batch ${batchIdx + 1} failed: ${err.message}`);
                setLoadCaseProgress(prev => ({
                  ...prev,
                  current: batchEnd,
                }));
              }
            }
          }
          
          setLoadCaseProgress(prev => ({ ...prev, isOpen: false }));
          
          if (errors.length > 0) {
            console.error('Some queries failed during case load:', errors);
            const details = errors.join('\n');
            alert(
              `Case loaded with ${errors.length} error(s) out of ${queries.length} queries.\n\n` +
              (details ? `Details:\n${details}` : '')
            );
          }

          await loadGraph();
          setLoadedCypherQueries(newCypherQueries);
          setCurrentCaseId(caseData.id);
          setCurrentCaseName(caseData.name);
          setCurrentCaseVersion(versionData.version);
        } catch (err) {
          console.error('Failed to load case:', err);
          setLoadCaseProgress(prev => ({ ...prev, isOpen: false }));
          alert(`Failed to load case: ${err.message}`);
          setIsLoading(false);
          return;
        } finally {
          setIsLoading(false);
          setLoadCaseProgress(prev => ({ ...prev, isOpen: false }));
        }
      } else {
        // Apply incremental updates (delta)
        console.log('Applying incremental graph updates (delta):', {
          toAdd: delta.toAdd.length,
          toRemove: delta.toRemove.length,
          deletes: delta.newDeletes?.length || 0
        });
        
        const incrementalQueries = buildIncrementalQueries(delta);
        
        if (incrementalQueries.length === 0) {
          console.log('No incremental changes to apply');
          // Still update case info
          setCurrentCaseId(caseData.id);
          setCurrentCaseName(caseData.name);
          setCurrentCaseVersion(versionData.version);
        } else {
          // Show progress dialog for incremental updates
          setLoadCaseProgress(prev => ({
            ...prev,
            isOpen: true,
            current: 0,
            total: incrementalQueries.length,
            caseName: caseData.name,
            version: versionData.version,
          }));
          
          await new Promise(resolve => setTimeout(resolve, 300));
          
          try {
            setIsLoading(true);
            
            // Execute incremental queries (additions first, then deletions)
            const errors = [];
            for (let i = 0; i < incrementalQueries.length; i++) {
              try {
                const result = await graphAPI.executeSingleQuery(incrementalQueries[i]);
                if (!result.success) {
                  errors.push(result.error || `Incremental query ${i + 1} failed`);
                }
                
                setLoadCaseProgress(prev => ({
                  ...prev,
                  current: i + 1,
                }));
              } catch (err) {
                errors.push(`Incremental query ${i + 1} failed: ${err.message}`);
                setLoadCaseProgress(prev => ({
                  ...prev,
                  current: i + 1,
                }));
              }
            }
            
            setLoadCaseProgress(prev => ({ ...prev, isOpen: false }));
            
            if (errors.length > 0) {
              console.warn('Some incremental queries failed:', errors);
              // Don't alert for incremental failures, just log
            }
            
            // Reload graph to reflect changes
            await loadGraph();
            
            // Store the loaded Cypher queries for future comparison
            setLoadedCypherQueries(newCypherQueries);
            
            // Set current case info
            setCurrentCaseId(caseData.id);
            setCurrentCaseName(caseData.name);
            setCurrentCaseVersion(versionData.version);
          } catch (err) {
            console.error('Failed to apply incremental updates:', err);
            setLoadCaseProgress(prev => ({ ...prev, isOpen: false }));
            // Fall back to full reload on error
            console.log('Falling back to full reload due to incremental update error');
            alert(`Failed to apply incremental updates: ${err.message}. Please try reloading the case.`);
            setIsLoading(false);
            return;
          } finally {
            setIsLoading(false);
            setLoadCaseProgress(prev => ({ ...prev, isOpen: false }));
          }
        }
      }
    }
    
    // Common section: Update case info and load snapshots/chats (for both same and different Cypher cases)
    try {
      // Store previous case ID to check if we're switching cases
      const previousCaseId = currentCaseId;
      
      // Case info is already set above (either in same-Cypher branch or after graph reload)
      
      // If switching to a different case, clear chat history and load case-specific history
      if (previousCaseId !== caseData.id) {
        // Clear current chat history when switching cases
        setChatHistory([]);
      }
      
      // Load chat history for this case/version (always load, even if same case, to get version-specific chats)
      try {
        const allChatHistories = await chatHistoryAPI.list();
        const caseChatHistories = allChatHistories
          .filter(chat => chat.case_id === caseData.id && chat.case_version === versionData.version)
          .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        
        if (caseChatHistories.length > 0) {
          // Use the most recent case-specific chat history
          const latestChat = caseChatHistories[0];
          setChatHistory(latestChat.messages);
        } else if (previousCaseId !== caseData.id) {
          // If switching cases and no chat history found, clear it
          setChatHistory([]);
        }
      } catch (err) {
        console.warn('Failed to load case chat history:', err);
        // Continue without chat history
      }
      
      // Restore snapshots from the case version
      // First, clear all existing snapshots that belong to this case (to avoid duplicates)
      const allSnapshots = await snapshotsAPI.list();
      for (const existingSnapshot of allSnapshots) {
        try {
          const fullSnapshot = await snapshotsAPI.get(existingSnapshot.id);
          // If this snapshot belongs to the same case, delete it before restoring version-specific ones
          if (fullSnapshot.case_id === caseData.id) {
            await snapshotsAPI.delete(existingSnapshot.id);
          }
        } catch (err) {
          // Snapshot might not exist, continue
        }
      }
      
      // Now restore snapshots from this specific version
      if (versionData.snapshots && versionData.snapshots.length > 0) {
        // Restore each snapshot to the snapshot storage
        for (const snapshotData of versionData.snapshots) {
          try {
            // Ensure snapshot has case and version metadata
            snapshotData.case_id = caseData.id;
            snapshotData.case_version = versionData.version;
            snapshotData.case_name = caseData.name;
            
            // Restore the snapshot using the restore endpoint
            await snapshotsAPI.restore(snapshotData);
          } catch (err) {
            console.warn(`Failed to restore snapshot ${snapshotData.id}:`, err);
            // Continue with other snapshots
          }
        }
        
        // Reload snapshots list to reflect restored snapshots
        const snapshotsData = await snapshotsAPI.list();
        setSnapshots(snapshotsData);
      } else {
        // No snapshots in this version, clear current snapshots list
        setSnapshots([]);
      }
      
      // Switch to graph view
      setAppView('graph');
      
      if (cypherQueriesAreSame) {
        console.log('Case version loaded (Cypher queries unchanged, graph not reloaded)');
      }
    } catch (err) {
      console.error('Failed to load case snapshots/chats:', err);
      // Don't fail the entire load if snapshots/chats fail
    }
  }, [loadGraph, currentCaseId, currentCaseVersion, loadedCypherQueries]);

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

  // Show case management view if appView is 'caseManagement'
  if (appView === 'caseManagement') {
    return (
      <>
        <CaseManagementView
          onLoadCase={handleLoadCase}
          onCreateCase={handleCreateCase}
          onLogout={handleLogout}
          isAuthenticated={isAuthenticated}
          authUsername={authUsername}
          onGoToGraphView={() => setAppView('graph')}
          onGoToEvidenceView={(caseData) => {
            if (!caseData) return;
            setCurrentCaseId(caseData.id);
            setCurrentCaseName(caseData.name);
            // Keep currentCaseVersion unchanged; evidence processing doesn't depend on it
            setAppView('evidence');
          }}
          initialCaseToSelect={caseToSelect}
          onViewDocument={handleViewDocument}
          onCaseSelected={() => setCaseToSelect(null)}
          onLoadLastGraph={async () => {
            try {
              // If we don't have lastGraphInfo in memory yet, fetch from backend
              let info = lastGraphInfo;
              if (!info || !info.cypher) {
                info = await graphAPI.getLastGraph();
                setLastGraphInfo(info);
              }

              if (!info || !info.cypher) {
                alert('No last graph is available to load.');
                return;
              }

              const result = await graphAPI.loadCase(info.cypher);
              if (!result.success) {
                console.error('Last graph load sanity check failed:', result.errors);
                const details = (result.errors || []).join('\n');
                alert(
                  `Failed to load last graph: one or more Cypher statements did not validate.\n\n` +
                  (details ? `Details:\n${details}` : '')
                );
                return;
              }
              await loadGraph();
              setAppView('graph');
              alert('Last graph loaded successfully.');
            } catch (err) {
              console.error('Failed to load last graph:', err);
              alert(`Failed to load last graph: ${err.message}`);
            }
          }}
          lastGraphInfo={lastGraphInfo}
        />
        {/* Load Case Progress Dialog - must be rendered in all views */}
        <LoadCaseProgressDialog
          isOpen={loadCaseProgress.isOpen}
          onClose={() => {
            // Only allow closing if loading is complete
            if (loadCaseProgress.current >= loadCaseProgress.total) {
              setLoadCaseProgress(prev => ({ ...prev, isOpen: false }));
            }
          }}
          current={loadCaseProgress.current}
          total={loadCaseProgress.total}
          caseName={loadCaseProgress.caseName}
          version={loadCaseProgress.version}
        />
        
        {/* Document Viewer Modal - must be rendered in all views */}
        <DocumentViewer
          isOpen={documentViewerState.isOpen}
          onClose={handleCloseDocumentViewer}
          documentUrl={documentViewerState.documentUrl}
          documentName={documentViewerState.documentName}
          initialPage={documentViewerState.page}
          highlightText={documentViewerState.highlightText}
        />
      </>
    );
  }

  // Evidence processing view for current case
  if (appView === 'evidence') {
    return (
      <>
        <EvidenceProcessingView
        caseId={currentCaseId}
        caseName={currentCaseName}
        onBackToCases={() => setAppView('caseManagement')}
        authUsername={authUsername}
        onViewCase={(caseId, version) => {
          setCaseToSelect({ caseId, version });
          setAppView('caseManagement');
        }}
        onGoToGraph={async () => {
          try {
            if (!currentCaseId) {
              // No case yet: ensure we show an empty graph
              await graphAPI.clearGraph().catch(() => {});
              setGraphData({ nodes: [], links: [] });
              setFullGraphData({ nodes: [], links: [] });
              await loadGraph();
              setAppView('graph');
              return;
            }

            // Load the latest case version's Cypher, if any
            const caseData = await casesAPI.get(currentCaseId);
            const versions = caseData.versions || [];
            if (versions.length > 0) {
              const sorted = [...versions].sort((a, b) => b.version - a.version);
              const latest = sorted[0];
              
              // Check if this case/version is already loaded
              if (currentCaseId === caseData.id && currentCaseVersion === latest.version) {
                // Already loaded, just switch to graph view
                console.log('Case/version already loaded, switching to graph view');
                setAppView('graph');
                return;
              }
              
              if (latest.cypher_queries && latest.cypher_queries.trim()) {
                // Only clear if switching to a different case/version
                if (currentCaseId !== caseData.id || currentCaseVersion !== latest.version) {
                  await graphAPI.clearGraph().catch((err) => {
                    console.warn('Failed to clear existing graph before opening case in graph:', err);
                  });
                }
                const result = await graphAPI.loadCase(latest.cypher_queries);
                if (!result.success) {
                  console.error('Case load (from Evidence view) sanity check failed:', result.errors);
                  const details = (result.errors || []).join('\n');
                  alert(
                    `Failed to load case graph: one or more Cypher statements did not validate.\n\n` +
                    (details ? `Details:\n${details}` : '')
                  );
                  return;
                }
                await loadGraph();
                setCurrentCaseId(caseData.id);
                setCurrentCaseName(caseData.name);
                setCurrentCaseVersion(latest.version);
                setAppView('graph');
                return;
              }
            }

            // No Cypher exists for this case yet: show an empty graph
            // Only clear if we don't already have this case loaded
            if (currentCaseId !== caseData.id) {
              await graphAPI.clearGraph().catch(() => {});
              setGraphData({ nodes: [], links: [] });
              setFullGraphData({ nodes: [], links: [] });
            }
            await loadGraph();
            setAppView('graph');
          } catch (err) {
            console.error('Failed to open case in graph:', err);
            alert(`Failed to open case in graph: ${err.message}`);
          }
        }}
        onLoadProcessedGraph={async (caseId, version) => {
          try {
            // Check if this case/version is already loaded
            if (currentCaseId === caseId && currentCaseVersion === version) {
              console.log('Case/version already loaded, switching to graph view');
              setAppView('graph');
              return;
            }
            
            const versionData = await casesAPI.getVersion(caseId, version);
            if (!versionData || !versionData.cypher_queries) {
              alert('No Cypher queries found for the processed case version.');
              return;
            }
            
            // Only clear if switching to a different case/version
            if (currentCaseId !== caseId || currentCaseVersion !== version) {
              await graphAPI.clearGraph().catch(() => {});
            }
            
            const result = await graphAPI.loadCase(versionData.cypher_queries);
            if (!result.success) {
              console.error('Processed graph load sanity check failed:', result.errors);
              const details = (result.errors || []).join('\n');
              alert(
                `Failed to load processed graph: one or more Cypher statements did not validate.\n\n` +
                (details ? `Details:\n${details}` : '')
              );
              return;
            }
            await loadGraph();
            setCurrentCaseId(caseId);
            setCurrentCaseName(currentCaseName || '');
            setCurrentCaseVersion(version);
            setAppView('graph');
            alert('Processed graph loaded successfully.');
          } catch (err) {
            console.error('Failed to load processed graph:', err);
            alert(`Failed to load processed graph: ${err.message}`);
          }
        }}
      />
        {/* Load Case Progress Dialog - must be rendered in all views */}
        <LoadCaseProgressDialog
          isOpen={loadCaseProgress.isOpen}
          onClose={() => {
            // Only allow closing if loading is complete
            if (loadCaseProgress.current >= loadCaseProgress.total) {
              setLoadCaseProgress(prev => ({ ...prev, isOpen: false }));
            }
          }}
          current={loadCaseProgress.current}
          total={loadCaseProgress.total}
          caseName={loadCaseProgress.caseName}
          version={loadCaseProgress.version}
        />
      </>
    );
  }

  return (
    <div className="h-screen w-screen bg-light-50 flex flex-col overflow-hidden">
      {/* Header */}
      <header className="h-16 bg-white border-b border-light-200 flex items-center justify-between px-4 flex-shrink-0 shadow-sm">
        <div className="flex items-center gap-3 relative">
          {/* File Management Button */}
          <button
            onClick={() => setShowFilePanel(!showFilePanel)}
            className={`p-2 rounded-lg transition-colors ${
              showFilePanel
                ? 'bg-owl-blue-500 text-white'
                : 'hover:bg-light-100 text-light-600'
            }`}
            title="File Management"
          >
            <HardDrive className="w-5 h-5" />
          </button>

          {/* Background Tasks Button */}
          <button
            onClick={() => setShowBackgroundTasksPanel(!showBackgroundTasksPanel)}
            className={`p-2 rounded-lg transition-colors relative ${
              showBackgroundTasksPanel
                ? 'bg-owl-blue-500 text-white'
                : 'hover:bg-light-100 text-light-600'
            }`}
            title="Background Tasks"
          >
            <Loader2 className="w-5 h-5" />
          </button>

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
                    onClick={() => {
                      setShowDocumentation(true);
                      setIsAccountDropdownOpen(false);
                    }}
                    className="w-full text-left px-2 py-1 rounded hover:bg-light-100 transition-colors text-sm text-dark-700"
                  >
                    Documentation
                  </button>
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
                <div className="px-3 py-2 space-y-1">
                  <button
                    onClick={() => {
                      setShowDocumentation(true);
                      setIsAccountDropdownOpen(false);
                    }}
                    className="w-full text-left px-2 py-1 rounded hover:bg-light-100 transition-colors text-sm text-dark-700"
                  >
                    Documentation
                  </button>
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

          {/* Current Case Name */}
          <div className="flex flex-col">
            <span className="text-sm font-semibold text-owl-blue-900">
              {currentCaseName || 'No Case Loaded'}
            </span>
            {viewMode === 'graph' && (
              <span className="text-xs text-light-600 bg-light-100 px-2 py-1 rounded mt-1">
                {selectedNodes.length > 0 
                  ? `${subgraphData.nodes.length} selected · ${subgraphData.links.length} connections`
                  : `${graphData.nodes.length} entities · ${graphData.links.length} relationships`
                }
              </span>
            )}
          </div>
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

                  <button
                    onClick={handleCreateSubgraphFromPageRank}
                    className="w-full text-left px-3 py-2 text-sm text-light-800 hover:bg-light-50 transition-colors cursor-pointer"
                  >
                    <div className="flex items-center gap-2">
                      <TrendingUp className="w-4 h-4" />
                      <span>PageRank (Influential Nodes)</span>
                    </div>
                    <div className="text-xs text-light-500 mt-0.5 ml-6">
                      {selectedNodeKeys.length > 0 
                        ? `Analyze ${selectedNodeKeys.length} selected nodes`
                        : 'Analyze full graph'}
                    </div>
                  </button>

                  <button
                    onClick={handleCreateSubgraphFromLouvain}
                    className="w-full text-left px-3 py-2 text-sm text-light-800 hover:bg-light-50 transition-colors cursor-pointer"
                  >
                    <div className="flex items-center gap-2">
                      <Users className="w-4 h-4" />
                      <span>Louvain (Communities)</span>
                    </div>
                    <div className="text-xs text-light-500 mt-0.5 ml-6">
                      {subgraphNodeKeys.length > 0
                        ? `Find communities in subgraph (${subgraphNodeKeys.length} nodes)`
                        : selectedNodeKeys.length > 0 
                        ? `Find communities in ${selectedNodeKeys.length} selected nodes`
                        : 'Find communities in full graph'}
                    </div>
                  </button>

                  <button
                    onClick={handleCreateSubgraphFromBetweenness}
                    className="w-full text-left px-3 py-2 text-sm text-light-800 hover:bg-light-50 transition-colors cursor-pointer"
                  >
                    <div className="flex items-center gap-2">
                      <Target className="w-4 h-4" />
                      <span>Betweenness Centrality (Bridge Nodes)</span>
                    </div>
                    <div className="text-xs text-light-500 mt-0.5 ml-6">
                      {subgraphNodeKeys.length > 0
                        ? `Find bridges in subgraph (${subgraphNodeKeys.length} nodes)`
                        : selectedNodeKeys.length > 0 
                        ? `Find bridges in ${selectedNodeKeys.length} selected nodes`
                        : 'Find bridges in full graph'}
                    </div>
                  </button>
                  
                  {paneViewMode === 'split' && (
                    <div className="border-t border-light-200 mt-1 pt-1">
                  <button
                    onClick={() => {
                      setPaneViewMode('single');
                      setPathSubgraphData(null); // Clear path subgraph when closing
                      setSubgraphAnalysis(null); // Clear analysis when closing
                      setSubgraphCommunityData(null); // Clear community data
                      setIsAnalysisExpanded(false); // Reset analysis expansion
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
            <button
              onClick={() => setViewMode('map')}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors ${
                viewMode === 'map'
                  ? 'bg-white text-owl-blue-900 shadow-sm'
                  : 'text-light-600 hover:text-light-800'
              }`}
            >
              <MapPin className="w-4 h-4" />
              Map
            </button>
          </div>

          {/* Date Range Filter */}
          {(viewMode === 'graph' || viewMode === 'timeline' || viewMode === 'map') && (
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
            <>
            {/* Relationship Mode Indicator */}
            {isRelationshipMode && (
              <div className="absolute top-20 left-1/2 transform -translate-x-1/2 z-50 bg-owl-blue-600 text-white px-6 py-3 rounded-lg shadow-lg flex items-center gap-3">
                <Link2 className="w-5 h-5" />
                <div>
                  <div className="font-semibold">Relationship Creation Mode</div>
                  <div className="text-sm text-owl-blue-100">
                    Source: {relationshipSourceNodes.map(n => n.name).join(', ')} • Select target node(s) and right-click to create relationship
                  </div>
                </div>
                <button
                  onClick={() => {
                    setIsRelationshipMode(false);
                    setRelationshipSourceNodes([]);
                  }}
                  className="ml-4 px-3 py-1 bg-white/20 hover:bg-white/30 rounded text-sm transition-colors"
                >
                  Cancel
                </button>
              </div>
            )}
            {isLoading && graphData.nodes.length === 0 ? (
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
                    onNodeDoubleClick={handleNodeDoubleClick}
                    onBackgroundClick={handleBackgroundClick}
                    width={graphWidth}
                    height={graphHeight}
                    paneViewMode={paneViewMode}
                    onPaneViewModeChange={setPaneViewMode}
                    onAddToSubgraph={handleAddToSubgraph}
                    onRemoveFromSubgraph={handleRemoveFromSubgraph}
                    subgraphNodeKeys={subgraphNodeKeys}
                    onAddNode={() => setShowAddNodeModal(true)}
                  />
                </div>
                
                {/* Right Panel - Subgraph View */}
                <div className="flex-1 relative bg-light-50 overflow-hidden" data-subgraph-container>
                  {subgraphNodeKeys.length > 0 ? (
                    // Show subgraph of selected nodes
                    <>
                      <div className="absolute top-4 left-4 right-4 z-10 flex flex-col gap-2">
                        {/* Subgraph Header */}
                        <div className="flex items-center justify-between bg-white/90 backdrop-blur-sm rounded-lg p-2 px-3 shadow-sm border border-light-200">
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
                        
                        {/* Analysis Overview - Expandable */}
                        {subgraphAnalysis && (
                          <div className="bg-white rounded-lg shadow-sm border border-light-200 overflow-hidden">
                            <button
                              onClick={() => setIsAnalysisExpanded(!isAnalysisExpanded)}
                              className="w-full flex items-center justify-between p-3 hover:bg-light-50 transition-colors"
                            >
                              <div className="flex items-center gap-2">
                                <FileText className="w-4 h-4 text-owl-blue-700" />
                                <h4 className="text-sm font-semibold text-owl-blue-900">Analysis Overview</h4>
                              </div>
                              {isAnalysisExpanded ? (
                                <ChevronUp className="w-4 h-4 text-light-600" />
                              ) : (
                                <ChevronDown className="w-4 h-4 text-light-600" />
                              )}
                            </button>
                            {isAnalysisExpanded && (
                              <div className="border-t border-light-200 max-h-96 overflow-y-auto p-4">
                                <div className="prose prose-sm max-w-none text-light-700 whitespace-pre-wrap break-words">
                                  {subgraphAnalysis.split('\n').map((line, idx) => {
                                    if (line.startsWith('## ')) {
                                      return <h2 key={idx} className="text-base font-bold text-owl-blue-900 mt-2 mb-1 break-words">{line.substring(3)}</h2>;
                                    } else if (line.startsWith('**') && line.endsWith('**')) {
                                      return <strong key={idx} className="font-semibold text-owl-blue-900 break-words">{line.replace(/\*\*/g, '')}</strong>;
                                    } else if (line.startsWith('- **')) {
                                      const parts = line.match(/\*\*(.*?)\*\*(.*)/);
                                      return <div key={idx} className="ml-4 mb-1 break-words"><strong className="font-semibold text-owl-blue-900">{parts[1]}</strong><span className="break-words">{parts[2]}</span></div>;
                                    } else if (line.startsWith('   - ')) {
                                      return <div key={idx} className="ml-8 text-xs mb-1 text-light-600 break-words">{line.substring(5)}</div>;
                                    } else if (line.trim() === '') {
                                      return <br key={idx} />;
                                    } else {
                                      // Parse node names in bold and make them clickable
                                      const renderLineWithClickableNodes = (text) => {
                                        // Match patterns like "1. **NodeName** (Type)" or "**NodeName**"
                                        const nodeNamePattern = /\*\*([^*]+)\*\*/g;
                                        const parts = [];
                                        let lastIndex = 0;
                                        let match;
                                        
                                        while ((match = nodeNamePattern.exec(text)) !== null) {
                                          // Add text before the match
                                          if (match.index > lastIndex) {
                                            parts.push({ type: 'text', content: text.substring(lastIndex, match.index) });
                                          }
                                          
                                          // Add the clickable node name
                                          const nodeName = match[1];
                                          parts.push({ type: 'node', name: nodeName });
                                          
                                          lastIndex = match.index + match[0].length;
                                        }
                                        
                                        // Add remaining text
                                        if (lastIndex < text.length) {
                                          parts.push({ type: 'text', content: text.substring(lastIndex) });
                                        }
                                        
                                        // If no matches, return the text as-is
                                        if (parts.length === 0) {
                                          return text;
                                        }
                                        
                                        return parts.map((part, partIdx) => {
                                          if (part.type === 'text') {
                                            return <span key={partIdx}>{part.content}</span>;
                                          } else {
                                            // Check if this is a community (format: "Community X")
                                            const communityMatch = part.name.match(/^Community (\d+)$/);
                                            if (communityMatch && subgraphCommunityData) {
                                              const communityId = parseInt(communityMatch[1]);
                                              const communityNodes = subgraphCommunityData[communityId] || [];
                                              
                                              if (communityNodes.length > 0) {
                                                return (
                                                  <button
                                                    key={partIdx}
                                                    onClick={(e) => {
                                                      e.stopPropagation();
                                                      const isMultiSelect = e.ctrlKey || e.metaKey;
                                                      
                                                      // Get all nodes in this community
                                                      const communityNodeObjects = communityNodes.map(node => ({
                                                        key: node.key,
                                                        id: node.id || node.key,
                                                        name: node.name,
                                                        type: node.type,
                                                      }));
                                                      
                                                      const communityNodeKeys = communityNodeObjects.map(n => n.key);
                                                      const currentlySelectedKeys = new Set(selectedNodes.map(n => n.key));
                                                      
                                                      // Check if all community nodes are already selected
                                                      const allSelected = communityNodeKeys.every(key => currentlySelectedKeys.has(key));
                                                      
                                                      if (isMultiSelect) {
                                                        // Toggle community: add if not all selected, remove if all selected
                                                        if (allSelected) {
                                                          // Remove all community nodes
                                                          setSelectedNodes(prev => {
                                                            const newSelection = prev.filter(n => !communityNodeKeys.includes(n.key));
                                                            const newKeys = newSelection.map(n => n.key);
                                                            if (newKeys.length > 0) {
                                                              loadNodeDetails(newKeys);
                                                            } else {
                                                              setSelectedNodesDetails([]);
                                                            }
                                                            return newSelection;
                                                          });
                                                        } else {
                                                          // Add all community nodes
                                                          setSelectedNodes(prev => {
                                                            const existingKeys = new Set(prev.map(n => n.key));
                                                            const newNodes = communityNodeObjects.filter(n => !existingKeys.has(n.key));
                                                            const newSelection = [...prev, ...newNodes];
                                                            const newKeys = newSelection.map(n => n.key);
                                                            loadNodeDetails(newKeys);
                                                            return newSelection;
                                                          });
                                                        }
                                                      } else {
                                                        // Single click: replace selection with all community nodes
                                                        setSelectedNodes(communityNodeObjects);
                                                        loadNodeDetails(communityNodeKeys);
                                                      }
                                                    }}
                                                    className="font-semibold text-owl-blue-900 hover:text-owl-blue-700 hover:underline cursor-pointer break-words"
                                                    title={`Click to select all ${communityNodes.length} nodes in this community (hold Ctrl/Cmd for multi-select)`}
                                                  >
                                                    {part.name}
                                                  </button>
                                                );
                                              }
                                            }
                                            
                                            // Find node in subgraph data by name
                                            const node = subgraphData.nodes.find(n => 
                                              (n.name === part.name) || (n.key === part.name)
                                            );
                                            
                                            if (node) {
                                              return (
                                                <button
                                                  key={partIdx}
                                                  onClick={(e) => {
                                                    e.stopPropagation();
                                                    const isMultiSelect = e.ctrlKey || e.metaKey;
                                                    
                                                    if (isMultiSelect) {
                                                      // Toggle node in selection
                                                      setSelectedNodes(prev => {
                                                        const isSelected = prev.some(n => n.key === node.key);
                                                        if (isSelected) {
                                                          const newSelection = prev.filter(n => n.key !== node.key);
                                                          const newKeys = newSelection.map(n => n.key);
                                                          if (newKeys.length > 0) {
                                                            loadNodeDetails(newKeys);
                                                          } else {
                                                            setSelectedNodesDetails([]);
                                                          }
                                                          return newSelection;
                                                        } else {
                                                          const newSelection = [...prev, {
                                                            key: node.key,
                                                            id: node.id || node.key,
                                                            name: node.name,
                                                            type: node.type,
                                                          }];
                                                          const newKeys = newSelection.map(n => n.key);
                                                          loadNodeDetails(newKeys);
                                                          return newSelection;
                                                        }
                                                      });
                                                    } else {
                                                      // Single select
                                                      const nodeObj = {
                                                        key: node.key,
                                                        id: node.id || node.key,
                                                        name: node.name,
                                                        type: node.type,
                                                      };
                                                      setSelectedNodes([nodeObj]);
                                                      loadNodeDetails([nodeObj.key]);
                                                    }
                                                  }}
                                                  className="font-semibold text-owl-blue-900 hover:text-owl-blue-700 hover:underline cursor-pointer break-words"
                                                  title="Click to select (hold Ctrl/Cmd for multi-select)"
                                                >
                                                  {part.name}
                                                </button>
                                              );
                                            } else {
                                              // Node not found, render as plain bold text
                                              return <strong key={partIdx} className="font-semibold text-owl-blue-900">{part.name}</strong>;
                                            }
                                          }
                                        });
                                      };
                                      
                                      return <p key={idx} className="mb-1 text-sm break-words">{renderLineWithClickableNodes(line)}</p>;
                                    }
                                  })}
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                      
                      <GraphView
                        ref={subgraphGraphRef}
                        graphData={subgraphData}
                        selectedNodes={selectedNodes}
                        onNodeClick={handleSubgraphNodeClick}
                        onBulkNodeSelect={handleBulkNodeSelect}
                        onNodeRightClick={handleNodeRightClick}
                    onNodeDoubleClick={handleNodeDoubleClick}
                        onBackgroundClick={handleSubgraphBackgroundClick}
                        width={graphWidth}
                        height={graphHeight}
                        paneViewMode={paneViewMode}
                        onPaneViewModeChange={setPaneViewMode}
                        isSubgraph={true}
                        onRemoveFromSubgraph={handleRemoveFromSubgraph}
                        subgraphNodeKeys={subgraphNodeKeys}
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
                ref={mainGraphRef}
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
                onAddNode={() => setShowAddNodeModal(true)}
              />
            )}
            </>
          ) : viewMode === 'timeline' ? (
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
          ) : (
            // Map View
            <MapView
              selectedNodes={selectedNodes}
              onNodeClick={handleNodeClick}
              onBulkNodeSelect={handleBulkNodeSelect}
              onBackgroundClick={handleBackgroundClick}
            />
          )}

        </div>

        {/* Node details sidebar - show all selected nodes */}
        {selectedNodesDetails.length > 0 && (
          <div className="w-80 bg-white border-l border-light-200 h-full flex flex-col overflow-hidden shadow-sm">
            <div className="p-4 border-b border-light-200 flex items-center justify-between flex-shrink-0">
              <h2 className="font-semibold text-owl-blue-900">
                Selected ({selectedNodesDetails.length})
              </h2>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowSnapshotModal(true)}
                  className="p-1.5 hover:bg-light-100 rounded transition-colors text-owl-blue-600 hover:text-owl-blue-700"
                  title="Create snapshot"
                >
                  <Camera className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setShowEditNodeModal(true)}
                  className="p-1.5 hover:bg-light-100 rounded transition-colors text-owl-blue-600 hover:text-owl-blue-700"
                  title="Edit node information"
                >
                  <Edit className="w-4 h-4" />
                </button>
                <button
                  onClick={handleCloseDetails}
                  className="p-1 hover:bg-light-100 rounded transition-colors"
                >
                  <X className="w-5 h-5 text-light-600" />
                </button>
              </div>
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
                    onViewDocument={handleViewDocument}
                    onNodeUpdate={(updatedNode) => {
                      // Update the node in selectedNodesDetails
                      setSelectedNodesDetails(prev => 
                        prev.map(n => n.key === updatedNode.key ? updatedNode : n)
                      );
                    }}
                    username={authUsername}
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
            onShowOnGraph={handleShowNodesOnGraph}
            initialMessages={chatHistory}
            onAutoSave={handleAutoSaveChat}
            currentCaseId={currentCaseId}
            currentCaseName={currentCaseName}
            currentCaseVersion={currentCaseVersion}
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
          onAddRelationship={handleStartRelationshipCreation}
          onCreateRelationship={handleCreateRelationship}
          onAnalyzeRelationships={handleAnalyzeRelationships}
          isRelationshipMode={isRelationshipMode}
          selectedNodes={selectedNodes}
        />
      )}

      {/* Create Relationship Modal */}
      <CreateRelationshipModal
        isOpen={showCreateRelationshipModal}
        onClose={handleCancelRelationshipCreation}
        sourceNodes={relationshipSourceNodes}
        targetNodes={selectedNodes.filter(
          target => !relationshipSourceNodes.some(source => source.key === target.key)
        )}
        onRelationshipCreated={handleRelationshipCreated}
      />

      {/* Relationship Analysis Modal */}
      <RelationshipAnalysisModal
        isOpen={showRelationshipAnalysisModal}
        onClose={() => {
          setShowRelationshipAnalysisModal(false);
          setNodeForAnalysis(null);
        }}
        node={nodeForAnalysis}
        onRelationshipsAdded={handleRelationshipsAddedFromAnalysis}
      />

      {/* Edit Node Modal */}
      <EditNodeModal
        isOpen={showEditNodeModal}
        onClose={() => setShowEditNodeModal(false)}
        nodes={selectedNodesDetails}
        onSave={handleUpdateNode}
      />

      {/* Snapshot Modal */}
      <SnapshotModal
        isOpen={showSnapshotModal}
        onClose={() => setShowSnapshotModal(false)}
        onSave={handleSaveSnapshot}
        onExportPDF={handleExportPDF}
        nodeCount={subgraphData.nodes.length}
        linkCount={subgraphData.links.length}
      />

      {/* File Management Panel */}
      <FileManagementPanel
        isOpen={showFilePanel}
        onClose={() => setShowFilePanel(false)}
        subgraphNodeKeys={subgraphNodeKeys}
        onSaveSnapshot={() => setShowSnapshotModal(true)}
        onReturnToCaseManagement={() => setAppView('caseManagement')}
        onExportPDF={async (snapshot) => {
          try {
            // Get full snapshot data if needed
            let fullSnapshot = snapshot;
            if (!fullSnapshot.subgraph) {
              fullSnapshot = await snapshotsAPI.get(snapshot.id);
            }
            // Ensure timeline is included
            if (!fullSnapshot.timeline) {
              fullSnapshot.timeline = [];
            }
            // Export to PDF (no canvas available for saved snapshots, but we'll include the data)
            await exportSnapshotToPDF(fullSnapshot, null);
            alert('PDF exported successfully!');
          } catch (err) {
            console.error('Failed to export PDF:', err);
            alert(`Failed to export PDF: ${err.message}`);
          }
        }}
        snapshots={snapshots}
        onLoadSnapshot={async (snapshot) => {
          // Show progress dialog
          setLoadSnapshotProgress({
            isOpen: true,
            current: 0,
            total: 4,
            snapshotName: snapshot.name || 'Snapshot',
            stage: 'Fetching snapshot data...',
            message: 'Loading snapshot...',
          });

          try {
            // Stage 1: Fetch snapshot data
            setLoadSnapshotProgress(prev => ({
              ...prev,
              current: 1,
              stage: 'Fetching snapshot data...',
              message: 'Loading snapshot data...',
            }));

            // Ensure we have full snapshot data (list() only returns summary)
            let fullSnapshot = snapshot;
            if (!fullSnapshot.subgraph || !fullSnapshot.subgraph.nodes) {
              fullSnapshot = await snapshotsAPI.get(snapshot.id);
            }

            if (!fullSnapshot.subgraph || !fullSnapshot.subgraph.nodes) {
              setLoadSnapshotProgress(prev => ({ ...prev, isOpen: false }));
              alert('This snapshot has no subgraph data to load.');
              return;
            }

            // Ensure split view is enabled to show the subgraph
            if (paneViewMode !== 'split') {
              setPaneViewMode('split');
            }

            // Set subgraph node keys to snapshot's subgraph nodes
            const snapshotNodes = fullSnapshot.subgraph.nodes;
            const nodeKeys = snapshotNodes.map(n => n.key);
            setSubgraphNodeKeys(nodeKeys);
            setSelectedNodes(snapshotNodes);
            setTimelineContextKeys(nodeKeys);

            // Stage 2: Load node details
            setLoadSnapshotProgress(prev => ({
              ...prev,
              current: 2,
              stage: `Loading node details (${nodeKeys.length} nodes)...`,
              message: 'Loading node details...',
            }));

            // Load node details for the selected nodes (for the overview panel)
            await loadNodeDetails(nodeKeys);

            // Stage 3: Restore chat history
            setLoadSnapshotProgress(prev => ({
              ...prev,
              current: 3,
              stage: 'Restoring chat history...',
              message: 'Restoring chat history...',
            }));

            // Restore chat history from snapshot
            // First try to load case-specific chat histories
            if (currentCaseId) {
              try {
                const allChatHistories = await chatHistoryAPI.list();
                const caseChatHistories = allChatHistories
                  .filter(chat => chat.case_id === currentCaseId)
                  .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
                
                if (caseChatHistories.length > 0) {
                  // Use the most recent case-specific chat history
                  const latestChat = caseChatHistories[0];
                  setChatHistory(latestChat.messages);
                } else if (fullSnapshot.chat_history && fullSnapshot.chat_history.length > 0) {
                  // Fall back to snapshot's chat history
                  setChatHistory(fullSnapshot.chat_history);
                }
              } catch (err) {
                console.warn('Failed to load case chat history:', err);
                // Fall back to snapshot chat history
                if (fullSnapshot.chat_history && fullSnapshot.chat_history.length > 0) {
                  setChatHistory(fullSnapshot.chat_history);
                }
              }
            } else if (fullSnapshot.chat_history && fullSnapshot.chat_history.length > 0) {
              setChatHistory(fullSnapshot.chat_history);
            } else {
              // Try to load chat history separately if not in snapshot
              try {
                const chatHistories = await chatHistoryAPI.getBySnapshot(snapshot.id);
                if (chatHistories && chatHistories.length > 0) {
                  // Use the most recent chat history
                  const latestChat = chatHistories[0];
                  setChatHistory(latestChat.messages);
                }
              } catch (err) {
                console.warn('Failed to load separate chat history:', err);
                // Continue without chat history
              }
            }

            // Stage 4: Setting up timeline
            setLoadSnapshotProgress(prev => ({
              ...prev,
              current: 4,
              stage: 'Setting up timeline...',
              message: 'Finalizing snapshot load...',
            }));

            // Timeline will be loaded automatically by the useEffect when timelineContextKeys changes
            // Small delay to ensure timeline starts loading
            await new Promise(resolve => setTimeout(resolve, 100));

            setShowFilePanel(false);

            // Close progress dialog
            setLoadSnapshotProgress(prev => ({ ...prev, isOpen: false }));
          } catch (err) {
            console.error('Failed to load snapshot:', err);
            setLoadSnapshotProgress(prev => ({ ...prev, isOpen: false }));
            alert(`Failed to load snapshot: ${err.message}`);
          }
        }}
        onDeleteSnapshot={async (snapshotId) => {
          try {
            await snapshotsAPI.delete(snapshotId);
            const data = await snapshotsAPI.list();
            setSnapshots(data);
          } catch (err) {
            console.error('Failed to delete snapshot:', err);
            throw err;
          }
        }}
        currentCaseId={currentCaseId}
        currentCaseName={currentCaseName}
        currentCaseVersion={currentCaseVersion}
        onSaveCase={() => setShowCaseModal(true)}
        onLoadCase={handleLoadCase}
      />

      {/* Background Tasks Panel */}
      <BackgroundTasksPanel
        isOpen={showBackgroundTasksPanel}
        onClose={() => setShowBackgroundTasksPanel(false)}
        authUsername={authUsername}
        onViewCase={(caseId, version) => {
          setCaseToSelect({ caseId, version });
          setShowBackgroundTasksPanel(false);
          setAppView('caseManagement');
        }}
      />

      {/* Snapshot Modal */}
      <SnapshotModal
        isOpen={showSnapshotModal}
        onClose={() => setShowSnapshotModal(false)}
        onSave={async (name, notes) => {
          await handleSaveSnapshot(name, notes);
          setShowFilePanel(true); // Reopen panel to show updated list
        }}
        onExportPDF={handleExportPDF}
        nodeCount={subgraphData.nodes.length}
        linkCount={subgraphData.links.length}
      />

      {/* Case Modal */}
      <CaseModal
        isOpen={showCaseModal}
        onClose={() => setShowCaseModal(false)}
        onSave={async (caseName, saveNotes) => {
          await handleSaveCase(caseName, saveNotes);
          setShowFilePanel(true); // Reopen panel to show updated list
        }}
        existingCaseId={currentCaseId}
        existingCaseName={currentCaseName}
        nextVersion={currentCaseVersion + 1}
      />

      <LoginPanel
        isOpen={showLoginPanel}
        onClose={() => setShowLoginPanel(false)}
        onLoginSuccess={handleLoginSuccess}
        onLogout={handleLogout}
        isAuthenticated={isAuthenticated}
        username={authUsername}
      />

      {/* Documentation Viewer */}
      <DocumentationViewer
        isOpen={showDocumentation}
        onClose={() => setShowDocumentation(false)}
      />

      {/* Load Case Progress Dialog */}
      <LoadCaseProgressDialog
        isOpen={loadCaseProgress.isOpen}
        onClose={() => {
          // Only allow closing if loading is complete
          if (loadCaseProgress.current >= loadCaseProgress.total) {
            setLoadCaseProgress(prev => ({ ...prev, isOpen: false }));
          }
        }}
        current={loadCaseProgress.current}
        total={loadCaseProgress.total}
        caseName={loadCaseProgress.caseName}
        version={loadCaseProgress.version}
      />

      <SaveSnapshotProgressDialog
        isOpen={saveSnapshotProgress.isOpen}
        progress={saveSnapshotProgress}
        onClose={null} // Don't allow closing during save
      />

      <LoadSnapshotProgressDialog
        isOpen={loadSnapshotProgress.isOpen}
        onClose={() => {
          // Only allow closing if loading is complete
          if (loadSnapshotProgress.current >= loadSnapshotProgress.total) {
            setLoadSnapshotProgress(prev => ({ ...prev, isOpen: false }));
          }
        }}
        current={loadSnapshotProgress.current}
        total={loadSnapshotProgress.total}
        snapshotName={loadSnapshotProgress.snapshotName}
        stage={loadSnapshotProgress.stage}
        message={loadSnapshotProgress.message}
      />

      <NodeSelectionProgressDialog
        isOpen={nodeSelectionProgress.isOpen}
        onClose={() => {
          // Only allow closing if loading is complete
          if (nodeSelectionProgress.current >= nodeSelectionProgress.total) {
            setNodeSelectionProgress(prev => ({ ...prev, isOpen: false }));
          }
        }}
        current={nodeSelectionProgress.current}
        total={nodeSelectionProgress.total}
        message={nodeSelectionProgress.message}
      />

      {/* Add Node Modal */}
      <AddNodeModal
        isOpen={showAddNodeModal}
        onClose={() => setShowAddNodeModal(false)}
        onNodeCreated={async (nodeKey) => {
          // Refresh the graph to show the new node
          await loadGraph();
        }}
      />

      {/* Document Viewer Modal */}
      <DocumentViewer
        isOpen={documentViewerState.isOpen}
        onClose={handleCloseDocumentViewer}
        documentUrl={documentViewerState.documentUrl}
        documentName={documentViewerState.documentName}
        initialPage={documentViewerState.page}
        highlightText={documentViewerState.highlightText}
      />
    </div>
  );
}
