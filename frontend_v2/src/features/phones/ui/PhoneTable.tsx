import { useVirtualizer } from "@tanstack/react-virtual"
import { useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react"
import { cn } from "@/lib/cn"
import { usePhoneSelection } from "@/stores/phone-selection.store"
import { ResultCount } from "./ResultCount"

/**
 * The one table for lists to compare (07 4.4): calls, contacts, locations, accounts, apps, approach results and
 * the list for each record type. Exact total (no paging, no Load more), sortable columns, keyboard-resizable
 * columns, virtual rows that still state their position and the list size, and the phone selection store as the
 * one selection model (click, Shift+click, Space, j/k and arrows).
 */
export interface Column<Row> {
  id: string
  header: string
  width: number
  cell: (row: Row) => ReactNode
  /** Sort value; omit for an unsortable column. */
  sortValue?: (row: Row) => string | number | null
}

export const ROW_PX = 36
const MIN_COL = 60

export function PhoneTable<Row>({
  rows,
  total,
  columns,
  rowId,
  noun,
  label,
  height = 360,
  onOpen,
  unconfirmed,
}: {
  rows: Row[]
  /** The exact total for the scope; equals rows.length unless the server still sends rows (then "(so far)"). */
  total: number
  columns: Column<Row>[]
  rowId: (row: Row) => string
  noun: string
  label: string
  height?: number
  onOpen?: (row: Row) => void
  unconfirmed?: number
}) {
  const [sort, setSort] = useState<{ id: string; dir: "ascending" | "descending" } | null>(null)
  const [widths, setWidths] = useState(() => Object.fromEntries(columns.map((c) => [c.id, c.width])))
  const selection = usePhoneSelection()
  const parent = useRef<HTMLDivElement>(null)

  const sorted = useMemo(() => {
    if (!sort) return rows
    const col = columns.find((c) => c.id === sort.id)
    if (!col?.sortValue) return rows
    const factor = sort.dir === "ascending" ? 1 : -1
    return [...rows].sort((a, b) => {
      const x = col.sortValue!(a)
      const y = col.sortValue!(b)
      if (x === y) return 0
      if (x === null) return 1
      if (y === null) return -1
      return (x < y ? -1 : 1) * factor
    })
  }, [rows, sort, columns])
  const order = useMemo(() => sorted.map(rowId), [sorted, rowId])

  const virtual = useVirtualizer({ count: sorted.length, getScrollElement: () => parent.current, estimateSize: () => ROW_PX, overscan: 8, scrollMargin: ROW_PX })
  const focusIndex = Math.max(0, selection.focus ? order.indexOf(selection.focus) : 0)

  const move = (to: number, extend: boolean) => {
    const i = Math.min(sorted.length - 1, Math.max(0, to))
    const id = order[i]
    if (!id) return
    if (extend) selection.extendTo(id, order)
    else selection.focusOn(id)
    virtual.scrollToIndex(i, { align: "auto" })
  }

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const k = e.key
    if (k === "j" || k === "ArrowDown") move(focusIndex + 1, false)
    else if (k === "k" || k === "ArrowUp") move(focusIndex - 1, false)
    else if (k === "J" || (e.shiftKey && k === "ArrowDown")) move(focusIndex + 1, true)
    else if (k === "K" || (e.shiftKey && k === "ArrowUp")) move(focusIndex - 1, true)
    else if (k === " ") {
      const id = order[focusIndex]
      if (id) selection.toggle(id)
    } else if (k === "Enter") {
      const row = sorted[focusIndex]
      if (row) onOpen?.(row)
    } else if (k === "Home") move(0, false)
    else if (k === "End") move(sorted.length - 1, false)
    else return
    e.preventDefault()
  }

  const template = columns.map((c) => `${widths[c.id]}px`).join(" ")
  return (
    <div className="flex flex-col gap-1 text-foreground" data-testid="phone-table">
      <ResultCount shown={rows.length} total={total} noun={noun} soFar={rows.length < total} unconfirmed={unconfirmed} />
      <div
        role="grid"
        aria-label={label}
        aria-rowcount={sorted.length + 1}
        aria-colcount={columns.length}
        aria-multiselectable
        tabIndex={0}
        onKeyDown={onKey}
        aria-activedescendant={order[focusIndex] ? `row-${order[focusIndex]}` : undefined}
        ref={parent}
        style={{ height, overflow: "auto" }}
        className="rounded border bg-card text-sm focus-visible:outline-2 focus-visible:outline-ring"
      >
        <div role="row" aria-rowindex={1} className="sticky top-0 z-10 grid border-b bg-muted font-medium" style={{ gridTemplateColumns: template, height: ROW_PX }}>
          {columns.map((c, ci) => {
            const state = sort?.id === c.id ? sort.dir : "none"
            return (
              <div key={c.id} role="columnheader" aria-colindex={ci + 1} aria-sort={c.sortValue ? state : undefined} className="relative flex items-center px-2 py-1.5">
                {c.sortValue ? (
                  <button
                    type="button"
                    className="text-left underline-offset-2 hover:underline"
                    onClick={() => setSort((s) => (s?.id === c.id ? { id: c.id, dir: s.dir === "ascending" ? "descending" : "ascending" } : { id: c.id, dir: "ascending" }))}
                  >
                    {c.header}
                    <span className="sr-only">{state === "none" ? ", not sorted" : `, sorted ${state}`}</span>
                    <span aria-hidden>{state === "ascending" ? " ▲" : state === "descending" ? " ▼" : ""}</span>
                  </button>
                ) : (
                  c.header
                )}
                <span
                  role="separator"
                  aria-orientation="vertical"
                  aria-label={`Resize ${c.header} column`}
                  aria-valuenow={widths[c.id]}
                  aria-valuemin={MIN_COL}
                  aria-valuemax={800}
                  tabIndex={0}
                  onKeyDown={(e) => {
                    const delta = e.key === "ArrowRight" ? 16 : e.key === "ArrowLeft" ? -16 : 0
                    if (!delta) return
                    e.preventDefault()
                    e.stopPropagation()
                    setWidths((w) => ({ ...w, [c.id]: Math.min(800, Math.max(MIN_COL, w[c.id] + delta)) }))
                  }}
                  className="absolute top-0 right-0 h-full w-1.5 cursor-col-resize focus-visible:bg-ring"
                />
              </div>
            )
          })}
        </div>
        <div role="rowgroup" style={{ height: virtual.getTotalSize(), position: "relative" }}>
            {virtual.getVirtualItems().map((item) => {
              const row = sorted[item.index]
              const id = order[item.index]
              const selected = selection.whole !== null || selection.ids.includes(id)
              const focused = item.index === focusIndex
              return (
                <div
                  key={id}
                  id={`row-${id}`}
                  role="row"
                  aria-rowindex={item.index + 2}
                  aria-selected={selected}
                  onClick={(e) => (e.shiftKey ? selection.extendTo(id, order) : (selection.focusOn(id), selection.toggle(id)))}
                  onDoubleClick={() => onOpen?.(row)}
                  className={cn("absolute left-0 grid w-full items-center border-b", selected && "bg-accent", focused && "outline-2 -outline-offset-2 outline-ring")}
                  style={{ top: item.start - ROW_PX, height: ROW_PX, gridTemplateColumns: template }}
                >
                  {columns.map((c, ci) => (
                    <div key={c.id} role="gridcell" aria-colindex={ci + 1} className="truncate px-2">
                      {c.cell(row)}
                    </div>
                  ))}
                </div>
              )
            })}
        </div>
      </div>
    </div>
  )
}
