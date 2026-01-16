import React, { useState, useMemo } from 'react';
import { useMap } from 'react-leaflet';
import {
  Flame,
  X,
  ChevronDown,
  ChevronUp,
  MapPin,
  ZoomIn,
  MousePointer
} from 'lucide-react';
import { gridCluster, formatDistance } from '../../utils/geo';

// Entity type colors (matching MapView)
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
 * HotspotPanel Component
 *
 * Displays a ranked list of high-activity geographic areas (hotspots).
 * Uses grid-based clustering to identify areas with many entities.
 */
export default function HotspotPanel({
  locations = [],
  onSelectEntities,
  isActive = false,
  onClose,
}) {
  const map = useMap();
  const [gridSize, setGridSize] = useState(10); // km
  const [expandedHotspot, setExpandedHotspot] = useState(null);

  // Calculate hotspots using grid clustering
  const hotspots = useMemo(() => {
    if (!locations || locations.length === 0) return [];
    return gridCluster(locations, gridSize).slice(0, 20); // Top 20 hotspots
  }, [locations, gridSize]);

  // Count entity types in a hotspot
  const getTypeCounts = (entities) => {
    const counts = {};
    entities.forEach(e => {
      const type = e.type || 'Other';
      counts[type] = (counts[type] || 0) + 1;
    });
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 4);
  };

  // Zoom to a hotspot
  const zoomToHotspot = (hotspot) => {
    map.setView([hotspot.centerLat, hotspot.centerLng], 12, { animate: true });
  };

  // Select all entities in a hotspot
  const selectHotspot = (hotspot) => {
    if (onSelectEntities) {
      onSelectEntities(hotspot.entities.map(e => ({
        key: e.key,
        id: e.id || e.key,
        name: e.name,
        type: e.type,
      })));
    }
  };

  // Calculate "heat" score (normalized 0-1)
  const maxCount = hotspots.length > 0 ? hotspots[0].count : 1;
  const getHeatScore = (count) => count / maxCount;

  // Get heat color gradient
  const getHeatColor = (score) => {
    // Gradient from yellow to orange to red
    if (score > 0.66) return '#ef4444'; // red
    if (score > 0.33) return '#f97316'; // orange
    return '#eab308'; // yellow
  };

  if (!isActive) return null;

  return (
    <div className="absolute top-4 right-4 z-[1000] bg-white/95 backdrop-blur-sm rounded-lg shadow-lg border border-light-200 w-80 max-h-[calc(100vh-120px)] overflow-hidden flex flex-col">
      {/* Header */}
      <div className="p-3 border-b border-light-200 flex items-center justify-between">
        <h3 className="font-semibold text-light-800 flex items-center gap-2">
          <Flame className="w-4 h-4 text-orange-500" />
          Activity Hotspots
        </h3>
        <button
          onClick={onClose}
          className="p-1 hover:bg-light-100 rounded"
        >
          <X className="w-4 h-4 text-light-500" />
        </button>
      </div>

      {/* Grid size control */}
      <div className="px-3 py-2 border-b border-light-200">
        <label className="text-xs font-medium text-light-600 block mb-1.5">
          Grid Size: {gridSize} km
        </label>
        <input
          type="range"
          min="2"
          max="50"
          value={gridSize}
          onChange={(e) => setGridSize(parseInt(e.target.value))}
          className="w-full h-2 bg-light-200 rounded-lg appearance-none cursor-pointer accent-orange-500"
        />
        <div className="flex justify-between text-xs text-light-500 mt-1">
          <span>Fine</span>
          <span>Coarse</span>
        </div>
      </div>

      {/* Hotspot list */}
      <div className="flex-1 overflow-y-auto p-2">
        {hotspots.length > 0 ? (
          <div className="space-y-2">
            {hotspots.map((hotspot, idx) => {
              const score = getHeatScore(hotspot.count);
              const heatColor = getHeatColor(score);
              const isExpanded = expandedHotspot === hotspot.key;
              const typeCounts = getTypeCounts(hotspot.entities);

              return (
                <div
                  key={hotspot.key}
                  className="bg-light-50 rounded-lg overflow-hidden"
                >
                  {/* Hotspot header */}
                  <div
                    className="p-2 cursor-pointer hover:bg-light-100 transition-colors"
                    onClick={() => setExpandedHotspot(isExpanded ? null : hotspot.key)}
                  >
                    <div className="flex items-center gap-2">
                      {/* Rank badge */}
                      <div
                        className="w-6 h-6 rounded-full flex items-center justify-center text-white text-xs font-bold"
                        style={{ backgroundColor: heatColor }}
                      >
                        {idx + 1}
                      </div>

                      {/* Info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1">
                          <span className="font-medium text-sm text-light-800">
                            {hotspot.count} entities
                          </span>
                          {/* Heat bar */}
                          <div className="flex-1 h-1.5 bg-light-200 rounded-full overflow-hidden ml-2">
                            <div
                              className="h-full rounded-full"
                              style={{
                                width: `${score * 100}%`,
                                backgroundColor: heatColor,
                              }}
                            />
                          </div>
                        </div>

                        {/* Type preview */}
                        <div className="flex items-center gap-1 mt-1">
                          {typeCounts.map(([type, count]) => (
                            <span
                              key={type}
                              className="inline-flex items-center gap-0.5 text-xs"
                              title={`${type}: ${count}`}
                            >
                              <div
                                className="w-2 h-2 rounded-full"
                                style={{ backgroundColor: TYPE_COLORS[type] || TYPE_COLORS.default }}
                              />
                              <span className="text-light-500">{count}</span>
                            </span>
                          ))}
                        </div>
                      </div>

                      {/* Expand icon */}
                      {isExpanded ? (
                        <ChevronUp className="w-4 h-4 text-light-400" />
                      ) : (
                        <ChevronDown className="w-4 h-4 text-light-400" />
                      )}
                    </div>
                  </div>

                  {/* Expanded content */}
                  {isExpanded && (
                    <div className="px-2 pb-2 border-t border-light-200">
                      {/* Action buttons */}
                      <div className="flex gap-2 mt-2 mb-2">
                        <button
                          onClick={() => zoomToHotspot(hotspot)}
                          className="flex-1 px-2 py-1.5 text-xs bg-blue-100 text-blue-700 rounded hover:bg-blue-200 transition-colors flex items-center justify-center gap-1"
                        >
                          <ZoomIn className="w-3 h-3" />
                          Zoom to
                        </button>
                        <button
                          onClick={() => selectHotspot(hotspot)}
                          className="flex-1 px-2 py-1.5 text-xs bg-orange-100 text-orange-700 rounded hover:bg-orange-200 transition-colors flex items-center justify-center gap-1"
                        >
                          <MousePointer className="w-3 h-3" />
                          Select all
                        </button>
                      </div>

                      {/* Entity list */}
                      <div className="space-y-1 max-h-32 overflow-y-auto">
                        {hotspot.entities.slice(0, 10).map(entity => (
                          <div
                            key={entity.key}
                            className="flex items-center gap-1.5 text-xs py-0.5"
                          >
                            <div
                              className="w-2 h-2 rounded-full flex-shrink-0"
                              style={{ backgroundColor: TYPE_COLORS[entity.type] || TYPE_COLORS.default }}
                            />
                            <span className="truncate text-light-700">
                              {entity.name}
                            </span>
                          </div>
                        ))}
                        {hotspot.entities.length > 10 && (
                          <div className="text-xs text-light-500 text-center">
                            +{hotspot.entities.length - 10} more
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="text-sm text-light-500 text-center py-8">
            <MapPin className="w-6 h-6 mx-auto mb-2 text-light-400" />
            No hotspots detected
            <p className="text-xs mt-1">
              Try adjusting the grid size
            </p>
          </div>
        )}
      </div>

      {/* Summary footer */}
      {hotspots.length > 0 && (
        <div className="p-2 border-t border-light-200 bg-light-50">
          <div className="text-xs text-light-600 text-center">
            {hotspots.length} hotspots found covering {locations.length} entities
          </div>
        </div>
      )}
    </div>
  );
}
