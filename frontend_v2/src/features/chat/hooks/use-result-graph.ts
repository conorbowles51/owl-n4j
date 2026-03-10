import { useMemo } from "react"
import { useChatStore } from "../stores/chat.store"
import type { ResultGraph } from "../types"

export function useResultGraph() {
  const mode = useChatStore((s) => s.resultGraphMode)
  const cumulative = useChatStore((s) => s.cumulativeGraph)
  const last = useChatStore((s) => s.lastResponseGraph)
  const selectedNodeKey = useChatStore((s) => s.selectedResultNodeKey)
  const setMode = useChatStore((s) => s.setResultGraphMode)
  const setSelectedNodeKey = useChatStore((s) => s.setSelectedResultNodeKey)

  const displayGraph: ResultGraph = useMemo(
    () => (mode === "cumulative" ? cumulative : last),
    [mode, cumulative, last]
  )

  const selectedNode = useMemo(
    () =>
      selectedNodeKey
        ? displayGraph.nodes.find((n) => n.key === selectedNodeKey) ?? null
        : null,
    [selectedNodeKey, displayGraph.nodes]
  )

  const isEmpty =
    displayGraph.nodes.length === 0 && displayGraph.links.length === 0

  return {
    mode,
    setMode,
    displayGraph,
    selectedNodeKey,
    setSelectedNodeKey,
    selectedNode,
    isEmpty,
    nodeCount: displayGraph.nodes.length,
    linkCount: displayGraph.links.length,
  }
}
