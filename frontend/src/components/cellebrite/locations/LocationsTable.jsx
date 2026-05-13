import React from 'react';
import { MapPin } from 'lucide-react';
import PhoneIdentityChip from '../shared/PhoneIdentityChip';
import { usePhoneReports } from '../../../context/PhoneReportsContext';
import { formatTs } from '../events/eventUtils';

/**
 * Compact table of locations rendered under the map. Single click
 * publishes selection to the universal rail (same handler the map
 * uses). Stays slim — the rail and the map together cover the
 * detail/visualisation needs, this just gives investigators a
 * scrollable list keyed by time/source app.
 *
 * Virtualisation is intentionally not used here yet — the parent
 * caps the load at 5000 rows and renders the table inside a fixed
 * 256px container, so the DOM cost is bounded by the visible area.
 * If a Locations tab usage exceeds this, swap the body for a
 * windowed list later.
 */
export default function LocationsTable({ locations = [], selectedId = null, onRowClick }) {
  const phoneCtx = usePhoneReports();
  const showPhoneChip = !!phoneCtx?.hasMultiple;

  if (!locations || locations.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-xs text-light-500">
        No locations match the current filters.
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-light-50 border-b border-light-200 z-10">
          <tr className="text-left text-light-500">
            <th className="px-3 py-1.5 font-medium">Time</th>
            <th className="px-3 py-1.5 font-medium">Type</th>
            <th className="px-3 py-1.5 font-medium">Source app</th>
            <th className="px-3 py-1.5 font-medium">Lat / Lon</th>
            {showPhoneChip && <th className="px-3 py-1.5 font-medium">Device</th>}
            <th className="px-3 py-1.5 font-medium">Address</th>
          </tr>
        </thead>
        <tbody>
          {locations.map((loc) => {
            const id = loc.id || loc.node_key;
            const sel = id != null && id === selectedId;
            return (
              <tr
                key={id || `${loc.latitude},${loc.longitude},${loc.timestamp}`}
                onClick={() => onRowClick?.(loc)}
                className={`border-b border-light-100 cursor-pointer ${
                  sel ? 'bg-emerald-50/60 ring-1 ring-emerald-300/60' : 'hover:bg-light-50'
                }`}
              >
                <td className="px-3 py-1 tabular-nums whitespace-nowrap">
                  {loc.timestamp ? formatTs(loc.timestamp) : '—'}
                </td>
                <td className="px-3 py-1 truncate max-w-[180px]">
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
                <td className="px-3 py-1 truncate max-w-[280px] text-light-700">
                  {loc.address || '—'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
