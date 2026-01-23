import React, { useRef, useCallback, useEffect, useState, useMemo, useImperativeHandle, forwardRef } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { Settings, MousePointer, Square, Maximize2, Layout, ChevronLeft, ChevronRight, Plus, ChevronDown, ChevronUp, Target, Search } from "lucide-react";
import { graphAPI, profilesAPI } from '../services/api';
import TimelineView from './timeline/TimelineView';
import MapView from './MapView';
import { convertGraphNodesToTimelineEvents, convertGraphNodesToMapLocations, hasTimelineData, hasMapData } from '../utils/graphDataConverter';
/**
 * Color palette for entity types
 */
const TYPE_COLORS = {
  Person: '#ef4444',       // red
  Company: '#3b82f6',      // blue
  Account: '#22c55e',      // green
  Bank: '#f59e0b',         // amber
  Organisation: '#8b5cf6', // violet
  Transaction: '#06b6d4',  // cyan
  Location: '#ec4899',     // pink
  Document: '#64748b',     // slate
  Transfer: '#14b8a6',     // teal
  Payment: '#84cc16',      // lime
  Email: '#f97316',        // orange
  PhoneCall: '#a855f7',    // purple
  Meeting: '#eab308',      // yellow
  Other: '#6b7280',        // gray
};

/**
 * Generate a deterministic color for an entity type based on its name
 */
function generateColorForType(type) {
  if (!type) return TYPE_COLORS.Other;
  
  // Use a simple hash function to generate a consistent color
  let hash = 0;
  for (let i = 0; i < type.length; i++) {
    hash = type.charCodeAt(i) + ((hash << 5) - hash);
  }
  
  // Use a palette of distinct colors
  const colors = [
    '#ef4444', '#3b82f6', '#22c55e', '#f59e0b', '#8b5cf6',
    '#06b6d4', '#ec4899', '#64748b', '#14b8a6', '#84cc16',
    '#f97316', '#a855f7', '#eab308', '#10b981', '#6366f1',
    '#ec4899', '#14b8a6', '#f43f5e', '#0ea5e9', '#22c55e',
  ];
  
  return colors[Math.abs(hash) % colors.length];
}

/**
 * Get color for entity type
 * Uses profile colors if available, otherwise falls back to predefined or generated colors
 */
function getNodeColor(type, profileColors = {}) {
  if (!type) return TYPE_COLORS.Other;
  
  // First check profile colors
  if (profileColors[type]) {
    return profileColors[type];
  }
  
  // Then check predefined colors
  if (TYPE_COLORS[type]) {
    return TYPE_COLORS[type];
  }
  
  // Finally generate a color
  return generateColorForType(type);
}

/**
 * Get color for community (for Louvain algorithm)
 * Uses a color palette that's distinct from entity type colors
 */
const COMMUNITY_COLORS = [
  '#8b5cf6', // violet
  '#3b82f6', // blue
  '#22c55e', // green
  '#f59e0b', // amber
  '#ef4444', // red
  '#06b6d4', // cyan
  '#ec4899', // pink
  '#14b8a6', // teal
  '#84cc16', // lime
  '#f97316', // orange
  '#a855f7', // purple
  '#eab308', // yellow
];

function getCommunityColor(communityId) {
  if (communityId === null || communityId === undefined) {
    return null;
  }
  return COMMUNITY_COLORS[communityId % COMMUNITY_COLORS.length];
}

/**
 * GraphView Component
 * 
 * Renders the force-directed graph visualization
 */
