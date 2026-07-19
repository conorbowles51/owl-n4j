import { Check, Database, Layers3, Star } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/cn"
import { useCaseLayer, useCaseLayerStore } from "../stores/case-layer.store"
import { useSignificantManifest } from "../hooks/use-significant"
import type { CaseLayer } from "../types"

interface CaseLayerSwitcherProps {
  caseId: string
  expanded: boolean
}

const OPTIONS: Array<{
  value: CaseLayer
  label: string
  description: string
  icon: typeof Database
}> = [
  {
    value: "all",
    label: "All data",
    description: "The complete case graph",
    icon: Database,
  },
  {
    value: "significant",
    label: "Significant",
    description: "The shared investigative layer",
    icon: Star,
  },
]

export function CaseLayerSwitcher({
  caseId,
  expanded,
}: CaseLayerSwitcherProps) {
  const layer = useCaseLayer(caseId)
  const setLayer = useCaseLayerStore((state) => state.setLayer)
  const { data } = useSignificantManifest(caseId)
  const count = data?.count ?? 0

  if (!expanded) {
    const trigger = (
      <Button
        variant="ghost"
        size="icon"
        aria-label={`Case layer: ${layer === "significant" ? "Significant" : "All data"}`}
        className={cn(
          "mx-auto size-10 border transition-colors",
          layer === "significant"
            ? "border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-300"
            : "border-transparent text-sidebar-muted hover:border-sidebar-border"
        )}
      >
        {layer === "significant" ? (
          <Star className="size-4 fill-current" />
        ) : (
          <Layers3 className="size-4" />
        )}
      </Button>
    )

    return (
      <Popover>
        <Tooltip>
          <PopoverTrigger asChild>
            <TooltipTrigger asChild>{trigger}</TooltipTrigger>
          </PopoverTrigger>
          <TooltipContent side="right">Choose case layer</TooltipContent>
        </Tooltip>
        <PopoverContent side="right" align="start" className="w-64 p-2">
          <LayerOptions
            layer={layer}
            count={count}
            onChange={(next) => setLayer(caseId, next)}
          />
        </PopoverContent>
      </Popover>
    )
  }

  return (
    <div className="mx-1 mb-2 rounded-lg border border-sidebar-border bg-black/[0.025] p-1 dark:bg-white/[0.025]">
      <div className="mb-1 flex items-center justify-between px-1.5 pt-1">
        <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-sidebar-muted">
          Case layer
        </span>
        <span className="font-mono text-[10px] tabular-nums text-sidebar-muted">
          {count.toLocaleString()} marked
        </span>
      </div>
      <div className="grid grid-cols-2 gap-1" role="group" aria-label="Case layer">
        {OPTIONS.map((option) => {
          const active = option.value === layer
          const Icon = option.icon
          return (
            <button
              key={option.value}
              type="button"
              aria-pressed={active}
              onClick={() => setLayer(caseId, option.value)}
              className={cn(
                "flex h-8 items-center justify-center gap-1.5 rounded-md px-2 text-[11px] font-medium transition-colors",
                active && option.value === "significant"
                  ? "bg-amber-500/15 text-amber-700 shadow-[inset_0_0_0_1px_rgba(217,119,6,0.28)] dark:text-amber-300"
                  : active
                    ? "bg-sidebar-accent text-sidebar-foreground shadow-sm"
                    : "text-sidebar-muted hover:bg-sidebar-accent/60 hover:text-sidebar-foreground"
              )}
            >
              <Icon
                className={cn(
                  "size-3.5",
                  active && option.value === "significant" && "fill-current"
                )}
              />
              {option.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function LayerOptions({
  layer,
  count,
  onChange,
}: {
  layer: CaseLayer
  count: number
  onChange: (layer: CaseLayer) => void
}) {
  return (
    <div>
      <div className="px-2 pb-2 pt-1">
        <p className="text-xs font-semibold">Case layer</p>
        <p className="mt-0.5 text-[11px] text-muted-foreground">
          This choice follows you across Graph, Timeline, Map and Table.
        </p>
      </div>
      {OPTIONS.map((option) => {
        const Icon = option.icon
        const active = option.value === layer
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={cn(
              "flex w-full items-center gap-3 rounded-md px-2 py-2 text-left",
              active ? "bg-muted" : "hover:bg-muted/60"
            )}
          >
            <span
              className={cn(
                "grid size-8 place-items-center rounded-md border",
                option.value === "significant"
                  ? "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-300"
                  : "border-border bg-background text-muted-foreground"
              )}
            >
              <Icon
                className={cn(
                  "size-4",
                  option.value === "significant" && active && "fill-current"
                )}
              />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-xs font-medium">{option.label}</span>
              <span className="block text-[10px] text-muted-foreground">
                {option.value === "significant"
                  ? `${count.toLocaleString()} marked entities`
                  : option.description}
              </span>
            </span>
            {active ? <Check className="size-4 text-amber-600" /> : null}
          </button>
        )
      })}
    </div>
  )
}
