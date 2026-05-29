import React, { useEffect, useRef, useState } from 'react';
import { Paperclip, X } from 'lucide-react';
import { createPortal } from 'react-dom';
import CommsAttachment from './CommsAttachment';

/**
 * Compact media indicator for dense spreadsheet-style table cells, where
 * inline thumbnails/players would blow up row heights and break the grid.
 *
 * Renders a small "📎 N" chip; clicking it opens a popover (portalled to
 * <body> so it isn't clipped by table overflow) containing the full
 * `CommsAttachment` renderers — image viewer, audio/voicenote player, video
 * poster, AI transcribe/recognition. Clicks are stopped from bubbling so the
 * row's own click handler (open-in-rail) isn't triggered.
 *
 * Props:
 *   attachments: Array<{ evidence_id, category, original_filename, missing }>
 *   className?: string
 */
export default function CommsMediaBadge({ attachments, className = '' }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState(null); // {top, left} viewport coords
  const btnRef = useRef(null);
  const popRef = useRef(null);

  const atts = Array.isArray(attachments) ? attachments.filter(Boolean) : [];

  useEffect(() => {
    if (!open) return undefined;
    const place = () => {
      const r = btnRef.current?.getBoundingClientRect();
      if (r) setPos({ top: r.bottom + 4, left: Math.max(8, r.left) });
    };
    place();
    const onDocClick = (e) => {
      if (
        popRef.current && !popRef.current.contains(e.target) &&
        btnRef.current && !btnRef.current.contains(e.target)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    window.addEventListener('scroll', place, true);
    window.addEventListener('resize', place);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      window.removeEventListener('scroll', place, true);
      window.removeEventListener('resize', place);
    };
  }, [open]);

  if (atts.length === 0) return null;

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}
        className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded border border-light-200 bg-light-50 hover:bg-light-100 text-[10px] text-light-600 ${className}`}
        title={`${atts.length} attachment${atts.length > 1 ? 's' : ''}`}
      >
        <Paperclip className="w-3 h-3" /> {atts.length}
      </button>
      {open && pos && createPortal(
        <div
          ref={popRef}
          onClick={(e) => e.stopPropagation()}
          role="presentation"
          style={{ position: 'fixed', top: pos.top, left: pos.left, zIndex: 60 }}
          className="w-72 max-h-[60vh] overflow-auto p-3 bg-white border border-light-300 rounded-lg shadow-lg"
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-medium text-light-600">
              {atts.length} attachment{atts.length > 1 ? 's' : ''}
            </span>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setOpen(false); }}
              className="text-light-400 hover:text-light-700"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {atts.map((a, i) => (
              <CommsAttachment key={a.file_id || a.evidence_id || i} attachment={a} />
            ))}
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
