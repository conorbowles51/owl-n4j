import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from 'react-leaflet';
import MarkerClusterGroup from 'react-leaflet-cluster';
import L from 'leaflet';
import { 
  Loader2, 
  MapPin, 
  Filter,
  X,
  Eye,
  EyeOff,
  RefreshCw
} from 'lucide-react';
import { graphAPI } from '../services/api';

// Import Leaflet CSS
import 'leaflet/dist/leaflet.css';
import 'leaflet.markercluster/dist/MarkerCluster.css';
import 'leaflet.markercluster/dist/MarkerCluster.Default.css';

// Fix Leaflet default icon issue with bundlers
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

// Entity type colors (matching graph view)
const TYPE_COLORS = {
  Person: '#3b82f6',      // blue
  Company: '#ef4444',     // red
  Account: '#22c55e',     // green
  Bank: '#f59e0b',        // amber
  Organisation: '#8b5cf6', // purple
  Location: '#06b6d4',    // cyan
  Transaction: '#f97316', // orange
  Meeting: '#ec4899',     // pink
  Payment: '#14b8a6',     // teal
  Email: '#6366f1',       // indigo
  PhoneCall: '#84cc16',   // lime
  Transfer: '#f43f5e',    // rose
  default: '#6b7280',     // gray
};

// Create custom marker icons by type
const createIcon = (type, isSelected) => {
  const color = TYPE_COLORS[type] || TYPE_COLORS.default;
  const size = isSelected ? 14 : 10;
  const borderWidth = isSelected ? 3 : 2;
  const borderColor = isSelected ? '#1e40af' : '#ffffff';
  
  return L.divIcon({
    className: 'custom-marker',
    html: `
      <div style="
        width: ${size}px;
        height: ${size}px;
        background-color: ${color};
        border: ${borderWidth}px solid ${borderColor};
        border-radius: 50%;
        box-shadow: 0 2px 4px rgba(0,0,0,0.3);
        ${isSelected ? 'transform: scale(1.2);' : ''}
      "></div>
    `,
    iconSize: [size + borderWidth * 2, size + borderWidth * 2],
    iconAnchor: [(size + borderWidth * 2) / 2, (size + borderWidth * 2) / 2],
    popupAnchor: [0, -size / 2 - borderWidth],
  });
};

// Component to fit map bounds to markers
function FitBounds({ locations }) {
  const map = useMap();
  
  useEffect(() => {
    if (locations && locations.length > 0) {
      const bounds = L.latLngBounds(
        locations.map(loc => [loc.latitude, loc.longitude])
      );
      map.fitBounds(bounds, { padding: [50, 50], maxZoom: 12 });
    }
  }, [locations, map]);
  
  return null;
}

// Component to center map on selected entities
function CenterOnSelected({ selectedKeys, locations }) {
  const map = useMap();
  const prevSelectedRef = useRef([]);
  
  useEffect(() => {
    // Only center if selection changed and we have selections
    if (selectedKeys.length > 0 && 
        JSON.stringify(selectedKeys) !== JSON.stringify(prevSelectedRef.current)) {
      const selectedLocations = locations.filter(loc => selectedKeys.includes(loc.key));
      if (selectedLocations.length > 0) {
        if (selectedLocations.length === 1) {
          map.setView(
            [selectedLocations[0].latitude, selectedLocations[0].longitude],
            Math.max(map.getZoom(), 10)
          );
        } else {
          const bounds = L.latLngBounds(
            selectedLocations.map(loc => [loc.latitude, loc.longitude])
          );
          map.fitBounds(bounds, { padding: [50, 50], maxZoom: 12 });
        }
      }
    }
    prevSelectedRef.current = selectedKeys;
  }, [selectedKeys, locations, map]);
  
  return null;
}

/**
 * MapView Component
 * 
 * Displays entities with geocoded locations on an interactive map.
 * Supports selection (click), multi-selection (Ctrl+click), and clustering.
 */
