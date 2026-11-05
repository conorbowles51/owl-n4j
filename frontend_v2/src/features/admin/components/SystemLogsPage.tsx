import { useState } from "react"
import { FileText, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { cn } from "@/lib/cn"

/** The server's row (routers/system_logs.py LogEntry). */
interface LogEntry {
  timestamp: string
  type: string
  origin: string
  action: string
  user?: string | null
  success: boolean
  error?: string | null
}

interface LogsResponse {
  logs: LogEntry[]
  total: number
}

/** Rows asked for; the server's own limit is 1,000. */
export const LOGS_SHOWN = 500

const words = (value: string) => value.replace(/_/g, " ")

export function logMatches(log: LogEntry, search: string): boolean {
  const needle = search.trim().toLowerCase()
  if (!needle) return true
  return [log.action, log.user, log.error, log.type, log.origin].some((v) => v?.toLowerCase().includes(needle))
}

export function SystemLogsPage() {
  const [outcome, setOutcome] = useState("all")
  const [search, setSearch] = useState("")

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["admin", "logs", outcome],
    queryFn: () => {
      const qs = new URLSearchParams({ limit: String(LOGS_SHOWN) })
      if (outcome !== "all") qs.set("success_only", outcome === "succeeded" ? "true" : "false")
      return fetchAPI<LogsResponse>(`/api/system-logs?${qs}`)
    },
    refetchInterval: 10000,
  })
  const logs = data?.logs ?? []
  const total = data?.total ?? 0
  const filtered = logs.filter((log) => logMatches(log, search))

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="flex items-center gap-2 border-b border-border bg-card px-4 py-2">
        <FileText className="size-4 text-amber-500" />
        <span className="font-display text-sm font-semibold">System Logs</span>
        <div className="flex-1" />
        <Input
          placeholder="Filter logs..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <Select value={outcome} onValueChange={setOutcome}>
          <SelectTrigger className="w-28" aria-label="Outcome">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
            <SelectItem value="succeeded">Succeeded</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="ghost" size="sm" onClick={() => refetch()}>
          <RefreshCw className="size-3.5" />
        </Button>
      </div>

      {total > logs.length && (
        <p className="border-b border-border px-4 py-1 text-xs text-muted-foreground">
          Showing the newest {logs.length.toLocaleString()} of {total.toLocaleString()} entries; the filter reads only these.
        </p>
      )}

      <ScrollArea className="flex-1">
        <div className="p-2 font-mono text-xs">
          {filtered.map((log, i) => (
            <div
              key={i}
              className="flex gap-2 rounded px-2 py-0.5 hover:bg-muted/30"
            >
              <span className="shrink-0 text-muted-foreground">
                {new Date(log.timestamp).toLocaleString()}
              </span>
              <span className={cn("w-14 shrink-0", log.success ? "text-muted-foreground" : "text-red-500")}>
                {log.success ? "ok" : "failed"}
              </span>
              <span className="shrink-0 text-muted-foreground">
                [{words(log.type)} · {log.origin}]
              </span>
              <span className="break-all">
                {log.action}
                {log.user && <span className="text-muted-foreground"> · {log.user}</span>}
                {log.error && <span className="text-red-500"> · {log.error}</span>}
              </span>
            </div>
          ))}
          {isError ? (
            <p role="alert" className="py-8 text-center text-red-500">
              System logs could not be read: {error?.message}
            </p>
          ) : filtered.length === 0 && (
            <p className="py-8 text-center text-muted-foreground">
              {isLoading ? "Loading logs..." : "No log entries"}
            </p>
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
