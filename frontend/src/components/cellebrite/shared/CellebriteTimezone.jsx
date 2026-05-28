import React, { createContext, useContext, useState, useMemo, useEffect, useCallback } from 'react';
import { Clock, ChevronDown, Check } from 'lucide-react';
import {
  CB_ZONES, DEFAULT_TZ_ID, setTzId as setModuleTzId,
  fmtTime, fmtDateTime, fmtShort, dayKey, zoneAbbr, zoneTag, offsetLabel,
} from './cellebriteTime';

/**
 * Case-scoped timezone selection for the Cellebrite view. Holds the active
 * zone, persists it per case (localStorage), and mirrors it into the
 * cellebriteTime module so the plain formatters (formatTs / formatShortTime)
 * render in the same zone as the hook-based ones.
 */
const TimezoneContext = createContext(null);

function storageKey(caseId) {
  return `cb_tz_${caseId || 'default'}`;
}

export function CellebriteTimezoneProvider({ caseId, children }) {
  const [tzId, setTzIdState] = useState(() => {
    try {
      const saved = localStorage.getItem(storageKey(caseId));
      if (saved && CB_ZONES[saved]) return saved;
    } catch { /* noop */ }
    return DEFAULT_TZ_ID;
  });

  // Mirror into the module so non-hook formatters follow the same zone.
  useEffect(() => { setModuleTzId(tzId); }, [tzId]);

  // Re-read when the case changes (each case remembers its own zone).
  useEffect(() => {
    let next = DEFAULT_TZ_ID;
    try {
      const saved = localStorage.getItem(storageKey(caseId));
      if (saved && CB_ZONES[saved]) next = saved;
    } catch { /* noop */ }
    setTzIdState(next);
    setModuleTzId(next);
  }, [caseId]);

  const setTzId = useCallback((id) => {
    if (!CB_ZONES[id]) return;
    setTzIdState(id);
    setModuleTzId(id);
    try { localStorage.setItem(storageKey(caseId), id); } catch { /* noop */ }
  }, [caseId]);

  const value = useMemo(() => ({ tzId, setTzId }), [tzId, setTzId]);
  return <TimezoneContext.Provider value={value}>{children}</TimezoneContext.Provider>;
}

/**
 * Hook returning the active zone + formatters bound to it. Consuming this in a
 * component makes that component re-render when the analyst flips the zone, so
 * its timestamps + day grouping update live.
 */
export function useCellebriteTime() {
  const ctx = useContext(TimezoneContext);
  const tzId = ctx?.tzId || DEFAULT_TZ_ID;
  return useMemo(() => ({
    tzId,
    setTzId: ctx?.setTzId || (() => {}),
    fmtTime: (iso) => fmtTime(iso, tzId),
    fmtDateTime: (iso) => fmtDateTime(iso, tzId),
    fmtShort: (iso) => fmtShort(iso, tzId),
    dayKey: (iso) => dayKey(iso, tzId),
    zoneAbbr: (iso) => zoneAbbr(iso, tzId),
    zoneTag: (iso) => zoneTag(iso, tzId),
    offsetLabel: (iso) => offsetLabel(iso, tzId),
  }), [tzId, ctx]);
}

/**
 * Compact zone selector for the Cellebrite tab bar. Shows the active zone with
 * its current UTC offset (e.g. "Device · EDT (UTC−4)") and lets the analyst
 * switch to UTC — the safe common clock when comparing devices set to
 * different timezones.
 */
export default function CellebriteTimezoneSelector() {
  const { tzId, setTzId } = useCellebriteTime();
  const [open, setOpen] = useState(false);
  const nowIso = new Date().toISOString();

  const current = CB_ZONES[tzId] || CB_ZONES[DEFAULT_TZ_ID];
  const currentTag = tzId === 'utc' ? 'UTC' : zoneTag(nowIso, tzId);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 px-2 py-1 text-[11px] rounded border border-light-300 bg-white hover:bg-light-50 text-light-700"
        title="Timezone used for all timestamps and the day grouping in this view"
      >
        <Clock className="w-3 h-3 text-light-500" />
        <span className="font-medium">{current.label}</span>
        <span className="text-light-500">· {currentTag}</span>
        <ChevronDown className="w-3 h-3 text-light-400" />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div className="absolute right-0 mt-1 z-40 w-56 rounded border border-light-200 bg-white shadow-lg py-1">
            <div className="px-2.5 py-1 text-[10px] uppercase tracking-wide text-light-400">
              Display timezone
            </div>
            {Object.entries(CB_ZONES).map(([id, z]) => {
              const tag = id === 'utc' ? 'UTC±0' : zoneTag(nowIso, id);
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => { setTzId(id); setOpen(false); }}
                  className={`w-full flex items-center gap-2 px-2.5 py-1.5 text-left text-xs hover:bg-light-50 ${
                    id === tzId ? 'text-owl-blue-800' : 'text-light-700'
                  }`}
                >
                  <span className="w-3 flex-shrink-0">
                    {id === tzId && <Check className="w-3 h-3 text-owl-blue-600" />}
                  </span>
                  <span className="font-medium">{z.label}</span>
                  <span className="ml-auto font-mono text-[10px] text-light-500">{tag}</span>
                </button>
              );
            })}
            <div className="px-2.5 pt-1.5 pb-1 text-[10px] text-light-400 border-t border-light-100 mt-1">
              Applies to every timestamp + the day grouping. Use UTC to align
              devices set to different timezones.
            </div>
          </div>
        </>
      )}
    </div>
  );
}
