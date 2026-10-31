/** Admin Speed page: what GET /api/request-speed/summary returns, and plain time formatting. */

export interface SpeedRoute {
  kind: "api" | "page"
  method: string
  route: string
  count: number
  p50_ms: number | null
  p95_ms: number | null
  max_ms: number | null
  mean_ms: number | null
  bytes: number
  errors: number
  cases: number
}

export interface SlowRequest {
  at: string
  kind: "api" | "page"
  method: string
  route: string
  case_id: string | null
  case_title: string | null
  status: number | null
  duration_ms: number
  bytes: number
  user_name: string | null
  /** When it reached its worker (at is when it finished), the worker, and its minute's context. */
  started_at?: string | null
  pid?: number | null
  pg_ms?: number | null
  /** Evidence-engine call time inside this request, summed over its calls. */
  engine_ms?: number | null
  cache?: string | null
  loop_lag_max_ms?: number | null
  host_cpu_pressure?: number | null
  fleet_cores?: number | null
}

export interface SpeedSummary {
  days: number
  routes: SpeedRoute[]
  slow: SlowRequest[]
  cases: { id: string; title: string | null; count: number }[]
  slow_row_seconds: number
  slow_keep_days: number
}

/** What GET /api/request-speed/page-cache returns: rendered PDF pages kept on disk. */
export interface PageCacheStats {
  enabled: boolean
  directory: string | null
  files?: number
  bytes?: number
  max_bytes?: number
  disk_free_fraction?: number | null
  min_free_fraction?: number
  writing?: boolean
  process?: { pid: number; hits: number; misses: number; not_modified: number; evicted_files: number }
}

/** One plain sentence about the page image store, or why new pages are not being kept. */
export function describePageCache(stats: PageCacheStats, formatBytes: (bytes: number) => string) {
  if (!stats.enabled) return "Stored page images: off. Every PDF page is drawn again on each view."
  const used = `${(stats.files ?? 0).toLocaleString()} pages, ${formatBytes(stats.bytes ?? 0)} of ${formatBytes(stats.max_bytes ?? 0)}`
  const writing = stats.writing
    ? ""
    : ` New pages are not being kept: the disk has under ${Math.round((stats.min_free_fraction ?? 0.1) * 100)}% free. Pages are still shown, drawn on each view.`
  const process = stats.process
    ? ` This server process since its start: ${stats.process.hits.toLocaleString()} served from store, ${stats.process.not_modified.toLocaleString()} already in the browser, ${stats.process.misses.toLocaleString()} drawn.`
    : ""
  return `Stored page images: ${used}.${writing}${process}`
}

export function formatDuration(ms: number | null | undefined) {
  if (ms === null || ms === undefined) return "–"
  if (ms < 1000) return `${Math.round(ms)} ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)} s`
  const seconds = Math.round(ms / 1000)
  return `${Math.floor(seconds / 60)} min ${seconds % 60} s`
}
