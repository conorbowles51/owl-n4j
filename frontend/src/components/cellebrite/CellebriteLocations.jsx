import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, MapPin, Route } from 'lucide-react';
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
  // Small sample of raw location rows used SOLELY to build search
  // typeahead suggestions. The main load is gated on renderMode (tiles
  // by default = no raw rows fetched), but the search needs distinct
  // values regardless. We keep this fetch tiny + filter-independent so
  // a user typing `type:` always sees real suggestions.
  const [suggestionsSample, setSuggestionsSample] = useState([]);
  // Table view-mode toggle. The MAP renderMode controls aggregation
  // on the map; this controls how the TABLE underneath presents the
  // same data so investigators can swap perspective without re-
  // fetching. Three options:
  //   'auto'        → mirrors renderMode (rows in raw mode, tiles in tile mode)
  //   'rows'        → force one row per Location node
  //   'byPhoneDay'  → pivot raw rows into (phone × day × source app)
  //                   buckets — the "what was actually happening here"
  //                   perspective the user asked for.
  const [tableView, setTableView] = useState('auto');
  // Trajectory mode: time-ordered polyline through visible points.
  // Only meaningful in raw mode (tile centroids aren't a path);
  // toggling it on while in tiles mode auto-switches to raw.
  const [trajectoryOn, setTrajectoryOn] = useState(false);
  // Fly-to-on-row-click: encode click time so the map's FlyToSelected
  // effect re-fires even when the user clicks the same row twice
  // after panning the map manually.
  const [flyToId, setFlyToId] = useState(null);
  // Coarse zoom we feed to the tiles endpoint. Reader-style approach:
  // a single coarse view for the whole case; finer-grained drilldowns
  // come from clicking a tile (G3) rather than from map zoom-tracking.
  const TILE_ZOOM = 6;

  // Trajectory needs individual points, not aggregated tiles. When
  // the user enables trajectory while in tiles mode, slip into raw
  // mode automatically so the polyline has data to draw.
  useEffect(() => {
    if (trajectoryOn && renderMode === 'tiles') {
      setRenderMode('raw');
    }
  }, [trajectoryOn, renderMode]);

  // Same auto-switch when the user starts typing a search — tiles
  // are server-aggregated centroids with no addresses, so any
  // place:/near:/text query needs raw points to filter against.
  useEffect(() => {
    if (searchQuery && searchQuery.trim() && renderMode === 'tiles') {
      setRenderMode('raw');
    }
  }, [searchQuery, renderMode]);

  // One-shot small fetch of raw location rows for the search typeahead.
  // The main fetch is filter-dependent and (in tile mode) returns
  // aggregated centroids with no location_type / source_app per row,
  // so we wouldn't have anything to suggest from. This separate fetch
  // is filter-independent and small (500 rows) — enough to seed the
  // dropdown with real distinct values for type / app / place /
  // admin1 / country.
  useEffect(() => {
    if (!caseId || !reportsReady) return undefined;
    if (selectedReportKeys.size === 0) {
      setSuggestionsSample([]);
      return undefined;
    }
    let cancelled = false;
    cellebriteEventsAPI
      .getEvents(caseId, {
        reportKeys: [...selectedReportKeys],
        eventTypes: ['location'],
        onlyGeolocated: false,
        limit: 500,
      })
      .then((res) => {
        if (cancelled) return;
        setSuggestionsSample(res?.events || []);
      })
      .catch(() => {
        if (cancelled) return;
        setSuggestionsSample([]);
      });
    return () => { cancelled = true; };
  }, [caseId, reportsReady, selectedReportKeys]);

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

  // Trajectory tracks. When the toggle is on AND we're in raw mode
  // (tiles mode auto-switched above), build one synth track per
  // device sorted chronologically. The map's existing track renderer
  // draws cyan-ish polylines through them.
  const trajectoryTracks = useMemo(() => {
    if (!trajectoryOn || renderMode !== 'raw') return [];
    // Group by device so each phone gets its own polyline coloured
    // by its identity — matches the Events Center / Overview pattern.
    const byDevice = new Map();
    for (const loc of locations) {
      if (loc.latitude == null || loc.longitude == null || !loc.timestamp) continue;
      const rk = loc.device_report_key || 'unknown';
      if (!byDevice.has(rk)) byDevice.set(rk, []);
      byDevice.get(rk).push({
        lat: loc.latitude,
        lon: loc.longitude,
        timestamp: loc.timestamp,
      });
    }
    const out = [];
    for (const [rk, pts] of byDevice.entries()) {
      if (pts.length < 2) continue;
      pts.sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || ''));
      out.push({
        device_report_key: rk,
        points: pts,
        color_hint: deviceColorOf(rk),
      });
    }
    return out;
  }, [trajectoryOn, renderMode, locations, deviceColorOf]);

  // Search typeahead — pulls suggestions out of the actual loaded
  // data so the user can `Tab` through real values instead of
  // having to remember the exact spelling / casing / punctuation.
  //
  // We union the LIVE rows (which may be empty in tiles mode) with
  // the small `suggestionsSample` fetch so the dropdown works
  // regardless of which map mode is active. Each operator is capped
  // at its top-N most-frequent values so a very busy case (e.g.
  // 50 apps) doesn't flood the dropdown.
  const searchSuggestions = useMemo(() => {
    const allRows = [...(locations || []), ...(suggestionsSample || [])];
    const tally = (rows, field) => {
      const m = new Map();
      for (const r of rows) {
        const v = r?.[field];
        if (!v) continue;
        m.set(v, (m.get(v) || 0) + 1);
      }
      return [...m.entries()]
        .sort((a, b) => b[1] - a[1])
        .slice(0, 50);
    };
    const apps = tally(allRows, 'source_app');
    const types = tally(allRows, 'location_type');
    const countries = tally(allRows, 'country');
    const admin1s = tally(allRows, 'admin1');
    const placeNames = tally(allRows, 'place_name');
    // Devices: pull from the case's report list so suggestions show
    // up even before any data row matches (e.g. typing `phone:` on
    // an empty search). Hint = device model / owner.
    const devs = (reports || []).map((r) => ({
      operator: 'phone',
      value: r.short_label || r.report_key,
      hint: [r.device_model, r.phone_owner_name].filter(Boolean).join(' · '),
    }));
    const out = [];
    for (const [v, n] of apps) {
      out.push({ operator: 'app', value: v, hint: `${n.toLocaleString()} hits` });
    }
    for (const [v, n] of types) {
      out.push({ operator: 'type', value: v, hint: `${n.toLocaleString()} hits` });
    }
    for (const [v, n] of placeNames) {
      out.push({ operator: 'place', value: v, hint: `${n.toLocaleString()} hits` });
    }
    for (const [v, n] of admin1s) {
      out.push({ operator: 'place', value: v, hint: `${n.toLocaleString()} hits · region` });
    }
    for (const [v, n] of countries) {
      out.push({ operator: 'place', value: v, hint: `${n.toLocaleString()} hits · country` });
    }
    out.push(...devs);
    // Synthetic fallbacks so the dropdown is never empty even on
    // edge cases where the sample fetch hasn't returned yet or the
    // case has no location_type data at all. These are the common
    // Cellebrite location_type values; they'll deduplicate naturally
    // when the real data also contains them (we don't try to filter
    // dupes here — the search input's filter step handles it cheaply).
    const seenTypes = new Set(types.map(([v]) => v.toLowerCase()));
    for (const v of ['Visited', 'Unknown', 'Saved', 'Recent', 'Native Locations']) {
      if (!seenTypes.has(v.toLowerCase())) {
        out.push({ operator: 'type', value: v, hint: 'common' });
      }
    }
    return out;
  }, [locations, suggestionsSample, reports]);

  // The actual flyToId we hand the map is the bare id (the
  // ::timestamp suffix is just our re-trigger signal).
  const flyToIdForMap = flyToId ? flyToId.split('::')[0] : null;

  // Selection bridge — clicking a marker or table row publishes to the
  // universal rail. Type 'location' routes to EventAccordion (raw row);
  // type 'location_tile' routes to LocationTileAccordion (which fetches
  // the rows inside that bucket so the user can drill into the cluster
  // without zooming in).
  const { selectEntity, selection } = useCellebriteSelection();
  const [selectedId, setSelectedId] = useState(null);
  // Rail-driven map recentering. When the user drills into a tile
  // through the rail (LocationTileAccordion -> click a row inside),
  // the selection becomes a `location` whose lat/lon isn't in the
  // map's `events` array (the map is still showing tile centroids).
  // We watch the selection and push lat/lon directly into the map
  // via flyToCoord — bypasses the events lookup. The tick bump
  // re-fires the effect on identical-coord re-selections.
  const [flyToCoord, setFlyToCoord] = useState(null);
  const lastFlyKeyRef = useRef(null);
  useEffect(() => {
    if (!selection) return;
    const t = selection.type;
    if (t !== 'location' && t !== 'location_tile') return;
    const p = selection.payload || {};
    const lat = p.latitude ?? p.lat;
    const lon = p.longitude ?? p.lon;
    if (lat == null || lon == null) return;
    // De-dupe: same selection id shouldn't re-fly on every render.
    const key = `${selection.id}|${lat}|${lon}`;
    if (lastFlyKeyRef.current === key) return;
    lastFlyKeyRef.current = key;
    setFlyToCoord({ lat: Number(lat), lon: Number(lon), tick: Date.now() });
  }, [selection]);

  const handleSelect = useCallback((row) => {
    if (!row) {
      setSelectedId(null);
      setFlyToId(null);
      return;
    }
    const id = row.id || row.node_key || null;
    setSelectedId(id);
    // Encode the click time so the map's FlyToSelected effect re-
    // fires even when the user clicks the same row twice after
    // panning the map manually.
    if (id) setFlyToId(id + '::' + Date.now());
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

      {/* Mode toggle + trajectory toggle. Tiles is the default for
          big cases (cheap server-side aggregation); raw mode shows
          individual points. Trajectory needs raw points to draw a
          polyline so enabling it auto-switches modes (effect above). */}
      <div className="flex items-center gap-2 px-4 py-1.5 border-b border-light-200 bg-light-50 text-xs">
        <span className="text-light-500">View:</span>
        <ModeButton current={renderMode} mode="tiles" onClick={setRenderMode}>
          Aggregated tiles
        </ModeButton>
        <ModeButton current={renderMode} mode="raw" onClick={setRenderMode}>
          Raw points
        </ModeButton>
        <button
          type="button"
          onClick={() => setTrajectoryOn((v) => !v)}
          className={`ml-2 flex items-center gap-1 px-2 py-0.5 rounded border transition-colors ${
            trajectoryOn
              ? 'bg-cyan-100 border-cyan-300 text-cyan-800'
              : 'bg-white border-light-300 text-light-700 hover:bg-light-100'
          }`}
          title={
            trajectoryOn
              ? 'Hide chronological trajectory line'
              : 'Draw a polyline through points in time order (auto-switches to raw mode)'
          }
        >
          <Route className="w-3 h-3" />
          {trajectoryOn ? 'Trajectory ON' : 'Show trajectory'}
        </button>
        <span className="ml-2 text-light-400 truncate">
          {renderMode === 'tiles'
            ? 'Click a tile for the rows it contains. Cluster numbers = nearby tiles grouped at this zoom — zoom in to split them.'
            : 'Capped at 5,000 points — narrow with date/search. Cluster numbers = overlapping points at this zoom.'}
        </span>

        {/* Table-perspective toggle — sits in its own group on the
            right so it doesn't crowd the map controls. "Auto" mirrors
            the map's renderMode (most familiar); "Phone × day"
            pivots raw rows into the "what happened here, when,
            who was involved" view the user asked for. */}
        <div className="ml-auto inline-flex items-center gap-1 border-l border-light-300 pl-2">
          <span className="text-light-500">Table:</span>
          <TableViewButton current={tableView} mode="auto" onClick={setTableView}>
            Auto
          </TableViewButton>
          <TableViewButton current={tableView} mode="rows" onClick={setTableView}>
            Rows
          </TableViewButton>
          <TableViewButton current={tableView} mode="byPhoneDay" onClick={setTableView}>
            Phone × day
          </TableViewButton>
        </div>
      </div>

      {/* Search bar — always visible. Tiles mode does substring match
          on the rare tiles that carry textual top_apps; raw mode does
          full per-point filtering with place: / near: support. */}
      <div className="px-4 py-2 border-b border-light-200 bg-white flex-shrink-0">
        <CellebriteSearchInput
          value={searchQuery}
          onChange={setSearchQuery}
          placeholder="Search — Tab for suggestions (try place:london, near:38.97,-76.91,5km, app:WhatsApp, after:2024-01-01)"
          matchCount={renderMode === 'raw' ? mapEvents.length : tileMarkers.length}
          totalCount={renderMode === 'raw' ? locations.length : tileMarkers.length}
          itemNoun={renderMode === 'raw' ? 'location' : 'tile'}
          focusOnSlash
          suggestions={searchSuggestions}
          suggestionOperators={[
            'type', 'app', 'place', 'phone', 'near', 'after', 'before',
          ]}
        />
      </div>

      {renderMode === 'raw' && (
        <TimelineScrubber
          items={mapEvents}
          windowStart={windowStart}
          windowEnd={windowEnd}
          onWindowChange={(s, e) => { setWindowStart(s); setWindowEnd(e); }}
        />
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
              tracks={
                trajectoryOn
                  ? trajectoryTracks
                  : (renderMode === 'raw' ? tracks : [])
              }
              playheadTime={null}
              trailWindowMs={30 * 60 * 1000}
              isPlaying={false}
              selectedEventId={selectedId}
              flyToId={flyToIdForMap}
              flyToCoord={flyToCoord}
              onEventClick={handleSelect}
              intersectionMatches={[]}
              deviceColorOf={deviceColorOf}
              isActive={isActive}
            />
          </div>
        )}
        second={(() => {
          // Resolve the effective table view: 'auto' mirrors the
          // map's renderMode (tiles → tiles, raw → rows). Manual
          // 'rows' / 'byPhoneDay' overrides the auto behaviour BUT
          // requires raw rows to be loaded — if the map is in tile
          // mode and the user picks 'byPhoneDay' we fall back to the
          // tile table with a hint, since the per-phone pivot can't
          // be computed from server-aggregated tiles.
          let resolved;
          if (tableView === 'auto') {
            resolved = renderMode === 'raw' ? 'rows' : 'tiles';
          } else if (tableView === 'byPhoneDay' && renderMode === 'tiles') {
            // Tile centroids have no source_app or per-row timestamp,
            // so the pivot would be empty. Surface the issue.
            resolved = 'tiles';
          } else {
            resolved = tableView;
          }
          const tableRows = resolved === 'tiles' ? tileMarkers : mapEvents;
          return (
            <LocationsTable
              locations={tableRows}
              selectedId={selectedId}
              onRowClick={handleSelect}
              reports={reports}
              viewMode={resolved}
            />
          );
        })()}
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

/**
 * Small pill button used by the Table perspective group. Styled
 * with a cooler accent than ModeButton (which is for map render
 * mode) so the two control groups read as separate concerns.
 */
function TableViewButton({ current, mode, onClick, children }) {
  const active = current === mode;
  return (
    <button
      type="button"
      onClick={() => onClick(mode)}
      className={`px-2 py-0.5 rounded transition-colors ${
        active
          ? 'bg-owl-blue-100 text-owl-blue-800'
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
