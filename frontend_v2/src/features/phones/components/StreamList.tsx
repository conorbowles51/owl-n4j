import { useVirtualizer } from "@tanstack/react-virtual"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { copyInGesture, readyToCopySentence, type CopyPayload } from "@/lib/copy-text"
import { cn } from "@/lib/cn"
import { failureText, StaleSnapshotError } from "../api"
import type { UseStream } from "../hooks/use-stream"
import { WINDOW_FAILED } from "../hooks/use-stream"
import { rowsHtml, rowsText } from "../lib/copy-rows"
import { LONG_BODY, plural, STALE_COPY, totalWords } from "../lib/stream-words"
import type { StreamRow } from "../schemas"
import { Arrow, ParticipantLabel } from "./ParticipantLabel"
import { rowBadges } from "../lib/badges"
import { StateBadges } from "./StateBadges"
import { TimeCell } from "./TimeCell"

/**
 * The one virtual list for phone rows (03 sections 3.1, 3.7, 3.9, 5.1), used by Conversations, the Timeline lens
 * and Search results. Sized to the exact total from the first paint; day headers name the day and the zone with
 * its offset; undated rows form the "No time recorded" group; a failed window shows a Retry row in place. There is
 * no "Load more" control.
 *
 * Selection: click a row's box or press Space; Shift+Click and Shift+J/K extend; Ctrl/Cmd+A selects the whole
 * result (the total, not the rendered rows). Copy (Ctrl/Cmd+C or the toolbar) writes text and HTML through the
 * copy helper that works on plain http; a selection whose rows are not all loaded is prepared first and copied by
 * a second click. j/k move the focus (tracked by event, not position), r opens the record behind the row.
 */

const HEADER = 44
const ROW = 76

export interface StreamListProps {
  stream: UseStream
  caseId: string
  caseName: string
  filterWords: string
  zoneName: string
  zone: string
  zoneBasis?: string
  noun?: { one: string; many: string }
  onOpenRecord?: (row: StreamRow) => void
  onFocusRow?: (row: StreamRow | null) => void
  className?: string
}

