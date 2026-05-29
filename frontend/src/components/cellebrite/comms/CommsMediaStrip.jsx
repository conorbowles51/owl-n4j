import React, { useState } from 'react';
import { Mic, Image as ImageIcon, Film, FileText, Paperclip, ChevronUp } from 'lucide-react';
import { attachmentKind, attachmentUrl } from './commsUtils';
import CommsAttachment from './CommsAttachment';

/**
 * Compact media preview for dense list / timeline rows.
 *
 * A timeline can hold thousands of message rows, so we DON'T render the full
 * <img>/<audio>/<video> for every attachment up-front (that would fire
 * thousands of requests and bloat the DOM). Instead each row shows a small
 * summary — up to a few tiny image thumbnails plus per-kind chips
 * (🎙 voicenote, video, file) with counts — and expands to the full
 * `CommsAttachment` (image viewer, audio player, video poster, AI
 * transcribe/recognition panel) inline when clicked.
 *
 * Clicks are stopped from propagating so expanding media inside a clickable
 * row doesn't also trigger the row's onClick (e.g. opening the detail flyout).
 *
 * Props:
 *   attachments: Array<{ evidence_id, category, original_filename, missing }>
 *   className?: string
 *   expandable?: boolean (default true) — when false the strip renders the
 *     compact preview only and lets clicks bubble to an enclosing row handler
 *     (e.g. a windowed timeline row whose fixed height + overflow-hidden can't
 *     grow to fit inline-expanded media; the row's click opens the detail
 *     flyout, which already renders full media).
 */
const KIND_META = {
  image: { Icon: ImageIcon, label: 'photo' },
  audio: { Icon: Mic, label: 'voicenote' },
  video: { Icon: Film, label: 'video' },
  doc: { Icon: FileText, label: 'file' },
  other: { Icon: Paperclip, label: 'attachment' },
};

const MAX_THUMBS = 3;

export default function CommsMediaStrip({ attachments, className = '', expandable = true }) {
  const [expanded, setExpanded] = useState(false);
  const atts = Array.isArray(attachments) ? attachments.filter(Boolean) : [];
  if (atts.length === 0) return null;

  // Expanded: the full attachment renderers, stopping clicks from bubbling to
  // an enclosing clickable row.
  if (expandable && expanded) {
    return (
      <div
        className={`mt-1 ${className}`}
        onClick={(e) => e.stopPropagation()}
        role="presentation"
      >
        <div className="flex flex-wrap gap-2">
          {atts.map((a, i) => (
            <CommsAttachment key={a.file_id || a.evidence_id || i} attachment={a} />
          ))}
        </div>
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); setExpanded(false); }}
          className="mt-1 inline-flex items-center gap-1 text-[10px] text-light-500 hover:text-light-700 hover:underline"
        >
          <ChevronUp className="w-3 h-3" /> Hide media
        </button>
      </div>
    );
  }

  // Compact: per-kind counts + a few tiny image thumbnails.
  const counts = {};
  for (const a of atts) {
    const k = a.missing ? 'other' : attachmentKind(a);
    counts[k] = (counts[k] || 0) + 1;
  }
  const imageThumbs = atts
    .filter((a) => !a.missing && attachmentKind(a) === 'image' && attachmentUrl(a))
    .slice(0, MAX_THUMBS);
  const shownImageCount = imageThumbs.length;

  const compactInner = (
    <>
      {imageThumbs.map((a, i) => (
        <img
          key={a.file_id || a.evidence_id || i}
          src={attachmentUrl(a)}
          alt=""
          loading="lazy"
          className="w-7 h-7 rounded object-cover border border-light-200"
        />
      ))}
      {Object.entries(counts).map(([k, n]) => {
        // The image chip is redundant when every image is already shown as a
        // thumbnail; only render it for the overflow.
        if (k === 'image') {
          const extra = n - shownImageCount;
          if (extra <= 0) return null;
          const { Icon, label } = KIND_META.image;
          return (
            <span key={k} className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-light-100 text-[10px] text-light-600">
              <Icon className="w-3 h-3" /> +{extra} {label}{extra > 1 ? 's' : ''}
            </span>
          );
        }
        const { Icon, label } = KIND_META[k] || KIND_META.other;
        return (
          <span key={k} className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-light-100 text-[10px] text-light-600">
            <Icon className="w-3 h-3" /> {n} {label}{n > 1 ? 's' : ''}
          </span>
        );
      })}
    </>
  );

  // Non-expandable (e.g. windowed timeline row): render a plain span and let
  // clicks bubble up so the row's own handler opens the detail flyout.
  if (!expandable) {
    return (
      <span className={`mt-1 inline-flex items-center gap-1.5 flex-wrap align-middle ${className}`}>
        {compactInner}
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); setExpanded(true); }}
      className={`mt-1 inline-flex items-center gap-1.5 flex-wrap align-middle ${className}`}
      title="Show media"
    >
      {compactInner}
    </button>
  );
}
