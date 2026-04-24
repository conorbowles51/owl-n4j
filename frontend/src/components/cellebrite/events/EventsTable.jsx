import React, { useEffect, useLayoutEffect, useMemo, useRef, useState, useCallback } from 'react';
import { ArrowUp, ArrowDown, MapPin } from 'lucide-react';
import { EVENT_COLORS, EVENT_ICONS, EVENT_LABELS, formatTs } from './eventUtils';

/**
 * Simple windowed table for Cellebrite events. Does its own row-culling via
 * absolute-positioned rows inside a tall container so we don't need a 3rd
 * party library. Handles 5k+ rows smoothly.
 *
 * Props:
 *   events                     — already-filtered events from the parent
 *   reports                    — for device label resolution
 *   playheadTime               — Date | null (drives highlight + auto-scroll)
 *   isPlaying                  — boolean
 *   selectedEventId            — currently-selected event id (drawer focus)
 *   onEventClick(event)        — open detail drawer
 */

const ROW_HEIGHT = 36;
const HEADER_HEIGHT = 32;
const FOOTER_HEIGHT = 26;
const OVERSCAN = 6; // extra rows rendered above/below the viewport

export default function EventsTable({
  events = [],
  reports = [],
  playheadTime = null,
  isPlaying = false,
  selectedEventId = null,
  onEventClick,
}) {
  const [sort, setSort] = useState({ key: 'timestamp', dir: 'desc' });
  const [scrollTop, setScrollTop] = useState(0);
  const [containerHeight, setContainerHeight] = useState(400);
  const bodyRef = useRef(null);
  const autoScrollPauseUntilRef = useRef(0);
  const lastAutoScrolledIndexRef = useRef(-1);

  // Resolve a short device label per report_key
  const deviceById = useMemo(() => {
    const m = {};
    for (const r of reports) {
      const label = [r.device_model, r.phone_owner_name].filter(Boolean).join(' · ');
      m[r.report_key] = label || r.device_model || 'Device';
    }
    return m;
  }, [reports]);

  // Sorted events
  const sortedEvents = useMemo(() => {
    const arr = [...events];
    const { key, dir } = sort;
    const factor = dir === 'asc' ? 1 : -1;
    arr.sort((a, b) => {
      const av = a?.[key];
      const bv = b?.[key];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (av < bv) return -1 * factor;
      if (av > bv) return 1 * factor;
      return 0;
    });
    return arr;
  }, [events, sort]);

  // Playhead-driven current row index (timestamp-sorted-ascending binary search)
  const currentIndex = useMemo(() => {
    if (!playheadTime) return -1;
    const t = playheadTime.getTime();
    // Use the sorted list regardless of direction for the binary search
    const asc = sort.key === 'timestamp' && sort.dir === 'asc';
    const list = asc ? sortedEvents : [...sortedEvents].reverse();
    // find last index whose timestamp <= t
    let lo = 0;
    let hi = list.length - 1;
    let result = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      const ts = list[mid]?.timestamp ? new Date(list[mid].timestamp).getTime() : 0;
      if (ts <= t) {
        result = mid;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }
    if (result < 0) return -1;
    return asc ? result : sortedEvents.length - 1 - result;
  }, [playheadTime, sortedEvents, sort]);

  // Observe container height for windowing
  useLayoutEffect(() => {
    const el = bodyRef.current;
    if (!el) return;
    const resize = () => setContainerHeight(el.clientHeight || 400);
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Scroll handler → windowing + pause auto-scroll when user scrolls
  const handleScroll = useCallback(
    (e) => {
      const top = e.currentTarget.scrollTop;
      setScrollTop(top);
      // User scrolled manually → pause auto-scroll for 3s (only during playback)
      if (isPlaying) {
        autoScrollPauseUntilRef.current = Date.now() + 3000;
      }
    },
    [isPlaying]
  );

  // Auto-scroll to the current row during playback
  useEffect(() => {
    if (!isPlaying || currentIndex < 0) return;
    if (Date.now() < autoScrollPauseUntilRef.current) return;
    if (currentIndex === lastAutoScrolledIndexRef.current) return;
    const el = bodyRef.current;
    if (!el) return;
    const rowTop = currentIndex * ROW_HEIGHT;
    const target = rowTop - el.clientHeight / 2 + ROW_HEIGHT / 2;
    el.scrollTo({ top: Math.max(0, target), behavior: 'smooth' });
    lastAutoScrolledIndexRef.current = currentIndex;
  }, [currentIndex, isPlaying]);

  const total = sortedEvents.length;
  const totalHeight = total * ROW_HEIGHT;
  const viewportRows = Math.ceil(containerHeight / ROW_HEIGHT) + OVERSCAN * 2;
  const startIdx = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
  const endIdx = Math.min(total, startIdx + viewportRows);
  const visibleRows = sortedEvents.slice(startIdx, endIdx);

  const toggleSort = (key) => {
    setSort((prev) =>
      prev.key === key ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: key === 'timestamp' ? 'desc' : 'asc' }
    );
  };

  const playheadMs = playheadTime ? playheadTime.getTime() : null;

  return (
    <div className="flex flex-col h-full min-h-0 bg-white text-xs">
      {/* Header */}
      <div
        className="grid border-b border-light-200 bg-light-50 text-[11px] font-semibold text-light-700 flex-shrink-0"
        style={{ gridTemplateColumns: COLUMN_TEMPLATE, height: HEADER_HEIGHT }}
      >
        <HeaderCell label="Time" sortKey="timestamp" sort={sort} onSort={toggleSort} />
        <HeaderCell label="Type" sortKey="event_type" sort={sort} onSort={toggleSort} />
        <HeaderCell label="Device" sortKey="device_report_key" sort={sort} onSort={toggleSort} />
        <HeaderCell label="Label" sortKey="label" sort={sort} onSort={toggleSort} />
        <HeaderCell label="From" sortKey="sender_name" sort={sort} onSort={toggleSort} />
        <HeaderCell label="To" sortKey="recipient_name" sort={sort} onSort={toggleSort} />
        <HeaderCell label="Summary" sortKey="summary" sort={sort} onSort={toggleSort} />
        <HeaderCell label="Geo" sortKey="latitude" sort={sort} onSort={toggleSort} align="right" />
      </div>

      {/* Body */}
      <div
        ref={bodyRef}
        onScroll={handleScroll}
        className="flex-1 min-h-0 overflow-auto relative"
      >
        <div style={{ height: totalHeight, position: 'relative' }}>
          {visibleRows.map((ev, i) => {
            const idx = startIdx + i;
            const top = idx * ROW_HEIGHT;
            const eventTs = ev.timestamp ? new Date(ev.timestamp).getTime() : null;
            const isSelected = selectedEventId && (ev.id === selectedEventId || ev.node_key === selectedEventId);
            const isCurrent = idx === currentIndex && isPlaying;
            const isFuture = playheadMs != null && eventTs != null && eventTs > playheadMs;
            return (
              <TableRow
                key={ev.id || ev.node_key || idx}
                ev={ev}
                top={top}
                deviceLabel={deviceById[ev.device_report_key]}
                isSelected={isSelected}
                isCurrent={isCurrent}
                isFuture={isFuture}
                onClick={() => onEventClick?.(ev)}
              />
            );
          })}
        </div>
      </div>

      {/* Footer */}
      <div
        className="flex items-center justify-between px-3 text-[10px] text-light-500 border-t border-light-200 bg-light-50 flex-shrink-0"
        style={{ height: FOOTER_HEIGHT }}
      >
        <span>
          Showing {total.toLocaleString()} event{total === 1 ? '' : 's'}
        </span>
        <span>
          Sorted by {sort.key} {sort.dir === 'asc' ? '↑' : '↓'}
        </span>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------
// Column template + header cell
// ------------------------------------------------------------------

const COLUMN_TEMPLATE =
  'minmax(140px, 160px) minmax(90px, 110px) minmax(140px, 180px) minmax(140px, 1fr) minmax(90px, 140px) minmax(90px, 140px) minmax(180px, 1.5fr) minmax(110px, 130px)';

function HeaderCell({ label, sortKey, sort, onSort, align = 'left' }) {
  const active = sort.key === sortKey;
  const Icon = sort.dir === 'asc' ? ArrowUp : ArrowDown;
  return (
    <button
      onClick={() => onSort(sortKey)}
      className={`flex items-center gap-1 px-2 border-r border-light-200 hover:bg-light-100 ${
        align === 'right' ? 'justify-end' : 'justify-start'
      } ${active ? 'text-owl-blue-700' : 'text-light-700'}`}
    >
      <span className="truncate">{label}</span>
      {active && <Icon className="w-2.5 h-2.5 flex-shrink-0" />}
    </button>
  );
}

// ------------------------------------------------------------------
// Row (memoised)
// ------------------------------------------------------------------

const TableRow = React.memo(function TableRow({
  ev,
  top,
  deviceLabel,
  isSelected,
  isCurrent,
  isFuture,
  onClick,
}) {
  const Icon = EVENT_ICONS[ev.event_type] || EVENT_ICONS.location;
  const color = EVENT_COLORS[ev.event_type] || '#64748b';
  const label = ev.label || EVENT_LABELS[ev.event_type] || ev.event_type;
  const senderName = ev.sender?.name || '';
  const recipientName =
    ev.recipient?.name ||
    (Array.isArray(ev.recipients) && ev.recipients[0]?.name) ||
    ev.counterpart?.name ||
    '';
  const hasGeo = ev.latitude != null && ev.longitude != null;

  const rowClasses = [
    'grid absolute inset-x-0 items-center border-b border-light-100 cursor-pointer select-none',
    isCurrent
      ? 'bg-owl-blue-100 ring-1 ring-owl-blue-400'
      : isSelected
      ? 'bg-owl-blue-50'
      : 'hover:bg-light-50',
    isFuture ? 'opacity-55' : '',
  ].join(' ');

  return (
    <div
      className={rowClasses}
      style={{
        top,
        height: ROW_HEIGHT,
        gridTemplateColumns: COLUMN_TEMPLATE,
      }}
      onClick={onClick}
    >
      <div className="px-2 border-r border-light-100 text-light-700 tabular-nums truncate">
        {ev.timestamp ? formatTs(ev.timestamp) : '—'}
      </div>
      <div className="px-2 border-r border-light-100 flex items-center gap-1.5 truncate">
        <span
          className="w-2 h-2 rounded-full flex-shrink-0"
          style={{ backgroundColor: color }}
        />
        <Icon className="w-3 h-3 flex-shrink-0" style={{ color }} />
        <span className="truncate text-light-800">
          {EVENT_LABELS[ev.event_type] || ev.event_type}
        </span>
      </div>
      <div className="px-2 border-r border-light-100 text-light-700 truncate" title={deviceLabel}>
        {deviceLabel || ev.device_report_key || '—'}
      </div>
      <div className="px-2 border-r border-light-100 text-light-900 truncate" title={label}>
        {label}
      </div>
      <div className="px-2 border-r border-light-100 text-light-700 truncate" title={senderName}>
        {senderName || '—'}
      </div>
      <div className="px-2 border-r border-light-100 text-light-700 truncate" title={recipientName}>
        {recipientName || '—'}
      </div>
      <div
        className="px-2 border-r border-light-100 text-light-600 truncate"
        title={ev.summary || ''}
      >
        {ev.summary || ''}
      </div>
      <div className="px-2 flex items-center justify-end gap-1 text-[10px] text-light-500 tabular-nums">
        {hasGeo ? (
          <>
            <MapPin className="w-2.5 h-2.5" />
            <span>
              {Number(ev.latitude).toFixed(3)}, {Number(ev.longitude).toFixed(3)}
            </span>
          </>
        ) : (
          <span>—</span>
        )}
      </div>
    </div>
  );
});
