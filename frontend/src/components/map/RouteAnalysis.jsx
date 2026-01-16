import React, { useState, useMemo, useCallback } from 'react';
import { useMap, Circle, Polyline, Marker } from 'react-leaflet';
import L from 'leaflet';
import {
  Route,
  X,
  MapPin,
  Calendar,
  ArrowRight,
  Ruler,
  Clock,
  Users,
  Target,
  ChevronDown,
  ChevronUp
} from 'lucide-react';
import {
  sortByDate,
  calculatePathDistance,
  formatDistance,
  haversineDistance,
  findGeographicCenter
} from '../../utils/geo';

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
 * RouteAnalysis Component
 *
 * Provides comprehensive route and path analysis tools:
 * 1. Connect selected entities in chronological order
 * 2. Calculate path distances and statistics
 * 3. Show intersection points between entity paths
 * 4. Track individual entity movements
 */
export default function RouteAnalysis({
  locations = [],
  selectedNodes = [],
  onSelectEntity,
  isActive = false,
  onClose,
}) {
  const map = useMap();
  const [showPath, setShowPath] = useState(true);
  const [showWaypoints, setShowWaypoints] = useState(true);
  const [expandedSection, setExpandedSection] = useState('route');

  // Get locations for selected entities
  const selectedLocations = useMemo(() => {
    return selectedNodes
      .map(node => {
        const loc = locations.find(l => l.key === node.key);
        return loc ? { ...loc, ...node } : null;
      })
      .filter(Boolean);
  }, [locations, selectedNodes]);

  // Sort by date for route
  const chronologicalRoute = useMemo(() => {
    if (selectedLocations.length < 2) return null;

    const sorted = sortByDate(selectedLocations);
    const positions = sorted.map(loc => [loc.latitude, loc.longitude]);
    const totalDistance = calculatePathDistance(sorted);

    // Calculate leg distances
    const legs = sorted.slice(0, -1).map((loc, idx) => {
      const nextLoc = sorted[idx + 1];
      const distance = haversineDistance(
        loc.latitude,
        loc.longitude,
        nextLoc.latitude,
        nextLoc.longitude
      );

      // Calculate time difference if dates are available
      let timeDiff = null;
      if (loc.date && nextLoc.date) {
        const date1 = new Date(loc.date);
        const date2 = new Date(nextLoc.date);
        if (!isNaN(date1.getTime()) && !isNaN(date2.getTime())) {
          const diffMs = Math.abs(date2.getTime() - date1.getTime());
          const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
          timeDiff = diffDays;
        }
      }

      return {
        from: loc,
        to: nextLoc,
        distance,
        timeDiff,
      };
    });

    return {
      locations: sorted,
      positions,
      totalDistance,
      legs,
      center: findGeographicCenter(sorted),
    };
  }, [selectedLocations]);

  // Find potential intersection points (entities that were close in space and time)
  const intersections = useMemo(() => {
    if (selectedLocations.length < 2) return [];

    const results = [];
    const proximityThreshold = 10; // km
    const timeThreshold = 7; // days

    for (let i = 0; i < selectedLocations.length; i++) {
      for (let j = i + 1; j < selectedLocations.length; j++) {
        const loc1 = selectedLocations[i];
        const loc2 = selectedLocations[j];

        const distance = haversineDistance(
          loc1.latitude,
          loc1.longitude,
          loc2.latitude,
          loc2.longitude
        );

        if (distance <= proximityThreshold) {
          let timeDiff = null;
          let timeClose = false;

          if (loc1.date && loc2.date) {
            const date1 = new Date(loc1.date);
            const date2 = new Date(loc2.date);
            if (!isNaN(date1.getTime()) && !isNaN(date2.getTime())) {
              const diffMs = Math.abs(date2.getTime() - date1.getTime());
              timeDiff = Math.floor(diffMs / (1000 * 60 * 60 * 24));
              timeClose = timeDiff <= timeThreshold;
            }
          }

          results.push({
            entity1: loc1,
            entity2: loc2,
            distance,
            timeDiff,
            timeClose,
            center: {
              lat: (loc1.latitude + loc2.latitude) / 2,
              lng: (loc1.longitude + loc2.longitude) / 2,
            },
          });
        }
      }
    }

    return results.sort((a, b) => a.distance - b.distance);
  }, [selectedLocations]);

  // Zoom to route
  const zoomToRoute = useCallback(() => {
    if (chronologicalRoute && chronologicalRoute.positions.length > 0) {
      const bounds = L.latLngBounds(chronologicalRoute.positions);
      map.fitBounds(bounds, { padding: [50, 50] });
    }
  }, [chronologicalRoute, map]);

  // Create waypoint icon
  const createWaypointIcon = (number, color) => {
    return L.divIcon({
      className: 'route-waypoint',
      html: `
        <div style="
          width: 28px;
          height: 28px;
          background: ${color};
          border: 3px solid white;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          color: white;
          font-size: 12px;
          font-weight: bold;
          box-shadow: 0 2px 6px rgba(0,0,0,0.4);
        ">
          ${number}
        </div>
      `,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    });
  };

  if (!isActive) return null;

  return (
    <>
      {/* Route path on map */}
      {showPath && chronologicalRoute && (
        <Polyline
          positions={chronologicalRoute.positions}
          pathOptions={{
            color: '#6366f1',
            weight: 3,
            opacity: 0.7,
            dashArray: '10, 6',
          }}
        />
      )}

      {/* Waypoint markers */}
      {showWaypoints && chronologicalRoute && (
        chronologicalRoute.locations.map((loc, idx) => (
          <Marker
            key={`route-waypoint-${idx}`}
            position={[loc.latitude, loc.longitude]}
            icon={createWaypointIcon(
              idx + 1,
              TYPE_COLORS[loc.type] || TYPE_COLORS.default
            )}
          />
        ))
      )}

      {/* Intersection circles */}
      {intersections.filter(i => i.timeClose).map((intersection, idx) => (
        <Circle
          key={`intersection-${idx}`}
          center={[intersection.center.lat, intersection.center.lng]}
          radius={intersection.distance * 500} // Scale for visibility
          pathOptions={{
            color: '#ef4444',
            fillColor: '#ef4444',
            fillOpacity: 0.1,
            weight: 2,
            dashArray: '4, 4',
          }}
        />
      ))}

      {/* Control panel */}
      <div className="absolute top-4 right-4 z-[1000] bg-white/95 backdrop-blur-sm rounded-lg shadow-lg border border-light-200 w-80 max-h-[calc(100vh-120px)] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-3 border-b border-light-200 flex items-center justify-between">
          <h3 className="font-semibold text-light-800 flex items-center gap-2">
            <Route className="w-4 h-4 text-indigo-500" />
            Route Analysis
          </h3>
          <button onClick={onClose} className="p-1 hover:bg-light-100 rounded">
            <X className="w-4 h-4 text-light-500" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {selectedNodes.length < 2 ? (
            <div className="p-4 text-center text-light-500 text-sm">
              <MapPin className="w-6 h-6 mx-auto mb-2 text-light-400" />
              Select 2 or more entities to analyze routes
            </div>
          ) : (
            <div className="p-3 space-y-3">
              {/* Route summary */}
              <div className="bg-indigo-50 rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-indigo-800">Route Summary</span>
                  <button
                    onClick={zoomToRoute}
                    className="text-xs text-indigo-600 hover:text-indigo-700"
                  >
                    Zoom to fit
                  </button>
                </div>

                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div className="flex items-center gap-2">
                    <MapPin className="w-4 h-4 text-indigo-500" />
                    <span className="text-light-600">{selectedNodes.length} stops</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Ruler className="w-4 h-4 text-indigo-500" />
                    <span className="text-light-600">
                      {chronologicalRoute ? formatDistance(chronologicalRoute.totalDistance) : '--'}
                    </span>
                  </div>
                </div>

                {/* Display toggles */}
                <div className="flex gap-2 mt-3">
                  <label className="flex items-center gap-1.5 text-xs">
                    <input
                      type="checkbox"
                      checked={showPath}
                      onChange={(e) => setShowPath(e.target.checked)}
                      className="rounded border-indigo-300"
                    />
                    <span className="text-indigo-700">Show path</span>
                  </label>
                  <label className="flex items-center gap-1.5 text-xs">
                    <input
                      type="checkbox"
                      checked={showWaypoints}
                      onChange={(e) => setShowWaypoints(e.target.checked)}
                      className="rounded border-indigo-300"
                    />
                    <span className="text-indigo-700">Show waypoints</span>
                  </label>
                </div>
              </div>

              {/* Route legs section */}
              <div className="border border-light-200 rounded-lg overflow-hidden">
                <button
                  onClick={() => setExpandedSection(expandedSection === 'route' ? null : 'route')}
                  className="w-full flex items-center justify-between p-2 hover:bg-light-50 transition-colors"
                >
                  <span className="text-sm font-medium text-light-700 flex items-center gap-1">
                    <ArrowRight className="w-4 h-4" />
                    Route Legs ({chronologicalRoute?.legs.length || 0})
                  </span>
                  {expandedSection === 'route' ? (
                    <ChevronUp className="w-4 h-4 text-light-400" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-light-400" />
                  )}
                </button>

                {expandedSection === 'route' && chronologicalRoute && (
                  <div className="border-t border-light-200 max-h-48 overflow-y-auto">
                    {chronologicalRoute.legs.map((leg, idx) => (
                      <div
                        key={idx}
                        className="p-2 border-b border-light-100 last:border-b-0"
                      >
                        <div className="flex items-center gap-2 text-xs">
                          <span className="font-medium text-indigo-600">
                            {idx + 1} → {idx + 2}
                          </span>
                          <span className="text-light-600">
                            {formatDistance(leg.distance)}
                          </span>
                          {leg.timeDiff !== null && (
                            <span className="text-light-500">
                              ({leg.timeDiff} days)
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-1 mt-1 text-xs text-light-500">
                          <span className="truncate max-w-[100px]" title={leg.from.name}>
                            {leg.from.name}
                          </span>
                          <ArrowRight className="w-3 h-3 flex-shrink-0" />
                          <span className="truncate max-w-[100px]" title={leg.to.name}>
                            {leg.to.name}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Intersections section */}
              {intersections.length > 0 && (
                <div className="border border-light-200 rounded-lg overflow-hidden">
                  <button
                    onClick={() => setExpandedSection(expandedSection === 'intersections' ? null : 'intersections')}
                    className="w-full flex items-center justify-between p-2 hover:bg-light-50 transition-colors"
                  >
                    <span className="text-sm font-medium text-light-700 flex items-center gap-1">
                      <Target className="w-4 h-4" />
                      Proximity Events ({intersections.length})
                    </span>
                    {expandedSection === 'intersections' ? (
                      <ChevronUp className="w-4 h-4 text-light-400" />
                    ) : (
                      <ChevronDown className="w-4 h-4 text-light-400" />
                    )}
                  </button>

                  {expandedSection === 'intersections' && (
                    <div className="border-t border-light-200 max-h-48 overflow-y-auto">
                      {intersections.map((intersection, idx) => (
                        <div
                          key={idx}
                          className={`p-2 border-b border-light-100 last:border-b-0 ${
                            intersection.timeClose ? 'bg-red-50' : ''
                          }`}
                        >
                          <div className="flex items-center gap-2 text-xs">
                            <div
                              className="w-2 h-2 rounded-full"
                              style={{ backgroundColor: TYPE_COLORS[intersection.entity1.type] || TYPE_COLORS.default }}
                            />
                            <span className="truncate max-w-[70px]">
                              {intersection.entity1.name}
                            </span>
                            <Users className="w-3 h-3 text-light-400" />
                            <div
                              className="w-2 h-2 rounded-full"
                              style={{ backgroundColor: TYPE_COLORS[intersection.entity2.type] || TYPE_COLORS.default }}
                            />
                            <span className="truncate max-w-[70px]">
                              {intersection.entity2.name}
                            </span>
                          </div>
                          <div className="flex items-center gap-3 mt-1 text-xs text-light-500">
                            <span>{formatDistance(intersection.distance)} apart</span>
                            {intersection.timeDiff !== null && (
                              <span className={intersection.timeClose ? 'text-red-600 font-medium' : ''}>
                                {intersection.timeDiff} days apart
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
