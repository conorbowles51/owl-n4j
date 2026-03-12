import { useCallback } from "react"
import { ChevronUp, ChevronDown, ChevronsUpDown, Network, ArrowRight, ArrowLeft, ArrowLeftRight } from "lucide-react"
import { Checkbox } from "@/components/ui/checkbox"
import { NodeBadge } from "@/components/ui/node-badge"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/cn"
import type { GraphNode } from "@/types/graph.types"
import type { EntityType } from "@/lib/theme"
import type { TableColumn } from "../hooks/use-table-columns"
import type { SortColumn } from "../stores/table.store"
import type { RelationshipInfo } from "../hooks/use-relationship-nodes"

interface TableGridProps {
  pageNodes: GraphNode[]
  visibleColumns: TableColumn[]
  sortColumns: SortColumn[]
  onToggleSort: (key: string, multi: boolean) => void
  // Selection (detail panel)
  selectedNodeKey: string | null
  onSelectNode: (key: string) => void
  // Checkbox selection (bulk)
  checkedKeys: Set<string>
  onToggleChecked: (key: string) => void
  onCheckRange: (startKey: string, endKey: string) => void
  onToggleAllChecked: () => void
  allChecked: boolean
  someChecked: boolean
  // Data
  connectionCounts: Map<string, number>
  sourceCounts: Map<string, number>
  // Search highlight
  searchTerm: string
  // Container ref for keyboard nav
  containerRef: React.RefObject<HTMLDivElement | null>
  // Relationship exploration
  onExploreRelationships?: (key: string) => void
  relationshipMap?: Map<string, RelationshipInfo>
  isExploring?: boolean
}

function HighlightText({ text, term }: { text: string; term: string }) {
  if (!term || !text) return <>{text}</>
  const lower = text.toLowerCase()
  const termLower = term.toLowerCase()
  const idx = lower.indexOf(termLower)
  if (idx === -1) return <>{text}</>
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-amber-400/30 text-foreground rounded-sm px-0.5">{text.slice(idx, idx + term.length)}</mark>
      {text.slice(idx + term.length)}
    </>
  )
}

function TruncatedCell({
  text,
  maxLength = 120,
  className,
  searchTerm,
}: {
  text: string
  maxLength?: number
  className?: string
  searchTerm?: string
}) {
  const truncated = text.length > maxLength
  const display = truncated ? text.slice(0, maxLength) + "..." : text

  if (truncated) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span className={className}>
            <HighlightText text={display} term={searchTerm ?? ""} />
          </span>
        </TooltipTrigger>
        <TooltipContent className="max-w-sm">
          <p className="text-xs">{text}</p>
        </TooltipContent>
      </Tooltip>
    )
  }

  return (
    <span className={className}>
      <HighlightText text={display} term={searchTerm ?? ""} />
    </span>
  )
}

function SortIcon({ column, sortColumns }: { column: TableColumn; sortColumns: SortColumn[] }) {
  if (!column.sortable) return null
  const sort = sortColumns.find((s) => s.key === column.key)
  const idx = sortColumns.findIndex((s) => s.key === column.key)
  if (!sort) {
    return <ChevronsUpDown className="ml-1 inline size-3 text-muted-foreground/40" />
  }
  return (
    <span className="ml-1 inline-flex items-center">
      {sort.asc ? (
        <ChevronUp className="inline size-3 text-foreground" />
      ) : (
        <ChevronDown className="inline size-3 text-foreground" />
      )}
      {sortColumns.length > 1 && (
        <span className="text-[9px] text-muted-foreground">{idx + 1}</span>
      )}
    </span>
  )
}

function RelationshipCell({ info }: { info: RelationshipInfo }) {
  const DirectionIcon =
    info.direction === "both"
      ? ArrowLeftRight
      : info.direction === "outgoing"
        ? ArrowRight
        : ArrowLeft

  return (
    <span className="inline-flex items-center gap-1 flex-wrap">
      <DirectionIcon className="size-3 text-muted-foreground shrink-0" />
      {info.relationshipTypes.map((t) => (
        <Badge
          key={t}
          variant="outline"
          className="text-[10px] px-1 py-0 h-4 font-mono text-amber-600 dark:text-amber-400 border-amber-500/30"
        >
          {t}
        </Badge>
      ))}
    </span>
  )
}

