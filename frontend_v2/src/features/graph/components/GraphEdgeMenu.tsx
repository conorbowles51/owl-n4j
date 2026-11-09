import { useEffect, useRef } from "react"
import { SignificantRelationshipButton } from "@/features/significant/components/SignificantRelationshipButton"

export interface EdgeMenuState {
  x: number
  y: number
  sourceKey: string
  sourceLabel: string
  type: string
  targetKey: string
  targetLabel: string
}

interface GraphEdgeMenuProps {
  caseId: string
  menu: EdgeMenuState
  onClose: () => void
}

/** The menu on a right-clicked relationship (GR-01): what it joins, and marking it significant. */
export function GraphEdgeMenu({ caseId, menu, onClose }: GraphEdgeMenuProps) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const outside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    const escape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("mousedown", outside)
    document.addEventListener("keydown", escape)
    return () => {
      document.removeEventListener("mousedown", outside)
      document.removeEventListener("keydown", escape)
    }
  }, [onClose])

  const words = menu.type.replace(/_/g, " ").toLowerCase()
  return (
    <div
      ref={ref}
      role="menu"
      aria-label="Relationship"
      data-testid="graph-edge-menu"
      className="fixed z-50 min-w-56 max-w-80 rounded-md border border-border bg-popover p-2 text-popover-foreground shadow-md"
      style={{ left: menu.x, top: menu.y }}
      onContextMenu={(e) => e.preventDefault()}
    >
      <p className="mb-1 px-1 text-xs text-muted-foreground">Relationship</p>
      <p className="mb-2 px-1 text-xs">
        <span className="font-medium">{menu.sourceLabel}</span> {words}{" "}
        <span className="font-medium">{menu.targetLabel}</span>
      </p>
      <SignificantRelationshipButton
        caseId={caseId}
        surface="graph_edge_menu"
        relationship={{ source_key: menu.sourceKey, type: menu.type, target_key: menu.targetKey }}
        description={`${menu.sourceLabel} ${words} ${menu.targetLabel}`}
        className="w-full justify-start"
        onChanged={onClose}
      />
    </div>
  )
}
