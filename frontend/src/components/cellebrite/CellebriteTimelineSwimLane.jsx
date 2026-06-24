/**
 * CellebriteTimelineSwimLane
 *
 * Alternative rendering of the Timeline events list — one swim-lane
 * per phone in the case, with every event placed on its lane by
 * timestamp. Two orientations:
 *
 *   - vertical  : phones are columns, time flows top → bottom
 *   - horizontal: phones are rows,    time flows left → right
 *
 * Extra features beyond the chronological list view:
 *
 *   1. Cross-phone link arcs — when a call/message/email's
 *      counterpart maps to another phone in the case (resolved via
 *      utils/crossPhoneResolver), we draw an SVG arc connecting the
 *      source event marker on lane A to the matching point on lane
 *      B's time axis. Hover an arc to see who → who; click to
 *      reveal the source event in the rail.
 *
 *   2. Drag-to-select — the investigator can drag a rectangular
 *      selection over the lane surface. The bounding box becomes a
 *      time window (and, for horizontal orientation, a phone-row
 *      window). A floating action bar then offers:
 *         · Apply as Timeline filter      (narrows the rest of the
 *           tab to the same window — no Cellebrite-tab change)
 *         · Open selection in Comms Center (writes a handoff payload
 *           via utils/commsHandoff, requests a tab switch).
 *
 * Inputs:
 *   - events      : pre-filtered events array from the parent
 *                   (already had event-type / search / scrubber
 *                   filters applied)
 *   - reports     : full reports list (phone identity lookup)
 *   - selectedReportKeys : Set<string> — phones currently visible.
 *                   Phones not in the set are hidden as lanes.
 *   - orientation : 'vertical' | 'horizontal'
 *   - onEventSelect(ev) : called when a marker is clicked
 *   - onApplyWindow({startTs, endTs, reportKeys}) : called when the
 *                   user picks "Apply as Timeline filter"
 *
 * Performance:
 *   - Markers are absolute-positioned divs; up to ~5000 per lane is
 *     fine. For larger spans the parent should already be windowing
 *     events by the global scrubber.
 *   - Link arcs are rendered in a single SVG overlay; up to ~500
 *     is comfortable.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Smartphone, ArrowRight, X, MessageSquareText, Filter } from 'lucide-react';
import PhoneIdentityChip from './shared/PhoneIdentityChip';
import { EVENT_COLORS, EVENT_ICONS, EVENT_LABELS, formatTs } from './events/eventUtils';
import { resolveCrossPhoneLinks } from '../../utils/crossPhoneResolver';
import { phoneHexByKey } from '../../utils/phoneIdentity';
import {
  setCommsHandoff,
  requestCellebriteTabSwitch,
} from '../../utils/commsHandoff';

// Pixel sizes for the lane geometry. Centralised so vertical /
// horizontal stay in sync.
const LANE_THICKNESS = 220; // column width (vertical) or row height (horizontal)
const LANE_HEADER_THICKNESS = 56;
const TIME_AXIS_THICKNESS = 64; // gutter holding tick labels
const MARKER_SIZE = 10;

export default function CellebriteTimelineSwimLane({
  caseId,
  events,
  reports,
  selectedReportKeys,
  orientation = 'vertical',
  onEventSelect,
  onApplyWindow,
}) {
  // -----------------------------------------------------------------
  // 1. Derive the active lanes — one per phone in selection that has
  //    at least one event in the current dataset. Skip silent phones
  //    rather than draw an empty lane (saves space when the
  //    investigator has 4 phones but only 2 had activity in window).
  // -----------------------------------------------------------------
  const lanes = useMemo(() => {
    const present = new Set();
    for (const ev of events) {
      if (ev?.device_report_key) present.add(ev.device_report_key);
    }
    const out = [];
    for (const r of reports) {
      if (!r?.report_key) continue;
      if (selectedReportKeys && selectedReportKeys.size > 0 &&
          !selectedReportKeys.has(r.report_key)) continue;
      if (!present.has(r.report_key)) continue;
      out.push({
        reportKey: r.report_key,
        report: r,
        color: phoneHexByKey(r.report_key, reports),
      });
    }
    // If selection allowed multiple phones but the data only spoke
    // about one, still show that single lane — but only if it has
    // events. (No lanes ⇒ caller shows an empty state.)
    return out;
  }, [events, reports, selectedReportKeys]);

  // -----------------------------------------------------------------
  // 2. Bucket events per lane + compute the global time range. We
  //    do both in one pass to keep the render path single-loop.
  // -----------------------------------------------------------------
  const { byLane, minMs, maxMs } = useMemo(() => {
    const map = new Map();
    let lo = Infinity;
    let hi = -Infinity;
    for (const ev of events) {
      const rk = ev?.device_report_key;
      if (!rk) continue;
      const ts = ev.timestamp ? new Date(ev.timestamp).getTime() : NaN;
      if (!Number.isFinite(ts)) continue;
      if (ts < lo) lo = ts;
      if (ts > hi) hi = ts;
      let arr = map.get(rk);
      if (!arr) {
        arr = [];
        map.set(rk, arr);
      }
      arr.push({ ev, ms: ts });
    }
    // Stable per-lane sort by time (older → newer); link arcs and
    // marker collision avoidance both rely on this.
    for (const arr of map.values()) arr.sort((a, b) => a.ms - b.ms);
    return {
      byLane: map,
      minMs: Number.isFinite(lo) ? lo : 0,
      maxMs: Number.isFinite(hi) ? hi : 0,
    };
  }, [events]);

  // -----------------------------------------------------------------
  // 3. Resolve cross-phone link arcs (call/message/email whose
  //    counterpart corresponds to another phone in the case).
  // -----------------------------------------------------------------
  const crossLinks = useMemo(
    () => resolveCrossPhoneLinks(events, reports),
    [events, reports],
  );

  // Pre-index each event's lane position so the arc layer can look
  // up two endpoints in O(1) per link without re-scanning byLane.
  const eventLaneIndex = useMemo(() => {
    const map = new Map(); // event_id -> { reportKey, ms }
    for (const [rk, arr] of byLane.entries()) {
      for (const { ev, ms } of arr) {
        const k = ev.id || ev.node_key;
        if (k) map.set(k, { reportKey: rk, ms });
      }
    }
    return map;
  }, [byLane]);

  // -----------------------------------------------------------------
  // 4. Layout. We size the time axis with a fixed pixel-per-hour
  //    density so very long datasets get a scrollbar rather than
  //    cramming everything into the viewport. Density adapts to the
  //    range: short windows zoom in, multi-month windows compress.
  // -----------------------------------------------------------------
  const rangeMs = Math.max(maxMs - minMs, 60_000); // never zero
  const PX_PER_HOUR = chooseDensity(rangeMs);
  const timeAxisPx = Math.max(
    600,
    Math.round((rangeMs / 3_600_000) * PX_PER_HOUR),
  );

  // -----------------------------------------------------------------
  // 5. Drag-to-select state. Coordinates are stored in the SAME
  //    space as `surfaceRef`, i.e. the inner scrollable container,
  //    so we don't have to factor scrolling into the math.
  // -----------------------------------------------------------------
  const surfaceRef = useRef(null);
  const [drag, setDrag] = useState(null); // { startX, startY, curX, curY }
  const [committedBox, setCommittedBox] = useState(null);

  const onMouseDown = useCallback((e) => {
    // Only left-click; ignore if started on an interactive child
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
    // Ignore micro-drags (treat as clicks)
    if (dx < 6 && dy < 6) {
      setDrag(null);
      return;
    }
    setCommittedBox({
      x1: Math.min(drag.startX, drag.curX),
      y1: Math.min(drag.startY, drag.curY),
      x2: Math.max(drag.startX, drag.curX),
      y2: Math.max(drag.startY, drag.curY),
    });
    setDrag(null);
  }, [drag]);

  // Translate a committed box → time window + phone-key window.
  // The lane/time math is orientation-aware so the same helper
  // serves both layouts.
  const selectionWindow = useMemo(() => {
    if (!committedBox) return null;
    const { x1, y1, x2, y2 } = committedBox;
    if (orientation === 'vertical') {
      // Time runs down the y-axis from minMs at top to maxMs at bottom.
      const a = pxToTime(y1, timeAxisPx, minMs, maxMs);
      const b = pxToTime(y2, timeAxisPx, minMs, maxMs);
      // Degenerate data (empty set / zero-height axis) makes a/b NaN, and
      // new Date(NaN).toISOString() THROWS — guard so a drag-select doesn't
      // crash the tab.
      if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
      const startTs = new Date(Math.min(a, b)).toISOString();
      const endTs = new Date(Math.max(a, b)).toISOString();
      // Phone lanes run along x. Each lane occupies a slot of
      // LANE_THICKNESS pixels starting after TIME_AXIS_THICKNESS.
      const x1Local = Math.max(0, x1 - TIME_AXIS_THICKNESS);
      const x2Local = Math.max(0, x2 - TIME_AXIS_THICKNESS);
      const i1 = Math.max(0, Math.floor(x1Local / LANE_THICKNESS));
      const i2 = Math.min(lanes.length - 1, Math.floor(x2Local / LANE_THICKNESS));
      const reportKeys = lanes.slice(i1, i2 + 1).map((l) => l.reportKey);
      return { startTs, endTs, reportKeys };
    }
    // horizontal
    const a = pxToTime(x1 - LANE_HEADER_THICKNESS, timeAxisPx, minMs, maxMs);
    const b = pxToTime(x2 - LANE_HEADER_THICKNESS, timeAxisPx, minMs, maxMs);
    if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
    const startTs = new Date(Math.min(a, b)).toISOString();
    const endTs = new Date(Math.max(a, b)).toISOString();
    const i1 = Math.max(0, Math.floor(y1 / LANE_THICKNESS));
    const i2 = Math.min(lanes.length - 1, Math.floor(y2 / LANE_THICKNESS));
    const reportKeys = lanes.slice(i1, i2 + 1).map((l) => l.reportKey);
    return { startTs, endTs, reportKeys };
  }, [committedBox, orientation, lanes, minMs, maxMs, timeAxisPx]);

  // -----------------------------------------------------------------
  // 6. Rendering.
  //
  // Vertical layout:
  //   ┌─────────┬────────────────┬────────────────┐
  //   │ (time)  │  Lane: P1      │  Lane: P2      │
  //   │ 00:00   │  · · · · ●     │  · ●           │
  //   │ 01:00   │      ●         │  ● · · ●       │
  //   │ ...     │                │                │
  //   └─────────┴────────────────┴────────────────┘
  //
  // Horizontal layout flips the same grid by 90°.
  //
  // Both share the same drag overlay + link-arc SVG and the same
  // floating action bar at the bottom.
  // -----------------------------------------------------------------
  if (lanes.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-light-500 italic">
        No phone activity in the current window. Adjust filters or add more phones.
      </div>
    );
  }

  // Floating action bar visibility — only when we have a committed box
  const showActionBar = selectionWindow != null;

  return (
    <div className="flex-1 min-h-0 flex flex-col relative">
      <div
        ref={surfaceRef}
        className="relative flex-1 min-h-0 overflow-auto select-none cursor-crosshair bg-light-50"
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={() => { if (drag) setDrag(null); }}
      >
        {orientation === 'vertical' ? (
          <VerticalLanes
            lanes={lanes}
            byLane={byLane}
            minMs={minMs}
            maxMs={maxMs}
            timeAxisPx={timeAxisPx}
            onEventSelect={onEventSelect}
            crossLinks={crossLinks}
            eventLaneIndex={eventLaneIndex}
          />
        ) : (
          <HorizontalLanes
            lanes={lanes}
            byLane={byLane}
            minMs={minMs}
            maxMs={maxMs}
            timeAxisPx={timeAxisPx}
            onEventSelect={onEventSelect}
            crossLinks={crossLinks}
            eventLaneIndex={eventLaneIndex}
          />
        )}

        {/* Drag preview rectangle */}
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
        {/* Committed box (until cleared) — outlined so the user
            keeps spatial context while reading the action bar. */}
        {committedBox && (
          <div
            className="pointer-events-none absolute border-2 border-amber-500 bg-amber-500/10 rounded-sm"
            style={{
              left: committedBox.x1,
              top: committedBox.y1,
              width: committedBox.x2 - committedBox.x1,
              height: committedBox.y2 - committedBox.y1,
            }}
          />
        )}
      </div>

      {showActionBar && (
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
            onClick={() => {
              setCommsHandoff({
                caseId,
                startTs: selectionWindow.startTs,
                endTs: selectionWindow.endTs,
                reportKeys: selectionWindow.reportKeys,
                source: 'swim-lane',
              });
              requestCellebriteTabSwitch('comms');
              setCommittedBox(null);
            }}
            className="inline-flex items-center gap-1 px-2 py-1 rounded bg-emerald-600 text-white hover:bg-emerald-700"
          >
            <MessageSquareText className="w-3 h-3" />
            Open in Communications
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

/* ───────────────────────── Vertical layout ───────────────────────── */

function VerticalLanes({
  lanes, byLane, minMs, maxMs, timeAxisPx,
  onEventSelect, crossLinks, eventLaneIndex,
}) {
  const ticks = useMemo(
    () => generateTicks(minMs, maxMs, timeAxisPx, 'vertical'),
    [minMs, maxMs, timeAxisPx],
  );
  // Total width = time-axis gutter + N lanes
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

      {/* Time-axis ticks */}
      <div
        className="absolute left-0 right-0 bg-light-50 border-r border-light-200"
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
        const events = byLane.get(l.reportKey) || [];
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
            {/* horizontal tick guide-lines */}
            {ticks.map((t) => (
              <div
                key={t.ms}
                className="absolute left-0 right-0 border-t border-dashed border-light-100"
                style={{ top: t.px }}
              />
            ))}
            {/* Event markers */}
            {events.map(({ ev, ms }) => {
              const py = timeToPx(ms, timeAxisPx, minMs, maxMs);
              const px = computeMarkerX(LANE_THICKNESS, ev.event_type);
              return (
                <EventMarker
                  key={ev.id || ev.node_key}
                  ev={ev}
                  x={px} y={py}
                  onSelect={onEventSelect}
                />
              );
            })}
          </div>
        );
      })}

      {/* Cross-phone link arcs — single SVG overlay sitting above
          lane bodies but below the action bar. */}
      <svg
        className="absolute pointer-events-none"
        style={{
          left: TIME_AXIS_THICKNESS, top: LANE_HEADER_THICKNESS,
          width: lanes.length * LANE_THICKNESS, height: timeAxisPx,
        }}
      >
        {crossLinks.map((link, i) => {
          const a = eventLaneIndex.get(link.id);
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
              stroke={EVENT_COLORS[link.event_type] || '#94a3b8'}
              strokeWidth="1.5"
              strokeOpacity="0.65"
              data-swim-link={link.id}
            />
          );
        })}
      </svg>
    </div>
  );
}

