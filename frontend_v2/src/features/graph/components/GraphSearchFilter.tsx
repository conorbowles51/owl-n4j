import { useState } from "react"
import { Search, ChevronDown, ChevronRight } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Slider } from "@/components/ui/slider"
import { Separator } from "@/components/ui/separator"
import { NodeBadge } from "@/components/ui/node-badge"
import { CypherInput } from "@/components/ui/cypher-input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/cn"
import { nodeColors, type EntityType } from "@/lib/theme"
import { useGraphStore } from "@/stores/graph.store"

interface GraphSearchFilterProps {
  entityTypes?: string[]
  onCypherExecute?: (query: string) => void
  className?: string
}

const allEntityTypes = Object.keys(nodeColors) as EntityType[]

export function GraphSearchFilter({
  entityTypes,
  onCypherExecute,
  className,
}: GraphSearchFilterProps) {
  const { searchTerm, setSearchTerm, filters, setFilter } = useGraphStore()
  const [confidenceThreshold, setConfidenceThreshold] = useState([0])
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [cypherQuery, setCypherQuery] = useState("")

  const availableTypes = entityTypes?.length
    ? allEntityTypes.filter((t) => entityTypes.includes(t))
    : allEntityTypes

  const activeFilterCount = Object.values(filters).filter(Boolean).length

  const clearFilters = () => {
    availableTypes.forEach((type) => setFilter(type, false))
    setConfidenceThreshold([0])
    setSearchTerm("")
  }

  return (
    <div className={cn("flex flex-col gap-3 rounded-lg border bg-card p-3", className)}>
      {/* Search */}
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          placeholder="Search entities..."
          className="pl-8"
        />
      </div>

      {/* Entity type filters */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-medium text-foreground">Entity Types</span>
          {activeFilterCount > 0 && (
            <Button variant="ghost" size="sm" onClick={clearFilters} className="h-5 px-1 text-[10px]">
              Clear ({activeFilterCount})
            </Button>
          )}
        </div>
        <ScrollArea className="max-h-[180px]">
          <div className="space-y-1">
            {availableTypes.map((type) => (
              <label
                key={type}
                className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 hover:bg-muted/50"
              >
                <Checkbox
                  checked={filters[type] ?? false}
                  onCheckedChange={(checked) => setFilter(type, !!checked)}
                />
                <NodeBadge type={type} />
              </label>
            ))}
          </div>
        </ScrollArea>
      </div>

      <Separator />

      {/* Confidence threshold */}
      <div>
        <span className="text-xs font-medium text-foreground">
          Min Confidence: {confidenceThreshold[0]}%
        </span>
        <Slider
          value={confidenceThreshold}
          onValueChange={setConfidenceThreshold}
          max={100}
          step={5}
          className="mt-2"
        />
      </div>

      <Separator />

      {/* Advanced: Cypher */}
      <button
        className="flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
        onClick={() => setShowAdvanced(!showAdvanced)}
      >
        {showAdvanced ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
        Advanced Query
      </button>
      {showAdvanced && (
        <div className="space-y-2">
          <CypherInput
            value={cypherQuery}
            onChange={(e) => setCypherQuery(e.target.value)}
            onExecute={(val) => onCypherExecute?.(val)}
            placeholder="MATCH (n) RETURN n LIMIT 25"
          />
          <p className="text-[10px] text-muted-foreground">
            Press Ctrl+Enter to execute
          </p>
        </div>
      )}
    </div>
  )
}
