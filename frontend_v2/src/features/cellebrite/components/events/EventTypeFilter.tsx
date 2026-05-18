import { MapPin } from "lucide-react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/cn"

import type { CellebriteRecord } from "../../types"
import { compactNumber, readNumber, readText } from "../shared/cellebrite-format"
import { EVENT_ICONS, eventColor, eventTypeLabel } from "./eventUtils"

export function EventTypeFilter({
  types,
  activeTypes,
  onlyGeolocated,
  onTypesChange,
  onOnlyGeolocatedChange,
}: {
  types: CellebriteRecord[]
  activeTypes: Set<string>
  onlyGeolocated: boolean
  onTypesChange: (types: Set<string>) => void
  onOnlyGeolocatedChange: (value: boolean) => void
}) {
  const typeKeys = types.map((type) => readText(type, ["event_type", "type"], "event"))

  function toggle(type: string) {
    const next = new Set(activeTypes)
    if (next.has(type)) next.delete(type)
    else next.add(type)
    onTypesChange(next)
  }

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-1.5">
      <Button type="button" variant="outline" size="sm" className="h-7 px-2 text-xs" onClick={() => onTypesChange(new Set(typeKeys))}>
        All
      </Button>
      <Button type="button" variant="outline" size="sm" className="h-7 px-2 text-xs" onClick={() => onTypesChange(new Set())}>
        None
      </Button>
      {types.map((row) => {
        const type = readText(row, ["event_type", "type"], "event")
        const label = eventTypeLabel(row)
        const Icon = EVENT_ICONS[type as keyof typeof EVENT_ICONS] ?? MapPin
        const active = activeTypes.has(type)
        const count = readNumber(row, ["count", "total"], 0)
        const geolocated = readNumber(row, ["geolocated", "geo_count", "location_count"], 0)
        return (
          <button
            key={type}
            type="button"
            onClick={() => toggle(type)}
            className={cn(
              "inline-flex h-7 items-center gap-1 rounded-full border px-2 text-xs font-medium transition-colors",
              active ? "border-transparent text-white" : "border-border bg-card text-muted-foreground hover:bg-muted"
            )}
            style={active ? { backgroundColor: eventColor(type) } : undefined}
            title={`${label}: ${compactNumber(count)} total${geolocated ? `, ${compactNumber(geolocated)} geolocated` : ""}`}
          >
            <Icon className="size-3" />
            <span>{label}</span>
            <span className={cn("text-[10px]", active ? "text-white/80" : "text-muted-foreground")}>
              {compactNumber(count)}
            </span>
          </button>
        )
      })}
      <label className="ml-1 inline-flex h-7 cursor-pointer select-none items-center gap-1 rounded-md border border-border bg-card px-2 text-xs text-muted-foreground hover:bg-muted">
        <input
          type="checkbox"
          checked={onlyGeolocated}
          onChange={(event) => onOnlyGeolocatedChange(event.target.checked)}
          className="size-3 accent-amber-500"
        />
        Geolocated
      </label>
    </div>
  )
}

