import React, { useEffect, useState } from 'react';
import { MapPin, Loader2 } from 'lucide-react';
import { cellebriteEventsAPI } from '../../../../services/api';
import { useCellebriteSelection } from '../CellebriteSelectionContext';
import { formatTs } from '../../events/eventUtils';

/**
 * Rail accordion for a clicked tile in the Locations tab. Fetches the
 * raw rows inside the tile via /cellebrite/locations/in-tile, then
 * renders them as a paginated list. Clicking a row inside this list
 * republishes the selection as type 'location' so the rail re-renders
 * via EventAccordion — the user gets a one-click drill-in path
 * without leaving the rail.
 */
export default function LocationTileAccordion({ selection }) {
  const payload = selection?.payload || {};
  const caseId = selection?.caseId;
  const cellX = payload.cell_x;
  const cellY = payload.cell_y;
  const cellDeg = payload.cell_deg;

  const [items, setItems] = useState([]);
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

      {/* Tile contents */}
      <div>
        <div className="text-[10px] uppercase tracking-wide text-light-500 mb-1">
          {loading ? 'Loading…' : `Tile contents (${items.length})`}
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
                  {it.timestamp && (
                    <span className="text-light-500 tabular-nums whitespace-nowrap">
                      {formatTs(it.timestamp)}
                    </span>
                  )}
                </div>
                <div className="text-light-500 mt-0.5">
                  {it.source_app && <span>{it.source_app}</span>}
                  {it.source_app && it.address && <span className="mx-1">·</span>}
                  {it.address && <span className="truncate">{it.address}</span>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
