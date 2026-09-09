import { useMemo } from "react"
import type { GraphData } from "@/types/graph.types"
import { useGraphStore } from "@/stores/graph.store"
import { applyNodeSearch, buildEntityFuse } from "../lib/entity-search"

export function useGraphSearch(data: GraphData | undefined) {
  const { appliedSearchQuery, searchMode, selectedEntityTypes } = useGraphStore()

  const fuse = useMemo(
    () => (data ? buildEntityFuse(data.nodes) : null),
    [data]
  )

  const filteredData = useMemo(() => {
    if (!data) return undefined

    let nodes = data.nodes
    let edges = data.edges

    // Apply entity type filters
    if (selectedEntityTypes !== null) {
      nodes = nodes.filter((node) => selectedEntityTypes.has(node.type))
    }

    // Apply search term (fuzzy + alias-aware)
    if (appliedSearchQuery.trim() && fuse) {
      nodes = applyNodeSearch(nodes, appliedSearchQuery, searchMode, fuse)
    }

    // Drop edges whose endpoints didn't survive
    if (nodes.length !== data.nodes.length) {
      const nodeKeys = new Set(nodes.map((n) => n.key))
      edges = edges.filter(
        (e) => nodeKeys.has(e.source) && nodeKeys.has(e.target)
      )
    }

    return { nodes, edges }
  }, [data, appliedSearchQuery, searchMode, selectedEntityTypes, fuse])

  return {
    filteredData,
    totalNodes: data?.nodes.length ?? 0,
    filteredNodes: filteredData?.nodes.length ?? 0,
  }
}
