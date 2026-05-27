/**
 * Conversation Timeline — swim-lane renderer.
 *
 * Sibling to CommsCrossTypeTimeline. Same data shape (the items array
 * returned by `cellebriteCommsAPI.getBetween(...)`), different layout:
 * one lane per phone, each message/call/email plotted on the lane at
 * its timestamp. Cross-phone link arcs are drawn when a comm's
 * counterpart (recipient phone, sender phone, etc.) matches the owner
 * of another lane.
 *
 * Vertical orientation places phones as columns, time top→bottom.
 * Horizontal orientation places phones as rows, time left→right.
 *
 * Drag-to-select supports two follow-up actions:
 *   - Apply window  → narrows the parent comms scrubber (start/end)
 *   - Open in Comms → no-op here (we ARE already in Comms); instead
 *                     this fires the parent thread-filter so the open
 *                     conversation pane jumps to the selected window.
 *
 * Lives inside the existing conversation-timeline flyover, accessed
 * via a List | Lanes ↓ | Lanes → toggle in the flyover header.
 */

import React, { useCallback, useMemo, useRef, useState } from 'react';
import { Phone, Mail, MessageSquare, Filter, MessageSquareText, X, Smartphone } from 'lucide-react';
import PhoneIdentityChip from '../shared/PhoneIdentityChip';
import { usePhoneReports } from '../../../context/PhoneReportsContext';
import { phoneHexByKey } from '../../../utils/phoneIdentity';
import { resolveCrossPhoneLinks } from '../../../utils/crossPhoneResolver';

const LANE_THICKNESS = 200;
const LANE_HEADER_THICKNESS = 56;
const TIME_AXIS_THICKNESS = 60;
const MARKER_SIZE = 10;

const TYPE_COLORS = {
  message: '#2563eb', // owl-blue-600
  call: '#10b981',    // emerald-500
  email: '#f59e0b',   // amber-500
};
const TYPE_ICONS = {
  message: MessageSquare,
  call: Phone,
  email: Mail,
};