/* ───────────────────────── Horizontal layout ─────────────────────── */

function HorizontalLanes({
  lanes, byLane, minMs, maxMs, timeAxisPx,
  onEventSelect, crossLinks, eventLaneIndex,
}) {
  const ticks = useMemo(
    () => generateTicks(minMs, maxMs, timeAxisPx, 'horizontal'),
    [minMs, maxMs, timeAxisPx],
  );
  const totalW = LANE_HEADER_THICKNESS + timeAxisPx;
  const totalH = TIME_AXIS_THICKNESS + lanes.length * LANE_THICKNESS;

  return (
    <div className="relative" style={{ width: totalW, height: totalH }}>
      {/* Top time-axis ticks */}
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

      {/* Lane bodies */}
      {lanes.map((l, laneIdx) => {
        const top = TIME_AXIS_THICKNESS + laneIdx * LANE_THICKNESS;
        const events = byLane.get(l.reportKey) || [];
        return (
          <React.Fragment key={l.reportKey}>
            {/* Header (left gutter) */}
            <div
              className="absolute left-0 flex items-center gap-2 px-2 border-r border-light-200 bg-white z-10"
              style={{
                top, width: LANE_HEADER_THICKNESS, height: LANE_THICKNESS,
                borderLeft: `3px solid ${l.color}`,
              }}
            >
              <PhoneIdentityChip reportKey={l.reportKey} variant="default" />
            </div>
            {/* Body */}
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
              {events.map(({ ev, ms }) => {
                const px = timeToPx(ms, timeAxisPx, minMs, maxMs);
                const py = computeMarkerX(LANE_THICKNESS, ev.event_type);
                return (
                  <EventMarker
                    key={ev.id || ev.node_key}
                    ev={ev}
                    x={px} y={py}
                    onSelect={onEventSelect}
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
          const a = eventLaneIndex.get(link.id);
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
              stroke={EVENT_COLORS[link.event_type] || '#94a3b8'}
              strokeWidth="1.5"
              strokeOpacity="0.65"
              data-swim-link={link.id}
            />
          );
        })}
      </svg>
    </div>
  );
}

/* ─────────────────────────── Bits & pieces ───────────────────────── */

function EventMarker({ ev, x, y, onSelect }) {
  const Icon = EVENT_ICONS[ev.event_type] || EVENT_ICONS.location;
  const color = EVENT_COLORS[ev.event_type] || '#64748b';
  const title = `${EVENT_LABELS[ev.event_type] || ev.event_type} · ${formatTs(ev.timestamp)}\n${ev.summary || ''}`.trim();
  return (
    <button
      type="button"
      data-swim-marker
      onClick={(e) => {
        e.stopPropagation();
        if (onSelect) onSelect(ev);
      }}
      title={title}
      className="absolute rounded-full flex items-center justify-center hover:scale-125 transition-transform"
      style={{
        left: x - MARKER_SIZE / 2,
        top: y - MARKER_SIZE / 2,
        width: MARKER_SIZE,
        height: MARKER_SIZE,
        background: color,
        boxShadow: '0 0 0 2px white',
      }}
    >
      <Icon className="w-2 h-2 text-white" />
    </button>
  );
}

function chooseDensity(rangeMs) {
  // Aim for a reasonable screen-fit even on long ranges. Roughly
  // 1 day → ~480px (so a week fills a wide laptop), 30 days → ~80
  // per day still fits in a vertical scroll.
  const days = rangeMs / 86_400_000;
  if (days <= 1) return 80;        // 80px/hour, ~2000px/day
  if (days <= 7) return 20;        // 20px/hour
  if (days <= 30) return 6;
  if (days <= 180) return 1.5;
  return 0.5;
}

function generateTicks(minMs, maxMs, timeAxisPx, orientation) {
  const range = Math.max(maxMs - minMs, 1);
  const days = range / 86_400_000;
  let step;
  if (days <= 1) step = 3_600_000;          // 1 hour
  else if (days <= 7) step = 6 * 3_600_000; // 6 hours
  else if (days <= 30) step = 86_400_000;   // 1 day
  else if (days <= 180) step = 7 * 86_400_000; // 1 week
  else step = 30 * 86_400_000;
  const out = [];
  let t = Math.ceil(minMs / step) * step;
  while (t <= maxMs && out.length < 60) {
    out.push({
      ms: t,
      px: timeToPx(t, timeAxisPx, minMs, maxMs),
      label: fmtTick(t, days, orientation),
    });
    t += step;
  }
  return out;
}

function fmtTick(ms, daysSpan, _orientation) {
  const d = new Date(ms);
  if (daysSpan <= 1) {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  if (daysSpan <= 7) {
    return d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit' });
  }
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

/**
 * Stable x-offset inside a lane (or y-offset for the horizontal
 * variant) so different event types don't pile on the same pixel
 * column when timestamps cluster. We pick a column per event-type
 * so visually-similar events stay aligned.
 */
function computeMarkerX(laneThickness, eventType) {
  const slots = [
    'location', 'cell_tower', 'wifi', 'call', 'message',
    'email', 'power', 'device_event', 'app_session',
    'search', 'visit', 'meeting',
  ];
  const i = Math.max(0, slots.indexOf(eventType));
  const colWidth = laneThickness / (slots.length + 1);
  return Math.round((i + 1) * colWidth);
}

function fmtRange(startIso, endIso) {
  try {
    const a = new Date(startIso);
    const b = new Date(endIso);
    if (isNaN(a.getTime()) || isNaN(b.getTime())) return '—';
    const sameDay =
      a.toDateString() === b.toDateString();
    const dStr = (d) => d.toLocaleString([], {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
    if (sameDay) {
      return `${dStr(a)} → ${b.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    }
    return `${dStr(a)} → ${dStr(b)}`;
  } catch {
    return '—';
  }
}
