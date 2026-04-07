import { useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import { Slider } from "@/components/ui/slider"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { NodeBadge } from "@/components/ui/node-badge"
import { ConfidenceBar } from "@/components/ui/confidence-bar"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { GitMerge, X, Search, StopCircle, Eye, Filter } from "lucide-react"
import { useSimilarEntities } from "../hooks/use-similar-entities"
import { useEntityTypes } from "../hooks/use-graph-data"
import { graphAPI } from "../api"
import { MergeEntitiesDialog } from "./MergeEntitiesDialog"
import { EntityComparisonDialog } from "./EntityComparisonDialog"
import { getNodeColor } from "@/lib/theme"
import type { GraphData, GraphNode, SimilarPair } from "@/types/graph.types"

interface SimilarEntitiesViewProps {
  caseId: string
  graphData: GraphData
  onRefresh: () => void
}

export function SimilarEntitiesView({
  caseId,
  graphData,
  onRefresh,
}: SimilarEntitiesViewProps) {
  const [threshold, setThreshold] = useState([0.7])
  const [selectedTypes, setSelectedTypes] = useState<Set<string>>(new Set())
  const [typeFilterOpen, setTypeFilterOpen] = useState(false)
  const [typeSearch, setTypeSearch] = useState("")
  const {
    isScanning,
    progress,
    currentType,
    results,
    error,
    startScan,
    cancel,
  } = useSimilarEntities(caseId)
  const { data: entityTypesData } = useEntityTypes(caseId)

  const [compareOpen, setCompareOpen] = useState(false)
  const [comparePair, setComparePair] = useState<SimilarPair | null>(null)

  const [mergeOpen, setMergeOpen] = useState(false)
  const [mergePair, setMergePair] = useState<{
    e1: GraphNode | null
    e2: GraphNode | null
    similarity: number
  }>({ e1: null, e2: null, similarity: 0 })

  const typeCounts = useMemo(() => {
    const counts = new Map<string, number>()

    for (const item of entityTypesData?.entity_types ?? []) {
      counts.set(item.type, item.count)
    }

    if (counts.size === 0) {
      for (const node of graphData.nodes) {
        counts.set(node.type, (counts.get(node.type) ?? 0) + 1)
      }
    }

    return counts
  }, [entityTypesData?.entity_types, graphData.nodes])

  const allTypes = useMemo(
    () => Array.from(typeCounts.keys()).sort((a, b) => a.localeCompare(b)),
    [typeCounts]
  )

  const visibleTypes = useMemo(
    () =>
      Array.from(typeCounts.entries())
        .sort(([, a], [, b]) => b - a)
        .filter(([type]) =>
          type.toLowerCase().includes(typeSearch.trim().toLowerCase())
        ),
    [typeCounts, typeSearch]
  )

  const hasActiveTypeFilter =
    selectedTypes.size > 0 && selectedTypes.size < allTypes.length

  const effectiveSelectedTypes =
    selectedTypes.size === 0 ? allTypes : Array.from(selectedTypes)

  const toggleType = (type: string) => {
    setSelectedTypes((current) => {
      const next = current.size === 0 ? new Set(allTypes) : new Set(current)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return next.size === 0 || next.size === allTypes.length
        ? new Set()
        : next
    })
  }

  const selectAllTypes = () => {
    setSelectedTypes(new Set())
  }

  const clearTypeFilter = () => {
    setSelectedTypes(new Set())
    setTypeSearch("")
  }

  const handleScan = () => {
    startScan({
      entityTypes: hasActiveTypeFilter ? effectiveSelectedTypes : null,
      similarityThreshold: threshold[0],
    })
  }

  const handleMerge = (pair: SimilarPair) => {
    const e1 = graphData.nodes.find((n) => n.key === pair.key1) ?? {
      key: pair.key1,
      label: pair.name1,
      type: pair.type1,
      properties: {},
    }
    const e2 = graphData.nodes.find((n) => n.key === pair.key2) ?? {
      key: pair.key2,
      label: pair.name2,
      type: pair.type2,
      properties: {},
    }
    setMergePair({ e1, e2, similarity: pair.similarity })
    setMergeOpen(true)
  }

  const handleReject = async (pair: SimilarPair) => {
    await graphAPI.rejectMergePair(caseId, pair.key1, pair.key2)
  }

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border px-4 py-3">
        <h3 className="text-sm font-semibold mb-3">Find Similar Entities</h3>

        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Popover open={typeFilterOpen} onOpenChange={setTypeFilterOpen}>
              <PopoverTrigger asChild>
                <Button variant="outline" size="sm" className="shrink-0">
                  <Filter className="size-3.5" />
                  Types
                  {hasActiveTypeFilter && (
                    <Badge variant="secondary" className="ml-1 h-4 px-1 text-[10px]">
                      {selectedTypes.size}
                    </Badge>
                  )}
                </Button>
              </PopoverTrigger>
              <PopoverContent align="start" className="w-64 p-0">
                <div className="border-b border-border p-2">
                  <Input
                    placeholder="Filter types..."
                    value={typeSearch}
                    onChange={(e) => setTypeSearch(e.target.value)}
                    className="h-7 text-xs"
                  />
                </div>
                <div className="flex items-center gap-1 border-b border-border px-2 py-1.5">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2 text-[11px]"
                    onClick={selectAllTypes}
                    disabled={allTypes.length === 0}
                  >
                    Select All
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2 text-[11px]"
                    onClick={clearTypeFilter}
                  >
                    Clear Filter
                  </Button>
                </div>
                <ScrollArea className="max-h-64">
                  <div className="p-1">
                    {visibleTypes.map(([type, count]) => {
                      const checked =
                        selectedTypes.size === 0 || selectedTypes.has(type)
                      return (
                        <button
                          key={type}
                          type="button"
                          onClick={() => toggleType(type)}
                          className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs hover:bg-muted"
                        >
                          <Checkbox checked={checked} />
                          <span
                            className="size-2.5 shrink-0 rounded-full"
                            style={{ backgroundColor: getNodeColor(type) }}
                          />
                          <span className="flex-1 text-left capitalize">{type}</span>
                          <Badge variant="outline" className="h-4 px-1 text-[10px]">
                            {count}
                          </Badge>
                        </button>
                      )
                    })}
                    {visibleTypes.length === 0 && (
                      <p className="px-2 py-3 text-center text-xs text-muted-foreground">
                        No types found
                      </p>
                    )}
                  </div>
                </ScrollArea>
              </PopoverContent>
            </Popover>

            <div className="min-w-0 flex-1">
              {hasActiveTypeFilter ? (
                <div className="flex flex-wrap gap-1">
                  {effectiveSelectedTypes
                    .sort((a, b) => a.localeCompare(b))
                    .map((type) => (
                      <NodeBadge key={type} type={type} className="text-[10px]">
                        {type}
                      </NodeBadge>
                    ))}
                </div>
              ) : (
                <span className="text-xs text-muted-foreground">All entity types</span>
              )}
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs text-muted-foreground">
                Similarity Threshold
              </span>
              <span className="text-xs font-medium">
                {Math.round(threshold[0] * 100)}%
              </span>
            </div>
            <Slider
              value={threshold}
              onValueChange={setThreshold}
              min={0.5}
              max={1}
              step={0.05}
            />
          </div>

          <div className="flex gap-2">
            {isScanning ? (
              <Button
                variant="outline"
                size="sm"
                onClick={cancel}
                className="flex-1"
              >
                <StopCircle className="size-3.5" />
                Cancel
              </Button>
            ) : (
              <Button
                variant="primary"
                size="sm"
                onClick={handleScan}
                className="flex-1"
              >
                <Search className="size-3.5" />
                Scan
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Progress */}
      {isScanning && progress && (
        <div className="border-b border-border px-4 py-2">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-muted-foreground">
              Scanning {currentType ?? "..."}
            </span>
            <span className="text-[10px] text-muted-foreground">
              {progress.compared}/{progress.total}
            </span>
          </div>
          <div className="h-1.5 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full bg-amber-500 transition-all"
              style={{
                width: `${progress.total ? (progress.compared / progress.total) * 100 : 0}%`,
              }}
            />
          </div>
          <p className="mt-1 text-[10px] text-muted-foreground">
            {progress.pairs_found} pairs found
          </p>
        </div>
      )}

      {isScanning && !progress && (
        <div className="flex justify-center py-4">
          <LoadingSpinner size="sm" />
        </div>
      )}

      {error && (
        <div className="mx-4 mt-2 rounded-md bg-red-50 dark:bg-red-500/10 p-2 text-xs text-red-600 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Results */}
      <ScrollArea className="flex-1">
        <div className="p-4 space-y-2">
          {results.length > 0 && (
            <div className="flex items-center justify-between mb-2">
              <Badge variant="amber">{results.length} pairs</Badge>
              {hasActiveTypeFilter && (
                <Badge variant="outline" className="text-[10px]">
                  {effectiveSelectedTypes.length} type{effectiveSelectedTypes.length !== 1 ? "s" : ""}
                </Badge>
              )}
            </div>
          )}
          {!isScanning && results.length === 0 && !error && (
            <p className="text-center text-xs text-muted-foreground py-4">
              Click Scan to find potential duplicate entities
            </p>
          )}
          {results.map((pair) => (
            <div
              key={`${pair.key1}-${pair.key2}`}
              className="rounded-lg border p-3"
            >
              <ConfidenceBar value={pair.similarity} className="mb-2" />
              <div className="grid grid-cols-2 gap-2 mb-2">
                <div className="flex items-center gap-1.5">
                  <NodeBadge type={pair.type1} />
                  <span className="min-w-0 truncate text-xs">{pair.name1}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <NodeBadge type={pair.type2} />
                  <span className="min-w-0 truncate text-xs">{pair.name2}</span>
                </div>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setComparePair(pair)
                    setCompareOpen(true)
                  }}
                >
                  <Eye className="size-3" />
                  Compare
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleMerge(pair)}
                >
                  <GitMerge className="size-3" />
                  Merge
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleReject(pair)}
                >
                  <X className="size-3" />
                  Dismiss
                </Button>
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>

      <EntityComparisonDialog
        open={compareOpen}
        onOpenChange={setCompareOpen}
        pair={comparePair}
        caseId={caseId}
        onMerge={handleMerge}
        onReject={handleReject}
      />

      <MergeEntitiesDialog
        open={mergeOpen}
        onOpenChange={setMergeOpen}
        entity1={mergePair.e1}
        entity2={mergePair.e2}
        caseId={caseId}
        similarity={mergePair.similarity}
        onMerged={() => {
          setMergeOpen(false)
          onRefresh()
        }}
      />
    </div>
  )
}
