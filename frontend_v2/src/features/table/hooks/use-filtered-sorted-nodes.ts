import { useMemo } from "react"
import type { GraphNode, GraphEdge } from "@/types/graph.types"
import type { SortColumn } from "../stores/table.store"
import type { RelationshipInfo } from "./use-relationship-nodes"
import { buildEntityFuse, filterNodesBySearch } from "@/features/graph/lib/entity-search"

interface UseFilteredSortedNodesParams {
  nodes: GraphNode[]
  edges: GraphEdge[]
  searchTerm: string
  selectedTypes: Set<string>
  sortColumns: SortColumn[]
  pageSize: number
  currentPage: number
  relationshipMap?: Map<string, RelationshipInfo>
}

interface UseFilteredSortedNodesResult {
  filteredNodes: GraphNode[]
  pageNodes: GraphNode[]
  totalCount: number
  filteredCount: number
  pageCount: number
  typeCounts: Map<string, number>
  connectionCounts: Map<string, number>
  sourceCounts: Map<string, number>
}

export function countNodeSources(node: GraphNode): number {
  if (typeof node.source_count === "number") return node.source_count
  const sourceDocuments = new Set<string>()
  const sourceFiles = node.properties.source_files
  if (Array.isArray(sourceFiles)) {
    for (const sourceFile of sourceFiles) {
      if (typeof sourceFile === "string" && sourceFile.trim()) {
        sourceDocuments.add(sourceFile.trim())
      }
    }
  }
  for (const fact of node.verified_facts ?? []) {
    if (fact.source_doc?.trim()) sourceDocuments.add(fact.source_doc.trim())
  }
  return sourceDocuments.size
}

function getNodeSortValue(
  node: GraphNode,
  key: string,
  connectionCounts: Map<string, number>,
  sourceCounts: Map<string, number>,
  relationshipMap?: Map<string, RelationshipInfo>
): string | number {
  switch (key) {
    case "_relationship":
      return relationshipMap?.get(node.key)?.relationshipTypes.join(", ") ?? ""
    case "label":
      return node.label.toLowerCase()
    case "type":
      return node.type.toLowerCase()
    case "confidence":
      return node.confidence ?? 0
    case "summary":
      return (node.summary ?? "").toLowerCase()
    case "connections":
      return connectionCounts.get(node.key) ?? 0
    case "sources":
      return sourceCounts.get(node.key) ?? 0
    default:
      if (key.startsWith("prop:")) {
        const propKey = key.slice(5)
        const val = node.properties[propKey]
        if (val == null) return ""
        if (typeof val === "number") return val
        return String(val).toLowerCase()
      }
      return ""
  }
}

export function useFilteredSortedNodes({
  nodes,
  edges,
  searchTerm,
  selectedTypes,
  sortColumns,
  pageSize,
  currentPage,
  relationshipMap,
}: UseFilteredSortedNodesParams): UseFilteredSortedNodesResult {
  // Pre-compute connection and source counts
  const connectionCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const edge of edges) {
      counts.set(edge.source, (counts.get(edge.source) ?? 0) + 1)
      counts.set(edge.target, (counts.get(edge.target) ?? 0) + 1)
    }
    return counts
  }, [edges])

  const sourceCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const node of nodes) {
      counts.set(node.key, countNodeSources(node))
    }
    return counts
  }, [nodes])

  // Compute type counts before filtering (for TypeFilterPopover badges)
  const typeCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const node of nodes) {
      counts.set(node.type, (counts.get(node.type) ?? 0) + 1)
    }
    return counts
  }, [nodes])

  const fuse = useMemo(() => buildEntityFuse(nodes), [nodes])

  const result = useMemo(() => {
    // [1] Type filter
    let filtered = selectedTypes.size > 0
      ? nodes.filter((n) => selectedTypes.has(n.type))
      : [...nodes]

    // [2] Text search (fuzzy + alias-aware)
    if (searchTerm.trim()) {
      filtered = filterNodesBySearch(filtered, searchTerm, fuse)
    }

    // [3] Multi-column sort
    if (sortColumns.length > 0) {
      filtered.sort((a, b) => {
        for (const { key, asc } of sortColumns) {
          const aVal = getNodeSortValue(a, key, connectionCounts, sourceCounts, relationshipMap)
          const bVal = getNodeSortValue(b, key, connectionCounts, sourceCounts, relationshipMap)
          let cmp: number
          if (typeof aVal === "number" && typeof bVal === "number") {
            cmp = aVal - bVal
          } else {
            cmp = String(aVal).localeCompare(String(bVal))
          }
          if (cmp !== 0) return asc ? cmp : -cmp
        }
        return 0
      })
    }

    const filteredCount = filtered.length
    const pageCount = pageSize === -1 ? 1 : Math.max(1, Math.ceil(filteredCount / pageSize))

    // [4] Paginate
    const pageNodes =
      pageSize === -1
        ? filtered
        : filtered.slice(currentPage * pageSize, (currentPage + 1) * pageSize)

    return { filteredNodes: filtered, pageNodes, filteredCount, pageCount }
  }, [nodes, searchTerm, selectedTypes, sortColumns, pageSize, currentPage, connectionCounts, sourceCounts, relationshipMap, fuse])

  return {
    ...result,
    totalCount: nodes.length,
    typeCounts,
    connectionCounts,
    sourceCounts,
  }
}
