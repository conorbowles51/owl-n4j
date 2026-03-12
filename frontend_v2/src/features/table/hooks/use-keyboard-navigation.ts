import { useEffect, useRef, useCallback } from "react"
import type { GraphNode } from "@/types/graph.types"

interface UseKeyboardNavigationParams {
  pageNodes: GraphNode[]
  onSelectNode: (key: string) => void
  onToggleChecked: (key: string) => void
  onCheckRange: (keys: string[]) => void
  onSelectAll: () => void
  onClearSelection: () => void
  searchInputRef: React.RefObject<HTMLInputElement | null>
  containerRef: React.RefObject<HTMLDivElement | null>
  enabled: boolean
}

export function useKeyboardNavigation({
  pageNodes,
  onSelectNode,
  onToggleChecked,
  onCheckRange,
  onSelectAll,
  onClearSelection,
  searchInputRef,
  containerRef,
  enabled,
}: UseKeyboardNavigationParams) {
  const focusIndexRef = useRef(-1)

  const scrollToRow = useCallback(
    (index: number) => {
      const container = containerRef.current
      if (!container) return
      const rows = container.querySelectorAll<HTMLElement>("[data-row-index]")
      const row = rows[index]
      if (row) {
        row.scrollIntoView({ block: "nearest" })
        row.focus({ preventScroll: true })
      }
    },
    [containerRef]
  )

  useEffect(() => {
    if (!enabled) return

    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      const isInput =
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.tagName === "SELECT" ||
        target.isContentEditable

      // Slash focuses search from anywhere
      if (e.key === "/" && !isInput) {
        e.preventDefault()
        searchInputRef.current?.focus()
        return
      }

      // Escape clears or blurs
      if (e.key === "Escape") {
        if (isInput) {
          ;(target as HTMLInputElement).blur()
        } else {
          onClearSelection()
          focusIndexRef.current = -1
        }
        return
      }

      // Don't handle navigation keys while in input
      if (isInput) return

      // Ctrl/Cmd+A select all
      if ((e.ctrlKey || e.metaKey) && e.key === "a") {
        e.preventDefault()
        onSelectAll()
        return
      }

      if (e.key === "ArrowDown" || e.key === "j") {
        e.preventDefault()
        const nextIndex = Math.min(focusIndexRef.current + 1, pageNodes.length - 1)
        focusIndexRef.current = nextIndex
        scrollToRow(nextIndex)

        if (e.shiftKey && pageNodes[nextIndex]) {
          onToggleChecked(pageNodes[nextIndex].key)
        }
        return
      }

      if (e.key === "ArrowUp" || e.key === "k") {
        e.preventDefault()
        const nextIndex = Math.max(focusIndexRef.current - 1, 0)
        focusIndexRef.current = nextIndex
        scrollToRow(nextIndex)

        if (e.shiftKey && pageNodes[nextIndex]) {
          onToggleChecked(pageNodes[nextIndex].key)
        }
        return
      }

      if (e.key === "Enter") {
        e.preventDefault()
        const node = pageNodes[focusIndexRef.current]
        if (node) onSelectNode(node.key)
        return
      }

      if (e.key === " ") {
        e.preventDefault()
        const node = pageNodes[focusIndexRef.current]
        if (node) onToggleChecked(node.key)
        return
      }
    }

    document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [
    enabled,
    pageNodes,
    onSelectNode,
    onToggleChecked,
    onCheckRange,
    onSelectAll,
    onClearSelection,
    searchInputRef,
    scrollToRow,
  ])

  return { focusIndexRef }
}
