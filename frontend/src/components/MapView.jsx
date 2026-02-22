import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap, Tooltip } from 'react-leaflet';
import MarkerClusterGroup from 'react-leaflet-cluster';
import L from 'leaflet';
import {
  Loader2,
  MapPin,
  Filter,
  X,
  Eye,
  EyeOff,
  RefreshCw,
  ArrowRight,
  ExternalLink,
  Link2,
  Tag,
  Flame,
  Settings2,
  Target,
  TrendingUp,
  Timer,
  Route,
  Pencil,
  Trash2,
  Check,
} from 'lucide-react';
import { graphAPI } from '../services/api';
import HeatmapLayer from './map/HeatmapLayer';
import ProximityAnalysis from './map/ProximityAnalysis';
import HotspotPanel from './map/HotspotPanel';
import TimeControl from './map/TimeControl';
import RouteAnalysis from './map/RouteAnalysis';

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

// Relationship type colors for connection lines
const RELATIONSHIP_COLORS = {
  OWNS_ACCOUNT: '#22c55e',    // green
  OWNS_COMPANY: '#3b82f6',    // blue
  TRANSFERRED_TO: '#f97316',  // orange
  MENTIONED_IN: '#6b7280',    // gray
  ASSOCIATED_WITH: '#8b5cf6', // purple
  RELATED_TO: '#6b7280',      // gray
  PART_OF_CASE: '#64748b',    // slate
  CALLED: '#84cc16',          // lime
  EMAILED: '#6366f1',         // indigo
  MET_WITH: '#ec4899',        // pink
  ATTENDED: '#06b6d4',        // cyan
  SIGNED: '#f59e0b',          // amber
  TRIGGERED: '#ef4444',       // red
  ISSUED_TO: '#14b8a6',       // teal
  RECEIVED_FROM: '#f43f5e',   // rose
  WORKS_FOR: '#3b82f6',       // blue
  DIRECTOR_OF: '#8b5cf6',     // purple
  SHAREHOLDER_OF: '#22c55e',  // green
  default: '#64748b',         // slate
};

// Helper to count entity types in a cluster
const countClusterTypes = (cluster) => {
  const markers = cluster.getAllChildMarkers();
  const typeCounts = {};
  markers.forEach(marker => {
    const type = marker.options.entityType || 'default';
    typeCounts[type] = (typeCounts[type] || 0) + 1;
  });
  return typeCounts;
};

// Helper to get dominant type (most common)
const getDominantType = (typeCounts) => {
  let maxCount = 0;
  let dominantType = 'default';
  Object.entries(typeCounts).forEach(([type, count]) => {
    if (count > maxCount) {
      maxCount = count;
      dominantType = type;
    }
  });
  return dominantType;
};

