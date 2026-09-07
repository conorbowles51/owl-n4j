import { createContext, useContext, useEffect, useRef, useState } from "react"
import { useEvidenceStore } from "../evidence.store"
import type { MoveSource } from "../utils/move-targets"

export const EVIDENCE_DRAG_TYPE = "application/x-loupe-evidence-move"
export interface EvidenceMoves {
  canMove: boolean
  dragging: MoveSource | null
  openMove: (source: MoveSource) => void
  startDrag: (event: React.DragEvent, source: MoveSource) => void
  endDrag: () => void
  invalidReason: (
    source: MoveSource,
    destination: string | null
  ) => string | null
  move: (source: MoveSource, destination: string | null) => void
}
export const EvidenceMovesContext = createContext<EvidenceMoves | null>(null)
export const useEvidenceMoves = () => useContext(EvidenceMovesContext)

export function useEvidenceDropTarget(
  folderId: string | null,
  expandOnHover = false
) {
  const moves = useEvidenceMoves()
  const [over, setOver] = useState<MoveSource | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const clearTimer = () => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = null
  }
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current)
      timer.current = null
    },
    [moves?.dragging]
  )
  const valid = Boolean(
    moves?.canMove &&
    moves.dragging &&
    !moves.invalidReason(moves.dragging, folderId)
  )
  return {
    "data-drop-active": over === moves?.dragging && valid ? "true" : undefined,
    onDragOver: (event: React.DragEvent) => {
      if (!event.dataTransfer.types.includes(EVIDENCE_DRAG_TYPE)) return
      event.preventDefault()
      event.stopPropagation()
      event.dataTransfer.dropEffect = valid ? "move" : "none"
      if (!valid) return
      setOver(moves!.dragging)
      if (expandOnHover && folderId && !timer.current)
        timer.current = setTimeout(
          () => useEvidenceStore.getState().expandFolder(folderId),
          600
        )
    },
    onDragLeave: (event: React.DragEvent) => {
      if (event.currentTarget.contains(event.relatedTarget as Node | null))
        return
      setOver(null)
      clearTimer()
    },
    onDrop: (event: React.DragEvent) => {
      if (!event.dataTransfer.types.includes(EVIDENCE_DRAG_TYPE)) return
      event.preventDefault()
      event.stopPropagation()
      setOver(null)
      clearTimer()
      if (valid && moves?.dragging) moves.move(moves.dragging, folderId)
      moves?.endDrag()
    },
  }
}
