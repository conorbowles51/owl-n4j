import { useState, useCallback } from "react"
import { useGraphStore } from "@/stores/graph.store"

interface ContextMenuState {
  open: boolean
  nodeKey: string | null
  nodeLabel: string | null
  x: number
  y: number
}

export function useGraphInteraction() {
  const { selectedNodeKeys, selectNodes, addToSelection, clearSelection } = useGraphStore()
  const [hoveredNode, setHoveredNode] = useState<string | null>(null)
  const [contextMenu, setContextMenu] = useState<ContextMenuState>({
    open: false,
    nodeKey: null,
    nodeLabel: null,
    x: 0,
    y: 0,
  })

  const handleNodeClick = useCallback(
    (key: string, multiSelect: boolean) => {
      if (multiSelect) {
        addToSelection(key)
      } else {
        selectNodes([key])
      }
    },
    [selectNodes, addToSelection]
  )

  const handleNodeDoubleClick = useCallback(
    (key: string) => {
      // Double-click expands the node — handled by parent
      selectNodes([key])
    },
    [selectNodes]
  )

  const handleNodeRightClick = useCallback(
    (key: string, label: string, x: number, y: number) => {
      setContextMenu({ open: true, nodeKey: key, nodeLabel: label, x, y })
    },
    []
  )

  const handleBackgroundClick = useCallback(() => {
    clearSelection()
    setContextMenu((prev) => ({ ...prev, open: false }))
  }, [clearSelection])

  const closeContextMenu = useCallback(() => {
    setContextMenu((prev) => ({ ...prev, open: false }))
  }, [])

  return {
    selectedNodeKeys,
    hoveredNode,
    setHoveredNode,
    contextMenu,
    closeContextMenu,
    handleNodeClick,
    handleNodeDoubleClick,
    handleNodeRightClick,
    handleBackgroundClick,
  }
}
