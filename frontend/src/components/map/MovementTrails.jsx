import React, { useMemo } from 'react';
import { Polyline, Marker, Tooltip } from 'react-leaflet';
import L from 'leaflet';
import { sortByDate, calculatePathDistance, formatDistance } from '../../utils/geo';

// Entity type colors
const TYPE_COLORS = {
  Person: '#3b82f6',
  Company: '#ef4444',
  Account: '#22c55e',
  Bank: '#f59e0b',
  Organisation: '#8b5cf6',
  Location: '#06b6d4',
  Transaction: '#f97316',
  Meeting: '#ec4899',
  Payment: '#14b8a6',
  Email: '#6366f1',
  PhoneCall: '#84cc16',
  Transfer: '#f43f5e',
  default: '#6b7280',
};

/**
 * MovementTrails Component
 *
 * Visualizes movement patterns by drawing paths between locations
 * of selected entities, ordered by date.
 */
export default function MovementTrails({
  locations = [],
  selectedNodes = [],
  showLabels = true,
  animationTime = null,
}) {
  // Get selected locations sorted by date
  const trails = useMemo(() => {
    if (selectedNodes.length === 0) return [];

    // Group locations by selected entities
    const entityTrails = [];

    selectedNodes.forEach(node => {
      // Find all locations for this entity
      const entityLocations = locations.filter(loc => loc.key === node.key);

      if (entityLocations.length > 1) {
        // Sort by date
        const sorted = sortByDate(entityLocations);

        // Filter by animation time if set
        const filtered = animationTime
          ? sorted.filter(loc => {
              if (!loc.date) return true;
              const locDate = new Date(loc.date);
              return !isNaN(locDate.getTime()) && locDate <= animationTime;
            })
          : sorted;

        if (filtered.length > 1) {
          const color = TYPE_COLORS[node.type] || TYPE_COLORS.default;
          const totalDistance = calculatePathDistance(filtered);

          entityTrails.push({
            key: node.key,
            name: node.name,
            type: node.type,
            color,
            locations: filtered,
            totalDistance,
            segments: filtered.slice(0, -1).map((loc, idx) => ({
              from: loc,
              to: filtered[idx + 1],
              positions: [
                [loc.latitude, loc.longitude],
                [filtered[idx + 1].latitude, filtered[idx + 1].longitude],
              ],
            })),
          });
        }
      }
    });

    return entityTrails;
  }, [locations, selectedNodes, animationTime]);

  // If only selected entities (with single locations) are shown,
  // draw paths connecting them in chronological order
  const connectionPath = useMemo(() => {
    if (selectedNodes.length < 2) return null;

    // Get locations for all selected entities
    const selectedLocations = selectedNodes
      .map(node => {
        const loc = locations.find(l => l.key === node.key);
        return loc ? { ...loc, ...node } : null;
      })
      .filter(Boolean);

    if (selectedLocations.length < 2) return null;

    // Sort by date if available
    const sorted = sortByDate(selectedLocations);

    // Filter by animation time if set
    const filtered = animationTime
      ? sorted.filter(loc => {
          if (!loc.date) return true;
          const locDate = new Date(loc.date);
          return !isNaN(locDate.getTime()) && locDate <= animationTime;
        })
      : sorted;

    if (filtered.length < 2) return null;

    const totalDistance = calculatePathDistance(filtered);

    return {
      locations: filtered,
      positions: filtered.map(loc => [loc.latitude, loc.longitude]),
      totalDistance,
      segments: filtered.slice(0, -1).map((loc, idx) => ({
        from: loc,
        to: filtered[idx + 1],
      })),
    };
  }, [locations, selectedNodes, animationTime]);

  // Create numbered waypoint icon
  const createWaypointIcon = (number, color) => {
    return L.divIcon({
      className: 'waypoint-marker',
      html: `
        <div style="
          width: 24px;
          height: 24px;
          background: ${color};
          border: 2px solid white;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          color: white;
          font-size: 11px;
          font-weight: bold;
          box-shadow: 0 2px 4px rgba(0,0,0,0.3);
        ">
          ${number}
        </div>
      `,
      iconSize: [24, 24],
      iconAnchor: [12, 12],
    });
  };

  return (
    <>
      {/* Entity-specific trails (for entities with multiple locations) */}
      {trails.map(trail => (
        <React.Fragment key={trail.key}>
          {/* Path segments */}
          {trail.segments.map((segment, idx) => (
            <Polyline
              key={`${trail.key}-segment-${idx}`}
              positions={segment.positions}
              pathOptions={{
                color: trail.color,
                weight: 3,
                opacity: 0.7,
                dashArray: '8, 4',
              }}
            >
              {showLabels && (
                <Tooltip sticky direction="top" offset={[0, -5]} opacity={0.95}>
                  <div className="text-xs">
                    <div className="font-medium" style={{ color: trail.color }}>
                      {trail.name}
                    </div>
                    <div className="text-gray-600">
                      {segment.from.date || 'Unknown'} → {segment.to.date || 'Unknown'}
                    </div>
                  </div>
                </Tooltip>
              )}
            </Polyline>
          ))}

          {/* Waypoint markers */}
          {trail.locations.map((loc, idx) => (
            <Marker
              key={`${trail.key}-waypoint-${idx}`}
              position={[loc.latitude, loc.longitude]}
              icon={createWaypointIcon(idx + 1, trail.color)}
            >
              <Tooltip direction="top" offset={[0, -10]} opacity={0.95}>
                <div className="text-xs">
                  <div className="font-medium">{trail.name}</div>
                  <div className="text-gray-600">
                    Stop {idx + 1}: {loc.location_formatted || 'Unknown location'}
                  </div>
                  {loc.date && (
                    <div className="text-gray-500">{loc.date}</div>
                  )}
                </div>
              </Tooltip>
            </Marker>
          ))}
        </React.Fragment>
      ))}

      {/* Connection path for selected entities */}
      {connectionPath && trails.length === 0 && (
        <>
          {/* Main path line */}
          <Polyline
            positions={connectionPath.positions}
            pathOptions={{
              color: '#6366f1', // indigo
              weight: 2.5,
              opacity: 0.6,
              dashArray: '10, 6',
            }}
          >
            <Tooltip sticky direction="top" offset={[0, -5]} opacity={0.95}>
              <div className="text-xs">
                <div className="font-medium text-indigo-600">
                  Path: {connectionPath.locations.length} stops
                </div>
                <div className="text-gray-600">
                  Total: {formatDistance(connectionPath.totalDistance)}
                </div>
              </div>
            </Tooltip>
          </Polyline>

          {/* Numbered waypoints */}
          {connectionPath.locations.map((loc, idx) => (
            <Marker
              key={`connection-waypoint-${idx}`}
              position={[loc.latitude, loc.longitude]}
              icon={createWaypointIcon(
                idx + 1,
                TYPE_COLORS[loc.type] || TYPE_COLORS.default
              )}
            >
              <Tooltip direction="top" offset={[0, -10]} opacity={0.95}>
                <div className="text-xs">
                  <div className="font-medium">
                    {idx + 1}. {loc.name}
                  </div>
                  {loc.date && (
                    <div className="text-gray-500">{loc.date}</div>
                  )}
                </div>
              </Tooltip>
            </Marker>
          ))}
        </>
      )}
    </>
  );
}
