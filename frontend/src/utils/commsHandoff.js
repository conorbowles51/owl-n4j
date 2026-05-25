/**
 * Comms Center handoff bridge.
 *
 * The swim-lane Timeline lets the investigator drag a box around a
 * region of interest (time × phones) and click "Open in Comms" to
 * jump into the Comms Center pre-filtered to those exact bounds.
 *
 * Two surfaces need to coordinate without becoming directly coupled:
 *   1. CellebriteTimelineSwimLane writes the handoff payload, then
 *      navigates / requests the parent route Cellebrite tab change.
 *   2. CellebriteCommsCenter reads the payload on mount and applies
 *      the start/end window + phone-key narrowing, then clears it
 *      so subsequent visits to the tab aren't unexpectedly filtered.
 *
 * sessionStorage is used (not a context or URL params) because:
 *   - it survives the Cellebrite-tab swap without lifting state to
 *     a parent we don't otherwise need to involve;
 *   - the payload is small, transient, and per-case-scoped so we
 *     stay well inside browser quotas;
 *   - URL query-string approach was rejected because the Comms
 *     Center already owns thread-id / search params in the URL and
 *     we don't want a 5-key query string.
 */

const STORAGE_KEY = 'owl.cellebrite.commsHandoff';

/**
 * Write a handoff payload that the Comms Center will pick up on its
 * next mount. Pass `null` (or omit fields) to clear.
 *
 * payload shape:
 *   {
 *     caseId,              // case scope so cross-case clicks don't bleed
 *     startTs,             // ISO string, inclusive
 *     endTs,               // ISO string, inclusive
 *     reportKeys,          // array<string> of phone report_keys
 *     source: 'swim-lane', // for telemetry / debugging
 *   }
 */
export function setCommsHandoff(payload) {
  if (typeof window === 'undefined') return;
  try {
    if (!payload) {
      window.sessionStorage.removeItem(STORAGE_KEY);
      return;
    }
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
      ...payload,
      writtenAt: Date.now(),
    }));
  } catch {
    /* sessionStorage disabled — handoff silently no-ops */
  }
}

/**
 * Read the current handoff. Returns null if none is set, or if the
 * stored payload is too old (>5 minutes — anything older is almost
 * certainly stale state from a previous session and would surprise
 * the user).
 */
export function readCommsHandoff() {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return null;
    const writtenAt = Number(parsed.writtenAt) || 0;
    if (writtenAt && Date.now() - writtenAt > 5 * 60_000) return null;
    return parsed;
  } catch {
    return null;
  }
}

/**
 * Read-and-clear (atomic consume). The Comms Center should call this
 * on mount so a single handoff applies exactly once. Subsequent
 * navigations land in the tab fresh.
 */
export function consumeCommsHandoff() {
  const p = readCommsHandoff();
  if (p) setCommsHandoff(null);
  return p;
}

/**
 * Tiny event-bus so a swim-lane sitting inside the Timeline tab can
 * ask the Cellebrite shell to switch to the Comms tab. Decoupled
 * from React context because the parent tab-host (CellebriteView)
 * is several levels above the Timeline and we don't want to pipe a
 * callback through every intermediate component just for one
 * action.
 */
const SWITCH_EVENT = 'owl-cellebrite-switch-tab';

export function requestCellebriteTabSwitch(tabId) {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(
    new CustomEvent(SWITCH_EVENT, { detail: { tabId } }),
  );
}

export function onCellebriteTabSwitch(handler) {
  if (typeof window === 'undefined') return () => {};
  const wrapped = (ev) => handler(ev?.detail?.tabId || null);
  window.addEventListener(SWITCH_EVENT, wrapped);
  return () => window.removeEventListener(SWITCH_EVENT, wrapped);
}
