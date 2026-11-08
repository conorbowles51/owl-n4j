import { useEffect, useState } from "react"

/** Seconds since `from`, ticking once a second while `running`. */
export function useElapsedSeconds(running: boolean, from: number) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!running) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [running])
  return Math.max(0, Math.floor((now - from) / 1000))
}
