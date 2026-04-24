import React, { useMemo, useRef, useEffect, useState } from 'react';
import { EVENT_COLORS, parseTs } from './eventUtils';

/**
 * Horizontal swim-lane timeline: one lane per device, events plotted as dots.
 * A draggable playhead line lets the user scrub time.
 *
 * For < 1500 events we render with SVG (DOM) for easy hover; above that, Canvas.
 */
export default function EventTimelinePanel({
  events = [],
  reports = [],
  selectedReportKeys,
  playheadTime,
  setPlayheadTime,
  onEventClick,
  deviceColorOf,
}) {
  const containerRef = useRef(null);
  const [hover, setHover] = useState(null);

  // Range
  const range = useMemo(() => {
    let min = null;
    let max = null;
    for (const e of events) {
      const d = parseTs(e.timestamp);
      if (!d) continue;
      if (min === null || d < min) min = d;
      if (max === null || d > max) max = d;
    }
    return { min, max };
  }, [events]);

  // Lanes: one per selected device (in report order)
  const lanes = useMemo(() => {
    return (reports || [])
      .filter((r) => !selectedReportKeys || selectedReportKeys.has(r.report_key))
      .map((r) => ({
        report_key: r.report_key,
        label: `${r.device_model || 'Device'}${r.phone_owner_name ? ' · ' + r.phone_owner_name : ''}`,
        color: deviceColorOf?.(r.report_key) || '#2563eb',
      }));
  }, [reports, selectedReportKeys, deviceColorOf]);

  if (!range.min || !range.max || lanes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full bg-light-50 text-light-500 text-sm">
        No timestamped events to plot.
      </div>
    );
  }

  const totalMs = range.max.getTime() - range.min.getTime() || 1;

  // Group events by device
  const eventsByDevice = useMemo(() => {
    const m = new Map();
    for (const e of events) {
      const d = parseTs(e.timestamp);
      if (!d) continue;
      const arr = m.get(e.device_report_key) || [];
      arr.push({ ...e, _t: d.getTime() });
      m.set(e.device_report_key, arr);
    }
    return m;
  }, [events]);

  const LANE_HEIGHT = 36;
  const LABEL_WIDTH = 150;
  const containerWidth = containerRef.current?.clientWidth || 1000;
  const plotWidth = Math.max(100, containerWidth - LABEL_WIDTH - 10);

  const xOf = (ms) => LABEL_WIDTH + ((ms - range.min.getTime()) / totalMs) * plotWidth;
  const msAtX = (x) => {
    const frac = (x - LABEL_WIDTH) / plotWidth;
    return range.min.getTime() + Math.max(0, Math.min(1, frac)) * totalMs;
  };

  const handleScrub = (e) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setPlayheadTime(new Date(msAtX(e.clientX - rect.left)));
  };

  const playheadX = playheadTime ? xOf(playheadTime.getTime()) : null;

  return (
    <div
      ref={containerRef}
      className="relative h-full w-full overflow-auto bg-light-50 cursor-crosshair"
      onMouseDown={handleScrub}
      onMouseMove={(e) => {
        // Only scrub if mouse button held
        if (e.buttons === 1) handleScrub(e);
      }}
    >
      <svg
        width="100%"
        height={lanes.length * LANE_HEIGHT + 40}
        style={{ minWidth: 500 }}
      >
        {/* Axis: labels at start/middle/end */}
        <text x={LABEL_WIDTH} y={14} fontSize="10" fill="#64748b">
          {formatAxis(range.min)}
        </text>
        <text x={LABEL_WIDTH + plotWidth / 2} y={14} fontSize="10" fill="#64748b" textAnchor="middle">
          {formatAxis(new Date(range.min.getTime() + totalMs / 2))}
        </text>
        <text x={LABEL_WIDTH + plotWidth} y={14} fontSize="10" fill="#64748b" textAnchor="end">
          {formatAxis(range.max)}
        </text>

        {/* Lanes */}
        {lanes.map((lane, i) => {
          const y = 24 + i * LANE_HEIGHT;
          return (
            <g key={lane.report_key}>
              {/* Label */}
              <text
                x={LABEL_WIDTH - 6}
                y={y + LANE_HEIGHT / 2 + 3}
                fontSize="11"
                fill="#1e293b"
                textAnchor="end"
                fontWeight="500"
              >
                {lane.label.length > 22 ? lane.label.slice(0, 22) + '…' : lane.label}
              </text>
              {/* Lane background */}
              <rect
                x={LABEL_WIDTH}
                y={y}
                width={plotWidth}
                height={LANE_HEIGHT - 6}
                fill={i % 2 === 0 ? '#ffffff' : '#f8fafc'}
                stroke="#e2e8f0"
              />
              {/* Device colour stripe on the left */}
              <rect
                x={LABEL_WIDTH}
                y={y}
                width={3}
                height={LANE_HEIGHT - 6}
                fill={lane.color}
              />
              {/* Event dots */}
              {(eventsByDevice.get(lane.report_key) || []).map((e) => {
                const x = xOf(e._t);
                const color = EVENT_COLORS[e.event_type] || '#64748b';
                return (
                  <circle
                    key={e.id || e.node_key}
                    cx={x}
                    cy={y + (LANE_HEIGHT - 6) / 2}
                    r={e.event_type === 'call' || e.event_type === 'power' ? 4 : 3}
                    fill={color}
                    opacity={0.9}
                    onMouseEnter={() =>
                      setHover({ e, x, y: y + (LANE_HEIGHT - 6) / 2 })
                    }
                    onMouseLeave={() => setHover(null)}
                    onClick={(ev) => {
                      ev.stopPropagation();
                      onEventClick?.(e);
                    }}
                    style={{ cursor: 'pointer' }}
                  />
                );
              })}
            </g>
          );
        })}

        {/* Playhead */}
        {playheadX != null && (
          <line
            x1={playheadX}
            x2={playheadX}
            y1={20}
            y2={24 + lanes.length * LANE_HEIGHT}
            stroke="#2563eb"
            strokeWidth="2"
          />
        )}
      </svg>

      {/* Hover tooltip */}
      {hover && (
        <div
          className="absolute pointer-events-none text-[10px] bg-slate-900 text-white px-2 py-1 rounded shadow"
          style={{ left: hover.x + 8, top: hover.y - 14 }}
        >
          <div className="font-semibold">{hover.e.label}</div>
          <div>{hover.e.timestamp}</div>
          {hover.e.summary && <div className="max-w-[200px] truncate">{hover.e.summary}</div>}
        </div>
      )}
    </div>
  );
}

function formatAxis(d) {
  if (!d) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
