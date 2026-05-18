import { useState } from "react"
import { ChevronDown, ChevronLeft, ChevronRight, Loader2, MapPin, Phone, Play, Radio, Users, Wifi } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/cn"

import { useRunIntersections } from "../../hooks/use-cellebrite"
import type { CellebriteRecord } from "../../types"
import { compactDate, compactNumber, isRecord, readList, readNumber, readText } from "../shared/cellebrite-format"

const METHOD_META = {
  spatial: {
    label: "Spatial co-presence",
    icon: MapPin,
    description: "Devices within a distance and time window.",
    defaults: { max_distance_m: 250, max_time_delta_s: 600 },
    fields: [
      { key: "max_distance_m", label: "Max distance (m)", min: 10, max: 5000, step: 10 },
      { key: "max_time_delta_s", label: "Max time delta (s)", min: 30, max: 7200, step: 30 },
    ],
  },
  cell_tower: {
    label: "Shared cell tower",
    icon: Radio,
    description: "Devices registered to the same tower.",
    defaults: { max_time_delta_s: 900 },
    fields: [{ key: "max_time_delta_s", label: "Max time delta (s)", min: 60, max: 7200, step: 60 }],
  },
  wifi: {
    label: "Shared WiFi",
    icon: Wifi,
    description: "Devices associated with the same network.",
    defaults: { max_time_delta_s: 1800 },
    fields: [{ key: "max_time_delta_s", label: "Max time delta (s)", min: 60, max: 14400, step: 60 }],
  },
  comm_hub: {
    label: "Communication hub",
    icon: Phone,
    description: "Multiple devices talking to the same third party.",
    defaults: { time_window_s: 3600, min_devices: 2 },
    fields: [
      { key: "time_window_s", label: "Time window (s)", min: 60, max: 86400, step: 60 },
      { key: "min_devices", label: "Min devices", min: 2, max: 10, step: 1 },
    ],
  },
  convoy: {
    label: "Convoy",
    icon: Users,
    description: "Sustained co-location across multiple samples.",
    defaults: { max_distance_m: 500, min_duration_s: 1800, min_samples: 5 },
    fields: [
      { key: "max_distance_m", label: "Max distance (m)", min: 10, max: 5000, step: 10 },
      { key: "min_duration_s", label: "Min duration (s)", min: 300, max: 86400, step: 300 },
      { key: "min_samples", label: "Min samples", min: 2, max: 50, step: 1 },
    ],
  },
} as const

const METHODS = Object.keys(METHOD_META) as (keyof typeof METHOD_META)[]

export function IntersectionPanel({
  caseId,
  reportKeys,
  startDate,
  endDate,
  results,
  collapsed,
  onResult,
  onJumpToMatch,
  onCollapsedChange,
}: {
  caseId: string
  reportKeys: string[] | null
  startDate: string
  endDate: string
  results: Record<string, CellebriteRecord>
  collapsed: boolean
  onResult: (method: string, result: CellebriteRecord) => void
  onJumpToMatch: (match: CellebriteRecord) => void
  onCollapsedChange: (collapsed: boolean) => void
}) {
  if (collapsed) {
    return (
      <aside className="flex w-9 shrink-0 flex-col items-center border-l border-border bg-muted/20">
        <Button type="button" variant="ghost" size="icon-sm" className="mt-2" onClick={() => onCollapsedChange(false)}>
          <ChevronLeft className="size-4" />
        </Button>
        <div className="mt-8 -rotate-90 whitespace-nowrap text-[10px] text-muted-foreground">Intersections</div>
      </aside>
    )
  }

  return (
    <aside className="flex w-80 shrink-0 flex-col border-l border-border bg-muted/20">
      <div className="flex h-11 items-center gap-2 border-b border-border bg-card px-3">
        <span className="text-xs font-semibold">Intersections</span>
        <Button type="button" variant="ghost" size="icon-sm" className="ml-auto" onClick={() => onCollapsedChange(true)}>
          <ChevronRight className="size-4" />
        </Button>
      </div>
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-2">
        {METHODS.map((method) => (
          <IntersectionMethodCard
            key={method}
            caseId={caseId}
            method={method}
            reportKeys={reportKeys}
            startDate={startDate || null}
            endDate={endDate || null}
            result={results[method] ?? null}
            onResult={onResult}
            onJumpToMatch={onJumpToMatch}
          />
        ))}
      </div>
    </aside>
  )
}

