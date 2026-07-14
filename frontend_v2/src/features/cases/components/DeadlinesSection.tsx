import { useState } from "react"
import { CalendarClock, Pencil, Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { EmptyState } from "@/components/ui/empty-state"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { useDeadlines, useDeleteDeadline } from "../hooks/use-deadlines"
import { AddDeadlineDialog } from "./AddDeadlineDialog"
import { EditDeadlineDialog } from "./EditDeadlineDialog"
import type { CaseDeadline } from "@/types/case.types"

interface DeadlinesSectionProps {
  caseId: string
}

function getDeadlineBadge(dueDateStr: string) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const due = new Date(dueDateStr + "T00:00:00")
  const diffMs = due.getTime() - today.getTime()
  const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24))

  if (diffDays < 0) {
    return (
      <Badge className="bg-red-500/15 text-[10px] text-red-600 dark:text-red-400">Overdue</Badge>
    )
  }
  if (diffDays === 0) {
    return (
      <Badge className="bg-yellow-500/15 text-[10px] text-yellow-700 dark:text-yellow-300">
        Today
      </Badge>
    )
  }
  if (diffDays <= 7) {
    return (
      <Badge className="bg-yellow-500/15 text-[10px] text-yellow-700 dark:text-yellow-300">
        {diffDays} day{diffDays !== 1 ? "s" : ""}
      </Badge>
    )
  }
  return (
      <Badge className="bg-green-500/15 text-[10px] text-green-700 dark:text-green-400">
      {diffDays} day{diffDays !== 1 ? "s" : ""}
    </Badge>
  )
}

export function DeadlinesSection({ caseId }: DeadlinesSectionProps) {
  const { data: deadlines, isLoading } = useDeadlines(caseId)
  const deleteDeadline = useDeleteDeadline(caseId)
  const [addOpen, setAddOpen] = useState(false)
  const [editing, setEditing] = useState<CaseDeadline | null>(null)

  if (isLoading) {
    return (
      <div className="flex justify-center py-4">
        <LoadingSpinner size="sm" />
      </div>
    )
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-end">
        <Button variant="ghost" size="sm" onClick={() => setAddOpen(true)}>
          <Plus className="mr-1 size-3" />
          Add Deadline
        </Button>
      </div>

      {!deadlines?.length ? (
        <EmptyState
          icon={CalendarClock}
          title="No deadlines"
          description="Add deadlines to track important dates"
          className="py-4"
        />
      ) : (
        <div className="space-y-1">
          {deadlines.map((d) => (
            <div
              key={d.id}
              className="group flex items-center gap-2 border-b border-border/80 px-2 py-2 text-sm transition-colors last:border-b-0 hover:bg-card"
            >
              <div className="min-w-0 flex-1">
                <span className="font-display font-semibold text-foreground">{d.name}</span>
                <div className="mt-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
                  <span>
                    {new Date(d.due_date + "T00:00:00").toLocaleDateString()}
                  </span>
                  {getDeadlineBadge(d.due_date)}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-0.5 opacity-0 group-hover:opacity-100">
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="size-6"
                  onClick={() => setEditing(d)}
                >
                  <Pencil className="size-3" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="size-6"
                  onClick={() => deleteDeadline.mutate(d.id)}
                >
                  <Trash2 className="size-3" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <AddDeadlineDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        caseId={caseId}
      />

      {editing && (
        <EditDeadlineDialog
          open={!!editing}
          onOpenChange={(open) => !open && setEditing(null)}
          caseId={caseId}
          deadline={editing}
        />
      )}
    </div>
  )
}
