import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { X, Users, Search, Download, Settings } from 'lucide-react';
import { workspaceAPI, casesAPI, graphAPI } from '../services/api';
import { parseSearchQuery, matchesQuery } from '../utils/searchParser';
import CaseContextPanel from './workspace/CaseContextPanel';
import WorkspaceGraphView from './workspace/WorkspaceGraphView';
import CaseHeaderBar from './workspace/CaseHeaderBar';
import SectionContentPanel from './workspace/SectionContentPanel';
import CaseOverviewView from './workspace/CaseOverviewView';
import VisualInvestigationTimeline from './workspace/VisualInvestigationTimeline';
import NodeDetails from './NodeDetails';

/**
 * WorkspaceView Component
 * 
 * Main workspace view for case investigation with:
 * - Case header bar
 * - Three-panel layout (Case Context, Graph, Investigation)
 * - Activity timeline at bottom
 */
export default function WorkspaceView({
  caseId,
  caseName,
  onBack,
  authUsername,
  onLogoClick,
}) {
  const [caseData, setCaseData] = useState(null);
  const [caseContext, setCaseContext] = useState(null);
  const [onlineUsers, setOnlineUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [fullGraphData, setFullGraphData] = useState({ nodes: [], links: [] }); // Store full graph for reset
  const [theoryGraphKeys, setTheoryGraphKeys] = useState(null); // Entity keys for theory graph filter
  const [theoryName, setTheoryName] = useState(null); // Name of the active theory (for banner display)
  const [tableScope, setTableScope] = useState('theory'); // 'theory' | 'full' – table shows theory-filtered or full graph
  const [selectedNode, setSelectedNode] = useState(null);
  const [viewMode, setViewMode] = useState('graph'); // 'graph', 'timeline', 'map', or 'table'
  const [tableViewState, setTableViewState] = useState(null); // Persisted table panels, filters, etc.
  const [selectedSection, setSelectedSection] = useState(null);
  const [rightPanelSourceInTableMode, setRightPanelSourceInTableMode] = useState('table-selection'); // 'section' | 'table-selection'
  const [graphSearchTerm, setGraphSearchTerm] = useState('');
  const [graphSearchFieldScope, setGraphSearchFieldScope] = useState('all'); // 'all' | 'selected'
  const [graphSearchMode, setGraphSearchMode] = useState('filter');
  const [pendingGraphSearch, setPendingGraphSearch] = useState('');
  const [selectedNodes, setSelectedNodes] = useState([]); // Array of node objects from table
  const [selectedNodesDetails, setSelectedNodesDetails] = useState([]); // Array of node details
  const loadNodeDetailsTimerRef = useRef(null);
  const [witnesses, setWitnesses] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [deadlines, setDeadlines] = useState([]);
  const [pinnedItems, setPinnedItems] = useState([]);

  // Load case data and context
  useEffect(() => {
    const loadData = async () => {
      if (!caseId) return;
      
      setLoading(true);
      try {
        // Load case metadata
        const caseInfo = await casesAPI.get(caseId);
        setCaseData(caseInfo);

        // Load case context
        const context = await workspaceAPI.getCaseContext(caseId);
        setCaseContext(context);

        // Load graph data
        const graph = await graphAPI.getGraph({ case_id: caseId });
        setGraphData(graph);
        setFullGraphData(graph); // Store full graph
        setTheoryGraphKeys(null); // Reset theory graph filter when case changes
        setTheoryName(null);
        setTableScope('theory');

        // Load presence
        const presence = await workspaceAPI.getPresence(caseId);
        setOnlineUsers(presence.online_users || []);

        // Load workspace data
        const [witnessesData, tasksData, deadlinesData, pinnedData] = await Promise.all([
          workspaceAPI.getWitnesses(caseId).catch(() => ({ witnesses: [] })),
          workspaceAPI.getTasks(caseId).catch(() => ({ tasks: [] })),
          workspaceAPI.getDeadlines(caseId).catch(() => ({ deadlines: [] })),
          workspaceAPI.getPinnedItems(caseId).catch(() => ({ pinned_items: [] })),
        ]);

        setWitnesses(witnessesData.witnesses || []);
        setTasks(tasksData.tasks || []);
        setDeadlines(deadlinesData.deadlines || []);
        setPinnedItems(pinnedData.pinned_items || []);
      } catch (err) {
        console.error('Failed to load workspace data:', err);
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [caseId]);

  // Refresh handlers
  const handleRefreshPinned = useCallback(async () => {
    try {
      const pinnedData = await workspaceAPI.getPinnedItems(caseId);
      setPinnedItems(pinnedData.pinned_items || []);
    } catch (err) {
      console.error('Failed to refresh pinned items:', err);
    }
  }, [caseId]);

  // Update case context
  const handleUpdateContext = useCallback(async (updates) => {
    try {
      const updated = await workspaceAPI.updateCaseContext(caseId, updates);
      setCaseContext(updated);
    } catch (err) {
      console.error('Failed to update case context:', err);
      throw err;
    }
  }, [caseId]);

  // Listen for theory graph built event
  useEffect(() => {
    const handleTheoryGraphBuilt = (event) => {
      const { entity_keys, theory_title } = event.detail;
      if (entity_keys && entity_keys.length > 0) {
        setTheoryGraphKeys(entity_keys);
        setTheoryName(theory_title ?? null);
      }
    };

    window.addEventListener('theory-graph-built', handleTheoryGraphBuilt);
    return () => {
      window.removeEventListener('theory-graph-built', handleTheoryGraphBuilt);
    };
  }, []);

  // Apply search filter to graph data
  const applyGraphFilter = useCallback((data, searchTerm) => {
    if (!searchTerm) {
      // If no search term, apply theory filter if active
      if (theoryGraphKeys && theoryGraphKeys.length > 0 && data.nodes.length > 0) {
        const keysSet = new Set(theoryGraphKeys);
        const filteredNodes = data.nodes.filter(node => keysSet.has(node.key));
        const filteredLinks = data.links.filter(link => {
          const sourceKey = typeof link.source === 'object' ? link.source?.key : link.source;
          const targetKey = typeof link.target === 'object' ? link.target?.key : link.target;
          return keysSet.has(sourceKey) && keysSet.has(targetKey);
        });
        setGraphData({ nodes: filteredNodes, links: filteredLinks });
      } else {
        setGraphData(data);
      }
      return;
    }

    // Parse the search query
    const queryAST = parseSearchQuery(searchTerm);
    
    // Filter nodes that match the query (allFields when scope is 'all')
    const searchOpts = { allFields: graphSearchFieldScope === 'all' };
    let matchingNodes = data.nodes.filter(node => matchesQuery(queryAST, node, searchOpts));
    
    // Apply theory filter on top of search if active
    if (theoryGraphKeys && theoryGraphKeys.length > 0) {
      const keysSet = new Set(theoryGraphKeys);
      matchingNodes = matchingNodes.filter(node => keysSet.has(node.key));
    }

    const matchingNodeKeys = new Set(matchingNodes.map(n => n.key));

    // Filter links to only include connections between matching nodes
    const matchingLinks = data.links.filter(link => {
      const sourceKey = typeof link.source === 'string' ? link.source : link.source.key;
      const targetKey = typeof link.target === 'string' ? link.target : link.target.key;
      return matchingNodeKeys.has(sourceKey) && matchingNodeKeys.has(targetKey);
    });

    setGraphData({ nodes: matchingNodes, links: matchingLinks });
  }, [theoryGraphKeys, graphSearchFieldScope]);

  // Filter graph when theory keys or search term changes
  useEffect(() => {
    if (fullGraphData.nodes.length > 0) {
      applyGraphFilter(fullGraphData, graphSearchTerm);
    }
  }, [theoryGraphKeys, fullGraphData, graphSearchTerm, applyGraphFilter]);

  // Reset graph when theory filter is cleared
  const handleClearTheoryFilter = useCallback(() => {
    setTheoryGraphKeys(null);
    setTheoryName(null);
    setTableScope('theory');
    // Reapply search filter if exists
    if (fullGraphData.nodes.length > 0) {
      applyGraphFilter(fullGraphData, graphSearchTerm);
    }
  }, [fullGraphData, graphSearchTerm, applyGraphFilter]);

  // Data for table: theory-filtered or full, then search-filtered when graphSearchTerm is set.
  const tableGraphData = useMemo(() => {
    let base;
    if (theoryGraphKeys && theoryGraphKeys.length > 0) {
      if (tableScope === 'full') {
        base = fullGraphData;
      } else {
        const keysSet = new Set(theoryGraphKeys);
        const nodes = fullGraphData.nodes.filter((n) => keysSet.has(n.key));
        const links = fullGraphData.links.filter((l) => {
          const sk = typeof l.source === 'object' ? l.source?.key : l.source;
          const tk = typeof l.target === 'object' ? l.target?.key : l.target;
          return keysSet.has(sk) && keysSet.has(tk);
        });
        base = { nodes, links };
      }
    } else {
      base = graphData;
    }
    const term = (graphSearchTerm || '').trim();
    if (!term || !base.nodes.length) return base;
    const queryAST = parseSearchQuery(term);
    const opts = { allFields: graphSearchFieldScope === 'all' };
    const matchingNodes = base.nodes.filter((n) => matchesQuery(queryAST, n, opts));
    const keys = new Set(matchingNodes.map((n) => n.key));
    const matchingLinks = base.links.filter((l) => {
      const sk = typeof l.source === 'object' ? l.source?.key : l.source;
      const tk = typeof l.target === 'object' ? l.target?.key : l.target;
      return keys.has(sk) && keys.has(tk);
    });
    return { nodes: matchingNodes, links: matchingLinks };
  }, [theoryGraphKeys, tableScope, fullGraphData, graphData, graphSearchTerm, graphSearchFieldScope]);

  // Whenever a theory is active (theory or full scope), don't restore panels so the table always builds
  // from current tableGraphData. Otherwise theory table would show full-data rows, or full table would
  // restore theory-only panels and still show only theory rows.
  const tableTableViewState = useMemo(() => {
    if (theoryGraphKeys?.length) {
      return { ...(tableViewState || {}), panels: [] };
    }
    return tableViewState;
  }, [theoryGraphKeys, tableViewState]);

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
        // Limit concurrent requests
        const BATCH_SIZE = 10;
        const details = [];
        
        for (let i = 0; i < keys.length; i += BATCH_SIZE) {
          const batch = keys.slice(i, i + BATCH_SIZE);
          const batchPromises = batch.map(key => graphAPI.getNodeDetails(key, caseId));
          const batchResults = await Promise.all(batchPromises);
          details.push(...batchResults);
        }
        
        setSelectedNodesDetails(details);
      } catch (err) {
        console.error('Failed to load node details:', err);
        setSelectedNodesDetails([]);
      }
    }, 100);
  }, [caseId]);

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

  // When in table mode, section focus from left menu shows section in right panel until user clicks a row again
  const handleSectionSelect = useCallback((section) => {
    setSelectedSection(section);
    if (viewMode === 'table') {
      setRightPanelSourceInTableMode('section');
    }
  }, [viewMode]);

  // Handle node selection from table view
  const handleTableNodeSelect = useCallback((node, panel, event) => {
    const isMultiSelect = event?.ctrlKey || event?.metaKey;
    
    if (viewMode === 'table') {
      setRightPanelSourceInTableMode('table-selection');
    }
    // Clear graph view selection when selecting in table view
    setSelectedNode(null);
    
    // If clicking a row in a relations table, include breadcrumb trail + clicked node
    const isRelationsPanel = panel?.type === 'relations' && panel?.breadcrumb?.length > 0;
    
    if (isRelationsPanel && !isMultiSelect) {
      const breadcrumbNodes = panel.breadcrumb
        .map((c) => graphData.nodes.find((n) => n.key === c.key))
        .filter(Boolean);
      // Order: clicked node first (most recent), then breadcrumb in reverse (most recent breadcrumb first)
      const nodesToShow = [
        ...(breadcrumbNodes.some((n) => n.key === node.key) ? [] : [node]),
        ...breadcrumbNodes.reverse(),
      ];
      const keysToLoad = nodesToShow.map((n) => n.key);
      setSelectedNodes(nodesToShow);
      loadNodeDetails(keysToLoad);
      return;
    }
    
    if (isMultiSelect) {
      setSelectedNodes((prev) => {
        const existingIndex = prev.findIndex(n => n.key === node.key);
        if (existingIndex >= 0) {
          const newSelection = prev.filter(n => n.key !== node.key);
          const newKeys = newSelection.map(n => n.key);
          if (newKeys.length > 0) {
            loadNodeDetails(newKeys);
          } else {
            setSelectedNodesDetails([]);
          }
          return newSelection;
        } else {
          const newSelection = [...prev, node];
          const newKeys = newSelection.map(n => n.key);
          loadNodeDetails(newKeys);
          return newSelection;
        }
      });
    } else {
      setSelectedNodes([node]);
      loadNodeDetails([node.key]);
    }
  }, [loadNodeDetails, graphData.nodes, viewMode]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-owl-blue-600 mx-auto mb-4"></div>
          <p className="text-light-600">Loading workspace...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-light-50">
      {/* Case Header Bar */}
      <CaseHeaderBar
        caseName={caseName || caseData?.name || 'Untitled Case'}
        caseId={caseId}
        caseType={caseData?.case_type}
        trialDate={caseContext?.trial_date}
        onlineUsers={onlineUsers}
        onBack={onBack}
        onLogoClick={onLogoClick}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Panel: Case Context */}
        <div className="w-80 border-r border-light-200 bg-white overflow-y-auto">
          <CaseContextPanel
            caseId={caseId}
            caseName={caseName || caseData?.name || 'Untitled Case'}
            caseContext={caseContext}
            onUpdateContext={handleUpdateContext}
            authUsername={authUsername}
            selectedSection={selectedSection}
            onSectionSelect={handleSectionSelect}
            pinnedItems={pinnedItems}
            onRefreshPinned={async () => {
              const data = await workspaceAPI.getPinnedItems(caseId);
              setPinnedItems(data.pinned_items || []);
            }}
          />
        </div>

        {/* Center/Right Panels */}
        {selectedSection === 'case-overview' ? (
          /* Case Overview Mode: Full width; CaseOverviewView handles toolbar + horizontal scroll */
          <div className="flex-1 overflow-hidden bg-white flex flex-col min-h-0">
            <CaseOverviewView
              caseId={caseId}
              caseName={caseName || caseData?.name || 'Untitled Case'}
              caseContext={caseContext}
              onUpdateContext={handleUpdateContext}
              authUsername={authUsername}
              witnesses={witnesses}
              tasks={tasks}
              deadlines={deadlines}
              pinnedItems={pinnedItems}
              graphData={graphData}
            />
          </div>
        ) : selectedSection === 'investigation-timeline' ? (
          /* Investigation Timeline Mode: Full width timeline */
          <div className="flex-1 overflow-hidden bg-white">
            <VisualInvestigationTimeline
              caseId={caseId}
              width={null}
              height={null}
            />
          </div>
        ) : (
          /* Normal Mode: Graph/Table + Section Content. Table view: 75/25 split; else 45/55 */
          <>
            {/* Center Panel: Graph / Table View */}
            <div
              className={`min-w-0 overflow-hidden border-r border-light-200 ${
                viewMode === 'table' ? 'flex-[0.75]' : 'flex-[0.45]'
              }`}
            >
              <WorkspaceGraphView
                caseId={caseId}
                graphData={graphData}
                tableGraphData={tableGraphData}
                onNodeSelect={setSelectedNode}
                selectedNode={selectedNode}
                theoryGraphKeys={theoryGraphKeys}
                theoryName={theoryName}
                onClearTheoryFilter={handleClearTheoryFilter}
                tableScope={tableScope}
                onTableScopeChange={setTableScope}
                viewMode={viewMode}
                onViewModeChange={setViewMode}
                tableViewState={tableTableViewState}
                onTableViewStateChange={setTableViewState}
                graphSearchTerm={graphSearchTerm}
                graphSearchFieldScope={graphSearchFieldScope}
                onGraphFieldScopeChange={setGraphSearchFieldScope}
                graphSearchMode={graphSearchMode}
                pendingGraphSearch={pendingGraphSearch}
                onGraphFilterChange={handleGraphFilterChange}
                onGraphQueryChange={handleGraphQueryChange}
                onGraphSearchExecute={handleGraphSearchExecute}
                onGraphModeChange={handleGraphModeChange}
                onTableNodeSelect={handleTableNodeSelect}
              />
            </div>

            {/* Right Panel: Section Content or Node Details. Narrow (25%) in table view, else 55% */}
            <div
              className={`min-w-0 border-l border-light-200 bg-white overflow-y-auto overflow-x-hidden ${
                viewMode === 'table' ? 'flex-[0.25]' : 'flex-[0.55]'
              }`}
            >
              {viewMode === 'table' && rightPanelSourceInTableMode === 'table-selection' && selectedNodesDetails.length > 0 ? (
                /* Show Node Details when in table view, user chose table selection, and has selected nodes */
                <div className="h-full flex flex-col overflow-hidden">
                  <div className="p-4 border-b border-light-200 flex items-center justify-between flex-shrink-0">
                    <h2 className="font-semibold text-owl-blue-900">
                      Selected ({selectedNodesDetails.length})
                    </h2>
                    <button
                      onClick={() => {
                        setSelectedNodes([]);
                        setSelectedNodesDetails([]);
                      }}
                      className="p-1.5 hover:bg-light-100 rounded transition-colors text-light-600 hover:text-light-800"
                      title="Clear selection"
                    >
                      <X className="w-4 h-4" />
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
                            if (newKeys.length > 0) {
                              loadNodeDetails(newKeys);
                            } else {
                              setSelectedNodesDetails([]);
                            }
                          }}
                          onSelectNode={(node) => {
                            // Find node in graphData and select it
                            const graphNode = graphData.nodes.find(n => n.key === node.key);
                            if (graphNode) {
                              setSelectedNode(graphNode);
                            }
                          }}
                          username={authUsername}
                          compact={selectedNodesDetails.length > 1}
                          caseId={caseId}
                          searchTerm={graphSearchTerm || ''}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                /* Show Section Content otherwise */
                <SectionContentPanel
                selectedSection={selectedSection}
                caseId={caseId}
                caseContext={caseContext}
                onUpdateContext={handleUpdateContext}
                authUsername={authUsername}
                witnesses={witnesses}
                tasks={tasks}
                deadlines={deadlines}
                pinnedItems={pinnedItems}
                onRefreshWitnesses={async () => {
                  const data = await workspaceAPI.getWitnesses(caseId);
                  setWitnesses(data.witnesses || []);
                }}
                onRefreshTasks={async () => {
                  const data = await workspaceAPI.getTasks(caseId);
                  setTasks(data.tasks || []);
                }}
                onRefreshDeadlines={async () => {
                  const data = await workspaceAPI.getDeadlines(caseId);
                  setDeadlines(data.deadlines || []);
                }}
                onRefreshPinned={async () => {
                  const data = await workspaceAPI.getPinnedItems(caseId);
                  setPinnedItems(data.pinned_items || []);
                }}
              />
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
