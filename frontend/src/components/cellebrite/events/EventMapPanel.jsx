import React, { useEffect, useMemo, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, CircleMarker, useMap } from 'react-leaflet';
import MarkerClusterGroup from 'react-leaflet-cluster';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import 'leaflet.markercluster/dist/MarkerCluster.css';
import 'leaflet.markercluster/dist/MarkerCluster.Default.css';

import {
  EVENT_COLORS,
  eventsWithinTrail,
  parseTs,
} from './eventUtils';
import PhoneIdentityChip from '../shared/PhoneIdentityChip';
import { usePhoneReports } from '../../../context/PhoneReportsContext';

/**
 * Build a divIcon with a circle coloured by event type, with a halo ring
 * for the device's track colour.
 */
function makeEventIcon(eventType, deviceColor, highlighted = false) {
  const color = EVENT_COLORS[eventType] || '#64748b';
  const size = highlighted ? 16 : 12;
  // Widened device-colour ring (2 px → 4 px) so the per-phone identity
  // is visible on the map without requiring a hover. The white outer
  // border keeps the marker readable on any base-tile colour.
  const html = `
    <div style="
      width:${size}px; height:${size}px; border-radius:50%;
      background:${color};
      box-shadow: 0 0 0 4px ${deviceColor}, 0 0 0 5px rgba(255,255,255,0.9);
      ${highlighted ? 'animation: pulse-ring 1.2s infinite;' : ''}
    "></div>
  `;
  return L.divIcon({
    html,
    iconSize: [size + 10, size + 10],
    iconAnchor: [(size + 10) / 2, (size + 10) / 2],
    className: 'cellebrite-event-marker',
  });
}

function BoundsFitter({ events, tracks, enabled }) {
  const map = useMap();
  // Track point count instead of a one-shot bool — late-arriving data
  // (the common case: tiles/events fetch resolves AFTER first paint)
  // would otherwise fly past a frozen `fitted=true` and the user gets
  // a blank world map at zoom 2 over an empty Atlantic.
  const lastCount = useRef(0);
  useEffect(() => {
    if (!enabled) return;
    const points = [];
    for (const e of events) {
      if (e.latitude != null && e.longitude != null) points.push([e.latitude, e.longitude]);
    }
    for (const t of tracks) {
      for (const p of t.points || []) points.push([p.lat, p.lon]);
    }
    // Only re-fit when the count grew — avoids stealing the user's
    // pan/zoom on every render where the same data passes through.
    if (points.length === 0 || points.length === lastCount.current) return;
    try {
      map.fitBounds(L.latLngBounds(points), { padding: [30, 30], maxZoom: 14 });
      lastCount.current = points.length;
    } catch {
      // ignore
    }
  }, [events, tracks, enabled, map]);
  return null;
}

/**
 * Pans the map to a specific event whenever `flyToId` changes. Used
 * by callers (e.g. OverviewLocationsView) that drive selection from
 * a side table — clicking a row should fly the map to that point and
 * pop its marker bubble. Optional; ignored when `flyToId` is null.
 */
function FlyToSelected({ events, flyToId, zoom = 14 }) {
  const map = useMap();
  useEffect(() => {
    if (!flyToId) return;
    const target = events.find((e) => (e.id || e.node_key) === flyToId);
    if (!target || target.latitude == null || target.longitude == null) return;
    try {
      map.flyTo([target.latitude, target.longitude], Math.max(map.getZoom(), zoom), {
        duration: 0.6,
      });
    } catch {
      // ignore — Leaflet throws if the map isn't ready yet
    }
  }, [flyToId, events, map, zoom]);
  return null;
}

