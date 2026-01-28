import React from 'react';
import { getHighlightRanges } from './searchParser';

/**
 * Render text with match highlights. Used for filter/search result highlighting in tables and panels.
 * @param {string|null|undefined} text - Text to render
 * @param {string[]} terms - Normalized terms to highlight (e.g. from getHighlightTerms(parseSearchQuery(query)))
 * @param {string} emptyPlaceholder - String to show when text is empty (default '—')
 * @returns {React.ReactNode} - Plain string or array of spans/fragments with <mark> around matches
 */
export function highlightMatchedText(text, terms, emptyPlaceholder = '—') {
  if (text == null || text === '') return emptyPlaceholder;
  if (text === '—' || !terms || terms.length === 0) return String(text);
  const str = String(text);
  const ranges = getHighlightRanges(str, terms);
  if (ranges.length === 0) return str;
  const segs = [];
  let i = 0;
  for (const [s, e] of ranges) {
    if (s > i) segs.push({ type: 'text', value: str.slice(i, s) });
    segs.push({ type: 'mark', value: str.slice(s, e) });
    i = e;
  }
  if (i < str.length) segs.push({ type: 'text', value: str.slice(i) });
  return segs.map((seg, idx) =>
    seg.type === 'mark' ? (
      <mark key={idx} className="bg-amber-200/80 dark:bg-amber-500/40 rounded px-0.5 font-medium">{seg.value}</mark>
    ) : (
      <React.Fragment key={idx}>{seg.value}</React.Fragment>
    )
  );
}
