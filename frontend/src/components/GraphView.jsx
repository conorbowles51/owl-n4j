import React, { useRef, useCallback, useEffect, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';

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
export default function GraphView({
  graphData,
  selectedNode,
  onNodeClick,
  onNodeRightClick,
  onBackgroundClick,
  width,
  height,
}) {
  const graphRef = useRef();
  const [hoveredNode, setHoveredNode] = useState(null);

  // Center graph on mount
  useEffect(() => {
    if (graphRef.current && graphData.nodes.length > 0) {
      setTimeout(() => {
        graphRef.current.zoomToFit(400, 50);
      }, 500);
    }
  }, [graphData]);

  // Node canvas rendering
  const paintNode = useCallback((node, ctx, globalScale) => {
    console.log(node)
    const label = node.name || node.key;
    const fontSize = Math.max(12 / globalScale, 4);
    const nodeRadius = node === selectedNode ? 8 : 6;
    const isHovered = node === hoveredNode;
    const isSelected = node === selectedNode;

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
  }, [selectedNode, hoveredNode]);

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
    if (event.ctrlKey || event.metaKey) {
      // Ctrl/Cmd click - show context menu
      onNodeRightClick?.(node, event);
    } else {
      onNodeClick?.(node);
    }
  }, [onNodeClick, onNodeRightClick]);

  // Handle right click
  const handleNodeRightClick = useCallback((node, event) => {
    event.preventDefault();
    onNodeRightClick?.(node, event);
  }, [onNodeRightClick]);

  // Handle background click
  const handleBackgroundClick = useCallback((event) => {
    onBackgroundClick?.();
  }, [onBackgroundClick]);

  return (
    <div className="relative w-full h-full bg-dark-950">
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
        onBackgroundClick={handleBackgroundClick}
        onNodeHover={setHoveredNode}
        cooldownTicks={100}
        d3AlphaDecay={0.02}
        d3VelocityDecay={0.3}
        backgroundColor="transparent"
      />
      
      {/* Legend */}
      <div className="absolute bottom-4 left-4 bg-dark-800/90 rounded-lg p-3 text-xs">
        <div className="font-medium text-dark-200 mb-2">Entity Types</div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          {Object.entries(TYPE_COLORS).slice(0, 10).map(([type, color]) => (
            <div key={type} className="flex items-center gap-2">
              <div 
                className="w-3 h-3 rounded-full" 
                style={{ backgroundColor: color }}
              />
              <span className="text-dark-300">{type}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
