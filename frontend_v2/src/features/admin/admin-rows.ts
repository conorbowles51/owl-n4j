/** The rows of the System Logs and Background Tasks screens, as the server sends them. */

/** routers/background_tasks.py TaskResponse. */
export interface BackgroundTask {
  id: string
  task_type: string
  task_name: string
  owner?: string | null
  status: string
  created_at: string
  started_at?: string | null
  progress: { total?: number; completed?: number; failed?: number }
  error?: string | null
}

/** routers/system_logs.py LogEntry. */
export interface LogEntry {
  timestamp: string
  type: string
  origin: string
  action: string
  user?: string | null
  success: boolean
  error?: string | null
}

export interface LogsResponse {
  logs: LogEntry[]
  total: number
}

/** Rows asked for; the server keeps the newest this many. */
export const TASKS_SHOWN = 200

/** Rows asked for; the server's own limit is 1,000. */
export const LOGS_SHOWN = 500

export function taskPercent(progress: BackgroundTask["progress"]): number | null {
  if (!progress.total) return null
  return Math.min(100, Math.floor(((progress.completed ?? 0) / progress.total) * 100))
}

export function logMatches(log: LogEntry, search: string): boolean {
  const needle = search.trim().toLowerCase()
  if (!needle) return true
  return [log.action, log.user, log.error, log.type, log.origin].some((v) => v?.toLowerCase().includes(needle))
}
