import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ArrowLeft, ArrowUp, ArrowDown, Search, Loader2, MapPin, Route,
} from 'lucide-react';
import { cellebriteOverviewAPI } from '../../../services/api';
import EventMapPanel from '../events/EventMapPanel';
import ResizableSplit from '../shared/ResizableSplit';
import PhoneIdentityChip from '../shared/PhoneIdentityChip';
import { formatTs, deviceColor } from '../events/eventUtils';
import { useCellebriteSelection } from '../shared/CellebriteSelectionContext';
import {
  ROW_HEIGHT, HEADER_HEIGHT, FOOTER_HEIGHT, useTableWindow, sortRows,
} from './overviewTableUtils';

/**
 * Overview → Locations.
 *
 * Unlike the other Overview tabs (Calls / Messages / Emails / Contacts)
 * this surface is fundamentally map-first. The default layout is a
 * resizable map-on-top, table-on-bottom split:
 *
 *   - Map shows every location point in the table; clicking a marker
 *     selects the row and opens its popup.
 *   - Clicking a table row pans+zooms the map to that point and opens
 *     its popup. Marker pulses with a halo via EventMapPanel's
 *     selectedEventId highlight.
 *   - "Show trajectory" toggle draws a chronological polyline through
 *     all visible points so investigators can see movement over time.
 *   - Selection also publishes to the universal right-rail so the
 *     existing location accordion can show full detail (address,
 *     accuracy, geocode source, etc.) — same pattern as Messages
 *     and Contacts.
 *
 * We don't reuse OverviewDetailView here because that shell owns the
 * whole height — we need a custom layout for the map/table split.
 * Fetch + sort + window-render utilities are reused directly.
 */

const DEFAULT_SORT = { key: 'timestamp', dir: 'desc' };
const TRAJECTORY_SORT = { key: 'timestamp', dir: 'asc' };