export default function CommsCrossTypeSwimLane({
  items,
  orientation = 'vertical',
  onItemSelect,
  onApplyWindow,
  // Pagination / progressive loading. When `hasMore` is true the
  // surface fires `onLoadMore` as the user scrolls near the temporal
  // bottom of the lane area. `totalAvailable` and `loadedCount`
  // drive the "X of Y loaded" hint at the bottom.
  hasMore = false,
  loadingMore = false,
  onLoadMore = null,
  totalAvailable = null,
  loadedCount = null,
  // Optional: phones the user explicitly has selected. When provided,
  // EVERY selected phone gets a lane (even those with no items in the
  // current load) so users see lane chrome + a "no activity loaded
  // yet" placeholder instead of silently vanishing lanes.
  expectedReportKeys = null,
}) {
  const phoneCtx = usePhoneReports();
  const reports = phoneCtx?.reports || [];

  // Map a comms feed item into the shape the cross-phone resolver
  // expects (it was built for the Timeline events feed and keys off
  // `device_report_key` + `counterpart`/`recipients`/`sender`). The
  // comms feed already supplies all of these — we just rename
  // `report_key` to `device_report_key` so the resolver finds it.
  const itemsForResolver = useMemo(() => items.map((it) => ({
    ...it,
    device_report_key: it.report_key,
    event_type: it.type, // resolver only acts on call/message/email
  })), [items]);

  // -----------------------------------------------------------------
  // Lanes — one per active phone.
  //
  // Selection rule (in priority order):
  //   1. If `expectedReportKeys` is supplied, render exactly those
  //      lanes — even ones with no items yet. The parent uses this
  //      to keep every selected phone visible while pagination /
  //      per-phone seeding fills them in.
  //   2. Otherwise render lanes for phones that own at least one
  //      item in the current feed (legacy behaviour).
  //   3. Final fallback: derive lanes from item.report_key values
  //      when no phoneCtx is available.
  // -----------------------------------------------------------------
  const lanes = useMemo(() => {
    const present = new Set();
    for (const it of items) {
      if (it?.report_key) present.add(it.report_key);
    }
    const expected = Array.isArray(expectedReportKeys) ? expectedReportKeys
      : (expectedReportKeys && typeof expectedReportKeys[Symbol.iterator] === 'function'
          ? [...expectedReportKeys]
          : null);

    const out = [];
    if (expected && expected.length > 0) {
      for (const rk of expected) {
        const r = reports.find((rr) => rr?.report_key === rk) || { report_key: rk };
        out.push({
          reportKey: rk,
          report: r,
          color: phoneHexByKey(rk, reports),
          hasItems: present.has(rk),
        });
      }
      return out;
    }

    for (const r of reports) {
      if (!r?.report_key) continue;
      if (!present.has(r.report_key)) continue;
      out.push({
        reportKey: r.report_key,
        report: r,
        color: phoneHexByKey(r.report_key, reports),
        hasItems: true,
      });
    }
    if (out.length === 0) {
      for (const rk of present) {
        out.push({ reportKey: rk, report: { report_key: rk }, color: '#94a3b8', hasItems: true });
      }
    }
    return out;
  }, [items, reports, expectedReportKeys]);

  const { byLane, minMs, maxMs } = useMemo(() => {
    const map = new Map();
    let lo = Infinity;
    let hi = -Infinity;
    for (const it of items) {
      const rk = it?.report_key;
      if (!rk) continue;
      const ts = it.timestamp ? new Date(it.timestamp).getTime() : NaN;
      if (!Number.isFinite(ts)) continue;
      if (ts < lo) lo = ts;
      if (ts > hi) hi = ts;
      let arr = map.get(rk);
      if (!arr) { arr = []; map.set(rk, arr); }
      arr.push({ it, ms: ts });
    }
    for (const arr of map.values()) arr.sort((a, b) => a.ms - b.ms);
    return {
      byLane: map,
      minMs: Number.isFinite(lo) ? lo : 0,
      maxMs: Number.isFinite(hi) ? hi : 0,
    };
  }, [items]);

  const crossLinks = useMemo(
    () => resolveCrossPhoneLinks(itemsForResolver, reports),
    [itemsForResolver, reports],
  );

  const itemLaneIndex = useMemo(() => {
    const map = new Map();
    for (const [rk, arr] of byLane.entries()) {
      for (const { it, ms } of arr) {
        const k = it.id || it.key;
        if (k) map.set(k, { reportKey: rk, ms });
      }
    }
    return map;
  }, [byLane]);

  const rangeMs = Math.max(maxMs - minMs, 60_000);
  const PX_PER_HOUR = chooseDensity(rangeMs);
  const timeAxisPx = Math.max(
    420,
    Math.round((rangeMs / 3_600_000) * PX_PER_HOUR),
  );

  // -----------------------------------------------------------------
  // Drag-to-select (same shape as the Timeline-tab swim-lane).
  // -----------------------------------------------------------------
  const surfaceRef = useRef(null);
  const [drag, setDrag] = useState(null);
  const [committedBox, setCommittedBox] = useState(null);

  const onMouseDown = useCallback((e) => {
    if (e.button !== 0) return;
    if (e.target.closest('[data-swim-marker]')) return;
    if (e.target.closest('[data-swim-link]')) return;
    const r = surfaceRef.current?.getBoundingClientRect();
    if (!r) return;
    const x = e.clientX - r.left + (surfaceRef.current?.scrollLeft || 0);
    const y = e.clientY - r.top + (surfaceRef.current?.scrollTop || 0);
    setDrag({ startX: x, startY: y, curX: x, curY: y });
    setCommittedBox(null);
  }, []);

  const onMouseMove = useCallback((e) => {
    if (!drag) return;
    const r = surfaceRef.current?.getBoundingClientRect();
    if (!r) return;
    const x = e.clientX - r.left + (surfaceRef.current?.scrollLeft || 0);
    const y = e.clientY - r.top + (surfaceRef.current?.scrollTop || 0);
    setDrag((d) => (d ? { ...d, curX: x, curY: y } : null));
  }, [drag]);

  const onMouseUp = useCallback(() => {
    if (!drag) return;
    const dx = Math.abs(drag.curX - drag.startX);
    const dy = Math.abs(drag.curY - drag.startY);
    if (dx < 6 && dy < 6) { setDrag(null); return; }
    setCommittedBox({
      x1: Math.min(drag.startX, drag.curX),
      y1: Math.min(drag.startY, drag.curY),
      x2: Math.max(drag.startX, drag.curX),
      y2: Math.max(drag.startY, drag.curY),
    });
    setDrag(null);
  }, [drag]);

  const selectionWindow = useMemo(() => {
    if (!committedBox) return null;
    const { x1, y1, x2, y2 } = committedBox;
    if (orientation === 'vertical') {
      const a = pxToTime(y1 - LANE_HEADER_THICKNESS, timeAxisPx, minMs, maxMs);
      const b = pxToTime(y2 - LANE_HEADER_THICKNESS, timeAxisPx, minMs, maxMs);
      const startTs = new Date(Math.min(a, b)).toISOString();
      const endTs = new Date(Math.max(a, b)).toISOString();
      const x1Local = Math.max(0, x1 - TIME_AXIS_THICKNESS);
      const x2Local = Math.max(0, x2 - TIME_AXIS_THICKNESS);
      const i1 = Math.max(0, Math.floor(x1Local / LANE_THICKNESS));
      const i2 = Math.min(lanes.length - 1, Math.floor(x2Local / LANE_THICKNESS));
      const reportKeys = lanes.slice(i1, i2 + 1).map((l) => l.reportKey);
      return { startTs, endTs, reportKeys };
    }
    const a = pxToTime(x1 - LANE_HEADER_THICKNESS, timeAxisPx, minMs, maxMs);
    const b = pxToTime(x2 - LANE_HEADER_THICKNESS, timeAxisPx, minMs, maxMs);
    const startTs = new Date(Math.min(a, b)).toISOString();
    const endTs = new Date(Math.max(a, b)).toISOString();
    const y1Local = Math.max(0, y1 - TIME_AXIS_THICKNESS);
    const y2Local = Math.max(0, y2 - TIME_AXIS_THICKNESS);
    const i1 = Math.max(0, Math.floor(y1Local / LANE_THICKNESS));
    const i2 = Math.min(lanes.length - 1, Math.floor(y2Local / LANE_THICKNESS));
    const reportKeys = lanes.slice(i1, i2 + 1).map((l) => l.reportKey);
    return { startTs, endTs, reportKeys };
  }, [committedBox, orientation, lanes, minMs, maxMs, timeAxisPx]);

  if (lanes.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center text-xs text-light-500 italic">
        No comms in the current window match the active filters.
      </div>
    );
  }

  // Infinite-scroll trigger — when the user nears the temporal edge
  // of the scroll surface (bottom for vertical, right for horizontal)
  // we fire onLoadMore to pull the next page. The library throttles
  // implicitly because React already coalesces fast scroll events.
  const onSurfaceScroll = useCallback((e) => {
    if (!hasMore || loadingMore || !onLoadMore) return;
    const el = e.currentTarget;
    const THRESHOLD = 120;
    if (orientation === 'vertical') {
      const dist = (el.scrollHeight - (el.scrollTop + el.clientHeight));
      if (dist < THRESHOLD) onLoadMore();
    } else {
      const dist = (el.scrollWidth - (el.scrollLeft + el.clientWidth));
      if (dist < THRESHOLD) onLoadMore();
    }
  }, [hasMore, loadingMore, onLoadMore, orientation]);

  return (
    <div className="flex-1 min-h-0 flex flex-col relative">
      <div
        ref={surfaceRef}
        className="relative flex-1 min-h-0 overflow-auto select-none cursor-crosshair bg-light-50"
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={() => { if (drag) setDrag(null); }}
        onScroll={onSurfaceScroll}
      >
        {orientation === 'vertical' ? (
          <VerticalCommsLanes
            lanes={lanes} byLane={byLane}
            minMs={minMs} maxMs={maxMs} timeAxisPx={timeAxisPx}
            onItemSelect={onItemSelect}
            crossLinks={crossLinks} itemLaneIndex={itemLaneIndex}
          />
        ) : (
          <HorizontalCommsLanes
            lanes={lanes} byLane={byLane}
            minMs={minMs} maxMs={maxMs} timeAxisPx={timeAxisPx}
            onItemSelect={onItemSelect}
            crossLinks={crossLinks} itemLaneIndex={itemLaneIndex}
          />
        )}

        {drag && (
          <div
            className="pointer-events-none absolute border-2 border-owl-blue-500 bg-owl-blue-500/10 rounded-sm"
            style={{
              left: Math.min(drag.startX, drag.curX),
              top: Math.min(drag.startY, drag.curY),
              width: Math.abs(drag.curX - drag.startX),
              height: Math.abs(drag.curY - drag.startY),
            }}
          />
        )}
        {committedBox && (
          <div
            className="pointer-events-none absolute border-2 border-amber-500 bg-amber-500/10 rounded-sm"
            style={{
              left: committedBox.x1, top: committedBox.y1,
              width: committedBox.x2 - committedBox.x1,
              height: committedBox.y2 - committedBox.y1,
            }}
          />
        )}

        {/* Progressive-load status pill — sticks to the bottom-right
            of the surface so it doesn't fight the action bar that
            sits centred above. Three states:
              · loading more — spinner + count
              · more available, idle — hint to scroll
              · all loaded — quiet confirmation
            Always shows the "X of Y loaded" counter when totals exist. */}
        {(loadedCount != null && totalAvailable != null) && (
          <div className="pointer-events-none absolute bottom-2 right-3 z-20 text-[11px] bg-white/90 border border-light-200 rounded-full px-2 py-0.5 shadow-sm text-light-700 tabular-nums">
            {loadingMore && (
              <span className="inline-flex items-center gap-1 text-owl-blue-700">
                <span className="inline-block w-2 h-2 border border-owl-blue-500 border-t-transparent rounded-full animate-spin" />
                loading more…
              </span>
            )}
            {!loadingMore && (
              <span>
                <span className="font-medium">{loadedCount.toLocaleString()}</span>
                {' of '}
                <span>{totalAvailable.toLocaleString()}</span>
                {' loaded'}
                {hasMore ? ' · scroll for more' : ' · all loaded'}
              </span>
            )}
          </div>
        )}
      </div>

      {selectionWindow && (
        <div className="absolute bottom-3 left-1/2 -translate-x-1/2 z-30 flex items-center gap-2 px-3 py-2 bg-white border border-light-300 shadow-lg rounded-full text-xs">
          <span className="text-light-600">Selection:</span>
          <span className="font-medium text-light-900">
            {selectionWindow.reportKeys.length} phone
            {selectionWindow.reportKeys.length === 1 ? '' : 's'}
            {' · '}
            {fmtRange(selectionWindow.startTs, selectionWindow.endTs)}
          </span>
          <button
            type="button"
            onClick={() => {
              if (onApplyWindow) onApplyWindow(selectionWindow);
              setCommittedBox(null);
            }}
            className="ml-2 inline-flex items-center gap-1 px-2 py-1 rounded bg-owl-blue-600 text-white hover:bg-owl-blue-700"
          >
            <Filter className="w-3 h-3" />
            Apply as filter
          </button>
          <button
            type="button"
            onClick={() => setCommittedBox(null)}
            className="inline-flex items-center justify-center w-5 h-5 rounded-full hover:bg-light-100 text-light-500"
            aria-label="Dismiss selection"
          >
            <X className="w-3 h-3" />
          </button>
        </div>
      )}
    </div>
  );
}