function IntersectionMethodCard({
  caseId,
  method,
  reportKeys,
  startDate,
  endDate,
  result,
  onResult,
  onJumpToMatch,
}: {
  caseId: string
  method: keyof typeof METHOD_META
  reportKeys: string[] | null
  startDate: string | null
  endDate: string | null
  result: CellebriteRecord | null
  onResult: (method: string, result: CellebriteRecord) => void
  onJumpToMatch: (match: CellebriteRecord) => void
}) {
  const meta = METHOD_META[method]
  const Icon = meta.icon
  const [expanded, setExpanded] = useState(false)
  const [params, setParams] = useState<Record<string, number>>(meta.defaults)
  const runIntersections = useRunIntersections(caseId)
  const matches = (Array.isArray(result?.matches) ? result.matches.filter(isRecord) : []) as CellebriteRecord[]

  async function run() {
    try {
      const data = await runIntersections.mutateAsync({
        methods: [method],
        reportKeys,
        startDate,
        endDate,
        params: { [method]: params },
      })
      const next = (data.results ?? []).find((row) => isRecord(row) && readText(row, ["method"]) === method)
      onResult(method, isRecord(next) ? next : { method, matches: [], params_used: params })
    } catch (error) {
      onResult(method, {
        method,
        matches: [],
        params_used: params,
        reason: error instanceof Error ? error.message : "Intersection check failed",
      })
    }
  }

  return (
    <div className="rounded-md border border-border bg-card">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs hover:bg-muted/50"
      >
        {expanded ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
        <Icon className="size-4 text-muted-foreground" />
        <span className="min-w-0 flex-1 font-semibold">{meta.label}</span>
        {result && (
          <Badge variant={matches.length ? "success" : "slate"}>
            {compactNumber(matches.length)}
          </Badge>
        )}
      </button>
      {expanded && (
        <div className="space-y-2 px-3 pb-3">
          <p className="text-[11px] text-muted-foreground">{meta.description}</p>
          <div className="space-y-2">
            {meta.fields.map((field) => (
              <label key={field.key} className="block text-[11px] text-muted-foreground">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span>{field.label}</span>
                  <Input
                    type="number"
                    min={field.min}
                    max={field.max}
                    step={field.step}
                    value={params[field.key] ?? field.min}
                    onChange={(event) => setParams((current) => ({ ...current, [field.key]: Number(event.target.value) }))}
                    className="h-7 w-24 text-xs"
                  />
                </div>
                <input
                  type="range"
                  min={field.min}
                  max={field.max}
                  step={field.step}
                  value={params[field.key] ?? field.min}
                  onChange={(event) => setParams((current) => ({ ...current, [field.key]: Number(event.target.value) }))}
                  className="w-full accent-amber-500"
                />
              </label>
            ))}
          </div>
          <Button type="button" size="sm" className="h-8 text-xs" disabled={runIntersections.isPending} onClick={run}>
            {runIntersections.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}
            {runIntersections.isPending ? "Running" : "Run check"}
          </Button>
          {readText(result, ["reason"]) && (
            <div className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-700 dark:text-amber-300">
              {readText(result, ["reason"])}
            </div>
          )}
          {result && matches.length === 0 && !readText(result, ["reason"]) && (
            <div className="text-[11px] text-muted-foreground">No matches for current parameters.</div>
          )}
          {matches.length > 0 && (
            <div className="max-h-56 space-y-1 overflow-y-auto border-t border-border pt-2">
              {matches.map((match, index) => {
                const devices = readList(match, ["devices", "report_keys", "device_report_keys"])
                const score = readNumber(match, ["score"], Number.NaN)
                return (
                  <button
                    key={readText(match, ["id"], `${method}-${index}`)}
                    type="button"
                    onClick={() => onJumpToMatch(match)}
                    className={cn("w-full rounded border border-border px-2 py-1.5 text-left text-[11px] hover:bg-muted/50")}
                  >
                    <div className="truncate font-medium">{readText(match, ["summary", "label"], "Match")}</div>
                    <div className="mt-0.5 flex flex-wrap gap-1 text-muted-foreground">
                      <span>{compactDate(readText(match, ["start_time", "timestamp"], "-"))}</span>
                      {devices.length > 0 && (
                        <>
                          <span>/</span>
                          <span>
                            {compactNumber(devices.length)} device{devices.length === 1 ? "" : "s"}
                          </span>
                        </>
                      )}
                      {Number.isFinite(score) && (
                        <>
                          <span>/</span>
                          <span>score {Math.round(score * 100)}%</span>
                        </>
                      )}
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
