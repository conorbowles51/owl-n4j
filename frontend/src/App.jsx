import React, { useState, useEffect, useCallback } from 'react';
import { 
  Network, 
  MessageSquare, 
  RefreshCw, 
  Loader2,
  AlertCircle 
} from 'lucide-react';
import { graphAPI } from './services/api';
import GraphView from './components/GraphView';
import NodeDetails from './components/NodeDetails';
import ChatPanel from './components/ChatPanel';
import ContextMenu from './components/ContextMenu';
import SearchBar from './components/SearchBar';

/**
 * Main App Component
 */
export default function App() {
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

  // Calculate graph dimensions
  const sidebarWidth = nodeDetails ? 320 : 0;
  const chatWidth = isChatOpen ? 384 : 0;
  const graphWidth = dimensions.width - sidebarWidth - chatWidth;
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
          {graphData.nodes.length > 0 && (
            <span className="text-xs text-dark-400 bg-dark-700 px-2 py-1 rounded">
              {graphData.nodes.length} entities · {graphData.links.length} relationships
            </span>
          )}
        </div>

        <div className="flex items-center gap-4">
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
        {/* Graph area */}
        <div className="flex-1 relative">
          {isLoading && graphData.nodes.length === 0 ? (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="flex flex-col items-center gap-3">
                <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
                <span className="text-dark-400">Loading graph...</span>
              </div>
            </div>
          ) : error ? (
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
          ) : (
            <GraphView
              graphData={graphData}
              selectedNode={selectedNode}
              onNodeClick={handleNodeClick}
              onNodeRightClick={handleNodeRightClick}
              onBackgroundClick={handleBackgroundClick}
              width={graphWidth}
              height={graphHeight}
            />
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