/* ─────────────────────── Vertical layout ─────────────────────── */

function VerticalCommsLanes({
  lanes, byLane, minMs, maxMs, timeAxisPx,
  onItemSelect, crossLinks, itemLaneIndex,
}) {
  const ticks = useMemo(
    () => generateTicks(minMs, maxMs, timeAxisPx),
    [minMs, maxMs, timeAxisPx],
  );
  const totalW = TIME_AXIS_THICKNESS + lanes.length * LANE_THICKNESS;
  const totalH = LANE_HEADER_THICKNESS + timeAxisPx;

  return (
    <div className="relative" style={{ width: totalW, height: totalH }}>
      {/* Lane headers */}
      <div
        className="absolute left-0 top-0 right-0 bg-white border-b border-light-200 z-20"
        style={{ height: LANE_HEADER_THICKNESS }}
      >
        <div className="flex h-full">
          <div
            className="border-r border-light-200 flex items-center justify-center text-[10px] text-light-500"
            style={{ width: TIME_AXIS_THICKNESS }}
          >
            time
          </div>
          {lanes.map((l) => (
            <div
              key={l.reportKey}
              className="border-r border-light-200 flex items-center gap-2 px-2"
              style={{ width: LANE_THICKNESS, borderTop: `3px solid ${l.color}` }}
            >
              <Smartphone className="w-3 h-3" style={{ color: l.color }} />
              <PhoneIdentityChip reportKey={l.reportKey} variant="default" />
            </div>
          ))}
        </div>
      </div>

      {/* Time axis */}
      <div
        className="absolute left-0 bg-light-50 border-r border-light-200"
        style={{
          top: LANE_HEADER_THICKNESS, width: TIME_AXIS_THICKNESS, height: timeAxisPx,
        }}
      >
        {ticks.map((t) => (
          <div
            key={t.ms}
            className="absolute left-0 right-0 px-1 text-[10px] text-light-500"
            style={{ top: t.px }}
          >
            <div className="border-t border-light-200" />
            <div className="pt-0.5 tabular-nums">{t.label}</div>
          </div>
        ))}
      </div>

      {/* Lane bodies */}
      {lanes.map((l, laneIdx) => {
        const left = TIME_AXIS_THICKNESS + laneIdx * LANE_THICKNESS;
        const arr = byLane.get(l.reportKey) || [];
        return (
          <div
            key={l.reportKey}
            className="absolute border-r border-light-100"
            style={{
              left, top: LANE_HEADER_THICKNESS,
              width: LANE_THICKNESS, height: timeAxisPx,
              background:
                laneIdx % 2 === 0 ? 'rgba(255,255,255,0.5)' : 'rgba(248,250,252,0.5)',
            }}
          >
            {ticks.map((t) => (
              <div
                key={t.ms}
                className="absolute left-0 right-0 border-t border-dashed border-light-100"
                style={{ top: t.px }}
              />
            ))}
            {arr.map(({ it, ms }) => {
              const py = timeToPx(ms, timeAxisPx, minMs, maxMs);
              const px = computeMarkerX(LANE_THICKNESS, it.type);
              return (
                <CommMarker
                  key={it.id || it.key}
                  item={it} x={px} y={py}
                  onSelect={onItemSelect}
                />
              );
            })}
          </div>
        );
      })}

      {/* Cross-phone link arcs */}
      <svg
        className="absolute pointer-events-none"
        style={{
          left: TIME_AXIS_THICKNESS, top: LANE_HEADER_THICKNESS,
          width: lanes.length * LANE_THICKNESS, height: timeAxisPx,
        }}
      >
        {crossLinks.map((link, i) => {
          const a = itemLaneIndex.get(link.id);
          if (!a) return null;
          const fromIdx = lanes.findIndex((l) => l.reportKey === link.from_report_key);
          const toIdx = lanes.findIndex((l) => l.reportKey === link.to_report_key);
          if (fromIdx === -1 || toIdx === -1) return null;
          const y = timeToPx(a.ms, timeAxisPx, minMs, maxMs);
          const x1 = fromIdx * LANE_THICKNESS + LANE_THICKNESS / 2;
          const x2 = toIdx * LANE_THICKNESS + LANE_THICKNESS / 2;
          const midX = (x1 + x2) / 2;
          const curve = Math.min(60, Math.abs(x2 - x1) / 3);
          const path = `M ${x1} ${y} C ${midX} ${y - curve}, ${midX} ${y - curve}, ${x2} ${y}`;
          return (
            <path
              key={`${link.id}-${i}`}
              d={path}
              fill="none"
              stroke={TYPE_COLORS[link.event_type] || '#94a3b8'}
              strokeWidth="1.5"
              strokeOpacity="0.7"
              data-swim-link={link.id}
            />
          );
        })}
      </svg>
    </div>
  );
}

