import React, { useEffect, useRef, useState } from 'react';
import { ChevronDown, BarChart3, Smartphone, X, Calendar } from 'lucide-react';
import CellebriteSearchInput from '../shared/CellebriteSearchInput';
import TimelineScrubber from '../shared/TimelineScrubber';
import CommsTypeFilter from './CommsTypeFilter';
import CommsAppFilter from './CommsAppFilter';
import AttachmentFilterToggle from '../shared/AttachmentFilterToggle';

/**
 * Phase K2 — Compact toolbar for the Comms Center.
 *
 * Replaces the three stacked rows (Source app filter row, Type
 * filter row, Search row) PLUS the always-mounted ~80px
 * TimelineScrubber with one toolbar row + an expand-on-click
 * scrubber handle.
 *
 * Layout (single row):
 *   [Search................] [Apps ▾] [Msg|Call|Email] [📊 Scrubber ▾]
 *
 * - Search: stays inline as the most-used input.
 * - Apps: dropdown popover. Counter shows "All" when no apps are
 *   filtered; otherwise the count of active apps. Inside the popover:
 *   the existing CommsAppFilter pill grid.
 * - Type pills: inline (3 toggles, ~80px wide combined).
 * - Scrubber handle: thin density spark + chevron. Click to expand
 *   the full TimelineScrubber inline below the toolbar; click again
 *   to collapse. State is purely UI; the scrubber's window state
 *   (windowStart/windowEnd) is owned by the parent.
 */
