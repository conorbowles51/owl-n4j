import { memo, useCallback, useRef } from "react"
import { observeElementRect, useVirtualizer, type Virtualizer } from "@tanstack/react-virtual"
import { fmt } from "@/features/phones/ui/count-sentence"
import type { ThreadRow } from "@/features/phones/schemas"

const ROW_HEIGHT = 65
const OVERSCAN = 8
/** A list not yet laid out draws this much, so a thread is never missing before the first measure. */
const UNMEASURED_HEIGHT = 900

/**
 * The thread list. A phone can hold about a thousand threads (942 on the largest reference phone) and the page redraws
 * for every reply it receives, so only the rows in view are in the page: drawing all of them was the largest share of
 * the browser's work between the list arriving and the first message (lx-convspeed). Every thread stays in the list,
 * in order and reachable by scrolling; the box above it finds by name, app or participant across all of them.
 */
export const ThreadList = memo(function ThreadList({ threads, total, open, multiPhone, byName, onPick }: {
  threads: ThreadRow[]
  /** How many threads the list holds before the find box, for its accessible name. */
  total: number
  open: string | null
  multiPhone: boolean
  byName: boolean
  onPick: (threadKey: string) => void
}) {
  const scroller = useRef<HTMLDivElement>(null)
  const virtualizer = useVirtualizer({
    count: threads.length,
    getScrollElement: () => scroller.current,
    getItemKey: (i) => threads[i].thread_key,
    estimateSize: () => ROW_HEIGHT,
    overscan: OVERSCAN,
    measureElement: (el) => el.getBoundingClientRect().height || ROW_HEIGHT,
    observeElementRect: useCallback(
      (v: Virtualizer<HTMLDivElement, Element>, cb: (r: { width: number; height: number }) => void) =>
        observeElementRect(v, (r) => cb(r.height ? r : { ...r, height: UNMEASURED_HEIGHT })),
      [],
    ),
  })
  return (
    <div ref={scroller} className="min-h-0 flex-1 overflow-auto" data-testid="thread-scroll">
      <ul role="listbox" aria-label={`Threads (${fmt(total)})`} className="relative" style={{ height: virtualizer.getTotalSize() }}>
        {virtualizer.getVirtualItems().map((v) => {
          const t = threads[v.index]
          const newPhone = multiPhone && byName && (v.index === 0 || threads[v.index - 1].phone.extraction_id !== t.phone.extraction_id)
          return (
            <li key={v.key} ref={virtualizer.measureElement} data-index={v.index} role="presentation" className="absolute left-0 top-0 w-full" style={{ transform: `translateY(${v.start}px)` }}>
              {newPhone && <p className="px-2 pt-2 text-xs font-semibold">{t.phone.label}</p>}
              <div
                role="option"
                tabIndex={0}
                aria-selected={t.thread_key === open}
                aria-setsize={threads.length}
                aria-posinset={v.index + 1}
                onClick={() => onPick(t.thread_key)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") onPick(t.thread_key)
                }}
                className="cursor-pointer border-b px-2 py-1.5 text-sm hover:bg-muted aria-selected:bg-accent"
              >
                <span className="block truncate font-medium">{t.title}</span>
                <span className="block text-xs text-muted-foreground">
                  {multiPhone ? `${t.phone.label} · ` : ""}
                  {t.app ?? "app not recorded"} · {fmt(t.event_count)} {t.event_count === 1 ? "message" : "messages"}
                  {t.deleted_count ? ` · ${fmt(t.deleted_count)} deleted` : ""}
                  {t.has_unreadable ? " · has unreadable content" : ""}
                </span>
                <span className="block text-xs">{t.review ? t.review.words : "Not yet reviewed"}</span>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
})
