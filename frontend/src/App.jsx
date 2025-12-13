import React, { useState, useEffect, useCallback } from 'react';
import { 
  Network, 
  MessageSquare, 
  RefreshCw, 
  Loader2,
  AlertCircle,
  Calendar,
  Layout,
  X
} from 'lucide-react';
import { graphAPI } from './services/api';
import GraphView from './components/GraphView';
import NodeDetails from './components/NodeDetails';
import ChatPanel from './components/ChatPanel';
import ContextMenu from './components/ContextMenu';
import SearchBar from './components/SearchBar';
import TimelineView from './components/TimelineView';  

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

  // Selection state
  const [selectedNode, setSelectedNode] = useState(null);
  const [nodeDetails, setNodeDetails] = useState(null);

  // Context menu state
  const [contextMenu, setContextMenu] = useState(null);

  // Chat panel state
  const [isChatOpen, setIsChatOpen] = useState(false);

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

  // Load node details
  const loadNodeDetails = useCallback(async (key) => {
    try {
      const details = await graphAPI.getNodeDetails(key);
      setNodeDetails(details);
    } catch (err) {
      console.error('Failed to load node details:', err);
    }
  }, []);

  // Handle node click
  const handleNodeClick = useCallback((node) => {
    setSelectedNode(node);
    loadNodeDetails(node.key);
    setContextMenu(null);
  }, [loadNodeDetails]);

  // Handle node right-click
  const handleNodeRightClick = useCallback((node, event) => {
    setContextMenu({
      node,
      position: { x: event.clientX, y: event.clientY },
    });
  }, []);

  // Handle background click
  const handleBackgroundClick = useCallback(() => {
    setSelectedNode(null);
    setNodeDetails(null);
    setContextMenu(null);
  }, []);

  // Handle show details from context menu
  const handleShowDetails = useCallback((node) => {
    setSelectedNode(node);
    loadNodeDetails(node.key);
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

      setSelectedNode(node);
      loadNodeDetails(node.key);
    } catch (err) {
      console.error('Failed to expand node:', err);
    }
  }, [loadNodeDetails]);

  // Handle search select
  const handleSearchSelect = useCallback((key) => {
    const node = graphData.nodes.find((n) => n.key === key);
    if (node) {
      setSelectedNode(node);
      loadNodeDetails(key);
    }
  }, [graphData.nodes, loadNodeDetails]);

  // Close details panel
  const handleCloseDetails = useCallback(() => {
    setSelectedNode(null);
    setNodeDetails(null);
  }, []);

  // Handle timeline event click
  const handleTimelineEventClick = useCallback((event) => {
    // Events have the same structure as nodes for details
    setSelectedNode(event);
    loadNodeDetails(event.key);
  }, [loadNodeDetails]);

  // Calculate graph dimensions
  const sidebarWidth = nodeDetails ? 320 : 0;
  const chatWidth = isChatOpen ? 384 : 0;
  const availableWidth = dimensions.width - sidebarWidth - chatWidth;
  const graphWidth = paneViewMode === 'split' ? availableWidth / 2 : availableWidth;
  const graphHeight = dimensions.height - 64; // Subtract header height

  // Get selected nodes for chat context
  const selectedNodes = selectedNode && nodeDetails ? [nodeDetails] : [];

  return (
    <div className="h-screen w-screen bg-dark-900 flex flex-col overflow-hidden">
      {/* Header */}
      <header className="h-16 bg-dark-800 border-b border-dark-700 flex items-center justify-between px-4 flex-shrink-0">
        <div className="flex items-center gap-3">
          <Network className="w-6 h-6 text-cyan-400" />
          <h1 className="text-lg font-semibold text-dark-100">
            Investigation Console
          </h1>
          {graphData.nodes.length > 0 && viewMode === 'graph' && (
            <span className="text-xs text-dark-400 bg-dark-700 px-2 py-1 rounded">
              {graphData.nodes.length} entities · {graphData.links.length} relationships
            </span>
          )}
        </div>

        <div className="flex items-center gap-4">
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
                    selectedNode={selectedNode}
                    onNodeClick={handleNodeClick}
                    onNodeRightClick={handleNodeRightClick}
                    onBackgroundClick={handleBackgroundClick}
                    width={graphWidth}
                    height={graphHeight}
                  />
                </div>
                
                {/* Right Panel - Info/Details */}
                <div className="flex-1 flex flex-col items-center justify-center p-8 bg-dark-950">
                  <div className="flex flex-col items-center gap-4 text-center max-w-md">
                    <Network className="w-12 h-12 text-cyan-400/50" />
                    <div>
                      <h3 className="text-md font-medium text-dark-300 mb-2">
                        Graph View
                      </h3>
                      <p className="text-dark-500 text-sm">
                        {graphData.nodes.length} entities · {graphData.links.length} relationships
                      </p>
                    </div>
                    {selectedNode && (
                      <div className="mt-4 p-4 bg-dark-800 rounded-lg text-left w-full">
                        <h4 className="text-xs font-semibold text-dark-400 mb-2 uppercase">
                          Selected Node
                        </h4>
                        <p className="text-xs text-dark-300">{selectedNode.name || selectedNode.key}</p>
                        <p className="text-xs text-dark-500 mt-1">Type: {selectedNode.type}</p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              // Single pane graph view
              <GraphView
                graphData={graphData}
                selectedNode={selectedNode}
                onNodeClick={handleNodeClick}
                onNodeRightClick={handleNodeRightClick}
                onBackgroundClick={handleBackgroundClick}
                width={graphWidth}
                height={graphHeight}
              />
            )
          ) : (
            // Timeline View
            <TimelineView
              onSelectEvent={handleTimelineEventClick}
              selectedEvent={selectedNode}
            />
          )}

          {/* Floating Pane Toggle Button - always visible in graph view, positioned above Entity Types legend */}
          {viewMode === 'graph' && (
            <button
              onClick={() => setPaneViewMode(paneViewMode === 'split' ? 'single' : 'split')}
              className={`absolute bottom-32 left-4 px-3 py-2 rounded-lg text-xs transition-colors flex items-center gap-2 shadow-lg backdrop-blur-sm z-10 ${
                paneViewMode === 'split'
                  ? 'bg-cyan-600/90 hover:bg-cyan-500 text-white'
                  : 'bg-dark-800/90 hover:bg-dark-700 text-dark-200'
              }`}
              title={paneViewMode === 'split' ? 'Switch to single pane view' : 'Switch to split pane view'}
            >
              <Layout className="w-4 h-4" />
              {paneViewMode === 'split' ? 'Single Pane' : 'Split View'}
            </button>
          )}
        </div>

        {/* Node details sidebar */}
        {nodeDetails && (
          <NodeDetails
            node={nodeDetails}
            onClose={handleCloseDetails}
            onSelectNode={handleSearchSelect}
          />
        )}

        {/* Chat panel */}
        {isChatOpen && (
          <ChatPanel
            isOpen={isChatOpen}
            onToggle={() => setIsChatOpen(!isChatOpen)}
            onClose={() => setIsChatOpen(false)}
            selectedNodes={selectedNodes}
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
    </div>
  );
}
