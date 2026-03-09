import { useQuery } from "@tanstack/react-query"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { EmptyState } from "@/components/ui/empty-state"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { FileText } from "lucide-react"
import { evidenceAPI } from "../api"

interface ProcessingLogViewerProps {
  caseId: string
  limit?: number
  polling?: boolean
}

interface LogEntry {
  timestamp: string
  level: string
  message: string
  file?: string
  [key: string]: unknown
}

const levelVariant = {
  info: "info",
  warning: "warning",
  error: "danger",
  success: "success",
  debug: "slate",
} as const

export function ProcessingLogViewer({
  caseId,
  limit = 50,
  polling = false,
}: ProcessingLogViewerProps) {
  const { data: logs, isLoading } = useQuery({
    queryKey: ["evidence-logs", caseId, limit],
    queryFn: () => evidenceAPI.logs(caseId, limit) as Promise<LogEntry[]>,
    refetchInterval: polling ? 5000 : false,
  })

  if (isLoading) {
    return (
      <div className="flex justify-center py-6">
        <LoadingSpinner size="sm" />
      </div>
    )
  }

  if (!logs?.length) {
    return (
      <EmptyState
        icon={FileText}
        title="No processing logs"
        description="Logs will appear here when files are processed"
        className="py-6"
      />
    )
  }

  return (
    <ScrollArea className="h-[200px]">
      <div className="space-y-0.5 p-2">
        {logs.map((log, i) => (
          <div
            key={i}
            className="flex items-start gap-2 rounded px-2 py-1 text-xs hover:bg-muted/50"
          >
            <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
              {new Date(log.timestamp).toLocaleTimeString()}
            </span>
            <Badge
              variant={levelVariant[log.level as keyof typeof levelVariant] ?? "slate"}
              className="shrink-0 text-[10px]"
            >
              {log.level}
            </Badge>
            <span className="min-w-0 flex-1 text-foreground">
              {log.file && (
                <span className="font-medium text-amber-500">{log.file}: </span>
              )}
              {log.message}
            </span>
          </div>
        ))}
      </div>
    </ScrollArea>
  )
}