export function StreamList({
  stream,
  caseId,
  caseName,
  filterWords,
  zoneName,
  zone,
  zoneBasis,
  noun = { one: "message", many: "messages" },
  onOpenRecord,
  onFocusRow,
  className,
}: StreamListProps) {
  const parentRef = useRef<HTMLDivElement>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [allSelected, setAllSelected] = useState(false)
  const [anchor, setAnchor] = useState<number | null>(null)
  const [focusIndex, setFocusIndex] = useState<number | null>(null)
  const [copyState, setCopyState] = useState<{ kind: "idle" } | { kind: "preparing"; done: number; total: number } | { kind: "ready"; payload: CopyPayload; n: number } | { kind: "copied"; n: number } | { kind: "failed" } | { kind: "load_failed"; message: string }>({ kind: "idle" })
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const virtualizer = useVirtualizer({
    count: stream.count,
    getScrollElement: () => parentRef.current,
    estimateSize: (i) => (stream.item(i).type === "header" ? HEADER : ROW),
    overscan: 8,
  })
  const virtualItems = virtualizer.getVirtualItems()
  const first = virtualItems[0]?.index ?? 0
  const last = virtualItems[virtualItems.length - 1]?.index ?? 0

  useEffect(() => {
    if (stream.count) stream.ensure(first, last)
  }, [first, last, stream])

  // Focus is tracked by event, so it stays on the same message when windows load or the list refreshes.
  const focusedRow = useMemo(() => {
    if (focusIndex === null) return null
    const it = stream.item(focusIndex)
    return it.type === "row" ? it.row : null
  }, [focusIndex, stream])
  useEffect(() => {
    stream.setFocused(focusedRow?.event_uid ?? null)
    onFocusRow?.(focusedRow)
  }, [focusedRow, stream, onFocusRow])

  const loadedSelection = useCallback((): StreamRow[] | null => {
    const out: StreamRow[] = []
    for (let i = 0; i < stream.count; i++) {
      const it = stream.item(i)
      if (it.type !== "row") continue
      if (!it.row) {
        if (allSelected) return null
        continue
      }
      if (allSelected || selected.has(it.row.event_uid)) out.push(it.row)
    }
    return out
  }, [stream, selected, allSelected])

  const selectionCount = allSelected ? stream.total : selected.size

  const copy = useCallback(() => {
    const rows = loadedSelection()
    if (rows && rows.length) {
      const payload = { text: rowsText(rows, caseName, filterWords, zoneName), html: rowsHtml(rows, caseName, filterWords, zoneName) }
      if (copyInGesture(payload)) setCopyState({ kind: "copied", n: rows.length })
      else setCopyState({ kind: "ready", payload, n: rows.length })
      return
    }
    if (!allSelected) return
    // Rows outside the loaded windows: fetch them first, then a second click copies (03 3.7; never refused).
    setCopyState({ kind: "preparing", done: 0, total: stream.total })
    void stream
      .allRows((done, total) => setCopyState({ kind: "preparing", done, total }))
      .then((all) => {
        const payload = { text: rowsText(all, caseName, filterWords, zoneName), html: rowsHtml(all, caseName, filterWords, zoneName) }
        setCopyState({ kind: "ready", payload, n: all.length })
      })
      .catch((e) =>
        setCopyState({
          kind: "load_failed",
          message: e instanceof StaleSnapshotError ? STALE_COPY : failureText(e, "The rows to copy could not be loaded. Nothing was copied."),
        }),
      )
  }, [loadedSelection, allSelected, stream, caseName, filterWords, zoneName])

  const toggle = (row: StreamRow, index: number, shift: boolean) => {
    setAllSelected(false)
    setSelected((prev) => {
      const next = new Set(prev)
      if (shift && anchor !== null) {
        const [a, b] = anchor < index ? [anchor, index] : [index, anchor]
        for (let i = a; i <= b; i++) {
          const it = stream.item(i)
          if (it.type === "row" && it.row) next.add(it.row.event_uid)
        }
      } else if (next.has(row.event_uid)) next.delete(row.event_uid)
      else next.add(row.event_uid)
      return next
    })
    setAnchor(index)
  }

  const moveFocus = (delta: number, extend: boolean) => {
    let i = focusIndex ?? (delta > 0 ? -1 : stream.count)
    for (;;) {
      i += delta
      if (i < 0 || i >= stream.count) return
      if (stream.item(i).type === "row") break
    }
    setFocusIndex(i)
    virtualizer.scrollToIndex(i, { align: "auto" })
    if (extend) {
      const it = stream.item(i)
      if (it.type === "row" && it.row) {
        const r = it.row
        setSelected((prev) => new Set(prev).add(r.event_uid))
      }
    }
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    const target = e.target as HTMLElement
    if (target.closest("input:not([type=checkbox]), textarea, select, [contenteditable=true]")) return
    const mod = e.ctrlKey || e.metaKey
    if (mod && e.key.toLowerCase() === "a") {
      e.preventDefault()
      setAllSelected(true)
      return
    }
    if (mod && e.key.toLowerCase() === "c") {
      if (selectionCount > 0) {
        e.preventDefault()
        copy()
      }
      return
    }
    if (e.key === "j" || e.key === "J" || e.key === "ArrowDown") {
      e.preventDefault()
      moveFocus(1, e.shiftKey)
    } else if (e.key === "k" || e.key === "K" || e.key === "ArrowUp") {
      e.preventDefault()
      moveFocus(-1, e.shiftKey)
    } else if (e.key === "Home") {
      e.preventDefault()
      setFocusIndex(null)
      virtualizer.scrollToIndex(0)
      moveFocus(1, false)
    } else if (e.key === "End") {
      e.preventDefault()
      virtualizer.scrollToIndex(stream.count - 1, { align: "end" })
      setFocusIndex(stream.count)
      moveFocus(-1, false)
    } else if (e.key === " " && focusIndex !== null) {
      e.preventDefault()
      const it = stream.item(focusIndex)
      if (it.type === "row" && it.row) toggle(it.row, focusIndex, false)
    } else if ((e.key === "r" || e.key === "Enter") && focusedRow) {
      e.preventDefault()
      onOpenRecord?.(focusedRow)
    } else if (e.key === "Escape") {
      setSelected(new Set())
      setAllSelected(false)
    } else if (e.altKey && (e.key === "j" || e.key === "k" || e.code === "KeyJ" || e.code === "KeyK")) {
      e.preventDefault()
      jumpDay(e.code === "KeyJ" || e.key === "j" ? 1 : -1)
    }
  }

  const jumpDay = (dir: 1 | -1) => {
    const pos = focusIndex ?? first
    const segs = stream.segments
    if (!segs.length) return
    let si = segs.findIndex((s, k) => pos >= s.start && (k === segs.length - 1 || pos < segs[k + 1].start))
    si = Math.max(0, Math.min(segs.length - 1, si + dir))
    virtualizer.scrollToIndex(segs[si].start, { align: "start" })
    setFocusIndex(segs[si].start + 1)
  }

  if (stream.status === "error") {
    return (
      <div role="alert" className="m-4 rounded border border-destructive/40 p-3 text-sm">
        <p>{stream.error}</p>
        <Button size="sm" variant="outline" className="mt-2" onClick={stream.reload}>
          Try again
        </Button>
      </div>
    )
  }

  return (
    <div className={cn("flex min-h-0 flex-1 flex-col", className)} onKeyDown={onKeyDown}>
      <div className="flex flex-wrap items-center gap-3 border-b px-3 py-2 text-sm" data-testid="stream-toolbar">
        <span data-testid="stream-total" className="font-medium">
          {stream.index ? totalWords(stream, noun) : ""}
        </span>
        {stream.index?.zone.note && <span className="text-muted-foreground">{stream.index.zone.note}</span>}
        {selectionCount > 0 && (
          <>
            <span>{plural(selectionCount, noun)} selected</span>
            <Button size="sm" variant="outline" onClick={copy}>
              Copy {selectionCount.toLocaleString("en-US")}
            </Button>
          </>
        )}
        {copyState.kind === "preparing" && (
          <span role="status">
            Preparing {copyState.total.toLocaleString("en-US")} {noun.many} to copy ({copyState.done.toLocaleString("en-US")} ready)
          </span>
        )}
        {copyState.kind === "ready" && (
          <>
            <span role="status">{readyToCopySentence(copyState.n, noun.many)}</span>
            <Button
              size="sm"
              onClick={() => setCopyState(copyInGesture(copyState.payload) ? { kind: "copied", n: copyState.n } : { kind: "failed" })}
            >
              Copy now
            </Button>
          </>
        )}
        {copyState.kind === "copied" && <span role="status">Copied {plural(copyState.n, noun)}.</span>}
        {copyState.kind === "failed" && <span role="status">The browser did not allow copying. Select the text and press Ctrl+C.</span>}
        {copyState.kind === "load_failed" && <span role="alert">{copyState.message}</span>}
        {stream.notice && (
          <span role="status" className="text-muted-foreground">
            {stream.notice}
          </span>
        )}
      </div>
      {stream.index && !stream.index.complete && (
        <div className="border-b bg-status-review-soft px-3 py-1 text-xs">
          {stream.index.limits.map((l) => (
            <p key={l.message}>{l.message}</p>
          ))}
        </div>
      )}
      <div ref={parentRef} className="min-h-0 flex-1 overflow-auto" data-testid="stream-scroll" tabIndex={0} aria-label="Messages">
        <div style={{ height: virtualizer.getTotalSize(), position: "relative" }} data-testid="stream-sizer">
          {virtualItems.map((v) => {
            const it = stream.item(v.index)
            const style = { position: "absolute" as const, top: 0, left: 0, width: "100%", transform: `translateY(${v.start}px)` }
            if (it.type === "header") {
              const s = stream.segments[it.segment]
              return (
                <div key={`h${it.segment}`} ref={virtualizer.measureElement} data-index={v.index} style={style} className="flex items-center gap-2 border-b bg-muted/60 px-3 py-2 text-sm" data-day={s.day ?? "none"}>
                  <span className="font-semibold">{s.header}</span>
                  {s.zoneLabel && <span className="text-muted-foreground">{s.zoneLabel}</span>}
                  <span className="text-muted-foreground">({plural(s.count, noun)})</span>
                  <span className="ml-auto flex gap-1">
                    <Button size="sm" variant="ghost" onClick={() => jumpDay(-1)} aria-label="Previous day">
                      Previous day
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => jumpDay(1)} aria-label="Next day">
                      Next day
                    </Button>
                  </span>
                </div>
              )
            }
            if (it.state === "failed") {
              return (
                <div key={`f${it.windowKey}:${it.offset}`} ref={virtualizer.measureElement} data-index={v.index} style={style} className="border-b px-3 py-3 text-sm" data-window-failed>
                  {WINDOW_FAILED.replace(" Retry.", "")}{" "}
                  <Button size="sm" variant="outline" onClick={() => stream.retry(it.windowKey)}>
                    Retry
                  </Button>
                </div>
              )
            }
            if (!it.row) {
              return <div key={`p${it.segment}:${it.offset}`} data-index={v.index} style={{ ...style, height: ROW }} className="border-b px-3 py-2" aria-hidden data-placeholder />
            }
            const row = it.row
            const isSel = allSelected || selected.has(row.event_uid)
            const long = (row.body?.length ?? 0) > LONG_BODY && !expanded.has(row.event_uid)
            return (
              <div
                key={row.event_uid}
                ref={virtualizer.measureElement}
                data-index={v.index}
                data-event={row.event_uid}
                style={style}
                className={cn("flex gap-3 border-b px-3 py-2 text-sm select-text", focusIndex === v.index && "outline outline-2 outline-ring", isSel && "bg-accent/40")}
                onClick={() => setFocusIndex(v.index)}
              >
                <input
                  type="checkbox"
                  aria-label="Select this message"
                  checked={isSel}
                  onChange={() => undefined}
                  onClick={(e) => {
                    e.stopPropagation()
                    toggle(row, v.index, e.shiftKey)
                  }}
                />
                <TimeCell caseId={caseId} recordUid={row.record_uid} time={row.time} zone={zone} zoneBasis={zoneBasis} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <span>
                      {row.phone.label} · {row.app ?? "app not recorded"}
                    </span>
                    <StateBadges badges={rowBadges(row)} />
                  </div>
                  <div className="text-sm">
                    <ParticipantLabel label={row.from} />
                    <Arrow />
                    {row.to.length ? (
                      row.to.map((t, k) => (
                        <span key={`${t.identity_key}-${k}`}>
                          {k > 0 && ", "}
                          <ParticipantLabel label={t} />
                        </span>
                      ))
                    ) : (
                      <span className="text-muted-foreground">(recipient not recorded)</span>
                    )}
                  </div>
                  {row.kind === "call" && <p>{row.call?.words}</p>}
                  {row.subject && <p className="font-semibold">{row.subject}</p>}
                  {row.body && (
                    <p className="whitespace-pre-wrap break-words">
                      {long ? row.body.slice(0, LONG_BODY) : row.body}
                      {long && (
                        <Button size="sm" variant="link" onClick={() => setExpanded((p) => new Set(p).add(row.event_uid))}>
                          Show all {row.body.length.toLocaleString("en-US")} characters
                        </Button>
                      )}
                    </p>
                  )}
                  {row.attachments.length > 0 && (
                    <p className="text-xs text-muted-foreground">
                      {row.attachments.map((a, k) => (
                        <span key={k}>[attachment: {a.filename ?? "file name not recorded"}{a.category ? `, ${a.category}` : ""}] </span>
                      ))}
                    </p>
                  )}
                </div>
                {onOpenRecord && (
                  <Button size="sm" variant="ghost" onClick={() => onOpenRecord(row)} aria-label="Open the record behind this">
                    Record
                  </Button>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
