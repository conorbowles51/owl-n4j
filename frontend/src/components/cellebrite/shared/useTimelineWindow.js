import { useCallback, useMemo, useState } from 'react';
import { useCellebriteTime } from './CellebriteTimezone';
import {
  wallClockToInstant,
  instantToWallClock,
  instantToZoneDate,
} from './cellebriteTime';

/**
 * Zone-anchored timeline filter window — the single source of truth every
 * Cellebrite timeline uses for its date/time scrubber + "Pick dates" filter.
 *
 * THE BUG THIS REPLACES: each timeline stored the window as an ABSOLUTE
 * instant and derived its server bound with a browser-LOCAL `toISODate`, while
 * the rows were displayed and day-bucketed in the analyst-selected zone. So the
 * filter frame and the display frame disagreed, and flipping the zone slid the
 * visible boundary by the offset (a 00:00 UTC window looked like it started at
 * "20:00 the day before" in UTC−4) even though the analyst hadn't touched it.
 *
 * THE MODEL NOW: the window is stored as WALL-CLOCK strings — the literal
 * numbers the analyst typed/dragged — which are zone-independent. The absolute
 * instants are derived from those numbers IN THE ACTIVE ZONE, so when the zone
 * flips the numbers stay put and the selected instant-set re-anchors by the
 * offset. That is exactly "keep my typed times; if I switch UTC→UTC−4 the start
 * becomes what was 04:00 in the UTC set."
 *
 * Returns:
 *   windowStart / windowEnd : Date | null  — absolute instants in the active
 *                             zone (feed straight to the scrubber, unchanged).
 *   startDate / endDate     : string       — coarse UTC day bounds for the
 *                             server fetch, widened ±1 day so the precise
 *                             client filter below can never clip an edge event.
 *   setWindow(s, e)         : commit a window from instants (scrubber drag,
 *                             "Pick dates", swim-lane brush) — stored as the
 *                             wall-clock they represent in the active zone.
 *   inWindow(iso)           : precise instant-level predicate for the in-memory
 *                             filter, giving the time-of-day precision the
 *                             date-only server filter can't.
 *   formatInput / parseInput: zone-aware <input type="datetime-local"> ⇄ instant
 *                             converters to hand the scrubber's picker so the
 *                             typed numbers are read in the active zone.
 *   hasWindow               : whether any bound is set.
 */
export default function useTimelineWindow() {
  const { tzId } = useCellebriteTime();
  // The committed window, as the wall-clock NUMBERS the analyst chose. Null =
  // unbounded on that end. Zone-independent on purpose.
  const [startWall, setStartWall] = useState(null);
  const [endWall, setEndWall] = useState(null);

  // Absolute instants, resolved in the active zone. Recompute when the zone
  // flips → the numbers stay, the instants re-anchor.
  const windowStart = useMemo(() => {
    if (!startWall) return null;
    const ms = wallClockToInstant(startWall, tzId);
    return ms == null ? null : new Date(ms);
  }, [startWall, tzId]);
  const windowEnd = useMemo(() => {
    if (!endWall) return null;
    const ms = wallClockToInstant(endWall, tzId);
    return ms == null ? null : new Date(ms);
  }, [endWall, tzId]);

  // Coarse server bound = the UTC calendar day of each instant. The server
  // filters on the UTC-stored `n.date` (date only), so the UTC day of each
  // bound is exactly a SUPERSET of the precise instant window: every event in
  // [windowStart, windowEnd] has a UTC day within [startDate, endDate]. The
  // exact time-of-day trimming then happens client-side via inWindow(). No
  // padding needed, so a view that relies only on this coarse bound never pulls
  // a spurious extra day.
  const startDate = useMemo(
    () => (windowStart ? instantToZoneDate(windowStart.getTime(), 'utc') : ''),
    [windowStart],
  );
  const endDate = useMemo(
    () => (windowEnd ? instantToZoneDate(windowEnd.getTime(), 'utc') : ''),
    [windowEnd],
  );

  // Commit instants (from scrubber drag / picker / swim-lane brush) as the
  // wall-clock they represent in the active zone.
  const setWindow = useCallback(
    (s, e) => {
      setStartWall(s instanceof Date && !isNaN(s.getTime()) ? instantToWallClock(s.getTime(), tzId) : null);
      setEndWall(e instanceof Date && !isNaN(e.getTime()) ? instantToWallClock(e.getTime(), tzId) : null);
    },
    [tzId],
  );

  // Precise instant-window test — the time-of-day filter the coarse date bound
  // can't express. Open-ended when a bound is null; permissive on bad input so
  // a dateless row is never silently dropped by the filter.
  const inWindow = useCallback(
    (iso) => {
      if (!windowStart && !windowEnd) return true;
      if (!iso) return true;
      const t = new Date(iso).getTime();
      if (isNaN(t)) return true;
      if (windowStart && t < windowStart.getTime()) return false;
      if (windowEnd && t > windowEnd.getTime()) return false;
      return true;
    },
    [windowStart, windowEnd],
  );

  // Zone-aware datetime-local converters for the scrubber's "Pick dates" entry,
  // so what the analyst types is read in the active zone (not browser-local).
  const formatInput = useCallback((ms) => instantToWallClock(ms, tzId), [tzId]);
  const parseInput = useCallback((v) => wallClockToInstant(v, tzId), [tzId]);

  const hasWindow = !!(startWall || endWall);

  return {
    tzId,
    windowStart,
    windowEnd,
    startDate,
    endDate,
    setWindow,
    inWindow,
    formatInput,
    parseInput,
    hasWindow,
  };
}
