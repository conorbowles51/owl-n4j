import { useState } from "react"
import { ChevronDown, ChevronRight, Focus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { getNodeColor } from "@/lib/theme"
import { useGraphStore } from "@/stores/graph.store"
import type { GraphNode } from "@/types/graph.types"

interface GraphLegendProps {
  /** The nodes drawn now (after any filter). */
  nodes: GraphNode[]
  /**
   * Every node loaded for the case (the whole case: the graph is not capped). A type's spotlight button takes all of
   * them, including nodes a filter hides, so it never works on a subset without saying so (BUG-015).
   */
  allNodes?: GraphNode[]
}

export function GraphLegend({ nodes, allNodes = nodes }: GraphLegendProps) {
  const [collapsed, setCollapsed] = useState(false)
  const [filter, setFilter] = useState("")
  const {
    selectedNodeKeys,
    selectNodes,
    addToSubgraph,
    removeFromSubgraph,
    subgraphNodeKeys,
  } = useGraphStore()

  // Count by type
  const typeCounts = nodes.reduce<Record<string, number>>((acc, n) => {
    acc[n.type] = (acc[n.type] ?? 0) + 1
    return acc
  }, {})

  const totalCounts = allNodes.reduce<Record<string, number>>((acc, n) => {
    acc[n.type] = (acc[n.type] ?? 0) + 1
    return acc
  }, {})

  const types = Object.entries(typeCounts).sort((a, b) => b[1] - a[1])

  const filteredTypes = filter
    ? types.filter(([type]) => type.toLowerCase().includes(filter.toLowerCase()))
    : types

  const selectAllOfType = (type: string) => {
    const keys = nodes.filter((n) => n.type === type).map((n) => n.key)
    selectNodes(keys)
  }

  const spotlightAllOfType = (type: string) => {
    addToSubgraph(allNodes.filter((n) => n.type === type).map((n) => n.key))
  }

  const selectAllVisible = () => selectNodes(nodes.map((n) => n.key))
  const deselectAll = () => selectNodes([])

  const addSelectedToSpotlight = () => {
    addToSubgraph(Array.from(selectedNodeKeys))
  }

  const removeSelectedFromSpotlight = () => {
    removeFromSubgraph(Array.from(selectedNodeKeys))
  }

  const hasSelectedInSpotlight = Array.from(selectedNodeKeys).some((k) =>
    subgraphNodeKeys.has(k)
  )

  const handleCollapse = () => {
    setCollapsed(!collapsed)
    if (!collapsed) setFilter("")
  }

  return (
    <div className="absolute bottom-3 right-3 z-10 max-h-[60vh] flex flex-col rounded-lg bg-popover/95 backdrop-blur-sm border border-border text-xs">
      <button
        className="flex w-full items-center gap-1 px-3 py-1.5 text-popover-foreground hover:text-foreground shrink-0"
        onClick={handleCollapse}
      >
        {collapsed ? (
          <ChevronRight className="size-3" />
        ) : (
          <ChevronDown className="size-3" />
        )}
        <span className="font-medium">Legend</span>
        <span className="ml-auto text-muted-foreground">{types.length} types</span>
      </button>

      {!collapsed && (
        <>
          {/* Filter input for 8+ types */}
          {types.length >= 8 && (
            <div className="px-3 pb-1.5 shrink-0">
              <input
                type="text"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Filter types..."
                className="w-full rounded bg-muted border border-border px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground outline-none focus:border-ring"
              />
            </div>
          )}

          {/* Scrollable type list */}
          <div className="overflow-y-auto min-h-0 border-t border-border px-3 py-2 space-y-1">
            {filteredTypes.map(([type, count]) => {
              const total = totalCounts[type] ?? count
              return (
                <div key={type} className="flex w-full items-center gap-1">
                  <button
                    className="flex min-w-0 flex-1 items-center gap-2 rounded px-1 py-0.5 hover:bg-muted/50"
                    onClick={() => selectAllOfType(type)}
                    title={total > count ? `Select the ${count} ${type} shown (${total - count} hidden by the filter)` : `Select all ${type}`}
                  >
                    <span
                      className="inline-block size-2.5 rounded-full shrink-0"
                      style={{ backgroundColor: getNodeColor(type) }}
                    />
                    <span className="flex-1 text-left capitalize text-popover-foreground">
                      {type}
                    </span>
                    <span className="text-muted-foreground" data-testid={`legend-count-${type}`}>
                      {total > count ? `${count} of ${total}` : count}
                    </span>
                  </button>
                  <button
                    type="button"
                    className="rounded p-0.5 text-muted-foreground hover:bg-muted/50 hover:text-amber-600"
                    onClick={() => spotlightAllOfType(type)}
                    aria-label={`Put all ${total} ${type} in the spotlight`}
                    title={`Put all ${total} ${type} loaded for this case in the spotlight${total > count ? `, including ${total - count} hidden by the filter` : ""}`}
                  >
                    <Focus className="size-3" />
                  </button>
                </div>
              )
            })}
          </div>

          {/* Fixed action buttons footer */}
          <div className="shrink-0 border-t border-border px-3 py-1.5 space-y-1">
            <div className="flex gap-1">
              <Button
                variant="ghost"
                size="sm"
                className="h-5 px-1.5 text-[10px] text-muted-foreground"
                onClick={selectAllVisible}
              >
                Select All
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-5 px-1.5 text-[10px] text-muted-foreground"
                onClick={deselectAll}
              >
                Deselect
              </Button>
            </div>

            {selectedNodeKeys.size > 0 && (
              <div className="flex gap-1 border-t border-border pt-1.5">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-5 px-1.5 text-[10px] text-amber-600 dark:text-amber-400"
                  onClick={addSelectedToSpotlight}
                >
                  + Spotlight
                </Button>
                {hasSelectedInSpotlight && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-5 px-1.5 text-[10px] text-red-600 dark:text-red-400"
                    onClick={removeSelectedFromSpotlight}
                  >
                    - Spotlight
                  </Button>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
