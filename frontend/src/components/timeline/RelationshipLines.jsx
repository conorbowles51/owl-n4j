
import { useMemo } from "react";
import { calculateVerticalPosition } from "../../utils/timeline";

/**
 * Calculate event positions for relationship lines
 */

// Width of collapsed and expanded columns
const COLLAPSED_COLUMN_WIDTH = 48;
const EXPANDED_COLUMN_WIDTH = 280;
const DATE_AXIS_WIDTH = 96; // w-24 = 96px
const HEADER_HEIGHT = 96; // h-24 = 96px

function calculateEventPositions(events, activeEventTypes, expandedColumns, minDate, maxDate, scaledHeight) {
  const positions = {};
  
  activeEventTypes.forEach((type, columnIndex) => {
    const isExpanded = expandedColumns.has(type);
    const columnWidth = isExpanded ? EXPANDED_COLUMN_WIDTH : COLLAPSED_COLUMN_WIDTH;
    
    // Calculate x offset to start of column
    let xOffset = DATE_AXIS_WIDTH;
    for (let i = 0; i < columnIndex; i++) {
      xOffset += expandedColumns.has(activeEventTypes[i]) ? EXPANDED_COLUMN_WIDTH : COLLAPSED_COLUMN_WIDTH;
    }
    
    // For expanded columns, use the left edge of the card (around 56px from column start)
    // For collapsed columns, use the center (dot position)
    const xLeft = isExpanded ? xOffset + 56 : xOffset + (columnWidth / 2);
    const xRight = isExpanded ? xOffset + columnWidth - 8 : xOffset + (columnWidth / 2);
    const xCenter = xOffset + (columnWidth / 2);
    
    // Calculate y positions for events of this type
    const typeEvents = events.filter(e => e.type === type);
    typeEvents.forEach(event => {
      const topPercent = calculateVerticalPosition(event.date, event.time, minDate, maxDate);
      const y = HEADER_HEIGHT + (topPercent / 100) * scaledHeight;
      positions[event.key] = { 
        xLeft, 
        xRight, 
        xCenter,
        y, 
        type, 
        columnIndex,
        isExpanded,
        event 
      };
    });
  });
  
  return positions;
}

/**
 * Find relationships between events
 */
function findEventRelationships(events) {
  const eventKeys = new Set(events.map(e => e.key));
  const relationships = [];
  
  events.forEach(event => {
    if (event.connections && Array.isArray(event.connections)) {
      event.connections.forEach(conn => {
        // Only include if the connected entity is also an event in our list
        if (conn.key && eventKeys.has(conn.key)) {
          // Avoid duplicates (A->B and B->A)
          const existingRel = relationships.find(r => 
            (r.from === event.key && r.to === conn.key) ||
            (r.from === conn.key && r.to === event.key)
          );
          if (!existingRel) {
            relationships.push({
              from: event.key,
              to: conn.key,
              relationship: conn.relationship,
              direction: conn.direction
            });
          }
        }
      });
    }
  });
  
  return relationships;
}

/**
 * Relationship Lines Overlay Component
 */
export function RelationshipLines({ events, activeEventTypes, expandedColumns, minDate, maxDate, scaledHeight }) {
  const positions = useMemo(() => 
    calculateEventPositions(events, activeEventTypes, expandedColumns, minDate, maxDate, scaledHeight),
    [events, activeEventTypes, expandedColumns, minDate, maxDate, scaledHeight]
  );
  
  const relationships = useMemo(() => 
    findEventRelationships(events),
    [events]
  );
  
  // Calculate total width needed for SVG
  const totalWidth = useMemo(() => {
    let width = DATE_AXIS_WIDTH;
    activeEventTypes.forEach(type => {
      width += expandedColumns.has(type) ? EXPANDED_COLUMN_WIDTH : COLLAPSED_COLUMN_WIDTH;
    });
    return width;
  }, [activeEventTypes, expandedColumns]);
  
  if (relationships.length === 0) return null;
  
  return (
    <svg
      className="absolute pointer-events-none"
      style={{
        top: 0,
        left: 0,
        width: `${totalWidth}px`,
        height: `${scaledHeight + HEADER_HEIGHT}px`,
        zIndex: 25,
        overflow: 'visible'
      }}
    >
      <defs>
        <marker
          id="arrowhead"
          markerWidth="10"
          markerHeight="7"
          refX="9"
          refY="3.5"
          orient="auto"
        >
          <polygon
            points="0 0, 10 3.5, 0 7"
            fill="#94a3b8"
          />
        </marker>
      </defs>
      
      {relationships.map((rel, idx) => {
        const fromPos = positions[rel.from];
        const toPos = positions[rel.to];
        
        if (!fromPos || !toPos) return null;
        
        // Determine which edges to connect based on relative column positions
        // Line goes from right edge of "from" to left edge of "to" if from is to the left
        // Otherwise, go from left edge of "from" to right edge of "to"
        const fromIsLeft = fromPos.columnIndex < toPos.columnIndex;
        const fromX = fromIsLeft ? fromPos.xRight : fromPos.xLeft;
        const toX = fromIsLeft ? toPos.xLeft : toPos.xRight;
        
        // If same column, use center positions
        const sameColumn = fromPos.columnIndex === toPos.columnIndex;
        const x1 = sameColumn ? fromPos.xCenter : fromX;
        const y1 = fromPos.y;
        const x2 = sameColumn ? toPos.xCenter : toX;
        const y2 = toPos.y;
        
        // Calculate control points for curved line
        const midX = (x1 + x2) / 2;
        const midY = (y1 + y2) / 2;
        const dx = x2 - x1;
        const dy = y2 - y1;
        const distance = Math.sqrt(dx * dx + dy * dy);
        
        if (distance < 1) return null; // Skip if same position
        
        // Curve offset based on distance
        const curveOffset = sameColumn 
          ? Math.min(Math.abs(dy) * 0.3, 80) // Curve more for same column (vertical lines)
          : Math.min(distance * 0.2, 40);
        
        // For same column, curve to the side; otherwise curve perpendicular
        const perpX = sameColumn 
          ? curveOffset 
          : -dy / distance * curveOffset;
        const perpY = sameColumn 
          ? 0 
          : dx / distance * curveOffset;
        
        const ctrlX = midX + perpX;
        const ctrlY = midY + perpY;
        
        return (
          <g key={idx}>
            {/* Relationship line */}
            <path
              d={`M ${x1} ${y1} Q ${ctrlX} ${ctrlY} ${x2} ${y2}`}
              stroke="#94a3b8"
              strokeWidth="2"
              fill="none"
              strokeDasharray="4 2"
              opacity="0.6"
              markerEnd="url(#arrowhead)"
            />
            {/* Relationship label */}
            {rel.relationship && (
              <text
                x={ctrlX + (sameColumn ? 10 : 0)}
                y={ctrlY - 5}
                fontSize="10"
                fill="#64748b"
                textAnchor={sameColumn ? "start" : "middle"}
                className="pointer-events-none"
              >
                {rel.relationship}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}