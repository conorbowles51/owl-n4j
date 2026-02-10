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
  Camera,
  Database,
  Settings,
  Maximize2,
  Copy,
  ChevronLeft,
  ChevronRight,
  Merge,
  Search,
  ArrowRight,
  Minimize2,
  Square,
  MousePointer,
  Table2,
  Eye,
  DollarSign,
} from 'lucide-react';
import { graphAPI, snapshotsAPI, timelineAPI, casesAPI, authAPI, evidenceAPI, chatHistoryAPI, chatAPI, setupAPI } from './services/api';
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
import GraphTableView from './components/GraphTableView';
import FinancialView from './components/financial/FinancialView';
import SnapshotModal from './components/SnapshotModal';
import SaveSnapshotProgressDialog from './components/SaveSnapshotProgressDialog';
import CaseModal from './components/CaseModal';
import DateRangeFilter from './components/DateRangeFilter';
import FileManagementPanel from './components/FileManagementPanel';
import BackgroundTasksPanel from './components/BackgroundTasksPanel';
import CaseManagementView from './components/CaseManagementView';
import EvidenceProcessingView from './components/EvidenceProcessingView';
import WorkspaceView from './components/WorkspaceView';
import { exportSnapshotToPDF } from './utils/pdfExport';
import { parseSearchQuery, matchesQuery } from './utils/searchParser';  
import LoginPanel from './components/LoginPanel';
import SetupPanel from './components/SetupPanel';
import DocumentationViewer from './components/DocumentationViewer';
import DocumentViewer from './components/DocumentViewer';
import LoadCaseProgressDialog from './components/LoadCaseProgressDialog';
import LoadSnapshotProgressDialog from './components/LoadSnapshotProgressDialog';
import NodeSelectionProgressDialog from './components/NodeSelectionProgressDialog';
import AddNodeModal from './components/AddNodeModal';
import CreateRelationshipModal from './components/CreateRelationshipModal';
import SystemLogsPanel from './components/SystemLogsPanel';
import DatabaseModal from './components/DatabaseModal';
import RelationshipAnalysisModal from './components/RelationshipAnalysisModal';
import EditNodeModal from './components/EditNodeModal';
import ExpandGraphModal from './components/ExpandGraphModal';
import MergeEntitiesModal from './components/MergeEntitiesModal';
import CollaboratorModal from './components/CollaboratorModal';
import SimilarEntitiesProgressDialog from './components/SimilarEntitiesProgressDialog';
import EntityComparisonModal from './components/EntityComparisonModal';
import EntityTypeSelectorModal from './components/EntityTypeSelectorModal';
import { CasePermissionProvider, useCasePermissions } from './contexts/CasePermissionContext';

/**
 * Wrapper component that conditionally renders ContextMenu based on edit permissions.
 * Must be used inside CasePermissionProvider.
 */
function PermissionAwareContextMenu({ contextMenu, ...props }) {
  const { canEdit } = useCasePermissions();

  if (!contextMenu || !canEdit) {
    return null;
  }

  return <ContextMenu node={contextMenu.node} position={contextMenu.position} {...props} />;
}

/**
 * Main App Component
 */
