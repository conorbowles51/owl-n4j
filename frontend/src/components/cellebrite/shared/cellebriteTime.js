/**
 * Single source of truth for how Cellebrite timestamps are displayed AND
 * grouped into days. Every event — WhatsApp/Instagram message, call, web
 * visit, log entry — is stored in UTC (verified: Cellebrite normalises the
 * XML to +00:00). The bug the team hit was that different surfaces rendered
 * those UTC instants in different zones (messages in browser-local, the detail
 * drawer effectively in another) and the Timeline grouped days by the *UTC*
 * calendar day while showing local times — so a UTC-midnight boundary looked
 * like "the day ends at 8 PM" and cross-day ordering looked scrambled.
 *
 * The cure: route ALL display + day-bucketing through these helpers with one
 * selected zone, so the whole view sits on the same clock. Sorting still uses
 * the absolute instant (new Date(iso).getTime()), which is zone-independent
 * and already correct.
 */

// Selectable zones. `device` = the device's local zone (this case's phones are
// US East Coast; America/New_York auto-handles the EST↔EDT DST change). `utc`
// is the safe common clock for comparing devices that were set to different
// zones. IANA zones drive Intl, which handles DST per-timestamp.
export const CB_ZONES = {
  device: { iana: 'America/New_York', label: 'Device' },
  utc: { iana: 'UTC', label: 'UTC' },
};
export const DEFAULT_TZ_ID = 'device';

const _dtfCache = new Map();
function _dtf(iana, opts) {
  const key = iana + '|' + JSON.stringify(opts);
  let f = _dtfCache.get(key);
  if (!f) {
    f = new Intl.DateTimeFormat('en-US', { timeZone: iana, hourCycle: 'h23', ...opts });
    _dtfCache.set(key, f);
  }
  return f;
}

function _ianaFor(tzId) {
  return (CB_ZONES[tzId] || CB_ZONES[DEFAULT_TZ_ID]).iana;
}

/** Wall-clock parts of an instant in a given zone, or null on bad input. */
function _parts(iso, iana) {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  const m = {};
  for (const p of _dtf(iana, {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  }).formatToParts(d)) {
    m[p.type] = p.value;
  }
  if (m.hour === '24') m.hour = '00'; // some engines emit 24 at midnight
  return m;
}

/** Minutes the zone is offset from UTC at this instant (handles DST). */
function _offsetMinutes(iso, iana) {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return 0;
  const m = _parts(iso, iana);
  if (!m) return 0;
  const asUTC = Date.UTC(+m.year, +m.month - 1, +m.day, +m.hour, +m.minute, +m.second);
  return Math.round((asUTC - d.getTime()) / 60000);
}

/**
 * Convert a wall-clock date/time the user typed in a given zone into the
 * equivalent UTC instant, formatted as a fixed-width "YYYY-MM-DDTHH:MM:SS"
 * string. Used by the date-range filter: stored event props are UTC, so a
 * boundary the user enters as "Apr 12 00:00 EDT" must be sent to the API as
 * the matching UTC instant ("2025-04-12T04:00:00"). Fixed width matters —
 * the backend does a lexicographic string compare.
 *
 * @param {string} dateStr  "YYYY-MM-DD" (falsy → returns null)
 * @param {string} [timeStr="00:00:00"] "HH:MM" or "HH:MM:SS"
 * @param {string} tzId     a CB_ZONES id (defaults to the device zone)
 * @returns {string|null}
 */
