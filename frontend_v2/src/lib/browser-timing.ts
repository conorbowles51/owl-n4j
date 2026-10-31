/**
 * What the browser itself spent on a page view, sent with each page-speed row (request_speed_pages).
 *
 * Everything here works on plain http (an insecure context): Navigation and Resource Timing, the
 * "longtask" observer, performance.memory and navigator.connection (the last three are Chromium only and
 * are left out where missing, never guessed). Observers are passive and buffered; nothing here blocks
 * the page or makes a request.
 *
 * Per view, over the resources that started between the view's start and its end:
 *  - resources, resource_bytes: how many, and bytes over the network (0 for a cached file);
 *  - queue_max_ms, queue_total_ms: from the request being made to it leaving the browser (requestStart),
 *    which is where HTTP/1.1's 6-connections-per-host queue, DNS and connecting show up;
 *  - transfer_total_ms: first byte to last byte; largest_*: the longest request, its route shape
 *    (ids replaced by {id}, no query) and its bytes;
 *  - longest_task_ms, long_tasks: main-thread tasks over 50 ms;
 *  - nav_* (opening only): response start, DOM ready and load, and the page's bytes.
 */

export type ViewDetail = Record<string, number | string | null>

const KEEP = 3000
const resources: PerformanceResourceTiming[] = []
const longTasks: { start: number; duration: number }[] = []
let observing = false

function observe() {
  if (observing || typeof PerformanceObserver === "undefined") return
  observing = true
  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) resources.push(entry as PerformanceResourceTiming)
      if (resources.length > KEEP) resources.splice(0, resources.length - KEEP)
    }).observe({ type: "resource", buffered: true })
  } catch {
    /* no resource timing */
  }
  try {
    if (PerformanceObserver.supportedEntryTypes?.includes("longtask")) {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) longTasks.push({ start: entry.startTime, duration: entry.duration })
        if (longTasks.length > KEEP) longTasks.splice(0, longTasks.length - KEEP)
      }).observe({ type: "longtask", buffered: true })
    }
  } catch {
    /* no long tasks (not Chromium) */
  }
}

observe()

const ID = /^([0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}|\d+|[0-9a-f]{16,})$/i

/** "/api/evidence/{id}/page/{id}" from a same-origin URL; null for another origin. */
export function routeShape(url: string): string | null {
  try {
    const parsed = new URL(url, window.location.href)
    if (parsed.origin !== window.location.origin) return null
    const parts = parsed.pathname.split("/").map((part) => {
      if (ID.test(part)) return "{id}"
      // A file name outside the built assets could name evidence: keep only its shape.
      if (part.includes(".") && !parsed.pathname.startsWith("/assets/")) return "{file}"
      return /^[A-Za-z0-9_.-]*$/.test(part) ? part : "{x}"
    })
    return parts.join("/").slice(0, 160) || "/"
  } catch {
    return null
  }
}

const round = (value: number) => Math.round(value * 10) / 10

/** Figures for a view that ran from `start` to `end` (performance.now times). */
export function viewDetail(start: number, end: number, opening: boolean): ViewDetail {
  const detail: ViewDetail = {}
  let count = 0
  let bytes = 0
  let queueMax = 0
  let queueTotal = 0
  let transferTotal = 0
  let largest: PerformanceResourceTiming | null = null
  for (const entry of resources) {
    if (entry.startTime < start - 1 || entry.startTime > end) continue
    count += 1
    bytes += entry.transferSize || 0
    if (entry.requestStart > 0) {
      const queued = Math.max(0, entry.requestStart - entry.startTime)
      queueMax = Math.max(queueMax, queued)
      queueTotal += queued
    }
    if (entry.responseStart > 0) transferTotal += Math.max(0, entry.responseEnd - entry.responseStart)
    if (!largest || entry.duration > largest.duration) largest = entry
  }
  detail.resources = count
  detail.resource_bytes = bytes
  detail.queue_max_ms = round(queueMax)
  detail.queue_total_ms = round(queueTotal)
  detail.transfer_total_ms = round(transferTotal)
  if (largest) {
    detail.largest_ms = round(largest.duration)
    detail.largest_route = routeShape(largest.name)
    detail.largest_bytes = largest.transferSize || 0
  }
  let longest = 0
  let tasks = 0
  for (const task of longTasks) {
    if (task.start + task.duration < start || task.start > end) continue
    tasks += 1
    longest = Math.max(longest, task.duration)
  }
  if (observing && PerformanceObserver.supportedEntryTypes?.includes("longtask")) {
    detail.long_tasks = tasks
    detail.longest_task_ms = round(longest)
  }
  if (opening) {
    const nav = performance.getEntriesByType?.("navigation")?.[0] as PerformanceNavigationTiming | undefined
    if (nav) {
      detail.nav_response_ms = round(nav.responseStart)
      detail.nav_dom_ms = round(nav.domContentLoadedEventEnd)
      if (nav.loadEventEnd > 0) detail.nav_load_ms = round(nav.loadEventEnd)
      detail.nav_bytes = nav.transferSize || 0
    }
  }
  const memory = (performance as unknown as { memory?: { usedJSHeapSize: number; jsHeapSizeLimit: number } }).memory
  if (memory) {
    detail.heap_used_mb = round(memory.usedJSHeapSize / 1048576)
    detail.heap_limit_mb = round(memory.jsHeapSizeLimit / 1048576)
  }
  const connection = (navigator as unknown as { connection?: { effectiveType?: string; downlink?: number; rtt?: number } })
    .connection
  if (connection) {
    if (connection.effectiveType) detail.effective_type = connection.effectiveType
    if (typeof connection.downlink === "number") detail.downlink_mbps = connection.downlink
    if (typeof connection.rtt === "number") detail.rtt_ms = connection.rtt
  }
  return detail
}

/** For tests: forget what has been observed. */
export function resetBrowserTiming() {
  resources.length = 0
  longTasks.length = 0
}

/** For tests: add an observed entry. */
export function noteForTest(kind: "resource", entry: Partial<PerformanceResourceTiming>): void
export function noteForTest(kind: "longtask", entry: { start: number; duration: number }): void
export function noteForTest(kind: string, entry: unknown) {
  if (kind === "resource") resources.push(entry as PerformanceResourceTiming)
  else longTasks.push(entry as { start: number; duration: number })
}
