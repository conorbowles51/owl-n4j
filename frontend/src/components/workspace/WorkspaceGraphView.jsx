import React, { useEffect, useRef, useState, useMemo } from 'react';
import GraphView from '../GraphView';
import GraphTableView from '../GraphTableView';
import VisualInvestigationTimeline from './VisualInvestigationTimeline';
import TimelineView from '../timeline/TimelineView';
import MapView from '../MapView';
import ViewModeSwitcher from '../ViewModeSwitcher';
import GraphSearchFilter from '../GraphSearchFilter';
import { convertGraphNodesToTimelineEvents, convertGraphNodesToMapLocations, hasTimelineData, hasMapData } from '../../utils/graphDataConverter';

/**
 * Workspace Graph View Component
 * 
 * Enhanced graph view for workspace with risk scoring and workspace-specific features
 */
export default function WorkspaceGraphView({
  caseId,
  graphData,
  tableGraphData,
  onNodeSelect,
  selectedNode,
  theoryGraphKeys,
  theoryName,
  onClearTheoryFilter,
  tableScope,
  onTableScopeChange,
  viewMode: externalViewMode,
  onViewModeChange,
  tableViewState,
  onTableViewStateChange,
  graphSearchTerm,
  graphSearchFieldScope,
  onGraphFieldScopeChange,
  graphSearchMode,
  pendingGraphSearch,
  onGraphFilterChange,
  onGraphQueryChange,
  onGraphSearchExecute,
  onGraphModeChange,
  onTableNodeSelect,
  onUpdateNode = null,
  onNodeCreated = null,
  onGraphRefresh = null,
  onDeleteNodes = null,
}) {
  const tableData = tableGraphData ?? graphData;
  const graphViewRef = useRef();
  const containerRef = useRef();
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [internalViewMode, setInternalViewMode] = useState(externalViewMode || 'graph');
  
  // Use internal view mode if external is not provided
  const currentViewMode = externalViewMode !== undefined ? externalViewMode : internalViewMode;
  const handleViewModeChange = (newMode) => {
    console.log('ViewMode change requested:', newMode, 'externalViewMode:', externalViewMode, 'onViewModeChange:', !!onViewModeChange);
    if (onViewModeChange) {
      onViewModeChange(newMode);
    } else {
      setInternalViewMode(newMode);
    }
  };

  // Track container dimensions
  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        setDimensions({
          width: rect.width || containerRef.current.offsetWidth,
          height: rect.height || containerRef.current.offsetHeight,
        });
      }
    };

    // Initial measurement
    updateDimensions();

    // Update on resize
    const resizeObserver = new ResizeObserver(updateDimensions);
    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }

    return () => {
      resizeObserver.disconnect();
    };
  }, []);

  // Center graph when data loads and container is ready
  useEffect(() => {
    if (graphViewRef.current && graphData.nodes.length > 0 && dimensions.width > 0 && dimensions.height > 0) {
      // Wait for graph to render and simulation to settle
      const timeoutId = setTimeout(() => {
        if (graphViewRef.current && graphViewRef.current.centerGraph) {
          graphViewRef.current.centerGraph();
        }
      }, 800);
      
      return () => clearTimeout(timeoutId);
    }
  }, [graphData, dimensions]);

  // Check if timeline and map data are available from current graph nodes
  const hasTimeline = useMemo(() => hasTimelineData(graphData.nodes), [graphData.nodes]);
  const hasMap = useMemo(() => hasMapData(graphData.nodes), [graphData.nodes]);
  
  // Convert graph nodes to timeline events and map locations
  // Always compute these so they're ready when switching modes
  const timelineEvents = useMemo(() => {
    if (hasTimeline) {
      return convertGraphNodesToTimelineEvents(graphData.nodes, graphData.links);
    }
    return [];
  }, [hasTimeline, graphData.nodes, graphData.links]);
  
  const mapLocations = useMemo(() => {
    if (hasMap) {
      return convertGraphNodesToMapLocations(graphData.nodes, graphData.links);
    }
    return [];
  }, [hasMap, graphData.nodes, graphData.links]);

  return (
    <div ref={containerRef} className="h-full w-full flex flex-col relative">
      {/* View Mode Switcher Banner - fixed at top */}
      <div className="flex-shrink-0 bg-white border-b border-light-200 px-4 py-2 flex items-center justify-between gap-4">
        <ViewModeSwitcher
          mode={currentViewMode}
          onModeChange={handleViewModeChange}
          hasTimelineData={hasTimeline}
          hasMapData={hasMap}
        />
        {currentViewMode === 'table' && (
          <GraphSearchFilter
            mode={graphSearchMode || 'filter'}
            onModeChange={onGraphModeChange}
            onFilterChange={onGraphFilterChange}
            onQueryChange={onGraphQueryChange}
            onSearch={onGraphSearchExecute}
            placeholder="Filter table nodes..."
            disabled={false}
          />
        )}
        {theoryGraphKeys && theoryGraphKeys.length > 0 && currentViewMode !== 'timeline' && currentViewMode !== 'map' && (
          <div className="flex items-center gap-4">
            {currentViewMode === 'table' ? (
              <>
                <div className="text-sm text-owl-blue-900">
                  <span className="font-semibold">
                    {tableScope === 'theory' ? 'Theory Table' : 'Full Table'}
                    {theoryName ? ` (${theoryName})` : ''}
                    {':'}
                  </span>
                  {' '}
                  Showing {tableData.nodes.length} {tableScope === 'theory' ? 'theory-relevant' : ''} entities
                </div>
                <button
                  onClick={() => onTableScopeChange && onTableScopeChange(tableScope === 'theory' ? 'full' : 'theory')}
                  className="text-xs text-owl-blue-600 hover:text-owl-blue-800 underline"
                >
                  {tableScope === 'theory' ? 'Show full table' : `Show theory table${theoryName ? ` (${theoryName})` : ''}`}
                </button>
              </>
            ) : (
              <>
                <div className="text-sm text-owl-blue-900">
                  <span className="font-semibold">
                    Theory Graph{theoryName ? ` (${theoryName})` : ''}:
                  </span>
                  {' '}
                  Showing {graphData.nodes.length} relevant entities
                </div>
                <button
                  onClick={onClearTheoryFilter}
                  className="text-xs text-owl-blue-600 hover:text-owl-blue-800 underline"
                >
                  Show Full Graph
                </button>
              </>
            )}
          </div>
        )}
      </div>
      
      <div className="flex-1 min-h-0">
        {dimensions.width > 0 && dimensions.height > 0 && (
          <>
            {currentViewMode === 'timeline' ? (
              hasTimeline ? (
                <div className="h-full w-full">
                  <TimelineView
                    timelineData={timelineEvents}
                    onSelectEvent={(event) => {
                      // Find the node in graphData and select it
                      const node = graphData.nodes.find(n => n.key === event.key);
                      if (node && onNodeSelect) {
                        onNodeSelect(node);
                      }
                    }}
                  />
                </div>
              ) : (
                <div className="flex items-center justify-center h-full">
                  <p className="text-sm text-light-500">No timeline data available for visible nodes</p>
                </div>
              )
            ) : currentViewMode === 'map' ? (
              hasMap ? (
                <div className="h-full w-full">
                  <MapView
                    locations={mapLocations}
                    caseId={caseId}
                    onNodeClick={(location) => {
                      // Find the node in graphData and select it
                      const node = graphData.nodes.find(n => n.key === location.key);
                      if (node && onNodeSelect) {
                        onNodeSelect(node);
                      }
                    }}
                  />
                </div>
              ) : (
                <div className="flex items-center justify-center h-full">
                  <p className="text-sm text-light-500">No map data available for visible nodes</p>
                </div>
              )
            ) : currentViewMode === 'table' ? (
              <div className="h-full w-full flex flex-col min-h-0">
                <GraphTableView
                  key={`table-${tableScope}-${(theoryGraphKeys?.length ?? 0)}-${tableData?.nodes?.length ?? 0}-${tableData?.nodes?.map(n => n.key).sort().join(',') || ''}`}
                  graphData={tableData}
                  searchTerm={graphSearchTerm || ''}
                  onNodeClick={(node, panel, e) => {
                    if (onTableNodeSelect) {
                      onTableNodeSelect(node, panel, e);
                    } else if (onNodeSelect) {
                      onNodeSelect(node, e);
                    }
                  }}
                  selectedNodeKeys={selectedNode ? [selectedNode.key] : []}
                  tableViewState={tableViewState}
                  onTableViewStateChange={onTableViewStateChange}
                  caseId={caseId}
                  onUpdateNode={onUpdateNode}
                  onNodeCreated={onNodeCreated}
                  onGraphRefresh={onGraphRefresh}
                  onDeleteNodes={onDeleteNodes}
                />
              </div>
            ) : (
              <GraphView
                ref={graphViewRef}
                graphData={graphData}
                onNodeClick={onNodeSelect}
                selectedNodes={selectedNode ? [selectedNode] : []}
                selectedNode={selectedNode}
                caseId={caseId}
                width={dimensions.width}
                height={dimensions.height}
                showCenterButton={false}
                isSubgraph={true}
                viewMode={currentViewMode}
                onViewModeChange={handleViewModeChange}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
