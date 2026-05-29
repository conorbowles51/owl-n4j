import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RotateCcw, CalendarRange } from 'lucide-react';

import { EVENT_COLORS } from '../events/eventUtils';

/**
 * Histogram + dual-range scrubber.
 *
 * Pure controlled component — parents own the window state.
 *
 * Props:
 *   items: Array<{ timestamp: string|Date, event_type?: string }>
 *     — anything with a parseable timestamp. Other fields are optional;
 *       event_type drives the per-bar stack colours when present.
 *   envelope?: { minDate?: string, maxDate?: string,
 *                histogram?: [{date, count}], total?: number,
 *                loading?: boolean, hasMoreThanItems?: boolean }
 *     — when provided, the scrubber uses these for its true bounds and
 *       density curve instead of (or in addition to) what it can derive
 *       from `items`. Wired by Comms Center to the cheap envelope
 *       endpoint so the bar reflects the WHOLE dataset, not just the
 *       loaded slice. `hasMoreThanItems` flips on a "+more" tint to make
 *       it visually obvious we're showing more than is currently loaded.
 *   windowStart: Date | null
 *   windowEnd:   Date | null
 *   onWindowChange: (start: Date|null, end: Date|null) => void
 *   bucketKey:   'auto' | 'hour' | 'day' | 'week'
 *   onBarClick:  (bucketStart: Date, bucketEnd: Date) => void
 *                — click a bar (not a handle) to jump-scroll to it
 *   compact:     boolean — slimmer (40px) for in-thread use
 *   getColorForType?: (event_type: string) => string  — overrides EVENT_COLORS
 */
