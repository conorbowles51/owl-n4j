import { useEffect, useState } from "react"

/**
 * False until the browser has painted the first frame of this app load, then true forever. Queries the page shell
 * does not need gate on it (jobs, my-marks, reader settings, scope presets), so the shell's own requests are not
 * queued behind them on a cold or warm start. After that first paint every later mount sees true at once, so
 * navigation inside the app defers nothing.
 */
let painted = false

/** Tests only: forget that a frame was painted, so each test starts before the first paint. */
export function resetAfterFirstPaintForTest() {
  painted = false
}

export function useAfterFirstPaint(): boolean {
  const [ready, setReady] = useState(painted)
  useEffect(() => {
    if (painted) return
    let second = 0
    // two frames: the first callback runs before the first paint is committed, the second after it
    const first = requestAnimationFrame(() => {
      second = requestAnimationFrame(() => {
        painted = true
        setReady(true)
      })
    })
    return () => {
      cancelAnimationFrame(first)
      cancelAnimationFrame(second)
    }
  }, [])
  return ready
}