export default function CommsCompactToolbar({
  searchQuery,
  onSearchChange,
  searchMatchCount,
  searchTotalCount,
  activeTypes,
  onTypesChange,
  sourceApps = [],
  activeApps,
  onAppsChange,
  hasAttachmentOnly = false,
  onHasAttachmentChange,
  scrubberItems,
  scrubberEnvelope,
  windowStart,
  windowEnd,
  onWindowChange,
}) {
  const [appsOpen, setAppsOpen] = useState(false);
  const [scrubberOpen, setScrubberOpen] = useState(false);
  const appsBtnRef = useRef(null);
  const appsPopoverRef = useRef(null);

  // Click outside the apps popover dismisses.
  useEffect(() => {
    if (!appsOpen) return undefined;
    const onDoc = (ev) => {
      if (
        appsPopoverRef.current &&
        !appsPopoverRef.current.contains(ev.target) &&
        appsBtnRef.current &&
        !appsBtnRef.current.contains(ev.target)
      ) {
        setAppsOpen(false);
      }
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [appsOpen]);

  const activeAppsCount = activeApps?.size || 0;
  const totalApps = sourceApps?.length || 0;

  // Whether the scrubber window is active — used to highlight the
  // handle with an accent so users see "you have a date filter on"
  // even when the scrubber is collapsed.
  const windowActive = !!(windowStart || windowEnd);

  return (
    <div className="border-b border-light-200 bg-white flex-shrink-0">
      {/* Toolbar row */}
      <div className="flex items-center gap-2 px-3 py-1.5">
        {/* Search — takes most of the width, capped so other controls
            stay reachable on wide screens. */}
        <div className="flex-1 min-w-[200px] max-w-3xl">
          <CellebriteSearchInput
            value={searchQuery}
            onChange={onSearchChange}
            placeholder='Search threads — try type:chat from:John app:WhatsApp'
            matchCount={searchMatchCount}
            totalCount={searchTotalCount}
            itemNoun="thread"
            focusOnSlash
            compact
          />
        </div>

        {/* Apps dropdown */}
        <div className="relative">
          <button
            ref={appsBtnRef}
            type="button"
            onClick={() => setAppsOpen(v => !v)}
            className={`inline-flex items-center gap-1 text-[11px] px-2 py-1 border rounded transition-colors ${
              activeAppsCount > 0
                ? 'bg-owl-blue-50 border-owl-blue-300 text-owl-blue-800'
                : 'bg-white border-light-300 text-light-700 hover:bg-light-100'
            }`}
            title={
              activeAppsCount > 0
                ? `${activeAppsCount} of ${totalApps} apps active`
                : 'Filter by source app (e.g. WhatsApp, SMS)'
            }
          >
            <Smartphone className="w-3 h-3" />
            <span>
              {activeAppsCount > 0
                ? `Apps (${activeAppsCount})`
                : 'All apps'}
            </span>
            <ChevronDown className="w-3 h-3" />
          </button>
          {appsOpen && (
            <div
              ref={appsPopoverRef}
              className="absolute right-0 top-full mt-1 z-30 bg-white border border-light-300 rounded shadow-xl p-2 max-h-[60vh] overflow-y-auto min-w-[280px]"
            >
              <div className="text-[10px] uppercase tracking-wide text-light-500 mb-1.5 px-1">
                Source app
              </div>
              <CommsAppFilter
                apps={sourceApps}
                active={activeApps}
                onChange={onAppsChange}
              />
            </div>
          )}
        </div>

        {/* Type pills (inline — ~80px wide, no point hiding behind
            a popover; users use these constantly) */}
        <CommsTypeFilter active={activeTypes} onChange={onTypesChange} />

        {/* Has-attachment thread filter */}
        {onHasAttachmentChange && (
          <AttachmentFilterToggle
            value={hasAttachmentOnly}
            onChange={onHasAttachmentChange}
            label="Attachments"
          />
        )}

        {/* Applied-date chips — render BEFORE the scrubber handle so
            they're the closest thing to it visually. Once you set a
            date window the scrubber's envelope-driven bounds collapse
            to that window (envelope refetches with the date filter
            applied), so the handle can't drag back outside it. These
            chips are the escape hatch — click × on either to drop
            that side, or "Clear" to remove both. */}
        {windowActive && (
          <div className="inline-flex items-center gap-1">
            {windowStart && (
              <DateChip
                label="From"
                date={windowStart}
                onClear={() => onWindowChange(null, windowEnd)}
                title="Remove start-date filter"
              />
            )}
            {windowEnd && (
              <DateChip
                label="Until"
                date={windowEnd}
                onClear={() => onWindowChange(windowStart, null)}
                title="Remove end-date filter"
              />
            )}
            <button
              type="button"
              onClick={() => onWindowChange(null, null)}
              className="text-[10px] text-light-500 hover:text-red-700 px-1"
              title="Clear both date bounds"
            >
              Clear
            </button>
          </div>
        )}

        {/* Scrubber handle */}
        <button
          type="button"
          onClick={() => setScrubberOpen(v => !v)}
          className={`inline-flex items-center gap-1 text-[11px] px-2 py-1 border rounded transition-colors ${
            windowActive
              ? 'bg-cyan-50 border-cyan-300 text-cyan-800'
              : 'bg-white border-light-300 text-light-700 hover:bg-light-100'
          }`}
          title={
            scrubberOpen
              ? 'Collapse the time scrubber'
              : 'Expand the time scrubber to filter by date range'
          }
        >
          <BarChart3 className="w-3 h-3" />
          <span>
            {windowActive
              ? `Date filter ON`
              : 'Scrubber'}
          </span>
          <ChevronDown
            className={`w-3 h-3 transition-transform ${scrubberOpen ? 'rotate-180' : ''}`}
          />
        </button>
      </div>

      {/* Expandable scrubber row */}
      {scrubberOpen && (
        <div className="border-t border-light-200">
          <TimelineScrubber
            items={scrubberItems}
            envelope={scrubberEnvelope}
            windowStart={windowStart}
            windowEnd={windowEnd}
            onWindowChange={onWindowChange}
          />
        </div>
      )}
    </div>
  );
}

/**
 * Tiny applied-date chip. "From: Jun 12, 2024 ×" / "Until: Aug 3, 2024 ×".
 * The × clears just that side; "Clear" in the parent clears both.
 *
 * Compact local date format (no time component) — the user picks date
 * boundaries, not timestamps, so the chip stays terse.
 */
function DateChip({ label, date, onClear, title }) {
  const display = date instanceof Date && !Number.isNaN(date.getTime())
    ? date.toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      })
    : '—';
  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full border border-cyan-300 bg-cyan-50 text-cyan-900 text-[11px]"
      title={title}
    >
      <Calendar className="w-3 h-3 opacity-70" />
      <span className="text-[9px] uppercase tracking-wide opacity-70">
        {label}
      </span>
      <span className="font-medium tabular-nums">{display}</span>
      <button
        type="button"
        onClick={onClear}
        className="flex-shrink-0 ml-0.5 p-0.5 rounded hover:opacity-70"
        title={title}
        aria-label={title}
      >
        <X className="w-3 h-3" />
      </button>
    </span>
  );
}