export default function TimelineScrubber({
  items = [],
  envelope = null,
  windowStart = null,
  windowEnd = null,
  onWindowChange,
  bucketKey = 'auto',
  onBarClick,
  compact = false,
  getColorForType,
}) {
  // ------------------------------------------------------------------
  // Bounds + bucketing
  //
  // Every hook below MUST run unconditionally on every render, regardless
  // of whether `items` has data — otherwise React's hook-order check
  // panics ("Rendered more hooks than during the previous render") when
  // the component first mounts with empty items and later receives data.
  // The only conditional return is the LAST line before the JSX block.
  // ------------------------------------------------------------------
  // The envelope (when present) is authoritative for bounds and density.
  // It comes from a cheap server-side aggregation that sees the WHOLE
  // dataset, not just the loaded slice — without it the scrubber lies
  // about end dates whenever the body fetch was capped.
  const { minTs, maxTs, buckets, bucketSizeMs, bucketUnit } = useMemo(
    () => (envelope && (envelope.histogram || envelope.minDate)
      ? buildBucketsFromEnvelope(envelope, bucketKey)
      : buildBuckets(items, bucketKey)),
    [envelope, items, bucketKey],
  );

  const colorFor = useCallback(
    (eventType) => {
      if (getColorForType) return getColorForType(eventType);
      return EVENT_COLORS[eventType] || '#94a3b8';
    },
    [getColorForType],
  );

  // Safe defaults so the hook chain below has finite numbers when
  // there's no time range yet. The component still renders nothing
  // (early return below) but the hook order stays consistent.
  const hasRange = minTs != null && maxTs != null && minTs < maxTs;
  const safeMinTs = hasRange ? minTs : 0;
  const safeMaxTs = hasRange ? maxTs : 1;

  // Effective window — defaults to full range when null.
  const propStart = windowStart instanceof Date ? windowStart.getTime() : safeMinTs;
  const propEnd = windowEnd instanceof Date ? windowEnd.getTime() : safeMaxTs;

  // Drag preview — while the user is mid-drag we render handles against
  // this local state instead of firing onWindowChange on every pointer
  // move. The parent's window prop (and the downstream API fetches) only
  // update once on pointerup. Without this, each pointermove event
  // (dozens/sec) re-triggered the comms/threads + comms/envelope
  // useEffects, saturating Chrome's 6-per-origin connection cap and
  // stalling new requests at the TCP layer.
  const [dragPreview, setDragPreview] = useState(null); // {start, end} ms or null
  // Mirror of dragPreview in a ref so pointerup can read the latest window
  // WITHOUT committing inside a setState updater (calling onWindowChange —
  // a parent setState — from within setDragPreview's updater ran a parent
  // update during this component's render = the "Cannot update a component
  // while rendering a different component" warning).
  const dragPreviewRef = useRef(null);
  const setPreview = useCallback((p) => {
    dragPreviewRef.current = p;
    setDragPreview(p);
  }, []);

  const effectiveStart = dragPreview ? dragPreview.start : propStart;
  const effectiveEnd = dragPreview ? dragPreview.end : propEnd;
  const isFullWindow = effectiveStart <= safeMinTs && effectiveEnd >= safeMaxTs;

  // ------------------------------------------------------------------
  // Layout — measure container width so handles can be positioned in px
  // ------------------------------------------------------------------
  const containerRef = useRef(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!hasRange) return;
    const el = containerRef.current;
    if (!el) return;
    const resize = () => setWidth(el.clientWidth || 0);
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    return () => ro.disconnect();
  }, [hasRange]);

  const totalSpan = safeMaxTs - safeMinTs;
  const tsToX = useCallback(
    (ts) => ((ts - safeMinTs) / totalSpan) * width,
    [safeMinTs, totalSpan, width],
  );
  const xToTs = useCallback(
    (x) => Math.round(safeMinTs + (x / Math.max(width, 1)) * totalSpan),
    [safeMinTs, totalSpan, width],
  );

  const startX = tsToX(Math.max(safeMinTs, Math.min(safeMaxTs, effectiveStart)));
  const endX = tsToX(Math.max(safeMinTs, Math.min(safeMaxTs, effectiveEnd)));

  // ------------------------------------------------------------------
  // Drag handling
  // ------------------------------------------------------------------
  const dragRef = useRef(null); // 'start' | 'end' | 'window'  | null
  const dragOffsetRef = useRef(0); // for 'window' drag
  const onPointerDown = (which) => (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragRef.current = which;
    if (which === 'window') {
      const rect = containerRef.current.getBoundingClientRect();
      const px = e.clientX - rect.left;
      dragOffsetRef.current = px - startX;
    }
    e.currentTarget.setPointerCapture?.(e.pointerId);
  };
  const onPointerMove = useCallback(
    (e) => {
      const which = dragRef.current;
      if (!which) return;
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return;
      let px = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
      if (which === 'start') {
        const ts = xToTs(px);
        const clamped = Math.min(ts, effectiveEnd - bucketSizeMs);
        setPreview({ start: Math.max(safeMinTs, clamped), end: effectiveEnd });
      } else if (which === 'end') {
        const ts = xToTs(px);
        const clamped = Math.max(ts, effectiveStart + bucketSizeMs);
        setPreview({ start: effectiveStart, end: Math.min(safeMaxTs, clamped) });
      } else if (which === 'window') {
        const newStartPx = Math.max(0, px - dragOffsetRef.current);
        const windowPx = endX - startX;
        const newEndPx = Math.min(rect.width, newStartPx + windowPx);
        const newStartTs = xToTs(newEndPx - windowPx);
        const newEndTs = xToTs(newEndPx);
        setPreview({ start: newStartTs, end: newEndTs });
      }
    },
    [bucketSizeMs, effectiveEnd, effectiveStart, endX, safeMaxTs, safeMinTs, startX, xToTs, setPreview],
  );
  const onPointerUp = useCallback(() => {
    if (!dragRef.current) return;
    dragRef.current = null;
    // Commit the previewed window to the parent — single onWindowChange
    // per drag gesture, instead of one per pointermove event. Read the
    // latest preview from the ref and clear state separately, so we never
    // run a parent setState from inside our own setState updater.
    const prev = dragPreviewRef.current;
    dragPreviewRef.current = null;
    setDragPreview(null);
    if (prev) onWindowChange?.(new Date(prev.start), new Date(prev.end));
  }, [onWindowChange]);
  useEffect(() => {
    if (!hasRange) return;
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
    return () => {
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
    };
  }, [hasRange, onPointerMove, onPointerUp]);

  // ------------------------------------------------------------------
  // Geometry
  // ------------------------------------------------------------------
  const chartHeight = compact ? 40 : 64;
  const tickHeight = 18;
  const totalHeight = chartHeight + tickHeight;

  // ------------------------------------------------------------------
  // Bars
  // ------------------------------------------------------------------
  const maxCount = useMemo(() => {
    let m = 0;
    for (const b of buckets) if (b.count > m) m = b.count;
    return m;
  }, [buckets]);

  const bucketWidthPx = width / Math.max(buckets.length, 1);
  // Leave a 1px gap between bars when there's room
  const visualBarWidth = Math.max(1, bucketWidthPx - 1);

  const ticks = useMemo(() => buildTicks(safeMinTs, safeMaxTs, 5), [safeMinTs, safeMaxTs]);

  // ------------------------------------------------------------------
  // Reset
  // ------------------------------------------------------------------
  const reset = () => onWindowChange?.(null, null);

  // Render nothing if we have no real time range (single point or empty
  // dataset). All hooks above ran unconditionally so React's hook-order
  // contract is satisfied.
  if (!hasRange) {
    return null;
  }

  return (
    <div className="px-3 py-2 border-b border-light-200 bg-light-50/60 flex-shrink-0">
      <div
        ref={containerRef}
        className="relative w-full select-none"
        style={{ height: totalHeight }}
      >
        {/* Background */}
        <div
          className="absolute inset-x-0 top-0 bg-white border border-light-200 rounded"
          style={{ height: chartHeight }}
        />

        {/* Bars */}
        <svg
          className="absolute inset-x-0 top-0"
          width={width || 0}
          height={chartHeight}
          style={{ overflow: 'visible' }}
        >
          {buckets.map((b, i) => {
            const inWindow = b.start >= effectiveStart - 1 && b.end <= effectiveEnd + 1;
            const baseX = i * bucketWidthPx;
            // Stack segments by event type, tallest at the top
            let cursorY = chartHeight;
            const segments = Object.entries(b.byType).sort((a, b2) => b2[1] - a[1]);
            const totalH = (b.count / Math.max(maxCount, 1)) * (chartHeight - 4);
            const yTop = chartHeight - totalH;
            return (
              <g
                key={i}
                opacity={inWindow ? 1 : 0.28}
                onClick={() => onBarClick?.(new Date(b.start), new Date(b.end))}
                style={{ cursor: onBarClick ? 'pointer' : 'default' }}
              >
                <title>
                  {`${formatBucketLabel(b.start, bucketUnit)} — ${b.count.toLocaleString()} event${b.count === 1 ? '' : 's'}`}
                </title>
                {/* Hover hit-target spanning the full bar column */}
                <rect
                  x={baseX}
                  y={0}
                  width={bucketWidthPx}
                  height={chartHeight}
                  fill="transparent"
                />
                {segments.map(([type, count], j) => {
                  const segH = (count / Math.max(b.count, 1)) * totalH;
                  cursorY -= segH;
                  return (
                    <rect
                      key={j}
                      x={baseX + (bucketWidthPx - visualBarWidth) / 2}
                      y={cursorY}
                      width={visualBarWidth}
                      height={Math.max(0.5, segH)}
                      fill={colorFor(type)}
                    />
                  );
                })}
                {/* Reset cursorY for next iter — handled via local var */}
                {b.count === 0 && null}
                {/* Stub to keep yTop referenced (so the linter sees it) */}
                {yTop < 0 && null}
              </g>
            );
          })}
        </svg>

        {/* Window overlay (dim outside) */}
        <div
          className="absolute top-0 bg-light-900/10 pointer-events-none"
          style={{ left: 0, width: `${Math.max(0, startX)}px`, height: chartHeight }}
        />
        <div
          className="absolute top-0 bg-light-900/10 pointer-events-none"
          style={{ left: `${Math.max(0, endX)}px`, right: 0, height: chartHeight }}
        />

        {/* Window region (draggable to pan) */}
        <div
          onPointerDown={onPointerDown('window')}
          className="absolute top-0 cursor-grab active:cursor-grabbing border-x-2 border-owl-blue-400/70"
          style={{
            left: `${startX}px`,
            width: `${Math.max(2, endX - startX)}px`,
            height: chartHeight,
          }}
        />

        {/* Start handle */}
        <div
          onPointerDown={onPointerDown('start')}
          className="absolute top-0 -translate-x-1/2 cursor-ew-resize"
          style={{ left: `${startX}px`, height: chartHeight }}
        >
          <div className="w-2.5 h-full bg-owl-blue-600 rounded-l shadow border border-owl-blue-700" />
        </div>

        {/* End handle */}
        <div
          onPointerDown={onPointerDown('end')}
          className="absolute top-0 -translate-x-1/2 cursor-ew-resize"
          style={{ left: `${endX}px`, height: chartHeight }}
        >
          <div className="w-2.5 h-full bg-owl-blue-600 rounded-r shadow border border-owl-blue-700" />
        </div>

        {/* Tick labels */}
        <div
          className="absolute inset-x-0 flex justify-between text-[10px] text-light-500 tabular-nums"
          style={{ top: chartHeight + 2 }}
        >
          {ticks.map((t, i) => (
            <span key={i}>{formatTick(t, bucketUnit)}</span>
          ))}
        </div>
      </div>

      {/* Loading stripe — shown while the envelope is recomputing so the
          user can tell the bar is briefly out of date vs. genuinely
          showing zero. Subtle by design; doesn't move the layout. */}
      {envelope?.loading && (
        <div className="absolute left-3 right-3 top-2 h-0.5 bg-owl-blue-200/40 overflow-hidden rounded-full">
          <div className="h-full w-1/3 bg-owl-blue-500/60 animate-pulse" />
        </div>
      )}

      {/* Window summary + reset */}
      <div className="flex items-center justify-between mt-1 text-[11px] text-light-600">
        <div>
          {isFullWindow ? (
            <span className="text-light-500">
              All time · {(envelope?.total ?? items.length).toLocaleString()} item
              {(envelope?.total ?? items.length) === 1 ? '' : 's'}
              {envelope?.hasMoreThanItems && (
                <span
                  className="ml-1 text-amber-700"
                  title="Scrubber bounds reflect the whole dataset; the body fetch is showing a slice"
                >
                  · scrubber covers full range
                </span>
              )}
            </span>
          ) : (
            <span>
              <span className="font-medium text-light-800">{formatTick(effectiveStart, bucketUnit)}</span>
              <span className="mx-1.5 text-light-400">→</span>
              <span className="font-medium text-light-800">{formatTick(effectiveEnd, bucketUnit)}</span>
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {/* Calendar / manual date-range entry — the scrubber gives the
              overview, this gives precise start/end selection. Operates in
              the same browser-local clock the ticks use, and is clamped to
              the data bounds. */}
          <DateRangePicker
            minTs={safeMinTs}
            maxTs={safeMaxTs}
            startTs={effectiveStart}
            endTs={effectiveEnd}
            onApply={(s, e) => onWindowChange?.(s, e)}
            onClear={reset}
          />
          {!isFullWindow && (
            <button
              type="button"
              onClick={reset}
              className="inline-flex items-center gap-1 text-owl-blue-700 hover:text-owl-blue-900 hover:underline"
            >
              <RotateCcw className="w-3 h-3" /> Reset
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Date-range picker — calendar + manual date/time entry
//
// The scrubber is great for seeing the available range at a glance but
// fiddly for selecting a precise window. This popover lets the analyst
// pick (or type) an exact start and end. It works in the same
// browser-local clock the scrubber's ticks render in, and stays in the
// component so every place that renders a scrubber gets it for free.
// ---------------------------------------------------------------------------
function DateRangePicker({ minTs, maxTs, startTs, endTs, onApply, onClear }) {
  const [open, setOpen] = useState(false);
  const [startVal, setStartVal] = useState('');
  const [endVal, setEndVal] = useState('');
  const ref = useRef(null);

  // Seed the inputs from the current window each time the popover opens
  // (or when the committed window changes while open, e.g. via a drag).
  useEffect(() => {
    if (!open) return;
    setStartVal(toLocalInputValue(startTs));
    setEndVal(toLocalInputValue(endTs));
  }, [open, startTs, endTs]);

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    const onDocClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  const minVal = toLocalInputValue(minTs);
  const maxVal = toLocalInputValue(maxTs);
  const startMs = fromLocalInputValue(startVal);
  const endMs = fromLocalInputValue(endVal);
  const invalid = startMs == null || endMs == null || startMs > endMs;

  const apply = () => {
    if (invalid) return;
    // Clamp to the data bounds so a typed value outside the range can't
    // push the window off the axis.
    onApply(
      new Date(Math.max(minTs, Math.min(maxTs, startMs))),
      new Date(Math.max(minTs, Math.min(maxTs, endMs))),
    );
    setOpen(false);
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1 text-owl-blue-700 hover:text-owl-blue-900 hover:underline"
        title="Pick an exact start and end date"
      >
        <CalendarRange className="w-3 h-3" /> Pick dates
      </button>
      {open && (
        <div className="absolute right-0 bottom-full mb-1 z-30 w-64 p-3 bg-white border border-light-300 rounded-lg shadow-lg text-light-700">
          <div className="space-y-2">
            <label className="block">
              <span className="block text-[10px] uppercase tracking-wide text-light-500 mb-0.5">Start</span>
              <input
                type="datetime-local"
                value={startVal}
                min={minVal}
                max={maxVal}
                onChange={(e) => setStartVal(e.target.value)}
                className="w-full px-2 py-1 text-[11px] border border-light-300 rounded focus:outline-none focus:ring-1 focus:ring-owl-blue-400"
              />
            </label>
            <label className="block">
              <span className="block text-[10px] uppercase tracking-wide text-light-500 mb-0.5">End</span>
              <input
                type="datetime-local"
                value={endVal}
                min={minVal}
                max={maxVal}
                onChange={(e) => setEndVal(e.target.value)}
                className="w-full px-2 py-1 text-[11px] border border-light-300 rounded focus:outline-none focus:ring-1 focus:ring-owl-blue-400"
              />
            </label>
          </div>
          {invalid && (
            <p className="mt-1.5 text-[10px] text-amber-700">Start must be on or before end.</p>
          )}
          <div className="flex items-center justify-between mt-2.5">
            <button
              type="button"
              onClick={() => { onClear(); setOpen(false); }}
              className="text-[11px] text-light-500 hover:text-light-700 hover:underline"
            >
              Clear
            </button>
            <button
              type="button"
              onClick={apply}
              disabled={invalid}
              className="px-2.5 py-1 text-[11px] font-medium rounded bg-owl-blue-600 text-white hover:bg-owl-blue-700 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Apply
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/** ms timestamp → "YYYY-MM-DDTHH:MM" in browser-local time for <input type="datetime-local">. */
function toLocalInputValue(ms) {
  const d = new Date(ms);
  if (isNaN(d.getTime())) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** "YYYY-MM-DDTHH:MM" (local) → ms timestamp, or null. */
function fromLocalInputValue(v) {
  if (!v) return null;
  const t = new Date(v).getTime();
  return isNaN(t) ? null : t;
}

// ---------------------------------------------------------------------------
// Bucket builder
// ---------------------------------------------------------------------------

/**
 * Build the bucket array from a server envelope { histogram: [{date,
 * count}], minDate, maxDate }. The histogram is per-day; if the span
 * is too long for daily bars we re-aggregate into weeks. If the span
 * is short and the histogram is empty (e.g. a freshly-filtered slice
 * with no matches yet) we return an empty bucket set, which the
 * component handles by rendering nothing.
 */
function buildBucketsFromEnvelope(envelope, bucketKey) {
  const hist = Array.isArray(envelope.histogram) ? envelope.histogram : [];
  const minDate = envelope.minDate || (hist.length ? hist[0].date : null);
  const maxDate = envelope.maxDate || (hist.length ? hist[hist.length - 1].date : null);
  if (!minDate || !maxDate) {
    return { minTs: null, maxTs: null, buckets: [], bucketSizeMs: 0, bucketUnit: 'day' };
  }
  // Parse YYYY-MM-DD as midnight LOCAL — matches the writer's day cut.
  const minTs = new Date(`${minDate}T00:00:00`).getTime();
  const maxTs = new Date(`${maxDate}T23:59:59.999`).getTime();
  if (isNaN(minTs) || isNaN(maxTs) || minTs >= maxTs) {
    return { minTs: null, maxTs: null, buckets: [], bucketSizeMs: 0, bucketUnit: 'day' };
  }
  const span = maxTs - minTs;
  const unit = pickBucketUnit(span, bucketKey);
  let sizeMs = unitMs(unit);
  const startBucket = floorTo(minTs, unit);
  let bucketCount = Math.max(1, Math.ceil((maxTs - startBucket) / sizeMs));
  // Backstop against a degenerate server envelope (e.g. a year-0001
  // minDate) blowing the bar count up and freezing the tab.
  if (bucketCount > MAX_BUCKETS) {
    sizeMs = Math.ceil((maxTs - startBucket) / MAX_BUCKETS);
    bucketCount = Math.max(1, Math.ceil((maxTs - startBucket) / sizeMs));
  }
  const buckets = [];
  for (let i = 0; i < bucketCount; i++) {
    buckets.push({
      start: startBucket + i * sizeMs,
      end: startBucket + (i + 1) * sizeMs,
      count: 0,
      byType: {},
    });
  }
  // Map per-day histogram into the chosen bucket unit. Per-day → daily
  // is 1:1; per-day → weekly aggregates 7-day spans into one bar.
  for (const row of hist) {
    if (!row || !row.date) continue;
    const ts = new Date(`${row.date}T12:00:00`).getTime();
    if (isNaN(ts)) continue;
    const idx = Math.min(bucketCount - 1, Math.max(0, Math.floor((ts - startBucket) / sizeMs)));
    const c = Number(row.count) || 0;
    buckets[idx].count += c;
    buckets[idx].byType.envelope = (buckets[idx].byType.envelope || 0) + c;
  }
  return {
    minTs: startBucket,
    maxTs: startBucket + bucketCount * sizeMs,
    buckets,
    bucketSizeMs: sizeMs,
    bucketUnit: unit,
  };
}

function buildBuckets(items, bucketKey) {
  if (!items || items.length === 0) {
    return { minTs: null, maxTs: null, buckets: [], bucketSizeMs: 0, bucketUnit: 'day' };
  }
  let minTs = Infinity;
  let maxTs = -Infinity;
  for (const it of items) {
    const t = parseTimestamp(it);
    if (t == null || !isPlausibleTs(t)) continue;
    if (t < minTs) minTs = t;
    if (t > maxTs) maxTs = t;
  }
  if (!isFinite(minTs) || !isFinite(maxTs)) {
    return { minTs: null, maxTs: null, buckets: [], bucketSizeMs: 0, bucketUnit: 'day' };
  }
  // Pad ends so the first/last events aren't visually flush against the edges.
  const span = maxTs - minTs;
  const pad = Math.max(span * 0.01, 1000);
  minTs -= pad;
  maxTs += pad;

  const unit = pickBucketUnit(span, bucketKey);
  let sizeMs = unitMs(unit);
  const startBucket = floorTo(minTs, unit);
  let bucketCount = Math.max(1, Math.ceil((maxTs - startBucket) / sizeMs));
  // Backstop: never build a runaway number of bars even if some
  // degenerate timestamp survives the plausibility filter — widen the
  // bucket so we stay under the cap. ~100k SVG <g> bars froze the tab.
  if (bucketCount > MAX_BUCKETS) {
    sizeMs = Math.ceil((maxTs - startBucket) / MAX_BUCKETS);
    bucketCount = Math.max(1, Math.ceil((maxTs - startBucket) / sizeMs));
  }
  const buckets = [];
  for (let i = 0; i < bucketCount; i++) {
    buckets.push({
      start: startBucket + i * sizeMs,
      end: startBucket + (i + 1) * sizeMs,
      count: 0,
      byType: {},
    });
  }
  for (const it of items) {
    const t = parseTimestamp(it);
    if (t == null) continue;
    const idx = Math.min(bucketCount - 1, Math.max(0, Math.floor((t - startBucket) / sizeMs)));
    const b = buckets[idx];
    b.count += 1;
    const type = it.event_type || it.thread_type || 'unknown';
    b.byType[type] = (b.byType[type] || 0) + 1;
  }
  return { minTs: startBucket, maxTs: startBucket + bucketCount * sizeMs, buckets, bucketSizeMs: sizeMs, bucketUnit: unit };
}

function parseTimestamp(it) {
  const v = it.timestamp ?? it.last_activity ?? it.last_message_at;
  if (!v) return null;
  if (v instanceof Date) return v.getTime();
  const t = new Date(v).getTime();
  return isNaN(t) ? null : t;
}

// Hard cap on the number of histogram bars. Each bar is an SVG <g>; left
// uncapped, a degenerate span renders ~100k of them and freezes the tab.
const MAX_BUCKETS = 2000;

// Phone-forensics timestamps live in the smartphone era. A value far
// outside it — most commonly a year-0001 / 1970 epoch-zero sentinel left
// by a failed date parse at ingest — is not real data, and letting it set
// the histogram bounds stretches the axis to ~2000 years (→ ~100k bars →
// frozen tab). Such items are excluded from the RANGE here; they're still
// dropped into the nearest edge bar by the bucketing loop, so nothing is
// hidden — they just can't blow up the axis. Upper bound is "tomorrow" so
// a clock-skewed future stamp can't stretch it either.
const PLAUSIBLE_MIN_MS = Date.UTC(2000, 0, 1);
function isPlausibleTs(t) {
  return t >= PLAUSIBLE_MIN_MS && t <= Date.now() + 24 * 60 * 60 * 1000;
}

function pickBucketUnit(spanMs, bucketKey) {
  if (bucketKey === 'hour' || bucketKey === 'day' || bucketKey === 'week') return bucketKey;
  const days = spanMs / (24 * 60 * 60 * 1000);
  if (days <= 2) return 'hour';
  if (days <= 120) return 'day';
  return 'week';
}

function unitMs(unit) {
  if (unit === 'hour') return 60 * 60 * 1000;
  if (unit === 'week') return 7 * 24 * 60 * 60 * 1000;
  return 24 * 60 * 60 * 1000;
}

function floorTo(ts, unit) {
  const d = new Date(ts);
  if (unit === 'hour') {
    d.setMinutes(0, 0, 0);
    return d.getTime();
  }
  if (unit === 'week') {
    d.setHours(0, 0, 0, 0);
    const dow = d.getDay(); // 0=Sun, 1=Mon
    const daysFromMonday = (dow + 6) % 7;
    d.setDate(d.getDate() - daysFromMonday);
    return d.getTime();
  }
  // day
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

function buildTicks(minTs, maxTs, n) {
  const ticks = [];
  for (let i = 0; i < n; i++) {
    ticks.push(minTs + ((maxTs - minTs) * i) / (n - 1));
  }
  return ticks;
}

function formatTick(ts, unit) {
  const d = new Date(ts);
  if (unit === 'hour') {
    return d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  }
  return d.toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' });
}

function formatBucketLabel(ts, unit) {
  const d = new Date(ts);
  if (unit === 'hour') {
    return d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  }
  if (unit === 'week') {
    const end = new Date(ts + 6 * 24 * 60 * 60 * 1000);
    return `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })} – ${end.toLocaleDateString([], { month: 'short', day: 'numeric' })}`;
  }
  return d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
}
