import React, { useMemo, useRef, useState, useEffect } from 'react';
import { MapPin, Layers } from 'lucide-react';
import PhoneIdentityChip from '../shared/PhoneIdentityChip';
import { usePhoneReports } from '../../../context/PhoneReportsContext';
import { formatTs } from '../events/eventUtils';

/**
 * Compact table of locations rendered under the map.
 *
 * Three view modes via the `viewMode` prop:
 *
 *   - 'rows'   — one row per Location node (default; raw mode source
 *                of truth)
 *   - 'tiles'  — one row per aggregated tile (used when the map is
 *                in tiles mode; surfaces tile-level fields like top
 *                apps + count instead of leaving Source-app blank)
 *   - 'byPhoneDay' — one row per (phone × day × source app),
 *                aggregated client-side from the raw rows. Answers
 *                "what was actually happening here, when, who was
 *                involved" without making investigators read 5000
 *                individual GPS pings.
 *
 * Click any row → publishes selection to the universal rail. For
 * aggregated modes (tiles / byPhoneDay) the click opens the most
 * recent / centroid row inside that bucket.
 */
export default function LocationsTable({
  locations = [],
  selectedId = null,
  onRowClick,
  viewMode = 'rows',
  // Playback props. When playheadTime is non-null, each row in the
  // 'rows' view picks up one of three visual states based on its
  // timestamp relative to the playhead:
  //   future  → opacity-30 (hasn't happened yet)
  //   trail   → left-edge ring in playback colour (in the trail window)
  //   past    → unchanged
  // Rows are NEVER removed — the user keeps their reading-position
  // even as the playhead moves. Aggregate views (tiles / byPhoneDay)
  // ignore these props since they don't have a single timestamp per
  // row.
  playheadTime = null,
  trailWindowMs = 30 * 60 * 1000,
}) {
  const phoneCtx = usePhoneReports();
  const showPhoneChip = !!phoneCtx?.hasMultiple;

  if (!locations || locations.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-xs text-light-500">
        No locations match the current filters.
      </div>
    );
  }

  if (viewMode === 'tiles') {
    return (
      <TilesTable locations={locations} selectedId={selectedId} onRowClick={onRowClick} />
    );
  }
  if (viewMode === 'byPhoneDay') {
    return (
      <ByPhoneDayTable
        locations={locations}
        selectedId={selectedId}
        onRowClick={onRowClick}
        showPhoneChip={showPhoneChip}
      />
    );
  }

  // viewMode === 'rows' (default). Windowed so a 68k-point case doesn't
  // mount 68k <tr> (its own multi-second freeze, separate from the map).
  return (
    <LocationRowsView
      locations={locations}
      selectedId={selectedId}
      onRowClick={onRowClick}
      showPhoneChip={showPhoneChip}
      playheadTime={playheadTime}
      trailWindowMs={trailWindowMs}
    />
  );
}

// Fixed row height drives the windowing math. Keep in sync with the row's
// padding (py-1 + text-xs ≈ 29px). Overscan keeps a smooth scroll from
// reaching a blank edge before more rows mount.
const ROWS_ROW_PX = 29;
const ROWS_OVERSCAN = 12;

/**
 * Virtualised 'rows' table — renders only the rows in (and just around) the
 * viewport, with top/bottom spacer rows holding the scrollbar at full height.
 * Every location stays in the data + scrollable; we just don't put 68k <tr>
 * in the DOM at once.
 */
