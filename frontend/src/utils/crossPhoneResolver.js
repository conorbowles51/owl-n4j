/**
 * Cross-phone counterpart resolver.
 *
 * Given a list of PhoneReport records (each carrying the owner's
 * msisdn list under `phone_numbers`) and a stream of Cellebrite event
 * rows, this resolver answers a single question:
 *
 *   "When event X on Phone A names a counterpart, does that counterpart
 *    correspond to the owner of Phone B?"
 *
 * If yes, the calling code can draw a swim-lane link between the two
 * phone columns. If no — either because the counterpart is an external
 * contact not represented by any other phone in the case, or because
 * we couldn't extract a useful identifier — we just skip the link.
 *
 * This file is deliberately a self-contained utility:
 *   - no React, no styles, no DOM
 *   - works synchronously, O(events) after a one-time index build
 *   - matches on normalised E.164-ish digit strings
 *
 * Backend follow-up: the eventual goal is for `/api/cellebrite/events`
 * to expose `counterpart_report_key` directly. Until then, this client
 * resolver fills the gap and powers the swim-lane link arcs.
 */

/**
 * Strip everything except digits, then trim to the last 10 digits.
 * Cellebrite reports inconsistently include country codes / leading
 * pluses / spaces / dashes / parentheses, so a digit-only suffix
 * comparison is the only reliable cross-phone match in practice.
 * Ten digits covers every NANP number and is more than enough to
 * disambiguate inside a single investigation.
 */
export function normaliseMsisdn(raw) {
  if (raw == null) return '';
  const digits = String(raw).replace(/\D+/g, '');
  if (!digits) return '';
  return digits.slice(-10);
}

/**
 * Build a `Map<normalised-msisdn, report_key>` from the case's phone
 * reports. Each report contributes every owner phone number it
 * declares, so multi-SIM devices light up multiple keys.
 *
 * Collisions (same number declared by two phones) keep the first
 * occurrence; this is rare in practice and harmless — both phones
 * point at the same physical line so either match draws the same
 * arc.
 */
export function buildPhoneOwnerIndex(reports) {
  const idx = new Map();
  if (!Array.isArray(reports)) return idx;
  for (const r of reports) {
    if (!r?.report_key) continue;
    const nums = Array.isArray(r.phone_numbers) ? r.phone_numbers : [];
    for (const raw of nums) {
      const k = normaliseMsisdn(raw);
      if (k && !idx.has(k)) idx.set(k, r.report_key);
    }
  }
  return idx;
}

/**
 * Pull every candidate identifier off an event row that could match
 * a phone-owner number. We look at:
 *   - counterpart.identifier (callee / SMS recipient phone)
 *   - counterpart.phones array (Person.phone_numbers projection)
 *   - recipients[*].identifier / recipients[*].phones
 *   - sender.identifier / sender.phones (for inbound comms where the
 *     direction is reversed)
 *   - direction string fallback (sometimes the only place the raw
 *     identifier survives)
 *
 * Each is normalised and de-duplicated.
 */
export function extractEventIdentifiers(event) {
  if (!event) return [];
  const out = new Set();
  const push = (v) => {
    const n = normaliseMsisdn(v);
    if (n) out.add(n);
  };

  const cp = event.counterpart || null;
  if (cp) {
    push(cp.identifier);
    push(cp.phone);
    push(cp.phone_number);
    if (Array.isArray(cp.phones)) cp.phones.forEach(push);
    if (Array.isArray(cp.phone_numbers)) cp.phone_numbers.forEach(push);
  }

  const sender = event.sender || null;
  if (sender) {
    push(sender.identifier);
    push(sender.phone);
    push(sender.phone_number);
    if (Array.isArray(sender.phones)) sender.phones.forEach(push);
    if (Array.isArray(sender.phone_numbers)) sender.phone_numbers.forEach(push);
  }

  if (Array.isArray(event.recipients)) {
    for (const r of event.recipients) {
      if (!r) continue;
      push(r.identifier);
      push(r.phone);
      push(r.phone_number);
      if (Array.isArray(r.phones)) r.phones.forEach(push);
    }
  }

  // Last-ditch: try to fish digits out of `direction` ("From: …, To: …")
  // when the structured fields above were empty. This catches a small
  // tail of legacy events where Cellebrite only populated the human
  // string. We scan for digit runs >=7 long.
  if (out.size === 0 && typeof event.direction === 'string') {
    const matches = event.direction.match(/\d[\d\s.()+-]{6,}\d/g) || [];
    for (const m of matches) push(m);
  }

  return Array.from(out);
}

/**
 * For a single event, return the `report_key` of the OTHER phone in
 * the case that owns the counterpart number — or `null` if the
 * counterpart is external to the case. Self-matches (counterpart =
 * same phone that the event came from) are filtered out so we never
 * draw a lane-to-self arc.
 */
export function resolveCounterpartReportKey(event, ownerIndex) {
  if (!event || !ownerIndex || ownerIndex.size === 0) return null;
  const selfKey = event.device_report_key || null;
  const ids = extractEventIdentifiers(event);
  for (const id of ids) {
    const k = ownerIndex.get(id);
    if (k && k !== selfKey) return k;
  }
  return null;
}

/**
 * Bulk pass — resolves a counterpart for every event in `events` in
 * a single O(n) walk. Returns an array of "link" descriptors that the
 * swim-lane component renders as arcs between phone columns.
 *
 * Each link carries enough info to draw a tooltip and re-open the
 * source event later (id, both report_keys, timestamp, summary).
 */
export function resolveCrossPhoneLinks(events, reports) {
  const ownerIndex = buildPhoneOwnerIndex(reports);
  if (ownerIndex.size === 0 || !Array.isArray(events)) return [];
  const links = [];
  for (const ev of events) {
    if (!ev) continue;
    // Only comms can be cross-phone interactions. Locations / WiFi /
    // power events have no counterpart concept so skip the work.
    const t = ev.event_type || '';
    if (t !== 'call' && t !== 'message' && t !== 'email') continue;
    const fromKey = ev.device_report_key;
    if (!fromKey) continue;
    const toKey = resolveCounterpartReportKey(ev, ownerIndex);
    if (!toKey) continue;
    links.push({
      id: ev.id || ev.node_key,
      from_report_key: fromKey,
      to_report_key: toKey,
      timestamp: ev.timestamp,
      event_type: t,
      source_app: ev.source_app || null,
      summary: ev.summary || ev.label || '',
    });
  }
  return links;
}
