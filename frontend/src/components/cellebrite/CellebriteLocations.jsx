import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, MapPin } from 'lucide-react';
import { cellebriteEventsAPI } from '../../services/api';
import { usePhoneReports } from '../../context/PhoneReportsContext';
import PhoneSelector from './shared/PhoneSelector';
import NoPhonesSelectedEmptyState from './shared/NoPhonesSelectedEmptyState';
import EventMapPanel from './events/EventMapPanel';
import TimelineScrubber from './shared/TimelineScrubber';
import CellebriteSearchInput from './shared/CellebriteSearchInput';
import LocationsTable from './locations/LocationsTable';
import ResizableSplit from './shared/ResizableSplit';
import { useCellebriteStatus } from './shared/CellebriteStatusBar';
import { useCellebriteSelection } from './shared/CellebriteSelectionContext';
import { parseQuery, matchItem } from '../../utils/cellebriteSearch';
import { deviceColor } from './events/eventUtils';

/**
 * Dedicated Locations tab.
 *
 * Promotes locations from a buried Events Center filter to a top-level
 * tab so investigators can work with them as their own surface — same
 * pattern as Cellebrite Reader's Device Locations view (map + table +
 * detail rail). Defers heavy spatial intelligence to follow-ups (tile
 * aggregation, place: search, geofence intersection).
 */
