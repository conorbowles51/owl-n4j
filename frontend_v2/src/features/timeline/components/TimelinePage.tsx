import { useParams } from "react-router-dom"
import { Clock, Filter, ZoomIn, ZoomOut } from "lucide-react"
import { Button } from "@/components/ui/button"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { EmptyState } from "@/components/ui/empty-state"
import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"

interface TimelineEvent {
  id: string
  date: string
  type: string
  label: string
  entity_key: string
  entity_type: string
}

function useTimelineEvents(caseId: string | undefined) {
  return useQuery({
    queryKey: ["timeline", caseId],
    queryFn: () =>
      fetchAPI<TimelineEvent[]>(`/api/timeline?case_id=${caseId}`),
    enabled: !!caseId,
  })
}

export function TimelinePage() {
  const { id: caseId } = useParams()
  const { data: events, isLoading } = useTimelineEvents(caseId)

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (!events?.length) {
    return (
      <EmptyState
        icon={Clock}
        title="No timeline events"
        description="Process evidence with temporal data to populate the timeline"
      />
    )
  }

  return (
    <div className="flex h-full flex-col">
      {/* Controls */}
      <div className="flex items-center gap-2 border-b border-border px-4 py-2">
        <Button variant="ghost" size="sm">
          <Filter className="size-3.5" />
          Filters
        </Button>
        <div className="flex-1" />
        <Button variant="ghost" size="icon-sm">
          <ZoomOut className="size-3.5" />
        </Button>
        <Button variant="ghost" size="icon-sm">
          <ZoomIn className="size-3.5" />
        </Button>
      </div>

      {/* Timeline content */}
      <div className="flex-1 overflow-auto p-4">
        <div className="relative border-l-2 border-border pl-6">
          {events.map((event) => (
            <div key={event.id} className="relative mb-4 last:mb-0">
              <div className="absolute -left-[31px] top-0.5 h-3 w-3 rounded-full border-2 border-amber-500 bg-background" />
              <div className="rounded-lg border border-border p-3">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-muted-foreground">
                    {new Date(event.date).toLocaleDateString()}
                  </span>
                  <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium">
                    {event.type}
                  </span>
                </div>
                <p className="mt-1 text-sm font-medium">{event.label}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