export function wallClockToUTCDateTime(dateStr, timeStr, tzId) {
  if (!dateStr) return null;
  const [y, mo, d] = dateStr.split('-').map(Number);
  const [h = 0, mi = 0, s = 0] = (timeStr || '00:00:00').split(':').map(Number);
  if ([y, mo, d, h, mi, s].some((n) => Number.isNaN(n))) return null;

  const iana = _ianaFor(tzId);
  // Treat the wall-clock parts as if they were UTC to get a provisional
  // instant, then look up how far the zone is ahead of UTC at that instant
  // (DST-aware) and shift back to the true UTC instant.
  const wallAsUTC = Date.UTC(y, mo - 1, d, h, mi, s);
  const offsetMin = _offsetMinutes(new Date(wallAsUTC).toISOString(), iana);
  const trueUTC = new Date(wallAsUTC - offsetMin * 60000);

  const p = (n) => String(n).padStart(2, '0');
  return (
    `${trueUTC.getUTCFullYear()}-${p(trueUTC.getUTCMonth() + 1)}-${p(trueUTC.getUTCDate())}` +
    `T${p(trueUTC.getUTCHours())}:${p(trueUTC.getUTCMinutes())}:${p(trueUTC.getUTCSeconds())}`
  );
}

// ---- Public formatters (all take an explicit tzId) --------------------

/** "HH:MM" in the selected zone. */
export function fmtTime(iso, tzId) {
  const m = _parts(iso, _ianaFor(tzId));
  return m ? `${m.hour}:${m.minute}` : '';
}

/** "YYYY-MM-DD HH:MM:SS" in the selected zone (detail/table use). */
export function fmtDateTime(iso, tzId) {
  const m = _parts(iso, _ianaFor(tzId));
  return m ? `${m.year}-${m.month}-${m.day} ${m.hour}:${m.minute}:${m.second}` : (iso || '');
}

/** Calendar day "YYYY-MM-DD" in the selected zone — the grouping/sort key. */
export function dayKey(iso, tzId) {
  const m = _parts(iso, _ianaFor(tzId));
  return m ? `${m.year}-${m.month}-${m.day}` : '—';
}

/** Short zone label for an instant, e.g. "EDT", "EST", "UTC". */
export function zoneAbbr(iso, tzId) {
  const iana = _ianaFor(tzId);
  try {
    const parts = _dtf(iana, { hour: '2-digit', timeZoneName: 'short' }).formatToParts(new Date(iso));
    const z = parts.find((p) => p.type === 'timeZoneName');
    if (z && z.value && !/^GMT/.test(z.value)) return z.value;
  } catch { /* fall through */ }
  return tzId === 'utc' ? 'UTC' : offsetLabel(iso, tzId);
}

/** "UTC−4" / "UTC+0" style offset label for an instant. */
export function offsetLabel(iso, tzId) {
  const off = _offsetMinutes(iso || new Date().toISOString(), _ianaFor(tzId));
  const sign = off < 0 ? '−' : '+';
  const abs = Math.abs(off);
  const h = Math.floor(abs / 60);
  const mm = abs % 60;
  return `UTC${sign}${h}${mm ? ':' + String(mm).padStart(2, '0') : ''}`;
}

/** "EDT (UTC−4)" combined tag for an instant. */
export function zoneTag(iso, tzId) {
  if (tzId === 'utc') return 'UTC';
  const ab = zoneAbbr(iso, tzId);
  const off = offsetLabel(iso, tzId);
  return ab && ab !== off ? `${ab} (${off})` : off;
}

/**
 * iMessage-style short label: time-only when on today's date (in zone),
 * otherwise "Mon D[, YYYY], HH:MM". Mirrors the old commsUtils.formatShortTime
 * shape but in the selected zone.
 */
export function fmtShort(iso, tzId) {
  if (!iso) return '';
  const iana = _ianaFor(tzId);
  const m = _parts(iso, iana);
  if (!m) return iso;
  const todayKey = dayKey(new Date().toISOString(), tzId);
  const thisKey = `${m.year}-${m.month}-${m.day}`;
  const time = `${m.hour}:${m.minute}`;
  if (thisKey === todayKey) return time;
  const monthName = _dtf(iana, { month: 'short' }).format(new Date(iso));
  const nowYear = dayKey(new Date().toISOString(), tzId).slice(0, 4);
  const datePart = m.year !== nowYear
    ? `${monthName} ${+m.day}, ${m.year}`
    : `${monthName} ${+m.day}`;
  return `${datePart}, ${time}`;
}

