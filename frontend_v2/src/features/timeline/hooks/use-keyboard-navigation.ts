import { useEffect, useCallback, useRef } from "react"
import type { StreamItem } from "./use-filtered-events"

interface UseKeyboardNavigationParams {
  items: StreamItem[]
  selectedEventKey: string | null
  onSelectEvent: (key: string) => void
  onClearSelection: () => void
  onPrevCluster: () => void
  onNextCluster: () => void
  onToggleFilterSidebar: () => void
  searchInputRef: React.RefObject<HTMLInputElement | null>
  scrollToEvent: (key: string) => void
}

export function useKeyboardNavigation({
  items,
  selectedEventKey,
  onSelectEvent,
  onClearSelection,
  onPrevCluster,
  onNextCluster,
  onToggleFilterSidebar,
  searchInputRef,
  scrollToEvent,
}: UseKeyboardNavigationParams) {
  const focusIndexRef = useRef(-1)

  // Build event-only index list
  const eventKeys = items
    .filter((it): it is Extract<StreamItem, { kind: "event" }> => it.kind === "event")
    .map((it) => it.event.key)

  // Sync focus index with selection
  useEffect(() => {
    if (selectedEventKey) {
      const idx = eventKeys.indexOf(selectedEventKey)
      if (idx >= 0) focusIndexRef.current = idx
    }
  }, [selectedEventKey, eventKeys])

  const moveFocus = useCallback(
    (delta: number) => {
      if (eventKeys.length === 0) return
      let next = focusIndexRef.current + delta
      next = Math.max(0, Math.min(eventKeys.length - 1, next))
      focusIndexRef.current = next
      const key = eventKeys[next]
      onSelectEvent(key)
      scrollToEvent(key)
    },
    [eventKeys, onSelectEvent, scrollToEvent]
  )

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement
      ) {
        // Only handle Escape in inputs
        if (e.key === "Escape") {
          ;(target as HTMLElement).blur()
          e.preventDefault()
        }
        return
      }

      switch (e.key) {
        case "ArrowDown":
        case "j":
          e.preventDefault()
          moveFocus(1)
          break
        case "ArrowUp":
        case "k":
          e.preventDefault()
          moveFocus(-1)
          break
        case "Enter":
        case " ":
          if (selectedEventKey) {
            e.preventDefault()
            // Already selected — detail panel is open
          } else if (focusIndexRef.current >= 0) {
            e.preventDefault()
            const key = eventKeys[focusIndexRef.current]
            if (key) onSelectEvent(key)
          }
          break
        case "Escape":
          e.preventDefault()
          onClearSelection()
          focusIndexRef.current = -1
          break
        case "ArrowLeft":
          if (e.altKey) {
            e.preventDefault()
            onPrevCluster()
          }
          break
        case "ArrowRight":
          if (e.altKey) {
            e.preventDefault()
            onNextCluster()
          }
          break
        case "[":
        case "]":
          e.preventDefault()
          onToggleFilterSidebar()
          break
        case "/":
          e.preventDefault()
          searchInputRef.current?.focus()
          break
      }
    }

    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [
    moveFocus,
    selectedEventKey,
    eventKeys,
    onSelectEvent,
    onClearSelection,
    onPrevCluster,
    onNextCluster,
    onToggleFilterSidebar,
    searchInputRef,
  ])
}
