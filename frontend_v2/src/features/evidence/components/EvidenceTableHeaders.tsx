import { useRef } from "react"
import { ArrowDown, ArrowUp, ArrowUpDown, GripVertical } from "lucide-react"
import { TableHead } from "@/components/ui/table"
import { useEvidenceStore } from "../evidence.store"

export function EvidenceSortHeader({
  column,
  children,
}: {
  column: "name" | "date"
  children: React.ReactNode
}) {
  const { sortBy, sortDirection, toggleSort, nameWidth, setNameWidth } =
    useEvidenceStore()
  const header = useRef<HTMLTableCellElement>(null)
  const drag = useRef<{ x: number; width: number } | null>(null)
  const active = sortBy === column
  const Icon = active
    ? sortDirection === "asc"
      ? ArrowUp
      : ArrowDown
    : ArrowUpDown
  return (
    <TableHead
      ref={header}
      className="relative"
      aria-sort={
        active ? (sortDirection === "asc" ? "ascending" : "descending") : "none"
      }
    >
      <button
        className="flex h-full w-full items-center gap-1 pr-3 text-xs hover:text-foreground"
        onClick={() => toggleSort(column)}
      >
        {children}
        <Icon aria-hidden="true" className="size-3 shrink-0" />
      </button>
      {column === "name" && (
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize Name column"
          tabIndex={0}
          aria-valuemin={180}
          aria-valuemax={1600}
          aria-valuenow={nameWidth ?? undefined}
          aria-valuetext={
            nameWidth === null
              ? "Automatic width"
              : `${Math.round(nameWidth)} pixels`
          }
          title="Drag or use Left/Right to resize. Double-click or Enter for automatic width."
          className="absolute inset-y-0 -right-1 z-10 flex w-3 cursor-col-resize touch-none items-center justify-center border-r border-border text-muted-foreground hover:bg-primary/15 focus-visible:bg-primary/15 focus-visible:outline-2 focus-visible:outline-ring"
          onPointerDown={(event) => {
            if (event.button !== 0) return
            event.preventDefault()
            event.stopPropagation()
            event.currentTarget.focus()
            drag.current = {
              x: event.clientX,
              width: header.current?.getBoundingClientRect().width ?? 300,
            }
            event.currentTarget.setPointerCapture(event.pointerId)
          }}
          onPointerMove={(event) => {
            if (drag.current)
              setNameWidth(drag.current.width + event.clientX - drag.current.x)
          }}
          onPointerUp={(event) => {
            drag.current = null
            if (event.currentTarget.hasPointerCapture(event.pointerId))
              event.currentTarget.releasePointerCapture(event.pointerId)
          }}
          onLostPointerCapture={() => {
            drag.current = null
          }}
          onPointerCancel={() => {
            drag.current = null
          }}
          onClick={(event) => event.stopPropagation()}
          onDoubleClick={() => setNameWidth(null)}
          onKeyDown={(event) => {
            if (!["ArrowLeft", "ArrowRight", "Enter"].includes(event.key))
              return
            event.preventDefault()
            event.stopPropagation()
            if (event.key === "Enter") setNameWidth(null)
            else
              setNameWidth(
                (nameWidth ??
                  header.current?.getBoundingClientRect().width ??
                  300) + (event.key === "ArrowLeft" ? -20 : 20)
              )
          }}
        >
          <GripVertical className="size-3" aria-hidden="true" />
        </div>
      )}
    </TableHead>
  )
}