/* ────────────────────── Horizontal layout ────────────────────── */

function HorizontalCommsLanes({
  lanes, byLane, minMs, maxMs, timeAxisPx,
  onItemSelect, crossLinks, itemLaneIndex,
}) {
  const ticks = useMemo(
    () => generateTicks(minMs, maxMs, timeAxisPx),
    [minMs, maxMs, timeAxisPx],
  );
  const totalW = LANE_HEADER_THICKNESS + timeAxisPx;
  const totalH = TIME_AXIS_THICKNESS + lanes.length * LANE_THICKNESS;

  return (
    <div className="relative" style={{ width: totalW, height: totalH }}>
      {/* Top time-axis */}
      <div
        className="absolute top-0 right-0 bg-white border-b border-light-200 z-20"
        style={{
          left: LANE_HEADER_THICKNESS, height: TIME_AXIS_THICKNESS, width: timeAxisPx,
        }}
      >
        {ticks.map((t) => (
          <div
            key={t.ms}
            className="absolute top-0 bottom-0 px-1 text-[10px] text-light-500 tabular-nums"
            style={{ left: t.px, transform: 'translateX(-50%)' }}
          >
            <div className="border-l border-light-200 h-full" />
            <div className="absolute top-1 left-1 whitespace-nowrap">{t.label}</div>
          </div>
        ))}
      </div>

      {lanes.map((l, laneIdx) => {
        const top = TIME_AXIS_THICKNESS + laneIdx * LANE_THICKNESS;
        const arr = byLane.get(l.reportKey) || [];
        return (
          <React.Fragment key={l.reportKey}>
            <div
              className="absolute left-0 flex items-center gap-2 px-2 border-r border-light-200 bg-white z-10"
              style={{
                top, width: LANE_HEADER_THICKNESS, height: LANE_THICKNESS,
                borderLeft: `3px solid ${l.color}`,
              }}
            >
              <PhoneIdentityChip reportKey={l.reportKey} variant="default" />
            </div>
            <div
              className="absolute border-b border-light-100"
              style={{
                left: LANE_HEADER_THICKNESS, top,
                width: timeAxisPx, height: LANE_THICKNESS,
                background:
                  laneIdx % 2 === 0 ? 'rgba(255,255,255,0.5)' : 'rgba(248,250,252,0.5)',
              }}
            >
              {ticks.map((t) => (
                <div
                  key={t.ms}
                  className="absolute top-0 bottom-0 border-l border-dashed border-light-100"
                  style={{ left: t.px }}
                />
              ))}
              {arr.map(({ it, ms }) => {
                const px = timeToPx(ms, timeAxisPx, minMs, maxMs);
                const py = computeMarkerX(LANE_THICKNESS, it.type);
                return (
                  <CommMarker
                    key={it.id || it.key}
                    item={it} x={px} y={py}
                    onSelect={onItemSelect}
                  />
                );
              })}
            </div>
          </React.Fragment>
        );
      })}

      <svg
        className="absolute pointer-events-none"
        style={{
          left: LANE_HEADER_THICKNESS, top: TIME_AXIS_THICKNESS,
          width: timeAxisPx, height: lanes.length * LANE_THICKNESS,
        }}
      >
        {crossLinks.map((link, i) => {
          const a = itemLaneIndex.get(link.id);
          if (!a) return null;
          const fromIdx = lanes.findIndex((l) => l.reportKey === link.from_report_key);
          const toIdx = lanes.findIndex((l) => l.reportKey === link.to_report_key);
          if (fromIdx === -1 || toIdx === -1) return null;
          const x = timeToPx(a.ms, timeAxisPx, minMs, maxMs);
          const y1 = fromIdx * LANE_THICKNESS + LANE_THICKNESS / 2;
          const y2 = toIdx * LANE_THICKNESS + LANE_THICKNESS / 2;
          const midY = (y1 + y2) / 2;
          const curve = Math.min(60, Math.abs(y2 - y1) / 3);
          const path = `M ${x} ${y1} C ${x + curve} ${midY}, ${x + curve} ${midY}, ${x} ${y2}`;
          return (
            <path
              key={`${link.id}-${i}`}
              d={path}
              fill="none"
              stroke={TYPE_COLORS[link.event_type] || '#94a3b8'}
              strokeWidth="1.5"
              strokeOpacity="0.7"
              data-swim-link={link.id}
            />
          );
        })}
      </svg>
    </div>
  );
}

