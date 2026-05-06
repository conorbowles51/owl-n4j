import React from 'react';
import { splitForHighlight } from '../../../utils/cellebriteSearch';

/**
 * Render `text` with any segments matching `highlights` wrapped in <mark>.
 * Pure render component — does no matching itself, defers to the shared
 * splitForHighlight helper so all surfaces stay consistent.
 *
 * Props:
 *   text       — the raw string to render
 *   highlights — array of lowercase substrings to mark
 *   className  — applied to the wrapping <span>
 *   markClassName — applied to each <mark>; defaults to a subtle yellow tint
 */
export default function HighlightedText({
  text,
  highlights,
  className = '',
  markClassName = 'bg-yellow-200 text-light-900 rounded-sm px-0.5',
}) {
  if (text == null || text === '') return null;
  const segments = splitForHighlight(String(text), highlights);
  if (segments.length === 1 && !segments[0].match) {
    return <span className={className}>{segments[0].text}</span>;
  }
  return (
    <span className={className}>
      {segments.map((seg, i) =>
        seg.match
          ? <mark key={i} className={markClassName}>{seg.text}</mark>
          : <React.Fragment key={i}>{seg.text}</React.Fragment>
      )}
    </span>
  );
}
