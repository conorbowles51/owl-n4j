import { useEffect, useState } from "react"
import { ProgressPanel } from "@/components/ui/progress-panel"
import { useTick } from "@/components/ui/progress-time"
import { isAppStartCheck } from "@/lib/browser-timing"
import { pageChunksPending } from "@/lib/page-chunks"
import { requestsSince, subscribeRequests } from "@/lib/request-progress"

/**
 * Tells the waiter during the app's own start. When the document has painted but, GAP_SHOW_MS later, the page has
 * still not asked the API for any data (the sign-in check and the speed beacons are not data,
 * lib/browser-timing.ts), the shared waiting panel shows over the content area until the first request leaves.
 * Measured on a cold open of the evidence workbench at load 52 (6 Nov): first paint at 1.2–2.0 s, the page's first
 * request at 7.1–15.8 s, and nothing on screen said the app was still working. While a page's code is on its way
 * the route's own loading panel is already up (app/page-loading.tsx), so this one stays away then. One-shot per
 * document: once the first data request has left it never returns (a switch inside the app has the page's own
 * panels), and after GIVE_UP_MS it stops watching rather than stay up on a page that never reads.
 */
export const GAP_SHOW_MS = 2000
export const GIVE_UP_MS = 60000

function firstDataRequested(): boolean {
  return requestsSince(0).some((request) => !isAppStartCheck(request.endpoint))
}

function readFirstPaint(): number | null {
  try {
    const entry = performance
      .getEntriesByType?.("paint")
      ?.find((candidate) => candidate.name === "first-contentful-paint")
    return entry ? entry.startTime : null
  } catch {
    return null
  }
}

export function AppStartWaiting() {
  const [done, setDone] = useState(firstDataRequested)
  const [paintedAt, setPaintedAt] = useState<number | null>(readFirstPaint)
  // The gap runs from the later of first paint and this shell appearing: after an in-document sign-in the
  // document painted long ago, and the wait the person feels starts when the signed-in shell is up.
  const [shownAt, setShownAt] = useState<number | null>(null)
  const now = useTick(!done)
  const startedAt = paintedAt === null || shownAt === null ? null : Math.max(paintedAt, shownAt)

  useEffect(() => {
    setShownAt((value) => value ?? performance.now())
  }, [])

  useEffect(() => {
    if (done) return
    if (firstDataRequested()) {
      setDone(true)
      return
    }
    return subscribeRequests(() => {
      if (firstDataRequested()) setDone(true)
    })
  }, [done])

  useEffect(() => {
    if (done) return
    if (paintedAt === null) {
      const painted = readFirstPaint()
      if (painted !== null) setPaintedAt(painted)
      return
    }
    if (startedAt !== null && now - startedAt > GIVE_UP_MS) setDone(true)
  }, [now, done, paintedAt, startedAt])

  if (done || startedAt === null) return null
  if (now - startedAt < GAP_SHOW_MS) return null
  if (pageChunksPending()) return null
  return (
    <div className="pointer-events-none absolute inset-x-0 top-3 z-50 mx-auto w-full max-w-md px-4">
      <ProgressPanel
        progress={{ step: "Opening the page", startedAt, movedAt: startedAt }}
        now={now}
        className="shadow-md"
      />
    </div>
  )
}