/**
 * Direct-coordinate flyTo — bypasses the events lookup. Used when
 * the caller drives map recentering from a source that doesn't have
 * its target row in the current `events` array (e.g. the rail
 * flyout drilling into a tile's contents while the map itself only
 * has the parent tile centroids loaded).
 *
 * The shape is `{ lat, lon, tick }`. `tick` is a monotonic counter
 * the caller bumps every time it wants the effect to re-fire even
 * when lat/lon are identical to the last call — same pattern as the
 * id::timestamp scheme used by FlyToSelected's caller.
 */
function FlyToCoord({ flyToCoord, zoom = 14 }) {
  const map = useMap();
  useEffect(() => {
    if (!flyToCoord || flyToCoord.lat == null || flyToCoord.lon == null) return;
    try {
      map.flyTo([flyToCoord.lat, flyToCoord.lon], Math.max(map.getZoom(), zoom), {
        duration: 0.6,
      });
    } catch {
      // ignore — Leaflet throws if the map isn't ready yet
    }
    // tick is the re-trigger signal; intentionally in deps so a fresh
    // click on the same row re-flies even when coords are unchanged.
  }, [flyToCoord?.lat, flyToCoord?.lon, flyToCoord?.tick, map, zoom]);
  return null;
}

/**
 * Direction indicators along a trajectory polyline.
 *
 * Sampling is by GEODESIC DISTANCE along the line, not by point
 * index. That distinction matters because real trajectories cluster
 * thousands of points around one or two "hot" nodes (home, office)
 * with a few long segments stretching out to the rest of the world.
 * Index-based sampling stacked every arrow on top of the hot node;
 * distance-based sampling spreads them evenly along the whole route
 * regardless of point density.
 *
 * We accumulate cumulative haversine distance across the polyline
 * once, then drop an arrow at evenly-spaced fractional positions
 * (capped at maxArrows). For very long intercontinental tracks the
 * cap kicks in and the spacing widens; for short walks each segment
 * still gets a couple of arrows.
 *
 * The arrow is drawn with a fat white stroke under a coloured fill
 * so it stays legible against both the line itself and the basemap.
 */
function DirectionArrows({ positions, color, maxArrows = 16 }) {
  const arrows = useMemo(() => {
    const n = positions.length;
    if (n < 2) return [];

    // Per-segment distance + cumulative total in one pass.
    const segDist = new Array(n - 1);
    let total = 0;
    for (let i = 0; i < n - 1; i += 1) {
      const a = positions[i];
      const b = positions[i + 1];
      const d = haversineMeters(a[0], a[1], b[0], b[1]);
      segDist[i] = d;
      total += d;
    }
    if (total <= 0) return [];

    // Target one arrow per ~50 km of track, but always between 3 and
    // maxArrows. The 50 km figure is a sweet spot: dense enough for
    // a city walk to get a few arrows, sparse enough that a 10 000 km
    // intercontinental track doesn't drown in markers.
    const targetCount = Math.min(maxArrows, Math.max(3, Math.round(total / 50000)));
    const step = total / targetCount;
    const out = [];

    // Walk the cumulative distance and place arrows at midpoints of
    // each step (so neither end of the line has an arrow stacked on
    // its terminal marker).
    let segIdx = 0;
    let segStartCum = 0;
    for (let k = 0; k < targetCount; k += 1) {
      const target = step * (k + 0.5);
      while (
        segIdx < segDist.length - 1
        && segStartCum + segDist[segIdx] < target
      ) {
        segStartCum += segDist[segIdx];
        segIdx += 1;
      }
      const segLen = segDist[segIdx] || 0;
      if (segLen <= 0) continue;
      const t = Math.max(0, Math.min(1, (target - segStartCum) / segLen));
      const a = positions[segIdx];
      const b = positions[segIdx + 1];
      // Linear lat/lon interpolation — visually identical to a
      // great-circle interpolation at trajectory segment lengths.
      const lat = a[0] + (b[0] - a[0]) * t;
      const lon = a[1] + (b[1] - a[1]) * t;
      const bearing = computeBearing(a[0], a[1], b[0], b[1]);
      out.push({ lat, lon, bearing, key: `${k}` });
    }
    return out;
  }, [positions, maxArrows]);

  if (arrows.length === 0) return null;
  return arrows.map((ar) => (
    <Marker
      key={ar.key}
      position={[ar.lat, ar.lon]}
      // The svg is rotated to the bearing; bearing 0 = north, 90 = east.
      icon={L.divIcon({
        className: 'cellebrite-trajectory-arrow',
        html: `<svg width="18" height="18" viewBox="-9 -9 18 18" style="transform: rotate(${ar.bearing}deg); transform-origin: center;">
          <path d="M0,-6 L4,4 L0,2 L-4,4 Z" fill="${color}" stroke="#ffffff" stroke-width="1.5" stroke-linejoin="round"/>
        </svg>`,
        iconSize: [18, 18],
        iconAnchor: [9, 9],
      })}
      // Don't intercept clicks — keep the marker visual-only so users
      // can still click through to underlying points.
      interactive={false}
      keyboard={false}
    />
  ));
}