// ---- Wall-clock ⇄ instant conversion (zone-anchored filtering) ----------
//
// The timeline filter is "wall-clock anchored": the analyst types a start/end
// (e.g. 00:00) and those NUMBERS are read in whatever zone the view is showing.
// So 00:00 viewed in UTC is the instant 00:00Z, but the SAME 00:00 viewed in
// UTC−4 (device, EDT) is 04:00Z. Flip the zone and the typed numbers stay put
// while the selected instant-set shifts by the offset — which is exactly what
// "the filter should not shift with the timezone" means to the user. These two
// helpers are the single conversion both directions go through; the offset is
// resolved per-instant so DST (EDT=UTC−4 in summer, EST=UTC−5 in winter) is
// handled automatically.

/** Parse "YYYY-MM-DDTHH:MM[:SS]" → numeric parts, or null. */
function _parseWall(wallStr) {
  if (!wallStr || typeof wallStr !== 'string') return null;
  const m = wallStr.match(
    /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?/,
  );
  if (!m) return null;
  return { y: +m[1], mo: +m[2], d: +m[3], h: +m[4], mi: +m[5], s: +(m[6] || 0) };
}

/**
 * A wall-clock string read IN `tzId` → the absolute instant (ms epoch), or
 * null. "2025-04-12T00:00" in `utc` → 2025-04-12T00:00:00Z; the same string in
 * `device` (EDT) → 2025-04-12T04:00:00Z.
 */
export function wallClockToInstant(wallStr, tzId) {
  const w = _parseWall(wallStr);
  if (!w) return null;
  const iana = _ianaFor(tzId);
  // Treat the wall parts as if they were UTC, then subtract the zone's offset
  // at that instant. Refine once so a value near a DST transition lands on the
  // offset that actually applies to the resolved instant, not the guess.
  const utcGuess = Date.UTC(w.y, w.mo - 1, w.d, w.h, w.mi, w.s);
  let off = _offsetMinutes(new Date(utcGuess).toISOString(), iana);
  let instant = utcGuess - off * 60000;
  off = _offsetMinutes(new Date(instant).toISOString(), iana);
  instant = utcGuess - off * 60000;
  return instant;
}

/** Instant (ms epoch or ISO) → "YYYY-MM-DDTHH:MM" wall-clock in `tzId`, or ''. */
export function instantToWallClock(msOrIso, tzId) {
  const iso = typeof msOrIso === 'number' ? new Date(msOrIso).toISOString() : msOrIso;
  const m = _parts(iso, _ianaFor(tzId));
  return m ? `${m.year}-${m.month}-${m.day}T${m.hour}:${m.minute}` : '';
}

/** Instant (ms epoch or ISO) → "YYYY-MM-DD" calendar day in `tzId`, or ''. */
export function instantToZoneDate(msOrIso, tzId) {
  const iso = typeof msOrIso === 'number' ? new Date(msOrIso).toISOString() : msOrIso;
  return dayKey(iso, tzId);
}

// ---- Module-level "current zone" (kept in sync by the React provider) ----
// Lets the plain formatter functions (eventUtils.formatTs / commsUtils.
// formatShortTime), which can't use hooks, render in the active zone so every
// surface is consistent even before it's converted to the hook.
let _currentTzId = DEFAULT_TZ_ID;
const _subs = new Set();
export function getTzId() { return _currentTzId; }
export function setTzId(id) {
  if (!CB_ZONES[id] || id === _currentTzId) return;
  _currentTzId = id;
  _subs.forEach((cb) => { try { cb(id); } catch { /* noop */ } });
}
export function subscribeTz(cb) {
  _subs.add(cb);
  return () => _subs.delete(cb);
}
