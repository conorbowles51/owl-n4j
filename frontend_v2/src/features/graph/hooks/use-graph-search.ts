import { useMemo } from "react"
import type { GraphData, GraphNode } from "@/types/graph.types"
import { useGraphStore } from "@/stores/graph.store"
import { buildEntityFuse, filterNodesBySearch } from "../lib/entity-search"

interface SearchResult {
  node: GraphNode
  matchField: string
  matchValue: string
}

export function useGraphSearch(data: GraphData | undefined) {
  const { searchTerm, filters } = useGraphStore()

  const fuse = useMemo(
    () => (data ? buildEntityFuse(data.nodes) : null),
    [data]
  )

  const filteredData = useMemo(() => {
    if (!data) return undefined

    let nodes = data.nodes
    let edges = data.edges

    // Apply entity type filters
    const activeFilters = Object.entries(filters)
      .filter(([, active]) => active)
      .map(([type]) => type)

    if (activeFilters.length > 0) {
      nodes = nodes.filter((n) => activeFilters.includes(n.type))
    }

    // Apply search term (fuzzy + alias-aware)
    if (searchTerm.trim() && fuse) {
      nodes = filterNodesBySearch(nodes, searchTerm, fuse)
    }

    // Drop edges whose endpoints didn't survive
    if (nodes.length !== data.nodes.length) {
      const nodeKeys = new Set(nodes.map((n) => n.key))
      edges = edges.filter(
        (e) => nodeKeys.has(e.source) && nodeKeys.has(e.target)
      )
    }

    return { nodes, edges }
  }, [data, searchTerm, filters, fuse])

  const searchResults = useMemo((): SearchResult[] => {
    if (!data || !searchTerm.trim() || !fuse) return []
    return filterNodesBySearch(data.nodes, searchTerm, fuse)
      .slice(0, 20)
      .map((node) => ({
        node,
        matchField: "label",
        matchValue: node.label,
      }))
  }, [data, searchTerm, fuse])

  return {
    filteredData,
    searchResults,
    totalNodes: data?.nodes.length ?? 0,
    filteredNodes: filteredData?.nodes.length ?? 0,
  }
}