// Create custom cluster icon with type distribution
const createClusterIcon = (cluster) => {
  const count = cluster.getChildCount();
  const typeCounts = countClusterTypes(cluster);
  const dominantType = getDominantType(typeCounts);
  const dominantColor = TYPE_COLORS[dominantType] || TYPE_COLORS.default;
  const typeCount = Object.keys(typeCounts).length;

  // Size based on count
  const size = count < 10 ? 36 : count < 50 ? 44 : count < 100 ? 52 : 60;

  // Generate mini pie segments for type distribution (simplified)
  const types = Object.entries(typeCounts).slice(0, 4);
  const total = types.reduce((sum, [, c]) => sum + c, 0);
  let segments = '';
  let currentAngle = 0;

  if (types.length > 1) {
    types.forEach(([type, typeCount]) => {
      const angle = (typeCount / total) * 360;
      const color = TYPE_COLORS[type] || TYPE_COLORS.default;
      segments += `${color} ${currentAngle}deg ${currentAngle + angle}deg,`;
      currentAngle += angle;
    });
    segments = segments.slice(0, -1); // Remove trailing comma
  }

  const background = types.length > 1
    ? `conic-gradient(${segments})`
    : dominantColor;

  return L.divIcon({
    className: 'custom-cluster-icon',
    html: `
      <div style="
        width: ${size}px;
        height: ${size}px;
        background: ${background};
        border: 3px solid white;
        border-radius: 50%;
        box-shadow: 0 3px 8px rgba(0,0,0,0.3);
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        position: relative;
      ">
        <div style="
          background: white;
          border-radius: 50%;
          width: ${size - 12}px;
          height: ${size - 12}px;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
        ">
          <span style="
            font-size: ${count >= 100 ? 11 : 13}px;
            font-weight: 700;
            color: ${dominantColor};
            line-height: 1;
          ">${count}</span>
          ${typeCount > 1 ? `
            <span style="
              font-size: 8px;
              color: #6b7280;
              line-height: 1;
              margin-top: 1px;
            ">${typeCount} types</span>
          ` : ''}
        </div>
      </div>
    `,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
};

// Create custom marker icons by type with hover support
const createIcon = (type, isSelected, isHovered = false) => {
  const color = TYPE_COLORS[type] || TYPE_COLORS.default;
  // Size hierarchy: selected > hovered > normal
  const size = isSelected ? 14 : isHovered ? 12 : 10;
  const borderWidth = isSelected ? 3 : isHovered ? 2.5 : 2;
  const borderColor = isSelected ? '#1e40af' : isHovered ? '#374151' : '#ffffff';
  const scale = isSelected ? 1.2 : isHovered ? 1.1 : 1;
  const shadow = isHovered || isSelected
    ? '0 4px 8px rgba(0,0,0,0.4)'
    : '0 2px 4px rgba(0,0,0,0.3)';

  return L.divIcon({
    className: 'custom-marker',
    html: `
      <div style="
        width: ${size}px;
        height: ${size}px;
        background-color: ${color};
        border: ${borderWidth}px solid ${borderColor};
        border-radius: 50%;
        box-shadow: ${shadow};
        transform: scale(${scale});
        transition: all 0.15s ease-out;
        ${isHovered ? 'cursor: pointer;' : ''}
      "></div>
    `,
    iconSize: [size + borderWidth * 2, size + borderWidth * 2],
    iconAnchor: [(size + borderWidth * 2) / 2, (size + borderWidth * 2) / 2],
    popupAnchor: [0, -size / 2 - borderWidth],
  });
};

// Connection line component with tooltip and optional arrow
function ConnectionLine({ line, showLabel }) {
  const map = useMap();
  const [labelPosition, setLabelPosition] = useState(null);

  // Calculate midpoint for label
  useEffect(() => {
    if (showLabel && line.positions.length >= 2) {
      const mid = [
        (line.positions[0][0] + line.positions[1][0]) / 2,
        (line.positions[0][1] + line.positions[1][1]) / 2,
      ];
      setLabelPosition(mid);
    }
  }, [line, showLabel]);

  // Calculate arrow points (small triangle at midpoint pointing toward target)
  const arrowPoints = useMemo(() => {
    if (line.positions.length < 2) return null;
    const [start, end] = line.positions;
    const midLat = (start[0] + end[0]) / 2;
    const midLng = (start[1] + end[1]) / 2;

    // Calculate angle of the line
    const dx = end[1] - start[1];
    const dy = end[0] - start[0];
    const angle = Math.atan2(dy, dx);

    // Arrow size (in degrees - small)
    const arrowSize = 0.015;

    // Calculate arrow points
    const tip = [midLat + Math.sin(angle) * arrowSize, midLng + Math.cos(angle) * arrowSize];
    const left = [
      midLat - Math.sin(angle - Math.PI / 6) * arrowSize * 0.6,
      midLng - Math.cos(angle - Math.PI / 6) * arrowSize * 0.6,
    ];
    const right = [
      midLat - Math.sin(angle + Math.PI / 6) * arrowSize * 0.6,
      midLng - Math.cos(angle + Math.PI / 6) * arrowSize * 0.6,
    ];

    return [left, tip, right];
  }, [line.positions]);

  // Format relationship name for display
  const formatRelationship = (rel) => {
    return rel.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, l => l.toUpperCase());
  };

  return (
    <>
      {/* Main connection line */}
      <Polyline
        positions={line.positions}
        color={line.color}
        weight={2.5}
        opacity={0.7}
        dashArray="6, 8"
      >
        <Tooltip sticky direction="top" offset={[0, -5]} opacity={0.95}>
          <div className="text-xs whitespace-nowrap">
            <div className="font-medium" style={{ color: line.color }}>
              {formatRelationship(line.relationship)}
            </div>
            <div className="text-gray-600 mt-0.5">
              {line.sourceName} → {line.targetName}
            </div>
          </div>
        </Tooltip>
      </Polyline>

      {/* Direction arrow */}
      {arrowPoints && (
        <Polyline
          positions={arrowPoints}
          color={line.color}
          weight={2.5}
          opacity={0.8}
          fill={true}
          fillColor={line.color}
          fillOpacity={0.8}
        />
      )}

      {/* Relationship label at midpoint */}
      {showLabel && labelPosition && (
        <Marker
          position={labelPosition}
          icon={L.divIcon({
            className: 'connection-label',
            html: `
              <div style="
                background: white;
                border: 1px solid ${line.color};
                color: ${line.color};
                padding: 1px 6px;
                border-radius: 10px;
                font-size: 10px;
                font-weight: 500;
                white-space: nowrap;
                box-shadow: 0 1px 3px rgba(0,0,0,0.2);
                transform: translate(-50%, -50%);
              ">
                ${formatRelationship(line.relationship)}
              </div>
            `,
            iconSize: [0, 0],
            iconAnchor: [0, 0],
          })}
          interactive={false}
        />
      )}
    </>
  );
}

// Call invalidateSize when map is shown or resized (e.g. in modal/tab) so Leaflet recalculates dimensions
function InvalidateSizeOnMount() {
  const map = useMap();
  useEffect(() => {
    const container = map.getContainer();
    if (!container) return;
    const invalidate = () => {
      map.invalidateSize();
    };
    const ro = new ResizeObserver(() => {
      invalidate();
    });
    ro.observe(container);
    invalidate();
    const t = setTimeout(invalidate, 150);
    const t2 = setTimeout(invalidate, 500);
    return () => {
      ro.disconnect();
      clearTimeout(t);
      clearTimeout(t2);
    };
  }, [map]);
  return null;
}

// Component to fit map bounds to markers
function FitBounds({ locations }) {
  const map = useMap();

  useEffect(() => {
    if (!locations || locations.length === 0) return;
    const pts = locations.map(loc => [loc.latitude, loc.longitude]);
    if (pts.length === 1) {
      map.setView(pts[0], 12);
      return;
    }
    const bounds = L.latLngBounds(pts);
    map.fitBounds(bounds, { padding: [50, 50], maxZoom: 12 });
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
  locations: externalLocations = null, // Allow passing locations directly
  caseId, // REQUIRED: Case ID for case-specific data
  containerStyle, // Optional: explicit style for MapContainer (e.g. minHeight in modals)
}) {
  const [locations, setLocations] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showFilters, setShowFilters] = useState(false);
  const [hiddenTypes, setHiddenTypes] = useState(new Set());
  const [showConnections, setShowConnections] = useState(false);
  const [showRelationshipLabels, setShowRelationshipLabels] = useState(true);
  const [hoveredEntityKey, setHoveredEntityKey] = useState(null);
  const [showHeatmap, setShowHeatmap] = useState(false);
  const [showHeatmapSettings, setShowHeatmapSettings] = useState(false);
  const [heatmapSettings, setHeatmapSettings] = useState({
    radius: 25,
    blur: 15,
    weightBy: 'uniform',
  });
  const [showProximityTool, setShowProximityTool] = useState(false);
  const [showHotspotPanel, setShowHotspotPanel] = useState(false);
  const [showTimeControl, setShowTimeControl] = useState(false);
  const [animationTime, setAnimationTime] = useState(null);
  const [showRouteAnalysis, setShowRouteAnalysis] = useState(false);
  const [contextMenu, setContextMenu] = useState(null); // { x, y, entity }
  const [editLocationModal, setEditLocationModal] = useState(null); // { entity, locationName, latitude, longitude }
  const [savingLocation, setSavingLocation] = useState(false);
  const [rescanRunning, setRescanRunning] = useState(false);
  const [rescanResult, setRescanResult] = useState(null);

  const selectedKeys = useMemo(() =>
    selectedNodes.map(n => n.key),
    [selectedNodes]
  );

  // Load locations data
  const loadLocations = useCallback(async () => {
    if (!caseId) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await graphAPI.getLocations(caseId);
      setLocations(data || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [caseId]);

  const handleRescanLocations = useCallback(async () => {
    if (!caseId || rescanRunning) return;
    setRescanRunning(true);
    setRescanResult(null);
    try {
      const result = await graphAPI.rescanLocations(caseId);
      setRescanResult(result);
      if (result?.success) {
        await loadLocations();
      }
    } catch (err) {
      setRescanResult({ success: false, error: err.message || 'Rescan failed' });
    } finally {
      setRescanRunning(false);
      setTimeout(() => setRescanResult(null), 12000);
    }
  }, [caseId, rescanRunning, loadLocations]);

  // Use external locations if provided, otherwise load from API
  useEffect(() => {
    if (externalLocations !== null) {
      setLocations(externalLocations);
      setIsLoading(false);
    } else {
      loadLocations();
    }
  }, [externalLocations, loadLocations]);

  // Filter locations by type and time
  const filteredLocations = useMemo(() => {
    let filtered = locations.filter(loc => !hiddenTypes.has(loc.type));

    // Apply time filter if animation is active
    if (animationTime) {
      filtered = filtered.filter(loc => {
        if (!loc.date) return true; // Show entities without dates
        const locDate = new Date(loc.date);
        return !isNaN(locDate.getTime()) && locDate <= animationTime;
      });
    }

    return filtered;
  }, [locations, hiddenTypes, animationTime]);

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

  // Handle right-click context menu on markers
  const handleMarkerContextMenu = useCallback((entity, e) => {
    e.originalEvent.preventDefault();
    setContextMenu({
      x: e.originalEvent.clientX,
      y: e.originalEvent.clientY,
      entity,
    });
  }, []);

  const handleEditLocation = useCallback((entity) => {
    setContextMenu(null);
    setEditLocationModal({
      entity,
      locationName: entity.location_formatted || entity.location_raw || '',
      latitude: entity.latitude,
      longitude: entity.longitude,
    });
  }, []);

  const handleSaveLocation = useCallback(async () => {
    if (!editLocationModal || !caseId) return;
    setSavingLocation(true);
    try {
      await graphAPI.updateLocation(editLocationModal.entity.key, {
        caseId,
        locationName: editLocationModal.locationName,
        latitude: parseFloat(editLocationModal.latitude),
        longitude: parseFloat(editLocationModal.longitude),
      });
      setLocations(prev => prev.map(loc =>
        loc.key === editLocationModal.entity.key
          ? { ...loc, latitude: parseFloat(editLocationModal.latitude), longitude: parseFloat(editLocationModal.longitude), location_formatted: editLocationModal.locationName }
          : loc
      ));
      setEditLocationModal(null);
    } catch (err) {
      console.error('Failed to update location:', err);
      alert('Failed to update location: ' + err.message);
    } finally {
      setSavingLocation(false);
    }
  }, [editLocationModal, caseId]);

  const handleRemoveLocation = useCallback(async (entity) => {
    setContextMenu(null);
    if (!caseId) return;
    try {
      await graphAPI.removeLocation(entity.key, caseId);
      setLocations(prev => prev.filter(loc => loc.key !== entity.key));
    } catch (err) {
      console.error('Failed to remove location:', err);
      alert('Failed to remove location: ' + err.message);
    }
  }, [caseId]);

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
              const relationship = conn.relationship || 'RELATED_TO';
              lines.push({
                id: lineId,
                positions: [
                  [loc.latitude, loc.longitude],
                  [connectedLoc.latitude, connectedLoc.longitude],
                ],
                relationship,
                color: RELATIONSHIP_COLORS[relationship] || RELATIONSHIP_COLORS.default,
                sourceName: loc.name,
                targetName: connectedLoc.name,
                sourceType: loc.type,
                targetType: connectedLoc.type,
                direction: conn.direction || 'outgoing',
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
      <div className="h-full flex items-center justify-center bg-light-50 relative">
        <div className="flex flex-col items-center gap-4 text-center max-w-md px-4">
          <MapPin className="w-12 h-12 text-light-400" />
          <span className="text-light-800 font-medium">No geocoded entities</span>
          <span className="text-light-600 text-sm">
            Entities need location data to appear on the map.
            Use AI Rescan to extract and geocode locations from your case documents.
          </span>
          <button
            onClick={handleRescanLocations}
            disabled={rescanRunning}
            className={`flex items-center gap-2 px-5 py-2.5 rounded-lg shadow-md border-2 transition-colors text-sm font-medium ${
              rescanRunning
                ? 'bg-emerald-100 border-emerald-400 text-emerald-800 cursor-wait'
                : 'bg-emerald-500 border-emerald-600 text-white hover:bg-emerald-600'
            }`}
          >
            {rescanRunning ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <MapPin className="w-4 h-4" />
            )}
            {rescanRunning ? 'Scanning documents…' : 'AI Rescan Locations'}
          </button>
          <button
            onClick={loadLocations}
            className="text-xs text-light-500 hover:text-light-700 underline"
          >
            Refresh
          </button>
        </div>

        {/* Rescan result toast */}
        {rescanResult && (
          <div className={`absolute top-4 right-4 z-10 max-w-sm rounded-lg shadow-lg border p-4 ${
            rescanResult.success
              ? 'bg-emerald-50 border-emerald-300 text-emerald-900'
              : 'bg-red-50 border-red-300 text-red-900'
          }`}>
            <div className="flex items-start gap-2">
              <div className="flex-1">
                {rescanResult.success ? (
                  <>
                    <p className="text-sm font-semibold">Location Rescan Complete</p>
                    <div className="text-xs mt-1 space-y-0.5">
                      <p>{rescanResult.chunks_scanned || 0} chunks scanned</p>
                      <p>{rescanResult.locations_geocoded || 0} locations geocoded</p>
                      <p>{rescanResult.entities_updated || 0} entities updated</p>
                      <p>{rescanResult.location_nodes_created || 0} new location nodes</p>
                      <p>{rescanResult.relationships_created || 0} relationships created</p>
                    </div>
                  </>
                ) : (
                  <>
                    <p className="text-sm font-semibold">Rescan Failed</p>
                    <p className="text-xs mt-1">{rescanResult.error || rescanResult.message || 'Unknown error'}</p>
                  </>
                )}
              </div>
              <button onClick={() => setRescanResult(null)} className="p-0.5 hover:bg-black/10 rounded">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>
    );
  }

  // Default center (world view)
  const defaultCenter = [20, 0];
  const defaultZoom = 2;

  const mapContainerStyle = { height: '100%', width: '100%', ...containerStyle };

  return (
    <div className="h-full relative">
      {/* Map Container */}
      <MapContainer
        center={defaultCenter}
        zoom={defaultZoom}
        className="h-full w-full"
        style={mapContainerStyle}
        onClick={handleMapClick}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        <InvalidateSizeOnMount />
        {/* Fit bounds to all markers on initial load */}
        <FitBounds locations={filteredLocations} />
        
        {/* Center on selected entities */}
        <CenterOnSelected selectedKeys={selectedKeys} locations={filteredLocations} />

        {/* Heatmap layer (rendered below markers) */}
        {showHeatmap && (
          <HeatmapLayer
            locations={filteredLocations}
            weightBy={heatmapSettings.weightBy}
            radius={heatmapSettings.radius}
            blur={heatmapSettings.blur}
          />
        )}

        {/* Clustered markers */}
        <MarkerClusterGroup
          chunkedLoading
          maxClusterRadius={50}
          spiderfyOnMaxZoom={true}
          showCoverageOnHover={true}
          iconCreateFunction={createClusterIcon}
          polygonOptions={{
            fillColor: '#3b82f6',
            color: '#3b82f6',
            weight: 2,
            opacity: 0.5,
            fillOpacity: 0.2,
          }}
        >
          {filteredLocations.map((entity) => {
            const isSelected = selectedKeys.includes(entity.key);
            const isHovered = hoveredEntityKey === entity.key;
            return (
              <Marker
                key={entity.key}
                position={[entity.latitude, entity.longitude]}
                icon={createIcon(entity.type, isSelected, isHovered)}
                entityType={entity.type}
                eventHandlers={{
                  click: (e) => handleMarkerClick(entity, e),
                  contextmenu: (e) => handleMarkerContextMenu(entity, e),
                  mouseover: () => setHoveredEntityKey(entity.key),
                  mouseout: () => setHoveredEntityKey(null),
                }}
              >
                {/* Hover tooltip */}
                <Tooltip
                  direction="top"
                  offset={[0, -10]}
                  opacity={0.95}
                  className="entity-tooltip"
                >
                  <div className="flex items-center gap-2 px-1">
                    <div
                      className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                      style={{ backgroundColor: TYPE_COLORS[entity.type] || TYPE_COLORS.default }}
                    />
                    <span className="font-medium text-gray-900 text-sm truncate max-w-[180px]">
                      {entity.name}
                    </span>
                    <span className="text-xs text-gray-500">
                      {entity.type}
                    </span>
                  </div>
                </Tooltip>

                {/* Click popup with full details */}
                <Popup>
                  <div className="min-w-[280px] max-w-[360px]">
                    {/* Header */}
                    <div className="flex items-start gap-2 mb-3">
                      <div
                        className="w-4 h-4 rounded-full flex-shrink-0 mt-0.5"
                        style={{ backgroundColor: TYPE_COLORS[entity.type] || TYPE_COLORS.default }}
                      />
                      <div className="flex-1 min-w-0">
                        <div className="font-semibold text-gray-900 leading-tight">{entity.name}</div>
                        <div className="text-xs text-gray-500 mt-0.5">{entity.type}</div>
                      </div>
                      {entity.geocoding_confidence && (
                        <span className={`text-xs px-1.5 py-0.5 rounded ${
                          entity.geocoding_confidence === 'high'
                            ? 'bg-green-100 text-green-700'
                            : entity.geocoding_confidence === 'medium'
                            ? 'bg-yellow-100 text-yellow-700'
                            : 'bg-gray-100 text-gray-600'
                        }`}>
                          {entity.geocoding_confidence}
                        </span>
                      )}
                    </div>

                    {/* Location */}
                    {entity.location_formatted && (
                      <div className="flex items-start gap-2 text-sm text-gray-600 mb-3 bg-gray-50 rounded px-2 py-1.5">
                        <MapPin className="w-3.5 h-3.5 mt-0.5 flex-shrink-0 text-gray-400" />
                        <span>{entity.location_formatted}</span>
                      </div>
                    )}

                    {/* Summary */}
                    {entity.summary && (
                      <div className="text-sm text-gray-700 mb-3 border-l-2 border-gray-200 pl-2">
                        {entity.summary.length > 200
                          ? entity.summary.substring(0, 200) + '...'
                          : entity.summary}
                      </div>
                    )}

                    {/* Connections preview */}
                    {entity.connections && entity.connections.length > 0 && (
                      <div className="mb-3">
                        <div className="text-xs font-medium text-gray-500 mb-1.5 flex items-center gap-1">
                          <Link2 className="w-3 h-3" />
                          Connections ({entity.connections.length})
                        </div>
                        <div className="flex flex-wrap gap-1">
                          {entity.connections.slice(0, 5).map((conn, idx) => (
                            <span
                              key={idx}
                              className="inline-flex items-center gap-1 text-xs bg-gray-100 rounded px-1.5 py-0.5"
                              title={`${conn.relationship}: ${conn.name}`}
                            >
                              <div
                                className="w-2 h-2 rounded-full"
                                style={{ backgroundColor: TYPE_COLORS[conn.type] || TYPE_COLORS.default }}
                              />
                              <span className="truncate max-w-[80px]">{conn.name}</span>
                            </span>
                          ))}
                          {entity.connections.length > 5 && (
                            <span className="text-xs text-gray-500">
                              +{entity.connections.length - 5} more
                            </span>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Footer with date and actions */}
                    <div className="flex items-center justify-between pt-2 border-t border-gray-100">
                      {entity.date ? (
                        <span className="text-xs text-gray-500">
                          {entity.date}{entity.time ? ` ${entity.time}` : ''}
                        </span>
                      ) : (
                        <span />
                      )}
                      <div className="flex items-center gap-1">
                        <span className="text-xs text-blue-600 flex items-center gap-0.5">
                          <ExternalLink className="w-3 h-3" />
                          Click to select
                        </span>
                      </div>
                    </div>
                  </div>
                </Popup>
              </Marker>
            );
          })}
        </MarkerClusterGroup>
        
        {/* Connection lines between selected entities */}
        {connectionLines.map(line => (
          <ConnectionLine
            key={line.id}
            line={line}
            showLabel={showRelationshipLabels}
          />
        ))}

        {/* Proximity analysis tool */}
        <ProximityAnalysis
          locations={filteredLocations}
          selectedNodes={selectedNodes}
          onSelectEntities={onBulkNodeSelect}
          isActive={showProximityTool}
          onClose={() => setShowProximityTool(false)}
        />

        {/* Hotspot panel */}
        <HotspotPanel
          locations={filteredLocations}
          onSelectEntities={onBulkNodeSelect}
          isActive={showHotspotPanel}
          onClose={() => setShowHotspotPanel(false)}
        />

        {/* Time control */}
        <TimeControl
          locations={locations}
          onTimeChange={setAnimationTime}
          isActive={showTimeControl}
          onClose={() => setShowTimeControl(false)}
        />

        {/* Route analysis */}
        <RouteAnalysis
          locations={filteredLocations}
          selectedNodes={selectedNodes}
          isActive={showRouteAnalysis}
          onClose={() => setShowRouteAnalysis(false)}
        />
      </MapContainer>
      
      {/* Controls overlay */}
      <div className="absolute top-4 left-4 z-[1000] flex flex-col gap-2 max-h-[calc(100%-2rem)] overflow-y-auto pr-1">
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

        {/* Show relationship labels toggle (only visible when connections are shown) */}
        {showConnections && (
          <button
            onClick={() => setShowRelationshipLabels(!showRelationshipLabels)}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg shadow-md border transition-colors ${
              showRelationshipLabels
                ? 'bg-owl-blue-100 border-owl-blue-300 text-owl-blue-900'
                : 'bg-white/90 backdrop-blur-sm border-light-200 text-light-700 hover:bg-light-50'
            }`}
            title="Show relationship labels on connection lines"
          >
            <Tag className={`w-4 h-4 ${showRelationshipLabels ? '' : 'opacity-50'}`} />
            <span className="text-sm">Labels</span>
          </button>
        )}

        {/* Heatmap toggle */}
        <div className="relative">
          <button
            onClick={() => setShowHeatmap(!showHeatmap)}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg shadow-md border transition-colors ${
              showHeatmap
                ? 'bg-orange-100 border-orange-300 text-orange-900'
                : 'bg-white/90 backdrop-blur-sm border-light-200 text-light-700 hover:bg-light-50'
            }`}
            title="Toggle heatmap layer"
          >
            <Flame className={`w-4 h-4 ${showHeatmap ? 'text-orange-600' : ''}`} />
            <span className="text-sm">Heatmap</span>
          </button>

          {/* Heatmap settings button */}
          {showHeatmap && (
            <button
              onClick={() => setShowHeatmapSettings(!showHeatmapSettings)}
              className={`absolute -right-2 -top-2 p-1 rounded-full shadow-md border transition-colors ${
                showHeatmapSettings
                  ? 'bg-orange-500 border-orange-600 text-white'
                  : 'bg-white border-light-200 text-light-600 hover:bg-light-50'
              }`}
              title="Heatmap settings"
            >
              <Settings2 className="w-3 h-3" />
            </button>
          )}
        </div>

        {/* Proximity tool toggle */}
        <button
          onClick={() => setShowProximityTool(!showProximityTool)}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg shadow-md border transition-colors ${
            showProximityTool
              ? 'bg-blue-100 border-blue-300 text-blue-900'
              : 'bg-white/90 backdrop-blur-sm border-light-200 text-light-700 hover:bg-light-50'
          }`}
          title="Proximity analysis tool"
        >
          <Target className={`w-4 h-4 ${showProximityTool ? 'text-blue-600' : ''}`} />
          <span className="text-sm">Proximity</span>
        </button>

        {/* Hotspot panel toggle */}
        <button
          onClick={() => setShowHotspotPanel(!showHotspotPanel)}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg shadow-md border transition-colors ${
            showHotspotPanel
              ? 'bg-orange-100 border-orange-300 text-orange-900'
              : 'bg-white/90 backdrop-blur-sm border-light-200 text-light-700 hover:bg-light-50'
          }`}
          title="View activity hotspots"
        >
          <TrendingUp className={`w-4 h-4 ${showHotspotPanel ? 'text-orange-600' : ''}`} />
          <span className="text-sm">Hotspots</span>
        </button>

        {/* Time animation toggle */}
        <button
          onClick={() => setShowTimeControl(!showTimeControl)}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg shadow-md border transition-colors ${
            showTimeControl
              ? 'bg-purple-100 border-purple-300 text-purple-900'
              : 'bg-white/90 backdrop-blur-sm border-light-200 text-light-700 hover:bg-light-50'
          }`}
          title="Time-based animation"
        >
          <Timer className={`w-4 h-4 ${showTimeControl ? 'text-purple-600' : ''}`} />
          <span className="text-sm">Timeline</span>
        </button>

        {/* Route analysis toggle */}
        <button
          onClick={() => setShowRouteAnalysis(!showRouteAnalysis)}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg shadow-md border transition-colors ${
            showRouteAnalysis
              ? 'bg-indigo-100 border-indigo-300 text-indigo-900'
              : 'bg-white/90 backdrop-blur-sm border-light-200 text-light-700 hover:bg-light-50'
          }`}
          title="Route and path analysis"
        >
          <Route className={`w-4 h-4 ${showRouteAnalysis ? 'text-indigo-600' : ''}`} />
          <span className="text-sm">Routes</span>
        </button>

        {/* Divider */}
        <div className="border-t border-light-300 my-0.5" />

        {/* AI Rescan Locations */}
        <button
          onClick={handleRescanLocations}
          disabled={rescanRunning}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg shadow-md border-2 transition-colors ${
            rescanRunning
              ? 'bg-emerald-100 border-emerald-400 text-emerald-800 cursor-wait'
              : 'bg-emerald-50 border-emerald-400 text-emerald-800 hover:bg-emerald-100'
          }`}
          title="Rescan all case documents with GPT to extract and geocode locations"
        >
          {rescanRunning ? (
            <Loader2 className="w-4 h-4 animate-spin text-emerald-600" />
          ) : (
            <MapPin className="w-4 h-4 text-emerald-600" />
          )}
          <span className="text-sm font-medium">{rescanRunning ? 'Scanning…' : 'AI Rescan Locations'}</span>
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

      {/* Heatmap settings panel */}
      {showHeatmapSettings && (
        <div className="absolute top-4 left-40 z-[1000] bg-white/95 backdrop-blur-sm rounded-lg shadow-lg border border-light-200 p-4 w-64">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-light-800 flex items-center gap-2">
              <Flame className="w-4 h-4 text-orange-500" />
              Heatmap Settings
            </h3>
            <button
              onClick={() => setShowHeatmapSettings(false)}
              className="p-1 hover:bg-light-100 rounded"
            >
              <X className="w-4 h-4 text-light-500" />
            </button>
          </div>

          <div className="space-y-4">
            {/* Weight by */}
            <div>
              <label className="text-xs font-medium text-light-600 block mb-1.5">
                Weight by
              </label>
              <select
                value={heatmapSettings.weightBy}
                onChange={(e) => setHeatmapSettings(s => ({ ...s, weightBy: e.target.value }))}
                className="w-full px-2 py-1.5 text-sm border border-light-200 rounded bg-white focus:border-owl-blue-400 focus:ring-1 focus:ring-owl-blue-400"
              >
                <option value="uniform">Uniform (all equal)</option>
                <option value="connections">Connection count</option>
                <option value="count">Density only</option>
              </select>
            </div>

            {/* Radius slider */}
            <div>
              <label className="text-xs font-medium text-light-600 block mb-1.5">
                Radius: {heatmapSettings.radius}px
              </label>
              <input
                type="range"
                min="10"
                max="50"
                value={heatmapSettings.radius}
                onChange={(e) => setHeatmapSettings(s => ({ ...s, radius: parseInt(e.target.value) }))}
                className="w-full h-2 bg-light-200 rounded-lg appearance-none cursor-pointer accent-orange-500"
              />
            </div>

            {/* Blur slider */}
            <div>
              <label className="text-xs font-medium text-light-600 block mb-1.5">
                Blur: {heatmapSettings.blur}px
              </label>
              <input
                type="range"
                min="5"
                max="30"
                value={heatmapSettings.blur}
                onChange={(e) => setHeatmapSettings(s => ({ ...s, blur: parseInt(e.target.value) }))}
                className="w-full h-2 bg-light-200 rounded-lg appearance-none cursor-pointer accent-orange-500"
              />
            </div>

            {/* Reset button */}
            <button
              onClick={() => setHeatmapSettings({ radius: 25, blur: 15, weightBy: 'uniform' })}
              className="w-full px-3 py-1.5 text-xs bg-light-100 hover:bg-light-200 rounded transition-colors"
            >
              Reset to defaults
            </button>
          </div>
        </div>
      )}

      {/* Rescan result toast */}
      {rescanResult && (
        <div className={`absolute top-4 right-4 z-[1001] max-w-sm rounded-lg shadow-lg border p-4 ${
          rescanResult.success
            ? 'bg-emerald-50 border-emerald-300 text-emerald-900'
            : 'bg-red-50 border-red-300 text-red-900'
        }`}>
          <div className="flex items-start gap-2">
            <div className="flex-1">
              {rescanResult.success ? (
                <>
                  <p className="text-sm font-semibold">Location Rescan Complete</p>
                  <div className="text-xs mt-1 space-y-0.5">
                    <p>{rescanResult.chunks_scanned || 0} chunks scanned</p>
                    <p>{rescanResult.locations_geocoded || 0} locations geocoded</p>
                    <p>{rescanResult.entities_updated || 0} entities updated</p>
                    <p>{rescanResult.location_nodes_created || 0} new location nodes</p>
                    <p>{rescanResult.relationships_created || 0} relationships created</p>
                    {rescanResult.locations_failed_geocode > 0 && (
                      <p className="text-amber-700">{rescanResult.locations_failed_geocode} failed to geocode</p>
                    )}
                  </div>
                </>
              ) : (
                <>
                  <p className="text-sm font-semibold">Rescan Failed</p>
                  <p className="text-xs mt-1">{rescanResult.error || rescanResult.message || 'Unknown error'}</p>
                </>
              )}
            </div>
            <button onClick={() => setRescanResult(null)} className="p-0.5 hover:bg-black/10 rounded">
              <X className="w-3.5 h-3.5" />
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

      {/* Right-click context menu */}
      {contextMenu && (
        <div
          className="fixed z-[9999] bg-white rounded-lg shadow-xl border border-light-200 py-1 min-w-[160px]"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onMouseLeave={() => setContextMenu(null)}
        >
          <div className="px-3 py-1.5 text-xs text-light-500 font-medium border-b border-light-100 truncate max-w-[200px]">
            {contextMenu.entity.name}
          </div>
          <button
            onClick={() => handleEditLocation(contextMenu.entity)}
            className="w-full text-left px-3 py-2 text-sm text-light-700 hover:bg-light-50 flex items-center gap-2 transition-colors"
          >
            <Pencil className="w-3.5 h-3.5" />
            Edit Location
          </button>
          <button
            onClick={() => handleRemoveLocation(contextMenu.entity)}
            className="w-full text-left px-3 py-2 text-sm text-red-600 hover:bg-red-50 flex items-center gap-2 transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Remove from Map
          </button>
        </div>
      )}

      {/* Edit Location Modal */}
      {editLocationModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-[9999]" onClick={() => setEditLocationModal(null)}>
          <div className="bg-white rounded-lg shadow-xl w-full max-w-sm mx-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-light-200">
              <h3 className="font-semibold text-owl-blue-900 flex items-center gap-2">
                <MapPin className="w-4 h-4 text-owl-blue-600" />
                Edit Location
              </h3>
              <button onClick={() => setEditLocationModal(null)} className="p-1 hover:bg-light-100 rounded transition-colors">
                <X className="w-4 h-4 text-light-600" />
              </button>
            </div>
            <div className="p-4 space-y-3">
              <div className="text-sm text-light-600">
                {editLocationModal.entity.name} <span className="text-light-400">({editLocationModal.entity.type})</span>
              </div>
              <div>
                <label className="text-xs font-medium text-light-700 block mb-1">Location Name</label>
                <input
                  type="text"
                  value={editLocationModal.locationName}
                  onChange={(e) => setEditLocationModal(prev => ({ ...prev, locationName: e.target.value }))}
                  className="w-full px-3 py-2 text-sm border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-light-700 block mb-1">Latitude</label>
                  <input
                    type="number"
                    step="any"
                    value={editLocationModal.latitude}
                    onChange={(e) => setEditLocationModal(prev => ({ ...prev, latitude: e.target.value }))}
                    className="w-full px-3 py-2 text-sm border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-light-700 block mb-1">Longitude</label>
                  <input
                    type="number"
                    step="any"
                    value={editLocationModal.longitude}
                    onChange={(e) => setEditLocationModal(prev => ({ ...prev, longitude: e.target.value }))}
                    className="w-full px-3 py-2 text-sm border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                  />
                </div>
              </div>
            </div>
            <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-light-200">
              <button
                onClick={() => setEditLocationModal(null)}
                className="px-4 py-2 text-sm text-light-700 hover:bg-light-100 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveLocation}
                disabled={savingLocation}
                className="px-4 py-2 text-sm bg-owl-blue-600 hover:bg-owl-blue-700 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-1.5"
              >
                <Check className="w-3.5 h-3.5" />
                {savingLocation ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