export default function App() {
  // Main app view state - 'caseManagement', 'graph', 'evidence', or 'workspace'
  const [appView, setAppView] = useState('caseManagement'); // Start with case management after login
  // View mode state (for graph view)
  const [viewMode, setViewMode] = useState('graph'); // 'graph' or 'timeline'
  
  // Table view state persistence
  const [tableViewState, setTableViewState] = useState({
    panels: null,
    selectedPanels: new Set(),
    columnFilters: new Map(),
  });
  // Graph state
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [fullGraphData, setFullGraphData] = useState({ nodes: [], links: [] }); // Store unfiltered graph
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dateRange, setDateRange] = useState({ start_date: null, end_date: null });
  const [graphSearchTerm, setGraphSearchTerm] = useState('');
  const [graphSearchFieldScope, setGraphSearchFieldScope] = useState('all'); // 'all' | 'selected'
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
  
  // Spotlight Graph history (breadcrumb navigation)
  const [queryFocusHistory, setQueryFocusHistory] = useState([{
    subgraphNodeKeys: [],
    selectedNodes: [],
    timestamp: Date.now()
  }]);
  const [queryFocusHistoryIndex, setQueryFocusHistoryIndex] = useState(0);
  const [isNavigatingHistory, setIsNavigatingHistory] = useState(false); // Flag to prevent history entry during navigation
  
  // Add history entry when Spotlight Graph changes
  const addQueryFocusHistoryEntry = useCallback((newNodeKeys, newSelectedNodes) => {
    if (isNavigatingHistory) return; // Don't add history during navigation
    
    const newEntry = {
      subgraphNodeKeys: [...newNodeKeys],
      selectedNodes: newSelectedNodes.map(n => ({ // Store minimal node info
        key: n.key,
        id: n.id || n.key,
        name: n.name,
        type: n.type,
      })),
      timestamp: Date.now()
    };
    
    // Check if this is the same as current entry (avoid duplicates)
    const currentEntry = queryFocusHistory[queryFocusHistoryIndex];
    if (currentEntry) {
      const currentKeysStr = JSON.stringify(currentEntry.subgraphNodeKeys.sort());
      const newKeysStr = JSON.stringify(newNodeKeys.sort());
      if (currentKeysStr === newKeysStr) {
        // Same state, don't add history
        return;
      }
    }
    
    // Remove any history entries after current index (when user navigated back and then made changes)
    const newHistory = queryFocusHistory.slice(0, queryFocusHistoryIndex + 1);
    newHistory.push(newEntry);
    
    // Limit history to 50 entries to prevent memory issues
    if (newHistory.length > 50) {
      newHistory.shift(); // Remove oldest entry
      setQueryFocusHistoryIndex(queryFocusHistoryIndex); // Keep same relative position
    } else {
      setQueryFocusHistoryIndex(newHistory.length - 1);
    }
    
    setQueryFocusHistory(newHistory);
  }, [isNavigatingHistory, queryFocusHistory, queryFocusHistoryIndex]);
  
  // Ref to track previous subgraphNodeKeys for history tracking
  const prevSubgraphNodeKeysRef = useRef([]);
  
  // Track Spotlight Graph changes and add to history
  // Only track subgraphNodeKeys changes (not selectedNodes) to avoid too many entries
  useEffect(() => {
    if (isNavigatingHistory) {
      // Update ref even during navigation so we don't miss the new state
      prevSubgraphNodeKeysRef.current = subgraphNodeKeys;
      return; // Don't add history during navigation
    }
    
    // Check if subgraphNodeKeys actually changed
    const prevKeysStr = JSON.stringify(prevSubgraphNodeKeysRef.current.sort());
    const currentKeysStr = JSON.stringify(subgraphNodeKeys.sort());
    
    if (prevKeysStr === currentKeysStr) {
      // No change, don't add history
      return;
    }
    
    // Update ref
    prevSubgraphNodeKeysRef.current = [...subgraphNodeKeys];
    
    // Add history entry (only if Spotlight Graph actually changed)
    addQueryFocusHistoryEntry(subgraphNodeKeys, selectedNodes);
  }, [subgraphNodeKeys, selectedNodes, isNavigatingHistory, addQueryFocusHistoryEntry]);
  
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
  const [showCollaboratorModal, setShowCollaboratorModal] = useState(false);
  const [collaboratorModalCase, setCollaboratorModalCase] = useState(null);

  // File management panel state
  const [showFilePanel, setShowFilePanel] = useState(false);
  // Background tasks panel state
  const [showBackgroundTasksPanel, setShowBackgroundTasksPanel] = useState(false);
  // Settings dropdown state
  const [isSettingsDropdownOpen, setIsSettingsDropdownOpen] = useState(false);
  const settingsDropdownRef = useRef(null);
  const settingsButtonRef = useRef(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [authUsername, setAuthUsername] = useState('');  // email
  const [authDisplayName, setAuthDisplayName] = useState('');  // user's name
  const [authUserRole, setAuthUserRole] = useState(null);  // user role (e.g., 'super_admin', 'user')
  const [showLoginPanel, setShowLoginPanel] = useState(false);
  const [needsSetup, setNeedsSetup] = useState(null);
  const [setupCheckComplete, setSetupCheckComplete] = useState(false);
  const [isAccountDropdownOpen, setIsAccountDropdownOpen] = useState(false);
  const [showDocumentation, setShowDocumentation] = useState(false);
  const [showAddNodeModal, setShowAddNodeModal] = useState(false);
  const [showSystemLogs, setShowSystemLogs] = useState(false);
  const [showDatabaseModal, setShowDatabaseModal] = useState(false);
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
  
  // Expand graph modal state
  const [showExpandGraphModal, setShowExpandGraphModal] = useState(false);
  const [expandGraphContext, setExpandGraphContext] = useState(null); // 'subgraph', 'result', 'selected', 'all'
  
  // Merge entities modal state
  const [showMergeModal, setShowMergeModal] = useState(false);
  const [mergeEntity1, setMergeEntity1] = useState(null);
  const [mergeEntity2, setMergeEntity2] = useState(null);
  const [mergeSimilarity, setMergeSimilarity] = useState(null);
  const [mergeModalOrigin, setMergeModalOrigin] = useState(null); // 'similar_entities' | 'comparison' | 'graph_selection'
  
  // Similar entities scan state
  const [similarEntitiesPairs, setSimilarEntitiesPairs] = useState([]);
  const [showSimilarEntitiesList, setShowSimilarEntitiesList] = useState(false);
  const [isScanningSimilar, setIsScanningSimilar] = useState(false);
  const [similarScanProgress, setSimilarScanProgress] = useState(null);
  const similarScanAbortRef = useRef(null);

  // Entity type selector modal state (for similar entities scan)
  const [showEntityTypeSelector, setShowEntityTypeSelector] = useState(false);
  const [scanEntityTypes, setScanEntityTypes] = useState([]);
  const [isLoadingEntityTypes, setIsLoadingEntityTypes] = useState(false);

  // Entity comparison modal state
  const [showComparisonModal, setShowComparisonModal] = useState(false);
  const [comparisonPair, setComparisonPair] = useState(null);

  // Close and clear spotlight confirmation popup state
  const [showClearSpotlightConfirm, setShowClearSpotlightConfirm] = useState(false);
  const clearSpotlightButtonRef = useRef(null);
  const clearSpotlightPopupRef = useRef(null);
  
  // Close confirmation popup when clicking outside
  useEffect(() => {
    if (!showClearSpotlightConfirm) return;
    
    const handleClickOutside = (e) => {
      if (
        clearSpotlightButtonRef.current &&
        clearSpotlightPopupRef.current &&
        !clearSpotlightButtonRef.current.contains(e.target) &&
        !clearSpotlightPopupRef.current.contains(e.target)
      ) {
        setShowClearSpotlightConfirm(false);
      }
    };
    
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showClearSpotlightConfirm]);

  // Keyboard shortcut for Save Snapshot (Cmd+S / Ctrl+S)
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Check for Cmd+S (Mac) or Ctrl+S (Windows/Linux)
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault(); // Prevent browser's default save dialog
        setShowSnapshotModal(true);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);
  
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
    async function initializeApp() {
      try {
        // First check if setup is needed
        const setupStatus = await setupAPI.getStatus();
        if (setupStatus.needs_setup) {
          setNeedsSetup(true);
          setSetupCheckComplete(true);
          return;
        }
        setNeedsSetup(false);

        // Setup not needed, check if user is authenticated
        try {
          const current = await authAPI.me();
          setIsAuthenticated(true);
          setAuthUsername(current.email);
          setAuthDisplayName(current.name);
          setAuthUserRole(current.role || null);
        } catch {
          setIsAuthenticated(false);
          setAuthUsername('');
          setAuthDisplayName('');
          setAuthUserRole(null);
          localStorage.removeItem('authToken');
        }
      } catch (err) {
        // If setup check fails, assume setup is not needed and proceed with auth check
        console.error('Setup status check failed:', err);
        setNeedsSetup(false);
        try {
          const current = await authAPI.me();
          setIsAuthenticated(true);
          setAuthUsername(current.email);
          setAuthDisplayName(current.name);
          setAuthUserRole(current.role || null);
        } catch {
          setIsAuthenticated(false);
          setAuthUsername('');
          setAuthDisplayName('');
          setAuthUserRole(null);
          localStorage.removeItem('authToken');
        }
      } finally {
        setSetupCheckComplete(true);
      }
    }

    initializeApp();
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
      if (
        isSettingsDropdownOpen &&
        settingsDropdownRef.current &&
        settingsButtonRef.current &&
        !settingsDropdownRef.current.contains(event.target) &&
        !settingsButtonRef.current.contains(event.target)
      ) {
        setIsSettingsDropdownOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isAccountDropdownOpen, isSettingsDropdownOpen]);

  const handleLoginSuccess = useCallback((token, email, name, role = null) => {
    localStorage.setItem('authToken', token);
    setIsAuthenticated(true);
    setAuthUsername(email);
    setAuthDisplayName(name);
    setAuthUserRole(role);
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
    setAuthDisplayName('');
    setAuthUserRole(null);
    setIsAccountDropdownOpen(false);
  }, []);


  // Pane view state (single, split, full, or minimized)
  const [paneViewMode, setPaneViewMode] = useState('single'); // 'single', 'split', 'full', or 'minimized'
  
  // Subgraph menu state
  const [isSubgraphMenuOpen, setIsSubgraphMenuOpen] = useState(false);
  const subgraphMenuRef = useRef(null);
  
  // Path-based subgraph state (for shortest paths feature)
  const [pathSubgraphData, setPathSubgraphData] = useState(null);
  
  // Result graph state (from AI assistant responses)
  const [resultGraphData, setResultGraphData] = useState(null);
  const [activeSubgraphTab, setActiveSubgraphTab] = useState('subgraph'); // 'subgraph' or 'result'
  
  // Track previous result graph to detect when a new one arrives
  const prevResultGraphRef = useRef(null);
  
  // Update result graph when chat messages change
  useEffect(() => {
    // Find the most recent assistant message with a result graph
    const lastMessageWithResultGraph = [...chatHistory]
      .reverse()
      .find(msg => msg.role === 'assistant' && msg.resultGraph && msg.resultGraph.nodes && msg.resultGraph.nodes.length > 0);
    
    if (lastMessageWithResultGraph && lastMessageWithResultGraph.resultGraph) {
      const newResultGraph = lastMessageWithResultGraph.resultGraph;
      
      // Check if this is a new result graph (different from previous)
      const isNewResultGraph = !prevResultGraphRef.current || 
        prevResultGraphRef.current.nodes.length !== newResultGraph.nodes.length ||
        prevResultGraphRef.current.nodes.some((n, i) => n.key !== newResultGraph.nodes[i]?.key);
      
      if (isNewResultGraph) {
        setResultGraphData(newResultGraph);
        prevResultGraphRef.current = newResultGraph;
        
        // Switch to result graph tab only when a new result graph arrives
        // This happens when AI assistant returns an answer with a result graph
        setActiveSubgraphTab(prev => {
          // Only switch if we're on subgraph tab (user hasn't manually switched)
          return prev === 'subgraph' ? 'result' : prev;
        });
      }
    } else if (chatHistory.length === 0) {
      // Clear result graph if chat is cleared
      setResultGraphData(null);
      prevResultGraphRef.current = null;
    }
  }, [chatHistory]);
  
  // Track previous chat open state to detect when chat is first opened
  const prevChatOpenRef = useRef(false);
  
  // Auto-open Spotlight Graph when AI assistant opens
  useEffect(() => {
    const chatJustOpened = isChatOpen && !prevChatOpenRef.current;
    prevChatOpenRef.current = isChatOpen;
    
    if (isChatOpen) {
      // If no nodes are selected and Spotlight Graph is empty, populate with all nodes
      if (selectedNodes.length === 0 && subgraphNodeKeys.length === 0 && graphData.nodes.length > 0) {
        const allNodeKeys = graphData.nodes.map(node => node.key).filter(key => key);
        setSubgraphNodeKeys(allNodeKeys);
        setTimelineContextKeys(allNodeKeys);
        console.log(`Auto-populated Spotlight Graph with ${allNodeKeys.length} nodes from graph`);
      }
      
      // Don't force split view - let user control the pane view mode
      // Only enable split view if no pane is currently visible (single mode)
      if (paneViewMode === 'single' && subgraphNodeKeys.length > 0) {
        setPaneViewMode('split');
      }
    }
  }, [isChatOpen, selectedNodes.length, subgraphNodeKeys.length, graphData.nodes, paneViewMode]);

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

    const queryAST = parseSearchQuery(searchTerm);
    const searchOpts = { allFields: graphSearchFieldScope === 'all' };
    const matchingNodes = data.nodes.filter(node => matchesQuery(queryAST, node, searchOpts));

    const matchingNodeKeys = new Set(matchingNodes.map(n => n.key));

    // Filter links to only include connections between matching nodes
    const matchingLinks = data.links.filter(link => {
      const sourceKey = typeof link.source === 'string' ? link.source : link.source.key;
      const targetKey = typeof link.target === 'string' ? link.target : link.target.key;
      return matchingNodeKeys.has(sourceKey) && matchingNodeKeys.has(targetKey);
    });

    setGraphData({ nodes: matchingNodes, links: matchingLinks });
  }, [graphSearchFieldScope]);

  // Load graph data
  const loadGraph = useCallback(async (caseIdOverride = null) => {
    setIsLoading(true);
    setError(null);
    try {
      // Use caseIdOverride if provided, otherwise use currentCaseId
      const caseId = caseIdOverride !== null ? caseIdOverride : currentCaseId;
      const data = await graphAPI.getGraph({
        case_id: caseId,
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
  }, [currentCaseId, dateRange, graphSearchTerm, applyGraphFilter]);

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
  const handleGraphFilterChange = useCallback((searchTerm, fieldScope) => {
    setGraphSearchTerm(searchTerm ?? '');
    if (fieldScope !== undefined) setGraphSearchFieldScope(fieldScope);
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
          const batchPromises = batch.map(key => graphAPI.getNodeDetails(key, currentCaseId));
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
  }, [currentCaseId]);

  // Handle opening chat from table view with selected nodes
  const handleTableChatOpen = useCallback(async (nodes) => {
    if (!nodes || nodes.length === 0) return;
    
    // Extract node keys
    const nodeKeys = nodes.map(n => n.key).filter(Boolean);
    if (nodeKeys.length === 0) return;
    
    // Set node details immediately with available info from table nodes
    // This ensures chat opens right away with basic node information
    const nodeDetails = nodes.map(node => ({
      key: node.key,
      name: node.name || node.key,
      type: node.type || '',
      summary: node.summary || '',
      notes: node.notes || '',
      properties: node.properties || {},
    }));
    setSelectedNodesDetails(nodeDetails);
    
    // Open chat panel
    setIsChatOpen(true);
    
    // Load full node details in background (will update selectedNodesDetails when complete)
    loadNodeDetails(nodeKeys);
  }, [loadNodeDetails]);

  // Navigate back in Spotlight Graph history
  const navigateQueryFocusHistoryBack = useCallback(() => {
    if (queryFocusHistoryIndex > 0) {
      setIsNavigatingHistory(true);
      const prevEntry = queryFocusHistory[queryFocusHistoryIndex - 1];
      const prevNodeKeys = prevEntry.subgraphNodeKeys || [];
      const prevSelectedNodes = prevEntry.selectedNodes || [];
      
      setSubgraphNodeKeys(prevNodeKeys);
      setSelectedNodes(prevSelectedNodes);
      setTimelineContextKeys(prevNodeKeys);
      setPathSubgraphData(null); // Clear path subgraph data
      
      // Load node details for restored nodes
      if (prevNodeKeys.length > 0) {
        loadNodeDetails(prevNodeKeys);
      } else {
        setSelectedNodesDetails([]);
      }
      
      // Update ref to prevent duplicate history entry
      prevSubgraphNodeKeysRef.current = [...prevNodeKeys];
      
      setQueryFocusHistoryIndex(queryFocusHistoryIndex - 1);
      setTimeout(() => setIsNavigatingHistory(false), 100); // Reset flag after state updates
    }
  }, [queryFocusHistory, queryFocusHistoryIndex, loadNodeDetails]);
  
  // Navigate forward in Spotlight Graph history
  const navigateQueryFocusHistoryForward = useCallback(() => {
    if (queryFocusHistoryIndex < queryFocusHistory.length - 1) {
      setIsNavigatingHistory(true);
      const nextEntry = queryFocusHistory[queryFocusHistoryIndex + 1];
      const nextNodeKeys = nextEntry.subgraphNodeKeys || [];
      const nextSelectedNodes = nextEntry.selectedNodes || [];
      
      setSubgraphNodeKeys(nextNodeKeys);
      setSelectedNodes(nextSelectedNodes);
      setTimelineContextKeys(nextNodeKeys);
      setPathSubgraphData(null); // Clear path subgraph data
      
      // Load node details for restored nodes
      if (nextNodeKeys.length > 0) {
        loadNodeDetails(nextNodeKeys);
      } else {
        setSelectedNodesDetails([]);
      }
      
      // Update ref to prevent duplicate history entry
      prevSubgraphNodeKeysRef.current = [...nextNodeKeys];
      
      setQueryFocusHistoryIndex(queryFocusHistoryIndex + 1);
      setTimeout(() => setIsNavigatingHistory(false), 100); // Reset flag after state updates
    }
  }, [queryFocusHistory, queryFocusHistoryIndex, loadNodeDetails]);

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
  // Table view passes (node, panel, event); graph/timeline/map pass (node, event)
  const handleNodeClick = useCallback((node, eventOrPanel, eventMaybe) => {
    const event = eventMaybe ?? eventOrPanel;
    const panel = eventMaybe !== undefined ? eventOrPanel : null;
    const isMultiSelect = event?.ctrlKey || event?.metaKey || event?.originalCtrlKey || event?.originalMetaKey;

    // Table row in relations panel: include breadcrumb trail + clicked node
    const isRelationsPanel = panel?.type === 'relations' && panel?.breadcrumb?.length > 0;
    if (isRelationsPanel && !isMultiSelect) {
      const nodes = graphData.nodes;
      const breadcrumbNodes = panel.breadcrumb
        .map((c) => nodes.find((n) => n.key === c.key))
        .filter(Boolean);
      // Order: clicked node first (most recent), then breadcrumb in reverse (most recent breadcrumb first)
      const nodesToShow = [
        ...(breadcrumbNodes.some((n) => n.key === node.key) ? [] : [node]),
        ...breadcrumbNodes.reverse(),
      ];
      const keysToLoad = nodesToShow.map((n) => n.key);
      setSelectedNodes(nodesToShow);
      loadNodeDetails(keysToLoad);
      setTimelineContextKeys(keysToLoad);
      setContextMenu(null);
      return;
    }

    if (isMultiSelect) {
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
          setTimelineContextKeys(newKeys);
          return newSelection;
        } else {
          const newSelection = [...prev, node];
          const newKeys = newSelection.map(n => n.key);
          loadNodeDetails(newKeys);
          setTimelineContextKeys(newKeys);
          return newSelection;
        }
      });
    } else {
      setSelectedNodes([node]);
      loadNodeDetails([node.key]);
      setTimelineContextKeys([node.key]);
    }
    setContextMenu(null);
  }, [loadNodeDetails, graphData.nodes]);

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

  // Handle node deletion
  const handleDeleteNode = useCallback(async (node) => {
    if (!node || !node.key) {
      return;
    }

    // Confirm deletion
    const nodeName = node.name || node.key;
    const confirmMessage = `Are you sure you want to delete "${nodeName}"?\n\nThis will permanently delete the node and all its relationships. This action cannot be undone.`;
    
    if (!window.confirm(confirmMessage)) {
      return;
    }

    try {
      await graphAPI.deleteNode(node.key, currentCaseId);

      // Remove from selected nodes if selected
      setSelectedNodes(prev => prev.filter(n => n.key !== node.key));
      
      // Remove from subgraph if present
      setSubgraphNodeKeys(prev => prev.filter(key => key !== node.key));
      
      // Remove from timeline context if present
      setTimelineContextKeys(prev => prev.filter(key => key !== node.key));
      
      // Reload graph to reflect deletion
      await loadGraph();
      
      // Close context menu
      setContextMenu(null);
      
      alert(`Node "${nodeName}" deleted successfully.`);
    } catch (err) {
      console.error('Failed to delete node:', err);
      alert(`Failed to delete node: ${err.message}`);
    }
  }, [loadGraph]);

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

  // Handle merge entities (from manual selection or similar entities scan)
  const handleMergeEntities = useCallback(async (sourceKey, targetKey, mergedData) => {
    try {
      setIsLoading(true);
      const result = await graphAPI.mergeEntities(currentCaseId, sourceKey, targetKey, mergedData);

      // Refresh graph to show merged entity
      await loadGraph();
      
      // Clear selection if merged entities were selected
      setSelectedNodes(prev => prev.filter(n => n.key !== sourceKey && n.key !== targetKey));
      
      // Add merged node to selection
      if (result.merged_node) {
        setSelectedNodes([{
          key: result.merged_node.key,
          id: result.merged_node.id,
          name: result.merged_node.name,
          type: result.merged_node.type,
        }]);
        await loadNodeDetails([result.merged_node.key]);
      }
      
      alert(`Successfully merged entities. ${result.relationships_updated || 0} relationships migrated.`);
    } catch (err) {
      console.error('Failed to merge entities:', err);
      alert(`Failed to merge entities: ${err.message}`);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [loadGraph, loadNodeDetails]);

  // Handle merge selected nodes
  const handleMergeSelected = useCallback(() => {
    if (selectedNodes.length < 2) {
      alert('Please select at least 2 nodes to merge');
      return;
    }

    // Use first node as source, second as target (user can change in modal)
    // Try to use full details from selectedNodesDetails, fall back to selectedNodes
    const entity1 = selectedNodesDetails.find(n => n.key === selectedNodes[0].key) || selectedNodes[0];
    const entity2 = selectedNodesDetails.find(n => n.key === selectedNodes[1].key) || selectedNodes[1];

    setMergeEntity1(entity1);
    setMergeEntity2(entity2);
    setMergeSimilarity(null);
    setMergeModalOrigin('graph_selection');
    setShowMergeModal(true);
  }, [selectedNodes, selectedNodesDetails]);

  // Handle find similar entities - opens type selector modal first
  const handleFindSimilarEntities = useCallback(async () => {
    if (!currentCaseId) {
      alert('Please select a case first');
      return;
    }

    // Fetch entity types and show selector modal
    setIsLoadingEntityTypes(true);
    setShowEntityTypeSelector(true);

    try {
      const response = await graphAPI.getEntityTypes(currentCaseId);
      setScanEntityTypes(response.entity_types || []);
    } catch (err) {
      console.error('Failed to fetch entity types:', err);
      setScanEntityTypes([]);
    } finally {
      setIsLoadingEntityTypes(false);
    }
  }, [currentCaseId]);

  // Start the actual similar entities scan with selected types
  const startSimilarEntitiesScan = useCallback((selectedTypes) => {
    if (!currentCaseId) return;

    // Reset state
    setIsScanningSimilar(true);
    setSimilarEntitiesPairs([]);
    setSimilarScanProgress({
      totalEntities: 0,
      totalTypes: 0,
      entityTypes: [],
      currentType: null,
      typeIndex: 0,
      comparisonsTotal: 0,
      comparisonsDone: 0,
      pairsFound: 0,
      isComplete: false,
      error: null,
    });

    // Start the streaming request with selected types
    const cancelFn = graphAPI.findSimilarEntitiesStream(
      currentCaseId,
      { entityTypes: selectedTypes, similarityThreshold: 0.7, maxResults: 1000 },
      {
        onStart: (data) => {
          setSimilarScanProgress(prev => ({
            ...prev,
            totalEntities: data.total_entities,
            totalTypes: data.total_types,
            entityTypes: data.entity_types,
            comparisonsTotal: data.total_comparisons,
          }));
        },
        onTypeStart: (data) => {
          setSimilarScanProgress(prev => ({
            ...prev,
            currentType: data.type_name,
            typeIndex: data.type_index,
          }));
        },
        onProgress: (data) => {
          setSimilarScanProgress(prev => ({
            ...prev,
            comparisonsDone: data.comparisons_done,
            pairsFound: data.pairs_found,
            currentType: data.current_type,
            typeIndex: data.type_index,
          }));
        },
        onTypeComplete: (data) => {
          setSimilarScanProgress(prev => ({
            ...prev,
            typeIndex: data.type_index,  // Display already adds 1, don't double-increment
          }));
        },
        onComplete: (data) => {
          // All results come in the complete event (no more per-result events)
          const finalPairs = data.limited_results || [];
          setSimilarEntitiesPairs(finalPairs);
          setSimilarScanProgress(prev => ({
            ...prev,
            comparisonsDone: data.total_comparisons,
            pairsFound: data.total_pairs,
            isComplete: true,
          }));
          setIsScanningSimilar(false);
          similarScanAbortRef.current = null;
          // Show results after a brief delay
          setTimeout(() => {
            setSimilarScanProgress(null);
            setShowSimilarEntitiesList(true);
          }, 500);
        },
        onError: (err) => {
          console.error('Failed to find similar entities:', err);
          setSimilarScanProgress(prev => ({
            ...prev,
            error: err.message || 'Unknown error occurred',
          }));
          setTimeout(() => {
            setSimilarScanProgress(null);
          }, 3000);
          setIsScanningSimilar(false);
          similarScanAbortRef.current = null;
        },
        onCancelled: (data) => {
          // Check if partial results were returned on cancellation
          const partialPairs = data?.partial_results || [];
          if (partialPairs.length > 0) {
            setSimilarEntitiesPairs(partialPairs);
            setShowSimilarEntitiesList(true);
          }
          setSimilarScanProgress(null);
          setIsScanningSimilar(false);
          similarScanAbortRef.current = null;
        },
      }
    );

    // Store cancel function
    similarScanAbortRef.current = cancelFn;
  }, [currentCaseId]);

  // Handle cancel similar entities scan
  const handleCancelSimilarScan = useCallback(() => {
    if (similarScanAbortRef.current) {
      similarScanAbortRef.current();
    }
  }, []);

  // Handle open merge modal for a similar pair
  const handleMergeSimilarPair = useCallback((pair) => {
    setMergeEntity1(pair.entity1);
    setMergeEntity2(pair.entity2);
    setMergeSimilarity(pair.similarity);
    setMergeModalOrigin('similar_entities');
    setShowMergeModal(true);
    setShowSimilarEntitiesList(false);
  }, []);

  // Handle rejecting a pair as false positive
  const handleRejectPair = useCallback(async (pair) => {
    if (!currentCaseId) return;

    try {
      await graphAPI.rejectMergePair(
        currentCaseId,
        pair.entity1.key,
        pair.entity2.key
      );

      // Remove the pair from the list
      setSimilarEntitiesPairs(prev =>
        prev.filter(p =>
          !(p.entity1.key === pair.entity1.key && p.entity2.key === pair.entity2.key)
        )
      );

      // Show feedback (using alert for simplicity - can be replaced with toast)
      console.log('Pair rejected - will not appear in future scans');
    } catch (err) {
      console.error('Failed to reject pair:', err);
      alert('Failed to reject pair: ' + (err.message || 'Unknown error'));
    }
  }, [currentCaseId]);

  // Handle viewing a similar pair in the comparison modal
  const handleViewSimilarPair = useCallback((pair) => {
    setComparisonPair(pair);
    setShowComparisonModal(true);
  }, []);

  // Handle closing the comparison modal
  const handleCloseComparisonModal = useCallback(() => {
    setShowComparisonModal(false);
    setComparisonPair(null);
  }, []);

  // Handle merge action from comparison modal
  const handleMergeFromComparison = useCallback((pair) => {
    setShowComparisonModal(false);
    setComparisonPair(null);
    setMergeEntity1(pair.entity1);
    setMergeEntity2(pair.entity2);
    setMergeSimilarity(pair.similarity);
    setMergeModalOrigin('comparison');
    setShowMergeModal(true);
    setShowSimilarEntitiesList(false);
  }, []);

  // Handle reject action from comparison modal
  const handleRejectFromComparison = useCallback(async (pair) => {
    await handleRejectPair(pair);
    setShowComparisonModal(false);
    setComparisonPair(null);
  }, [handleRejectPair]);

  // Handle merge modal cancel - return to appropriate view
  const handleMergeModalCancel = useCallback(() => {
    setShowMergeModal(false);

    // Return to similar entities list if came from there
    if (mergeModalOrigin === 'similar_entities' || mergeModalOrigin === 'comparison') {
      setShowSimilarEntitiesList(true);
    }

    setMergeEntity1(null);
    setMergeEntity2(null);
    setMergeSimilarity(null);
    setMergeModalOrigin(null);
  }, [mergeModalOrigin]);

  // Handle merge modal success - return to appropriate view and remove merged pair
  const handleMergeModalSuccess = useCallback((mergedPair) => {
    setShowMergeModal(false);

    // Remove merged pair from results
    if (mergedPair) {
      setSimilarEntitiesPairs(prev =>
        prev.filter(p =>
          !(p.entity1.key === mergedPair.entity1.key && p.entity2.key === mergedPair.entity2.key)
        )
      );
    }

    // Return to similar entities list if came from there
    if (mergeModalOrigin === 'similar_entities' || mergeModalOrigin === 'comparison') {
      setShowSimilarEntitiesList(true);
    }

    setMergeEntity1(null);
    setMergeEntity2(null);
    setMergeSimilarity(null);
    setMergeModalOrigin(null);
  }, [mergeModalOrigin]);

  // Handle updating node information
  const handleUpdateNode = useCallback(async (nodeKey, updates) => {
    try {
      // updateNode API will throw if there's an error, so we don't need to check result.success
      await graphAPI.updateNode(nodeKey, updates);
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

  // Handle expand from context menu (main graph only - old behavior)
  const handleExpand = useCallback(async (node) => {
    try {
      const expandedData = await graphAPI.getNodeNeighbours(node.key, 1, currentCaseId);

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

  // Handle graph expansion (for subgraph and result graph)
  const handleExpandGraph = useCallback((context, nodeKeys = null) => {
    // context: 'subgraph', 'result', 'selected', 'all'
    setExpandGraphContext(context);
    setShowExpandGraphModal(true);
  }, []);

  // Execute graph expansion
  const executeGraphExpansion = useCallback(async (depth) => {
    if (!expandGraphContext) return;

    try {
      setIsLoading(true);
      let nodeKeysToExpand = [];

      if (expandGraphContext === 'selected') {
        // Expand selected nodes
        nodeKeysToExpand = selectedNodes.map(n => n.key);
        if (nodeKeysToExpand.length === 0) {
          alert('Please select nodes to expand');
          setIsLoading(false);
          return;
        }
      } else if (expandGraphContext === 'subgraph') {
        // Expand all nodes in spotlight graph
        nodeKeysToExpand = subgraphNodeKeys;
        if (nodeKeysToExpand.length === 0) {
          alert('Spotlight Graph is empty. Please add nodes first.');
          setIsLoading(false);
          return;
        }
      } else if (expandGraphContext === 'result') {
        // Expand all nodes in result graph
        if (!resultGraphData || !resultGraphData.nodes || resultGraphData.nodes.length === 0) {
          alert('Result Graph is empty.');
          setIsLoading(false);
          return;
        }
        nodeKeysToExpand = resultGraphData.nodes.map(n => n.key).filter(key => key);
      } else {
        // 'all' - expand all nodes in current subgraph (shouldn't happen, but handle it)
        nodeKeysToExpand = subgraphNodeKeys;
      }

      if (nodeKeysToExpand.length === 0) {
        setIsLoading(false);
        return;
      }

      // Call expansion API
      const expandedData = await graphAPI.expandNodes(currentCaseId, nodeKeysToExpand, depth);

      // Merge expanded nodes into main graph data so they're available for subgraph
      // This ensures expanded nodes show up in the Spotlight Graph without reloading the entire graph
      setFullGraphData(prev => {
        const existingNodeKeys = new Set(prev.nodes.map(n => n.key));
        const existingLinkKeys = new Set(
          prev.links.map(l => {
            const sourceKey = typeof l.source === 'object' ? l.source.key : l.source;
            const targetKey = typeof l.target === 'object' ? l.target.key : l.target;
            return `${sourceKey}-${targetKey}-${l.type}`;
          })
        );
        
        const newNodes = expandedData.nodes.filter(n => n.key && !existingNodeKeys.has(n.key));
        const newLinks = expandedData.links.filter(l => {
          const sourceKey = typeof l.source === 'object' ? l.source.key : l.source;
          const targetKey = typeof l.target === 'object' ? l.target.key : l.target;
          const linkKey = `${sourceKey}-${targetKey}-${l.type}`;
          return !existingLinkKeys.has(linkKey);
        });
        
        return {
          nodes: [...prev.nodes, ...newNodes],
          links: [...prev.links, ...newLinks],
        };
      });

      if (expandGraphContext === 'subgraph') {
        // For spotlight graph: add expanded nodes to subgraphNodeKeys
        // Stay on Spotlight Graph tab (don't switch)
        const existingKeys = new Set(subgraphNodeKeys);
        const newKeys = expandedData.nodes
          .map(n => n.key)
          .filter(key => key && !existingKeys.has(key));
        
        if (newKeys.length > 0) {
          setSubgraphNodeKeys(prev => [...prev, ...newKeys]);
        }
        // Ensure we're on the Spotlight Graph tab
        setActiveSubgraphTab('subgraph');
      } else if (expandGraphContext === 'result') {
        // For result graph: push result graph to Spotlight Graph, then expand there
        // First, copy all result graph nodes to Spotlight Graph
        const resultNodeKeys = resultGraphData.nodes.map(n => n.key).filter(key => key);
        setSubgraphNodeKeys(resultNodeKeys);
        setPathSubgraphData(null); // Clear path subgraph data
        
        // Now expand those nodes (which are now in Spotlight Graph)
        const existingKeys = new Set(resultNodeKeys);
        const newKeys = expandedData.nodes
          .map(n => n.key)
          .filter(key => key && !existingKeys.has(key));
        
        if (newKeys.length > 0) {
          setSubgraphNodeKeys(prev => [...prev, ...newKeys]);
        }
        
        // Switch to Spotlight Graph tab to show the expansion
        setActiveSubgraphTab('subgraph');
      } else if (expandGraphContext === 'selected') {
        // For selected nodes: add to spotlight graph (subgraph)
        // Only operate on the Spotlight Graph, not the main graph
        const existingKeys = new Set(subgraphNodeKeys);
        const newKeys = expandedData.nodes
          .map(n => n.key)
          .filter(key => key && !existingKeys.has(key));
        
        if (newKeys.length > 0) {
          setSubgraphNodeKeys(prev => [...prev, ...newKeys]);
        }
        // Ensure we're on the Spotlight Graph tab
        setActiveSubgraphTab('subgraph');
      }

      // Don't reload the entire graph - we've already merged the expanded nodes
      // The subgraph will automatically update because it's built from subgraphNodeKeys
    } catch (err) {
      console.error('Failed to expand graph:', err);
      alert(`Failed to expand graph: ${err.message}`);
    } finally {
      setIsLoading(false);
      setShowExpandGraphModal(false);
      setExpandGraphContext(null);
    }
  }, [expandGraphContext, selectedNodes, subgraphNodeKeys, resultGraphData, loadGraph]);

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
  // Calculate graph width based on pane view mode
  const graphWidth = paneViewMode === 'split' ? availableWidth / 2 : 
                     paneViewMode === 'full' ? 0 : // Main graph hidden in full mode
                     paneViewMode === 'minimized' ? availableWidth : // Main graph full width when minimized
                     availableWidth; // single mode
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
        const pathData = await graphAPI.getShortestPaths(currentCaseId, selectedNodeKeys, 10);

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
      const pagerankData = await graphAPI.getPageRank(currentCaseId, nodeKeysToAnalyze, 20, 20, 0.85);

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

      const louvainData = await graphAPI.getLouvainCommunities(currentCaseId, nodeKeysToAnalyze, 1.0, 10);

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

      const betweennessData = await graphAPI.getBetweennessCentrality(currentCaseId, nodeKeysToAnalyze, 20, true);

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
  const regularSubgraphData = pathSubgraphData || buildSubgraph(subgraphNodeKeys);
  
  // Use result graph if result tab is active, otherwise use regular subgraph
  const subgraphData = activeSubgraphTab === 'result' && resultGraphData 
    ? resultGraphData 
    : regularSubgraphData;

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
        // Pass date range and case_id to timeline API if set
        const timelineParams = {};
        if (dateRange.start_date) {
          timelineParams.startDate = dateRange.start_date;
        }
        if (dateRange.end_date) {
          timelineParams.endDate = dateRange.end_date;
        }
        if (currentCaseId) {
          timelineParams.caseId = currentCaseId;
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
  }, [timelineContextKeys, dateRange, currentCaseId]);

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
    // Allow saving snapshots even without subgraph - save complete work state
    // Show progress dialog
    setSaveSnapshotProgress({
      isOpen: true,
      message: 'Preparing snapshot...',
      stage: null,
      stageProgress: 0,
      stageTotal: 0,
      current: 0,
      total: 6, // Loading nodes, extracting citations, processing chat, generating AI overview, collecting state, saving
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
        const batchPromises = batch.map(key => graphAPI.getNodeDetails(key, currentCaseId));
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
      
      // Stage 3: Collect full chat history (all messages and AI responses)
      setSaveSnapshotProgress(prev => ({
        ...prev,
        stage: 'Collecting chat history',
        stageProgress: 0,
        stageTotal: chatHistory.length,
        current: 3,
        message: 'Collecting complete chat history and AI responses...',
      }));

      // Save full chat history including all AI responses
      const fullChatHistory = chatHistory.map(msg => ({
        role: msg.role,
        content: msg.content,
        timestamp: msg.timestamp || new Date().toISOString(),
        contextMode: msg.contextMode,
        contextDescription: msg.contextDescription,
        cypherUsed: msg.cypherUsed,
        usedNodeKeys: msg.usedNodeKeys,
        resultGraph: msg.resultGraph, // Include result graph from AI responses
        modelInfo: msg.modelInfo,
        selectedNodes: msg.selectedNodes,
        isError: msg.isError,
      }));

      setSaveSnapshotProgress(prev => ({
        ...prev,
        stageProgress: chatHistory.length,
      }));

      // Stage 4: Generate AI overview of the snapshot (only if we have subgraph nodes)
      let aiOverview = null;
      if (subgraphNodeKeys.length > 0 && allSubgraphNodeDetails.length > 0) {
        setSaveSnapshotProgress(prev => ({
          ...prev,
          stage: 'Generating AI overview',
          stageProgress: 0,
          stageTotal: 1,
          current: 4,
          message: 'Generating AI overview...',
        }));

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
      } else {
        // Skip AI overview if no subgraph
        setSaveSnapshotProgress(prev => ({
          ...prev,
          stage: 'Skipping AI overview',
          stageProgress: 1,
          stageTotal: 1,
          current: 4,
          message: 'No subgraph nodes for AI overview',
        }));
      }

      // Stage 5: Collect complete work state
      setSaveSnapshotProgress(prev => ({
        ...prev,
        stage: 'Collecting work state',
        stageProgress: 0,
        stageTotal: 1,
        current: 5,
        message: 'Collecting complete work state (graph, table, selections)...',
      }));

      // Create a deep copy of all snapshot data to prevent reference issues
      // This ensures that if the original state is modified later, it won't affect the saved snapshot
      const snapshot = {
        name: name || `Snapshot ${new Date().toLocaleString()}`,
        notes: notes || '',
        // Subgraph data (spotlight graph)
        subgraph: subgraphNodeKeys.length > 0 
          ? JSON.parse(JSON.stringify(subgraphData)) 
          : { nodes: [], links: [] }, // Empty if no subgraph
        timeline: JSON.parse(JSON.stringify(timelineData || [])), // Deep copy timeline
        overview: {
          nodes: JSON.parse(JSON.stringify(allSubgraphNodeDetails)), // Deep copy node details
          nodeCount: subgraphData.nodes.length,
          linkCount: subgraphData.links.length,
        },
        citations: JSON.parse(JSON.stringify(citations)), // Deep copy citations
        // Full chat history with all AI responses
        chat_history: JSON.parse(JSON.stringify(fullChatHistory)), // Full chat history
        ai_overview: aiOverview ? String(aiOverview) : null, // Ensure string, not reference
        // Complete work state
        work_state: {
          // Graph state
          full_graph: JSON.parse(JSON.stringify(fullGraphData)), // Full graph data
          result_graph: resultGraphData ? JSON.parse(JSON.stringify(resultGraphData)) : null, // AI assistant result graph
          selected_nodes: JSON.parse(JSON.stringify(selectedNodes)), // Currently selected nodes
          selected_node_keys: Array.from(selectedNodeKeys), // Selected node keys
          subgraph_node_keys: Array.from(subgraphNodeKeys), // Spotlight graph node keys
          view_mode: viewMode, // Current view mode (graph, table, timeline, map)
          active_subgraph_tab: activeSubgraphTab, // Which subgraph tab is active
          // Table view state
          table_view_state: tableViewState ? JSON.parse(JSON.stringify(tableViewState)) : null, // Table panels, filters, selections
          // Graph view state
          date_range: JSON.parse(JSON.stringify(dateRange)), // Date range filter
          graph_search_term: graphSearchTerm, // Graph search term
          graph_search_mode: graphSearchMode, // Graph search mode
        },
      };

      setSaveSnapshotProgress(prev => ({
        ...prev,
        stageProgress: 1,
      }));

      // Stage 6: Save snapshot
      setSaveSnapshotProgress(prev => ({
        ...prev,
        stage: 'Saving snapshot',
        stageProgress: 0,
        stageTotal: 1,
        current: 6,
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
    async (caseTitle, saveNotes, description = '') => {
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

        // Use new API format with title/description, fallback to legacy format
        const result = await casesAPI.create({
          title: caseTitle,
          description: description || undefined,
        });

        // Handle both new response format (id, title) and legacy format (case_id, case_name)
        const caseId = result.id || result.case_id;
        const caseName = result.title || result.name || caseTitle;

        // Set current case context
        setCurrentCaseId(caseId);
        setCurrentCaseName(caseName);
        setCurrentCaseVersion(result.version || 1);
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

  // Load case version - simplified with case_id-based graph isolation
  // Graph data persists in Neo4j filtered by case_id, no more Cypher query execution
  const handleLoadCase = useCallback(async (caseData, versionData) => {
    // Check if this case/version is already loaded - if so, just switch to graph view
    if (currentCaseId === caseData.id && currentCaseVersion === versionData.version) {
      console.log('Case/version already loaded, switching to graph view without reloading');
      setAppView('graph');
      return;
    }

    // Store previous case ID to check if we're switching cases
    const previousCaseId = currentCaseId;
    const isSwitchingCase = previousCaseId !== caseData.id;

    try {
      setIsLoading(true);

      // With case_id-based isolation, just load the graph filtered by case_id
      // No need to clear or execute Cypher queries - data persists in Neo4j
      console.log(`Loading case ${caseData.id} (version ${versionData.version}) with case_id filter`);

      // Set case info first
      setCurrentCaseId(caseData.id);
      setCurrentCaseName(caseData.title || caseData.name);
      setCurrentCaseVersion(versionData.version);

      // Load the graph filtered by case_id
      await loadGraph(caseData.id);

      // If switching to a different case, clear chat history and load case-specific history
      if (isSwitchingCase) {
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

      console.log(`Case ${caseData.name} loaded successfully`);
    } catch (err) {
      console.error('Failed to load case:', err);
      alert('Failed to load case: ' + err.message);
    } finally {
      setIsLoading(false);
    }
  }, [loadGraph, currentCaseId, currentCaseVersion]);

  // Handle date range change - memoized to prevent infinite loops
  const handleDateRangeChange = useCallback((range) => {
    setDateRange({
      start_date: range.start_date,
      end_date: range.end_date,
    });
  }, []);

  // Show loading spinner while checking setup/auth status
  if (!setupCheckComplete) {
    return (
      <div className="min-h-screen bg-dark-950 text-light-100 flex items-center justify-center px-4">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 animate-spin text-owl-blue-500" />
          <p className="text-light-400">Loading...</p>
        </div>
      </div>
    );
  }

  // Show setup panel if no users exist
  if (needsSetup) {
    return (
      <div className="min-h-screen bg-dark-950 text-light-100 flex items-center justify-center px-4">
        <div className="w-full max-w-md">
          <SetupPanel
            onSetupComplete={() => {
              setNeedsSetup(false);
              // User will now see the login panel
            }}
          />
        </div>
      </div>
    );
  }

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
      <CasePermissionProvider userRole={authUserRole}>
        <CaseManagementView
          onLoadCase={handleLoadCase}
          onCreateCase={handleCreateCase}
          onLogout={handleLogout}
          isAuthenticated={isAuthenticated}
          authUsername={authUsername}
          authDisplayName={authDisplayName}
          onGoToEvidenceView={(caseData) => {
            if (!caseData) return;
            setCurrentCaseId(caseData.id);
            setCurrentCaseName(caseData.title || caseData.name);
            // Keep currentCaseVersion unchanged; evidence processing doesn't depend on it
            setAppView('evidence');
          }}
          onGoToWorkspaceView={(caseData) => {
            if (!caseData) return;
            setCurrentCaseId(caseData.id);
            setCurrentCaseName(caseData.title || caseData.name);
            setAppView('workspace');
          }}
          initialCaseToSelect={caseToSelect}
          onViewDocument={handleViewDocument}
          onCaseSelected={() => setCaseToSelect(null)}
          onShowCollaboratorModal={(caseData) => {
            setCollaboratorModalCase(caseData);
            setShowCollaboratorModal(true);
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

        {/* Collaborator Modal for managing case members */}
        <CollaboratorModal
          isOpen={showCollaboratorModal}
          onClose={() => {
            setShowCollaboratorModal(false);
            setCollaboratorModalCase(null);
          }}
          caseData={collaboratorModalCase}
          onMembersChanged={() => {
            // Optionally refresh the case list or permissions
          }}
        />
      </CasePermissionProvider>
    );
  }

  // Workspace view for current case
  if (appView === 'workspace') {
    const accountDropdownContent = (
      <div className="w-48 rounded-lg bg-white shadow-lg border border-light-200 py-2">
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
    );
    return (
      <>
        <WorkspaceView
          caseId={currentCaseId}
          caseName={currentCaseName}
          onBack={() => setAppView('caseManagement')}
          authUsername={authUsername}
          onLogoClick={() => setIsAccountDropdownOpen(prev => !prev)}
        />
        {isAccountDropdownOpen && (
          <div
            className="fixed inset-0 z-50"
            onClick={() => setIsAccountDropdownOpen(false)}
            aria-hidden="true"
          >
            <div
              className="absolute left-6 top-16"
              onClick={(e) => e.stopPropagation()}
            >
              {accountDropdownContent}
            </div>
          </div>
        )}
      </>
    );
  }

  // Evidence processing view for current case
  if (appView === 'evidence') {
    return (
      <CasePermissionProvider userRole={authUserRole}>
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
            // With case_id-based graph isolation, we simply load the graph filtered by case_id
            // No need to clear or reload cypher - data already persists in Neo4j
            if (!currentCaseId) {
              // No case yet: show an empty graph
              setGraphData({ nodes: [], links: [] });
              setFullGraphData({ nodes: [], links: [] });
              setAppView('graph');
              return;
            }

            // Load the graph for this case (data persists in Neo4j with case_id property)
            await loadGraph(currentCaseId);

            // Get latest version number for display
            try {
              const caseData = await casesAPI.get(currentCaseId);
              const versions = caseData.versions || [];
              if (versions.length > 0) {
                const sorted = [...versions].sort((a, b) => b.version - a.version);
                setCurrentCaseVersion(sorted[0].version);
              }
            } catch {
              // Ignore errors getting version info
            }

            setAppView('graph');
          } catch (err) {
            console.error('Failed to open case in graph:', err);
            alert(`Failed to open case in graph: ${err.message}`);
          }
        }}
        onLoadProcessedGraph={async (caseId, version) => {
          try {
            // With case_id-based graph isolation, we simply switch to the case
            // The graph data persists in Neo4j with case_id property
            setCurrentCaseId(caseId);
            setCurrentCaseVersion(version);
            await loadGraph(caseId);
            setAppView('graph');
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
      </CasePermissionProvider>
    );
  }

  return (
    <CasePermissionProvider userRole={authUserRole}>
    <div className="h-screen w-screen bg-light-50 flex flex-col overflow-hidden">
      {/* Header */}
      <header className="h-16 bg-white border-b border-light-200 flex items-center justify-between px-4 flex-shrink-0 shadow-sm">
        {/* Left side: File Management, Settings, Logo, and Save Snapshot */}
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

          {/* Settings Dropdown */}
          <div className="relative" ref={settingsDropdownRef}>
            <button
              ref={settingsButtonRef}
              onClick={() => setIsSettingsDropdownOpen(!isSettingsDropdownOpen)}
              className={`p-2 rounded-lg transition-colors relative ${
                isSettingsDropdownOpen || showBackgroundTasksPanel || showSystemLogs || showDatabaseModal
                  ? 'bg-owl-blue-500 text-white'
                  : 'hover:bg-light-100 text-light-600'
              }`}
              title="Settings"
            >
              <Settings className="w-5 h-5" />
            </button>

            {isSettingsDropdownOpen && (
              <div
                className="absolute z-50 mt-2 w-48 rounded-lg bg-white shadow-lg border border-light-200 py-2 left-0"
                style={{ top: '100%' }}
              >
                <button
                  onClick={() => {
                    setShowBackgroundTasksPanel(!showBackgroundTasksPanel);
                    setIsSettingsDropdownOpen(false);
                  }}
                  className={`w-full text-left px-4 py-2 rounded transition-colors text-sm flex items-center gap-2 ${
                    showBackgroundTasksPanel
                      ? 'bg-owl-blue-50 text-owl-blue-700'
                      : 'text-light-700 hover:bg-light-100'
                  }`}
                >
                  <Loader2 className="w-4 h-4" />
                  Background Tasks
                </button>
                <button
                  onClick={() => {
                    setShowSystemLogs(!showSystemLogs);
                    setIsSettingsDropdownOpen(false);
                  }}
                  className={`w-full text-left px-4 py-2 rounded transition-colors text-sm flex items-center gap-2 ${
                    showSystemLogs
                      ? 'bg-owl-blue-50 text-owl-blue-700'
                      : 'text-light-700 hover:bg-light-100'
                  }`}
                >
                  <FileText className="w-4 h-4" />
                  System Logs
                </button>
                <button
                  onClick={() => {
                    setShowDatabaseModal(!showDatabaseModal);
                    setIsSettingsDropdownOpen(false);
                  }}
                  className={`w-full text-left px-4 py-2 rounded transition-colors text-sm flex items-center gap-2 ${
                    showDatabaseModal
                      ? 'bg-owl-blue-50 text-owl-blue-700'
                      : 'text-light-700 hover:bg-light-100'
                  }`}
                >
                  <Database className="w-4 h-4" />
                  Vector Database
                </button>
              </div>
            )}
          </div>

          {/* Owl Logo */}
          <button
            ref={logoButtonRef}
            onClick={() => setIsAccountDropdownOpen(prev => !prev)}
            className="group focus:outline-none relative"
            type="button"
          >
            <img src="/owl-logo.webp" alt="Owl Consultancy Group" className="w-40 h-40 object-contain" />
            
            {isAccountDropdownOpen && (
              <div
                ref={accountDropdownRef}
                className="absolute z-50 mt-2 w-48 rounded-lg bg-white shadow-lg border border-light-200 py-2 left-0"
                style={{ top: '70px' }}
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
          </button>

        </div>

        {/* Right side: View controls and other buttons */}
        <div className="flex items-center gap-3">
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
                title="Spotlight Graph options"
              >
                <GitBranch className="w-4 h-4" />
                Spotlight Graph
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
                  
                  <div className="border-t border-light-200 my-1"></div>

                  <button
                    onClick={handleFindSimilarEntities}
                    disabled={isScanningSimilar}
                    className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                      isScanningSimilar
                        ? 'text-light-400 cursor-not-allowed opacity-50'
                        : 'text-light-800 hover:bg-light-50 cursor-pointer'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <Search className="w-4 h-4" />
                      <span>{isScanningSimilar ? 'Scanning...' : 'Find Similar Entities'}</span>
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
            <button
              onClick={() => setViewMode('financial')}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors ${
                viewMode === 'financial'
                  ? 'bg-white text-owl-blue-900 shadow-sm'
                  : 'text-light-600 hover:text-light-800'
              }`}
            >
              <DollarSign className="w-4 h-4" />
              Financial
            </button>
            <button
              onClick={() => setViewMode('table')}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors ${
                viewMode === 'table'
                  ? 'bg-white text-owl-blue-900 shadow-sm'
                  : 'text-light-600 hover:text-light-800'
              }`}
            >
              <Table2 className="w-4 h-4" />
              Table
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

          {(viewMode === 'graph' || viewMode === 'table') && (
            <GraphSearchFilter
              mode={graphSearchMode}
              onModeChange={handleGraphModeChange}
              onFilterChange={handleGraphFilterChange}
              onQueryChange={handleGraphQueryChange}
              onSearch={handleGraphSearchExecute}
              placeholder={viewMode === 'table' ? 'Filter table nodes...' : 'Filter graph nodes...'}
              disabled={isLoading}
            />
          )}

          {viewMode !== 'graph' && viewMode !== 'table' && (
            <SearchBar onSelectNode={handleSearchSelect} caseId={currentCaseId} />
          )}
          
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

          <button
            onClick={() => setShowSnapshotModal(true)}
            className="p-2 rounded-lg transition-colors bg-owl-orange-500 hover:bg-owl-orange-600 text-white"
            title="Save Snapshot (Cmd/Ctrl+S)"
          >
            <Camera className="w-5 h-5" />
          </button>
        </div>
      </header>

      {/* Main content - min-w-0 so it can shrink when table has Selected/Chat alongside */}
      <div className="flex-1 flex min-w-0 overflow-hidden">
        {/* Main view area - min-w-0 prevents flex item from expanding beyond container */}
        {viewMode === 'table' ? (
          // Table mode: table | selected | chat in one row; Selected/Chat push table (shrink), never overlay
          <div className="flex-1 flex min-w-0 overflow-hidden w-full">
            {/* Table view - takes remaining space, shrinks when Selected or Chat are shown */}
            <div className="flex-1 min-w-0 overflow-hidden">
              <div className="h-full flex flex-col min-h-0">
                <GraphTableView
                  graphData={graphData}
                  searchTerm={graphSearchTerm || ''}
                  onNodeClick={handleNodeClick}
                  selectedNodeKeys={selectedNodeKeys}
                  onOpenChat={handleTableChatOpen}
                  isChatOpen={isChatOpen || selectedNodesDetails.length > 0}
                  resultGraphData={resultGraphData}
                  tableViewState={tableViewState}
                  onTableViewStateChange={setTableViewState}
                  caseId={currentCaseId}
                  onMergeNodes={handleMergeEntities}
                  onDeleteNodes={async (nodesToDelete) => {
                    for (const node of nodesToDelete) {
                      await graphAPI.deleteNode(node.key, currentCaseId);
                    }
                    await loadGraph();
                  }}
                  onUpdateNode={handleUpdateNode}
                  onNodeCreated={async (nodeKey) => {
                    await loadGraph();
                  }}
                  onGraphRefresh={loadGraph}
                />
              </div>
            </div>
            
            {/* Selected nodes sidebar - only show in table mode if nodes are selected */}
            {selectedNodesDetails.length > 0 && (
              <div className="w-80 bg-white border-l border-light-200 h-full flex flex-col overflow-hidden shadow-sm flex-shrink-0">
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
                          if (newSelection.length > 0) {
                            loadNodeDetails(newKeys);
                          } else {
                            setSelectedNodesDetails([]);
                          }
                        }}
                        onSelectNode={handleSearchSelect}
                        onViewDocument={handleViewDocument}
                        onNodeUpdate={(updatedNode) => {
                          setSelectedNodesDetails(prev =>
                            prev.map(n => n.key === updatedNode.key ? updatedNode : n)
                          );
                        }}
                        username={authUsername}
                        compact={selectedNodesDetails.length > 1}
                        caseId={currentCaseId}
                        searchTerm={graphSearchTerm || ''}
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}
            
            {/* Chat panel - side by side with table view */}
            {isChatOpen && (
              <ChatPanel
                isOpen={isChatOpen}
                onToggle={() => setIsChatOpen(!isChatOpen)}
                onClose={() => setIsChatOpen(false)}
                selectedNodes={selectedNodesDetails}
                onMessagesChange={setChatHistory}
                initialMessages={chatHistory}
                onAutoSave={handleAutoSaveChat}
                currentCaseId={currentCaseId}
                currentCaseName={currentCaseName}
                currentCaseVersion={currentCaseVersion}
                isTableMode={true}
              />
            )}
          </div>
        ) : (
          // Normal view mode (graph, timeline, map) or table without chat
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
            ) : paneViewMode === 'full' || paneViewMode === 'split' || paneViewMode === 'minimized' ? (
              // Full, Split, or Minimized panel graph view
              <div className="absolute inset-0 flex relative">
                {/* Main Graph Panel - Hidden in full mode, visible in split/minimized */}
                <div 
                  className={`relative bg-light-50 transition-all duration-300 ease-in-out ${
                    paneViewMode === 'full' ? 'w-0 overflow-hidden' :
                    paneViewMode === 'minimized' ? 'flex-1' :
                    'flex-1 border-r border-light-200'
                  }`}
                >
                  {paneViewMode !== 'full' && (
                    <GraphView
                      graphData={graphData}
                      selectedNodes={selectedNodes}
                      onNodeClick={handleNodeClick}
                      onBulkNodeSelect={handleBulkNodeSelect}
                      onNodeRightClick={handleNodeRightClick}
                      onNodeDoubleClick={handleNodeDoubleClick}
                      onBackgroundClick={handleBackgroundClick}
                      width={paneViewMode === 'minimized' ? availableWidth : availableWidth / 2}
                      height={graphHeight}
                      paneViewMode={paneViewMode}
                      onPaneViewModeChange={setPaneViewMode}
                      onAddToSubgraph={handleAddToSubgraph}
                      onRemoveFromSubgraph={handleRemoveFromSubgraph}
                      subgraphNodeKeys={subgraphNodeKeys}
                      onAddNode={() => setShowAddNodeModal(true)}
                      onFindSimilarEntities={handleFindSimilarEntities}
                      isScanningSimilar={isScanningSimilar}
                      caseId={currentCaseId}
                    />
                  )}
                </div>
                
                {/* Spotlight/Result Graph Panel */}
                <div 
                  className={`relative bg-light-50 overflow-hidden transition-all duration-300 ease-in-out ${
                    paneViewMode === 'full' ? 'flex-1' :
                    paneViewMode === 'minimized' ? 'w-0 overflow-hidden' :
                    'flex-1'
                  }`}
                  data-subgraph-container
                >
                  {/* Window Controls - Always on leftmost border */}
                  {paneViewMode !== 'minimized' && (
                    <div className="absolute left-0 top-0 bottom-0 w-10 bg-white/90 backdrop-blur-sm border-r border-light-200 shadow-lg flex flex-col items-center py-2 z-20 gap-2">
                      {paneViewMode === 'split' ? (
                        // Middle state: show one left and one right
                        <>
                          <button
                            onClick={() => setPaneViewMode('minimized')}
                            className="p-2 hover:bg-light-100 rounded transition-colors mb-2"
                            title="Minimize"
                          >
                            <ChevronRight className="w-4 h-4 text-light-600" />
                          </button>
                          <button
                            onClick={() => setPaneViewMode('full')}
                            className="p-2 hover:bg-light-100 rounded transition-colors"
                            title="Maximize to Full View"
                          >
                            <ChevronLeft className="w-4 h-4 text-light-600" />
                          </button>
                        </>
                      ) : paneViewMode === 'full' ? (
                        // Maximized state: show one right to go to middle, two right to minimize
                        <>
                          <button
                            onClick={() => setPaneViewMode('minimized')}
                            className="p-2 hover:bg-light-100 rounded transition-colors mb-2"
                            title="Minimize"
                          >
                            <div className="flex items-center gap-0.5">
                              <ChevronRight className="w-4 h-4 text-light-600" />
                              <ChevronRight className="w-4 h-4 text-light-600" />
                            </div>
                          </button>
                          <button
                            onClick={() => setPaneViewMode('split')}
                            className="p-2 hover:bg-light-100 rounded transition-colors"
                            title="Restore to Split View"
                          >
                            <ChevronRight className="w-4 h-4 text-light-600" />
                          </button>
                        </>
                      ) : null}
                      
                      {/* Graph Control Icons - Only show in spotlight/result graph */}
                      {subgraphGraphRef.current && (
                        <>
                          {/* Center Button */}
                          <button
                            onClick={() => {
                              if (subgraphGraphRef.current) {
                                if (selectedNodes && selectedNodes.length > 0) {
                                  const selectedKeys = selectedNodes.map(n => n.key);
                                  subgraphGraphRef.current.centerOnNodes(selectedKeys);
                                } else {
                                  subgraphGraphRef.current.centerGraph();
                                }
                              }
                            }}
                            className="p-2 hover:bg-light-100 rounded transition-colors"
                            title={selectedNodes && selectedNodes.length > 0 ? "Center on selected nodes" : "Center and fit graph"}
                          >
                            <Target className="w-4 h-4 text-light-600" />
                          </button>
                          
                          {/* Selection Mode Toggle */}
                          <button
                            onClick={() => {
                              if (subgraphGraphRef.current) {
                                const newMode = subgraphGraphRef.current.selectionMode === 'click' ? 'drag' : 'click';
                                subgraphGraphRef.current.setSelectionMode(newMode);
                              }
                            }}
                            className={`p-2 hover:bg-light-100 rounded transition-colors ${
                              subgraphGraphRef.current?.selectionMode === 'drag' ? 'bg-owl-blue-100' : ''
                            }`}
                            title={subgraphGraphRef.current?.selectionMode === 'click' ? 'Switch to drag selection' : 'Switch to click selection'}
                          >
                            {subgraphGraphRef.current?.selectionMode === 'click' ? (
                              <Square className="w-4 h-4 text-light-600" />
                            ) : (
                              <MousePointer className="w-4 h-4 text-owl-blue-600" />
                            )}
                          </button>
                          
                          {/* Settings Button */}
                          <button
                            onClick={() => {
                              if (subgraphGraphRef.current) {
                                subgraphGraphRef.current.setShowControls(!subgraphGraphRef.current.showControls);
                              }
                            }}
                            className={`p-2 hover:bg-light-100 rounded transition-colors ${
                              subgraphGraphRef.current?.showControls ? 'bg-owl-blue-100' : ''
                            }`}
                            title="Graph Settings"
                          >
                            <Settings className={`w-4 h-4 ${subgraphGraphRef.current?.showControls ? 'text-owl-blue-600' : 'text-light-600'}`} />
                          </button>
                        </>
                      )}
                    </div>
                  )}
                  {paneViewMode !== 'minimized' && (
                    subgraphNodeKeys.length > 0 ? (
                    // Show subgraph of selected nodes
                    <>
                      <div className="absolute top-4 left-[44px] right-4 z-10 flex flex-col gap-2">
                        {/* Subgraph Header with Tabs */}
                        <div className="bg-white/90 backdrop-blur-sm rounded-lg shadow-sm border border-light-200 overflow-hidden">
                          {/* Tabs */}
                          <div className="flex border-b border-light-200">
                            <button
                              onClick={() => setActiveSubgraphTab('subgraph')}
                              className={`flex-1 px-3 py-2 text-xs font-medium transition-colors ${
                                activeSubgraphTab === 'subgraph'
                                  ? 'bg-owl-blue-500 text-white'
                                  : 'bg-white text-light-700 hover:bg-light-100'
                              }`}
                            >
                              Spotlight Graph ({regularSubgraphData.nodes.length} nodes)
                            </button>
                            <button
                              onClick={() => setActiveSubgraphTab('result')}
                              className={`flex-1 px-3 py-2 text-xs font-medium transition-colors ${
                                activeSubgraphTab === 'result'
                                  ? 'bg-owl-blue-500 text-white'
                                  : 'bg-white text-light-700 hover:bg-light-100'
                              }`}
                              disabled={!resultGraphData || !resultGraphData.nodes || resultGraphData.nodes.length === 0}
                            >
                              Result Graph ({resultGraphData?.nodes?.length || 0} nodes)
                            </button>
                          </div>
                          
                          {/* Header Actions */}
                          <div className="flex items-center justify-between p-2 px-3">
                            <div className="flex items-center gap-2">
                              <Network className="w-4 h-4 text-owl-blue-700" />
                              <h3 className="text-sm font-semibold text-owl-blue-900">
                                {activeSubgraphTab === 'result' ? 'Result Graph' : 'Spotlight Graph'} ({subgraphData.nodes.length} nodes, {subgraphData.links.length} links)
                              </h3>
                              {activeSubgraphTab === 'subgraph' && queryFocusHistory.length > 1 && (
                                <span className="text-xs text-light-500 ml-1">
                                  ({queryFocusHistoryIndex + 1}/{queryFocusHistory.length})
                                </span>
                              )}
                            </div>
                            <div className="flex items-center gap-2">
                              {activeSubgraphTab === 'subgraph' && (
                                <>
                                  {/* History Navigation */}
                                  {queryFocusHistory.length > 1 && (
                                    <div className="flex items-center gap-1 border-r border-light-200 pr-2 mr-1">
                                      <button
                                        onClick={navigateQueryFocusHistoryBack}
                                        disabled={queryFocusHistoryIndex <= 0}
                                        className="p-1 hover:bg-light-100 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                        title={`Navigate back (${queryFocusHistoryIndex + 1}/${queryFocusHistory.length})`}
                                      >
                                        <ChevronLeft className="w-4 h-4 text-light-600" />
                                      </button>
                                      <button
                                        onClick={navigateQueryFocusHistoryForward}
                                        disabled={queryFocusHistoryIndex >= queryFocusHistory.length - 1}
                                        className="p-1 hover:bg-light-100 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                        title={`Navigate forward (${queryFocusHistoryIndex + 1}/${queryFocusHistory.length})`}
                                      >
                                        <ChevronRight className="w-4 h-4 text-light-600" />
                                      </button>
                                    </div>
                                  )}
                                  <button
                                    onClick={handleSelectAllSubgraphNodes}
                                    className="flex items-center gap-1.5 px-2 py-1 text-xs bg-owl-blue-500 hover:bg-owl-blue-600 text-white rounded transition-colors"
                                    title="Select all subgraph nodes"
                                  >
                                    <CheckSquare className="w-3.5 h-3.5" />
                                    Select All
                                  </button>
                                </>
                              )}
                              {activeSubgraphTab === 'result' && (
                                <>
                                  <button
                                    onClick={() => {
                                      // Overwrite Spotlight Graph with Result Graph
                                      if (resultGraphData && resultGraphData.nodes && resultGraphData.nodes.length > 0) {
                                        const resultNodeKeys = resultGraphData.nodes.map(node => node.key).filter(key => key);
                                        setSubgraphNodeKeys(resultNodeKeys);
                                        setPathSubgraphData(null); // Clear path subgraph data
                                        // Show alert first, then switch tab after user clicks OK
                                        alert(`Spotlight Graph updated with ${resultNodeKeys.length} node${resultNodeKeys.length > 1 ? 's' : ''} from Result Graph`);
                                        // Switch to Spotlight Graph tab after alert is dismissed
                                        setActiveSubgraphTab('subgraph');
                                      }
                                    }}
                                    className="flex items-center gap-1.5 px-2 py-1 text-xs bg-owl-blue-500 hover:bg-owl-blue-600 text-white rounded transition-colors"
                                    title="Copy Result Graph to Spotlight Graph"
                                  >
                                    <Copy className="w-3.5 h-3.5" />
                                    Use in Spotlight
                                  </button>
                                </>
                              )}
                              {activeSubgraphTab === 'subgraph' && selectedNodes.length > 0 && (
                                <>
                                  <button
                                    onClick={() => handleExpandGraph('selected')}
                                    className="flex items-center gap-1.5 px-2 py-1 text-xs bg-owl-orange-500 hover:bg-owl-orange-600 text-white rounded transition-colors"
                                    title={`Expand ${selectedNodes.length} selected node${selectedNodes.length > 1 ? 's' : ''}`}
                                  >
                                    <Maximize2 className="w-3.5 h-3.5" />
                                    Expand Selected
                                  </button>
                                  <div className="relative">
                                    <button
                                      ref={clearSpotlightButtonRef}
                                      onClick={() => setShowClearSpotlightConfirm(true)}
                                      className="flex items-center gap-1.5 px-2 py-1 text-xs bg-red-500 hover:bg-red-600 text-white rounded transition-colors"
                                      title="Clear Spotlight Graph and selected nodes"
                                    >
                                      <X className="w-3.5 h-3.5" />
                                      Clear Graph
                                    </button>
                                    {/* Confirmation Popup */}
                                    {showClearSpotlightConfirm && (
                                      <div
                                        ref={clearSpotlightPopupRef}
                                        className="absolute bottom-full right-0 mb-2 bg-white border border-light-200 rounded-lg shadow-xl p-3 z-[9999] min-w-[200px]"
                                        style={{
                                          transform: 'translateX(-20px)',
                                        }}
                                      >
                                        <p className="text-sm text-light-800 mb-3">
                                          Clear Spotlight Graph and selected nodes?
                                        </p>
                                        <div className="flex items-center gap-2">
                                          <button
                                            onClick={() => {
                                              // Clear spotlight graph
                                              setSubgraphNodeKeys([]);
                                              setPathSubgraphData(null);
                                              // Clear selected nodes
                                              setSelectedNodes([]);
                                              setSelectedNodesDetails([]);
                                              setTimelineContextKeys([]);
                                              // Reset history
                                              setQueryFocusHistory([{
                                                subgraphNodeKeys: [],
                                                selectedNodes: [],
                                                timestamp: Date.now()
                                              }]);
                                              setQueryFocusHistoryIndex(0);
                                              // Close spotlight pane
                                              setPaneViewMode('single');
                                              // Close confirmation
                                              setShowClearSpotlightConfirm(false);
                                            }}
                                            className="flex-1 px-3 py-1.5 text-xs bg-red-500 hover:bg-red-600 text-white rounded transition-colors"
                                          >
                                            Confirm
                                          </button>
                                          <button
                                            onClick={() => setShowClearSpotlightConfirm(false)}
                                            className="flex-1 px-3 py-1.5 text-xs bg-light-100 hover:bg-light-200 text-light-700 rounded transition-colors"
                                          >
                                            Cancel
                                          </button>
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                </>
                              )}
                              <button
                                onClick={handleCloseDetails}
                                className="p-1 hover:bg-light-100 rounded transition-colors"
                                title="Clear selection"
                              >
                                <X className="w-4 h-4 text-light-600" />
                              </button>
                            </div>
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
                        width={paneViewMode === 'full' ? availableWidth : availableWidth / 2}
                        height={graphHeight}
                        paneViewMode={paneViewMode}
                        onPaneViewModeChange={setPaneViewMode}
                        isSubgraph={true}
                        onRemoveFromSubgraph={handleRemoveFromSubgraph}
                        subgraphNodeKeys={subgraphNodeKeys}
                        caseId={currentCaseId}
                      />
                    </>
                  ) : (
                    // Show empty state when no nodes are selected
                    <div className="h-full flex flex-col items-center justify-center p-8">
                      <div className="flex flex-col items-center gap-4 text-center max-w-md">
                        <Network className="w-12 h-12 text-owl-blue-300" />
                        <div>
                          <h3 className="text-md font-medium text-light-700 mb-2">
                            Spotlight Graph View
                          </h3>
                          <p className="text-light-600 text-sm">
                            Select nodes in the main graph to view their spotlight graph here.
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
                  )
                  )}
                </div>
                
                {/* Minimized Panel - Slides in from right when minimized */}
                {paneViewMode === 'minimized' && subgraphNodeKeys.length > 0 && (
                  <div className="absolute right-0 top-0 bottom-0 w-[10px] bg-white/90 backdrop-blur-sm border-l border-light-200 shadow-lg flex flex-col items-center py-2 z-20 transition-all duration-300 ease-in-out">
                    <button
                      onClick={() => setPaneViewMode('full')}
                      className="p-2 hover:bg-light-100 rounded transition-colors mb-2"
                      title="Maximize to Full View"
                    >
                      <div className="flex items-center gap-0.5">
                        <ChevronLeft className="w-4 h-4 text-light-600" />
                        <ChevronLeft className="w-4 h-4 text-light-600" />
                      </div>
                    </button>
                    <button
                      onClick={() => setPaneViewMode('split')}
                      className="p-2 hover:bg-light-100 rounded transition-colors mb-2"
                      title="Restore to Split View"
                    >
                      <ChevronLeft className="w-4 h-4 text-light-600" />
                    </button>
                    <div className="flex-1 flex items-center">
                      <div className="writing-vertical-rl text-xs font-semibold text-owl-blue-900 transform rotate-180">
                        {activeSubgraphTab === 'result' ? 'Result' : 'Spotlight'}
                      </div>
                    </div>
                  </div>
                )}
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
                onFindSimilarEntities={handleFindSimilarEntities}
                isScanningSimilar={isScanningSimilar}
                caseId={currentCaseId}
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
          ) : viewMode === 'financial' ? (
            // Financial View
            <div className="h-full">
              <FinancialView
                caseId={currentCaseId}
                onNodeSelect={(nodeKey) => {
                  const node = graphData.nodes.find(n => n.key === nodeKey);
                  if (node) handleNodeClick(node);
                }}
              />
            </div>
          ) : viewMode === 'table' ? (
            // Table View - tabular view of graph nodes with expandable relations
            <div className="h-full flex flex-col min-h-0">
              <GraphTableView
                graphData={graphData}
                searchTerm={graphSearchTerm || ''}
                onNodeClick={handleNodeClick}
                selectedNodeKeys={selectedNodeKeys}
                onOpenChat={handleTableChatOpen}
                isChatOpen={isChatOpen}
                resultGraphData={resultGraphData}
                tableViewState={tableViewState}
                onTableViewStateChange={setTableViewState}
                caseId={currentCaseId}
                onMergeNodes={handleMergeEntities}
                onDeleteNodes={async (nodesToDelete) => {
                  for (const node of nodesToDelete) {
                    await graphAPI.deleteNode(node.key, currentCaseId);
                  }
                  await loadGraph();
                }}
                onUpdateNode={handleUpdateNode}
                onNodeCreated={async (nodeKey) => {
                  await loadGraph();
                }}
                onGraphRefresh={loadGraph}
              />
            </div>
          ) : (
            // Map View
            <MapView
              selectedNodes={selectedNodes}
              onNodeClick={handleNodeClick}
              onBulkNodeSelect={handleBulkNodeSelect}
              onBackgroundClick={handleBackgroundClick}
              caseId={currentCaseId}
            />
          )}
          </div>
        )}

        {/* Node details sidebar - show all selected nodes (only for non-table views) */}
        {selectedNodesDetails.length > 0 && viewMode !== 'table' && (
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
                    caseId={currentCaseId}
                    searchTerm={graphSearchTerm || ''}
                  />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Chat panel - only show if not in table mode (table mode chat is handled above) */}
        {isChatOpen && viewMode !== 'table' && (
          <ChatPanel
            isOpen={isChatOpen}
            onToggle={() => setIsChatOpen(!isChatOpen)}
            onClose={() => setIsChatOpen(false)}
            selectedNodes={selectedNodesDetails}
            onMessagesChange={setChatHistory}
            initialMessages={chatHistory}
            onAutoSave={handleAutoSaveChat}
            currentCaseId={currentCaseId}
            currentCaseName={currentCaseName}
            currentCaseVersion={currentCaseVersion}
            isTableMode={false}
          />
        )}
      </div>

      {/* Context menu - only show for users with edit permission */}
      <PermissionAwareContextMenu
        contextMenu={contextMenu}
        onShowDetails={handleShowDetails}
        onExpand={handleExpand}
        onClose={() => setContextMenu(null)}
        onAddRelationship={handleStartRelationshipCreation}
        onCreateRelationship={handleCreateRelationship}
        onAnalyzeRelationships={handleAnalyzeRelationships}
        isRelationshipMode={isRelationshipMode}
        selectedNodes={selectedNodes}
        onExpandGraph={(context, nodeKeys) => {
          if (nodeKeys && nodeKeys.length > 0) {
            setExpandGraphContext(context);
            setShowExpandGraphModal(true);
          }
        }}
        isSubgraph={paneViewMode === 'split'}
        onMerge={handleMergeSelected}
        onDelete={handleDeleteNode}
      />

      {/* Create Relationship Modal */}
      <CreateRelationshipModal
        isOpen={showCreateRelationshipModal}
        onClose={handleCancelRelationshipCreation}
        sourceNodes={relationshipSourceNodes}
        targetNodes={selectedNodes.filter(
          target => !relationshipSourceNodes.some(source => source.key === target.key)
        )}
        onRelationshipCreated={handleRelationshipCreated}
        caseId={currentCaseId}
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
        caseId={currentCaseId}
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
            total: 6, // Fetching, loading nodes, restoring chat, setting up timeline, restoring work state, finalizing
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

            // Restore work state if available
            const workState = fullSnapshot.work_state || {};
            
            // Stage 2: Restore graph state
            setLoadSnapshotProgress(prev => ({
              ...prev,
              current: 2,
              stage: 'Restoring graph state...',
              message: 'Restoring graph and result graph...',
            }));

            if (workState.full_graph) {
              setFullGraphData(workState.full_graph);
            }
            if (workState.result_graph) {
              setResultGraphData(workState.result_graph);
            }
            if (workState.view_mode) {
              setViewMode(workState.view_mode);
            }
            if (workState.active_subgraph_tab) {
              setActiveSubgraphTab(workState.active_subgraph_tab);
            }
            if (workState.date_range) {
              setDateRange(workState.date_range);
            }
            if (workState.graph_search_term !== undefined) {
              setGraphSearchTerm(workState.graph_search_term);
            }
            if (workState.graph_search_mode) {
              setGraphSearchMode(workState.graph_search_mode);
            }

            // Restore subgraph node keys and selected nodes
            if (fullSnapshot.subgraph && fullSnapshot.subgraph.nodes) {
              const snapshotNodes = fullSnapshot.subgraph.nodes;
              const nodeKeys = snapshotNodes.map(n => n.key);
              
              // Use work_state node keys if available, otherwise use subgraph nodes
              const subgraphKeys = workState.subgraph_node_keys || nodeKeys;
              const selectedKeys = workState.selected_node_keys || nodeKeys;
              
              setSubgraphNodeKeys(subgraphKeys);
              setSelectedNodes(snapshotNodes.filter(n => selectedKeys.includes(n.key)));
              setTimelineContextKeys(subgraphKeys);
              
              // Ensure split view is enabled to show the subgraph
              if (paneViewMode !== 'split') {
                setPaneViewMode('split');
              }
            } else if (workState.subgraph_node_keys && workState.subgraph_node_keys.length > 0) {
              // Restore from work_state even if no subgraph in snapshot
              setSubgraphNodeKeys(workState.subgraph_node_keys);
              if (workState.selected_nodes && workState.selected_nodes.length > 0) {
                setSelectedNodes(workState.selected_nodes);
              }
              setTimelineContextKeys(workState.subgraph_node_keys);
              if (paneViewMode !== 'split') {
                setPaneViewMode('split');
              }
            }

            // Stage 3: Restore table view state
            setLoadSnapshotProgress(prev => ({
              ...prev,
              current: 3,
              stage: 'Restoring table view state...',
              message: 'Restoring table panels and filters...',
            }));

            if (workState.table_view_state) {
              setTableViewState(workState.table_view_state);
            }

            // Stage 4: Load node details
            const nodeKeysToLoad = workState.subgraph_node_keys || 
              (fullSnapshot.subgraph ? fullSnapshot.subgraph.nodes.map(n => n.key) : []);
            
            if (nodeKeysToLoad.length > 0) {
              setLoadSnapshotProgress(prev => ({
                ...prev,
                current: 4,
                stage: `Loading node details (${nodeKeysToLoad.length} nodes)...`,
                message: 'Loading node details...',
              }));

              // Load node details for the selected nodes (for the overview panel)
              await loadNodeDetails(nodeKeysToLoad);
            }

            // Stage 5: Restore chat history
            setLoadSnapshotProgress(prev => ({
              ...prev,
              current: 5,
              stage: 'Restoring chat history...',
              message: 'Restoring complete chat history and AI responses...',
            }));

            // Restore full chat history from snapshot (includes all AI responses)
            if (fullSnapshot.chat_history && fullSnapshot.chat_history.length > 0) {
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

            // Stage 6: Finalizing
            setLoadSnapshotProgress(prev => ({
              ...prev,
              current: 6,
              stage: 'Finalizing...',
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

      {/* System Logs Panel */}
      <SystemLogsPanel
        isOpen={showSystemLogs}
        onClose={() => setShowSystemLogs(false)}
      />

      {/* Database Modal */}
      <DatabaseModal
        isOpen={showDatabaseModal}
        onClose={() => setShowDatabaseModal(false)}
        currentUser={authUsername}
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

      {/* Similar Entities Scan Progress Dialog */}
      <SimilarEntitiesProgressDialog
        isOpen={similarScanProgress !== null}
        onCancel={handleCancelSimilarScan}
        progress={similarScanProgress}
      />

      {/* Entity Type Selector Modal (for similar entities scan) */}
      <EntityTypeSelectorModal
        isOpen={showEntityTypeSelector}
        onClose={() => setShowEntityTypeSelector(false)}
        onStartScan={(selectedTypes) => {
          setShowEntityTypeSelector(false);
          startSimilarEntitiesScan(selectedTypes);
        }}
        entityTypes={scanEntityTypes}
        isLoading={isLoadingEntityTypes}
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
        caseId={currentCaseId}
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

      {/* Expand Graph Modal */}
      <ExpandGraphModal
        isOpen={showExpandGraphModal}
        onClose={() => {
          setShowExpandGraphModal(false);
          setExpandGraphContext(null);
        }}
        onExpand={executeGraphExpansion}
        nodeCount={
          expandGraphContext === 'selected' ? selectedNodes.length :
          expandGraphContext === 'subgraph' ? subgraphNodeKeys.length :
          expandGraphContext === 'result' ? (resultGraphData?.nodes?.length || 0) :
          0
        }
      />

      {/* Merge Entities Modal */}
      <MergeEntitiesModal
        isOpen={showMergeModal}
        onClose={handleMergeModalCancel}
        onSuccess={handleMergeModalSuccess}
        entity1={mergeEntity1}
        entity2={mergeEntity2}
        similarity={mergeSimilarity}
        onMerge={handleMergeEntities}
      />

      {/* Similar Entities List Modal */}
      {showSimilarEntitiesList && (
        <div 
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" 
          onClick={() => setShowSimilarEntitiesList(false)}
        >
          <div 
            className="bg-white rounded-lg shadow-xl w-full max-w-4xl max-h-[80vh] overflow-hidden flex flex-col" 
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-4 border-b border-light-200 bg-owl-blue-50">
              <h2 className="text-lg font-semibold text-owl-blue-900">
                Similar Entities Found ({similarEntitiesPairs.length})
              </h2>
              <button 
                onClick={() => setShowSimilarEntitiesList(false)} 
                className="p-1 hover:bg-light-100 rounded"
              >
                <X className="w-5 h-5 text-light-600" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              {similarEntitiesPairs.length === 0 ? (
                <p className="text-light-600 text-center py-8">No similar entities found.</p>
              ) : (
                <div className="space-y-3">
                  {similarEntitiesPairs.map((pair, idx) => (
                    <div key={idx} className="border border-light-200 rounded-lg p-4 hover:bg-light-50 transition-colors">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-3">
                          <span className="text-sm font-medium text-owl-blue-900">{pair.entity1.name}</span>
                          <ArrowRight className="w-4 h-4 text-light-400" />
                          <span className="text-sm font-medium text-owl-blue-900">{pair.entity2.name}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-light-600">{Math.round(pair.similarity * 100)}% similar</span>
                          <button
                            onClick={() => handleViewSimilarPair(pair)}
                            className="px-3 py-1 text-xs bg-owl-blue-100 text-owl-blue-700 rounded hover:bg-owl-blue-200 transition-colors flex items-center gap-1"
                            title="View detailed comparison"
                          >
                            <Eye className="w-3 h-3" />
                            View
                          </button>
                          <button
                            onClick={() => handleRejectPair(pair)}
                            className="px-3 py-1 text-xs bg-light-200 text-light-700 rounded hover:bg-light-300 transition-colors flex items-center gap-1"
                            title="Mark as false positive - won't appear in future scans"
                          >
                            <X className="w-3 h-3" />
                            Reject
                          </button>
                          <button
                            onClick={() => handleMergeSimilarPair(pair)}
                            className="px-3 py-1 text-xs bg-owl-blue-500 text-white rounded hover:bg-owl-blue-600 transition-colors flex items-center gap-1"
                          >
                            <Merge className="w-3 h-3" />
                            Merge
                          </button>
                        </div>
                      </div>
                      <div className="text-xs text-light-600">
                        Type: {pair.entity1.type} • Similarity: {pair.similarity.toFixed(3)}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Entity Comparison Modal */}
      <EntityComparisonModal
        isOpen={showComparisonModal}
        onClose={handleCloseComparisonModal}
        entity1={comparisonPair?.entity1}
        entity2={comparisonPair?.entity2}
        similarity={comparisonPair?.similarity}
        caseId={currentCaseId}
        onMerge={handleMergeFromComparison}
        onReject={handleRejectFromComparison}
        onSelectNode={handleSearchSelect}
        onViewDocument={handleViewDocument}
        username={authUsername}
      />
    </div>
    </CasePermissionProvider>
  );
}
