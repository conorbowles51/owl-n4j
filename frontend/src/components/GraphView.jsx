import React, { useRef, useCallback, useEffect, useState, useMemo, useImperativeHandle, forwardRef } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { Settings, MousePointer, Square, Maximize2, Layout } from "lucide-react"
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
 * Get color for entity type
 */
function getNodeColor(type) {
  return TYPE_COLORS[type] || TYPE_COLORS.Other;
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
  onBackgroundClick,
  width,
  height,
  showCenterButton = true, // Show center button by default
  paneViewMode, // 'single' or 'split'
  onPaneViewModeChange, // Callback to change pane view mode
}, ref) {
  const graphRef = useRef();
  const containerRef = useRef();
  const isDraggingRef = useRef(false); // Ref to track dragging state synchronously
  const [hoveredNode, setHoveredNode] = useState(null);
  const [modifierKeys, setModifierKeys] = useState({ ctrl: false, meta: false });
  const [selectedEntityTypes, setSelectedEntityTypes] = useState(new Set()); // Track selected entity types

  // Selection mode: 'click' or 'drag'
  const [selectionMode, setSelectionMode] = useState('click');

  // Drag selection state
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState(null);
  const [dragEnd, setDragEnd] = useState(null);
  const [fixedSelectionBox, setFixedSelectionBox] = useState(null); // Selection box that stays after mouseUp

  // Force simulation controls
  const [showControls, setShowControls] = useState(false);
  const [linkDistance, setLinkDistance] = useState(200);
  const [chargeStrength, setChargeStrength] = useState(-500);
  const [centerStrength, setCenterStrength] = useState(0.05);

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
    if (graphRef.current && graphData.nodes.length > 0) {
      graphRef.current.zoomToFit(400, 50);
    }
  }, [graphData]);

  // Get graph canvas for PDF export
  const getGraphCanvas = useCallback(() => {
    if (containerRef.current) {
      // Find the canvas element within the container
      const canvas = containerRef.current.querySelector('canvas');
      return canvas || null;
    }
    return null;
  }, []);

  // Expose centerGraph and getGraphCanvas methods via ref
  useImperativeHandle(ref, () => ({
    centerGraph,
    getGraphCanvas,
  }), [centerGraph, getGraphCanvas]);

  // Center graph on mount
  useEffect(() => {
    if (graphRef.current && graphData.nodes.length > 0) {
      setTimeout(() => {
        centerGraph();
      }, 500);
    }
  }, [graphData, centerGraph]);

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
    console.log(node)
    const label = node.name || node.key;
    const fontSize = Math.max(12 / globalScale, 4);
    const isSelected = selectedNodes.some(n => n.key === node.key);
    const nodeRadius = isSelected ? 8 : 6;
    const isHovered = node === hoveredNode;

    // Node circle
    ctx.beginPath();
    ctx.arc(node.x, node.y, nodeRadius, 0, 2 * Math.PI);
    ctx.fillStyle = getNodeColor(node.type);
    ctx.fill();

    // Selection/hover ring
    if (isSelected || isHovered) {
      ctx.strokeStyle = isSelected ? '#ffffff' : '#8e8ea0';
      ctx.lineWidth = isSelected ? 2 : 1;
      ctx.stroke();
    }

    // Label
    ctx.font = `${fontSize}px Inter, system-ui, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillStyle = '#ececf1';
    
    // Truncate long labels
    const maxLabelLength = 20;
    const displayLabel = label.length > maxLabelLength 
      ? label.substring(0, maxLabelLength) + '...' 
      : label;
    
    ctx.fillText(displayLabel, node.x, node.y + nodeRadius + 2);
  }, [selectedNodes, hoveredNode]);

  // Link rendering
  const paintLink = useCallback((link, ctx, globalScale) => {
    const start = link.source;
    const end = link.target;

    if (!start.x || !end.x) return;

    ctx.beginPath();
    ctx.moveTo(start.x, start.y);
    ctx.lineTo(end.x, end.y);
    ctx.strokeStyle = '#565869';
    ctx.lineWidth = 1;
    ctx.stroke();

    // Draw arrow
    const arrowLength = 6;
    const dx = end.x - start.x;
    const dy = end.y - start.y;
    const angle = Math.atan2(dy, dx);
    
    // Position arrow before the node
    const nodeRadius = 8;
    const dist = Math.sqrt(dx * dx + dy * dy);
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
    ctx.fillStyle = '#565869';
    ctx.fill();
  }, []);

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
    setSelectedEntityTypes(typesInSelection);
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

  return (
    <div 
      ref={containerRef}
      className="relative w-full h-full bg-dark-950"
      style={{ cursor: selectionMode === 'drag' ? 'crosshair' : 'default' }}
    >
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
        enableZoomInteraction={selectionMode !== 'drag'}
        enablePanInteraction={selectionMode !== 'drag'}
        onBackgroundClick={handleBackgroundClick}
        onNodeHover={setHoveredNode}
        cooldownTicks={100}
        d3AlphaDecay={0.02}
        d3VelocityDecay={0.3}
        backgroundColor="transparent"
      />
      
      {/* Legend */}
      <div className="absolute bottom-4 left-4 bg-dark-800/90 rounded-lg p-3 text-xs z-10">
        {/* Pane View Toggle */}
        {onPaneViewModeChange && (
          <button
            onClick={() => onPaneViewModeChange(paneViewMode === 'split' ? 'single' : 'split')}
            className={`mb-3 w-full px-2 py-1.5 rounded text-xs transition-colors flex items-center justify-center gap-2 ${
              paneViewMode === 'split'
                ? 'bg-cyan-600/90 hover:bg-cyan-500 text-white'
                : 'bg-dark-700 hover:bg-dark-600 text-dark-200'
            }`}
            title={paneViewMode === 'split' ? 'Switch to single pane view' : 'Switch to split pane view'}
          >
            <Layout className="w-3 h-3" />
            {paneViewMode === 'split' ? 'Single Pane' : 'Split View'}
          </button>
        )}
        <div className="font-medium text-dark-200 mb-2">Entity Types</div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          {Object.entries(TYPE_COLORS).slice(0, 10).map(([type, color]) => {
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
                className={`flex items-center gap-2 p-1 rounded transition-colors hover:bg-dark-700 ${
                  isSelected || isSelectedInGraph ? 'bg-cyan-600/20' : ''
                }`}
                title={`Click to select all ${type} entities (${nodesOfType.length})`}
              >
                <div 
                  className={`w-3 h-3 rounded-full ${isSelected || isSelectedInGraph ? 'ring-2 ring-cyan-400' : ''}`}
                  style={{ backgroundColor: color }}
                />
                <span className={`text-dark-300 ${isSelected || isSelectedInGraph ? 'text-cyan-300 font-medium' : ''}`}>
                  {type}
                </span>
                {nodesOfType.length > 0 && (
                  <span className="text-dark-500 text-[10px]">({nodesOfType.length})</span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Center Graph Button */}
      {showCenterButton && (
        <button
          onClick={centerGraph}
          className="absolute top-4 right-4 z-20 p-2 bg-dark-800/90 hover:bg-dark-700 rounded-lg transition-colors text-dark-300 hover:text-dark-100"
          title="Center and fit graph"
        >
          <Maximize2 className="w-4 h-4" />
        </button>
      )}

      {/* Selection Mode Toggle */}
      <button
        onClick={() => setSelectionMode(selectionMode === 'click' ? 'drag' : 'click')}
        className={`absolute top-4 left-4 p-2 bg-dark-800/90 hover:bg-dark-700 rounded-lg transition-colors ${
          selectionMode === 'drag' ? 'bg-cyan-600/20' : ''
        }`}
        title={selectionMode === 'click' ? 'Switch to drag selection' : 'Switch to click selection'}
      >
        {selectionMode === 'click' ? (
          <Square className="w-5 h-5 text-dark-400" />
        ) : (
          <MousePointer className="w-5 h-5 text-cyan-400" />
        )}
      </button>

      {/* Force Controls Toggle */}
      <button
        onClick={() => setShowControls(!showControls)}
        className="absolute top-4 left-14 p-2 bg-dark-800/90 hover:bg-dark-700 rounded-lg transition-colors"
        title="Graph Settings"
      >
        <Settings className={`w-5 h-5 ${showControls ? 'text-cyan-400' : 'text-dark-400'}`} />
      </button>

      {/* Selection Box Overlay */}
      {selectionBox && selectionBox.width > 0 && selectionBox.height > 0 && (
        <div
          className="absolute border-2 border-cyan-400 bg-cyan-400/10 pointer-events-none z-50"
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
        <div className="absolute top-20 left-4 bg-dark-800/90 p-2 text-xs text-dark-200 z-50">
          Box: {selectionBox.x.toFixed(0)}, {selectionBox.y.toFixed(0)} - {selectionBox.width.toFixed(0)}x{selectionBox.height.toFixed(0)}
          {fixedSelectionBox && <div>FIXED</div>}
        </div>
      )}

      {/* Force Controls Panel */}
      {showControls && (
        <div className="absolute top-14 left-4 bg-dark-800/95 rounded-lg p-4 text-sm w-64 space-y-4">
          <div className="font-medium text-dark-200 border-b border-dark-700 pb-2">
            Graph Layout
          </div>
          
          {/* Link Distance */}
          <div>
            <div className="flex justify-between text-xs text-dark-400 mb-1">
              <span>Link Distance</span>
              <span>{linkDistance}</span>
            </div>
            <input
              type="range"
              min="20"
              max="500"
              value={linkDistance}
              onChange={(e) => setLinkDistance(Number(e.target.value))}
              className="w-full accent-cyan-500"
            />
          </div>
          
          {/* Charge Strength */}
          <div>
            <div className="flex justify-between text-xs text-dark-400 mb-1">
              <span>Repulsion</span>
              <span>{Math.abs(chargeStrength)}</span>
            </div>
            <input
              type="range"
              min="20"
              max="1500"
              value={Math.abs(chargeStrength)}
              onChange={(e) => setChargeStrength(-Number(e.target.value))}
              className="w-full accent-cyan-500"
            />
          </div>
          
          {/* Center Strength */}
          <div>
            <div className="flex justify-between text-xs text-dark-400 mb-1">
              <span>Center Pull</span>
              <span>{centerStrength.toFixed(2)}</span>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              value={centerStrength * 1000}
              onChange={(e) => setCenterStrength(Number(e.target.value) / 1000)}
              className="w-full accent-cyan-500"
            />
          </div>
          
          {/* Reset Button */}
          <button
            onClick={() => {
              setLinkDistance(200);
              setChargeStrength(-500);
              setCenterStrength(0.05);
            }}
            className="w-full py-1.5 bg-dark-700 hover:bg-dark-600 rounded text-dark-300 text-xs transition-colors"
          >
            Reset to Defaults
          </button>
        </div>
      )}
    </div>
  );
});

export default GraphView;
