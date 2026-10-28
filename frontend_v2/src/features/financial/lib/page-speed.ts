import { useEffect, useRef } from "react"
import { useQueryClient, type QueryClient } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"

/**
 * Time from opening a Financial view to its data being on screen, as the person sees it.
 *
 * "Opened" (LOAD): the browser loaded this Financial address directly, so the time runs from the
 * browser's navigation start (performance time origin). "Switched to" (VIEW): the view or case
 * changed inside the app, so the time runs from that change. Either way it ends at the first
 * frame painted after every request the view started has returned. A view left before that is
 * not recorded. Timings are queued and posted in small batches; a failed post is dropped, never
 * retried and never shown. Uses only performance.now, timers and fetch (safe over plain http).
 */

export interface PageView {
  page: string
  method: "LOAD" | "VIEW"
  case_id: string | null
  ms: number
}

const ENDPOINT = "/api/request-speed/page-views"
const BATCH = 20
const FLUSH_MS = 5000
const GIVE_UP_MS = 120000

const queue: PageView[] = []
let timer: ReturnType<typeof setTimeout> | null = null
let loadTaken = false
let listening = false

export function flushPageViews(keepalive = false) {
  if (timer) {
    clearTimeout(timer)
    timer = null
  }
  const views = queue.splice(0, 50)
  if (!views.length) return
  void fetchAPI(ENDPOINT, { method: "POST", body: { views }, keepalive, timeout: 15000 }).catch(() => undefined)
}

export function recordPageView(view: PageView) {
  queue.push({ ...view, ms: Math.max(0, Math.round(view.ms)) })
  if (!listening && typeof window !== "undefined") {
    listening = true
    window.addEventListener("pagehide", () => flushPageViews(true))
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") flushPageViews(true)
    })
  }
  if (queue.length >= BATCH) flushPageViews()
  else if (!timer) timer = setTimeout(() => flushPageViews(), FLUSH_MS)
}

/** True once: the document was loaded at this very address and nothing has been timed yet. */
export function takeDocumentLoad(pathname: string) {
  if (loadTaken) return false
  loadTaken = true
  const entry = performance.getEntriesByType?.("navigation")?.[0] as PerformanceNavigationTiming | undefined
  if (!entry?.name) return false
  try {
    return new URL(entry.name).pathname === pathname
  } catch {
    return false
  }
}

/** Resolves (with performance.now) at the first frame after nothing is fetching, or null on give-up/cancel. */
export function whenSettled(client: QueryClient, signal: { cancelled: boolean }): Promise<number | null> {
  return new Promise((resolve) => {
    let unsubscribe = () => {}
    let done = false
    const finish = (value: number | null) => {
      if (done) return
      done = true
      unsubscribe()
      clearTimeout(giveUp)
      resolve(value)
    }
    const giveUp = setTimeout(() => finish(null), GIVE_UP_MS)
    const check = () => {
      if (signal.cancelled) return finish(null)
      if (client.isFetching() > 0) return
      // Data has arrived; time the next paint, when it is on screen.
      requestAnimationFrame(() => finish(signal.cancelled ? null : performance.now()))
    }
    unsubscribe = client.getQueryCache().subscribe(() => {
      if (!done) check()
    })
    check()
  })
}

/** Times each Financial view (page name like "financial/ledger") for a case. */
export function useFinancialViewSpeed(caseId: string | undefined, page: string) {
  const client = useQueryClient()
  const current = useRef<{ start: number; method: "LOAD" | "VIEW"; armed: boolean; signal: { cancelled: boolean } } | null>(null)

  useEffect(() => {
    if (!caseId || typeof performance === "undefined") return
    if (document.visibilityState === "hidden") {
      takeDocumentLoad(window.location.pathname) // a hidden opening is not timed, and not reused later
      return
    }
    const previous = current.current
    // A view set by the address in the same frame as opening (not by the person) keeps the
    // opening's start: it is the same page load.
    const inherit = previous && !previous.armed
    const method = inherit ? previous.method : takeDocumentLoad(window.location.pathname) ? "LOAD" : "VIEW"
    const start = inherit ? previous.start : method === "LOAD" ? 0 : performance.now()
    const signal = { cancelled: false }
    const measuring = { start, method, armed: false, signal }
    current.current = measuring
    // Wait one frame so the view's own requests have started before looking for quiet.
    const frame = requestAnimationFrame(() => {
      measuring.armed = true
      void whenSettled(client, signal).then((end) => {
        if (end === null || signal.cancelled) return
        recordPageView({ page, method, case_id: caseId, ms: end - start })
      })
    })
    return () => {
      signal.cancelled = true
      cancelAnimationFrame(frame)
    }
  }, [caseId, page, client])
}
