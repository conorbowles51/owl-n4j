import { useState, useRef, useEffect } from "react"
import { useQuery } from "@tanstack/react-query"
import { EmptyState } from "@/components/ui/empty-state"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { FileText, ArrowDownToLine } from "lucide-react"
import { evidenceAPI } from "../api"
interface ProcessingLogViewerProps {
  caseId: string
  limit?: number
  polling?: boolean
}

const LEVEL_COLORS: Record<string, string> = {
  info: "text-blue-400",
  warning: "text-yellow-400",
  error: "text-red-400",
  success: "text-emerald-400",
  debug: "text-gray-500",
}

const LEVELS = ["all", "info", "warning", "error"] as const

export function ProcessingLogViewer({
  caseId,
  limit = 50,
  polling = false,
}: ProcessingLogViewerProps) {
  const [levelFilter, setLevelFilter] = useState<string>("all")
  const [pinBottom, setPinBottom] = useState(true)
  const scrollRef = useRef<HTMLDivElement>(null)

  const { data: logs, isLoading } = useQuery({
    queryKey: ["evidence-logs", caseId, limit],
    queryFn: () => evidenceAPI.logs(caseId, limit),
    refetchInterval: polling ? 5000 : false,
  })

  // Auto-scroll to bottom
  useEffect(() => {
    if (pinBottom && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [logs, pinBottom])

  const filtered =
    levelFilter === "all"
      ? logs
      : logs?.filter((log) => log.level === levelFilter)

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
    <div className="flex flex-col">
      {/* Level filter bar */}
      <div className="flex items-center justify-between border-b border-white/10 px-3 py-1.5 bg-[#161b22]">
        <div className="flex gap-1">
          {LEVELS.map((level) => (
            <button
              key={level}
              onClick={() => setLevelFilter(level)}
              className={`rounded px-2 py-0.5 text-[10px] font-medium transition-colors ${
                levelFilter === level
                  ? "bg-white/10 text-white"
                  : "text-gray-500 hover:text-gray-300"
              }`}
            >
              {level.charAt(0).toUpperCase() + level.slice(1)}
            </button>
          ))}
        </div>
        <button
          onClick={() => setPinBottom(!pinBottom)}
          className={`rounded p-1 transition-colors ${
            pinBottom ? "text-amber-500" : "text-gray-500 hover:text-gray-300"
          }`}
          title={pinBottom ? "Auto-scroll on" : "Auto-scroll off"}
        >
          <ArrowDownToLine className="size-3" />
        </button>
      </div>

      {/* Log entries */}
      <div
        ref={scrollRef}
        className="h-[200px] overflow-auto p-2 font-mono text-[11px] leading-relaxed"
      >
        {filtered?.map((log, i) => (
          <div
            key={i}
            className="flex items-start gap-2 rounded px-2 py-0.5 hover:bg-white/5"
          >
            <span className="shrink-0 text-gray-600">
              {new Date(log.timestamp).toLocaleTimeString()}
            </span>
            <span
              className={`shrink-0 w-12 text-right uppercase ${
                LEVEL_COLORS[log.level] ?? "text-gray-500"
              }`}
            >
              {log.level}
            </span>
            <span className="min-w-0 flex-1 text-gray-300">
              {log.file && (
                <span className="text-amber-400">{log.file}: </span>
              )}
              {log.message}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
