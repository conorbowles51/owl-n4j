/**
 * Shared row-windowing helpers for the Overview drill-down detail views.
 *
 * The pattern: an outer scrollable div, an inner sized-to-total-height div,
 * and absolutely-positioned rows. Components use `useWindowedRows` to
 * compute which slice of rows is currently visible (with overscan).
 *
 * No dependency on react-window — keeps the bundle lean.
 */
import { useEffect, useLayoutEffect, useRef, useState } from 'react';

export const ROW_HEIGHT = 40;
export const HEADER_HEIGHT = 32;
export const FOOTER_HEIGHT = 26;
const OVERSCAN = 6;

export function useWindowedRows(totalRows, scrollTop, containerHeight) {
  const totalHeight = totalRows * ROW_HEIGHT;
  const viewportRows = Math.ceil((containerHeight || 400) / ROW_HEIGHT) + OVERSCAN * 2;
  const startIdx = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
  const endIdx = Math.min(totalRows, startIdx + viewportRows);
  return { startIdx, endIdx, totalHeight };
}

/**
 * Hook combining: scroll observer, ResizeObserver, and the slice indices.
 * Returns:
 *   - bodyRef       — attach to the scrollable container
 *   - startIdx,endIdx — slice your sorted rows by these
 *   - totalHeight   — for the inner sizing div
 *   - onScroll      — bind to the scroll handler
 */
export function useTableWindow(totalRows) {
  const bodyRef = useRef(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [containerHeight, setContainerHeight] = useState(400);

  useLayoutEffect(() => {
    const el = bodyRef.current;
    if (!el) return;
    const resize = () => setContainerHeight(el.clientHeight || 400);
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const onScroll = (e) => setScrollTop(e.currentTarget.scrollTop);

  const { startIdx, endIdx, totalHeight } = useWindowedRows(totalRows, scrollTop, containerHeight);

  return { bodyRef, startIdx, endIdx, totalHeight, onScroll };
}

/**
 * Generic sort comparator. Handles null/undefined and basic string vs numeric.
 */
export function sortRows(rows, key, dir = 'desc') {
  const factor = dir === 'asc' ? 1 : -1;
  const arr = [...rows];
  arr.sort((a, b) => {
    const av = a?.[key];
    const bv = b?.[key];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === 'number' && typeof bv === 'number') {
      return (av - bv) * factor;
    }
    if (av < bv) return -1 * factor;
    if (av > bv) return 1 * factor;
    return 0;
  });
  return arr;
}
