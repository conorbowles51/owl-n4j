import { useMemo, useState } from "react"
import { History } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { useInvestigationTimeline } from "../hooks/use-workspace"
import { formatWorkspaceDateTime } from "../lib/format-date"

interface TimelineSectionProps {
  caseId: string
}

export function TimelineSection({ caseId }: TimelineSectionProps) {
  const { data: events = [], isLoading } = useInvestigationTimeline(caseId)
  const [threadFilter, setThreadFilter] = useState("all")
  const [typeFilter, setTypeFilter] = useState("all")

  const threads = useMemo(
    () => ["all", ...new Set(events.map((event) => event.thread).filter(Boolean))],
    [events],
  )
  const types = useMemo(
    () => ["all", ...new Set(events.map((event) => event.type).filter(Boolean))],
    [events],
  )

  const filtered = useMemo(
    () =>
      [...events]
        .filter((event) => threadFilter === "all" || event.thread === threadFilter)
        .filter((event) => typeFilter === "all" || event.type === typeFilter)
        .sort((a, b) => (a.date < b.date ? 1 : -1)),
    [events, threadFilter, typeFilter],
  )

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <History className="size-4 text-sky-500" />
        <h2 className="text-sm font-semibold">Timeline</h2>
        <Badge variant="slate" className="h-5 px-1.5 text-[10px]">
          {events.length}
        </Badge>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-1">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Thread
          </p>
          <select
            value={threadFilter}
            onChange={(event) => setThreadFilter(event.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-xs"
          >
            {threads.map((thread) => (
              <option key={thread} value={thread}>
                {thread === "all" ? "All Threads" : thread}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-1">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Type
          </p>
          <select
            value={typeFilter}
            onChange={(event) => setTypeFilter(event.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-xs"
          >
            {types.map((type) => (
              <option key={type} value={type}>
                {type === "all" ? "All Types" : type}
              </option>
            ))}
          </select>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((index) => (
            <div key={index} className="h-16 animate-pulse rounded-lg bg-muted/30" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border py-10 text-center text-xs text-muted-foreground">
          No timeline events match the current filters.
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((event) => (
            <div key={event.id} className="rounded-lg border border-border p-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline" className="text-[10px]">
                  {event.thread}
                </Badge>
                <Badge variant="slate" className="text-[10px]">
                  {event.type}
                </Badge>
                <span className="text-[10px] text-muted-foreground">
                  {formatWorkspaceDateTime(event.date)}
                </span>
              </div>
              <p className="mt-2 text-xs font-medium">{event.title}</p>
              {event.description && (
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  {event.description}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
