import React, { useEffect, useLayoutEffect, useState } from 'react';
import ReactDOM from 'react-dom';

/**
 * Paints a subtle outline around the DOM element referenced by `ctx.anchorRef`
 * while the chat panel is open. Used to visually confirm which panel the AI
 * assistant is currently "seeing".
 *
 * Positioned via a fixed-position portal overlay that tracks the anchor via
 * getBoundingClientRect + ResizeObserver + scroll/resize listeners.
 *
 * Props:
 *   anchorRef  — a React ref whose .current points to the panel to outline
 *   visible    — whether the ring should be shown
 */
export default function ChatContextRing({ anchorRef, visible }) {
  const [rect, setRect] = useState(null);

  useLayoutEffect(() => {
    if (!visible) {
      setRect(null);
      return;
    }
    const el = anchorRef?.current;
    if (!el) {
      setRect(null);
      return;
    }

    let rafId = 0;
    const update = () => {
      if (rafId) cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        const r = el.getBoundingClientRect();
        // Only update when the rect actually changes to avoid re-renders on scroll
        setRect((prev) => {
          if (
            prev &&
            prev.top === r.top &&
            prev.left === r.left &&
            prev.width === r.width &&
            prev.height === r.height
          ) {
            return prev;
          }
          return { top: r.top, left: r.left, width: r.width, height: r.height };
        });
      });
    };

    update();

    const ro = new ResizeObserver(update);
    ro.observe(el);
    window.addEventListener('scroll', update, true);
    window.addEventListener('resize', update);

    return () => {
      if (rafId) cancelAnimationFrame(rafId);
      ro.disconnect();
      window.removeEventListener('scroll', update, true);
      window.removeEventListener('resize', update);
    };
  }, [anchorRef, visible]);

  if (!visible || !rect) return null;

  const style = {
    position: 'fixed',
    top: rect.top - 3,
    left: rect.left - 3,
    width: rect.width + 6,
    height: rect.height + 6,
    border: '2px solid rgba(37, 99, 235, 0.55)', // owl-blue-600 @ 55%
    borderRadius: 8,
    pointerEvents: 'none',
    zIndex: 9997,
    boxShadow: '0 0 0 3px rgba(59, 130, 246, 0.12)',
    transition: 'top 120ms ease, left 120ms ease, width 120ms ease, height 120ms ease',
  };

  return ReactDOM.createPortal(<div style={style} aria-hidden="true" />, document.body);
}