export default function MapView({
  selectedNodes = [],
  onNodeClick,
  onBulkNodeSelect,
  onBackgroundClick,
}) {
  const [locations, setLocations] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showFilters, setShowFilters] = useState(false);
  const [hiddenTypes, setHiddenTypes] = useState(new Set());
  const [showConnections, setShowConnections] = useState(false);
  
  const selectedKeys = useMemo(() => 
    selectedNodes.map(n => n.key), 
    [selectedNodes]
  );

  // Load locations data
  const loadLocations = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await graphAPI.getLocations();
      setLocations(data || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadLocations();
  }, [loadLocations]);

  // Filter locations by type
  const filteredLocations = useMemo(() => {
    return locations.filter(loc => !hiddenTypes.has(loc.type));
  }, [locations, hiddenTypes]);

  // Get unique entity types
  const entityTypes = useMemo(() => {
    const types = new Set(locations.map(loc => loc.type));
    return Array.from(types).sort();
  }, [locations]);

  // Handle marker click
  const handleMarkerClick = useCallback((entity, event) => {
    const isMultiSelect = event?.originalEvent?.ctrlKey || event?.originalEvent?.metaKey;
    
    if (onNodeClick) {
      // Pass the original event modifiers to the handler
      onNodeClick({
        key: entity.key,
        id: entity.id || entity.key,
        name: entity.name,
        type: entity.type,
      }, {
        ctrlKey: isMultiSelect,
        metaKey: isMultiSelect,
      });
    }
  }, [onNodeClick]);

  // Handle map click (background)
  const handleMapClick = useCallback((e) => {
    // Only trigger if clicking on the map itself, not a marker
    if (e.originalEvent.target.classList.contains('leaflet-container') ||
        e.originalEvent.target.classList.contains('leaflet-pane') ||
        e.originalEvent.target.tagName === 'svg' ||
        e.originalEvent.target.tagName === 'path') {
      if (onBackgroundClick) {
        onBackgroundClick();
      }
    }
  }, [onBackgroundClick]);

  // Toggle type visibility
  const toggleType = useCallback((type) => {
    setHiddenTypes(prev => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  }, []);

  // Generate connection lines between selected entities
  const connectionLines = useMemo(() => {
    if (!showConnections || selectedKeys.length < 2) return [];
    
    const lines = [];
    const selectedLocations = filteredLocations.filter(loc => 
      selectedKeys.includes(loc.key)
    );
    
    // Draw lines between selected entities that have connections
    selectedLocations.forEach(loc => {
      if (loc.connections) {
        loc.connections.forEach(conn => {
          const connectedLoc = selectedLocations.find(l => l.key === conn.key);
          if (connectedLoc) {
            // Only add each line once (use sorted keys as id)
            const lineId = [loc.key, connectedLoc.key].sort().join('-');
            if (!lines.some(l => l.id === lineId)) {
              lines.push({
                id: lineId,
                positions: [
                  [loc.latitude, loc.longitude],
                  [connectedLoc.latitude, connectedLoc.longitude],
                ],
                type: conn.relationship,
              });
            }
          }
        });
      }
    });
    
    return lines;
  }, [showConnections, selectedKeys, filteredLocations]);

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center bg-light-50">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-8 h-8 text-owl-blue-600 animate-spin" />
          <span className="text-light-600">Loading map data...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center bg-light-50">
        <div className="flex flex-col items-center gap-3 text-center">
          <MapPin className="w-12 h-12 text-red-400" />
          <span className="text-light-800">Failed to load map data</span>
          <span className="text-light-600 text-sm">{error}</span>
          <button
            onClick={loadLocations}
            className="mt-2 px-4 py-2 bg-owl-orange-500 hover:bg-owl-orange-600 rounded-lg text-sm text-white transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (locations.length === 0) {
    return (
      <div className="h-full flex items-center justify-center bg-light-50">
        <div className="flex flex-col items-center gap-3 text-center max-w-md px-4">
          <MapPin className="w-12 h-12 text-light-400" />
          <span className="text-light-800">No geocoded entities</span>
          <span className="text-light-600 text-sm">
            Entities need location data to appear on the map. 
            Ingest documents with location information to use this feature.
          </span>
        </div>
      </div>
    );
  }

  // Default center (world view)
  const defaultCenter = [20, 0];
  const defaultZoom = 2;

  return (
    <div className="h-full relative">
      {/* Map Container */}
      <MapContainer
        center={defaultCenter}
        zoom={defaultZoom}
        className="h-full w-full"
        onClick={handleMapClick}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        
        {/* Fit bounds to all markers on initial load */}
        <FitBounds locations={filteredLocations} />
        
        {/* Center on selected entities */}
        <CenterOnSelected selectedKeys={selectedKeys} locations={filteredLocations} />
        
        {/* Clustered markers */}
        <MarkerClusterGroup
          chunkedLoading
          maxClusterRadius={50}
          spiderfyOnMaxZoom={true}
          showCoverageOnHover={false}
        >
          {filteredLocations.map((entity) => {
            const isSelected = selectedKeys.includes(entity.key);
            return (
              <Marker
                key={entity.key}
                position={[entity.latitude, entity.longitude]}
                icon={createIcon(entity.type, isSelected)}
                eventHandlers={{
                  click: (e) => handleMarkerClick(entity, e),
                }}
              >
                <Popup>
                  <div className="min-w-[200px]">
                    <div className="flex items-center gap-2 mb-2">
                      <div
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: TYPE_COLORS[entity.type] || TYPE_COLORS.default }}
                      />
                      <span className="font-semibold text-gray-900">{entity.name}</span>
                    </div>
                    <div className="text-xs text-gray-500 mb-2">{entity.type}</div>
                    {entity.location_formatted && (
                      <div className="text-sm text-gray-600 mb-2">
                        <MapPin className="w-3 h-3 inline mr-1" />
                        {entity.location_formatted}
                      </div>
                    )}
                    {entity.summary && (
                      <div className="text-sm text-gray-700 mt-2 border-t pt-2">
                        {entity.summary.length > 150 
                          ? entity.summary.substring(0, 150) + '...' 
                          : entity.summary}
                      </div>
                    )}
                    {entity.date && (
                      <div className="text-xs text-gray-500 mt-2">
                        Date: {entity.date}
                      </div>
                    )}
                  </div>
                </Popup>
              </Marker>
            );
          })}
        </MarkerClusterGroup>
        
        {/* Connection lines between selected entities */}
        {connectionLines.map(line => (
          <Polyline
            key={line.id}
            positions={line.positions}
            color="#3b82f6"
            weight={2}
            opacity={0.6}
            dashArray="5, 10"
          />
        ))}
      </MapContainer>
      
      {/* Controls overlay */}
      <div className="absolute top-4 left-4 z-[1000] flex flex-col gap-2">
        {/* Stats badge */}
        <div className="bg-white/90 backdrop-blur-sm rounded-lg px-3 py-2 shadow-md border border-light-200">
          <div className="flex items-center gap-2 text-sm">
            <MapPin className="w-4 h-4 text-owl-blue-600" />
            <span className="text-light-700">
              {filteredLocations.length} entities with locations
            </span>
          </div>
        </div>
        
        {/* Filter toggle */}
        <button
          onClick={() => setShowFilters(!showFilters)}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg shadow-md border transition-colors ${
            showFilters 
              ? 'bg-owl-blue-100 border-owl-blue-300 text-owl-blue-900' 
              : 'bg-white/90 backdrop-blur-sm border-light-200 text-light-700 hover:bg-light-50'
          }`}
        >
          <Filter className="w-4 h-4" />
          <span className="text-sm">Filters</span>
          {hiddenTypes.size > 0 && (
            <span className="bg-owl-orange-500 text-white text-xs px-1.5 py-0.5 rounded-full">
              {hiddenTypes.size}
            </span>
          )}
        </button>
        
        {/* Show connections toggle */}
        <button
          onClick={() => setShowConnections(!showConnections)}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg shadow-md border transition-colors ${
            showConnections 
              ? 'bg-owl-blue-100 border-owl-blue-300 text-owl-blue-900' 
              : 'bg-white/90 backdrop-blur-sm border-light-200 text-light-700 hover:bg-light-50'
          }`}
          title="Show connection lines between selected entities"
        >
          {showConnections ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
          <span className="text-sm">Connections</span>
        </button>
        
        {/* Refresh button */}
        <button
          onClick={loadLocations}
          className="flex items-center gap-2 px-3 py-2 bg-white/90 backdrop-blur-sm rounded-lg shadow-md border border-light-200 text-light-700 hover:bg-light-50 transition-colors"
          title="Refresh map data"
        >
          <RefreshCw className="w-4 h-4" />
          <span className="text-sm">Refresh</span>
        </button>
      </div>
      
      {/* Filter panel */}
      {showFilters && (
        <div className="absolute top-4 left-40 z-[1000] bg-white/95 backdrop-blur-sm rounded-lg shadow-lg border border-light-200 p-4 max-h-[400px] overflow-y-auto">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-light-800">Entity Types</h3>
            <button
              onClick={() => setShowFilters(false)}
              className="p-1 hover:bg-light-100 rounded"
            >
              <X className="w-4 h-4 text-light-500" />
            </button>
          </div>
          
          <div className="space-y-2">
            {entityTypes.map(type => {
              const count = locations.filter(l => l.type === type).length;
              const isHidden = hiddenTypes.has(type);
              
              return (
                <label
                  key={type}
                  className="flex items-center gap-2 cursor-pointer hover:bg-light-50 px-2 py-1 rounded"
                >
                  <input
                    type="checkbox"
                    checked={!isHidden}
                    onChange={() => toggleType(type)}
                    className="rounded border-light-300"
                  />
                  <div
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: TYPE_COLORS[type] || TYPE_COLORS.default }}
                  />
                  <span className={`text-sm flex-1 ${isHidden ? 'text-light-400' : 'text-light-700'}`}>
                    {type}
                  </span>
                  <span className="text-xs text-light-500">{count}</span>
                </label>
              );
            })}
          </div>
          
          <div className="mt-3 pt-3 border-t border-light-200 flex gap-2">
            <button
              onClick={() => setHiddenTypes(new Set())}
              className="flex-1 px-3 py-1.5 text-xs bg-light-100 hover:bg-light-200 rounded transition-colors"
            >
              Show All
            </button>
            <button
              onClick={() => setHiddenTypes(new Set(entityTypes))}
              className="flex-1 px-3 py-1.5 text-xs bg-light-100 hover:bg-light-200 rounded transition-colors"
            >
              Hide All
            </button>
          </div>
        </div>
      )}
      
      {/* Legend */}
      <div className="absolute bottom-4 right-4 z-[1000] bg-white/90 backdrop-blur-sm rounded-lg shadow-md border border-light-200 p-3">
        <div className="text-xs text-light-600 mb-2">Legend</div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          {entityTypes.slice(0, 8).map(type => (
            <div key={type} className="flex items-center gap-1.5">
              <div
                className="w-2.5 h-2.5 rounded-full"
                style={{ backgroundColor: TYPE_COLORS[type] || TYPE_COLORS.default }}
              />
              <span className="text-xs text-light-700">{type}</span>
            </div>
          ))}
          {entityTypes.length > 8 && (
            <div className="col-span-2 text-xs text-light-500 mt-1">
              +{entityTypes.length - 8} more types
            </div>
          )}
        </div>
      </div>
      
      {/* Selection info */}
      {selectedKeys.length > 0 && (
        <div className="absolute bottom-4 left-4 z-[1000] bg-white/90 backdrop-blur-sm rounded-lg shadow-md border border-light-200 px-3 py-2">
          <div className="text-sm text-light-700">
            <span className="font-medium">{selectedKeys.length}</span> selected
            <span className="text-light-500 text-xs ml-2">
              (Ctrl+click for multi-select)
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

