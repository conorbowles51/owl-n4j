import { useState } from "react"
import { ChevronDown, ChevronUp, Eye, EyeOff } from "lucide-react"
import { getNodeColor } from "@/lib/theme"
import {
  CONFIDENCE_TIERS,
  CONFIDENCE_TIER_COLORS,
  CONFIDENCE_TIER_LABELS,
  getConfidenceTier,
} from "@/lib/location-confidence"
import { useMapStore } from "../stores/map.store"
import type { MapLocation } from "../hooks/use-map-data"

interface MapLegendProps {
  locations: MapLocation[]
}

export function MapLegend({ locations }: MapLegendProps) {
  const [collapsed, setCollapsed] = useState(false)
  const [filter, setFilter] = useState("")
  const hiddenTypes = useMapStore((s) => s.hiddenTypes)
  const toggleType = useMapStore((s) => s.toggleType)
  const hiddenConfidenceTiers = useMapStore((s) => s.hiddenConfidenceTiers)
  const toggleConfidenceTier = useMapStore((s) => s.toggleConfidenceTier)

  // Count locations per confidence tier (same vocabulary as filter + popup)
  const tierCounts = new Map<string, number>()
  for (const loc of locations) {
    const tier = getConfidenceTier(loc)
    tierCounts.set(tier, (tierCounts.get(tier) ?? 0) + 1)
  }
  const tiers = CONFIDENCE_TIERS.filter((tier) => (tierCounts.get(tier) ?? 0) > 0)

  // Count locations per type
  const typeCounts = new Map<string, number>()
  for (const loc of locations) {
    typeCounts.set(loc.type, (typeCounts.get(loc.type) ?? 0) + 1)
  }

  // Derive types from actual data (like GraphLegend), sorted by count descending
  const types = [...typeCounts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([type, count]) => ({ type, count, color: getNodeColor(type) }))

  const filteredTypes = filter
    ? types.filter(({ type }) => type.toLowerCase().includes(filter.toLowerCase()))
    : types

  if (types.length === 0) return null

  return (
    <div className="absolute bottom-3 left-3 z-10 rounded-lg border border-border bg-card/95 shadow-md backdrop-blur">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground"
      >
        Legend
        {collapsed ? (
          <ChevronUp className="ml-auto size-3" />
        ) : (
          <ChevronDown className="ml-auto size-3" />
        )}
      </button>

      {!collapsed && (
        <div className="px-2 pb-2">
          <input
            type="text"
            placeholder="Filter..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="w-full rounded border border-border bg-background px-2 pt-1 pb-1 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none"
          />
          <div className="mt-1 flex max-h-[240px] flex-col gap-0.5 overflow-y-auto">
          {filteredTypes.map(({ type, count, color }) => {
            const isHidden = hiddenTypes.has(type)
            return (
              <button
                key={type}
                onClick={() => toggleType(type)}
                className="flex items-center gap-2 rounded px-1.5 py-0.5 text-xs hover:bg-muted"
                style={{ opacity: isHidden ? 0.4 : 1 }}
              >
                <div
                  className="size-2.5 rounded-full"
                  style={{ backgroundColor: color }}
                />
                <span className="capitalize">{type}</span>
                <span className="ml-auto text-[10px] text-muted-foreground">
                  {count}
                </span>
                {isHidden ? (
                  <EyeOff className="size-3 text-muted-foreground" />
                ) : (
                  <Eye className="size-3 text-muted-foreground" />
                )}
              </button>
            )
          })}
          </div>

          {tiers.length > 0 && (
            <>
              <div className="mt-2 px-1.5 text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">
                Confidence
              </div>
              <div className="mt-1 flex flex-col gap-0.5">
                {tiers.map((tier) => {
                  const isHidden = hiddenConfidenceTiers.has(tier)
                  return (
                    <button
                      key={tier}
                      onClick={() => toggleConfidenceTier(tier)}
                      className="flex items-center gap-2 rounded px-1.5 py-0.5 text-xs hover:bg-muted"
                      style={{ opacity: isHidden ? 0.4 : 1 }}
                    >
                      <div
                        className="size-2.5 rounded-full"
                        style={{ backgroundColor: CONFIDENCE_TIER_COLORS[tier] }}
                      />
                      <span>{CONFIDENCE_TIER_LABELS[tier]}</span>
                      <span className="ml-auto text-[10px] text-muted-foreground">
                        {tierCounts.get(tier)}
                      </span>
                      {isHidden ? (
                        <EyeOff className="size-3 text-muted-foreground" />
                      ) : (
                        <Eye className="size-3 text-muted-foreground" />
                      )}
                    </button>
                  )
                })}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
