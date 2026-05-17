import React, { useEffect, useState } from 'react';
import { MapPin, Loader2, Smartphone } from 'lucide-react';
import { cellebriteEventsAPI } from '../../../../services/api';
import { useCellebriteSelection } from '../CellebriteSelectionContext';
import { formatTs } from '../../events/eventUtils';
import PhoneIdentityChip from '../PhoneIdentityChip';

/**
 * Rail accordion for a clicked tile in the Locations tab.
 *
 * Renders three layered views of the same tile so the investigator
 * can answer the user's "what was actually happening here, when, who
 * was involved" question without leaving the rail:
 *
 *   1. Tile summary — total count, lat/lon centroid, top apps
 *   2. Per-phone breakdown — one row per device that contributed,
 *      with its visit count, first/last seen and the apps it used
 *      while inside this tile. Sourced from the new `per_phone`
 *      array on the /locations/in-tile response.
 *   3. Raw rows — every Location node inside the tile (paginated,
 *      capped at 200). Clicking one re-publishes as a `location`
 *      selection so the rail re-renders via EventAccordion.
 *
 * The per-phone block is the new thing — previously the rail showed
 * only "top apps" as a single line, hiding the device→app correlation
 * the user actually needed.
 */
export default function LocationTileAccordion({ selection }) {
  const payload = selection?.payload || {};
  const caseId = selection?.caseId;
  const cellX = payload.cell_x;
  const cellY = payload.cell_y;
  const cellDeg = payload.cell_deg;

  const [items, setItems] = useState([]);
  const [perPhone, setPerPhone] = useState([]);
  const [truncated, setTruncated] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Re-fetch whenever the user picks a different tile. We deliberately
  // refetch even if cell_x/cell_y haven't changed but the date window
  // has — the parent rebuilds the selection in that case.
  useEffect(() => {
    if (!caseId || cellDeg == null) return undefined;
    let cancelled = false;
    setLoading(true);
    setError(null);
    cellebriteEventsAPI.getLocationsInTile(caseId, {
      cellX,
      cellY,
      cellDeg,
      reportKeys: payload.report_keys || null,
      startDate: payload.start_date || null,
      endDate: payload.end_date || null,
      limit: 200,
    })
      .then((res) => {
        if (cancelled) return;
        setItems(res?.items || []);
        setPerPhone(res?.per_phone || []);
        setTruncated(!!res?.truncated);
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e?.message || 'Failed to load tile contents');
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, [caseId, cellX, cellY, cellDeg, payload.start_date, payload.end_date, payload.report_keys]);

  const { selectEntity } = useCellebriteSelection();

  if (cellDeg == null) {
    return (
      <div className="px-3 py-4 text-xs text-red-600">
        Tile selection is missing cell metadata.
      </div>
    );
  }

  return (
    <div className="px-3 py-2 space-y-3">
      {/* Tile summary header */}
      <div className="text-xs text-light-700">
        <div className="flex items-center gap-1.5">
          <MapPin className="w-3.5 h-3.5 text-cyan-600" />
          <span className="font-semibold">{(payload.count || 0).toLocaleString()} location{payload.count === 1 ? '' : 's'}</span>
          <span className="text-light-500">
            in this aggregated area
          </span>
        </div>
        {payload.top_apps && payload.top_apps.length > 0 && (
          <div className="mt-1 text-[11px] text-light-600">
            Top apps: {payload.top_apps.join(', ')}
          </div>
        )}
        {payload.lat != null && payload.lon != null && (
          <div className="mt-1 font-mono text-[10px] text-light-500">
            ~{Number(payload.lat).toFixed(4)}, {Number(payload.lon).toFixed(4)}
          </div>
        )}
      </div>

      {/* Per-phone breakdown — new */}
      {perPhone.length > 0 && (
        <PerPhoneBreakdown rows={perPhone} truncated={truncated} />
      )}

      {/* Raw rows */}
      <div>
        <div className="text-[10px] uppercase tracking-wide text-light-500 mb-1">
          {loading ? 'Loading…' : `Tile contents (${items.length}${truncated ? '+' : ''})`}
        </div>
        {loading && items.length === 0 ? (
          <div className="flex items-center justify-center py-4 text-xs text-light-500">
            <Loader2 className="w-3 h-3 animate-spin mr-1.5" />
            Fetching rows…
          </div>
        ) : error ? (
          <div className="text-xs text-red-700">{error}</div>
        ) : items.length === 0 ? (
          <div className="text-xs text-light-500 italic">
            No rows in this tile for the active filters.
          </div>
        ) : (
          <ul className="space-y-1 max-h-[320px] overflow-y-auto pr-1">
            {items.map((it) => (
              <li
                key={it.id || it.node_key}
                onClick={() => selectEntity({
                  type: 'location',
                  id: it.id || it.node_key,
                  caseId,
                  reportKey: it.device_report_key,
                  payload: { ...it, event_type: 'location' },
                  source: 'locations.tile',
                })}
                className="text-[11px] border border-light-100 rounded px-2 py-1 cursor-pointer hover:bg-light-50"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-owl-blue-900 truncate">
                    {it.label || it.location_type || 'Location'}
                  </span>
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    {it.device_report_key && (
                      <PhoneIdentityChip
                        reportKey={it.device_report_key}
                        variant="dense"
                      />
                    )}
                    {it.timestamp && (
                      <span className="text-light-500 tabular-nums whitespace-nowrap">
                        {formatTs(it.timestamp)}
                      </span>
                    )}
                  </div>
                </div>
                <div className="text-light-500 mt-0.5">
                  {it.source_app && <span>{it.source_app}</span>}
                  {it.source_app && (it.address || it.place_name) && <span className="mx-1">·</span>}
                  {(it.address || it.place_name) && (
                    <span className="truncate">
                      {it.address || it.place_name}
                      {!it.address && it.country && (
                        <span className="text-light-400"> · {it.country}</span>
                      )}
                    </span>
                  )}
                  {it.geocode_source && it.geocode_source !== 'cellebrite' && it.geocode_source !== 'none' && (
                    <span
                      className="ml-1 text-[9px] uppercase tracking-wide bg-light-100 text-light-500 px-1 rounded"
                      title={`Reverse-geocoded via ${it.geocode_source}`}
                    >
                      via {it.geocode_source}
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/**
 * Per-phone × per-app breakdown for one tile.
 *
 * Direct answer to the user's "the flyout doesn't really show what
 * phones are responsible for what apps making location hits"
 * complaint. One row per device, sorted by contribution descending;
 * the apps that phone used while inside this tile render as tiny
 * count chips so the device→app correlation is visible at a glance.
 *
 * Truncated when the underlying /locations/in-tile fetch hit its
 * row cap — surfaced as a warning so the user knows the counts are
 * a lower bound, not the full picture.
 */
function PerPhoneBreakdown({ rows, truncated }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-light-500 mb-1 flex items-center gap-1.5">
        <Smartphone className="w-3 h-3" />
        Per phone
        {truncated && (
          <span className="text-amber-700 normal-case tracking-normal">
            (counts based on first {rows.reduce((s, r) => s + r.count, 0)} rows — tile has more)
          </span>
        )}
      </div>
      <ul className="space-y-1.5">
        {rows.map((r) => (
          <li
            key={r.device_report_key || '_unknown'}
            className="border border-light-100 rounded px-2 py-1.5 text-[11px]"
          >
            <div className="flex items-center gap-2">
              {r.device_report_key ? (
                <PhoneIdentityChip reportKey={r.device_report_key} variant="dense" />
              ) : (
                <span className="text-light-400 italic">Unknown device</span>
              )}
              <span className="text-light-700 font-medium tabular-nums">
                {r.count.toLocaleString()} hit{r.count === 1 ? '' : 's'}
              </span>
              {r.last_seen && (
                <span className="ml-auto text-light-500 tabular-nums whitespace-nowrap">
                  last {formatTs(r.last_seen)}
                </span>
              )}
            </div>
            {r.apps && r.apps.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-1">
                {r.apps.slice(0, 8).map((a) => (
                  <span
                    key={a.app}
                    className="inline-flex items-center gap-1 px-1.5 py-px rounded-full bg-light-100 text-light-700 text-[10px]"
                    title={`${a.count} hits via ${a.app}`}
                  >
                    {a.app}
                    <span className="text-light-500 tabular-nums">{a.count}</span>
                  </span>
                ))}
                {r.apps.length > 8 && (
                  <span className="text-[10px] text-light-500">+{r.apps.length - 8} more</span>
                )}
              </div>
            )}
            {r.first_seen && r.last_seen && r.first_seen !== r.last_seen && (
              <div className="text-[10px] text-light-500 mt-0.5">
                {formatTs(r.first_seen)} → {formatTs(r.last_seen)}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
