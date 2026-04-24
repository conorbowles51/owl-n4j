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

/**
 * Build a divIcon with a circle coloured by event type, with a halo ring
 * for the device's track colour.
 */
function makeEventIcon(eventType, deviceColor, highlighted = false) {
  const color = EVENT_COLORS[eventType] || '#64748b';
  const size = highlighted ? 16 : 12;
  const html = `
    <div style="
      width:${size}px; height:${size}px; border-radius:50%;
      background:${color};
      box-shadow: 0 0 0 2px ${deviceColor}, 0 0 0 3px rgba(255,255,255,0.9);
      ${highlighted ? 'animation: pulse-ring 1.2s infinite;' : ''}
    "></div>
  `;
  return L.divIcon({
    html,
    iconSize: [size + 6, size + 6],
    iconAnchor: [(size + 6) / 2, (size + 6) / 2],
    className: 'cellebrite-event-marker',
  });
}

function BoundsFitter({ events, tracks, enabled }) {
  const map = useMap();
  const fitted = useRef(false);
  useEffect(() => {
    if (!enabled || fitted.current) return;
    const points = [];
    for (const e of events) {
      if (e.latitude != null && e.longitude != null) points.push([e.latitude, e.longitude]);
    }
    for (const t of tracks) {
      for (const p of t.points || []) points.push([p.lat, p.lon]);
    }
    if (points.length === 0) return;
    try {
      map.fitBounds(L.latLngBounds(points), { padding: [30, 30], maxZoom: 14 });
      fitted.current = true;
    } catch {
      // ignore
    }
  }, [events, tracks, enabled, map]);
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
  intersectionMatches = [],
  deviceColorOf,
}) {
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
