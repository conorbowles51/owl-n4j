import { useEffect, useMemo, useState } from "react"
import {
  Activity,
  ArrowDownWideNarrow,
  ArrowUpWideNarrow,
  Layers,
  Loader2,
  Mail,
  MessageSquare,
  Phone,
  X,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/cn"

import { useCommsBetween } from "../../hooks/use-cellebrite"
import type { CommsItem, CommsType } from "../../types"
import { compactNumber } from "../shared/cellebrite-format"
import {
  itemId,
  itemKind,
  messageTitle,
  partyName,
  previewText,
  recipients,
  sender,
  shortDate,
  sourceAppLabel,
} from "./commsUtils"

type SortMode = "desc" | "asc" | "type"

export function CommsTimelineFlyover({
  caseId,
  reportKeys,
  fromKeys,
  toKeys,
  participantKeys,
  activeTypes,
  activeApps,
  startDate,
  endDate,
  onClose,
  onItemSelect,
}: {
  caseId: string
  reportKeys: string[] | null
  fromKeys: string[] | null
  toKeys: string[] | null
  participantKeys: string[] | null
  activeTypes: Set<CommsType>
  activeApps: Set<string>
  startDate: string
  endDate: string
  onClose: () => void
  onItemSelect: (item: CommsItem) => void
}) {
  const [sortMode, setSortMode] = useState<SortMode>("desc")
  const query = useCommsBetween(
    caseId,
    {
      reportKeys,
      fromKeys,
      toKeys,
      participantKeys,
      sourceApps: activeApps.size ? [...activeApps] : null,
      types: activeTypes.size ? [...activeTypes] : null,
      startDate: startDate || null,
      endDate: endDate || null,
      limit: 2000,
      sort: sortMode === "asc" ? "asc" : "desc",
    },
    true
  )

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose()
    }
    document.addEventListener("keydown", onKeyDown)
    return () => document.removeEventListener("keydown", onKeyDown)
  }, [onClose])

  const items = useMemo(() => {
    const rows = query.data?.items ?? []
    if (sortMode !== "type") return rows
    const rank: Record<string, number> = { message: 0, call: 1, email: 2 }
    return [...rows].sort((a, b) => {
      const byType = (rank[itemKind(a)] ?? 9) - (rank[itemKind(b)] ?? 9)
      if (byType !== 0) return byType
      return String(b.timestamp ?? "").localeCompare(String(a.timestamp ?? ""))
    })
  }, [query.data?.items, sortMode])

  const total = query.data?.total ?? items.length

  return (
    <div className="absolute inset-x-3 bottom-3 z-20 max-h-[50vh] overflow-hidden rounded-md border border-border bg-card shadow-2xl">
      <div className="flex h-10 items-center gap-2 border-b border-border bg-card px-3">
        <Activity className="size-4 text-amber-500" />
        <span className="text-xs font-semibold">Conversation timeline</span>
        <span className="text-[11px] text-muted-foreground">
          across current filters
        </span>
        {query.isLoading && <Loader2 className="size-3.5 animate-spin text-muted-foreground" />}
        <Badge variant="slate" className="ml-auto">{compactNumber(total)} items</Badge>
        <SortButton sortMode={sortMode} onChange={setSortMode} />
        <Button type="button" variant="ghost" size="icon-sm" onClick={onClose}>
          <X className="size-3.5" />
        </Button>
      </div>
      <div className="max-h-[calc(50vh-2.5rem)] overflow-y-auto">
        {items.length === 0 && !query.isLoading ? (
          <div className="px-4 py-8 text-center text-xs text-muted-foreground">
            No communications in this timeline.
          </div>
        ) : (
          items.map((item, index) => (
            <TimelineRow
              key={`${itemId(item, "timeline")}-${index}`}
              item={item}
              onSelect={() => onItemSelect(item)}
            />
          ))
        )}
      </div>
    </div>
  )
}

function SortButton({
  sortMode,
  onChange,
}: {
  sortMode: SortMode
  onChange: (mode: SortMode) => void
}) {
  const [open, setOpen] = useState(false)
  const options: { key: SortMode; label: string; icon: typeof ArrowDownWideNarrow }[] = [
    { key: "desc", label: "Newest first", icon: ArrowDownWideNarrow },
    { key: "asc", label: "Oldest first", icon: ArrowUpWideNarrow },
    { key: "type", label: "By type", icon: Layers },
  ]
  const active = options.find((option) => option.key === sortMode) ?? options[0]
  const ActiveIcon = active.icon
  return (
    <div className="relative">
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="h-7 gap-1.5 text-xs"
        onClick={() => setOpen((value) => !value)}
      >
        <ActiveIcon className="size-3.5" />
        {active.label}
      </Button>
      {open && (
        <div className="absolute right-0 top-full z-30 mt-1 w-36 rounded-md border border-border bg-popover p-1 shadow-xl">
          {options.map((option) => {
            const Icon = option.icon
            return (
              <button
                key={option.key}
                type="button"
                onClick={() => {
                  onChange(option.key)
                  setOpen(false)
                }}
                className={cn(
                  "flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs",
                  sortMode === option.key ? "bg-amber-500/10 text-foreground" : "text-muted-foreground hover:bg-muted"
                )}
              >
                <Icon className="size-3.5" />
                {option.label}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

function TimelineRow({ item, onSelect }: { item: CommsItem; onSelect: () => void }) {
  const kind = itemKind(item)
  const Icon = kind === "message" ? MessageSquare : kind === "call" ? Phone : Mail
  const from = partyName(sender(item))
  const to = recipients(item).map(partyName).join(", ") || partyName(item.counterpart)
  const body = previewText(item, 120)

  return (
    <button
      type="button"
      onClick={onSelect}
      className="grid w-full grid-cols-[130px_26px_minmax(0,1fr)_160px] items-center gap-2 border-b border-border px-3 py-2 text-left text-xs transition-colors hover:bg-muted/50"
    >
      <span className="text-[11px] text-muted-foreground">{shortDate(item.timestamp)}</span>
      <Icon className="size-4 text-muted-foreground" />
      <span className="min-w-0">
        <span className="font-medium">{from}</span>
        {to && <span className="text-muted-foreground"> to {to}</span>}
        <span className="text-muted-foreground"> - </span>
        <span className="text-foreground">{body || messageTitle(item)}</span>
      </span>
      <span className="truncate text-[11px] text-muted-foreground">{sourceAppLabel(item)}</span>
    </button>
  )
}

