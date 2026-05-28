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
