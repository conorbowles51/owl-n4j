import { useMemo } from "react"
import type { GraphData, GraphNode } from "@/types/graph.types"
import { useGraphStore } from "@/stores/graph.store"

interface SearchResult {
  node: GraphNode
  matchField: string
  matchValue: string
}

export function useGraphSearch(data: GraphData | undefined) {
  const { searchTerm, filters } = useGraphStore()

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
      const nodeKeys = new Set(nodes.map((n) => n.key))
      edges = edges.filter(
        (e) => nodeKeys.has(e.source) && nodeKeys.has(e.target)
      )
    }

    // Apply search term
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase()
      nodes = nodes.filter(
        (n) =>
          n.label.toLowerCase().includes(term) ||
          n.type.toLowerCase().includes(term) ||
          Object.values(n.properties).some(
            (v) => typeof v === "string" && v.toLowerCase().includes(term)
          )
      )
      const nodeKeys = new Set(nodes.map((n) => n.key))
      edges = edges.filter(
        (e) => nodeKeys.has(e.source) && nodeKeys.has(e.target)
      )
    }

    return { nodes, edges }
  }, [data, searchTerm, filters])

  const searchResults = useMemo((): SearchResult[] => {
    if (!data || !searchTerm.trim()) return []
    const term = searchTerm.toLowerCase()

    return data.nodes
      .filter((n) => n.label.toLowerCase().includes(term))
      .slice(0, 20)
      .map((node) => ({
        node,
        matchField: "label",
        matchValue: node.label,
      }))
  }, [data, searchTerm])

  return {
    filteredData,
    searchResults,
    totalNodes: data?.nodes.length ?? 0,
    filteredNodes: filteredData?.nodes.length ?? 0,
  }
}
