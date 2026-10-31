import { useEffect, useRef } from "react"
import { useQueryClient, type QueryClient } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { viewDetail, type ViewDetail } from "@/lib/browser-timing"

/**
 * Time from opening a Financial view to its data being on screen, as the person sees it.
 *
 * "Opened" (LOAD): the browser loaded this Financial address directly, so the time runs from the
 * browser's navigation start (performance time origin). "Switched to" (VIEW): the view or case
 * changed inside the app, so the time runs from that change. Either way it ends at the first
 * frame painted after every request the view started has returned. A view the person leaves
 * before that (another view, case or page, or closing the tab) is recorded as LEFT with how long they
 * waited, so the slowest loads are not lost. Timings are queued and posted in small batches; a failed post is dropped, never
 * retried and never shown. Uses only performance.now, timers and fetch (safe over plain http).
 *
 * The same timing runs for every route of the app (lib/route-speed.ts, page names like "case/timeline"),
 * and each row carries what the browser spent on the view (lib/browser-timing.ts).
 */

export interface PageView {
  page: string
  method: "LOAD" | "VIEW" | "LEFT"
  case_id: string | null
  ms: number
  detail?: ViewDetail
}

const ENDPOINT = "/api/request-speed/page-views"
const BATCH = 20
const FLUSH_MS = 5000
const MAX_MS = 600000 // the server accepts up to 10 minutes
const GIVE_UP_MS = MAX_MS

const queue: PageView[] = []
let timer: ReturnType<typeof setTimeout> | null = null
const loadTaken = new Set<string>()
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
  queue.push({ ...view, ms: Math.min(MAX_MS, Math.max(0, Math.round(view.ms))) })
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

/** True once per channel: the document was loaded at this very address and nothing has been timed yet. */
export function takeDocumentLoad(pathname: string, channel = "financial") {
  if (loadTaken.has(channel)) return false
  loadTaken.add(channel)
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
  useViewSpeed(caseId ?? null, caseId ? page : null, "financial")
}

/**
 * Times each view named `page` (null: not timed). `channel` keeps the opening (LOAD) of one timer
 * separate from another's, so the route timer and the Financial view timer both see the same opening.
 */
export function useViewSpeed(caseId: string | null, page: string | null, channel: string) {
  const client = useQueryClient()
  const current = useRef<{ start: number; method: "LOAD" | "VIEW"; armed: boolean; signal: { cancelled: boolean } } | null>(null)

  useEffect(() => {
    if (!page || typeof performance === "undefined") return
    if (document.visibilityState === "hidden") {
      takeDocumentLoad(window.location.pathname, channel) // a hidden opening is not timed, and not reused later
      return
    }
    const previous = current.current
    // A view set by the address in the same frame as opening (not by the person) keeps the
    // opening's start: it is the same page load.
    const inherit = previous && !previous.armed
    const method = inherit ? previous.method : takeDocumentLoad(window.location.pathname, channel) ? "LOAD" : "VIEW"
    const start = inherit ? previous.start : method === "LOAD" ? 0 : performance.now()
    const signal = { cancelled: false }
    const measuring = { start, method, armed: false, signal }
    current.current = measuring
    let settled = false
    // Wait one frame so the view's own requests have started before looking for quiet.
    const frame = requestAnimationFrame(() => {
      measuring.armed = true
      void whenSettled(client, signal).then((end) => {
        if (end === null || signal.cancelled) return
        settled = true
        recordPageView({ page, method, case_id: caseId, ms: end - start, detail: viewDetail(start, end, method === "LOAD") })
      })
    })
    const leave = () => {
      // Left by the person before the data was shown (not the same-frame address sync).
      if (measuring.armed && !settled && !signal.cancelled) {
        const now = performance.now()
        recordPageView({ page, method: "LEFT", case_id: caseId, ms: now - start, detail: viewDetail(start, now, method === "LOAD") })
      }
    }
    // Closing or reloading the tab runs no React cleanup: record the leave and post it now.
    const unload = () => {
      leave()
      signal.cancelled = true
      flushPageViews(true)
    }
    window.addEventListener("pagehide", unload)
    return () => {
      window.removeEventListener("pagehide", unload)
      leave()
      signal.cancelled = true
      cancelAnimationFrame(frame)
    }
  }, [caseId, page, channel, client])
}