export default function CellebriteLocations({ caseId, reports: reportsProp = [], isActive = true }) {
  const phoneCtx = usePhoneReports();
  const fallbackReports = useMemo(() => reportsProp || [], [reportsProp]);
  const fallbackSelection = useMemo(
    () => new Set(fallbackReports.map(r => r.report_key)),
    [fallbackReports],
  );
  const reports = phoneCtx?.reports?.length ? phoneCtx.reports : fallbackReports;
  const selectedReportKeys = phoneCtx ? phoneCtx.selectedReportKeys : fallbackSelection;
  // Wait for the PhoneReportsContext to finish hydrating before
  // firing per-tab fetches — see CommsCenter for the rationale.
  const reportsReady = phoneCtx ? phoneCtx.hydrated : true;

  // --- Filter state ---
  const [windowStart, setWindowStart] = useState(null);
  const [windowEnd, setWindowEnd] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const startDate = windowStart ? toISODate(windowStart) : '';
  const endDate = windowEnd ? toISODate(windowEnd) : '';

  // --- Data state ---
  const [locations, setLocations] = useState([]);
  const [tiles, setTiles] = useState([]);
  const [tileCellDeg, setTileCellDeg] = useState(0);
  const [tracks, setTracks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  // Two render modes — tiles is the default for big cases (cheap
  // server-side aggregation); raw mode shows individual points and
  // is gated behind a button so users can drill in when they want
  // street-level detail. The choice is per-session, not persisted.
  const [renderMode, setRenderMode] = useState('tiles');
  // Coarse zoom we feed to the tiles endpoint. Reader-style approach:
  // a single coarse view for the whole case; finer-grained drilldowns
  // come from clicking a tile (G3) rather than from map zoom-tracking.
  const TILE_ZOOM = 6;

  // Fetch locations across the selected phones. Tiles mode hits the
  // cheap aggregation endpoint; raw mode pulls the individual points.
  useEffect(() => {
    if (!caseId) return undefined;
    if (!reportsReady) return undefined;
    if (selectedReportKeys.size === 0) {
      setLocations([]);
      setTiles([]);
      setTracks([]);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    const reportKeysArr = [...selectedReportKeys];

    const dataPromise = renderMode === 'tiles'
      ? cellebriteEventsAPI.getLocationTiles(caseId, {
          zoom: TILE_ZOOM,
          reportKeys: reportKeysArr,
          startDate: startDate || null,
          endDate: endDate || null,
        })
      : cellebriteEventsAPI.getEvents(caseId, {
          reportKeys: reportKeysArr,
          eventTypes: ['location'],
          onlyGeolocated: true,
          startDate: startDate || null,
          endDate: endDate || null,
          limit: 5000,
        });

    Promise.all([
      dataPromise,
      cellebriteEventsAPI.getTracks(caseId, {
        reportKeys: reportKeysArr,
        startDate: startDate || null,
        endDate: endDate || null,
      }),
    ])
      .then(([dataRes, tracksRes]) => {
        if (cancelled) return;
        if (renderMode === 'tiles') {
          setTiles(dataRes?.tiles || []);
          setTileCellDeg(dataRes?.cell_deg || 0);
          setLocations([]);
        } else {
          setLocations(dataRes?.events || []);
          setTiles([]);
          setTileCellDeg(0);
        }
        setTracks(tracksRes?.tracks || []);
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e?.message || 'Failed to load locations');
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [caseId, selectedReportKeys, startDate, endDate, renderMode, reportsReady]);

  // Synthesize event-shaped rows for the map. In tiles mode each tile
  // becomes one marker with its centroid + count surfaced via label/
  // summary; in raw mode we pass the original location rows through.
  // Search is only applied in raw mode — tiles are aggregated on the
  // server and there's nothing meaningful to substring-match here.
  const parsedQuery = useMemo(() => parseQuery(searchQuery), [searchQuery]);
  const tileMarkers = useMemo(() => tiles.map((t) => ({
    id: t.tile_id,
    node_key: t.tile_id,
    event_type: 'location_tile',
    label: `${t.count.toLocaleString()} location${t.count === 1 ? '' : 's'}`,
    summary: t.top_apps?.length ? `Apps: ${t.top_apps.join(', ')}` : '',
    timestamp: null,
    latitude: t.lat,
    longitude: t.lon,
    is_geolocated: true,
    location_source: 'direct',
    // Carry the cell coords through so the click handler can fetch
    // the rows in this tile without re-deriving the bucket.
    _tile: { cell_x: t.cell_x, cell_y: t.cell_y, count: t.count, top_apps: t.top_apps },
  })), [tiles]);
  const mapEvents = useMemo(() => {
    if (renderMode === 'tiles') return tileMarkers;
    if (!searchQuery) return locations;
    return locations.filter((loc) => matchItem(loc, parsedQuery, 'event', reports).matches);
  }, [renderMode, tileMarkers, locations, searchQuery, parsedQuery, reports]);

  // Status bar — choose the count source per mode.
  const totalCount = renderMode === 'tiles'
    ? tiles.reduce((s, t) => s + (t.count || 0), 0)
    : locations.length;
  useCellebriteStatus({
    isActive,
    total: totalCount,
    displayed: renderMode === 'tiles' ? totalCount : mapEvents.length,
    selected: 0,
    label: 'locations',
    hint: loading ? 'Loading…' : (
      renderMode === 'tiles'
        ? `${tiles.length.toLocaleString()} aggregated tile${tiles.length === 1 ? '' : 's'}`
        : (tracks.length > 0
            ? `${tracks.length} device track${tracks.length === 1 ? '' : 's'}`
            : null)
    ),
  });

  // Per-device colour for markers / track polylines — reuses the same
  // palette as the Events Center so a phone's colour is consistent
  // across tabs.
  const deviceColorOf = useCallback(
    (key) => deviceColor(key, reports),
    [reports],
  );

  // Selection bridge — clicking a marker or table row publishes to the
  // universal rail. Type 'location' routes to EventAccordion (raw row);
  // type 'location_tile' routes to LocationTileAccordion (which fetches
  // the rows inside that bucket so the user can drill into the cluster
  // without zooming in).
  const { selectEntity } = useCellebriteSelection();
  const [selectedId, setSelectedId] = useState(null);

  const handleSelect = useCallback((row) => {
    if (!row) {
      setSelectedId(null);
      return;
    }
    const id = row.id || row.node_key || null;
    setSelectedId(id);
    if (row.event_type === 'location_tile' && row._tile) {
      selectEntity({
        type: 'location_tile',
        id,
        caseId,
        payload: {
          ...row,
          cell_x: row._tile.cell_x,
          cell_y: row._tile.cell_y,
          cell_deg: tileCellDeg,
          count: row._tile.count,
          top_apps: row._tile.top_apps,
          report_keys: [...selectedReportKeys],
          start_date: startDate || null,
          end_date: endDate || null,
        },
        source: 'locations',
      });
    } else {
      selectEntity({
        type: 'location',
        id,
        caseId,
        reportKey: row.device_report_key,
        payload: { ...row, event_type: 'location' },
        source: 'locations',
      });
    }
  }, [caseId, selectEntity, tileCellDeg, selectedReportKeys, startDate, endDate]);

  // ------------------------------------------------------------------
  // Layout
  // ------------------------------------------------------------------

  if (!caseId) return null;

  if (selectedReportKeys.size === 0) {
    return (
      <div className="h-full flex flex-col bg-white">
        <PhoneSelector />
        <NoPhonesSelectedEmptyState message="Select one or more phones to see their locations." />
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-white min-h-0">
      <PhoneSelector />

      {/* Mode toggle + scrubber. Tiles mode hides the scrubber + search
          (they don't carry meaningful info when the rows have been
          server-aggregated). Raw mode keeps both for finer drilldown. */}
      <div className="flex items-center gap-2 px-4 py-1.5 border-b border-light-200 bg-light-50 text-xs">
        <span className="text-light-500">View:</span>
        <ModeButton current={renderMode} mode="tiles" onClick={setRenderMode}>
          Aggregated tiles
        </ModeButton>
        <ModeButton current={renderMode} mode="raw" onClick={setRenderMode}>
          Raw points
        </ModeButton>
        <span className="ml-2 text-light-400">
          {renderMode === 'tiles'
            ? 'Cheap server-side aggregation. Click a tile for the rows it contains.'
            : 'Capped at 5,000 points — narrow with date/search to focus.'}
        </span>
      </div>

      {renderMode === 'raw' && (
        <TimelineScrubber
          items={mapEvents}
          windowStart={windowStart}
          windowEnd={windowEnd}
          onWindowChange={(s, e) => { setWindowStart(s); setWindowEnd(e); }}
        />
      )}

      {/* Search — only useful in raw mode. */}
      {renderMode === 'raw' && (
        <div className="px-4 py-2 border-b border-light-200 bg-white flex-shrink-0">
          <CellebriteSearchInput
            value={searchQuery}
            onChange={setSearchQuery}
            placeholder="Search locations — try place:london or near:51.5,-0.1,5km"
            matchCount={mapEvents.length}
            totalCount={locations.length}
            itemNoun="location"
            focusOnSlash
          />
        </div>
      )}

      {/* Map / table split. Map gets the larger share — table scrolls
          underneath. Reader's Device Locations view uses the same
          horizontal banner-then-table layout.

          Resizable: drag the divider to give the map or table more
          room. Persisted per-case so the user's preferred ratio comes
          back next session. */}
      <ResizableSplit
        direction="vertical"
        storageKey={`cb.locations.mapTable.${caseId}`}
        defaultSize={420}
        minSize={120}
        maxSize={1200}
        className="flex-1"
        first={(
          <div className="h-full relative">
            {error && (
              <div className="absolute inset-0 flex items-center justify-center text-sm text-red-700 bg-white/80 z-10">
                {error}
              </div>
            )}
            {loading && mapEvents.length === 0 && (
              <div className="absolute inset-0 flex items-center justify-center text-sm text-light-500 bg-white/80 z-10">
                <Loader2 className="w-4 h-4 animate-spin mr-2" />
                Loading locations…
              </div>
            )}
            <EventMapPanel
              events={mapEvents}
              tracks={renderMode === 'raw' ? tracks : []}
              playheadTime={null}
              trailWindowMs={30 * 60 * 1000}
              isPlaying={false}
              selectedEventId={selectedId}
              onEventClick={handleSelect}
              intersectionMatches={[]}
              deviceColorOf={deviceColorOf}
              isActive={isActive}
            />
          </div>
        )}
        second={(
          <LocationsTable
            locations={renderMode === 'raw' ? mapEvents : tileMarkers}
            selectedId={selectedId}
            onRowClick={handleSelect}
            reports={reports}
          />
        )}
      />
    </div>
  );
}

function toISODate(d) {
  if (!(d instanceof Date) || isNaN(d.getTime())) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function ModeButton({ current, mode, onClick, children }) {
  const active = current === mode;
  return (
    <button
      type="button"
      onClick={() => onClick(mode)}
      className={`px-2 py-0.5 rounded transition-colors ${
        active
          ? 'bg-emerald-100 text-emerald-800'
          : 'text-light-600 hover:bg-light-100'
      }`}
    >
      {children}
    </button>
  );
}

// Default export with no other side effects.
export { CellebriteLocations as RawLocations };

// Small leading icon so import sites don't have to repeat the import.
export const LocationsTabIcon = MapPin;