/* ─────────────────────────── Pieces ─────────────────────────── */

function CommMarker({ item, x, y, onSelect }) {
  const Icon = TYPE_ICONS[item.type] || MessageSquare;
  const color = TYPE_COLORS[item.type] || '#64748b';
  const ts = item.timestamp
    ? new Date(item.timestamp).toLocaleString([], {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
      })
    : '';
  const from = item.sender?.name || '?';
  const to = (item.recipients && item.recipients[0]?.name) || '?';
  const preview = item.type === 'email' ? (item.subject || '') : (item.body || '');
  const title =
    `${item.type} · ${ts}\n${from} → ${to}\n${preview}`.trim();
  return (
    <button
      type="button"
      data-swim-marker
      onClick={(e) => { e.stopPropagation(); if (onSelect) onSelect(item); }}
      title={title}
      className="absolute rounded-full flex items-center justify-center hover:scale-125 transition-transform"
      style={{
        left: x - MARKER_SIZE / 2,
        top: y - MARKER_SIZE / 2,
        width: MARKER_SIZE, height: MARKER_SIZE,
        background: color, boxShadow: '0 0 0 2px white',
      }}
    >
      <Icon className="w-2 h-2 text-white" />
    </button>
  );
}

function chooseDensity(rangeMs) {
  const days = rangeMs / 86_400_000;
  if (days <= 1) return 80;
  if (days <= 7) return 20;
  if (days <= 30) return 6;
  if (days <= 180) return 1.5;
  return 0.5;
}