function LocationRowsView({ locations, selectedId, onRowClick, showPhoneChip, playheadTime, trailWindowMs }) {
  const scrollRef = useRef(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportH, setViewportH] = useState(480);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return undefined;
    setViewportH(el.clientHeight || 480);
    const onScroll = () => setScrollTop(el.scrollTop);
    el.addEventListener('scroll', onScroll, { passive: true });
    let ro;
    if (typeof ResizeObserver !== 'undefined') {
      ro = new ResizeObserver(() => setViewportH(el.clientHeight || 480));
      ro.observe(el);
    }
    return () => { el.removeEventListener('scroll', onScroll); if (ro) ro.disconnect(); };
  }, []);

  const colCount = showPhoneChip ? 10 : 9;
  const start = Math.max(0, Math.floor(scrollTop / ROWS_ROW_PX) - ROWS_OVERSCAN);
  const end = Math.min(locations.length, Math.ceil((scrollTop + viewportH) / ROWS_ROW_PX) + ROWS_OVERSCAN);
  const topPad = start * ROWS_ROW_PX;
  const bottomPad = Math.max(0, (locations.length - end) * ROWS_ROW_PX);
  const visible = locations.slice(start, end);

  return (
    <div ref={scrollRef} className="h-full overflow-y-auto">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-light-50 border-b border-light-200 z-10">
          <tr className="text-left text-light-500">
            <th className="px-3 py-1.5 font-medium">Time</th>
            <th className="px-3 py-1.5 font-medium">Type</th>
            <th className="px-3 py-1.5 font-medium">Source app</th>
            <th className="px-3 py-1.5 font-medium">Lat / Lon</th>
            <th className="px-3 py-1.5 font-medium" title="GPS accuracy in metres">±m</th>
            <th className="px-3 py-1.5 font-medium" title="Cellebrite carving confidence">Conf.</th>
            {showPhoneChip && <th className="px-3 py-1.5 font-medium">Device</th>}
            <th className="px-3 py-1.5 font-medium">Place</th>
            <th className="px-3 py-1.5 font-medium">Region</th>
            <th className="px-3 py-1.5 font-medium">Country</th>
          </tr>
        </thead>
        <tbody>
          {topPad > 0 && <tr style={{ height: topPad }}><td colSpan={colCount} /></tr>}
          {visible.map((loc) => {
            const id = loc.id || loc.node_key;
            const sel = id != null && id === selectedId;
            let playState = null;
            if (playheadTime && loc.timestamp) {
              const t = new Date(loc.timestamp).getTime();
              if (isFinite(t)) {
                const head = playheadTime.getTime();
                if (t > head) playState = 'future';
                else if (t >= head - trailWindowMs) playState = 'trail';
                else playState = 'past';
              }
            }
            const playClass = playState === 'future'
              ? 'opacity-30'
              : playState === 'trail'
                ? 'border-l-4 border-l-owl-blue-500'
                : '';
            return (
              <tr
                key={id || `${loc.latitude},${loc.longitude},${loc.timestamp}`}
                onClick={() => onRowClick?.(loc)}
                style={{ height: ROWS_ROW_PX }}
                className={`border-b border-light-100 cursor-pointer ${playClass} ${
                  sel ? 'bg-emerald-50/60 ring-1 ring-emerald-300/60' : 'hover:bg-light-50'
                }`}
              >
                <td className="px-3 py-1 tabular-nums whitespace-nowrap">
                  {loc.timestamp ? formatTs(loc.timestamp) : '—'}
                </td>
                <td className="px-3 py-1 truncate max-w-[160px]">
                  {loc.location_type || loc.label || '—'}
                </td>
                <td className="px-3 py-1 truncate max-w-[140px]">
                  {loc.source_app || '—'}
                </td>
                <td className="px-3 py-1 font-mono whitespace-nowrap text-[11px]">
                  <span className="inline-flex items-center gap-1">
                    <MapPin className="w-2.5 h-2.5 text-cyan-600" />
                    {Number(loc.latitude).toFixed(4)}, {Number(loc.longitude).toFixed(4)}
                  </span>
                </td>
                <td className="px-3 py-1 tabular-nums whitespace-nowrap text-light-600">
                  {loc.accuracy_meters != null
                    ? Math.round(loc.accuracy_meters).toLocaleString()
                    : <span className="text-light-400">—</span>}
                </td>
                <td className="px-3 py-1 whitespace-nowrap text-light-600">
                  {loc.confidence_score != null
                    ? String(loc.confidence_score)
                    : <span className="text-light-400">—</span>}
                </td>
                {showPhoneChip && (
                  <td className="px-3 py-1 whitespace-nowrap">
                    {loc.device_report_key ? (
                      <PhoneIdentityChip
                        reportKey={loc.device_report_key}
                        variant="dense"
                      />
                    ) : '—'}
                  </td>
                )}
                <td className="px-3 py-1 truncate max-w-[260px] text-light-700">
                  {loc.address || loc.place_name || <span className="text-light-400">—</span>}
                  {loc.geocode_source && loc.geocode_source !== 'cellebrite' && loc.geocode_source !== 'none' && (
                    <span
                      className="ml-1.5 text-[9px] uppercase tracking-wide bg-light-100 text-light-600 px-1 py-px rounded"
                      title={`Address reverse-geocoded via ${loc.geocode_source}${loc.geocode_accuracy ? ` (${loc.geocode_accuracy})` : ''}`}
                    >
                      via {loc.geocode_source}
                    </span>
                  )}
                </td>
                <td className="px-3 py-1 truncate max-w-[140px] text-light-600">
                  {loc.admin1 || <span className="text-light-400">—</span>}
                </td>
                <td className="px-3 py-1 truncate max-w-[120px] text-light-600">
                  {loc.country || <span className="text-light-400">—</span>}
                </td>
              </tr>
            );
          })}
          {bottomPad > 0 && <tr style={{ height: bottomPad }}><td colSpan={colCount} /></tr>}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Tile-view rows. Each row is one aggregated tile carrying its count
 * and top apps. Was previously rendered through the generic 'rows'
 * table which left Source-app blank — this is the dedicated view
 * that surfaces the tile-level fields instead.
 */
function TilesTable({ locations, selectedId, onRowClick }) {
  return (
    <div className="h-full overflow-y-auto">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-light-50 border-b border-light-200 z-10">
          <tr className="text-left text-light-500">
            <th className="px-3 py-1.5 font-medium">Tile</th>
            <th className="px-3 py-1.5 font-medium">Hits</th>
            <th className="px-3 py-1.5 font-medium">Top apps</th>
            <th className="px-3 py-1.5 font-medium">Lat / Lon (centroid)</th>
          </tr>
        </thead>
        <tbody>
          {locations.map((loc) => {
            const id = loc.id || loc.node_key;
            const sel = id != null && id === selectedId;
            const tile = loc._tile || {};
            const topApps = tile.top_apps || [];
            return (
              <tr
                key={id || `${loc.latitude},${loc.longitude}`}
                onClick={() => onRowClick?.(loc)}
                className={`border-b border-light-100 cursor-pointer ${
                  sel ? 'bg-emerald-50/60 ring-1 ring-emerald-300/60' : 'hover:bg-light-50'
                }`}
              >
                <td className="px-3 py-1 truncate max-w-[180px]">
                  <span className="inline-flex items-center gap-1">
                    <Layers className="w-2.5 h-2.5 text-cyan-600" />
                    {loc.label || 'Tile'}
                  </span>
                </td>
                <td className="px-3 py-1 tabular-nums whitespace-nowrap font-medium">
                  {(tile.count || 0).toLocaleString()}
                </td>
                <td className="px-3 py-1 truncate max-w-[280px] text-light-700">
                  {topApps.length > 0 ? topApps.join(', ') : <span className="text-light-400">—</span>}
                </td>
                <td className="px-3 py-1 font-mono whitespace-nowrap text-[11px]">
                  <span className="inline-flex items-center gap-1">
                    <MapPin className="w-2.5 h-2.5 text-cyan-600" />
                    {Number(loc.latitude).toFixed(4)}, {Number(loc.longitude).toFixed(4)}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/**
 * By-phone-by-day pivot. Aggregates raw rows into (phone × day ×
 * source_app) buckets so the user can read the table as "what device
 * was where on which day, and which app reported it" rather than as
 * thousands of individual fixes.
 *
 * Row click picks the LATEST raw row from the bucket so the rail /
 * map fly-to still resolves to a real Location node.
 */
function ByPhoneDayTable({ locations, selectedId, onRowClick, showPhoneChip }) {
  const rows = useMemo(() => {
    const buckets = new Map();
    for (const loc of locations) {
      if (loc.latitude == null || loc.longitude == null) continue;
      const day = (loc.timestamp || '').slice(0, 10) || '—';
      const phone = loc.device_report_key || '_unknown';
      const app = loc.source_app || '—';
      const key = `${phone}|${day}|${app}`;
      let b = buckets.get(key);
      if (!b) {
        b = {
          key,
          phone,
          day,
          app,
          count: 0,
          first: null,
          last: null,
          latSum: 0,
          lonSum: 0,
          sampleRow: loc,
        };
        buckets.set(key, b);
      }
      b.count += 1;
      b.latSum += loc.latitude;
      b.lonSum += loc.longitude;
      if (!b.first || (loc.timestamp || '') < b.first) b.first = loc.timestamp;
      if (!b.last || (loc.timestamp || '') > b.last) {
        b.last = loc.timestamp;
        b.sampleRow = loc; // latest row wins for click target
      }
    }
    const out = [...buckets.values()].map((b) => ({
      ...b,
      lat: b.latSum / b.count,
      lon: b.lonSum / b.count,
    }));
    out.sort((a, b) => (b.last || '').localeCompare(a.last || ''));
    return out;
  }, [locations]);

  if (rows.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-xs text-light-500">
        Nothing to group by phone × day under the current filters.
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-light-50 border-b border-light-200 z-10">
          <tr className="text-left text-light-500">
            <th className="px-3 py-1.5 font-medium">Day</th>
            {showPhoneChip && <th className="px-3 py-1.5 font-medium">Device</th>}
            <th className="px-3 py-1.5 font-medium">Source app</th>
            <th className="px-3 py-1.5 font-medium">Hits</th>
            <th className="px-3 py-1.5 font-medium">First → Last</th>
            <th className="px-3 py-1.5 font-medium">Centroid</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const id = r.sampleRow.id || r.sampleRow.node_key;
            const sel = id != null && id === selectedId;
            return (
              <tr
                key={r.key}
                onClick={() => onRowClick?.(r.sampleRow)}
                className={`border-b border-light-100 cursor-pointer ${
                  sel ? 'bg-emerald-50/60 ring-1 ring-emerald-300/60' : 'hover:bg-light-50'
                }`}
              >
                <td className="px-3 py-1 tabular-nums whitespace-nowrap">{r.day}</td>
                {showPhoneChip && (
                  <td className="px-3 py-1 whitespace-nowrap">
                    {r.phone && r.phone !== '_unknown' ? (
                      <PhoneIdentityChip reportKey={r.phone} variant="dense" />
                    ) : (
                      <span className="text-light-400">—</span>
                    )}
                  </td>
                )}
                <td className="px-3 py-1 truncate max-w-[160px]">{r.app}</td>
                <td className="px-3 py-1 tabular-nums whitespace-nowrap font-medium">
                  {r.count.toLocaleString()}
                </td>
                <td className="px-3 py-1 tabular-nums whitespace-nowrap text-light-600">
                  {r.first && r.last
                    ? r.first === r.last
                      ? formatTs(r.first)
                      : `${formatTs(r.first)} → ${formatTs(r.last)}`
                    : '—'}
                </td>
                <td className="px-3 py-1 font-mono whitespace-nowrap text-[11px]">
                  <span className="inline-flex items-center gap-1">
                    <MapPin className="w-2.5 h-2.5 text-cyan-600" />
                    {r.lat.toFixed(4)}, {r.lon.toFixed(4)}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
