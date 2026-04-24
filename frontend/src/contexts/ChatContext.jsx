import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';

/**
 * ChatContext — centralises the "what view is the user looking at, with what
 * filters and selections applied?" state so the AI assistant can receive rich
 * view-aware context with every question.
 *
 * Views call publish({...partial}) when their filter / selection state changes.
 * Publications are debounced (300ms, latest-wins) to avoid thrashing when the
 * user rapidly adjusts filters.
 *
 * The ChatPanel consumes `ctx` plus `includeInChat` to decide whether to attach
 * a `view_context` to its /api/chat request. The ChatContextRing component
 * reads `anchorRef` to paint a subtle outline around the referenced panel.
 */

export const MAX_RESULT_IDS = 5000;
export const MAX_RESULT_PREVIEW = 200;

const defaultCtx = {
  viewType: null,        // "financial" | "graph_table" | "comms" | "events" | "files" | "workspace_section"
  viewLabel: null,
  anchorRef: null,       // React ref.current — the DOM node to outline
  filters: {},           // compact key→value map (used for chips + prompt)
  filterLabels: {},      // optional human-readable versions per filter key
  selectionIds: [],
  resultIds: [],
  resultPreview: [],
  totalMatching: 0,
  publishedAt: null,
};

const ChatContextCtx = createContext(null);

export function ChatContextProvider({ children }) {
  const [ctx, setCtx] = useState(defaultCtx);
  const [includeInChat, setIncludeInChat] = useState(true);
  // Internal buffer for debouncing — we keep the latest publication here and
  // flush it to state after a quiet period of 300ms.
  const pendingRef = useRef(null);
  const timerRef = useRef(null);

  // Flush the latest pending state into React state. Caps the arrays to
  // avoid runaway token costs server-side.
  const flush = useCallback(() => {
    timerRef.current = null;
    const next = pendingRef.current;
    pendingRef.current = null;
    if (!next) return;
    setCtx((prev) => ({
      ...prev,
      ...next,
      resultIds: Array.isArray(next.resultIds)
        ? next.resultIds.slice(0, MAX_RESULT_IDS)
        : prev.resultIds,
      resultPreview: Array.isArray(next.resultPreview)
        ? next.resultPreview.slice(0, MAX_RESULT_PREVIEW)
        : prev.resultPreview,
      publishedAt: new Date().toISOString(),
    }));
  }, []);

  const publish = useCallback((partial) => {
    if (!partial || typeof partial !== 'object') return;
    // Accumulate the partial update so successive calls within the debounce
    // window merge rather than overwrite each other.
    pendingRef.current = { ...(pendingRef.current || {}), ...partial };
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    timerRef.current = setTimeout(flush, 300);
  }, [flush]);

  // Immediate version — bypasses debounce. Useful for critical transitions
  // like clearing on unmount or when the active tab changes.
  const publishNow = useCallback((partial) => {
    if (!partial || typeof partial !== 'object') return;
    pendingRef.current = { ...(pendingRef.current || {}), ...partial };
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    flush();
  }, [flush]);

  const clear = useCallback(() => {
    pendingRef.current = null;
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    setCtx({ ...defaultCtx });
  }, []);

  // Remove a single filter key (used by chip × buttons).
  const removeFilter = useCallback((key) => {
    setCtx((prev) => {
      if (!prev.filters || !(key in prev.filters)) return prev;
      const nextFilters = { ...prev.filters };
      const nextLabels = { ...(prev.filterLabels || {}) };
      delete nextFilters[key];
      delete nextLabels[key];
      return {
        ...prev,
        filters: nextFilters,
        filterLabels: nextLabels,
        publishedAt: new Date().toISOString(),
      };
    });
  }, []);

  // Flush on unmount so dangling timers don't fire.
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const value = useMemo(
    () => ({ ctx, publish, publishNow, clear, removeFilter, includeInChat, setIncludeInChat }),
    [ctx, publish, publishNow, clear, removeFilter, includeInChat]
  );

  return <ChatContextCtx.Provider value={value}>{children}</ChatContextCtx.Provider>;
}

export function useChatContext() {
  const ctx = useContext(ChatContextCtx);
  if (!ctx) {
    // If the provider isn't mounted (tests / storybook), degrade gracefully
    // so view components can still call the hook without crashing.
    return {
      ctx: defaultCtx,
      publish: () => {},
      publishNow: () => {},
      clear: () => {},
      removeFilter: () => {},
      includeInChat: false,
      setIncludeInChat: () => {},
    };
  }
  return ctx;
}

/**
 * useViewContextAnchor — binds a DOM ref as the current view's anchor so
 * ChatContextRing knows what to outline. Call in a view that publishes context.
 *
 * Usage:
 *   const panelRef = useRef(null);
 *   useViewContextAnchor(panelRef);
 *   return <div ref={panelRef}>...</div>
 */
export function useViewContextAnchor(ref, enabled = true) {
  const { publish, clear } = useChatContext();
  useEffect(() => {
    if (!enabled) return;
    publish({ anchorRef: ref });
    return () => {
      // Clear only the anchorRef, not the whole ctx (other effects own filters)
      publish({ anchorRef: null });
    };
  }, [ref, enabled, publish]);
}
