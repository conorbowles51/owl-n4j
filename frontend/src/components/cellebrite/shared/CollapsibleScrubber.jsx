import React, { useState } from 'react';
import { ChevronDown, BarChart3 } from 'lucide-react';
import TimelineScrubber from './TimelineScrubber';

/**
 * Collapsible wrapper around TimelineScrubber. A thin header bar toggles the
 * histogram open/closed; when collapsed it still shows whether a date-range
 * filter is active so the user knows the view is narrowed even with the
 * scrubber hidden.
 *
 * Forwards every other prop straight through to TimelineScrubber
 * (items, envelope, windowStart, windowEnd, onWindowChange, onBarClick, …).
 */
export default function CollapsibleScrubber({
  defaultOpen = true,
  label = 'Timeline',
  windowStart = null,
  windowEnd = null,
  ...scrubberProps
}) {
  const [open, setOpen] = useState(defaultOpen);
  const rangeActive = windowStart instanceof Date || windowEnd instanceof Date;

  return (
    <div className="flex-shrink-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-[11px] text-light-600 border-b border-light-200 bg-light-50/60 hover:bg-light-100"
      >
        <BarChart3 className="w-3.5 h-3.5 text-light-500" />
        <span className="font-medium">{label}</span>
        {rangeActive && (
          <span className="text-owl-blue-700">· date range filtered</span>
        )}
        <span className="flex-1" />
        <span className="text-light-400">{open ? 'Hide' : 'Show'}</span>
        <ChevronDown className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <TimelineScrubber
          windowStart={windowStart}
          windowEnd={windowEnd}
          {...scrubberProps}
        />
      )}
    </div>
  );
}
