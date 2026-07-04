/**
 * Shared client-side search engine for Cellebrite surfaces.
 *
 * Used by:
 *   - Timeline (events)
 *   - Comms Center (threads + messages within a thread)
 *   - Events Center (events + map markers)
 *
 * Why client-side:
 *   The backend already returns the full per-case dataset (≤500K cap;
 *   in practice ≤30K rows). Re-querying on every keystroke is wasteful.
 *   This module gives instant per-keystroke filtering with operators,
 *   highlights, and a uniform feature set across every Cellebrite tab.
 *
 * Operators (case-insensitive prefix; combine freely):
 *   type:call               — event_type / thread_type / human label
 *   from:John               — sender / first-non-owner participant name+identifier
 *   to:+123                 — counterpart / recipient
 *   app:WhatsApp            — source_app
 *   phone:P1                — phone short label or device_model substring
 *   before:2023-01-15       — ISO date upper bound on item.timestamp / last_activity
 *   after:2022-12-01        — ISO date lower bound
 *   place:london            — substring match on reverse-geocoded fields
 *                             (address / place_name / country / admin levels)
 *                             Items without geocode info fail closed — the
 *                             user asked a place question, get place answers.
 *   near:51.5,-0.1,5km      — within radius of lat,lng. Unit km|m, default km.
 *   "exact text"            — quoted exact-substring match
 *   -word  /  not:word      — exclude matches containing this term
 *   anything else           — free-text substring match across the haystack
 *
 * The matcher is purely synchronous and deterministic. It returns
 * `{ matches, highlights }` so a row renderer can wrap matched
 * substrings in <mark>.
 */

// ---------------------------------------------------------------------------
// Query parsing
// ---------------------------------------------------------------------------

const KNOWN_OPERATORS = new Set([
  'type', 'from', 'to', 'app', 'phone', 'before', 'after',
  // Geo operators (G5). `place:` does substring matching across the
  // reverse-geocoded fields (address / place_name / country / admin
  // levels) added by G4. `near:` takes "lat,lng,radius" with optional
  // unit suffix (km|m, default km) and filters items by haversine
  // distance from the supplied centre.
  'place', 'near',
  // `has:attachment` (aliases: attachments / media / file) — keep only
  // items that carry at least one attachment. Drives the shared
  // "Has attachment" toggle across the messaging views.
  'has',
]);

/**
 * Tokenise a query string into:
 *   - terms      : free-text substrings to match anywhere
 *   - excludes   : substrings whose presence should disqualify a row
 *   - operators  : { type, from, to, app, phone, before, after } (string|null)
 *
 * Tokens are split on whitespace, except inside double quotes.
 */
