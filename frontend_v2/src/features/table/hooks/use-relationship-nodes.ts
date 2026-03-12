import { useMemo } from "react"
import type { GraphNode, GraphEdge } from "@/types/graph.types"
import type { RelationshipNavEntry } from "../stores/table.store"

export interface RelationshipInfo {
  relationshipTypes: string[]
  direction: "outgoing" | "incoming" | "both"
}

export interface UseRelationshipNodesResult {
  displayNodes: GraphNode[]
  relationshipMap: Map<string, RelationshipInfo>
  isExploring: boolean
  currentParent: RelationshipNavEntry | null
}

export function useRelationshipNodes(
  nodes: GraphNode[],
  edges: GraphEdge[],
  navigationStack: RelationshipNavEntry[]
): UseRelationshipNodesResult {
  return useMemo(() => {
    if (navigationStack.length === 0) {
      return {
        displayNodes: nodes,
        relationshipMap: new Map(),
        isExploring: false,
        currentParent: null,
      }
    }

    const currentParent = navigationStack[navigationStack.length - 1]
    const focalKey = currentParent.nodeKey

    // Build a lookup of nodeKey -> GraphNode
    const nodeMap = new Map<string, GraphNode>()
    for (const n of nodes) {
      nodeMap.set(n.key, n)
    }

    // Find all edges connected to the focal node, group by other node key
    const relMap = new Map<string, { types: Set<string>; outgoing: boolean; incoming: boolean }>()

    for (const edge of edges) {
      let otherKey: string | null = null
      let isOutgoing = false
      let isIncoming = false

      if (edge.source === focalKey) {
        otherKey = edge.target
        isOutgoing = true
      } else if (edge.target === focalKey) {
        otherKey = edge.source
        isIncoming = true
      }

      if (!otherKey || !nodeMap.has(otherKey)) continue

      const existing = relMap.get(otherKey)
      if (existing) {
        existing.types.add(edge.type)
        if (isOutgoing) existing.outgoing = true
        if (isIncoming) existing.incoming = true
      } else {
        relMap.set(otherKey, {
          types: new Set([edge.type]),
          outgoing: isOutgoing,
          incoming: isIncoming,
        })
      }
    }

    const displayNodes: GraphNode[] = []
    const relationshipMap = new Map<string, RelationshipInfo>()

    for (const [key, info] of relMap) {
      const node = nodeMap.get(key)!
      displayNodes.push(node)
      relationshipMap.set(key, {
        relationshipTypes: Array.from(info.types),
        direction:
          info.outgoing && info.incoming
            ? "both"
            : info.outgoing
              ? "outgoing"
              : "incoming",
      })
    }

    return { displayNodes, relationshipMap, isExploring: true, currentParent }
  }, [nodes, edges, navigationStack])
}
