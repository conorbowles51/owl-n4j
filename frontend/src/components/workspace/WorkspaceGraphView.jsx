import React, { useEffect, useRef, useState, useMemo } from 'react';
import GraphView from '../GraphView';
import VisualInvestigationTimeline from './VisualInvestigationTimeline';
import TimelineView from '../timeline/TimelineView';
import MapView from '../MapView';
import ViewModeSwitcher from '../ViewModeSwitcher';
import { convertGraphNodesToTimelineEvents, convertGraphNodesToMapLocations, hasTimelineData, hasMapData } from '../../utils/graphDataConverter';

/**
 * Workspace Graph View Component
 * 
 * Enhanced graph view for workspace with risk scoring and workspace-specific features
 */
export default function WorkspaceGraphView({
  caseId,
  graphData,
  onNodeSelect,
  selectedNode,
  theoryGraphKeys,
  onClearTheoryFilter,
  viewMode: externalViewMode,
  onViewModeChange,
}) {
  const graphViewRef = useRef();
  const containerRef = useRef();
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [internalViewMode, setInternalViewMode] = useState(externalViewMode || 'graph');
  
  // Use internal view mode if external is not provided
  const currentViewMode = externalViewMode || internalViewMode;
  const handleViewModeChange = onViewModeChange || setInternalViewMode;

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
  const timelineEvents = useMemo(() => {
    if (currentViewMode === 'timeline' && hasTimeline) {
      return convertGraphNodesToTimelineEvents(graphData.nodes, graphData.links);
    }
    return [];
  }, [currentViewMode, hasTimeline, graphData.nodes, graphData.links]);
  
  const mapLocations = useMemo(() => {
    if (currentViewMode === 'map' && hasMap) {
      return convertGraphNodesToMapLocations(graphData.nodes, graphData.links);
    }
    return [];
  }, [currentViewMode, hasMap, graphData.nodes, graphData.links]);

  return (
    <div ref={containerRef} className="h-full w-full flex flex-col relative">
      {/* View Mode Switcher - positioned in viewport */}
      <div className="absolute top-4 left-4 z-30">
        <ViewModeSwitcher
          mode={currentViewMode}
          onModeChange={handleViewModeChange}
          hasTimelineData={hasTimeline}
          hasMapData={hasMap}
        />
      </div>
      
      {theoryGraphKeys && theoryGraphKeys.length > 0 && currentViewMode !== 'timeline' && currentViewMode !== 'map' && (
        <div className="bg-owl-blue-50 border-b border-owl-blue-200 px-4 py-2 flex items-center justify-between flex-shrink-0">
          <div className="text-sm text-owl-blue-900">
            <span className="font-semibold">Theory Graph Mode:</span> Showing {graphData.nodes.length} relevant entities
          </div>
          <button
            onClick={onClearTheoryFilter}
            className="text-xs text-owl-blue-600 hover:text-owl-blue-800 underline"
          >
            Show Full Graph
          </button>
        </div>
      )}
      <div className="flex-1 min-h-0">
        {dimensions.width > 0 && dimensions.height > 0 && (
          <>
            {currentViewMode === 'timeline' ? (
              hasTimeline ? (
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
              ) : (
                <div className="flex items-center justify-center h-full">
                  <p className="text-sm text-light-500">No timeline data available for visible nodes</p>
                </div>
              )
            ) : currentViewMode === 'map' ? (
              hasMap ? (
                <MapView
                  locations={mapLocations}
                  onNodeClick={(location) => {
                    // Find the node in graphData and select it
                    const node = graphData.nodes.find(n => n.key === location.key);
                    if (node && onNodeSelect) {
                      onNodeSelect(node);
                    }
                  }}
                />
              ) : (
                <div className="flex items-center justify-center h-full">
                  <p className="text-sm text-light-500">No map data available for visible nodes</p>
                </div>
              )
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
