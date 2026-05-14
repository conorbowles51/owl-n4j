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

  if (!hasPoints) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center bg-light-50 text-light-500 text-sm p-6 text-center">
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
    <div className="flex-1 relative min-h-0">
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


        {/* Device tracks */}
        {splitTracks.map((t) => (
          <React.Fragment key={t.device_report_key}>
            {t.past.length > 1 && (
              <Polyline
                positions={t.past}
                color={t.color_hint || deviceColorOf?.(t.device_report_key) || '#2563eb'}
                weight={3}
                opacity={0.85}
              />
            )}
            {t.future.length > 1 && (
              <Polyline
                positions={t.future}
                color={t.color_hint || deviceColorOf?.(t.device_report_key) || '#2563eb'}
                weight={2}
                opacity={0.25}
                dashArray="4,6"
              />
            )}
          </React.Fragment>
        ))}

        {/* Event markers, clustered */}
        <MarkerClusterGroup disableClusteringAtZoom={15} chunkedLoading>
          {visibleEvents
            .filter((e) => e.latitude != null && e.longitude != null)
            .map((e) => {
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
