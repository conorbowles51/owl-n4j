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

/** services/running_work.py: one piece of work running now. */
export interface RunningWork {
  kind: "processing" | "export" | "statement_import"
  id: string
  case_id: string
  case_title?: string | null
  name: string
  status: "running"
  started_at?: string | null
  started_by?: string | null
  progress: { total?: number; completed?: number }
}

/** services/running_work.py: a stop, as answered and as listed afterwards. */
export interface StoppedWork {
  kind?: string | null
  id?: string | null
  case_id?: string | null
  name?: string | null
  status: "stopped"
  stopped_by?: string | null
  stopped_at?: string | null
  summary?: string | null
}

export interface RunningWorkList {
  scope: "all" | "owned_cases"
  tasks: RunningWork[]
  stopped: StoppedWork[]
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
