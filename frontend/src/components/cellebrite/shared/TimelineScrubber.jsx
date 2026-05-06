import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RotateCcw } from 'lucide-react';

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
  const { minTs, maxTs, buckets, bucketSizeMs, bucketUnit } = useMemo(
    () => buildBuckets(items, bucketKey),
    [items, bucketKey],
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
  const effectiveStart = windowStart instanceof Date ? windowStart.getTime() : safeMinTs;
  const effectiveEnd = windowEnd instanceof Date ? windowEnd.getTime() : safeMaxTs;
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
        onWindowChange?.(new Date(Math.max(safeMinTs, clamped)), new Date(effectiveEnd));
      } else if (which === 'end') {
        const ts = xToTs(px);
        const clamped = Math.max(ts, effectiveStart + bucketSizeMs);
        onWindowChange?.(new Date(effectiveStart), new Date(Math.min(safeMaxTs, clamped)));
      } else if (which === 'window') {
        const newStartPx = Math.max(0, px - dragOffsetRef.current);
        const windowPx = endX - startX;
        const newEndPx = Math.min(rect.width, newStartPx + windowPx);
        const newStartTs = xToTs(newEndPx - windowPx);
        const newEndTs = xToTs(newEndPx);
        onWindowChange?.(new Date(newStartTs), new Date(newEndTs));
      }
    },
    [bucketSizeMs, effectiveEnd, effectiveStart, endX, safeMaxTs, safeMinTs, onWindowChange, startX, xToTs],
  );
  const onPointerUp = useCallback(() => {
    dragRef.current = null;
  }, []);
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

      {/* Window summary + reset */}
      <div className="flex items-center justify-between mt-1 text-[11px] text-light-600">
        <div>
          {isFullWindow ? (
            <span className="text-light-500">All time · {items.length.toLocaleString()} item{items.length === 1 ? '' : 's'}</span>
          ) : (
            <span>
              <span className="font-medium text-light-800">{formatTick(effectiveStart, bucketUnit)}</span>
              <span className="mx-1.5 text-light-400">→</span>
              <span className="font-medium text-light-800">{formatTick(effectiveEnd, bucketUnit)}</span>
            </span>
          )}
        </div>
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
  );
}

// ---------------------------------------------------------------------------
// Bucket builder
// ---------------------------------------------------------------------------

function buildBuckets(items, bucketKey) {
  if (!items || items.length === 0) {
    return { minTs: null, maxTs: null, buckets: [], bucketSizeMs: 0, bucketUnit: 'day' };
  }
  let minTs = Infinity;
  let maxTs = -Infinity;
  for (const it of items) {
    const t = parseTimestamp(it);
    if (t == null) continue;
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
  const sizeMs = unitMs(unit);
  const startBucket = floorTo(minTs, unit);
  const bucketCount = Math.max(1, Math.ceil((maxTs - startBucket) / sizeMs));
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
