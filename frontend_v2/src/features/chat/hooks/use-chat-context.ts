import { useMemo } from "react"
import { useGraphStore } from "@/stores/graph.store"
import type { EntityType } from "@/lib/theme"

interface ContextNode {
  key: string
  label: string
  type: EntityType
}

export function useChatContext(_caseId: string) {
  const selectedNodeKeys = useGraphStore((s) => s.selectedNodeKeys)

  // Selected nodes are derived from keys only — detail resolution
  // happens via TanStack Query in components that need full details
  const selectedNodes = useMemo<ContextNode[]>(() => {
    return Array.from(selectedNodeKeys).map((key) => ({
      key,
      label: key,
      type: "person" as EntityType,
    }))
  }, [selectedNodeKeys])

  const scopedDocument = useMemo<string | null>(() => {
    return null
  }, [])

  return {
    selectedNodes,
    scopedDocument,
    selectedNodeKeys: Array.from(selectedNodeKeys),
  }
}
