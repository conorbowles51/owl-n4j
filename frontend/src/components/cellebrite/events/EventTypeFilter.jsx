import React from 'react';
import { EVENT_COLORS, EVENT_ICONS, EVENT_LABELS } from './eventUtils';

/**
 * Chip grid for toggling event types on/off.
 *
 * Props:
 *   types: array of {event_type, label, count, geolocated}
 *   active: Set<string> of event types currently enabled
 *   onChange: (Set<string>) => void
 *   onlyGeolocated: boolean
 *   onOnlyGeolocatedChange: (boolean) => void
 */
export default function EventTypeFilter({
  types = [],
  active,
  onChange,
  onlyGeolocated = false,
  onOnlyGeolocatedChange,
}) {
  const toggle = (et) => {
    const next = new Set(active);
    if (next.has(et)) next.delete(et);
    else next.add(et);
    onChange(next);
  };

  const allOn = () => onChange(new Set(types.map((t) => t.event_type)));
  const allOff = () => onChange(new Set());

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <button
        onClick={allOn}
        className="px-2 py-0.5 text-[10px] rounded border border-light-300 text-light-600 hover:bg-light-100"
      >
        All
      </button>
      <button
        onClick={allOff}
        className="px-2 py-0.5 text-[10px] rounded border border-light-300 text-light-600 hover:bg-light-100"
      >
        None
      </button>

      {types.map((t) => {
        const Icon = EVENT_ICONS[t.event_type] || EVENT_ICONS.location;
        const color = EVENT_COLORS[t.event_type] || '#64748b';
        const on = active.has(t.event_type);
        const dimmed = !on;
        return (
          <button
            key={t.event_type}
            onClick={() => toggle(t.event_type)}
            className={`flex items-center gap-1 px-2 py-1 rounded-full border text-xs font-medium transition-colors ${
              dimmed ? 'bg-white border-light-300 text-light-400' : 'text-white border-transparent'
            }`}
            style={dimmed ? undefined : { backgroundColor: color }}
            title={
              `${t.label}: ${t.count.toLocaleString()} total` +
              (t.geolocated ? ` · ${t.geolocated.toLocaleString()} geolocated` : '')
            }
          >
            <Icon className="w-3 h-3" />
            <span>{t.label}</span>
            <span className={`text-[10px] ${dimmed ? 'text-light-400' : 'text-white/80'}`}>
              {t.count.toLocaleString()}
            </span>
          </button>
        );
      })}

      <label className="flex items-center gap-1 ml-2 text-xs text-light-600 cursor-pointer select-none">
        <input
          type="checkbox"
          checked={onlyGeolocated}
          onChange={(e) => onOnlyGeolocatedChange?.(e.target.checked)}
          className="w-3 h-3"
        />
        Only geolocated
      </label>
    </div>
  );
}
