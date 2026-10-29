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
}

export interface SpeedSummary {
  days: number
  routes: SpeedRoute[]
  slow: SlowRequest[]
  cases: { id: string; title: string | null; count: number }[]
  slow_row_seconds: number
  slow_keep_days: number
}

export function formatDuration(ms: number | null | undefined) {
  if (ms === null || ms === undefined) return "–"
  if (ms < 1000) return `${Math.round(ms)} ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)} s`
  const seconds = Math.round(ms / 1000)
  return `${Math.floor(seconds / 60)} min ${seconds % 60} s`
}
