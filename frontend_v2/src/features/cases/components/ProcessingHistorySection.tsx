import { useRef, useEffect } from "react"
import { Terminal } from "lucide-react"
import { EmptyState } from "@/components/ui/empty-state"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { useEvidenceLogs } from "../hooks/use-case-evidence"

interface ProcessingHistorySectionProps {
  caseId: string
}

interface LogEntry {
  timestamp?: string
  message?: string
  level?: string
  status?: string
  [key: string]: unknown
}

const levelColor: Record<string, string> = {
  error: "text-red-400",
  warning: "text-yellow-400",
  info: "text-blue-400",
  success: "text-emerald-400",
}

export function ProcessingHistorySection({
  caseId,
}: ProcessingHistorySectionProps) {
  const { data: logs, isLoading } = useEvidenceLogs(caseId)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [logs])

  if (isLoading) {
    return (
      <div className="flex justify-center py-4">
        <LoadingSpinner size="sm" />
      </div>
    )
  }

  const entries = (logs ?? []) as LogEntry[]

  if (entries.length === 0) {
    return (
      <EmptyState
        icon={Terminal}
        title="No processing logs"
        description="Logs appear when evidence is processed"
        className="py-4"
      />
    )
  }

  return (
    <div
      ref={scrollRef}
      className="max-h-64 overflow-auto rounded-md border border-border bg-slate-950 p-3 font-mono text-[11px] leading-relaxed"
    >
      {entries.map((log, i) => {
        const level = (log.level ?? log.status ?? "info").toLowerCase()
        const color = levelColor[level] ?? "text-slate-400"
        const time = log.timestamp
          ? new Date(log.timestamp).toLocaleTimeString()
          : ""
        const msg =
          log.message ??
          (typeof log === "string" ? log : JSON.stringify(log))

        return (
          <div key={i} className="flex gap-2">
            {time && (
              <span className="shrink-0 text-slate-600">{time}</span>
            )}
            <span className={color}>
              [{level.toUpperCase()}]
            </span>
            <span className="text-slate-300">{msg}</span>
          </div>
        )
      })}
    </div>
  )
}
