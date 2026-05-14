import React, { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Two-pane split with a draggable divider between them. Used to give
 * Cellebrite tab panes (Comms Center filter/feed, Locations map/table,
 * etc.) user-controllable height so the section that matters most for
 * the current investigation gets the room it needs.
 *
 * The "first" pane has a controlled size (height for vertical splits,
 * width for horizontal); the "second" pane flexes to fill what's left.
 *
 * Persists size to localStorage when `storageKey` is provided. Per-
 * case keys (e.g. "cb.comms.filter.{caseId}") are recommended so a
 * comms-heavy case's layout doesn't bleed into a location-heavy one.
 *
 * Props:
 *   storageKey   string  — localStorage key. Omit for per-mount only.
 *   direction    'vertical' | 'horizontal'  — defaults to 'vertical'
 *   defaultSize  number  — px size of the "first" pane on first mount
 *   minSize      number  — px minimum size of the "first" pane
 *   maxSize      number  — px maximum size of the "first" pane
 *   first        ReactNode — the controlled pane
 *   second       ReactNode — the flexing pane
 *   className    string  — extra classes on the outer wrapper
 *
 * The divider is 6px thick with a hover affordance + grab cursor.
 * pointermove + pointerup live on `document` while dragging so the
 * drag tracks even when the cursor leaves the divider.
 */
export default function ResizableSplit({
  storageKey = null,
  direction = 'vertical',
  defaultSize = 200,
  minSize = 80,
  maxSize = 800,
  first,
  second,
  className = '',
}) {
  const isVertical = direction === 'vertical';
  // Hydrate from localStorage on first render (synchronous so the
  // first paint already has the persisted size — no flicker).
  const [size, setSize] = useState(() => {
    if (storageKey && typeof window !== 'undefined') {
      try {
        const raw = window.localStorage.getItem(storageKey);
        if (raw) {
          const n = Number(raw);
          if (Number.isFinite(n) && n >= minSize && n <= maxSize) return n;
        }
      } catch { /* ignore */ }
    }
    return defaultSize;
  });

  // Persist on commit. Throttling isn't worth it — we only commit on
  // pointer-up (see handlePointerUp) and on the rare React re-render.
  useEffect(() => {
    if (!storageKey || typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(storageKey, String(Math.round(size)));
    } catch { /* ignore */ }
  }, [storageKey, size]);

  // Drag state lives in refs so the document-level pointermove handler
  // doesn't trigger React re-renders for every pixel — it just updates
  // the size state which IS reactive.
  const containerRef = useRef(null);
  const dragRef = useRef({ active: false, startCoord: 0, startSize: 0 });

  const onPointerMove = useCallback((ev) => {
    if (!dragRef.current.active) return;
    const delta = (isVertical ? ev.clientY : ev.clientX) - dragRef.current.startCoord;
    const next = Math.max(minSize, Math.min(maxSize, dragRef.current.startSize + delta));
    setSize(next);
  }, [isVertical, minSize, maxSize]);

  const onPointerUp = useCallback(() => {
    if (!dragRef.current.active) return;
    dragRef.current.active = false;
    document.removeEventListener('pointermove', onPointerMove);
    document.removeEventListener('pointerup', onPointerUp);
    // Restore the user's normal cursor + selection behaviour.
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }, [onPointerMove]);

  const onPointerDown = useCallback((ev) => {
    ev.preventDefault();
    dragRef.current = {
      active: true,
      startCoord: isVertical ? ev.clientY : ev.clientX,
      startSize: size,
    };
    // Lock the cursor + suppress text selection while dragging so the
    // user gets unambiguous feedback they're resizing, not selecting.
    document.body.style.cursor = isVertical ? 'row-resize' : 'col-resize';
    document.body.style.userSelect = 'none';
    document.addEventListener('pointermove', onPointerMove);
    document.addEventListener('pointerup', onPointerUp);
  }, [isVertical, size, onPointerMove, onPointerUp]);

  // Cleanup on unmount in case a drag is somehow still in flight (e.g.
  // tab unmounted mid-drag).
  useEffect(() => () => {
    document.removeEventListener('pointermove', onPointerMove);
    document.removeEventListener('pointerup', onPointerUp);
  }, [onPointerMove, onPointerUp]);

  const containerClass = isVertical
    ? 'flex flex-col min-h-0'
    : 'flex flex-row min-w-0';
  const firstStyle = isVertical
    ? { height: `${size}px`, flexShrink: 0 }
    : { width: `${size}px`, flexShrink: 0 };
  const dividerClass = isVertical
    ? 'h-1.5 cursor-row-resize bg-light-100 hover:bg-emerald-300 active:bg-emerald-400 transition-colors flex-shrink-0'
    : 'w-1.5 cursor-col-resize bg-light-100 hover:bg-emerald-300 active:bg-emerald-400 transition-colors flex-shrink-0';

  return (
    <div ref={containerRef} className={`${containerClass} ${className}`}>
      <div style={firstStyle} className={isVertical ? 'overflow-hidden' : 'overflow-hidden h-full'}>
        {first}
      </div>
      <div
        className={dividerClass}
        onPointerDown={onPointerDown}
        title={isVertical ? 'Drag to resize vertically' : 'Drag to resize horizontally'}
        role="separator"
        aria-orientation={isVertical ? 'horizontal' : 'vertical'}
      />
      <div className="flex-1 min-h-0 min-w-0 overflow-hidden">
        {second}
      </div>
    </div>
  );
}
