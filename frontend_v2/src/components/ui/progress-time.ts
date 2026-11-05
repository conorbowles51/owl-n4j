import { useEffect, useState } from "react"
import type { ProgressState, StallState } from "./progress-panel"

export const STALL_INTERACTIVE_MS = 3_000

export const SLOW_INTERACTIVE_MS = 10_000

export const STALL_BACKGROUND_MS = 30_000

export const TICK_MS = 1_000

export function secondsWords(ms: number): string {
  const s = Math.max(1, Math.round(ms / 1000))
  if (s < 90) return `${s} s`
  const m = Math.round(s / 60)
  return `${m} min`
}

/** Time left in words, the late sentence for a step past its last time, or the first-run sentence. Never invented. */
export function timeLeft(p: ProgressState, now: number): string {
  const elapsed = now - p.startedAt
  if (p.done !== undefined && p.total !== undefined && p.total > 0) {
    if (p.done >= p.total) return "finishing"
    if (p.done > 0 && elapsed > 0) return `about ${secondsWords(((p.total - p.done) * elapsed) / p.done)} left`
    if (p.lastRateMsPerUnit) return `about ${secondsWords((p.total - p.done) * p.lastRateMsPerUnit)} left`
  }
  if (p.lastDurationMs) {
    if (elapsed >= p.lastDurationMs) return `Taking longer than last time (${secondsWords(p.lastDurationMs)})`
    return `about ${secondsWords(p.lastDurationMs - elapsed)} left (this took ${secondsWords(p.lastDurationMs)} last time)`
  }
  return "Working out time left (first run of this step)"
}

export function percentShown(p: ProgressState): number | null {
  if (p.done === undefined || p.total === undefined || p.total <= 0) return null
  const raw = Math.floor((p.done / p.total) * 100)
  return p.drawn ? Math.min(100, raw) : Math.min(99, raw)
}

export function stallState(p: ProgressState, now: number, background: boolean, thresholdMs = STALL_BACKGROUND_MS): StallState {
  const quietMs = now - p.movedAt
  if (background) return quietMs >= thresholdMs ? { kind: "still", quietMs } : { kind: "moving" }
  if (quietMs >= SLOW_INTERACTIVE_MS) return { kind: "slow", quietMs }
  if (quietMs >= STALL_INTERACTIVE_MS) return { kind: "still", quietMs }
  return { kind: "moving" }
}

export function useTick(active: boolean, clock: () => number = () => performance.now()) {
  const [now, setNow] = useState(clock)
  useEffect(() => {
    if (!active) return
    const t = setInterval(() => setNow(clock()), TICK_MS)
    return () => clearInterval(t)
  }, [active, clock])
  return now
}
