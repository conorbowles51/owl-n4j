import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Play, Pause, X, Rewind, FastForward } from 'lucide-react';

/**
 * Locations playback scrubber.
 *
 * Pure controlled component:
 *   playheadTime : Date | null   — null = playback inactive
 *   minTime/maxTime : Date | null — envelope (start/end of the filtered set)
 *   isPlaying : boolean
 *   speed : number               — multiplier on real time (1 / 4 / 16 / 64 / 256)
 *   onPlayheadChange, onPlayToggle, onSpeedChange, onExit
 *
 * Keyboard (when the bar is mounted AND playheadTime != null):
 *   Space     play / pause
 *   ← / →     step ±1% of envelope
 *   Shift+← / →  step ±5%
 *   Home/End  jump to start/end
 *   Esc       exit playback
 *
 * Drag handle to scrub; click anywhere on the rail to jump.
 *
 * No envelope (filtered set empty / single point) → renders a disabled
 * stub so the layout doesn't pop in/out when filters narrow to zero.
 */
const SPEEDS = [1, 4, 16, 64, 256];

function fmtTimestamp(d) {
  if (!d) return '—';
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} `
    + `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export default function PlaybackBar({
  playheadTime,
  minTime,
  maxTime,
  isPlaying,
  speed,
  trailWindowMs = 30 * 60 * 1000,
  onPlayheadChange,
  onPlayToggle,
  onSpeedChange,
  onExit,
}) {
  const railRef = useRef(null);
  const draggingRef = useRef(false);
  const [hoverPct, setHoverPct] = useState(null); // for tooltip while hovering

  const minMs = minTime ? minTime.getTime() : null;
  const maxMs = maxTime ? maxTime.getTime() : null;
  const spanMs = (minMs != null && maxMs != null && maxMs > minMs) ? (maxMs - minMs) : null;
  const headMs = playheadTime ? playheadTime.getTime() : null;

  const headPct = (() => {
    if (spanMs == null || headMs == null) return 0;
    const clamped = Math.max(minMs, Math.min(maxMs, headMs));
    return ((clamped - minMs) / spanMs) * 100;
  })();

  const stepBy = useCallback((pctDelta) => {
    if (spanMs == null) return;
    const cur = headMs != null ? headMs : minMs;
    const deltaMs = (pctDelta / 100) * spanMs;
    const next = Math.max(minMs, Math.min(maxMs, cur + deltaMs));
    onPlayheadChange(new Date(next));
  }, [spanMs, headMs, minMs, maxMs, onPlayheadChange]);

  const setFromPct = useCallback((pct) => {
    if (spanMs == null) return;
    const clamped = Math.max(0, Math.min(100, pct));
    onPlayheadChange(new Date(minMs + (clamped / 100) * spanMs));
  }, [spanMs, minMs, onPlayheadChange]);

  const pctFromEvent = useCallback((evt) => {
    const rail = railRef.current;
    if (!rail) return null;
    const rect = rail.getBoundingClientRect();
    return ((evt.clientX - rect.left) / rect.width) * 100;
  }, []);

  // ------------------------------------------------------------------
  // Drag handling — document-level listeners so the user can drag past
  // the rail edges without losing the gesture (same trick the resize
  // splitter uses).
  // ------------------------------------------------------------------
  useEffect(() => {
    const onMove = (e) => {
      if (!draggingRef.current) return;
      const pct = pctFromEvent(e);
      if (pct != null) setFromPct(pct);
    };
    const onUp = () => {
      draggingRef.current = false;
      setHoverPct(null);
    };
    document.addEventListener('pointermove', onMove);
    document.addEventListener('pointerup', onUp);
    return () => {
      document.removeEventListener('pointermove', onMove);
      document.removeEventListener('pointerup', onUp);
    };
  }, [pctFromEvent, setFromPct]);

  // ------------------------------------------------------------------
  // Playback tick. Advances playheadTime by `speed` real seconds per
  // wall-clock second using a single setInterval. Stops at maxTime
  // (auto-pauses) so the playhead doesn't fall off the end silently.
  // ------------------------------------------------------------------
  useEffect(() => {
    if (!isPlaying || spanMs == null) return undefined;
    const TICK_MS = 60; // ~16fps — smooth enough, light on the matcher
    const id = setInterval(() => {
      const cur = headMs != null ? headMs : minMs;
      const next = cur + (TICK_MS * speed);
      if (next >= maxMs) {
        onPlayheadChange(new Date(maxMs));
        onPlayToggle(false);
      } else {
        onPlayheadChange(new Date(next));
      }
    }, TICK_MS);
    return () => clearInterval(id);
  }, [isPlaying, spanMs, headMs, minMs, maxMs, speed, onPlayheadChange, onPlayToggle]);

  // ------------------------------------------------------------------
  // Keyboard shortcuts — global while a playhead is active. Skip when
  // the user is typing in an input so Space inside the search box
  // doesn't pause playback.
  // ------------------------------------------------------------------
  useEffect(() => {
    if (headMs == null) return undefined;
    const onKey = (e) => {
      const tag = (e.target?.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || e.target?.isContentEditable) return;
      switch (e.key) {
        case ' ':
        case 'Spacebar':
          e.preventDefault();
          onPlayToggle(!isPlaying);
          break;
        case 'ArrowLeft':
          e.preventDefault();
          stepBy(e.shiftKey ? -5 : -1);
          break;
        case 'ArrowRight':
          e.preventDefault();
          stepBy(e.shiftKey ? 5 : 1);
          break;
        case 'Home':
          e.preventDefault();
          setFromPct(0);
          break;
        case 'End':
          e.preventDefault();
          setFromPct(100);
          break;
        case 'Escape':
          e.preventDefault();
          onExit();
          break;
        default:
          break;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [headMs, isPlaying, onPlayToggle, stepBy, setFromPct, onExit]);

  const noEnvelope = spanMs == null;

  const hoverTime = useMemo(() => {
    if (hoverPct == null || spanMs == null) return null;
    return new Date(minMs + (hoverPct / 100) * spanMs);
  }, [hoverPct, spanMs, minMs]);

  return (
    <div className="flex items-center gap-2 px-2 py-1.5 bg-white border-b border-light-200 text-xs">
      <button
        type="button"
        onClick={() => onPlayToggle(!isPlaying)}
        disabled={noEnvelope}
        title={isPlaying ? 'Pause (Space)' : 'Play (Space)'}
        className={`p-1 rounded ${
          noEnvelope
            ? 'text-light-300 cursor-not-allowed'
            : 'text-owl-blue-600 hover:bg-light-100'
        }`}
      >
        {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
      </button>
      <button
        type="button"
        onClick={() => stepBy(-1)}
        disabled={noEnvelope}
        title="Step back 1% (←) — hold Shift for 5%"
        className={`p-1 rounded ${
          noEnvelope ? 'text-light-300 cursor-not-allowed' : 'text-light-600 hover:bg-light-100'
        }`}
      >
        <Rewind className="w-3 h-3" />
      </button>
      <button
        type="button"
        onClick={() => stepBy(1)}
        disabled={noEnvelope}
        title="Step forward 1% (→) — hold Shift for 5%"
        className={`p-1 rounded ${
          noEnvelope ? 'text-light-300 cursor-not-allowed' : 'text-light-600 hover:bg-light-100'
        }`}
      >
        <FastForward className="w-3 h-3" />
      </button>

      {/* Rail */}
      <div
        ref={railRef}
        onPointerDown={(e) => {
          if (noEnvelope) return;
          draggingRef.current = true;
          const pct = pctFromEvent(e);
          if (pct != null) setFromPct(pct);
        }}
        onMouseMove={(e) => {
          if (noEnvelope) return;
          const pct = pctFromEvent(e);
          if (pct != null) setHoverPct(pct);
        }}
        onMouseLeave={() => setHoverPct(null)}
        className={`relative flex-1 h-2 rounded-full ${
          noEnvelope ? 'bg-light-100' : 'bg-light-200 cursor-pointer'
        } select-none`}
      >
        {/* Past — solid bar up to the playhead */}
        {!noEnvelope && headMs != null && (
          <div
            className="absolute left-0 top-0 h-full bg-owl-blue-200 rounded-l-full pointer-events-none"
            style={{ width: `${headPct}%` }}
          />
        )}
        {/* Trail-window highlight just behind the playhead */}
        {!noEnvelope && headMs != null && spanMs > 0 && (
          <div
            className="absolute top-0 h-full bg-owl-blue-400/40 pointer-events-none"
            style={{
              left: `${Math.max(0, headPct - (trailWindowMs / spanMs) * 100)}%`,
              width: `${Math.min(headPct, (trailWindowMs / spanMs) * 100)}%`,
            }}
          />
        )}
        {/* Playhead dot */}
        {!noEnvelope && headMs != null && (
          <div
            className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-owl-blue-600 border-2 border-white shadow pointer-events-none"
            style={{ left: `${headPct}%` }}
          />
        )}
        {/* Hover tooltip */}
        {hoverTime && !draggingRef.current && (
          <div
            className="absolute -top-6 -translate-x-1/2 px-1.5 py-0.5 rounded bg-light-900 text-white text-[10px] whitespace-nowrap pointer-events-none"
            style={{ left: `${hoverPct}%` }}
          >
            {fmtTimestamp(hoverTime)}
          </div>
        )}
      </div>

      {/* Live timestamp readout */}
      <span className="tabular-nums text-light-700 min-w-[140px] text-right">
        {fmtTimestamp(playheadTime)}
      </span>

      {/* Speed selector */}
      <select
        value={speed}
        onChange={(e) => onSpeedChange(Number(e.target.value))}
        disabled={noEnvelope}
        title="Playback speed"
        className="text-[11px] border border-light-300 rounded px-1 py-0.5 bg-white"
      >
        {SPEEDS.map((s) => (
          <option key={s} value={s}>{s}×</option>
        ))}
      </select>

      <button
        type="button"
        onClick={onExit}
        title="Exit playback (Esc)"
        className="p-1 rounded text-light-500 hover:text-red-600 hover:bg-light-100"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
