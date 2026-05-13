import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';

/**
 * Cellebrite-wide selection state.
 *
 * Replaces the per-tab "open a slide-over drawer" pattern with a single
 * persistent right-rail (see CellebriteSelectionRail). One piece of
 * state per Cellebrite tab tree:
 *
 *   selection: {
 *     type: 'message' | 'call' | 'email' | 'location' | 'cell_tower'
 *           | 'contact' | 'app_session' | 'device_event' | 'event'
 *           | 'generic',
 *     id: string,                 // node id (or any stable handle)
 *     caseId: string,             // for fetch-on-demand renderers
 *     reportKey?: string,         // optional — drives phone chip
 *     payload?: object,           // initial fields the caller already has;
 *                                 // renderer can show them immediately and
 *                                 // hydrate fuller details async if needed
 *     source?: string,            // origin tab — for back-nav / breadcrumb
 *   }
 *
 * Tabs publish via selectEntity({...}). Passing null clears it. The rail
 * resolves the renderer from `type` and renders its accordions.
 *
 * Selection is intentionally NOT persisted to localStorage — refreshing
 * with a stale id would land on a broken "loading… not found" rail. The
 * rail's collapsed/expanded state IS persisted (see CellebriteSelectionRail).
 */

const CellebriteSelectionContext = createContext({
  selection: null,
  selectEntity: () => {},
  clearSelection: () => {},
});

export function CellebriteSelectionProvider({ children }) {
  const [selection, setSelection] = useState(null);

  const selectEntity = useCallback((next) => {
    if (!next || !next.type || !next.id) {
      setSelection(null);
      return;
    }
    setSelection(next);
  }, []);

  const clearSelection = useCallback(() => setSelection(null), []);

  const value = useMemo(
    () => ({ selection, selectEntity, clearSelection }),
    [selection, selectEntity, clearSelection],
  );
  return (
    <CellebriteSelectionContext.Provider value={value}>
      {children}
    </CellebriteSelectionContext.Provider>
  );
}

/**
 * Tabs call this with the entity they want highlighted in the rail.
 * Pass null to clear.
 *
 *   const { selectEntity } = useCellebriteSelection();
 *   onRowClick = (row) =>
 *     selectEntity({ type: 'message', id: row.id, payload: row, ... });
 */
export function useCellebriteSelection() {
  return useContext(CellebriteSelectionContext);
}
