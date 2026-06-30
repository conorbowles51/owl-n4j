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
 *     (the row's click opens the detail flyout, which already renders full
 *     media).
 *   inline?: boolean (default false) — inline mode for the measured (dynamic-
 *     height) timeline scroller. Renders image thumbnails (click = lightbox via
 *     the full CommsAttachment renderer) AND an always-visible <audio> player
 *     for voice notes, so the investigator can see thumbnails and play voice
 *     notes with ZERO clicks while scrolling. The audio uses preload="none" so
 *     bytes aren't fetched until play; only on-screen rows are mounted (the
 *     virtualizer handles that), so no extra lazy logic is needed. All media
 *     clicks stop propagation so they don't trigger the enclosing row's onClick.
 */
const KIND_META = {
  image: { Icon: ImageIcon, label: 'photo' },
  audio: { Icon: Mic, label: 'voicenote' },
  video: { Icon: Film, label: 'video' },
  doc: { Icon: FileText, label: 'file' },
  other: { Icon: Paperclip, label: 'attachment' },
};

const MAX_THUMBS = 3;

export default function CommsMediaStrip({ attachments, className = '', expandable = true, inline = false }) {
  const [expanded, setExpanded] = useState(false);
  const atts = Array.isArray(attachments) ? attachments.filter(Boolean) : [];
  if (atts.length === 0) return null;

  // Inline mode (measured timeline scroller): render media directly in the row.
  // Voice notes get an ALWAYS-VISIBLE <audio> player (no click to listen);
  // images render via the full CommsAttachment renderer so the thumbnail is
  // visible inline and clicking it opens the lightbox. Other kinds (video/doc)
  // also use CommsAttachment. Clicks are stopped from bubbling so they don't
  // fire the enclosing row's onClick (which opens the detail flyout).
  if (inline) {
    // Split audio out so we can render a lean <audio preload="none"> directly
    // (CommsAttachment's audio uses preload="metadata", which would fetch
    // header bytes per row — we explicitly avoid that here).
    const audioAtts = atts.filter((a) => !a.missing && attachmentKind(a) === 'audio' && attachmentUrl(a));
    const otherAtts = atts.filter((a) => !(audioAtts.includes(a)));
    return (
      <div
        className={`mt-1 ${className}`}
        onClick={(e) => e.stopPropagation()}
        role="presentation"
      >
        {audioAtts.length > 0 && (
          <div className="flex flex-col gap-1">
            {audioAtts.map((a, i) => (
              <audio
                key={a.file_id || a.evidence_id || `audio-${i}`}
                controls
                preload="none"
                src={attachmentUrl(a)}
                className="max-w-[300px] h-9"
              />
            ))}
          </div>
        )}
        {otherAtts.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-1">
            {otherAtts.map((a, i) => (
              <CommsAttachment key={a.file_id || a.evidence_id || `att-${i}`} attachment={a} />
            ))}
          </div>
        )}
      </div>
    );
  }

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
          className="w-7 h-7 rounded object-contain bg-light-100 border border-light-200"
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
