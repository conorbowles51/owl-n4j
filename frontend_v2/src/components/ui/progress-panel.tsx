import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/cn"

/**
 * The shared waiting panel (07 4.7), for phone screens and any Loupe screen. Built from the Financial loading
 * panel's rules (features/financial/components/LoadProgress.tsx stays as it is):
 * - shows after 300 ms; names the step in words; completion from true counts ("98,000 of 186,787");
 * - time left only from a measured rate (this step's rate so far, or this view's last load); with no rate it says
 *   "Working out time left (first run of this step)", never an invented figure;
 * - redraws every second; never shows 100% before the page is drawn;
 * - one stall rule: interactive reads say "Still working on <step>" after 3 s with no movement and name the slow
 *   part with Try again after 10 s; background stages say "No change on <step> for <n> s. The server is still on
 *   this step. Last change at <time>" after their threshold (30 s for intake stages until rates are measured).
 */

export const SHOW_AFTER_MS = 300
export const STALL_INTERACTIVE_MS = 3_000
export const SLOW_INTERACTIVE_MS = 10_000
export const STALL_BACKGROUND_MS = 30_000
export const TICK_MS = 1_000

export interface ProgressState {
  /** The step in words, e.g. "Counting matching messages on 3 phones". */
  step: string
  done?: number
  total?: number
  /** Unit for the counts, e.g. "messages". */
  unit?: string
  /** performance.now (or Date.now, consistently) when this step started and when its count last moved. */
  startedAt: number
  movedAt: number
  /** Milliseconds per unit measured on this view's last load, when there is one. */
  lastRateMsPerUnit?: number | null
  /** Milliseconds this view took last time, when known and no counts are available. */
  lastDurationMs?: number | null
  failed?: { what: string; referenceId: string } | null
  /** True once the result is drawn on the page; only then may the panel reach 100%. */
  drawn?: boolean
}

const n = (v: number) => v.toLocaleString("en-US")

export function secondsWords(ms: number): string {
  const s = Math.max(1, Math.round(ms / 1000))
  if (s < 90) return `${s} s`
  const m = Math.round(s / 60)
  return `${m} min`
}

/** Time left in words, or the first-run sentence. Never invented. */
export function timeLeft(p: ProgressState, now: number): string {
  const elapsed = now - p.startedAt
  if (p.done !== undefined && p.total !== undefined && p.total > 0) {
    if (p.done >= p.total) return "finishing"
    if (p.done > 0 && elapsed > 0) return `about ${secondsWords(((p.total - p.done) * elapsed) / p.done)} left`
    if (p.lastRateMsPerUnit) return `about ${secondsWords((p.total - p.done) * p.lastRateMsPerUnit)} left`
  } else if (p.lastDurationMs && elapsed < p.lastDurationMs) {
    return `about ${secondsWords(p.lastDurationMs - elapsed)} left (this took ${secondsWords(p.lastDurationMs)} last time)`
  }
  return "Working out time left (first run of this step)"
}

export function percentShown(p: ProgressState): number | null {
  if (p.done === undefined || p.total === undefined || p.total <= 0) return null
  const raw = Math.floor((p.done / p.total) * 100)
  return p.drawn ? Math.min(100, raw) : Math.min(99, raw)
}

export type StallState = { kind: "moving" } | { kind: "still"; quietMs: number } | { kind: "slow"; quietMs: number }

export function stallState(p: ProgressState, now: number, background: boolean, thresholdMs = STALL_BACKGROUND_MS): StallState {
  const quietMs = now - p.movedAt
  if (background) return quietMs >= thresholdMs ? { kind: "still", quietMs } : { kind: "moving" }
  if (quietMs >= SLOW_INTERACTIVE_MS) return { kind: "slow", quietMs }
  if (quietMs >= STALL_INTERACTIVE_MS) return { kind: "still", quietMs }
  return { kind: "moving" }
}

const lower = (s: string) => s.charAt(0).toLowerCase() + s.slice(1)

export function useTick(active: boolean, clock: () => number = () => performance.now()) {
  const [now, setNow] = useState(clock)
  useEffect(() => {
    if (!active) return
    const t = setInterval(() => setNow(clock()), TICK_MS)
    return () => clearInterval(t)
  }, [active, clock])
  return now
}

export function ProgressPanel({
  progress,
  now,
  background = false,
  stallThresholdMs,
  onRetry,
  formatClock = (t: number) => new Date(t).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", second: "2-digit" }),
  className,
}: {
  progress: ProgressState
  /** The current time on the same clock as startedAt/movedAt (useTick gives one that updates every second). */
  now: number
  background?: boolean
  stallThresholdMs?: number
  onRetry?: () => void
  /** For background stages, turns movedAt into a time of day. */
  formatClock?: (t: number) => string
  className?: string
}) {
  const p = progress
  if (!background && now - p.startedAt < SHOW_AFTER_MS && !p.failed) return null
  const pct = percentShown(p)
  const stall = stallState(p, now, background, stallThresholdMs)
  let sentence = p.step
  if (stall.kind === "still") {
    sentence = background
      ? `No change on ${lower(p.step)} for ${secondsWords(stall.quietMs)}. The server is still on this step. Last change at ${formatClock(p.movedAt)}`
      : `Still working on ${lower(p.step)}`
  } else if (stall.kind === "slow") {
    sentence = `${p.step} is taking longer: no change for ${secondsWords(stall.quietMs)}`
  }
  return (
    <div className={cn("rounded border bg-card px-3 py-2 text-sm text-foreground", className)} data-testid="progress-panel">
      <p role="status" aria-live="polite" className="flex flex-wrap items-baseline gap-x-2">
        <span className="font-medium">{sentence}</span>
        {p.done !== undefined && p.total !== undefined && (
          <span>
            {n(p.done)} of {n(p.total)}
            {p.unit ? ` ${p.unit}` : ""}
          </span>
        )}
        <span className="text-muted-foreground">
          {pct !== null ? `${pct}% · ` : ""}
          {timeLeft(p, now)}
        </span>
      </p>
      {pct !== null && (
        <div role="progressbar" aria-label={p.step} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} className="mt-1.5 h-1.5 w-full overflow-hidden rounded bg-muted">
          <div className="h-full bg-primary transition-[width] duration-300" style={{ width: `${pct}%` }} />
        </div>
      )}
      {(p.failed || stall.kind === "slow") && (
        <div role={p.failed ? "alert" : undefined} className="mt-1.5 flex flex-wrap items-center gap-3">
          <span className={p.failed ? "text-status-error" : undefined}>
            {p.failed ? `${p.failed.what} stopped. Reference: ${p.failed.referenceId}.` : "You can keep waiting or try again."}
          </span>
          {onRetry && (
            <Button size="sm" variant="outline" onClick={onRetry}>
              Try again
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
