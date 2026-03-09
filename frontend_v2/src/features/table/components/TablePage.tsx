import { useState, useMemo } from "react"
import { useParams } from "react-router-dom"
import { Download, Filter, Columns } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { NodeBadge } from "@/components/ui/node-badge"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { EmptyState } from "@/components/ui/empty-state"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useGraphData } from "@/features/graph/hooks/use-graph-data"
import type { EntityType } from "@/lib/theme"

export function TablePage() {
  const { id: caseId } = useParams()
  const { data: graphData, isLoading } = useGraphData(caseId)
  const [search, setSearch] = useState("")
  const [sortKey, setSortKey] = useState<"label" | "type">("label")
  const [sortAsc, setSortAsc] = useState(true)

  const filtered = useMemo(() => {
    if (!graphData) return []
    let nodes = graphData.nodes.filter(
      (n) =>
        n.label.toLowerCase().includes(search.toLowerCase()) ||
        n.type.toLowerCase().includes(search.toLowerCase())
    )
    nodes.sort((a, b) => {
      const cmp = a[sortKey].localeCompare(b[sortKey])
      return sortAsc ? cmp : -cmp
    })
    return nodes
  }, [graphData, search, sortKey, sortAsc])

  const handleSort = (key: "label" | "type") => {
    if (sortKey === key) {
      setSortAsc(!sortAsc)
    } else {
      setSortKey(key)
      setSortAsc(true)
    }
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-border px-4 py-2">
        <Input
          placeholder="Filter entities..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <Button variant="ghost" size="sm">
          <Filter className="size-3.5" />
          Filters
        </Button>
        <Button variant="ghost" size="sm">
          <Columns className="size-3.5" />
          Columns
        </Button>
        <div className="flex-1" />
        <Badge variant="slate">{filtered.length} entities</Badge>
        <Button variant="outline" size="sm">
          <Download className="size-3.5" />
          Export CSV
        </Button>
      </div>

      <div className="flex-1 overflow-auto">
        {filtered.length === 0 ? (
          <EmptyState
            title="No entities found"
            description={search ? "Try a different search" : "No data available"}
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead
                  className="cursor-pointer"
                  onClick={() => handleSort("label")}
                >
                  Name {sortKey === "label" && (sortAsc ? "↑" : "↓")}
                </TableHead>
                <TableHead
                  className="cursor-pointer"
                  onClick={() => handleSort("type")}
                >
                  Type {sortKey === "type" && (sortAsc ? "↑" : "↓")}
                </TableHead>
                <TableHead>Properties</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((node) => (
                <TableRow key={node.key}>
                  <TableCell className="font-medium">{node.label}</TableCell>
                  <TableCell>
                    <NodeBadge type={node.type as EntityType} />
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {Object.keys(node.properties).length} properties
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  )
}
