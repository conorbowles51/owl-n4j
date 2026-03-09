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

interface LogEntry {
  timestamp: string
  level: string
  message: string
  source?: string
}

export function SystemLogsPage() {
  const [level, setLevel] = useState("all")
  const [search, setSearch] = useState("")

  const { data: logs = [], isLoading, refetch } = useQuery({
    queryKey: ["admin", "logs", level],
    queryFn: () => {
      const qs = new URLSearchParams()
      if (level !== "all") qs.set("level", level)
      return fetchAPI<LogEntry[]>(`/api/admin/logs?${qs}`)
    },
    refetchInterval: 10000,
  })

  const filtered = logs.filter(
    (log) =>
      log.message.toLowerCase().includes(search.toLowerCase()) ||
      (log.source?.toLowerCase().includes(search.toLowerCase()) ?? false)
  )

  const levelColor = (lvl: string) => {
    switch (lvl.toLowerCase()) {
      case "error": return "text-red-500"
      case "warning": return "text-amber-500"
      case "info": return "text-blue-500"
      case "debug": return "text-muted-foreground"
      default: return "text-foreground"
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-border px-4 py-2">
        <FileText className="size-4 text-amber-500" />
        <span className="text-sm font-semibold">System Logs</span>
        <div className="flex-1" />
        <Input
          placeholder="Filter logs..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <Select value={level} onValueChange={setLevel}>
          <SelectTrigger className="w-28">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            <SelectItem value="error">Error</SelectItem>
            <SelectItem value="warning">Warning</SelectItem>
            <SelectItem value="info">Info</SelectItem>
            <SelectItem value="debug">Debug</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="ghost" size="sm" onClick={() => refetch()}>
          <RefreshCw className="size-3.5" />
        </Button>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-2 font-mono text-xs">
          {filtered.map((log, i) => (
            <div
              key={i}
              className="flex gap-2 rounded px-2 py-0.5 hover:bg-muted/30"
            >
              <span className="shrink-0 text-muted-foreground">
                {new Date(log.timestamp).toLocaleTimeString()}
              </span>
              <span className={cn("w-14 shrink-0 uppercase", levelColor(log.level))}>
                {log.level}
              </span>
              {log.source && (
                <span className="shrink-0 text-muted-foreground">
                  [{log.source}]
                </span>
              )}
              <span className="break-all">{log.message}</span>
            </div>
          ))}
          {filtered.length === 0 && (
            <p className="py-8 text-center text-muted-foreground">
              {isLoading ? "Loading logs..." : "No log entries"}
            </p>
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