function generateTicks(minMs, maxMs, timeAxisPx) {
  const range = Math.max(maxMs - minMs, 1);
  const days = range / 86_400_000;
  let step;
  if (days <= 1) step = 3_600_000;
  else if (days <= 7) step = 6 * 3_600_000;
  else if (days <= 30) step = 86_400_000;
  else if (days <= 180) step = 7 * 86_400_000;
  else step = 30 * 86_400_000;
  const out = [];
  let t = Math.ceil(minMs / step) * step;
  while (t <= maxMs && out.length < 60) {
    out.push({
      ms: t,
      px: timeToPx(t, timeAxisPx, minMs, maxMs),
      label: fmtTick(t, days),
    });
    t += step;
  }
  return out;
}

function fmtTick(ms, daysSpan) {
  const d = new Date(ms);
  if (daysSpan <= 1) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  if (daysSpan <= 7) return d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit' });
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

function timeToPx(ms, axisPx, minMs, maxMs) {
  const range = Math.max(maxMs - minMs, 1);
  return ((ms - minMs) / range) * axisPx;
}
function pxToTime(px, axisPx, minMs, maxMs) {
  const range = maxMs - minMs;
  if (axisPx <= 0) return minMs;
  return minMs + (px / axisPx) * range;
}
function computeMarkerX(laneThickness, type) {
  const slots = ['message', 'call', 'email'];
  const i = Math.max(0, slots.indexOf(type));
  const colWidth = laneThickness / (slots.length + 1);
  return Math.round((i + 1) * colWidth);
}
function fmtRange(startIso, endIso) {
  try {
    const a = new Date(startIso);
    const b = new Date(endIso);
    if (isNaN(a.getTime()) || isNaN(b.getTime())) return '—';
    const sameDay = a.toDateString() === b.toDateString();
    const dStr = (d) => d.toLocaleString([], {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
    if (sameDay) {
      return `${dStr(a)} → ${b.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    }
    return `${dStr(a)} → ${dStr(b)}`;
  } catch { return '—'; }
}
