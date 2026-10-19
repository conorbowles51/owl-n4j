import type { ReactNode } from "react"
import { ChevronDown, ChevronRight, Pencil, CalendarPlus } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { CaseworkEntry } from "@/features/workspace/casework-api"
import {
  findingDraft,
  findingKindLabel,
  findingPaymentIds,
} from "../lib/investigator-finding"

export function FinancialFindingCard({
  entry,
  expanded,
  onToggle,
  canEdit,
  onEdit,
  onTimeline,
  included,
  onInclude,
  selectionDisabled,
  children,
}: {
  entry: CaseworkEntry
  expanded: boolean
  onToggle: () => void
  canEdit: boolean
  onEdit: () => void
  onTimeline: () => void
  included: boolean
  onInclude: (included: boolean) => void
  selectionDisabled: boolean
  children: ReactNode
}) {
  const draft = findingDraft(entry)
  const title = entry.title || "Untitled note"
  const report = entry.tags.includes("financial-report")
  const payments = findingPaymentIds(entry).length
  const Chevron = expanded ? ChevronDown : ChevronRight
  return (
    <article
      className="finance-panel finding-card rounded-lg border"
      data-expanded={expanded}
      aria-label={title}
      data-finance-tone={
        entry.tags.includes("financial-workspace") && draft.kind === "question"
          ? "review"
          : "work"
      }
    >
      <div className="finding-card-summary">
        <p className="finance-badge capitalize">
          {entry.tags.includes("financial-workspace")
            ? `${findingKindLabel(draft.kind)} · ${draft.progress.replace("-", " ")}`
            : report
              ? "Saved report"
              : "Saved note or analysis"}
        </p>
        <h3 className="font-semibold leading-snug break-words">
          <button
            type="button"
            className="flex w-full items-start gap-1 text-left hover:underline rounded focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring"
            aria-expanded={expanded}
            aria-controls={`finding-details-${entry.id}`}
            onClick={(event) => {
              const button = event.currentTarget
              onToggle()
              requestAnimationFrame(() =>
                button.scrollIntoView({ block: "nearest" })
              )
            }}
          >
            <Chevron className="size-4 shrink-0 mt-0.5" aria-hidden="true" />
            {title}
          </button>
        </h3>
        {canEdit && !report && (
          <div className="flex flex-wrap gap-2" aria-label="Finding actions">
            <Button size="sm" className="min-h-9" onClick={onTimeline}>
              <CalendarPlus aria-hidden="true" /> Add to Timeline
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="min-h-9"
              onClick={onEdit}
            >
              <Pencil aria-hidden="true" /> Edit
            </Button>
          </div>
        )}
        <div className="mt-auto space-y-2 pt-1">
          {payments > 0 && (
            <p className="text-sm">
              {payments} supporting {payments === 1 ? "payment" : "payments"}
            </p>
          )}
          <p className="text-xs text-muted-foreground break-words">
            {entry.author_name || entry.author_email || "Author not recorded"}
            {entry.updated_at
              ? ` · ${new Date(entry.updated_at).toLocaleDateString()}`
              : ""}
          </p>
          {canEdit && !report && (
            <label className="flex gap-2 items-center text-sm">
              <input
                type="checkbox"
                aria-label={`Include ${title} in report`}
                checked={included}
                disabled={selectionDisabled}
                onChange={(event) => onInclude(event.target.checked)}
              />
              Include in report
            </label>
          )}
        </div>
      </div>
      {expanded && (
        <div
          id={`finding-details-${entry.id}`}
          className="min-w-0 border-t pt-4 space-y-3"
        >
          {children}
        </div>
      )}
    </article>
  )
}
