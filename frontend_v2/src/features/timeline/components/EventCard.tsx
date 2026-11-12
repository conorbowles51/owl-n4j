import { memo, useCallback } from "react"
import { cn } from "@/lib/cn"
import { Checkbox } from "@/components/ui/checkbox"
import { NodeBadge } from "@/components/ui/node-badge"
import { markdownToPlainText } from "@/lib/markdown-text"
import { getEventTypeColor, hasAmount, modelReadingFile } from "../api"
import type { EventFile, TimelineEvent } from "../api"
import { displayEventTime, getEventTimeValue } from "../lib/timeline-utils"
import { CheckTag, DirectionMark, MONEY } from "@/lib/data-colour"

interface EventCardProps {
  event: TimelineEvent
  /** Files a person attached to this event. */
  attachedFiles?: EventFile[]
  isSelected: boolean
  isMultiSelected: boolean
  curationMode?: boolean
  isCurationSelected?: boolean
  searchTerm: string
  highlightedEntityKeys: Set<string>
  onSelect: (key: string) => void
  onMultiSelect: (key: string) => void
  onToggleCurationSelection?: (key: string) => void
}

function highlightText(text: string, term: string) {
  if (!term.trim()) return text
  const regex = new RegExp(
    `(${term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`,
    "gi"
  )
  const parts = text.split(regex)
  return parts.map((part, i) =>
    regex.test(part) ? (
      <mark key={i} className="bg-amber-500/30 text-inherit rounded-sm px-0.5">
        {part}
      </mark>
    ) : (
      part
    )
  )
}

export const EventCard = memo(function EventCard({
  event,
  attachedFiles = [],
  isSelected,
  isMultiSelected,
  curationMode = false,
  isCurationSelected = false,
  searchTerm,
  highlightedEntityKeys,
  onSelect,
  onMultiSelect,
  onToggleCurationSelection,
}: EventCardProps) {
  const color = getEventTypeColor(event.type)
  const attached = attachedFiles
  const direction = event.direction === "credit" ? "in" : event.direction === "debit" ? "out" : null
  const active = isSelected || isMultiSelected
  const summaryText = event.summary ? markdownToPlainText(event.summary) : null
  const shownTime = displayEventTime(event)
  const timeLabel = shownTime.text
  const hasTime = Boolean(getEventTimeValue(event))
  const readFrom = modelReadingFile(event)

  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.ctrlKey || e.metaKey) {
        onMultiSelect(event.key)
      } else {
        onSelect(event.key)
      }
    },
    [event.key, onSelect, onMultiSelect]
  )

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key !== "Enter" && e.key !== " ") return
      e.preventDefault()
      if (e.ctrlKey || e.metaKey) onMultiSelect(event.key)
      else onSelect(event.key)
    },
    [event.key, onMultiSelect, onSelect]
  )

  const stopCurationClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
  }, [])

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      className={cn(
        "group w-full cursor-pointer rounded-lg border border-l-4 bg-card px-3 py-3 text-left transition-colors duration-150",
        "hover:bg-muted/40",
        active
          ? "border-brand-300 bg-brand-50 shadow-sm ring-1 ring-brand-300/40 dark:border-brand-700/60 dark:bg-brand-500/10 dark:ring-brand-600/35"
          : "border-border/80"
      )}
      style={{ borderLeftColor: color }}
      data-type-edge={event.type}
    >
      <div
        className={cn(
          "grid gap-3",
          curationMode
            ? "grid-cols-[1.5rem_4.75rem_minmax(0,1fr)]"
            : "grid-cols-[4.75rem_minmax(0,1fr)]"
        )}
      >
        {curationMode && (
          <div className="pt-0.5">
            <Checkbox
              checked={isCurationSelected}
              aria-label="Select event for timeline view"
              title={
                isCurationSelected
                  ? "Remove from selection"
                  : "Select for timeline view"
              }
              onClick={stopCurationClick}
              onKeyDown={(event) => event.stopPropagation()}
              onCheckedChange={() => onToggleCurationSelection?.(event.key)}
            />
          </div>
        )}

        <div className="flex flex-col items-start gap-1 pt-0.5">
          <span
            className={cn(
              "font-mono text-xs font-semibold leading-none tabular-nums",
              hasTime ? "text-foreground" : "text-muted-foreground"
            )}
            title={shownTime.title ?? undefined}
          >
            {timeLabel}
          </span>
          <span
            className="inline-flex max-w-full items-center gap-1 rounded-full border bg-background/70 px-1.5 py-0.5 text-[10px] font-medium leading-none"
            style={{ borderColor: `${color}40`, color }}
          >
            <span
              className="size-1.5 shrink-0 rounded-full"
              style={{ backgroundColor: color }}
            />
            <span className="truncate">{event.type}</span>
          </span>
        </div>

        <div className="min-w-0">
          <div className="flex min-w-0 items-start gap-2">
            <span className="min-w-0 flex-1 text-sm font-medium leading-snug text-foreground line-clamp-2">
              {highlightText(event.name, searchTerm)}
            </span>
            {hasAmount(event.amount) &&
              (/^\s*unknown\s*$/i.test(String(event.amount)) ? (
                <CheckTag className="shrink-0">Amount unknown · check source</CheckTag>
              ) : (
                <span className="flex shrink-0 items-baseline gap-1.5">
                  <span
                    className={cn(
                      "text-xs font-semibold tabular-nums",
                      direction ? MONEY[direction].text : "text-status-info"
                    )}
                  >
                    {event.amount}
                  </span>
                  {direction && <DirectionMark direction={direction} />}
                </span>
              ))}
          </div>

          {summaryText && (
            <p className="mt-1 text-xs text-muted-foreground line-clamp-2 leading-relaxed">
              {highlightText(summaryText, searchTerm)}
            </p>
          )}

          {readFrom && (
            <p
              className="mt-1 text-xs text-muted-foreground"
              data-model-reading=""
              title="The document model wrote this event from the file. No person has checked it, and it is not a ledger row."
            >
              Model reading, not checked · {readFrom}
            </p>
          )}

          {event.thumbnail_url && (
            <img
              src={event.thumbnail_url}
              alt={`Photo ${event.source?.label ?? ""}`.trim()}
              loading="lazy"
              className="mt-1.5 h-24 w-auto max-w-full rounded border object-cover"
            />
          )}
          {attached.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1.5" data-event-files="">
              {attached.map((file) => (
                <img
                  key={file.id}
                  src={file.thumbnail_url}
                  alt={`Attached ${file.name}`}
                  title={`${file.name}, attached by ${file.added_by}`}
                  loading="lazy"
                  className="h-14 w-auto rounded border object-cover"
                />
              ))}
            </div>
          )}
          {event.source && (
            <p className="mt-1 text-xs text-muted-foreground">
              {event.source.date_basis} ·{" "}
              {event.source.state === "snapshot"
                ? "Saved copy; source changed or removed"
                : event.source.kind === "evidence_file"
                  ? `File ${event.source.label}`
                  : event.source.kind === "transaction"
                  ? "Open payment and statement"
                  : `Open ${event.type.toLowerCase()} and supporting evidence`}
            </p>
          )}
          {event.connections.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {event.connections.map((conn) => (
                <NodeBadge
                  key={conn.key}
                  type={conn.type}
                  className={cn(
                    "text-[9px] py-0",
                    highlightedEntityKeys.has(conn.key) &&
                      "ring-1 ring-slate-400/60"
                  )}
                >
                  {conn.name}
                </NodeBadge>
              ))}
            </div>
          )}
        </div>
      </div>
    </article>
  )
})
