import { useEffect, useMemo, useRef, useState } from "react"
import { BarChart3, Calendar, ChevronDown, Mail, MessageSquare, Phone, Search, Smartphone, X } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/cn"

import type { CommsEnvelopeResponse, CommsSourceApp, CommsType } from "../../types"
import { compactNumber } from "../shared/cellebrite-format"
import { ALL_COMMS_TYPES, sourceAppLabel, typeLabel } from "./commsUtils"

export function CommsToolbar({
  search,
  onSearchChange,
  threadsShown,
  threadsTotal,
  activeTypes,
  onTypesChange,
  sourceApps,
  activeApps,
  onAppsChange,
  envelope,
  envelopeLoading,
  startDate,
  endDate,
  onWindowChange,
}: {
  search: string
  onSearchChange: (value: string) => void
  threadsShown: number
  threadsTotal: number
  activeTypes: Set<CommsType>
  onTypesChange: (types: Set<CommsType>) => void
  sourceApps: CommsSourceApp[]
  activeApps: Set<string>
  onAppsChange: (apps: Set<string>) => void
  envelope: CommsEnvelopeResponse | null
  envelopeLoading?: boolean
  startDate: string
  endDate: string
  onWindowChange: (startDate: string, endDate: string) => void
}) {
  const [appsOpen, setAppsOpen] = useState(false)
  const [scrubberOpen, setScrubberOpen] = useState(false)
  const appsButtonRef = useRef<HTMLButtonElement | null>(null)
  const appsPanelRef = useRef<HTMLDivElement | null>(null)
  const hasWindow = Boolean(startDate || endDate)

  useEffect(() => {
    if (!appsOpen) return
    function onDocumentMouseDown(event: MouseEvent) {
      const target = event.target as Node
      if (appsPanelRef.current?.contains(target) || appsButtonRef.current?.contains(target)) return
      setAppsOpen(false)
    }
    document.addEventListener("mousedown", onDocumentMouseDown)
    return () => document.removeEventListener("mousedown", onDocumentMouseDown)
  }, [appsOpen])

  function toggleType(type: CommsType) {
    const next = new Set(activeTypes)
    if (next.has(type)) {
      if (next.size === 1) return
      next.delete(type)
    } else {
      next.add(type)
    }
    onTypesChange(next)
  }

  const total = envelope?.total ?? 0
  const histogram = envelope?.histogram ?? []

  return (
    <div className="shrink-0 border-b border-border bg-card">
      <div className="flex min-h-11 items-center gap-2 px-3 py-1.5">
        <div className="relative min-w-[220px] flex-1">
          <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search threads, participants, messages"
            className="h-8 pl-7 pr-20 text-xs"
          />
          <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[11px] text-muted-foreground">
            {compactNumber(threadsShown)} / {compactNumber(threadsTotal)}
          </span>
        </div>

        <div className="relative">
          <Button
            ref={appsButtonRef}
            type="button"
            variant={activeApps.size ? "secondary" : "outline"}
            size="sm"
            className="h-8 gap-1.5 text-xs"
            onClick={() => setAppsOpen((value) => !value)}
          >
            <Smartphone className="size-3.5" />
            {activeApps.size ? `Apps (${activeApps.size})` : "All apps"}
            <ChevronDown className={cn("size-3 transition-transform", appsOpen && "rotate-180")} />
          </Button>
          {appsOpen && (
            <div
              ref={appsPanelRef}
              className="absolute right-0 top-full z-30 mt-1 w-[320px] rounded-md border border-border bg-popover p-2 shadow-xl"
            >
              <div className="mb-2 flex items-center gap-2 px-1">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Source app
                </span>
                {activeApps.size > 0 && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="ml-auto h-6 px-1.5 text-[11px]"
                    onClick={() => onAppsChange(new Set())}
                  >
                    Clear
                  </Button>
                )}
              </div>
              <div className="max-h-[280px] overflow-y-auto">
                <button
                  type="button"
                  onClick={() => onAppsChange(new Set())}
                  className={cn(
                    "mb-1 flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-xs",
                    activeApps.size === 0 ? "bg-amber-500/10 text-foreground" : "hover:bg-muted"
                  )}
                >
                  <span>All apps</span>
                  <Badge variant="outline">{compactNumber(sourceApps.length)}</Badge>
                </button>
                {sourceApps.map((app) => {
                  const label = sourceAppLabel(app)
                  const active = activeApps.has(label)
                  return (
                    <button
                      key={label}
                      type="button"
                      onClick={() => {
                        const next = new Set(activeApps)
                        if (next.has(label)) next.delete(label)
                        else next.add(label)
                        onAppsChange(next)
                      }}
                      className={cn(
                        "flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs transition-colors",
                        active ? "bg-amber-500/10 text-foreground" : "text-muted-foreground hover:bg-muted"
                      )}
                    >
                      <input type="checkbox" checked={active} readOnly tabIndex={-1} className="size-3 accent-amber-500" />
                      <span className="min-w-0 flex-1 truncate">{label}</span>
                      {typeof app.count === "number" && <span className="text-[11px]">{compactNumber(app.count)}</span>}
                    </button>
                  )
                })}
              </div>
            </div>
          )}
        </div>

        <div className="inline-flex overflow-hidden rounded-md border border-border">
          {ALL_COMMS_TYPES.map((type) => {
            const Icon = type === "message" ? MessageSquare : type === "call" ? Phone : Mail
            const active = activeTypes.has(type)
            return (
              <button
                key={type}
                type="button"
                onClick={() => toggleType(type)}
                className={cn(
                  "inline-flex h-8 items-center gap-1 border-r border-border px-2 text-xs last:border-r-0",
                  active ? "bg-secondary text-secondary-foreground" : "bg-card text-muted-foreground hover:bg-muted"
                )}
                title={typeLabel(type)}
              >
                <Icon className="size-3.5" />
                {typeLabel(type).replace("s", "")}
              </button>
            )
          })}
        </div>

        {hasWindow && (
          <div className="hidden items-center gap-1 lg:flex">
            {startDate && (
              <DateChip label="From" value={startDate} onClear={() => onWindowChange("", endDate)} />
            )}
            {endDate && (
              <DateChip label="Until" value={endDate} onClear={() => onWindowChange(startDate, "")} />
            )}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 px-1.5 text-[11px]"
              onClick={() => onWindowChange("", "")}
            >
              Clear
            </Button>
          </div>
        )}

        <Button
          type="button"
          variant={hasWindow || scrubberOpen ? "secondary" : "outline"}
          size="sm"
          className="h-8 gap-1.5 text-xs"
          onClick={() => setScrubberOpen((value) => !value)}
        >
          <BarChart3 className="size-3.5" />
          {hasWindow ? "Date on" : "Scrubber"}
          <ChevronDown className={cn("size-3 transition-transform", scrubberOpen && "rotate-180")} />
        </Button>
      </div>

      {scrubberOpen && (
        <div className="border-t border-border px-3 py-2">
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_280px]">
            <div>
              <div className="mb-1 flex items-center gap-2 text-[11px] text-muted-foreground">
                <span>Communication density</span>
                {envelopeLoading && <span>updating...</span>}
                <span className="ml-auto">{compactNumber(total)} items</span>
              </div>
              <DensityBars rows={histogram} />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <label className="space-y-1">
                <span className="text-[11px] text-muted-foreground">From</span>
                <Input
                  type="date"
                  value={startDate}
                  onChange={(event) => onWindowChange(event.target.value, endDate)}
                  className="h-8 text-xs"
                />
              </label>
              <label className="space-y-1">
                <span className="text-[11px] text-muted-foreground">Until</span>
                <Input
                  type="date"
                  value={endDate}
                  onChange={(event) => onWindowChange(startDate, event.target.value)}
                  className="h-8 text-xs"
                />
              </label>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function DateChip({
  label,
  value,
  onClear,
}: {
  label: string
  value: string
  onClear: () => void
}) {
  return (
    <span className="inline-flex h-7 items-center gap-1 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2 text-[11px] text-cyan-700 dark:text-cyan-300">
      <Calendar className="size-3" />
      <span className="uppercase tracking-wide opacity-70">{label}</span>
      <span className="tabular-nums">{value}</span>
      <button type="button" onClick={onClear} className="rounded hover:opacity-70">
        <X className="size-3" />
      </button>
    </span>
  )
}

function DensityBars({ rows }: { rows: { date: string; count: number }[] }) {
  const visible = useMemo(() => rows.slice(-80), [rows])
  if (visible.length === 0) {
    return (
      <div className="flex h-16 items-center justify-center rounded-md border border-border bg-muted/30 text-xs text-muted-foreground">
        No dated communications in this filter.
      </div>
    )
  }
  const max = Math.max(...visible.map((row) => row.count), 1)
  return (
    <div className="flex h-16 items-end gap-px rounded-md border border-border bg-muted/20 p-1">
      {visible.map((row) => (
        <div
          key={row.date}
          className="min-w-1 flex-1 rounded-t bg-amber-500/80"
          style={{ height: `${Math.max(4, (row.count / max) * 52)}px` }}
          title={`${row.date}: ${compactNumber(row.count)}`}
        />
      ))}
    </div>
  )
}

