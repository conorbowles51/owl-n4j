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
  Archive
} from 'lucide-react';
import { graphAPI, artifactsAPI, timelineAPI } from './services/api';
import GraphView from './components/GraphView';
import NodeDetails from './components/NodeDetails';
import ChatPanel from './components/ChatPanel';
import ContextMenu from './components/ContextMenu';
import SearchBar from './components/SearchBar';
import TimelineView from './components/TimelineView';
import ArtifactModal from './components/ArtifactModal';
import ArtifactList from './components/ArtifactList';
import { exportArtifactToPDF } from './utils/pdfExport';  

/**
 * Main App Component
 */
export default function App() {
  // View mode state
  const [viewMode, setViewMode] = useState('graph'); // 'graph' or 'timeline'
  // Graph state
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  // Selection state - support multiple nodes
  const [selectedNodes, setSelectedNodes] = useState([]); // Array of node objects
  const [selectedNodesDetails, setSelectedNodesDetails] = useState([]); // Array of node details

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

  // Pane view state (single or split)
  const [paneViewMode, setPaneViewMode] = useState('single'); // 'single' or 'split'

  // Dimensions
  const [dimensions, setDimensions] = useState({
    width: window.innerWidth,
    height: window.innerHeight,
  });

  // Load graph data
  const loadGraph = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await graphAPI.getGraph();
      setGraphData(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

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
    setContextMenu(null);
  }, [loadNodeDetails]);

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
    }
  }, [graphData.nodes, loadNodeDetails]);

  // Close details panel
  const handleCloseDetails = useCallback(() => {
    setSelectedNodes([]);
    setSelectedNodesDetails([]);
  }, []);

  // Handle timeline event click
  const handleTimelineEventClick = useCallback((event) => {
    // Events have the same structure as nodes for details
    setSelectedNodes([event]);
    loadNodeDetails([event.key]);
  }, [loadNodeDetails]);

  // Build subgraph from selected nodes
  const buildSubgraph = useCallback((selectedNodeKeys) => {
    if (selectedNodeKeys.length === 0) {
      return { nodes: [], links: [] };
    }

    // Get all selected nodes
    const subgraphNodes = graphData.nodes.filter(node => 
      selectedNodeKeys.includes(node.key)
    );

    // Get all links between selected nodes
    const subgraphLinks = graphData.links.filter(link => {
      const sourceKey = typeof link.source === 'object' ? link.source.key : link.source;
      const targetKey = typeof link.target === 'object' ? link.target.key : link.target;
      return selectedNodeKeys.includes(sourceKey) && selectedNodeKeys.includes(targetKey);
    });

    return { nodes: subgraphNodes, links: subgraphLinks };
  }, [graphData]);

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
  
  // Build subgraph for selected nodes
  const subgraphData = buildSubgraph(selectedNodeKeys);

  // Load timeline - from subgraph when nodes are selected, from main graph when not
  const [timelineData, setTimelineData] = useState([]);
  useEffect(() => {
    const loadTimeline = async () => {
      try {
        const response = await timelineAPI.getEvents({});
        // Handle both array response and object with events property
        const events = Array.isArray(response) ? response : (response?.events || []);
        
        // Ensure events is an array
        if (!Array.isArray(events)) {
          console.warn('Timeline API returned non-array data:', response);
          setTimelineData([]);
          return;
        }

        if (selectedNodeKeys.length > 0) {
          // Filter events related to selected nodes (subgraph timeline)
          // Timeline events have a 'connections' array with connected entity keys
          console.log('🔍 Filtering timeline for subgraph:', {
            selectedNodeKeys,
            selectedNodeKeysCount: selectedNodeKeys.length,
            totalEvents: events.length,
            sampleEvent: events[0]
          });
          
          // Create a Set for faster lookup
          const selectedKeysSet = new Set(selectedNodeKeys);
          
          const filteredEvents = events.filter(event => {
            // Check if the event itself is in the selected nodes
            if (selectedKeysSet.has(event.key)) {
              console.log('✅ Event matches by key:', event.key);
              return true;
            }
            
            // Check if event is connected to any selected nodes via connections array
            if (event.connections && Array.isArray(event.connections)) {
              const matchingConnections = event.connections.filter(conn => 
                conn.key && selectedKeysSet.has(conn.key)
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
            selectedNodeKeys: Array.from(selectedKeysSet)
          });
          
          setTimelineData(filteredEvents);
        } else {
          // No subgraph selected - show all events from main graph
          console.log('📅 Showing all timeline events (no subgraph):', events.length);
          setTimelineData(events);
        }
      } catch (err) {
        console.error('Failed to load timeline:', err);
        setTimelineData([]);
      }
    };
    loadTimeline();
  }, [selectedNodeKeys]);

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
    if (selectedNodeKeys.length === 0) {
      alert('Please select nodes to export as PDF');
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
        // Check if this is a user message with selected nodes matching our selection
        if (msg.role === 'user' && msg.selectedNodes) {
          const isRelevant = msg.selectedNodes.some(key => selectedNodeKeys.includes(key));
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
  }, [selectedNodeKeys, subgraphData, timelineData, selectedNodesDetails, chatHistory]);

  // Save artifact
  const handleSaveArtifact = useCallback(async (name, notes) => {
    if (selectedNodeKeys.length === 0) {
      alert('Please select nodes to save as an artifact');
      return;
    }

    try {
      // Filter chat history to include both user questions and AI responses
      // Find relevant conversation pairs (user question + AI response)
      const relevantChatHistory = [];
      for (let i = 0; i < chatHistory.length; i++) {
        const msg = chatHistory[i];
        // Check if this is a user message with selected nodes matching our selection
        if (msg.role === 'user' && msg.selectedNodes) {
          const isRelevant = msg.selectedNodes.some(key => selectedNodeKeys.includes(key));
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
  }, [selectedNodeKeys, subgraphData, timelineData, selectedNodesDetails, chatHistory]);

  return (
    <div className="h-screen w-screen bg-dark-900 flex flex-col overflow-hidden">
      {/* Header */}
      <header className="h-16 bg-dark-800 border-b border-dark-700 flex items-center justify-between px-4 flex-shrink-0">
        <div className="flex items-center gap-3">
          <Network className="w-6 h-6 text-cyan-400" />
          <h1 className="text-lg font-semibold text-dark-100">
            Investigation Console
          </h1>
          {viewMode === 'graph' && (
            <span className="text-xs text-dark-400 bg-dark-700 px-2 py-1 rounded">
              {selectedNodes.length > 0 
                ? `${subgraphData.nodes.length} selected · ${subgraphData.links.length} connections`
                : `${graphData.nodes.length} entities · ${graphData.links.length} relationships`
              }
            </span>
          )}
        </div>

        <div className="flex items-center gap-4">
          {/* Save Artifact Button */}
          {viewMode === 'graph' && selectedNodeKeys.length > 0 && (
            <button
              onClick={() => setShowArtifactModal(true)}
              className="flex items-center gap-2 px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white rounded-md text-sm transition-colors"
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
                ? 'bg-dark-700 text-dark-100'
                : 'text-dark-400 hover:text-dark-200'
            }`}
            title="View saved artifacts"
          >
            <Archive className="w-4 h-4" />
            Artifacts
          </button>

          {/* View Toggle */}
          <div className="flex items-center bg-dark-900 rounded-lg p-1">
            <button
              onClick={() => setViewMode('graph')}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors ${
                viewMode === 'graph'
                  ? 'bg-dark-700 text-dark-100'
                  : 'text-dark-400 hover:text-dark-200'
              }`}
            >
              <Network className="w-4 h-4" />
              Graph
            </button>
            <button
              onClick={() => setViewMode('timeline')}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors ${
                viewMode === 'timeline'
                  ? 'bg-dark-700 text-dark-100'
                  : 'text-dark-400 hover:text-dark-200'
              }`}
            >
              <Calendar className="w-4 h-4" />
              Timeline
            </button>
          </div>

          <SearchBar onSelectNode={handleSearchSelect} />
          
          <button
            onClick={loadGraph}
            disabled={isLoading}
            className="p-2 hover:bg-dark-700 rounded-lg transition-colors disabled:opacity-50"
            title="Refresh graph"
          >
            <RefreshCw className={`w-5 h-5 text-dark-300 ${isLoading ? 'animate-spin' : ''}`} />
          </button>

          <button
            onClick={() => setIsChatOpen(!isChatOpen)}
            className={`p-2 rounded-lg transition-colors ${
              isChatOpen 
                ? 'bg-cyan-600 text-white' 
                : 'hover:bg-dark-700 text-dark-300'
            }`}
            title="Toggle AI Chat"
          >
            <MessageSquare className="w-5 h-5" />
          </button>
        </div>
      </header>

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Main view area */}
        <div className="flex-1 relative">
          {viewMode === 'graph' ? (
            // Graph View
            isLoading && graphData.nodes.length === 0 ? (
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="flex flex-col items-center gap-3">
                  <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
                  <span className="text-dark-400">Loading graph...</span>
                </div>
              </div>
            ) : error ? (
              paneViewMode === 'split' ? (
                // Split panel error view
                <div className="absolute inset-0 flex">
                  {/* Left Panel - Error Details */}
                  <div className="flex-1 flex flex-col items-center justify-center border-r border-dark-700 p-8">
                    <div className="flex flex-col items-center gap-4 text-center max-w-md">
                      <AlertCircle className="w-12 h-12 text-red-400" />
                      <div>
                        <h2 className="text-lg font-semibold text-dark-200 mb-2">
                          Failed to load graph
                        </h2>
                        <p className="text-dark-400 text-sm mb-4">{error}</p>
                      </div>
                      <button
                        onClick={loadGraph}
                        className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 rounded-lg text-sm text-white transition-colors"
                      >
                        Retry
                      </button>
                    </div>
                  </div>
                  
                  {/* Right Panel - Fallback/Info */}
                  <div className="flex-1 flex flex-col items-center justify-center p-8 bg-dark-950">
                    <div className="flex flex-col items-center gap-4 text-center max-w-md">
                      <Network className="w-12 h-12 text-dark-600" />
                      <div>
                        <h3 className="text-md font-medium text-dark-300 mb-2">
                          Graph Unavailable
                        </h3>
                        <p className="text-dark-500 text-sm">
                          The graph data could not be loaded. Please check your connection
                          and ensure the backend API is running.
                        </p>
                      </div>
                      <div className="mt-4 p-4 bg-dark-800 rounded-lg text-left w-full">
                        <h4 className="text-xs font-semibold text-dark-400 mb-2 uppercase">
                          Troubleshooting
                        </h4>
                        <ul className="text-xs text-dark-500 space-y-1">
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
                    <AlertCircle className="w-8 h-8 text-red-400" />
                    <span className="text-dark-200">Failed to load graph</span>
                    <span className="text-dark-400 text-sm">{error}</span>
                    <button
                      onClick={loadGraph}
                      className="mt-2 px-4 py-2 bg-dark-700 hover:bg-dark-600 rounded-lg text-sm text-dark-200 transition-colors"
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
                <div className="flex-1 relative border-r border-dark-700">
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
                  />
                </div>
                
                {/* Right Panel - Subgraph View */}
                <div className="flex-1 relative bg-dark-950 overflow-hidden" data-subgraph-container>
                  {selectedNodesDetails.length > 0 ? (
                    // Show subgraph of selected nodes
                    <>
                      <div className="absolute top-4 left-4 right-4 z-10 flex items-center justify-between bg-dark-800/90 rounded-lg p-2 px-3">
                        <div className="flex items-center gap-2">
                          <Network className="w-4 h-4 text-cyan-400" />
                          <h3 className="text-sm font-semibold text-dark-100">
                            Subgraph ({subgraphData.nodes.length} nodes, {subgraphData.links.length} links)
                          </h3>
                        </div>
                        <button
                          onClick={handleCloseDetails}
                          className="p-1 hover:bg-dark-700 rounded transition-colors"
                          title="Clear selection"
                        >
                          <X className="w-4 h-4 text-dark-400" />
                        </button>
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
                        <Network className="w-12 h-12 text-cyan-400/50" />
                        <div>
                          <h3 className="text-md font-medium text-dark-300 mb-2">
                            Subgraph View
                          </h3>
                          <p className="text-dark-500 text-sm">
                            Select nodes in the main graph to view their subgraph here.
                          </p>
                        </div>
                        <div className="mt-4 p-4 bg-dark-800 rounded-lg text-left w-full">
                          <p className="text-xs text-dark-400 mb-2">
                            Click on nodes in the left graph to select them.
                          </p>
                          <p className="text-xs text-dark-500">
                            Hold <kbd className="px-1.5 py-0.5 bg-dark-700 rounded text-xs">Ctrl</kbd> or <kbd className="px-1.5 py-0.5 bg-dark-700 rounded text-xs">Cmd</kbd> to select multiple nodes.
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
              />
            )
          ) : (
            // Timeline View - only show if there are timeline events
            timelineData.length > 0 ? (
              <TimelineView
                onSelectEvent={handleTimelineEventClick}
                selectedEvent={selectedNodes.length > 0 ? selectedNodes[0] : null}
                selectedNodeKeys={selectedNodeKeys}
                timelineData={timelineData}
              />
            ) : (
              <div className="h-full flex items-center justify-center bg-dark-950">
                <div className="flex flex-col items-center gap-3 text-center">
                  <Calendar className="w-12 h-12 text-dark-600" />
                  <span className="text-dark-200">No timeline events available</span>
                  <span className="text-dark-400 text-sm">
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
          <div className="w-80 bg-dark-800 border-l border-dark-700 h-full flex flex-col overflow-hidden">
            <div className="p-4 border-b border-dark-700 flex items-center justify-between flex-shrink-0">
              <h2 className="font-semibold text-dark-100">
                Selected ({selectedNodesDetails.length})
              </h2>
              <button
                onClick={handleCloseDetails}
                className="p-1 hover:bg-dark-700 rounded transition-colors"
              >
                <X className="w-5 h-5 text-dark-400" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto">
              {selectedNodesDetails.map((node, idx) => (
                <div key={node.key} className={idx > 0 ? "border-t border-dark-700" : ""}>
                  <NodeDetails
                    node={node}
                    onClose={() => {
                      const newSelection = selectedNodes.filter(n => n.key !== node.key);
                      setSelectedNodes(newSelection);
                      if (newSelection.length > 0) {
                        loadNodeDetails(newSelection.map(n => n.key));
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
          // Load artifact into subgraph (right pane) by setting selected nodes
          // This will automatically build the subgraph in the right pane
          if (artifact.subgraph && artifact.subgraph.nodes) {
            // Ensure split view is enabled to show the subgraph
            if (paneViewMode !== 'split') {
              setPaneViewMode('split');
            }
            
            // Set selected nodes to artifact's subgraph nodes
            // The subgraph will be built automatically from these nodes
            const artifactNodes = artifact.subgraph.nodes;
            setSelectedNodes(artifactNodes);
            
            // Load node details for the selected nodes (for the overview panel)
            const nodeKeys = artifactNodes.map(n => n.key);
            await loadNodeDetails(nodeKeys);
            
            // Timeline will be loaded automatically by the useEffect when selectedNodes changes
            // But if artifact has saved timeline data, we could use it here if needed
            
            setShowArtifactList(false);
          }
        }}
      />
    </div>
  );
}
