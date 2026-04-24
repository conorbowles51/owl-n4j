import React, { useEffect, useRef, useMemo } from 'react';
import { Play, Pause, SkipBack, SkipForward, ChevronLeft, ChevronRight, Clock } from 'lucide-react';
import { PLAYBACK_SPEEDS, parseTs, formatTs } from './eventUtils';

/**
 * Playback bar: play/pause, scrubber, speed pills, jump-prev/next, time readout.
 *
 * Props:
 *   events: array of events (uses timestamp to compute range and neighbours)
 *   playheadTime: Date | null
 *   setPlayheadTime: (Date) => void
 *   isPlaying: boolean
 *   setIsPlaying: (bool) => void
 *   playbackSpeed: number (multiplier — real-world seconds per wall-clock second)
 *   setPlaybackSpeed: (number) => void
 */
export default function EventPlaybackBar({
  events = [],
  playheadTime,
  setPlayheadTime,
  isPlaying,
  setIsPlaying,
  playbackSpeed,
  setPlaybackSpeed,
}) {
  // Compute range
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

  // Sorted unique timestamps for jump-prev/next
  const sortedTimes = useMemo(() => {
    const arr = events
      .map((e) => parseTs(e.timestamp))
      .filter((d) => d)
      .map((d) => d.getTime())
      .sort((a, b) => a - b);
    return arr;
  }, [events]);

  const rafRef = useRef(null);
  const lastTickRef = useRef(null);
  // Accumulate simulated real-world-ms between commits so we can throttle
  // the React setState to ~10fps without losing precision.
  const pendingSimMsRef = useRef(0);

  // Initialise playhead when range appears
  useEffect(() => {
    if (range.min && (!playheadTime || playheadTime < range.min || playheadTime > range.max)) {
      setPlayheadTime(range.min);
    }
  }, [range.min, range.max]); // eslint-disable-line react-hooks/exhaustive-deps

  // Throttled animation loop.
  // The internal math runs every RAF (60fps) so sub-frame precision is
  // preserved, but we only call setPlayheadTime every ~100ms so React / the
  // map / the table re-renders at a manageable 10fps even at 1800× speed.
  useEffect(() => {
    if (!isPlaying || !range.min || !range.max) {
      lastTickRef.current = null;
      pendingSimMsRef.current = 0;
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      return;
    }
    const COMMIT_MS = 100; // 10fps
    let sinceCommit = 0;
    const tick = (now) => {
      if (lastTickRef.current == null) lastTickRef.current = now;
      const dtMs = now - lastTickRef.current;
      lastTickRef.current = now;
      sinceCommit += dtMs;
      // Accumulate simulated time
      pendingSimMsRef.current += dtMs * playbackSpeed;
      if (sinceCommit >= COMMIT_MS) {
        const advanceMs = pendingSimMsRef.current;
        pendingSimMsRef.current = 0;
        sinceCommit = 0;
        setPlayheadTime((prev) => {
          const cur = prev || range.min;
          const nextMs = cur.getTime() + advanceMs;
          if (nextMs >= range.max.getTime()) {
            setIsPlaying(false);
            return range.max;
          }
          return new Date(nextMs);
        });
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [isPlaying, playbackSpeed, range.min, range.max, setPlayheadTime, setIsPlaying]);

  if (!range.min || !range.max) {
    return (
      <div className="flex items-center justify-center px-4 py-2 border-t border-b border-light-200 bg-light-50 text-xs text-light-500">
        No timestamped events to play back.
      </div>
    );
  }

  const totalMs = range.max.getTime() - range.min.getTime();
  const fraction = playheadTime
    ? Math.max(0, Math.min(1, (playheadTime.getTime() - range.min.getTime()) / Math.max(totalMs, 1)))
    : 0;

  const handleScrub = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const frac = (e.clientX - rect.left) / rect.width;
    setPlayheadTime(new Date(range.min.getTime() + frac * totalMs));
  };

  const jumpPrev = () => {
    if (!playheadTime) return;
    const cur = playheadTime.getTime();
    let target = null;
    for (let i = sortedTimes.length - 1; i >= 0; i--) {
      if (sortedTimes[i] < cur - 1) {
        target = sortedTimes[i];
        break;
      }
    }
    if (target != null) setPlayheadTime(new Date(target));
  };
  const jumpNext = () => {
    if (!playheadTime) return;
    const cur = playheadTime.getTime();
    const target = sortedTimes.find((t) => t > cur + 1);
    if (target != null) setPlayheadTime(new Date(target));
  };

  return (
    <div className="flex items-center gap-3 px-3 py-1.5 border-t border-b border-light-200 bg-white flex-shrink-0">
      <button
        onClick={() => setPlayheadTime(range.min)}
        className="p-1 text-light-600 hover:text-owl-blue-700"
        title="Skip to start"
      >
        <SkipBack className="w-4 h-4" />
      </button>
      <button
        onClick={jumpPrev}
        className="p-1 text-light-600 hover:text-owl-blue-700"
        title="Jump to previous event"
      >
        <ChevronLeft className="w-4 h-4" />
      </button>
      <button
        onClick={() => setIsPlaying(!isPlaying)}
        className="p-1.5 text-white bg-owl-blue-600 hover:bg-owl-blue-700 rounded"
        title={isPlaying ? 'Pause' : 'Play'}
      >
        {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
      </button>
      <button
        onClick={jumpNext}
        className="p-1 text-light-600 hover:text-owl-blue-700"
        title="Jump to next event"
      >
        <ChevronRight className="w-4 h-4" />
      </button>
      <button
        onClick={() => setPlayheadTime(range.max)}
        className="p-1 text-light-600 hover:text-owl-blue-700"
        title="Skip to end"
      >
        <SkipForward className="w-4 h-4" />
      </button>

      {/* Scrubber */}
      <div
        className="relative flex-1 h-2 bg-light-200 rounded cursor-pointer"
        onClick={handleScrub}
      >
        <div
          className="absolute top-0 left-0 h-2 bg-owl-blue-400 rounded"
          style={{ width: `${fraction * 100}%` }}
        />
        <div
          className="absolute top-1/2 -translate-y-1/2 w-3 h-3 bg-owl-blue-700 rounded-full border-2 border-white shadow"
          style={{ left: `calc(${fraction * 100}% - 6px)` }}
        />
      </div>

      {/* Speed */}
      <div className="flex items-center gap-0.5">
        {PLAYBACK_SPEEDS.map((s) => (
          <button
            key={s}
            onClick={() => setPlaybackSpeed(s)}
            className={`px-1.5 py-0.5 text-[10px] rounded ${
              playbackSpeed === s
                ? 'bg-owl-blue-600 text-white'
                : 'text-light-600 hover:bg-light-100'
            }`}
          >
            {s}x
          </button>
        ))}
      </div>

      {/* Readout */}
      <div className="flex items-center gap-1 text-xs text-light-700 tabular-nums flex-shrink-0">
        <Clock className="w-3 h-3" />
        {playheadTime ? formatTs(playheadTime.toISOString()) : '—'}
      </div>
    </div>
  );
}