export function parseQuery(query) {
  const result = {
    raw: query || '',
    terms: [],
    excludes: [],
    operators: {
      type: null,
      from: null,
      to: null,
      app: null,
      phone: null,
      before: null,   // Date.getTime() once parsed
      after: null,    // Date.getTime() once parsed
      place: null,    // string; substring match on geocoded fields
      near: null,     // { lat, lng, radiusMeters } once parsed
      has: null,      // 'attachment' | 'media' | … — structural presence gate
    },
  };
  if (!query || typeof query !== 'string') return result;

  const tokens = tokenise(query);
  for (const tok of tokens) {
    let t = tok;
    let exclude = false;
    if (t.startsWith('-') && t.length > 1) {
      exclude = true;
      t = t.slice(1);
    }
    // Operator detection is restricted to KNOWN_OPERATORS (+ "not") so
    // that random colon-bearing input — pasted URLs ("http://..."),
    // file paths ("C:\\Users\\..."), MAC addresses, IP:port pairs — is
    // treated as plain free-text instead of being mis-parsed into a
    // bogus operator. This was the user-reported "avoid symbols like
    // slashes" issue: a paste containing "://" was silently swallowed
    // as the unknown operator "http" and produced no matches.
    const opMatch = t.match(/^([a-zA-Z]+):(.*)$/);
    const knownOpHere = opMatch && (
      opMatch[1].toLowerCase() === 'not'
      || KNOWN_OPERATORS.has(opMatch[1].toLowerCase())
    );
    if (knownOpHere) {
      const op = opMatch[1].toLowerCase();
      const val = stripQuotes(opMatch[2]).toLowerCase();
      if (op === 'not') {
        if (val) result.excludes.push(val);
        continue;
      }
      if (val) {
        if (op === 'before' || op === 'after') {
          const ts = parseDate(val);
          if (ts != null) result.operators[op] = ts;
        } else if (op === 'near') {
          // "lat,lng,radius[unit]" — parse once, store the structured
          // form so the matcher doesn't re-parse on every row. Bad
          // input drops silently (no operator applied) rather than
          // erroring; same posture as the date operators.
          const parsed = parseNearSpec(val);
          if (parsed) result.operators.near = parsed;
        } else {
          // Multiple of the same operator — keep them as an array so
          // the matcher can do (matches A or B). Edge case; rare.
          if (result.operators[op] == null) {
            result.operators[op] = val;
          } else if (Array.isArray(result.operators[op])) {
            result.operators[op].push(val);
          } else {
            result.operators[op] = [result.operators[op], val];
          }
        }
      }
      continue;
    }
    const cleaned = stripQuotes(t).toLowerCase();
    if (!cleaned) continue;
    (exclude ? result.excludes : result.terms).push(cleaned);
  }
  return result;
}

function tokenise(input) {
  const tokens = [];
  let buf = '';
  let inQuotes = false;
  for (let i = 0; i < input.length; i++) {
    const ch = input[i];
    if (ch === '"') {
      inQuotes = !inQuotes;
      buf += ch;
      continue;
    }
    if (!inQuotes && /\s/.test(ch)) {
      if (buf) {
        tokens.push(buf);
        buf = '';
      }
      continue;
    }
    buf += ch;
  }
  if (buf) tokens.push(buf);
  return tokens;
}

function stripQuotes(s) {
  if (!s) return '';
  if (s.length >= 2 && s.startsWith('"') && s.endsWith('"')) {
    return s.slice(1, -1);
  }
  return s;
}

/**
 * Parse a `near:` operator value of the form "lat,lng,radius[unit]".
 *   - Coordinates are decimal degrees (signed).
 *   - Radius is a positive number; unit defaults to km, "m" also accepted.
 *   - Examples: "51.5,-0.1,5km", "40.7128,-74.006,500m", "37.77,-122.42,2"
 *
 * Returns { lat, lng, radiusMeters } or null on any parse failure.
 * Bad input drops silently in parseQuery — same posture as bad dates.
 */
function parseNearSpec(raw) {
  if (!raw) return null;
  const parts = String(raw).split(',').map((s) => s.trim());
  if (parts.length < 3) return null;
  const lat = parseFloat(parts[0]);
  const lng = parseFloat(parts[1]);
  if (!isFinite(lat) || !isFinite(lng)) return null;
  if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;
  // Pull a numeric prefix off the radius token + optional unit suffix.
  // Anything else than km/m falls back to km — catches "5KM" / "5kms".
  const radiusToken = parts[2].toLowerCase();
  const m = radiusToken.match(/^([\d.]+)\s*(km|m|meters|metre|meter)?$/);
  if (!m) return null;
  const value = parseFloat(m[1]);
  if (!isFinite(value) || value <= 0) return null;
  const unit = (m[2] || 'km').toLowerCase();
  const radiusMeters = unit === 'm' || unit.startsWith('met') ? value : value * 1000;
  return { lat, lng, radiusMeters };
}

/**
 * Haversine distance in metres between two lat/lng pairs. Used by
 * the `near:` operator. Self-contained so the search engine doesn't
 * pull a math library for one-off use.
 */
function haversineMeters(lat1, lng1, lat2, lng2) {
  if (!isFinite(lat1) || !isFinite(lng1) || !isFinite(lat2) || !isFinite(lng2)) {
    return Infinity;
  }
  const R = 6371008.8; // mean Earth radius in metres
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
}

