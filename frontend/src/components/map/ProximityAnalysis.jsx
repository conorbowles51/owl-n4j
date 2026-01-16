import React, { useState, useCallback, useMemo } from 'react';
import { Circle, useMapEvents } from 'react-leaflet';
import {
  Crosshair,
  X,
  Target,
  Ruler,
  ChevronDown,
  ChevronUp,
  MapPin
} from 'lucide-react';
import {
  findEntitiesWithinRadius,
  formatDistance,
  calculatePairwiseDistances
} from '../../utils/geo';

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
 * ProximityAnalysis Component
 *
 * Provides tools for proximity-based analysis:
 * 1. Click on map to define a center point and radius
 * 2. Find all entities within the radius
 * 3. Calculate distances between selected entities
 */
export default function ProximityAnalysis({
  locations = [],
  selectedNodes = [],
  onSelectEntities,
  isActive = false,
  onClose,
}) {
  const [centerPoint, setCenterPoint] = useState(null);
  const [radiusKm, setRadiusKm] = useState(5);
  const [isDrawing, setIsDrawing] = useState(false);
  const [showResults, setShowResults] = useState(true);
  const [mode, setMode] = useState('radius'); // 'radius' | 'distance'

  // Handle map clicks when in drawing mode
  useMapEvents({
    click(e) {
      if (isActive && isDrawing) {
        setCenterPoint({ lat: e.latlng.lat, lng: e.latlng.lng });
        setIsDrawing(false);
      }
    },
  });

  // Find entities within radius
  const entitiesInRadius = useMemo(() => {
    if (!centerPoint) return [];
    return findEntitiesWithinRadius(centerPoint, radiusKm, locations);
  }, [centerPoint, radiusKm, locations]);

  // Calculate distances between selected entities
  const selectedDistances = useMemo(() => {
    const selectedLocs = locations.filter(loc =>
      selectedNodes.some(n => n.key === loc.key)
    );
    if (selectedLocs.length < 2) return [];
    return calculatePairwiseDistances(selectedLocs);
  }, [locations, selectedNodes]);

  // Group entities by type
  const entitiesByType = useMemo(() => {
    const groups = {};
    entitiesInRadius.forEach(entity => {
      const type = entity.type || 'Other';
      if (!groups[type]) groups[type] = [];
      groups[type].push(entity);
    });
    return groups;
  }, [entitiesInRadius]);

  // Handle selecting all entities in radius
  const handleSelectAll = useCallback(() => {
    if (onSelectEntities && entitiesInRadius.length > 0) {
      onSelectEntities(entitiesInRadius.map(e => ({
        key: e.key,
        id: e.id || e.key,
        name: e.name,
        type: e.type,
      })));
    }
  }, [entitiesInRadius, onSelectEntities]);

  // Start drawing mode
  const startDrawing = useCallback(() => {
    setIsDrawing(true);
    setCenterPoint(null);
  }, []);

  // Clear the current selection
  const clearSelection = useCallback(() => {
    setCenterPoint(null);
    setIsDrawing(false);
  }, []);

  if (!isActive) return null;

  return (
    <>
      {/* Radius circle on map */}
      {centerPoint && (
        <Circle
          center={[centerPoint.lat, centerPoint.lng]}
          radius={radiusKm * 1000} // Convert km to meters
          pathOptions={{
            color: '#3b82f6',
            fillColor: '#3b82f6',
            fillOpacity: 0.1,
            weight: 2,
            dashArray: '5, 5',
          }}
        />
      )}

      {/* Control panel */}
      <div className="absolute top-4 right-4 z-[1000] bg-white/95 backdrop-blur-sm rounded-lg shadow-lg border border-light-200 w-80 max-h-[calc(100vh-120px)] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-3 border-b border-light-200 flex items-center justify-between">
          <h3 className="font-semibold text-light-800 flex items-center gap-2">
            <Target className="w-4 h-4 text-blue-500" />
            Proximity Analysis
          </h3>
          <button
            onClick={onClose}
            className="p-1 hover:bg-light-100 rounded"
          >
            <X className="w-4 h-4 text-light-500" />
          </button>
        </div>

        {/* Mode tabs */}
        <div className="flex border-b border-light-200">
          <button
            onClick={() => setMode('radius')}
            className={`flex-1 px-3 py-2 text-sm font-medium transition-colors ${
              mode === 'radius'
                ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50'
                : 'text-light-600 hover:text-light-800'
            }`}
          >
            <Crosshair className="w-3.5 h-3.5 inline mr-1.5" />
            Radius Search
          </button>
          <button
            onClick={() => setMode('distance')}
            className={`flex-1 px-3 py-2 text-sm font-medium transition-colors ${
              mode === 'distance'
                ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50'
                : 'text-light-600 hover:text-light-800'
            }`}
          >
            <Ruler className="w-3.5 h-3.5 inline mr-1.5" />
            Distances
          </button>
        </div>

        {/* Content based on mode */}
        <div className="flex-1 overflow-y-auto">
          {mode === 'radius' ? (
            <div className="p-3 space-y-4">
              {/* Instructions and controls */}
              <div className="space-y-3">
                {/* Radius slider */}
                <div>
                  <label className="text-xs font-medium text-light-600 block mb-1.5">
                    Search Radius: {radiusKm} km
                  </label>
                  <input
                    type="range"
                    min="1"
                    max="50"
                    value={radiusKm}
                    onChange={(e) => setRadiusKm(parseInt(e.target.value))}
                    className="w-full h-2 bg-light-200 rounded-lg appearance-none cursor-pointer accent-blue-500"
                  />
                </div>

                {/* Action buttons */}
                <div className="flex gap-2">
                  <button
                    onClick={startDrawing}
                    className={`flex-1 px-3 py-2 text-sm rounded-lg transition-colors flex items-center justify-center gap-1.5 ${
                      isDrawing
                        ? 'bg-blue-500 text-white'
                        : 'bg-blue-100 text-blue-700 hover:bg-blue-200'
                    }`}
                  >
                    <Crosshair className="w-4 h-4" />
                    {isDrawing ? 'Click on map...' : 'Set Center Point'}
                  </button>
                  {centerPoint && (
                    <button
                      onClick={clearSelection}
                      className="px-3 py-2 text-sm bg-light-100 text-light-700 rounded-lg hover:bg-light-200 transition-colors"
                    >
                      Clear
                    </button>
                  )}
                </div>
              </div>

              {/* Results */}
              {centerPoint && (
                <div className="border-t border-light-200 pt-3">
                  <div className="flex items-center justify-between mb-2">
                    <button
                      onClick={() => setShowResults(!showResults)}
                      className="text-sm font-medium text-light-700 flex items-center gap-1"
                    >
                      {showResults ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                      Found {entitiesInRadius.length} entities
                    </button>
                    {entitiesInRadius.length > 0 && (
                      <button
                        onClick={handleSelectAll}
                        className="text-xs text-blue-600 hover:text-blue-700"
                      >
                        Select all
                      </button>
                    )}
                  </div>

                  {showResults && entitiesInRadius.length > 0 && (
                    <div className="space-y-2 max-h-60 overflow-y-auto">
                      {Object.entries(entitiesByType).map(([type, entities]) => (
                        <div key={type} className="bg-light-50 rounded p-2">
                          <div className="flex items-center gap-1.5 text-xs font-medium text-light-600 mb-1">
                            <div
                              className="w-2.5 h-2.5 rounded-full"
                              style={{ backgroundColor: TYPE_COLORS[type] || TYPE_COLORS.default }}
                            />
                            {type} ({entities.length})
                          </div>
                          <div className="space-y-1">
                            {entities.slice(0, 5).map(entity => (
                              <div
                                key={entity.key}
                                className="flex items-center justify-between text-xs"
                              >
                                <span className="truncate text-light-700 max-w-[160px]">
                                  {entity.name}
                                </span>
                                <span className="text-light-500 ml-2">
                                  {formatDistance(entity.distance)}
                                </span>
                              </div>
                            ))}
                            {entities.length > 5 && (
                              <div className="text-xs text-light-500 text-center">
                                +{entities.length - 5} more
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {showResults && entitiesInRadius.length === 0 && (
                    <div className="text-sm text-light-500 text-center py-4">
                      No entities found within {radiusKm} km
                    </div>
                  )}
                </div>
              )}

              {!centerPoint && !isDrawing && (
                <div className="text-sm text-light-500 text-center py-4 bg-light-50 rounded-lg">
                  <MapPin className="w-5 h-5 mx-auto mb-1 text-light-400" />
                  Click "Set Center Point" then click on the map to search for nearby entities
                </div>
              )}
            </div>
          ) : (
            /* Distance mode */
            <div className="p-3">
              {selectedDistances.length > 0 ? (
                <div className="space-y-2">
                  <div className="text-xs text-light-600 mb-2">
                    Distances between {selectedNodes.length} selected entities:
                  </div>
                  <div className="space-y-1.5 max-h-80 overflow-y-auto">
                    {selectedDistances.map((pair, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between text-sm bg-light-50 rounded px-2 py-1.5"
                      >
                        <div className="flex items-center gap-1 min-w-0 flex-1">
                          <div
                            className="w-2 h-2 rounded-full flex-shrink-0"
                            style={{ backgroundColor: TYPE_COLORS[pair.from.type] || TYPE_COLORS.default }}
                          />
                          <span className="truncate text-light-700 max-w-[80px]" title={pair.from.name}>
                            {pair.from.name}
                          </span>
                          <span className="text-light-400 mx-1">→</span>
                          <div
                            className="w-2 h-2 rounded-full flex-shrink-0"
                            style={{ backgroundColor: TYPE_COLORS[pair.to.type] || TYPE_COLORS.default }}
                          />
                          <span className="truncate text-light-700 max-w-[80px]" title={pair.to.name}>
                            {pair.to.name}
                          </span>
                        </div>
                        <span className="text-blue-600 font-medium ml-2 whitespace-nowrap">
                          {formatDistance(pair.distance)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="text-sm text-light-500 text-center py-8 bg-light-50 rounded-lg">
                  <Ruler className="w-5 h-5 mx-auto mb-1 text-light-400" />
                  Select 2 or more entities on the map to calculate distances between them
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
