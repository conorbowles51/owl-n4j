import { useEffect, useState } from "react"
import { SHOW_AFTER_MS } from "./progress-panel"
import { TICK_MS } from "./progress-time"

/**
 * The clock for a ProgressPanel started by a press: it ticks when the panel is due (SHOW_AFTER_MS after the start)
 * and then every `everyMs`. A plain interval would first tick at `everyMs`, so a panel due at 300 ms showed at the
 * interval's first tick (500 ms or 1 s), or later on a busy page.
 */
export function useProgressClock(active: boolean, startedAt: number, everyMs: number = TICK_MS) {
  const [now, setNow] = useState(() => performance.now())
  useEffect(() => {
    if (!active) return
    const tick = () => setNow(performance.now())
    const due = setTimeout(tick, Math.max(0, startedAt + SHOW_AFTER_MS - performance.now()))
    const every = setInterval(tick, everyMs)
    return () => {
      clearTimeout(due)
      clearInterval(every)
    }
  }, [active, startedAt, everyMs])
  return now
}