const GraphView = forwardRef(function GraphView({
  graphData,
  selectedNodes = [],
  onNodeClick,
  onBulkNodeSelect, // New prop for bulk selection
  onNodeRightClick,
  onNodeDoubleClick, // Callback for double-clicking a node
  onBackgroundClick,
  width,
  height,
  showCenterButton = true, // Show center button by default
  paneViewMode, // 'single' or 'split'
  onPaneViewModeChange, // Callback to change pane view mode
  isSubgraph = false, // Whether this is the subgraph view
  onAddToSubgraph, // Callback to add selected nodes to subgraph
  onRemoveFromSubgraph, // Callback to remove selected nodes from subgraph
  subgraphNodeKeys = [], // Keys of nodes currently in the subgraph
  onAddNode, // Callback to open Add Node modal
  onFindSimilarEntities, // Callback to find similar entities
  isScanningSimilar = false, // Whether similar entities scan is in progress
  caseId, // REQUIRED: Case ID for case-specific data
  viewMode: externalViewMode, // External view mode control
  onViewModeChange, // Callback when view mode changes
}, ref) {
  const graphRef = useRef();
  const containerRef = useRef();
  const isDraggingRef = useRef(false); // Ref to track dragging state synchronously
  const [hoveredNode, setHoveredNode] = useState(null);
  const [modifierKeys, setModifierKeys] = useState({ ctrl: false, meta: false });
  const [selectedEntityTypes, setSelectedEntityTypes] = useState(new Set()); // Track selected entity types
  const [allEntityTypes, setAllEntityTypes] = useState([]); // All entity types from database
  const [profileColors, setProfileColors] = useState({}); // Entity type colors from profile
  const [isLegendMinimized, setIsLegendMinimized] = useState(true); // Track if legend is minimized - default to minimized
  
  // View mode state
  const [internalViewMode, setInternalViewMode] = useState('graph');
  const viewMode = externalViewMode !== undefined ? externalViewMode : internalViewMode;
  const setViewMode = onViewModeChange || setInternalViewMode;

  // Selection mode: 'click' or 'drag'
  const [selectionMode, setSelectionMode] = useState('click');

  // Drag selection state
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState(null);
  const [dragEnd, setDragEnd] = useState(null);
  const [fixedSelectionBox, setFixedSelectionBox] = useState(null); // Selection box that stays after mouseUp

  // Force simulation controls
  // Use tighter clustering for subgraphs (Spotlight and Result graphs)
  const [showControls, setShowControls] = useState(false);
  const [linkDistance, setLinkDistance] = useState(isSubgraph ? 120 : 200);
  // Reduce repulsion for main graph to nearly nothing so clusters stay close together
  const [chargeStrength, setChargeStrength] = useState(isSubgraph ? -800 : -50);
  // Stronger center force for main graph to bring disconnected clusters closer together
  const [centerStrength, setCenterStrength] = useState(isSubgraph ? 0.15 : 0.4);

  // Relationship labels toggle (independent per graph instance)
  // Default to ON for spotlight and result graphs
  const [showRelationshipLabels, setShowRelationshipLabels] = useState(isSubgraph ? true : false);

  // Track modifier keys (Ctrl/Cmd)
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Check for Ctrl (Windows/Linux) or Cmd (Mac)
      if (e.key === 'Control' || e.ctrlKey) {
        setModifierKeys(prev => ({ ...prev, ctrl: true }));
      }
      if (e.key === 'Meta' || e.metaKey) {
        setModifierKeys(prev => ({ ...prev, meta: true }));
      }
    };
    
    const handleKeyUp = (e) => {
      // Reset when modifier key is released
      if (e.key === 'Control') {
        setModifierKeys(prev => ({ ...prev, ctrl: false }));
      }
      if (e.key === 'Meta') {
        setModifierKeys(prev => ({ ...prev, meta: false }));
      }
      // Also check if modifier is no longer pressed
      if (!e.ctrlKey) {
        setModifierKeys(prev => ({ ...prev, ctrl: false }));
      }
      if (!e.metaKey) {
        setModifierKeys(prev => ({ ...prev, meta: false }));
      }
    };

    // Also track mouse events to catch modifier state
    const handleMouseDown = (e) => {
      if (e.ctrlKey) setModifierKeys(prev => ({ ...prev, ctrl: true }));
      if (e.metaKey) setModifierKeys(prev => ({ ...prev, meta: true }));
    };

    const handleMouseUp = (e) => {
      if (!e.ctrlKey) setModifierKeys(prev => ({ ...prev, ctrl: false }));
      if (!e.metaKey) setModifierKeys(prev => ({ ...prev, meta: false }));
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    window.addEventListener('mousedown', handleMouseDown);
    window.addEventListener('mouseup', handleMouseUp);
    
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
      window.removeEventListener('mousedown', handleMouseDown);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  // Center graph function
  const centerGraph = useCallback(() => {
    if (graphRef.current && graphData.nodes.length > 0 && containerRef.current) {
      // Wait for container to have dimensions and simulation to settle
      const checkAndCenter = () => {
        if (!graphRef.current || !containerRef.current) return;
        
        const container = containerRef.current;
        const containerWidth = container.offsetWidth || container.clientWidth;
        const containerHeight = container.offsetHeight || container.clientHeight;
        
        // Only center if container has valid dimensions
        if (containerWidth > 0 && containerHeight > 0) {
          // Use zoomToFit with proper padding to center nodes in viewport
          // The padding values ensure nodes are centered within the visible area
          graphRef.current.zoomToFit(400, 50);
        } else {
          // Retry if container doesn't have dimensions yet
          setTimeout(checkAndCenter, 100);
        }
      };
      
      // Initial delay for simulation to settle
      setTimeout(checkAndCenter, 200);
    }
  }, [graphData]);

  // Center graph on specific nodes
  const centerOnNodes = useCallback((nodeKeys) => {
    if (!graphRef.current || !nodeKeys || nodeKeys.length === 0) return;
    
    // Find the nodes in the graph data
    const nodesToCenter = graphData.nodes.filter(node => nodeKeys.includes(node.key));
    if (nodesToCenter.length === 0) return;
    
    // Wait a bit for the simulation to settle, then use zoomToFit with a filter
    setTimeout(() => {
      if (!graphRef.current) return;
      
      // Use zoomToFit with a custom filter to only fit the selected nodes
      // This properly centers and fits the nodes in the viewport
      graphRef.current.zoomToFit(400, 50, (node) => {
        return nodeKeys.includes(node.key);
      });
    }, 100);
  }, [graphData]);

  // Handle center button click - center on selected nodes if any, otherwise center whole graph
  const handleCenterClick = useCallback(() => {
    if (selectedNodes && selectedNodes.length > 0) {
      const nodeKeys = selectedNodes.map(n => n.key);
      centerOnNodes(nodeKeys);
    } else {
      centerGraph();
    }
  }, [selectedNodes, centerOnNodes, centerGraph]);

  // Get graph canvas for PDF export
  const getGraphCanvas = useCallback(() => {
    if (containerRef.current) {
      // Find the canvas element within the container
      const canvas = containerRef.current.querySelector('canvas');
      return canvas || null;
    }
    return null;
  }, []);

  // Expose centerGraph, centerOnNodes, getGraphCanvas, and control methods via ref
  useImperativeHandle(ref, () => ({
    centerGraph,
    centerOnNodes,
    getGraphCanvas,
    setSelectionMode,
    selectionMode,
    setShowControls,
    showControls,
  }), [centerGraph, centerOnNodes, getGraphCanvas, setSelectionMode, selectionMode, setShowControls, showControls]);

  // Center graph on mount - only when graphData changes, not when centerGraph changes
  useEffect(() => {
    if (graphRef.current && graphData.nodes.length > 0) {
      const timeoutId = setTimeout(() => {
        if (graphRef.current) {
          graphRef.current.zoomToFit(400, 50);
        }
      }, 500);
      return () => clearTimeout(timeoutId);
    }
  }, [graphData]); // Remove centerGraph from dependencies to avoid loop

  // Apply force simulation settings
  useEffect(() => {
    if (graphRef.current) {
      const fg = graphRef.current;
      
      const linkForce = fg.d3Force('link');
      if (linkForce) linkForce.distance(linkDistance);
      
      const chargeForce = fg.d3Force('charge');
      if (chargeForce) chargeForce.strength(chargeStrength);
      
      const centerForce = fg.d3Force('center');
      if (centerForce) centerForce.strength(centerStrength);
      
      fg.d3ReheatSimulation();
    }
  }, [graphData, linkDistance, chargeStrength, centerStrength]);

  // Node canvas rendering
  const paintNode = useCallback((node, ctx, globalScale) => {
    const label = node.name || node.key;
    const fontSize = Math.max(12 / globalScale, 4);
    const isSelected = selectedNodes.some(n => n.key === node.key);
    const isHovered = node === hoveredNode;

    // Base node radius
    let baseRadius = isSelected ? 8 : 6;
    
    // Adjust node size based on confidence score (for result graph nodes)
    // Higher confidence = larger node
    // Range: baseRadius * 0.75 (low confidence) to baseRadius * 2.0 (high confidence)
    if (node.confidence !== undefined && node.confidence !== null) {
      // Confidence ranges from 0.0 to 1.0 (1.0 = highest confidence)
      const confidenceMultiplier = 0.75 + (node.confidence * 1.25); // 0.75 to 2.0
      baseRadius = baseRadius * confidenceMultiplier;
    }
    
    const nodeRadius = baseRadius;

    // Get color - prioritize community_id if present (from Louvain), otherwise use entity type
    let nodeColor;
    if (node.community_id !== null && node.community_id !== undefined) {
      // Use community color for Louvain communities
      nodeColor = getCommunityColor(node.community_id);
    } else {
      // Use entity type color (with profile colors if available)
      nodeColor = getNodeColor(node.type, profileColors);
    }

    // Node circle
    ctx.beginPath();
    ctx.arc(node.x, node.y, nodeRadius, 0, 2 * Math.PI);
    ctx.fillStyle = nodeColor;
    ctx.fill();

    // Selection/hover ring - using Owl blue for selection, light gray for hover
    if (isSelected || isHovered) {
      ctx.strokeStyle = isSelected ? '#245e8f' : '#9ca3af'; // owl-blue-700 for selected, light-400 for hover
      ctx.lineWidth = isSelected ? 2.5 : 1.5;
      ctx.stroke();
    }

    // Label - dark text for light theme
    ctx.font = `${fontSize}px Inter, system-ui, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillStyle = '#1f2937'; // light-800 - dark text for light background
    
    // Truncate long labels
    const maxLabelLength = 20;
    const displayLabel = label.length > maxLabelLength 
      ? label.substring(0, maxLabelLength) + '...' 
      : label;
    
    ctx.fillText(displayLabel, node.x, node.y + nodeRadius + 2);
  }, [selectedNodes, hoveredNode, profileColors]);

  // Link rendering - updated for light theme with optional labels
  const paintLink = useCallback((link, ctx, globalScale) => {
    const start = link.source;
    const end = link.target;

    if (!start.x || !end.x) return;

    // Calculate midpoint for label
    const midX = (start.x + end.x) / 2;
    const midY = (start.y + end.y) / 2;
    const dx = end.x - start.x;
    const dy = end.y - start.y;
    const angle = Math.atan2(dy, dx);
    const dist = Math.sqrt(dx * dx + dy * dy);

    if (dist === 0) return; // Avoid division by zero

    // Base link width
    let linkWidth = 1.5;
    
    // Adjust link width based on confidence scores of connected nodes
    // Use average confidence of both nodes
    const startConfidence = start.confidence !== undefined && start.confidence !== null ? start.confidence : null;
    const endConfidence = end.confidence !== undefined && end.confidence !== null ? end.confidence : null;
    
    if (startConfidence !== null || endConfidence !== null) {
      // Calculate average confidence
      const confidences = [startConfidence, endConfidence].filter(c => c !== null);
      if (confidences.length > 0) {
        const avgConfidence = confidences.reduce((sum, c) => sum + c, 0) / confidences.length;
        // Link width ranges from 1.0 (low confidence) to 4.0 (high confidence)
        linkWidth = 1.0 + (avgConfidence * 3.0); // 1.0 to 4.0
      }
    }

    // Draw the link line
    ctx.beginPath();
    ctx.moveTo(start.x, start.y);
    ctx.lineTo(end.x, end.y);
    ctx.strokeStyle = '#9ca3af'; // light-400 - lighter gray for light background
    ctx.lineWidth = linkWidth;
    ctx.stroke();

    // Draw arrow
    const arrowLength = 6;
    const nodeRadius = 8;
    const arrowX = start.x + (dx / dist) * (dist - nodeRadius - 2);
    const arrowY = start.y + (dy / dist) * (dist - nodeRadius - 2);

    ctx.beginPath();
    ctx.moveTo(arrowX, arrowY);
    ctx.lineTo(
      arrowX - arrowLength * Math.cos(angle - Math.PI / 6),
      arrowY - arrowLength * Math.sin(angle - Math.PI / 6)
    );
    ctx.lineTo(
      arrowX - arrowLength * Math.cos(angle + Math.PI / 6),
      arrowY - arrowLength * Math.sin(angle + Math.PI / 6)
    );
    ctx.closePath();
    ctx.fillStyle = '#9ca3af'; // light-400 - match link color
    ctx.fill();

    // Draw relationship label (only if enabled and zoomed in enough)
    if (showRelationshipLabels && link.type && globalScale > 0.3) {
      const label = link.type || '';
      const fontSize = Math.max(10 / globalScale, 8);
      
      ctx.save();
      ctx.translate(midX, midY);
      ctx.rotate(angle);
      
      // Draw background rectangle for better readability
      ctx.font = `${fontSize}px Inter, system-ui, sans-serif`;
      const metrics = ctx.measureText(label);
      const textWidth = metrics.width;
      const textHeight = fontSize;
      const padding = 4;
      
      ctx.fillStyle = 'rgba(255, 255, 255, 0.9)'; // White background with slight transparency
      ctx.fillRect(
        -textWidth / 2 - padding,
        -textHeight / 2 - padding / 2,
        textWidth + padding * 2,
        textHeight + padding
      );
      
      // Draw text
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = '#1f2937'; // light-800 - dark text for light background
      ctx.fillText(label, 0, 0);
      
      ctx.restore();
    }
  }, [showRelationshipLabels]);

  // Handle node click
  const handleNodeClick = useCallback((node, event) => {
    // Use tracked modifier keys state (more reliable than event for canvas)
    const isMultiSelect = modifierKeys.ctrl || modifierKeys.meta;
    
    // Create a synthetic event with modifier info
    const syntheticEvent = {
      ...event,
      ctrlKey: modifierKeys.ctrl,
      metaKey: modifierKeys.meta,
      // Also preserve original event modifiers if available
      originalCtrlKey: event?.ctrlKey,
      originalMetaKey: event?.metaKey,
    };
    
    // Pass to parent with modifier info for multi-select
    onNodeClick?.(node, syntheticEvent);
  }, [onNodeClick, modifierKeys]);

  // Handle right click
  const handleNodeRightClick = useCallback((node, event) => {
    event.preventDefault();
    onNodeRightClick?.(node, event);
  }, [onNodeRightClick]);

  // Handle double click
  const handleNodeDoubleClick = useCallback((node, event) => {
    onNodeDoubleClick?.(node, event);
  }, [onNodeDoubleClick]);

  // Handle background click
  const handleBackgroundClick = useCallback((event) => {
    if (selectionMode === 'click') {
      onBackgroundClick?.();
    }
  }, [onBackgroundClick, selectionMode]);

  // Handle entity type click - select all nodes of that type
  const handleEntityTypeClick = useCallback((entityType, nodesOfType) => {
    if (nodesOfType.length === 0) {
      console.warn(`No nodes found for type: ${entityType}`);
      return;
    }

    console.log(`Entity type clicked: ${entityType}, nodes found: ${nodesOfType.length}`);

    // Check if this type is already selected (all nodes of this type are in selectedNodes)
    const nodesOfTypeInSelection = selectedNodes.filter(n => n.type === entityType);
    const isCurrentlySelected = nodesOfTypeInSelection.length === nodesOfType.length && nodesOfType.length > 0;
    
    if (isCurrentlySelected) {
      // Deselect: remove nodes of this type from selection
      const newSelectedNodes = selectedNodes.filter(n => n.type !== entityType);
      console.log(`Deselecting ${entityType}, new count: ${newSelectedNodes.length}`);
      // Update parent's selected nodes
      if (onBulkNodeSelect) {
        onBulkNodeSelect(newSelectedNodes);
      } else if (onNodeClick) {
        // Fallback: clear and set new selection
        // This is a workaround if bulk select isn't available
        console.warn('onBulkNodeSelect not available, using fallback');
      }
    } else {
      // Select: add all nodes of this type to selection
      // Get currently selected nodes that are NOT of this type
      const otherSelectedNodes = selectedNodes.filter(n => n.type !== entityType);
      // Combine with new nodes of this type (avoid duplicates)
      const existingKeys = new Set(otherSelectedNodes.map(n => n.key));
      const newNodes = nodesOfType.filter(n => !existingKeys.has(n.key));
      const newSelectedNodes = [...otherSelectedNodes, ...newNodes];
      
      console.log(`Selecting ${entityType}, adding ${newNodes.length} new nodes, total: ${newSelectedNodes.length}`);
      
      // Use bulk select if available
      if (onBulkNodeSelect) {
        onBulkNodeSelect(newSelectedNodes);
      } else {
        console.error('onBulkNodeSelect is not available! Entity type selection will not work.');
      }
    }
  }, [selectedNodes, onBulkNodeSelect, onNodeClick]);

  // Update selectedEntityTypes when selectedNodes changes
  useEffect(() => {
    const typesInSelection = new Set(selectedNodes.map(n => n.type));
    // Only update if the Set actually changed (compare sizes and contents)
    setSelectedEntityTypes(prev => {
      if (prev.size !== typesInSelection.size) {
        return typesInSelection;
      }
      // Check if contents are the same
      for (const type of typesInSelection) {
        if (!prev.has(type)) {
          return typesInSelection;
        }
      }
      return prev; // No change, return previous value to avoid re-render
    });
  }, [selectedNodes]);

  // Handle mouse down for drag selection
  const handleMouseDown = useCallback((event) => {
    if (selectionMode === 'drag') {
      // Check if clicking on canvas or container (not on a button or control)
      const target = event.target;
      const isControl = target.closest('button') || target.closest('.absolute');
      
      if (!isControl && (target.tagName === 'CANVAS' || target === containerRef.current)) {
        // Clear fixed selection box when starting a new drag
        setFixedSelectionBox(null);
        
        const rect = containerRef.current?.getBoundingClientRect();
        if (rect) {
          const x = event.clientX - rect.left;
          const y = event.clientY - rect.top;
          isDraggingRef.current = true; // Set ref immediately
          setIsDragging(true);
          setDragStart({ x, y });
          setDragEnd({ x, y });
          event.preventDefault();
          event.stopPropagation();
        }
      }
    } else {
      // In click mode, clear fixed selection box on any click
      setFixedSelectionBox(null);
    }
  }, [selectionMode]);

  // Handle mouse move for drag selection
  const handleMouseMove = useCallback((event) => {
    // Use ref to check dragging state synchronously (avoids stale closure)
    if (!isDraggingRef.current || selectionMode !== 'drag') {
      return;
    }
    
    const rect = containerRef.current?.getBoundingClientRect();
    if (rect) {
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      setDragEnd({ x, y });
    }
  }, [selectionMode]);

  // Handle mouse up for drag selection - fix box and select nodes
  const handleMouseUp = useCallback((event) => {
    // Stop dragging immediately
    if (!isDraggingRef.current || selectionMode !== 'drag') {
      return;
    }
    
    isDraggingRef.current = false;
    
    // Capture current drag values
    if (dragStart && dragEnd) {
      // Calculate selection box bounds
      const minX = Math.min(dragStart.x, dragEnd.x);
      const maxX = Math.max(dragStart.x, dragEnd.x);
      const minY = Math.min(dragStart.y, dragEnd.y);
      const maxY = Math.max(dragStart.y, dragEnd.y);

      // Only proceed if there's a meaningful selection box
      if (Math.abs(maxX - minX) > 5 && Math.abs(maxY - minY) > 5) {
        // Fix the selection box
        const box = {
          x: minX,
          y: minY,
          width: maxX - minX,
          height: maxY - minY,
        };
        setFixedSelectionBox(box);

        // Find nodes within selection box
        // Since zoom and pan are disabled during drag selection mode,
        // we need to calculate the transform by sampling node positions
        
        const fg = graphRef.current;
        if (!fg) {
          console.error('Graph ref not available');
          return;
        }

        // Get zoom level
        const zoom = fg.zoom() || 1;
        
        // Calculate the bounding box of all nodes
        let minGraphX = Infinity, maxGraphX = -Infinity;
        let minGraphY = Infinity, maxGraphY = -Infinity;
        const validNodes = graphData.nodes.filter(n => n.x !== undefined && n.y !== undefined);
        
        validNodes.forEach(node => {
          minGraphX = Math.min(minGraphX, node.x);
          maxGraphX = Math.max(maxGraphX, node.x);
          minGraphY = Math.min(minGraphY, node.y);
          maxGraphY = Math.max(maxGraphY, node.y);
        });
        
        // Graph center in graph coordinates
        const graphCenterX = (minGraphX + maxGraphX) / 2;
        const graphCenterY = (minGraphY + maxGraphY) / 2;
        
        // Graph dimensions
        const graphWidth = maxGraphX - minGraphX;
        const graphHeight = maxGraphY - minGraphY;
        
        // Screen center
        const screenCenterX = width / 2;
        const screenCenterY = height / 2;
        
        // react-force-graph-2d centers and scales the graph to fit
        // The transform is: screenX = (graphX - graphCenterX) * scale + screenCenterX
        // We need to find the scale that fits the graph in the viewport
        
        // Calculate scale to fit graph in viewport (with some padding)
        const scaleX = (width * 0.9) / Math.max(graphWidth, 1);
        const scaleY = (height * 0.9) / Math.max(graphHeight, 1);
        const scale = Math.min(scaleX, scaleY, zoom); // Use the smaller of fit scale or current zoom
        
        // Now convert selection box from screen to graph coordinates
        // Inverse transform: graphX = (screenX - screenCenterX) / scale + graphCenterX
        const graphMinX = (minX - screenCenterX) / scale + graphCenterX;
        const graphMaxX = (maxX - screenCenterX) / scale + graphCenterX;
        const graphMinY = (minY - screenCenterY) / scale + graphCenterY;
        const graphMaxY = (maxY - screenCenterY) / scale + graphCenterY;

        console.log('🔍 Coordinate conversion details:', {
          screenBox: { minX, maxX, minY, maxY, width: maxX - minX, height: maxY - minY },
          graphBox: { 
            minX: graphMinX.toFixed(1), 
            maxX: graphMaxX.toFixed(1), 
            minY: graphMinY.toFixed(1), 
            maxY: graphMaxY.toFixed(1),
            width: (graphMaxX - graphMinX).toFixed(1),
            height: (graphMaxY - graphMinY).toFixed(1)
          },
          transform: { 
            zoom: zoom.toFixed(3),
            calculatedScale: scale.toFixed(3),
            scaleX: scaleX.toFixed(3),
            scaleY: scaleY.toFixed(3)
          },
          graphBounds: {
            minX: minGraphX.toFixed(1),
            maxX: maxGraphX.toFixed(1),
            minY: minGraphY.toFixed(1),
            maxY: maxGraphY.toFixed(1),
            width: graphWidth.toFixed(1),
            height: graphHeight.toFixed(1)
          },
          graphCenter: { x: graphCenterX.toFixed(1), y: graphCenterY.toFixed(1) },
          screenCenter: { x: screenCenterX, y: screenCenterY }
        });

        // Find nodes within selection box in graph coordinates
        const selectedNodesInBox = validNodes.filter(node => {
          // Check if node is within graph coordinate box
          const inBox = node.x >= Math.min(graphMinX, graphMaxX) && 
                       node.x <= Math.max(graphMinX, graphMaxX) &&
                       node.y >= Math.min(graphMinY, graphMaxY) && 
                       node.y <= Math.max(graphMinY, graphMaxY);
          
          if (inBox) {
            // Convert back to screen to verify
            const screenX = (node.x - graphCenterX) * scale + screenCenterX;
            const screenY = (node.y - graphCenterY) * scale + screenCenterY;
            const actuallyInBox = screenX >= minX && screenX <= maxX && screenY >= minY && screenY <= maxY;
            
            console.log(actuallyInBox ? '✅' : '❌', 'Node:', node.key.substring(0, 30), { 
              graphCoords: { x: node.x.toFixed(1), y: node.y.toFixed(1) },
              screenCoords: { x: screenX.toFixed(1), y: screenY.toFixed(1) },
              inScreenBox: actuallyInBox,
              boxBounds: { minX, maxX, minY, maxY }
            });
          }
          
          return inBox;
        });

        console.log('MouseUp - Selection box:', { minX, maxX, minY, maxY, width: maxX - minX, height: maxY - minY });
        console.log('MouseUp - Total nodes:', graphData.nodes.length);
        console.log('MouseUp - Nodes in box:', selectedNodesInBox.length);
        console.log('MouseUp - Sample node coords:', graphData.nodes.slice(0, 3).map(n => ({ key: n.key, x: n.x, y: n.y })));

        // Select ALL nodes in box - THIS IS THE MOST IMPORTANT
        if (selectedNodesInBox.length > 0) {
          console.log('✓ Selecting', selectedNodesInBox.length, 'nodes:', selectedNodesInBox.map(n => `${n.key} (${n.x?.toFixed(0)}, ${n.y?.toFixed(0)})`));
          
          // Use bulk selection if available (more efficient)
          if (onBulkNodeSelect) {
            onBulkNodeSelect(selectedNodesInBox);
          } else if (onNodeClick) {
            // Fallback: select nodes one by one (less efficient but works)
            setTimeout(() => {
              // First node replaces selection
              onNodeClick(selectedNodesInBox[0], { ctrlKey: false, metaKey: false });
              
              // Rest are added with Ctrl modifier (simulate multi-select)
              for (let i = 1; i < selectedNodesInBox.length; i++) {
                setTimeout(() => {
                  onNodeClick(selectedNodesInBox[i], { ctrlKey: true, metaKey: false });
                }, i * 10); // Small delay between each to avoid race conditions
              }
            }, 0);
          } else {
            console.error('❌ Neither onBulkNodeSelect nor onNodeClick is defined!');
          }
        } else {
          console.warn('⚠️ No nodes found in selection box.');
          console.log('Debug info:', {
            box: { minX, maxX, minY, maxY },
            sampleNodes: graphData.nodes.slice(0, 5).map(n => ({ 
              key: n.key, 
              x: n.x, 
              y: n.y,
              inBox: n.x >= minX && n.x <= maxX && n.y >= minY && n.y <= maxY
            }))
          });
        }
      }
    }
    
    // Clear drag state
    setIsDragging(false);
    setDragStart(null);
    setDragEnd(null);
  }, [selectionMode, dragStart, dragEnd, graphData.nodes, onNodeClick]);

  // Handle right-click to fix selection box and select nodes
  const handleRightClick = useCallback((event) => {
    if (selectionMode === 'drag' && (dragStart && dragEnd || fixedSelectionBox)) {
      event.preventDefault();
      event.stopPropagation();
      
      // Use current drag coordinates or fixed box
      const currentStart = dragStart;
      const currentEnd = dragEnd;
      
      if (!currentStart || !currentEnd) {
        // If no current drag, use fixed box if it exists
        if (fixedSelectionBox) {
          // Already fixed, just select nodes
          const minX = fixedSelectionBox.x;
          const maxX = fixedSelectionBox.x + fixedSelectionBox.width;
          const minY = fixedSelectionBox.y;
          const maxY = fixedSelectionBox.y + fixedSelectionBox.height;
          
          // Find nodes within selection box
          const selectedNodesInBox = graphData.nodes.filter(node => {
            if (node.x === undefined || node.y === undefined) return false;
            return node.x >= minX && node.x <= maxX && 
                   node.y >= minY && node.y <= maxY;
          });
          
          // Select all nodes in box
          if (selectedNodesInBox.length > 0) {
            // First node replaces selection
            onNodeClick?.(selectedNodesInBox[0], { ctrlKey: false, metaKey: false });
            // Rest are added
            for (let i = 1; i < selectedNodesInBox.length; i++) {
              onNodeClick?.(selectedNodesInBox[i], { ctrlKey: true, metaKey: false });
            }
          }
        }
        return;
      }
      
      // Calculate selection box bounds in screen coordinates
      const minX = Math.min(currentStart.x, currentEnd.x);
      const maxX = Math.max(currentStart.x, currentEnd.x);
      const minY = Math.min(currentStart.y, currentEnd.y);
      const maxY = Math.max(currentStart.y, currentEnd.y);

      // Only proceed if there's a meaningful selection box (at least 5px in each dimension)
      if (Math.abs(maxX - minX) > 5 && Math.abs(maxY - minY) > 5) {
        // Fix the selection box - it will stay visible until next click
        const box = {
          x: minX,
          y: minY,
          width: maxX - minX,
          height: maxY - minY,
        };
        setFixedSelectionBox(box);

        // Stop dragging
        isDraggingRef.current = false;
        setIsDragging(false);
        setDragStart(null);
        setDragEnd(null);

        // Find nodes within selection box
        // In react-force-graph-2d, node.x and node.y are in canvas coordinates
        // which match our drag coordinates (both relative to the canvas)
        const selectedNodesInBox = graphData.nodes.filter(node => {
          if (node.x === undefined || node.y === undefined) return false;
          // Node coordinates should match screen coordinates directly
          return node.x >= minX && node.x <= maxX && 
                 node.y >= minY && node.y <= maxY;
        });

        console.log('Selection box:', { minX, maxX, minY, maxY });
        console.log('Nodes in graph:', graphData.nodes.length);
        console.log('Nodes in box:', selectedNodesInBox.length, selectedNodesInBox.map(n => ({ key: n.key, x: n.x, y: n.y })));

        // Select nodes in box on right-click - THIS IS THE MOST IMPORTANT PART
        if (selectedNodesInBox.length > 0) {
          // Always replace selection with all nodes in box
          // First node replaces selection
          onNodeClick?.(selectedNodesInBox[0], { ctrlKey: false, metaKey: false });
          // Rest are added with Ctrl modifier
          for (let i = 1; i < selectedNodesInBox.length; i++) {
            onNodeClick?.(selectedNodesInBox[i], { ctrlKey: true, metaKey: false });
          }
        } else {
          console.warn('No nodes found in selection box');
        }
      }
    }
  }, [selectionMode, dragStart, dragEnd, fixedSelectionBox, graphData.nodes, onNodeClick]);

  // Add mouse event listeners for drag selection
  useEffect(() => {
    if (selectionMode === 'drag') {
      const container = containerRef.current;
      if (container) {
        // Use capture phase to catch events before they reach the canvas
        container.addEventListener('mousedown', handleMouseDown, true);
        container.addEventListener('contextmenu', handleRightClick, true); // Right-click to fix
        window.addEventListener('mousemove', handleMouseMove);
        window.addEventListener('mouseup', handleMouseUp);
        
        return () => {
          container.removeEventListener('mousedown', handleMouseDown, true);
          container.removeEventListener('contextmenu', handleRightClick, true);
          window.removeEventListener('mousemove', handleMouseMove);
          window.removeEventListener('mouseup', handleMouseUp);
        };
      }
    } else {
      // Clean up drag state when switching back to click mode
      isDraggingRef.current = false;
      setIsDragging(false);
      setDragStart(null);
      setDragEnd(null);
      setFixedSelectionBox(null);
    }
  }, [selectionMode, handleMouseDown, handleMouseMove, handleMouseUp, handleRightClick]);

  // Calculate selection box coordinates
  // Show fixed box if available, otherwise show dragging box
  const selectionBox = useMemo(() => {
    // If there's a fixed selection box, show that (don't update with mouse)
    if (fixedSelectionBox) {
      return fixedSelectionBox;
    }
    
    // Otherwise, show the dragging box if actively dragging
    if (isDragging && dragStart && dragEnd) {
      const minX = Math.min(dragStart.x, dragEnd.x);
      const maxX = Math.max(dragStart.x, dragEnd.x);
      const minY = Math.min(dragStart.y, dragEnd.y);
      const maxY = Math.max(dragStart.y, dragEnd.y);
      
      return {
        x: minX,
        y: minY,
        width: maxX - minX,
        height: maxY - minY,
      };
    }
    
    return null;
  }, [fixedSelectionBox, isDragging, dragStart, dragEnd]);

  // Load all entity types from database and profile colors
  useEffect(() => {
    const loadEntityTypes = async () => {
      if (!caseId) return;
      try {
        // Get all entity types from database
        const typesData = await graphAPI.getEntityTypes(caseId);
        setAllEntityTypes(typesData.entity_types || []);

        // Try to get colors from the currently selected profile (if any)
        // For now, we'll use a default approach - in the future we could pass selected profile
        // For now, we'll generate colors for all types
        const colors = {};
        (typesData.entity_types || []).forEach(({ type }) => {
          colors[type] = getNodeColor(type, {});
        });
        setProfileColors(colors);
      } catch (err) {
        console.error('Failed to load entity types:', err);
      }
    };

    loadEntityTypes();
  }, [caseId]);

  // Calculate entity types to display - use all types from database, merge with graph data counts
  const entityTypesInGraph = useMemo(() => {
    // Start with all types from database
    const typesMap = new Map();
    
    // Add all types from database with their counts
    allEntityTypes.forEach(({ type, count }) => {
      typesMap.set(type, {
        type,
        count: count || 0,
        color: getNodeColor(type, profileColors)
      });
    });
    
    // Also add any types found in current graph data (in case they're new)
    graphData.nodes.forEach(node => {
      const type = node.type || 'Unknown';
      if (!typesMap.has(type)) {
        typesMap.set(type, {
          type,
          count: 0,
          color: getNodeColor(type, profileColors)
        });
      }
      // Update count from visible graph (for reference, but database count is authoritative)
    });
    
    // Sort by count (descending), then by type name
    return Array.from(typesMap.values()).sort((a, b) => {
      if (b.count !== a.count) return b.count - a.count;
      return a.type.localeCompare(b.type);
    });
  }, [allEntityTypes, graphData.nodes, profileColors]);

  const areAllVisibleNodesSelected = useMemo(() => {
    if (!graphData.nodes.length || !selectedNodes?.length) return false;
    const visibleKeys = new Set(graphData.nodes.map(node => node.key));
    return selectedNodes.every(n => visibleKeys.has(n.key));
  }, [graphData.nodes, selectedNodes]);

  const selectVisibleNodes = useCallback(() => {
    if (!graphData.nodes.length) return;
    onBulkNodeSelect?.(graphData.nodes);
  }, [graphData.nodes, onBulkNodeSelect]);

  const deselectVisibleNodes = useCallback(() => {
    if (!graphData.nodes.length) return;
    onBulkNodeSelect?.([]);
  }, [graphData.nodes, onBulkNodeSelect]);

  const toggleSubgraphPanel = useCallback(() => {
    if (!onPaneViewModeChange) return;
    const nextMode = paneViewMode === 'split' ? 'single' : 'split';
    onPaneViewModeChange(nextMode);
  }, [paneViewMode, onPaneViewModeChange]);

  // Convert graph data to timeline and map formats
  const timelineEvents = useMemo(() => {
    if (viewMode !== 'timeline') return [];
    return convertGraphNodesToTimelineEvents(graphData.nodes, graphData.links);
  }, [graphData, viewMode]);

  const mapLocations = useMemo(() => {
    if (viewMode !== 'map') return [];
    return convertGraphNodesToMapLocations(graphData.nodes, graphData.links);
  }, [graphData, viewMode]);

  // Check if data is available for each mode
  const hasTimeline = useMemo(() => hasTimelineData(graphData.nodes), [graphData.nodes]);
  const hasMap = useMemo(() => hasMapData(graphData.nodes), [graphData.nodes]);

  // Handle timeline event selection
  const handleTimelineEventSelect = useCallback((event, isMultiSelect) => {
    if (!onNodeClick) return;
    const node = graphData.nodes.find(n => n.key === event.key);
    if (node) {
      onNodeClick(node, { ctrlKey: isMultiSelect, metaKey: isMultiSelect });
    }
  }, [graphData.nodes, onNodeClick]);

  // Handle map node click
  const handleMapNodeClick = useCallback((entity, event) => {
    if (!onNodeClick) return;
    const node = graphData.nodes.find(n => n.key === entity.key);
    if (node) {
      onNodeClick(node, event);
    }
  }, [graphData.nodes, onNodeClick]);

  // Get selected event keys for timeline
  const selectedEventKeys = useMemo(() => {
    return selectedNodes.map(n => n.key);
  }, [selectedNodes]);

  return (
    <div 
      ref={containerRef}
      className="relative w-full h-full bg-light-50 flex flex-col"
      style={{ cursor: viewMode === 'graph' && selectionMode === 'drag' ? 'crosshair' : 'default' }}
    >
      {/* Conditional rendering based on view mode */}
      {viewMode === 'graph' && (
      <div className="flex-1 min-h-0 relative">
      <ForceGraph2D
        ref={graphRef}
        graphData={graphData}
        width={width}
        height={height}
        nodeId="key"
        nodeCanvasObject={paintNode}
        nodePointerAreaPaint={(node, color, ctx) => {
          ctx.beginPath();
          ctx.arc(node.x, node.y, 10, 0, 2 * Math.PI);
          ctx.fillStyle = color;
          ctx.fill();
        }}
        linkCanvasObject={paintLink}
        linkDirectionalArrowLength={0}
        onNodeClick={handleNodeClick}
        onNodeRightClick={handleNodeRightClick}
        onNodeDoubleClick={handleNodeDoubleClick}
        enableZoomInteraction={selectionMode !== 'drag'}
        enablePanInteraction={selectionMode !== 'drag'}
        onBackgroundClick={handleBackgroundClick}
        onNodeHover={setHoveredNode}
        cooldownTicks={isSubgraph ? 150 : 100}
        d3AlphaDecay={isSubgraph ? 0.05 : 0.02}
        d3VelocityDecay={isSubgraph ? 0.4 : 0.3}
        backgroundColor="transparent"
      />
      
      {/* Legend */}
      <div className={`absolute bottom-4 bg-white/90 backdrop-blur-sm rounded-lg p-3 text-xs z-10 shadow-lg border border-light-200 ${
        isSubgraph ? 'left-[44px]' : 'left-4'
      }`}>
        {/* Relationship Labels Toggle - Only show in subgraph */}
        {isSubgraph && (
          <div className={`${isLegendMinimized ? 'mb-0 pb-0' : 'mb-3 pb-3 border-b border-light-200'}`}>
            <label className="flex items-center gap-2 cursor-pointer hover:bg-light-50 rounded px-1 py-1 -mx-1 transition-colors">
              <input
                type="checkbox"
                checked={showRelationshipLabels}
                onChange={(e) => setShowRelationshipLabels(e.target.checked)}
                className="w-3.5 h-3.5 rounded border-light-300 text-owl-blue-600 focus:ring-owl-blue-500 focus:ring-1 cursor-pointer"
              />
              <span className="text-xs text-light-700 select-none">
                Show Relationship Labels
              </span>
            </label>
          </div>
        )}
        
        <div className={`flex items-center justify-between ${isLegendMinimized ? '' : 'mb-2'}`}>
          <div className="font-medium text-owl-blue-900">Entity Types</div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setIsLegendMinimized(!isLegendMinimized)}
              className="p-1 rounded hover:bg-light-100 transition-colors"
              title={isLegendMinimized ? 'Expand legend' : 'Minimize legend'}
              type="button"
            >
              {isLegendMinimized ? (
                <ChevronUp className="w-4 h-4 text-light-700" />
              ) : (
                <ChevronDown className="w-4 h-4 text-light-700" />
              )}
            </button>
            {!isSubgraph && (
              <button
                onClick={toggleSubgraphPanel}
                className="p-1 rounded hover:bg-light-100 transition-colors"
                title={paneViewMode === 'split' ? 'Hide subgraph panel' : 'Show subgraph panel'}
                type="button"
              >
                {paneViewMode === 'split' ? (
                  <ChevronLeft className="w-4 h-4 text-light-700" />
                ) : (
                  <ChevronRight className="w-4 h-4 text-light-700" />
                )}
              </button>
            )}
          </div>
        </div>
        {!isLegendMinimized && (
          <>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 max-h-64 overflow-y-auto">
              {entityTypesInGraph.map(({ type, count, color }) => {
                const isSelected = selectedEntityTypes.has(type);
                const nodesOfType = graphData.nodes.filter(n => n.type === type);
                const isSelectedInGraph = selectedNodes.some(n => n.type === type);
                
                return (
                  <button
                    key={type}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleEntityTypeClick(type, nodesOfType);
                    }}
                    className={`flex items-center gap-2 p-1 rounded transition-colors hover:bg-light-100 ${
                      isSelected || isSelectedInGraph ? 'bg-owl-blue-100' : ''
                    }`}
                    title={`Click to select all ${type} entities (${count})`}
                  >
                    <div 
                      className={`w-3 h-3 rounded-full flex-shrink-0 ${isSelected || isSelectedInGraph ? 'ring-2 ring-owl-blue-500' : ''}`}
                      style={{ backgroundColor: color }}
                    />
                    <span className={`text-light-800 truncate ${isSelected || isSelectedInGraph ? 'text-owl-blue-700 font-medium' : ''}`}>
                      {type}
                    </span>
                    <span className="text-light-600 text-[10px] flex-shrink-0">({count})</span>
                  </button>
                );
              })}
            </div>
            <div className="mt-3 pt-2 border-t border-light-200 space-y-2">
              <button
                onClick={areAllVisibleNodesSelected ? deselectVisibleNodes : selectVisibleNodes}
                className="w-full px-3 py-1.5 bg-light-100 hover:bg-light-200 rounded text-xs text-light-700 transition-colors"
                title={areAllVisibleNodesSelected ? "Deselect all visible nodes" : "Select all currently visible nodes"}
              >
                {areAllVisibleNodesSelected ? 'Deselect all visible' : 'Select all visible'}
              </button>
              
              {/* Add/Remove from subgraph buttons */}
              {selectedNodes.length > 0 && (
                <>
                  {/* Add to subgraph - only show in main graph */}
                  {!isSubgraph && onAddToSubgraph && (
                    <button
                      onClick={onAddToSubgraph}
                      disabled={selectedNodes.every(n => subgraphNodeKeys.includes(n.key))}
                      className="w-full px-3 py-1.5 bg-owl-blue-500 hover:bg-owl-blue-600 disabled:bg-light-300 disabled:text-light-500 disabled:cursor-not-allowed rounded text-xs text-white transition-colors"
                      title="Add selected nodes to Spotlight Graph"
                      >
                      Add to Spotlight Graph
                    </button>
                  )}
                  {/* Remove from Spotlight Graph - show in both main graph and Spotlight Graph */}
                  {onRemoveFromSubgraph && (
                    <button
                      onClick={onRemoveFromSubgraph}
                      disabled={!selectedNodes.some(n => subgraphNodeKeys.includes(n.key))}
                      className="w-full px-3 py-1.5 bg-red-500 hover:bg-red-600 disabled:bg-light-300 disabled:text-light-500 disabled:cursor-not-allowed rounded text-xs text-white transition-colors"
                      title="Remove selected nodes from Spotlight Graph"
                      >
                      Remove from Spotlight Graph
                    </button>
                  )}
                </>
              )}
            </div>
          </>
        )}
      </div>

      {/* Center Graph Button - Only show in main graph, not subgraph */}
      {showCenterButton && !isSubgraph && (
        <button
          onClick={centerGraph}
          className="absolute top-4 right-4 z-20 p-2 bg-white/90 backdrop-blur-sm hover:bg-white rounded-lg transition-colors text-light-700 hover:text-owl-blue-900 shadow-sm border border-light-200"
          title="Center and fit graph"
        >
          <Maximize2 className="w-4 h-4" />
        </button>
      )}

      {/* Center Graph Button - Only show in main graph, not subgraph */}
      {!isSubgraph && (
        <button
          onClick={handleCenterClick}
          className="absolute top-4 left-4 p-2 bg-white/90 backdrop-blur-sm hover:bg-white rounded-lg transition-colors shadow-sm border border-light-200 z-10"
          title={selectedNodes && selectedNodes.length > 0 ? "Center on selected nodes" : "Center and fit graph"}
        >
          <Target className="w-5 h-5 text-light-600" />
        </button>
      )}

      {/* Add Node Button - Only show in main graph, not subgraph */}
      {!isSubgraph && onAddNode && (
        <button
          onClick={onAddNode}
          className="absolute top-[54px] left-4 p-2 bg-white/90 backdrop-blur-sm hover:bg-white rounded-lg transition-colors shadow-sm border border-light-200 z-10"
          title="Add Node to Graph"
        >
          <Plus className="w-5 h-5 text-light-600" />
        </button>
      )}

      {/* Selection Mode Toggle - Only show in main graph, not subgraph */}
      {!isSubgraph && (
        <button
          onClick={() => setSelectionMode(selectionMode === 'click' ? 'drag' : 'click')}
          className={`absolute ${onAddNode ? 'top-[92px]' : 'top-[54px]'} left-4 p-2 bg-white/90 backdrop-blur-sm hover:bg-white rounded-lg transition-colors shadow-sm border border-light-200 z-10 ${
            selectionMode === 'drag' ? 'bg-owl-blue-100' : ''
          }`}
          title={selectionMode === 'click' ? 'Switch to drag selection' : 'Switch to click selection'}
        >
          {selectionMode === 'click' ? (
            <Square className="w-5 h-5 text-light-600" />
          ) : (
            <MousePointer className="w-5 h-5 text-owl-blue-600" />
          )}
        </button>
      )}

      {/* Find Similar Entities Button - Only show in main graph, not subgraph */}
      {!isSubgraph && onFindSimilarEntities && (
        <button
          onClick={onFindSimilarEntities}
          disabled={isScanningSimilar}
          className={`absolute ${!isSubgraph && onAddNode ? 'top-[130px]' : 'top-[92px]'} left-4 p-2 bg-white/90 backdrop-blur-sm hover:bg-white rounded-lg transition-colors shadow-sm border border-light-200 z-10 disabled:opacity-50 disabled:cursor-not-allowed`}
          title="Find Similar Entities"
        >
          <Search className={`w-5 h-5 ${isScanningSimilar ? 'text-light-400' : 'text-light-600'}`} />
        </button>
      )}

      {/* Force Controls Toggle - Only show in main graph, not subgraph */}
      {!isSubgraph && (
        <button
          onClick={() => setShowControls(!showControls)}
          className={`absolute ${onAddNode ? (onFindSimilarEntities ? 'top-[168px]' : 'top-[130px]') : (onFindSimilarEntities ? 'top-[130px]' : 'top-[92px]')} left-4 p-2 bg-white/90 backdrop-blur-sm hover:bg-white rounded-lg transition-colors shadow-sm border border-light-200 z-10`}
          title="Graph Settings"
        >
          <Settings className={`w-5 h-5 ${showControls ? 'text-owl-blue-600' : 'text-light-600'}`} />
        </button>
      )}

      {/* Selection Box Overlay */}
      {selectionBox && selectionBox.width > 0 && selectionBox.height > 0 && (
        <div
          className="absolute border-2 border-owl-blue-500 bg-owl-blue-100/50 pointer-events-none z-50"
          style={{
            left: `${selectionBox.x}px`,
            top: `${selectionBox.y}px`,
            width: `${Math.max(selectionBox.width, 1)}px`,
            height: `${Math.max(selectionBox.height, 1)}px`,
            borderStyle: 'dashed',
            position: 'absolute',
          }}
        />
      )}
      
      {/* Debug info - remove after testing */}
      {selectionBox && process.env.NODE_ENV === 'development' && (
        <div className="absolute top-20 left-4 bg-white/90 backdrop-blur-sm p-2 text-xs text-light-800 z-50 rounded shadow-sm border border-light-200">
          Box: {selectionBox.x.toFixed(0)}, {selectionBox.y.toFixed(0)} - {selectionBox.width.toFixed(0)}x{selectionBox.height.toFixed(0)}
          {fixedSelectionBox && <div>FIXED</div>}
        </div>
      )}

      {/* Force Controls Panel */}
      {showControls && (
        <div className={`absolute top-14 bg-white/95 backdrop-blur-sm rounded-lg p-4 text-sm w-64 space-y-4 shadow-lg border border-light-200 ${
          isSubgraph ? 'left-[12px]' : 'left-4'
        }`}>
          <div className="font-medium text-owl-blue-900 border-b border-light-200 pb-2">
            Graph Layout
          </div>
          
          {/* Link Distance */}
          <div>
            <div className="flex justify-between text-xs text-light-600 mb-1">
              <span>Link Distance</span>
              <span>{linkDistance}</span>
            </div>
            <input
              type="range"
              min="20"
              max="500"
              value={linkDistance}
              onChange={(e) => setLinkDistance(Number(e.target.value))}
              className="w-full accent-owl-blue-500"
            />
          </div>
          
          {/* Charge Strength */}
          <div>
            <div className="flex justify-between text-xs text-light-600 mb-1">
              <span>Repulsion</span>
              <span>{Math.abs(chargeStrength)}</span>
            </div>
            <input
              type="range"
              min="20"
              max="1500"
              value={Math.abs(chargeStrength)}
              onChange={(e) => setChargeStrength(-Number(e.target.value))}
              className="w-full accent-owl-blue-500"
            />
          </div>
          
          {/* Center Strength */}
          <div>
            <div className="flex justify-between text-xs text-light-600 mb-1">
              <span>Center Pull</span>
              <span>{centerStrength.toFixed(2)}</span>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              value={centerStrength * 1000}
              onChange={(e) => setCenterStrength(Number(e.target.value) / 1000)}
              className="w-full accent-owl-blue-500"
            />
          </div>
          
          {/* Reset Button */}
          <button
            onClick={() => {
              setLinkDistance(200);
              setChargeStrength(-500);
              setCenterStrength(0.05);
            }}
            className="w-full py-1.5 bg-light-100 hover:bg-light-200 rounded text-light-700 text-xs transition-colors"
          >
            Reset to Defaults
          </button>
        </div>
      )}
      </div>
      )}

      {viewMode === 'timeline' && hasTimeline && (
        <div className="flex-1 min-h-0">
          <TimelineView
            timelineData={timelineEvents}
            onSelectEvent={handleTimelineEventSelect}
            selectedEvent={selectedNodes[0] ? graphData.nodes.find(n => n.key === selectedNodes[0].key) : null}
            selectedEventKeys={selectedEventKeys}
            onSelectEvents={(events) => {
              // Convert events to nodes and call onBulkNodeSelect
              if (onBulkNodeSelect) {
                const nodes = events.map(e => graphData.nodes.find(n => n.key === e.key)).filter(Boolean);
                onBulkNodeSelect(nodes);
              }
            }}
            onBackgroundClick={onBackgroundClick}
          />
        </div>
      )}

      {viewMode === 'map' && hasMap && (
        <div className="flex-1 min-h-0">
          <MapView
            selectedNodes={selectedNodes}
            onNodeClick={handleMapNodeClick}
            onBulkNodeSelect={onBulkNodeSelect}
            onBackgroundClick={onBackgroundClick}
            locations={mapLocations}
          />
        </div>
      )}

      {viewMode === 'timeline' && !hasTimeline && (
        <div className="flex-1 flex items-center justify-center text-light-500">
          <div className="text-center">
            <p className="text-lg font-medium mb-2">No timeline data available</p>
            <p className="text-sm">Nodes need date properties to appear in timeline view</p>
          </div>
        </div>
      )}

      {viewMode === 'map' && !hasMap && (
        <div className="flex-1 flex items-center justify-center text-light-500">
          <div className="text-center">
            <p className="text-lg font-medium mb-2">No map data available</p>
            <p className="text-sm">Nodes need latitude and longitude properties to appear on the map</p>
          </div>
        </div>
      )}
    </div>
  );
});

export default GraphView;
