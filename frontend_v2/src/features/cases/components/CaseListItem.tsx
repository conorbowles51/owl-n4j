import { CalendarClock, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { RoleBadge } from "./RoleBadge"
import { cn } from "@/lib/cn"
import type { Case } from "@/types/case.types"

interface CaseListItemProps {
  caseData: Case
  isSelected: boolean
  onSelect: () => void
  onDelete?: () => void
}

export function CaseListItem({
  caseData,
  isSelected,
  onSelect,
  onDelete,
}: CaseListItemProps) {
  return (
    <button
      onClick={onSelect}
      className={cn(
        "group flex w-full items-start gap-2.5 rounded-md px-3 py-2.5 text-left transition-colors",
        isSelected
          ? "bg-amber-500/10 ring-1 ring-amber-500/30"
          : "hover:bg-accent/50"
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-medium text-foreground">
            {caseData.title}
          </p>
        </div>
        <div className="mt-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
          {caseData.owner_name && <span>{caseData.owner_name}</span>}
          <span>{new Date(caseData.updated_at).toLocaleDateString()}</span>
        </div>
        {caseData.next_deadline_date && (
          <div className={cn(
            "mt-0.5 flex items-center gap-1 text-[11px]",
            new Date(caseData.next_deadline_date + "T00:00:00") < new Date(new Date().toDateString())
              ? "text-red-400"
              : "text-muted-foreground"
          )}>
            <CalendarClock className="size-3" />
            <span className="truncate">
              {caseData.next_deadline_name} &middot;{" "}
              {new Date(caseData.next_deadline_date + "T00:00:00").toLocaleDateString()}
            </span>
          </div>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-1.5">
        <RoleBadge role={caseData.user_role} />
        {onDelete && (
          <Button
            variant="ghost"
            size="icon-sm"
            className="size-6 opacity-0 group-hover:opacity-100"
            onClick={(e) => {
              e.stopPropagation()
              onDelete()
            }}
          >
            <Trash2 className="size-3" />
          </Button>
        )}
      </div>
    </button>
  )
}