function CellRenderer({
  node,
  column,
  connectionCounts,
  sourceCounts,
  searchTerm,
  onExploreRelationships,
  relationshipMap,
}: {
  node: GraphNode
  column: TableColumn
  connectionCounts: Map<string, number>
  sourceCounts: Map<string, number>
  searchTerm: string
  onExploreRelationships?: (key: string) => void
  relationshipMap?: Map<string, RelationshipInfo>
}) {
  switch (column.key) {
    case "label": {
      const connCount = connectionCounts.get(node.key) ?? 0
      return (
        <span className="inline-flex items-center gap-1.5">
          <TruncatedCell
            text={node.label}
            maxLength={60}
            className="font-medium"
            searchTerm={searchTerm}
          />
          {connCount > 0 && onExploreRelationships && (
            <button
              onClick={(e) => { e.stopPropagation(); onExploreRelationships(node.key) }}
              className="rounded p-0.5 text-muted-foreground/50 hover:text-amber-500 hover:bg-amber-500/10 transition-colors opacity-0 group-hover:opacity-100"
              title={`Explore ${connCount} relationships`}
            >
              <Network className="size-3.5" />
            </button>
          )}
        </span>
      )
    }
    case "_relationship": {
      const info = relationshipMap?.get(node.key)
      if (!info) return <span className="text-muted-foreground">—</span>
      return <RelationshipCell info={info} />
    }
    case "type":
      return <NodeBadge type={node.type as EntityType} />
    case "connections":
      return (
        <Badge variant="outline" className="font-mono text-[11px]">
          {connectionCounts.get(node.key) ?? 0}
        </Badge>
      )
    case "sources":
      return (
        <Badge variant="outline" className="font-mono text-[11px]">
          {sourceCounts.get(node.key) ?? 0}
        </Badge>
      )
    default:
      if (column.key.startsWith("prop:")) {
        const propKey = column.key.slice(5)
        const val = node.properties[propKey]
        if (val == null) return <span className="text-muted-foreground">—</span>
        return (
          <TruncatedCell
            text={String(val)}
            maxLength={80}
            className="font-mono text-xs"
            searchTerm={searchTerm}
          />
        )
      }
      return null
  }
}

export function TableGrid({
  pageNodes,
  visibleColumns,
  sortColumns,
  onToggleSort,
  selectedNodeKey,
  onSelectNode,
  checkedKeys,
  onToggleChecked,
  onCheckRange,
  onToggleAllChecked,
  allChecked,
  someChecked,
  connectionCounts,
  sourceCounts,
  searchTerm,
  containerRef,
  onExploreRelationships,
  relationshipMap,
}: TableGridProps) {
  const handleRowClick = useCallback(
    (e: React.MouseEvent, node: GraphNode) => {
      // Don't handle if clicking checkbox
      if ((e.target as HTMLElement).closest('[role="checkbox"]')) return

      if (e.shiftKey) {
        // Range select is handled by the parent
        onCheckRange(node.key, node.key)
      } else if (e.ctrlKey || e.metaKey) {
        onToggleChecked(node.key)
      } else {
        onSelectNode(node.key)
      }
    },
    [onSelectNode, onToggleChecked, onCheckRange]
  )

  return (
    <div ref={containerRef} className="flex-1 overflow-auto">
      <Table>
        <TableHeader className="sticky top-0 z-10 bg-card">
          <TableRow className="hover:bg-transparent">
            {visibleColumns.map((col) =>
              col.key === "_checkbox" ? (
                <TableHead key={col.key} className="w-10 px-2">
                  <Checkbox
                    checked={allChecked ? true : someChecked ? "indeterminate" : false}
                    onCheckedChange={onToggleAllChecked}
                  />
                </TableHead>
              ) : (
                <TableHead
                  key={col.key}
                  className={cn(
                    "h-9 text-[13px]",
                    col.sortable && "cursor-pointer select-none hover:text-foreground"
                  )}
                  onClick={(e) => col.sortable && onToggleSort(col.key, e.shiftKey)}
                >
                  {col.label}
                  <SortIcon column={col} sortColumns={sortColumns} />
                </TableHead>
              )
            )}
          </TableRow>
        </TableHeader>
        <TableBody>
          {pageNodes.map((node, idx) => {
            const isSelected = selectedNodeKey === node.key
            const isChecked = checkedKeys.has(node.key)
            return (
              <TableRow
                key={node.key}
                data-row-index={idx}
                tabIndex={0}
                className={cn(
                  "group h-9 cursor-pointer text-[13px] transition-colors",
                  "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
                  isSelected && "bg-amber-500/10 border-l-2 border-l-amber-500",
                  isChecked && !isSelected && "bg-muted/50",
                  !isSelected && !isChecked && "hover:bg-muted/30"
                )}
                onClick={(e) => handleRowClick(e, node)}
              >
                {visibleColumns.map((col) =>
                  col.key === "_checkbox" ? (
                    <TableCell key={col.key} className="w-10 px-2">
                      <Checkbox
                        checked={isChecked}
                        onCheckedChange={() => onToggleChecked(node.key)}
                      />
                    </TableCell>
                  ) : (
                    <TableCell key={col.key} className="py-1">
                      <CellRenderer
                        node={node}
                        column={col}
                        connectionCounts={connectionCounts}
                        sourceCounts={sourceCounts}
                        searchTerm={searchTerm}
                        onExploreRelationships={onExploreRelationships}
                        relationshipMap={relationshipMap}
                      />
                    </TableCell>
                  )
                )}
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