function parseDate(s) {
  // Accept YYYY-MM-DD, YYYY/MM/DD, YYYY-MM-DD HH:MM, full ISO.
  const cleaned = s.trim().replace(/\//g, '-');
  const d = new Date(cleaned.length === 10 ? cleaned + 'T00:00:00' : cleaned);
  return isNaN(d.getTime()) ? null : d.getTime();
}

// ---------------------------------------------------------------------------
// Haystack builders — concatenate every plausible search field for one item
// ---------------------------------------------------------------------------

function partyToText(p) {
  if (!p) return '';
  const parts = [];
  if (p.name) parts.push(p.name);
  if (p.identifier && p.identifier !== p.name) parts.push(p.identifier);
  if (p.phone && p.phone !== p.identifier) parts.push(p.phone);
  if (p.key && p.key !== p.identifier) parts.push(p.key);
  return parts.join(' ');
}

/**
 * Build a flat lowercase haystack string for an item plus a per-field
 * map the matcher uses for operator-scoped checks.
 */
export function buildHaystack(item, kind, reports = []) {
  if (!item) {
    return { full: '', fields: { type: '', from: '', to: '', app: '', phone: '', place: '' } };
  }
  const fields = { type: '', from: '', to: '', app: '', phone: '', place: '' };
  const parts = [];

  const phoneIdentity = (() => {
    const key = item.device_report_key || item.report_key;
    if (!key) return null;
    const r = reports.find((x) => x && x.report_key === key);
    if (!r) return null;
    const short = Number.isInteger(r.display_index) ? `p${r.display_index + 1}` : '';
    return {
      short,
      model: (r.device_model || '').toLowerCase(),
      owner: (r.phone_owner_name || '').toLowerCase(),
    };
  })();
  if (phoneIdentity) {
    fields.phone = [phoneIdentity.short, phoneIdentity.model, phoneIdentity.owner]
      .filter(Boolean).join(' ');
    parts.push(fields.phone);
  }

  if (kind === 'thread') {
    fields.type = (item.thread_type || '').toString().toLowerCase();
    fields.app = (item.source_app || '').toString().toLowerCase();
    parts.push(fields.type);
    parts.push(fields.app);
    parts.push((item.name || '').toLowerCase());
    parts.push((item.thread_id || '').toLowerCase());
    const participants = item.participants || [];
    const participantTexts = participants.map(partyToText).join(' ').toLowerCase();
    fields.from = participantTexts;
    fields.to = fields.from; // threads don't distinguish from/to
    // Push the LOWERCASED participant blob into the free-text haystack.
    // Every other field here is lowercased and search terms arrive
    // lowercased (parseQuery), but matching is a case-sensitive
    // substring test — so pushing the raw mixed-case participant text
    // meant a lowercased term ("thomas") never hit a capitalised name
    // ("Thomas Hookah"). A 1:1 chat whose own `name` is a generic label
    // ("Chat (Native Messages)") then had NO searchable "thomas" at all
    // and vanished from a contact-name search — DKT-42: the individual
    // conversation with a contact was missing from the Comms Center while
    // a group chat that carried the name in its title still showed.
    parts.push(participantTexts);
  } else {
    // event / message. `fields.type` is what the `type:` operator
    // matches against. We deliberately concatenate MULTIPLE type-ish
    // fields with spaces so `type:visited` (the human-meaningful
    // subtype on Location nodes) works alongside `type:location`
    // (the top-level event discriminator). Previously fields.type
    // was just the discriminator, so the autocomplete-suggested
    // location_type values silently filtered everything out.
    const eventTypeStr = (item.event_type || item.type || '').toString().toLowerCase();
    const locationTypeStr = (item.location_type || '').toString().toLowerCase();
    fields.type = [eventTypeStr, locationTypeStr].filter(Boolean).join(' ');
    fields.app = (item.source_app || '').toString().toLowerCase();
    fields.from = partyToText(item.sender).toLowerCase();
    const recipients = Array.isArray(item.recipients)
      ? item.recipients : (item.counterpart ? [item.counterpart] : []);
    fields.to = recipients.map(partyToText).join(' ').toLowerCase();
    parts.push(fields.type);
    parts.push(fields.app);
    parts.push(fields.from);
    parts.push(fields.to);
    parts.push((item.label || '').toLowerCase());
    parts.push((item.summary || '').toLowerCase());
    parts.push((item.body || '').toLowerCase());
    parts.push((item.direction || '').toLowerCase());
    parts.push((item.app_name || '').toLowerCase());
    parts.push((item.deleted_state || '').toLowerCase());
    if (item.latitude != null && item.longitude != null) {
      parts.push(`${item.latitude} ${item.longitude}`);
    }
    if (item.location_formatted) parts.push(item.location_formatted.toLowerCase());
  }

  // Geocoded place fields (G4) — populated whichever kind we are.
  // Combined into one searchable blob the `place:` operator scopes
  // against, while also feeding the free-text haystack so an
  // unscoped "london" still hits when the address has it.
  const placeBits = [
    item.address,
    item.place_name,
    item.country,
    item.country_code,
    item.admin1,
    item.admin2,
  ].filter(Boolean).map((v) => String(v).toLowerCase());
  if (placeBits.length) {
    fields.place = placeBits.join(' ');
    parts.push(fields.place);
  }

  return { full: parts.filter(Boolean).join(' '), fields };
}

// ---------------------------------------------------------------------------
// Matching
// ---------------------------------------------------------------------------

function timestampOf(item, kind) {
  if (!item) return null;
  if (kind === 'thread') {
    const v = item.last_activity || item.last_message_at || item.timestamp;
    return v ? new Date(v).getTime() : null;
  }
  return item.timestamp ? new Date(item.timestamp).getTime() : null;
}

function valueMatches(needle, haystack) {
  if (!needle) return true;
  if (Array.isArray(needle)) return needle.some((n) => haystack.includes(n));
  return haystack.includes(needle);
}

/**
 * Does this item carry at least one attachment? Works for both resolved
 * message/event rows (attachments[] / attachment_file_ids[] / attachment_count)
 * and thread-level rows (has_attachments / attachment_count aggregate).
 */
function itemHasAttachment(item) {
  if (!item) return false;
  if (Array.isArray(item.attachments)) {
    if (item.attachments.some((a) => a && !a.missing)) return true;
  }
  if (Array.isArray(item.attachment_file_ids) && item.attachment_file_ids.length > 0) return true;
  if (typeof item.attachment_count === 'number' && item.attachment_count > 0) return true;
  if (item.has_attachments) return true;
  return false;
}

/**
 * Return `{ matches, highlights }` for one item against a parsed query.
 *
 * `matches` is a boolean. `highlights` is the list of literal substrings
 * (lowercase) that contributed positively, suitable for passing to
 * highlightText() to wrap them in <mark>.
 */
export function matchItem(item, parsed, kind, reports = []) {
  if (!parsed) return { matches: true, highlights: [] };
  const { full, fields } = buildHaystack(item, kind, reports);

  // Operator gates
  const ops = parsed.operators;
  if (ops.type && !valueMatches(ops.type, fields.type)) return NO_MATCH;
  if (ops.from && !valueMatches(ops.from, fields.from)) return NO_MATCH;
  if (ops.to && !valueMatches(ops.to, fields.to)) return NO_MATCH;
  if (ops.app && !valueMatches(ops.app, fields.app)) return NO_MATCH;
  if (ops.phone && !valueMatches(ops.phone, fields.phone)) return NO_MATCH;

  // place: scopes free-text matching to the reverse-geocoded fields
  // only. Items that have no geocode info (fields.place is '') fail
  // closed — investigators get exactly what was matched on, no
  // surprise hits from body text that happens to contain the term.
  if (ops.place) {
    if (!fields.place) return NO_MATCH;
    if (!valueMatches(ops.place, fields.place)) return NO_MATCH;
  }

  // near: filters by haversine distance from a centre point. Items
  // without coordinates fail closed — same posture as place:; the
  // user asked a geo question, the rows we keep have geo answers.
  if (ops.near) {
    const lat = item.latitude;
    const lng = item.longitude;
    if (lat == null || lng == null) return NO_MATCH;
    const d = haversineMeters(ops.near.lat, ops.near.lng, lat, lng);
    if (d > ops.near.radiusMeters) return NO_MATCH;
  }

  if (ops.before != null || ops.after != null) {
    const t = timestampOf(item, kind);
    if (t == null) return NO_MATCH;
    if (ops.before != null && t > ops.before) return NO_MATCH;
    if (ops.after != null && t < ops.after) return NO_MATCH;
  }

  // has:attachment — structural gate. Items with no attachment fail closed.
  if (ops.has) {
    const wantAttachment = (Array.isArray(ops.has) ? ops.has : [ops.has]).some(
      (v) => ['attachment', 'attachments', 'media', 'file', 'files'].includes(v),
    );
    if (wantAttachment && !itemHasAttachment(item)) return NO_MATCH;
  }

  // Exclusions short-circuit
  for (const ex of parsed.excludes) {
    if (full.includes(ex)) return NO_MATCH;
  }

  // Free-text terms — every term must match somewhere
  const highlights = [];
  for (const term of parsed.terms) {
    if (!full.includes(term)) return NO_MATCH;
    highlights.push(term);
  }
  // Operator values are also worth highlighting in body text where they
  // happen to appear (e.g. typing `app:WhatsApp` should still highlight
  // "WhatsApp" in the displayed source_app text).
  for (const k of ['type', 'from', 'to', 'app', 'phone', 'place']) {
    const v = ops[k];
    if (!v) continue;
    if (Array.isArray(v)) v.forEach((vi) => vi && highlights.push(vi));
    else highlights.push(v);
  }
  // near: doesn't get highlighted — there's nothing useful to mark
  // in a text body for a coordinate match.
  return { matches: true, highlights: dedupe(highlights) };
}

const NO_MATCH = { matches: false, highlights: [] };

function dedupe(arr) {
  return Array.from(new Set(arr));
}

// ---------------------------------------------------------------------------
// Highlight renderer (returns a string of segments callers can render)
// ---------------------------------------------------------------------------

/**
 * Split `text` into alternating non-match / match segments based on the
 * supplied highlight terms. The result is a plain JS array — callers
 * pass it to <HighlightedText> for React rendering, or to any other
 * renderer if needed.
 *
 * Returns: [{ text, match }, ...]
 */
export function splitForHighlight(text, highlights) {
  if (!text) return [];
  if (!highlights || highlights.length === 0) {
    return [{ text, match: false }];
  }
  // Sort longest-first so "WhatsApp Web" wins over "WhatsApp" when both
  // are present — avoids re-highlighting overlapping ranges.
  const sortedTerms = highlights
    .map((h) => (h || '').toString())
    .filter(Boolean)
    .sort((a, b) => b.length - a.length);

  const lower = text.toLowerCase();
  const ranges = [];
  for (const term of sortedTerms) {
    const t = term.toLowerCase();
    if (!t) continue;
    let from = 0;
    while (from < lower.length) {
      const idx = lower.indexOf(t, from);
      if (idx < 0) break;
      ranges.push([idx, idx + t.length]);
      from = idx + t.length;
    }
  }
  if (ranges.length === 0) return [{ text, match: false }];
  // Merge overlapping ranges
  ranges.sort((a, b) => a[0] - b[0]);
  const merged = [];
  for (const r of ranges) {
    const last = merged[merged.length - 1];
    if (last && r[0] <= last[1]) {
      last[1] = Math.max(last[1], r[1]);
    } else {
      merged.push([...r]);
    }
  }
  // Build segments
  const segments = [];
  let cursor = 0;
  for (const [s, e] of merged) {
    if (s > cursor) segments.push({ text: text.slice(cursor, s), match: false });
    segments.push({ text: text.slice(s, e), match: true });
    cursor = e;
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor), match: false });
  return segments;
}