/**
 * Great-circle distance in metres between two (lat, lon) points.
 * Used by DirectionArrows to space markers along the line by real
 * distance rather than by polyline-vertex index.
 */
function haversineMeters(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const toRad = (d) => (d * Math.PI) / 180;
  const dφ = toRad(lat2 - lat1);
  const dλ = toRad(lon2 - lon1);
  const φ1 = toRad(lat1);
  const φ2 = toRad(lat2);
  const a = Math.sin(dφ / 2) ** 2 + Math.cos(φ1) * Math.cos(φ2) * Math.sin(dλ / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

/**
 * Initial bearing from (lat1, lon1) to (lat2, lon2) in degrees from
 * north. Standard forward-azimuth formula on a sphere.
 */
function computeBearing(lat1, lon1, lat2, lon2) {
  const toRad = (d) => (d * Math.PI) / 180;
  const toDeg = (r) => (r * 180) / Math.PI;
  const φ1 = toRad(lat1);
  const φ2 = toRad(lat2);
  const Δλ = toRad(lon2 - lon1);
  const y = Math.sin(Δλ) * Math.cos(φ2);
  const x =
    Math.cos(φ1) * Math.sin(φ2) -
    Math.sin(φ1) * Math.cos(φ2) * Math.cos(Δλ);
  let θ = Math.atan2(y, x);
  θ = toDeg(θ);
  return (θ + 360) % 360;
}

/**
 * Tells Leaflet to recompute its container size whenever the parent
 * tab becomes visible again, OR when fresh data lands. Without this
 * the map renders at zero size when the events tab was inactive
 * (display:none) at mount, OR shows a frozen blank canvas when tiles
 * arrive after the parent flex finishes its first paint.
 */
function VisibilityInvalidator({ isActive, dataKey }) {
  const map = useMap();
  useEffect(() => {
    if (!isActive) return;
    // Defer to the next paint so the container has its real size.
    // Re-keying on `dataKey` (an event-count fingerprint passed from
    // the parent) means a kick on every data arrival, not just on
    // tab-visibility flips. This is the fix for the Locations tab
    // blank-map bug — tiles come back after the first paint and the
    // earlier mount-only invalidate had already fired against a 0-h
    // container.
    const id = requestAnimationFrame(() => {
      try { map.invalidateSize(); } catch { /* ignore */ }
    });
    return () => cancelAnimationFrame(id);
  }, [isActive, dataKey, map]);
  return null;
}

export default function EventMapPanel({
  events = [],
  tracks = [],
  playheadTime = null,
  trailWindowMs = 30 * 60 * 1000,
  isPlaying = false,
  onEventClick,
  selectedEventId,
  // When set, the map flies to the event with this id whenever it
  // changes. Independent of selectedEventId (which only controls the
  // marker highlight ring) so callers can choose: highlight-only,
  // fly-to-only, or both. Used by Overview Locations where clicking a
  // row should pan the map.
  flyToId = null,
  // Direct-coordinate flyTo — used by callers that drive recentering
  // from a source where the target row isn't in the `events` array
  // (e.g. tile rail drill-in). Shape: { lat, lon, tick }. tick is a
  // monotonic re-trigger signal — bump it to refly to the same point.
  flyToCoord = null,
  intersectionMatches = [],
  deviceColorOf,
  // True when the parent tab is the active one. The map needs to
  // know so it can invalidateSize() after being un-hidden.
  isActive = true,
}) {
  const phoneCtx = usePhoneReports();
  const showPhoneChip = !!phoneCtx?.hasMultiple;

  const visibleEvents = useMemo(() => {
    if (!isPlaying || !playheadTime) return events;
    return eventsWithinTrail(events, playheadTime, trailWindowMs);
  }, [events, playheadTime, isPlaying, trailWindowMs]);

  // Pre-parse each track point's timestamp ONCE when tracks change. This
  // lets the playhead-driven split below avoid re-parsing thousands of ISO
  // strings on every animation frame.
  const tracksWithMs = useMemo(() => {
    return tracks.map((t) => ({
      ...t,
      pointsMs: (t.points || []).map((p) => {
        const pt = parseTs(p.timestamp);
        return pt ? { lat: p.lat, lon: p.lon, t_ms: pt.getTime() } : null;
      }).filter(Boolean),
    }));
  }, [tracks]);

  // Split tracks into "before" and "after" playhead for styling.
  // Uses the pre-parsed pointsMs so this stays a pure numeric sweep.
  const splitTracks = useMemo(() => {
    if (!playheadTime) {
      return tracksWithMs.map((t) => ({
        ...t,
        past: t.pointsMs.map((p) => [p.lat, p.lon]),
        future: [],
      }));
    }
    const t_ms = playheadTime.getTime();
    return tracksWithMs.map((t) => {
      const past = [];
      const future = [];
      for (const p of t.pointsMs) {
        if (p.t_ms <= t_ms) past.push([p.lat, p.lon]);
        else future.push([p.lat, p.lon]);
      }
      return { ...t, past, future };
    });
  }, [tracksWithMs, playheadTime]);

  const { hasPoints, geolocatedCount } = useMemo(() => {
    let n = 0;
    for (const e of events) {
      if (e.latitude != null && e.longitude != null) n += 1;
    }
    let hp = n > 0;
    if (!hp) {
      for (const t of tracks) if ((t.points || []).length) { hp = true; break; }
    }
    return { hasPoints: hp, geolocatedCount: n };
  }, [events, tracks]);

  // --- Marker rendering strategy --------------------------------------
  // DOM divIcon markers inside MarkerClusterGroup melt the main thread at
  // tens of thousands of points — the Locations tab froze Chrome for minutes
  // on this case's ~68k geolocations (each divIcon parses an HTML string into
  // a DOM node; preferCanvas does NOT apply to divIcons). Above a threshold
  // we switch to canvas-rendered CircleMarkers and decimate to a cap. The
  // trajectory POLYLINE is drawn separately from `tracks` and always uses
  // every point, so the path stays complete; only the clickable dots thin
  // out — surfaced to the user via a visible note.
  const CANVAS_THRESHOLD = 3000;
  const MAX_CANVAS_MARKERS = 8000;
  const geoEvents = useMemo(
    () => visibleEvents.filter((e) => e.latitude != null && e.longitude != null),
    [visibleEvents],
  );
  const useCanvasMarkers = geoEvents.length > CANVAS_THRESHOLD;
  const drawnMarkers = useMemo(() => {
    if (!useCanvasMarkers || geoEvents.length <= MAX_CANVAS_MARKERS) return geoEvents;
    // Even stride keeps the spatial/temporal spread of the full set.
    const stride = Math.ceil(geoEvents.length / MAX_CANVAS_MARKERS);
    const out = [];
    for (let i = 0; i < geoEvents.length; i += stride) out.push(geoEvents[i]);
    // Never drop the selected point just because decimation skipped it.
    if (selectedEventId) {
      const sel = geoEvents.find((e) => (e.id || e.node_key) === selectedEventId);
      if (sel && !out.includes(sel)) out.push(sel);
    }
    return out;
  }, [geoEvents, useCanvasMarkers, selectedEventId]);
  const markersDecimated = drawnMarkers.length < geoEvents.length;

  if (!hasPoints) {
    return (
      <div className="h-full w-full flex flex-col items-center justify-center bg-light-50 text-light-500 text-sm p-6 text-center">
        <div className="mb-2 font-medium">No geolocated events in the current selection.</div>
        <div className="text-xs text-light-400">
          Switch to <span className="font-medium text-owl-blue-700">Table</span> view to browse all filtered events, including ones without location data.
        </div>
      </div>
    );
  }

  // If only a small fraction of the events are geolocated, nudge the user
  // toward the table view.
  const showLowGeoHint = events.length > 20 && geolocatedCount < events.length * 0.3;

  return (
    // h-full (not flex-1) — every caller wraps this in a sized
    // container (ResizableSplit pane, fixed-height div, etc.) that
    // is NOT a flex container. flex-1 on this root therefore
    // collapses to content height (0 with no children), which makes
    // the MapContainer's height:100% resolve to 0 → blank map. The
    // bug was load-bearing for the Locations tab; same parent shape
    // also bites the rail flyout and any other surface that mounts
    // the map without an explicit flex column wrapper.
    <div className="h-full w-full relative min-h-0">
      <style>{`
        @keyframes pulse-ring {
          0% { transform: scale(1); }
          50% { transform: scale(1.3); }
          100% { transform: scale(1); }
        }
        .cellebrite-event-marker { background: transparent !important; border: none !important; }
      `}</style>
      {showLowGeoHint && (
        <div className="absolute top-2 left-1/2 -translate-x-1/2 z-[400] bg-amber-50 border border-amber-300 text-amber-900 text-[11px] px-3 py-1 rounded-full shadow-sm">
          Only {geolocatedCount.toLocaleString()} of {events.length.toLocaleString()} events are geolocated — switch to <span className="font-semibold">Table</span> or <span className="font-semibold">Split</span> to see the full feed.
        </div>
      )}
      {markersDecimated && (
        <div className="absolute top-2 right-2 z-[400] bg-owl-blue-50 border border-owl-blue-200 text-owl-blue-900 text-[11px] px-2.5 py-1 rounded-full shadow-sm">
          {drawnMarkers.length.toLocaleString()} of {geoEvents.length.toLocaleString()} points shown as dots · full path drawn · table lists all
        </div>
      )}
      <MapContainer
        center={[0, 0]}
        zoom={2}
        style={{ height: '100%', width: '100%' }}
        preferCanvas
      >
        <TileLayer
          attribution='&copy; OpenStreetMap contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <BoundsFitter events={events} tracks={tracks} enabled />
        <VisibilityInvalidator
          isActive={isActive}
          dataKey={`${events.length}:${tracks.length}`}
        />
        <FlyToSelected events={events} flyToId={flyToId} />
        <FlyToCoord flyToCoord={flyToCoord} />


        {/* Device tracks. Each track is drawn TWICE: a fat white halo
            first, then the coloured line on top. This is the classic
            Google-Maps-style "directions" treatment — without it the
            polyline disappears behind the clustered marker icons on
            dense Locations cases (the user complaint about trajectory
            "not working"). Halo weight 6 / opacity 0.9 + line weight 4
            gives clear contrast at any zoom.

            Direction arrows are sampled along the past polyline (~12
            per track regardless of point count) so the eye can read
            which way the device was moving without the user having
            to follow timestamps. Skipped for the future segment —
            it's the "not yet" half during playback and shouldn't
            advertise direction. */}
        {splitTracks.map((t) => {
          const color = t.color_hint || deviceColorOf?.(t.device_report_key) || '#2563eb';
          return (
            <React.Fragment key={t.device_report_key}>
              {t.past.length > 1 && (
                <>
                  <Polyline
                    positions={t.past}
                    color="#ffffff"
                    weight={6}
                    opacity={0.9}
                  />
                  <Polyline
                    positions={t.past}
                    color={color}
                    weight={4}
                    opacity={1.0}
                  />
                  <DirectionArrows positions={t.past} color={color} maxArrows={12} />
                </>
              )}
              {t.future.length > 1 && (
                <Polyline
                  positions={t.future}
                  color={color}
                  weight={2}
                  opacity={0.25}
                  dashArray="4,6"
                />
              )}
            </React.Fragment>
          );
        })}

        {/* Event markers. Dense sets (e.g. the Locations tab's tens of
            thousands of points) render as canvas CircleMarkers — clicking a
            dot opens its detail in the rail. Sparser sets keep the richer
            divIcon + clustering UX with an inline popup. */}
        {useCanvasMarkers ? (
          drawnMarkers.map((e) => {
            const devColor = deviceColorOf?.(e.device_report_key) || '#2563eb';
            const isSelected = selectedEventId === (e.id || e.node_key);
            return (
              <CircleMarker
                key={e.id || e.node_key}
                center={[e.latitude, e.longitude]}
                radius={isSelected ? 7 : 4}
                pathOptions={{
                  color: isSelected ? '#111827' : devColor,
                  weight: isSelected ? 2 : 1,
                  fillColor: EVENT_COLORS[e.event_type] || '#64748b',
                  fillOpacity: 0.85,
                }}
                eventHandlers={{ click: () => onEventClick?.(e) }}
              />
            );
          })
        ) : (
          <MarkerClusterGroup disableClusteringAtZoom={15} chunkedLoading>
            {geoEvents.map((e) => {
              const devColor = deviceColorOf?.(e.device_report_key) || '#2563eb';
              const isSelected = selectedEventId === (e.id || e.node_key);
              return (
                <Marker
                  key={e.id || e.node_key}
                  position={[e.latitude, e.longitude]}
                  icon={makeEventIcon(e.event_type, devColor, isSelected)}
                  eventHandlers={{ click: () => onEventClick?.(e) }}
                >
                  <Popup>
                    <div className="text-xs">
                      {showPhoneChip && e.device_report_key && (
                        <div className="mb-1">
                          <PhoneIdentityChip
                            reportKey={e.device_report_key}
                            variant="default"
                          />
                        </div>
                      )}
                      <div className="font-semibold">{e.label}</div>
                      <div className="text-light-600">{e.timestamp}</div>
                      {e.summary && <div className="mt-1">{e.summary.slice(0, 140)}</div>}
                      {e.location_source === 'nearest' && (
                        <div className="text-[10px] text-amber-700 mt-1">
                          (inferred location — not directly tagged)
                        </div>
                      )}
                    </div>
                  </Popup>
                </Marker>
              );
            })}
          </MarkerClusterGroup>
        )}

        {/* Intersection flags */}
        {intersectionMatches
          .filter((m) => m.center)
          .map((m, idx) => (
            <CircleMarker
              key={`intr-${idx}-${m.id}`}
              center={[m.center.lat, m.center.lon]}
              radius={14}
              pathOptions={{
                color: '#f43f5e',
                fillColor: '#f43f5e',
                fillOpacity: 0.15,
                weight: 2,
              }}
            >
              <Popup>
                <div className="text-xs">
                  <div className="font-semibold text-red-700">{m.method}</div>
                  <div>{m.summary}</div>
                </div>
              </Popup>
            </CircleMarker>
          ))}
      </MapContainer>
    </div>
  );
}