export default function OverviewLocationsView({ caseId, report, onBack }) {
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [sort, setSort] = useState(DEFAULT_SORT);
  const [selectedId, setSelectedId] = useState(null);
  const [flyToId, setFlyToId] = useState(null);
  const [trajectoryOn, setTrajectoryOn] = useState(false);

  const { selectEntity } = useCellebriteSelection();

  // Debounce search input.
  useEffect(() => {
    const id = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(id);
  }, [search]);

  // Fetch when filters / device change. Same pattern as
  // OverviewDetailView's effect — duplicated rather than shared
  // because the rest of this component diverges enough that the
  // shell wasn't reusable.
  useEffect(() => {
    if (!report?.report_key || !caseId) return undefined;
    let cancelled = false;
    setLoading(true);
    setError(null);
    cellebriteOverviewAPI.getLocations(caseId, report.report_key, {
      search: debouncedSearch || null,
      limit: 5000,
      offset: 0,
    })
      .then((data) => {
        if (cancelled) return;
        setRows(data.rows || []);
        setTotal(data.total || 0);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setRows([]);
        setError(err.message || 'Failed to load');
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, [caseId, report?.report_key, debouncedSearch]);

  // When trajectory mode is toggled on, force a chronological sort so
  // the polyline draws in time order. Switching back doesn't restore
  // the user's previous choice — kept simple; one sort at a time.
  useEffect(() => {
    if (trajectoryOn) setSort(TRAJECTORY_SORT);
  }, [trajectoryOn]);

  const sortedRows = useMemo(() => sortRows(rows, sort.key, sort.dir), [rows, sort]);
  const totalRows = sortedRows.length;
  const { bodyRef, startIdx, endIdx, totalHeight, onScroll } = useTableWindow(totalRows);
  const visibleRows = sortedRows.slice(startIdx, endIdx);

  // Map needs the projected event-row shape. Strip everything that
  // isn't geolocated — points without lat/lon would just throw the
  // bounds-fitter off-centre and clutter the cluster index.
  const mapEvents = useMemo(() => {
    return rows
      .filter((r) => r.latitude != null && r.longitude != null)
      .map((r) => ({
        id: r.id || r.node_key,
        node_key: r.node_key,
        event_type: 'location',
        label: r.name || r.location_type || 'Location',
        summary: [r.location_type, r.source_app].filter(Boolean).join(' · '),
        timestamp: r.timestamp,
        latitude: r.latitude,
        longitude: r.longitude,
        is_geolocated: true,
        location_source: 'direct',
        device_report_key: report?.report_key,
        source_app: r.source_app,
      }));
  }, [rows, report?.report_key]);

  // Synthetic single-device "track" containing all visible points in
  // chronological order — used by EventMapPanel's polyline renderer
  // to draw the trajectory. Only built when the toggle is on so we
  // don't pay the sort cost every render.
  const trajectoryTracks = useMemo(() => {
    if (!trajectoryOn) return [];
    const pts = sortedRows
      .filter((r) => r.latitude != null && r.longitude != null && r.timestamp)
      .map((r) => ({ lat: r.latitude, lon: r.longitude, timestamp: r.timestamp }));
    if (pts.length < 2) return [];
    return [{
      device_report_key: report?.report_key || 'overview-locations',
      points: pts,
      // Pre-bake the colour so EventMapPanel doesn't try to look it up.
      color_hint: '#0891b2', // cyan-600 — matches the Locations tab accent
    }];
  }, [trajectoryOn, sortedRows, report?.report_key]);

  // Row click → select + fly-to + publish to rail.
  const onRowClick = useCallback((row) => {
    const id = row.id || row.node_key;
    if (!id) return;
    setSelectedId(id);
    // Encode the click time into flyToId so the FlyToSelected effect
    // re-fires even when the user clicks the same row twice after
    // panning the map manually.
    setFlyToId(id + '::' + Date.now());
    selectEntity({
      type: 'location',
      id,
      caseId,
      reportKey: report?.report_key,
      payload: {
        ...row,
        node_key: row.node_key || row.id,
        event_type: 'location',
        device_report_key: report?.report_key,
      },
      source: 'overview.locations',
    });
  }, [caseId, report?.report_key, selectEntity]);

  // Map marker click → same flow as a row click.
  const onMarkerClick = useCallback((evt) => {
    const id = evt?.id || evt?.node_key;
    if (!id) return;
    const srcRow = rows.find((r) => (r.id || r.node_key) === id);
    onRowClick(srcRow || { id, node_key: id, ...evt });
  }, [onRowClick, rows]);

  const toggleSort = useCallback((key) => {
    setSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
        : { key, dir: 'desc' });
  }, []);

  // The actual flyToId we hand the map is the bare event id (the
  // ::timestamp suffix is just our re-trigger signal — strip it).
  const flyToIdForMap = flyToId ? flyToId.split('::')[0] : null;

  // Per-device colour for markers. Only one device on this surface
  // so really a fixed value, but we wire the function for parity
  // with how other map-using surfaces use it.
  const deviceColorOf = useCallback(
    (key) => report ? deviceColor(key, [report]) : '#0891b2',
    [report],
  );

  return (
    <div className="flex flex-col h-full min-h-0 bg-white">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-light-200 bg-light-50 flex-shrink-0">
        <button
          onClick={onBack}
          className="flex items-center gap-1 px-2 py-1 text-xs text-light-700 hover:text-owl-blue-700 hover:bg-light-100 rounded"
          title="Back to overview"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back
        </button>

        {report?.report_key && (
          <PhoneIdentityChip
            reportKey={report.report_key}
            variant="full"
            showIcon
          />
        )}

        <div className="flex items-center gap-1.5">
          <MapPin className="w-4 h-4 text-cyan-600" />
          <span className="text-sm font-semibold text-owl-blue-900">Locations</span>
          <span className="text-xs text-light-500">({total.toLocaleString()})</span>
        </div>

        <div className="relative flex-1 max-w-md ml-2">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-light-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search…"
            className="w-full pl-7 pr-2 py-1 text-xs border border-light-300 rounded focus:outline-none focus:border-owl-blue-400"
          />
        </div>

        {/* Trajectory toggle. When ON the table forces chronological
            sort and the map renders a cyan polyline through all
            visible points so investigators can see movement over time. */}
        <button
          type="button"
          onClick={() => setTrajectoryOn((v) => !v)}
          className={`flex items-center gap-1 px-2 py-1 text-xs rounded border transition-colors ${
            trajectoryOn
              ? 'bg-cyan-100 border-cyan-300 text-cyan-800'
              : 'bg-white border-light-300 text-light-700 hover:bg-light-100'
          }`}
          title={
            trajectoryOn
              ? 'Hide chronological trajectory line'
              : 'Show a polyline through all locations in time order'
          }
        >
          <Route className="w-3.5 h-3.5" />
          {trajectoryOn ? 'Trajectory ON' : 'Show trajectory'}
        </button>

        <div className="flex-1" />
        {loading && <Loader2 className="w-4 h-4 animate-spin text-light-400" />}
        {error && <span className="text-xs text-red-600">{error}</span>}
      </div>

      {/* Map / table split — resizable per-case via localStorage so
          investigators get their preferred layout back next session. */}
      <ResizableSplit
        direction="vertical"
        storageKey={`cb.overview.locations.mapTable.${caseId}.${report?.report_key || 'unknown'}`}
        defaultSize={420}
        minSize={120}
        maxSize={1200}
        className="flex-1"
        first={(
          <div className="h-full relative">
            {mapEvents.length === 0 && !loading && (
              <div className="absolute inset-0 flex items-center justify-center text-sm text-light-500 bg-light-50 z-10">
                No geolocated locations on this device.
              </div>
            )}
            <EventMapPanel
              events={mapEvents}
              tracks={trajectoryTracks}
              playheadTime={null}
              isPlaying={false}
              selectedEventId={selectedId}
              flyToId={flyToIdForMap}
              onEventClick={onMarkerClick}
              intersectionMatches={[]}
              deviceColorOf={deviceColorOf}
              isActive
            />
          </div>
        )}
        second={(
          <div className="flex flex-col h-full min-h-0 bg-white">
            {/* Column header */}
            <div
              className="grid border-b border-light-200 bg-light-50 text-[11px] font-semibold text-light-700 flex-shrink-0"
              style={{ gridTemplateColumns: '160px 200px 1fr 200px', height: HEADER_HEIGHT }}
            >
              <SortHeader col="timestamp" label="Time" sort={sort} toggleSort={toggleSort} />
              <SortHeader col="name" label="Name" sort={sort} toggleSort={toggleSort} />
              <SortHeader col="location_type" label="Type · Source" sort={sort} toggleSort={toggleSort} />
              <SortHeader col="latitude" label="Lat / Lon" sort={sort} toggleSort={toggleSort} />
            </div>

            {/* Body */}
            <div ref={bodyRef} onScroll={onScroll} className="flex-1 min-h-0 overflow-auto relative">
              {totalRows === 0 ? (
                <div className="flex items-center justify-center h-full text-sm text-light-500 italic">
                  {loading ? 'Loading…' : 'No locations found.'}
                </div>
              ) : (
                <div style={{ height: totalHeight, position: 'relative' }}>
                  {visibleRows.map((row, i) => {
                    const idx = startIdx + i;
                    const top = idx * ROW_HEIGHT;
                    const id = row.id || row.node_key;
                    const isSelected = id === selectedId;
                    return (
                      <div
                        key={id || idx}
                        className={`grid absolute inset-x-0 items-center border-b border-light-100 cursor-pointer ${
                          isSelected ? 'bg-cyan-50' : 'hover:bg-owl-blue-50'
                        }`}
                        style={{
                          top,
                          height: ROW_HEIGHT,
                          gridTemplateColumns: '160px 200px 1fr 200px',
                        }}
                        onClick={() => onRowClick(row)}
                      >
                        <div className="px-2 border-r border-light-100 truncate text-xs text-light-800">
                          {row.timestamp ? formatTs(row.timestamp) : '—'}
                        </div>
                        <div className="px-2 border-r border-light-100 truncate text-xs text-light-800">
                          {row.name || '—'}
                        </div>
                        <div className="px-2 border-r border-light-100 truncate text-xs text-light-700">
                          {[row.location_type, row.source_app].filter(Boolean).join(' · ') || '—'}
                        </div>
                        <div className="px-2 border-r border-light-100 truncate text-xs text-light-800">
                          {row.latitude != null && row.longitude != null ? (
                            <span className="flex items-center gap-1 font-mono text-[10px]">
                              <MapPin className="w-2.5 h-2.5 text-cyan-600" />
                              {Number(row.latitude).toFixed(4)}, {Number(row.longitude).toFixed(4)}
                            </span>
                          ) : '—'}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Footer */}
            <div
              className="flex items-center justify-between px-3 text-[10px] text-light-500 border-t border-light-200 bg-light-50 flex-shrink-0"
              style={{ height: FOOTER_HEIGHT }}
            >
              <span>
                Showing {totalRows.toLocaleString()} of {total.toLocaleString()}
                {trajectoryOn && ' · trajectory mode (sorted oldest → newest)'}
              </span>
              <span>
                Sorted by {sort.key} {sort.dir === 'asc' ? '↑' : '↓'}
              </span>
            </div>
          </div>
        )}
      />
    </div>
  );
}

function SortHeader({ col, label, sort, toggleSort }) {
  const active = sort.key === col;
  return (
    <button
      onClick={() => toggleSort(col)}
      className={`flex items-center gap-1 px-2 border-r border-light-200 hover:bg-light-100 justify-start ${
        active ? 'text-owl-blue-700' : 'text-light-700'
      }`}
    >
      <span className="truncate">{label}</span>
      {active && (sort.dir === 'asc'
        ? <ArrowUp className="w-2.5 h-2.5" />
        : <ArrowDown className="w-2.5 h-2.5" />
      )}
    </button>
  );
}
