import { useEffect, useMemo, useRef, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { BatchStatementReview } from "./FinancialBatchPanel"
import {
  entryPeriod,
  importOutcome,
  useReviewQueue,
  type QueueEntry,
  type ReviewQueue,
} from "../lib/review-queue"
import { ReadingProgress } from "./ReadingProgress"

type ListName = "waiting" | "copies" | "unreadable"
const QUEUE_KEYS = ["queueItem", "queueList", "queueFiles"]

function listOf(data: ReviewQueue | undefined, name: ListName): QueueEntry[] {
  if (!data) return []
  return name === "copies"
    ? data.copies
    : name === "unreadable"
      ? data.unreadable
      : data.items
}

/** The plain per-case status line; every number is a count of the queue's own lists. */
export function ReviewStatusLine({
  data,
  onOpen,
}: {
  data: Pick<ReviewQueue, "counts">
  onOpen?: (list: ListName) => void
}) {
  const c = data.counts
  const part = (label: string, value: number, list?: ListName) =>
    list && onOpen && value ? (
      <button
        type="button"
        className="underline underline-offset-2"
        onClick={() => onOpen(list)}
      >
        {label} {value}
      </button>
    ) : (
      <span>
        {label} {value}
      </span>
    )
  const parts = [
    part("Imported", c.imported),
    part("Waiting for you", c.waiting, "waiting"),
    ...(c.ready ? [part("Ready to save", c.ready)] : []),
    part("Copies set aside", c.copies, "copies"),
    part("Couldn't read", c.unreadable + c.unreadable_files, "unreadable"),
    ...(c.saving ? [part("Saving", c.saving)] : []),
    ...(c.rechecking ? [part("Being rechecked", c.rechecking)] : []),
    ...(c.left_unimported ? [part("Left unimported", c.left_unimported)] : []),
  ]
  return (
    <p className="text-sm" aria-label="Statement status">
      {parts.map((value, index) => (
        <span key={index}>
          {index > 0 && " · "}
          {value}
        </span>
      ))}
    </p>
  )
}

function EntryLine({ entry }: { entry: QueueEntry }) {
  return (
    <>
      <p className="font-medium">
        {entry.filename}
        {entry.file_statements > 1 &&
          ` · statement ${entry.file_position} of ${entry.file_statements} in this file`}
      </p>
      <p className="text-xs text-muted-foreground">
        {[
          entry.holder,
          entry.account,
          entry.institution,
          entryPeriod(entry),
          entry.page ? `page ${entry.page}` : "",
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>
    </>
  )
}

export function ReviewQueuePanel({
  caseId,
  onOpenBatch,
}: {
  caseId: string
  onOpenBatch: (batchId: string, check?: string) => void
}) {
  const [params, setParams] = useSearchParams()
  const fileIds = useMemo(
    () => (params.get("queueFiles") || "").split(",").filter(Boolean),
    [params]
  )
  const itemId = params.get("queueItem")
  const list = (params.get("queueList") as ListName | null) || "waiting"
  const query = useReviewQueue(caseId, fileIds)
  const client = useQueryClient()
  const [outcome, setOutcome] = useState<{
    entry: QueueEntry
    message: string
    held: boolean
  } | null>(null)
  // The order the investigator is working through. Next is computed from it
  // on the client, so moving on never waits for the queue to reload.
  const [order, setOrder] = useState<QueueEntry[]>([])
  const current = listOf(query.data, list)
  const orderKey = `${list}:${fileIds.join(",")}`
  const appliedOrder = useRef("")
  useEffect(() => {
    if (!query.data || query.isPlaceholderData) return
    if (!itemId || appliedOrder.current !== orderKey) {
      appliedOrder.current = orderKey
      setOrder(listOf(query.data, list))
    }
  }, [query.data, query.isPlaceholderData, itemId, orderKey, list])
  const open = (entry: QueueEntry | undefined, name: ListName = list) => {
    setParams((previous) => {
      const next = new URLSearchParams(previous)
      next.set("view", "statements")
      next.set("queue", "1")
      if (entry) next.set("queueItem", entry.id)
      else next.delete("queueItem")
      next.set("queueList", name)
      return next
    })
  }
  const back = () => {
    void client.invalidateQueries({ queryKey: ["financial-review-queue", caseId] })
    open(undefined)
  }
  const showList = (name: ListName) => {
    setOrder(listOf(query.data, name))
    appliedOrder.current = `${name}:${fileIds.join(",")}`
    open(undefined, name)
  }
  const clearFilter = () =>
    setParams((previous) => {
      const next = new URLSearchParams(previous)
      for (const key of QUEUE_KEYS) next.delete(key)
      return next
    })
  const entries = order.length || !query.data ? order : current
  const index = entries.findIndex((entry) => entry.id === itemId)
  const active = index >= 0 ? entries[index] : current.find((e) => e.id === itemId)
  const step = (direction: 1 | -1) => {
    // Skip statements the latest queue no longer lists (fixed meanwhile).
    const latest = new Set(current.map((entry) => entry.id))
    let position = index + direction
    while (
      position >= 0 &&
      position < entries.length &&
      query.data &&
      !query.isPlaceholderData &&
      !latest.has(entries[position].id)
    )
      position += direction
    if (position < 0 || position >= entries.length) return back()
    open(entries[position])
  }

  if (itemId && active?.batch_id)
    return (
      <div className="space-y-3">
        {outcome && (
          <OutcomeNote outcome={outcome} onDismiss={() => setOutcome(null)} />
        )}
        <BatchStatementReview
          key={active.id}
          caseId={caseId}
          batchId={active.batch_id}
          itemId={active.id}
          rowId={active.row_id ?? (active.page ? `page:${active.page}` : undefined)}
          onBack={back}
          queue={{
            issue: active.issue,
            field: active.field ?? undefined,
            position: Math.max(index, 0) + 1,
            total: entries.length || 1,
            onNext: () => step(1),
            onPrevious: () => step(-1),
            onImported: (receipt) => {
              setOutcome({ entry: active, ...importOutcome(receipt) })
              void client.invalidateQueries({
                queryKey: ["financial-review-queue", caseId],
              })
              step(1)
            },
          }}
        />
      </div>
    )

  return (
    <section aria-label="Review queue" className="space-y-4">
      <header className="space-y-1">
        <h3 className="text-lg font-semibold">
          {list === "copies"
            ? "Review copies"
            : list === "unreadable"
              ? "Couldn't read"
              : "Waiting for you"}
        </h3>
        <p className="text-sm text-muted-foreground">
          {list === "copies"
            ? "Statements that are copies of another statement in this case. Copies the system set aside count nothing; possible copies wait for you to compare them with the original."
            : list === "unreadable"
              ? "Statements or files where nothing usable could be read. Open one to see its pages."
              : "Only statements that need a decision from you. Each says what to fix before you open it. Imported statements, copies and statements that check out are not listed here."}
        </p>
      </header>
      {fileIds.length > 0 && (
        <div role="status" className="flex flex-wrap items-center gap-2 rounded border p-2 text-sm">
          <span>
            Showing the {fileIds.length} selected{" "}
            {fileIds.length === 1 ? "file" : "files"}, from their saved readings. Nothing is read again.
          </span>
          <Button size="sm" variant="outline" onClick={clearFilter}>
            Show the whole case
          </Button>
        </div>
      )}
      {outcome && (
        <OutcomeNote outcome={outcome} onDismiss={() => setOutcome(null)} />
      )}
      {query.isError ? (
        <div role="alert" className="space-y-2">
          <p>{query.error.message}</p>
          <Button variant="outline" onClick={() => void query.refetch()}>
            Try again
          </Button>
        </div>
      ) : !query.data ? (
        <p role="status">Loading the review queue…</p>
      ) : (
        <>
          <ReviewStatusLine data={query.data} onOpen={showList} />
          <ReadingProgress caseId={caseId} reading={query.data.reading} />
          {list !== "waiting" && (
            <Button variant="outline" size="sm" onClick={() => showList("waiting")}>
              Back to waiting for you ({query.data.counts.waiting})
            </Button>
          )}
          {list === "waiting" && query.data.ready_batches.length > 0 && (
            <div className="rounded border p-3 text-sm space-y-2" aria-label="Ready to save">
              <p>
                {query.data.counts.ready}{" "}
                {query.data.counts.ready === 1
                  ? "statement checks out"
                  : "statements check out"}{" "}
                and can be saved. Nothing needs fixing in{" "}
                {query.data.counts.ready === 1 ? "it" : "them"}.
              </p>
              <div className="flex flex-wrap gap-2">
                {query.data.ready_batches.map((batch) => (
                  <Button
                    key={batch.batch_id}
                    size="sm"
                    variant="outline"
                    onClick={() => onOpenBatch(batch.batch_id, "ready_to_save")}
                  >
                    Save {batch.statements} ready{" "}
                    {batch.statements === 1 ? "statement" : "statements"}
                  </Button>
                ))}
              </div>
            </div>
          )}
          {list === "waiting" && query.data.copies.length > 0 && (
            <Button variant="outline" size="sm" onClick={() => showList("copies")}>
              Review copies ({query.data.copies.length})
            </Button>
          )}
          {current.length === 0 ? (
            <p role="status" className="rounded border p-3">
              {list === "waiting"
                ? "Nothing is waiting for you."
                : list === "copies"
                  ? "No copies."
                  : "Every statement could be read."}
            </p>
          ) : (
            <ol className="divide-y rounded border" aria-label="Statements to review">
              {current.map((entry, position) => (
                <li
                  key={entry.id}
                  className="flex flex-wrap items-center justify-between gap-3 p-3 text-sm"
                >
                  <div className="min-w-0 flex-1 basis-72">
                    <EntryLine entry={entry} />
                    {entry.issue && (
                      <p className="mt-1 font-medium" aria-label="Issue">
                        {entry.issue}
                        {entry.other_problems > 0 &&
                          ` (and ${entry.other_problems} more ${entry.other_problems === 1 ? "check" : "checks"})`}
                      </p>
                    )}
                    {list === "copies" && (
                      <p className="mt-1">
                        {entry.set_aside
                          ? `Set aside as a copy${entry.copy_of ? ` of ${entry.copy_of}` : ""}. It counts nothing.`
                          : "Possible copy of another statement: compare it with the original."}
                      </p>
                    )}
                  </div>
                  {entry.batch_id && (
                    <Button
                      size="sm"
                      variant={position === 0 ? "primary" : "outline"}
                      onClick={() => {
                        setOrder(current)
                        appliedOrder.current = orderKey
                        open(entry)
                      }}
                    >
                      {list === "copies" ? "Open copy" : "Open"}
                    </Button>
                  )}
                </li>
              ))}
            </ol>
          )}
          {list === "unreadable" && query.data.unreadable_files.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium">Files that could not be prepared</p>
              <ul className="divide-y rounded border">
                {query.data.unreadable_files.map((file) => (
                  <li
                    key={`${file.batch_id}:${file.source_id}`}
                    className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm"
                  >
                    <span>
                      {file.filename}: {file.message}
                    </span>
                    <Button size="sm" variant="outline" onClick={() => onOpenBatch(file.batch_id)}>
                      Open its batch
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  )
}

function OutcomeNote({
  outcome,
  onDismiss,
}: {
  outcome: { entry: QueueEntry; message: string; held: boolean }
  onDismiss: () => void
}) {
  return (
    <div
      role="status"
      aria-label="Result of your last save"
      className={`flex flex-wrap items-start justify-between gap-2 rounded border p-3 text-sm ${outcome.held ? "border-amber-500/60" : "border-teal-500/60"}`}
    >
      <p>
        <span className="font-medium">
          {outcome.entry.filename} ({entryPeriod(outcome.entry)}):
        </span>{" "}
        {outcome.message}
      </p>
      <Button size="sm" variant="ghost" onClick={onDismiss}>
        Dismiss
      </Button>
    </div>
  )
}
