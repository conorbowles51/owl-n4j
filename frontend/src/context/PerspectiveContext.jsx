/**
 * PerspectiveContext
 *
 * Global "people lens" for the Cellebrite multi-phone view. Every tab
 * (Communications, Comms Center, Cross-Phone Graph, Timeline, Locations,
 * Events) can read this context and narrow its data to the active
 * perspective without needing tab-to-tab plumbing.
 *
 * A perspective is a stack of frames. Each frame holds:
 *   - personKeys: Set<string>  — the people the user is currently
 *                                "looking through"
 *   - label:     short human label  ("Sender Lemus", "Lemus + 2 more")
 *   - source:    string informing telemetry/debugging
 *                ("communications.drill", "rail.name-menu", etc.)
 *
 * The stack supports breadcrumbed drill-down: clicking a name in any
 * tab pushes a frame; clicking a breadcrumb pops back to that frame;
 * clearing pops the whole stack.
 *
 * Persistence:
 *   - frames persist per-case in localStorage so a refresh keeps the
 *     investigator's place. Drill-downs are an exploratory state, not
 *     a navigation event, so URL-level persistence isn't appropriate.
 *
 * Consumers should treat the context as optional (returns null when
 * no provider is mounted) so non-Cellebrite surfaces don't crash.
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

const PerspectiveContext = createContext(null);

const STORAGE_PREFIX = 'owl.cellebrite.perspective.';

function storageKey(caseId) {
  return `${STORAGE_PREFIX}${caseId}`;
}

function loadFrames(caseId) {
  if (!caseId || typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(storageKey(caseId));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // Validate shape — drop frames missing the required fields rather
    // than crashing later when consumers try to read them.
    return parsed
      .map((f) => ({
        personKeys: Array.isArray(f?.personKeys)
          ? f.personKeys.filter((k) => typeof k === 'string' && k.length > 0)
          : [],
        label: typeof f?.label === 'string' ? f.label : '',
        source: typeof f?.source === 'string' ? f.source : 'unknown',
        addedAt: typeof f?.addedAt === 'number' ? f.addedAt : Date.now(),
      }))
      .filter((f) => f.personKeys.length > 0);
  } catch {
    return [];
  }
}

function saveFrames(caseId, frames) {
  if (!caseId || typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(storageKey(caseId), JSON.stringify(frames));
  } catch {
    /* full / disabled — silent */
  }
}

export function PerspectiveProvider({ caseId, children }) {
  // Frames stack. Top of stack = active perspective.
  const [frames, setFrames] = useState(() => loadFrames(caseId));
  const hydratedRef = useRef(false);

  // Reset frames when the case changes — perspectives are case-scoped.
  useEffect(() => {
    setFrames(loadFrames(caseId));
    hydratedRef.current = true;
  }, [caseId]);

  useEffect(() => {
    if (!hydratedRef.current) return;
    saveFrames(caseId, frames);
  }, [caseId, frames]);

  /**
   * Push a new frame onto the perspective stack. Use when the user
   * drills deeper into a contact (e.g. clicks a recipient's name).
   */
  const pushFrame = useCallback((personKeys, label, source = 'unknown') => {
    const keys = (Array.isArray(personKeys) ? personKeys : [personKeys])
      .filter((k) => typeof k === 'string' && k.length > 0);
    if (keys.length === 0) return;
    setFrames((prev) => [
      ...prev,
      { personKeys: keys, label: label || keys[0], source, addedAt: Date.now() },
    ]);
  }, []);

  /**
   * Replace the entire stack with a single frame. Use when the user
   * picks "View Cross-Phone Graph from this perspective" — that's a
   * scope reset, not a drill.
   */
  const setPerspective = useCallback((personKeys, label, source = 'unknown') => {
    const keys = (Array.isArray(personKeys) ? personKeys : [personKeys])
      .filter((k) => typeof k === 'string' && k.length > 0);
    if (keys.length === 0) {
      setFrames([]);
      return;
    }
    setFrames([
      { personKeys: keys, label: label || keys[0], source, addedAt: Date.now() },
    ]);
  }, []);

  /**
   * Pop frames down to (but not past) the given index. -1 clears
   * everything, 0 keeps the root frame, etc. Used by breadcrumb
   * clicks to navigate back through the drill history.
   */
  const popToFrame = useCallback((index) => {
    setFrames((prev) => {
      if (index < 0) return [];
      if (index >= prev.length) return prev;
      return prev.slice(0, index + 1);
    });
  }, []);

  const popFrame = useCallback(() => {
    setFrames((prev) => (prev.length === 0 ? prev : prev.slice(0, -1)));
  }, []);

  const clear = useCallback(() => setFrames([]), []);

  /**
   * Add keys to the active frame (no new frame). Use when the user
   * wants to widen the lens — e.g. "also include this person".
   * No-op when no active frame exists; the caller should setPerspective
   * for the first one.
   */
  const widenActive = useCallback((personKeys) => {
    const keys = (Array.isArray(personKeys) ? personKeys : [personKeys])
      .filter((k) => typeof k === 'string' && k.length > 0);
    if (keys.length === 0) return;
    setFrames((prev) => {
      if (prev.length === 0) return prev;
      const last = prev[prev.length - 1];
      const merged = Array.from(new Set([...last.personKeys, ...keys]));
      if (merged.length === last.personKeys.length) return prev;
      const next = prev.slice();
      next[next.length - 1] = {
        ...last,
        personKeys: merged,
        // Label gets a suffix when widening so the breadcrumb still
        // signals "this is more than the original person".
        label: keys.length === 1 && merged.length === last.personKeys.length + 1
          ? `${last.label} +1`
          : `${merged.length} people`,
      };
      return next;
    });
  }, []);

  // Derived: the active perspective = top of stack, or null.
  const active = frames.length > 0 ? frames[frames.length - 1] : null;
  const activeKeys = useMemo(
    () => (active ? new Set(active.personKeys) : new Set()),
    [active],
  );

  const value = useMemo(
    () => ({
      caseId,
      frames,
      active,
      activeKeys,
      hasPerspective: frames.length > 0,
      pushFrame,
      popFrame,
      popToFrame,
      setPerspective,
      widenActive,
      clear,
    }),
    [
      caseId,
      frames,
      active,
      activeKeys,
      pushFrame,
      popFrame,
      popToFrame,
      setPerspective,
      widenActive,
      clear,
    ],
  );

  return (
    <PerspectiveContext.Provider value={value}>
      {children}
    </PerspectiveContext.Provider>
  );
}

/**
 * Read the perspective context. Returns null when no provider is
 * mounted — non-Cellebrite surfaces (or unit tests) keep working.
 */
export function usePerspective() {
  return useContext(PerspectiveContext);
}
