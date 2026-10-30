import { useEffect, useRef, type ReactNode } from "react"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { entryPeriod, type QueueEntry } from "../lib/review-queue"
import type { Guidance } from "../lib/queue-guidance"
import { problemRowLocator } from "../lib/statement-row-locator"
import { statementReadingQuery } from "../lib/statement-reading"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"

/** True while the person is typing: J, K, arrows and Esc then belong to the field. */
function typing(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false
  return (
    target.isContentEditable ||
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement
  )
}

/** The page a queue item points at: its problem's page, else the page the item names. */
const previewPage = (entry: QueueEntry) => entry.issue_pages[0] ?? entry.page ?? 1

/**
 * A quick look at one queue item without leaving the list: the PDF page with
 * the problem highlighted as the statement review highlights it, beside the
 * item's own fixes (the same forms and saves as on the list). J or Down: next
 * item, K or Up: previous, Esc: close (none of them while typing in a field).
 */
export function QueuePreview({
  caseId,
  entry,
  guide,
  position,
  total,
  onNext,
  onPrevious,
  onClose,
  onOpen,
  children,
}: {
  caseId: string
  entry: QueueEntry
  guide: Guidance
  position: number
  total: number
  onNext: () => void
  onPrevious: () => void
  onClose: () => void
  onOpen: () => void
  /** The item's fixes, rendered by the list so they are the very same forms. */
  children: ReactNode
}) {
  const panel = useRef<HTMLElement>(null)
  // The problem row's highlight needs the statement's reading (the same request
  // the statement review makes, shared through its cache); a page needs nothing.
  const reading = useQuery({
    ...statementReadingQuery(caseId, entry.file_id, entry.currency || "", entry.statement_id || ""),
    enabled: !!entry.row_id,
  })
  const row = entry.row_id ? reading.data?.rows.find((candidate) => candidate.id === entry.row_id) : undefined
  const page = row?.page_number ?? previewPage(entry)
  const locator = row ? problemRowLocator(row) : { kind: "page_only", page }

  const keys = useRef({ onNext, onPrevious, onClose })
  useEffect(() => {
    keys.current = { onNext, onPrevious, onClose }
  })
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || typing(event.target)) return
      // A menu or dialog opened from the preview handles its own keys.
      if (event.target instanceof HTMLElement && event.target.closest('[role="menu"],[role="listbox"],[role="alertdialog"]'))
        return
      if (event.key === "j" || event.key === "J" || event.key === "ArrowDown") {
        event.preventDefault()
        keys.current.onNext()
      } else if (event.key === "k" || event.key === "K" || event.key === "ArrowUp") {
        event.preventDefault()
        keys.current.onPrevious()
      } else if (event.key === "Escape") {
        event.preventDefault()
        keys.current.onClose()
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])
  // Focus moves into the preview when it opens and when it moves to another item.
  useEffect(() => {
    panel.current?.focus({ preventScroll: true })
  }, [entry.id])

  return (
    <aside
      ref={panel}
      tabIndex={-1}
      role="dialog"
      aria-modal="false"
      aria-label={`Preview of ${entry.filename}`}
      className="fixed inset-y-0 right-0 z-40 flex w-full max-w-[min(1040px,100vw)] flex-col border-l bg-background shadow-2xl outline-none sm:w-[85vw]"
    >
      <header className="flex flex-wrap items-center gap-2 border-b px-4 py-2">
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold">{entry.filename}</p>
          <p className="text-xs text-muted-foreground">
            {entryPeriod(entry)} · page {page} · {position} of {total}
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={onPrevious} disabled={position <= 1} title="Previous item (K or Up)">
          Previous
        </Button>
        <Button size="sm" variant="outline" onClick={onNext} disabled={position >= total} title="Next item (J or Down)">
          Next
        </Button>
        <Button size="sm" variant="ghost" onClick={onClose} title="Close (Esc)">
          Close preview
        </Button>
      </header>
      <div className="grid min-h-0 flex-1 overflow-auto lg:grid-cols-[minmax(0,1fr)_340px]">
        <section aria-label={`Page ${page} of ${entry.filename}`} className="min-w-0 border-b p-3 lg:border-b-0 lg:border-r">
          {entry.row_id && reading.isPending ? (
            <p role="status" className="text-xs text-muted-foreground">Finding the problem on the page…</p>
          ) : (
            <>
              {entry.row_id && !row && (
                <p role="status" className="mb-2 text-xs text-muted-foreground">
                  The problem row is not in the current reading; showing page {page}.
                </p>
              )}
              <TransactionSourceHighlight
                key={`${entry.id}:${page}`}
                sourceDocumentId={entry.file_id}
                locatorPayload={locator}
                wholePage={!row}
              />
            </>
          )}
        </section>
        <section aria-label="What it needs" className="min-w-0 space-y-2 p-3 text-sm">
          <p className="text-base font-semibold">{guide.title}</p>
          <ol className="list-decimal space-y-0.5 pl-5 text-xs">
            {guide.steps.map((text, index) => (
              <li key={index}>{text}</li>
            ))}
          </ol>
          {children}
          <Button size="sm" variant="outline" onClick={onOpen}>
            {guide.action}
          </Button>
          <p className="text-xs text-muted-foreground">J or ↓ next · K or ↑ previous · Esc closes</p>
        </section>
      </div>
    </aside>
  )
}
