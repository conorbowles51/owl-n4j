import { Archive, ArchiveRestore, CalendarClock, Trash2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { RoleBadge } from "./RoleBadge"
import { cn } from "@/lib/cn"
import type { Case } from "@/types/case.types"

interface CaseListItemProps {
  caseData: Case
  isSelected: boolean
  onSelect: () => void
  onDelete?: () => void
  onArchiveToggle?: () => void
}

export function CaseListItem({
  caseData,
  isSelected,
  onSelect,
  onDelete,
  onArchiveToggle,
}: CaseListItemProps) {
  return (
    <div
      className={cn(
        "group flex w-full items-start gap-2.5 rounded-md border border-transparent px-3 py-2.5 text-left transition-[background-color,border-color,box-shadow] duration-150 focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/30",
        isSelected
          ? "border-brand-200 bg-brand-50 shadow-[inset_2px_0_0_var(--color-brand-400)] dark:border-brand-700/40 dark:bg-brand-500/10"
          : "hover:border-border hover:bg-panel-raised/75"
      )}
    >
      <button
        type="button"
        aria-pressed={isSelected}
        onClick={onSelect}
        className="min-w-0 flex-1 cursor-pointer text-left outline-none"
      >
        <div className="flex items-center gap-2">
          <p className="font-display truncate text-sm font-semibold tracking-[-0.018em] text-foreground">
            {caseData.title}
          </p>
          {caseData.archived && <Badge variant="slate">Archived</Badge>}
        </div>
        <div className="mt-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
          {caseData.owner_name && <span>{caseData.owner_name}</span>}
          <span>{new Date(caseData.updated_at).toLocaleDateString()}</span>
        </div>
        {caseData.next_deadline_date && (
          <div className={cn(
            "mt-0.5 flex items-center gap-1 text-[11px]",
            new Date(caseData.next_deadline_date + "T00:00:00") < new Date(new Date().toDateString())
              ? "text-destructive"
              : "text-muted-foreground"
          )}>
            <CalendarClock className="size-3" />
            <span className="truncate">
              {caseData.next_deadline_name} &middot;{" "}
              {new Date(caseData.next_deadline_date + "T00:00:00").toLocaleDateString()}
            </span>
          </div>
        )}
      </button>

      <div className="flex shrink-0 items-center gap-1.5">
        <RoleBadge role={caseData.user_role} />
        {onArchiveToggle && (
          <Button
            variant="ghost"
            size="icon-sm"
            className="size-6 opacity-0 group-hover:opacity-100"
            title={caseData.archived ? "Unarchive case" : "Archive case"}
            onClick={(e) => {
              e.stopPropagation()
              onArchiveToggle()
            }}
          >
            {caseData.archived ? (
              <ArchiveRestore className="size-3" />
            ) : (
              <Archive className="size-3" />
            )}
          </Button>
        )}
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
    </div>
  )
}
