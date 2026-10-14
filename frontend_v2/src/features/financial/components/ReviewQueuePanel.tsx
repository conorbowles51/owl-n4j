import { useEffect, useMemo, useRef, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { BatchStatementReview } from "./FinancialBatchPanel"
import { useFinancialAccess } from "../hooks/use-financial-access"
import {
  entryPeriod,
  importOutcome,
  fillAndSaveReady,
  useReviewQueue,
  type QueueEntry,
  type QueueSaveResult,
  type ReviewQueue,
} from "../lib/review-queue"
import { ReadingProgress } from "./ReadingProgress"

type ListName = "waiting" | "ready" | "filled" | "reader" | "copies" | "unreadable"
const QUEUE_KEYS = ["queueItem", "queueList", "queueFiles"]
const FIELD_NAMES: Record<string, string> = {
  currency: "currency",
  institution: "bank",
  holder: "account holder",
  account_number: "account number",
}

function listOf(data: ReviewQueue | undefined, name: ListName): QueueEntry[] {
  if (!data) return []
  return name === "copies"
    ? data.copies
    : name === "filled"
      ? data.filled
      : name === "reader"
        ? data.reader_fix
      : name === "unreadable"
      ? data.unreadable
      : name === "ready"
        ? data.ready
      : data.items
}

/** The plain per-case status line; every number is a count of the queue's own lists. */
export function ReviewStatusLine({
  data,
  onOpen,
  onSaveReady,
  saving = false,
}: {
  data: Pick<ReviewQueue, "counts">
  onOpen?: (list: ListName) => void
  /** One click: save every ready statement of the case (or of the filtered files). */
  onSaveReady?: () => void
  saving?: boolean
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
  const ready = c.ready + c.filled
  const total =
    c.imported + c.waiting + (c.reader_fix ?? 0) + c.filled + c.ready + c.copies +
    c.unreadable + c.unreadable_files + c.saving + c.rechecking + c.left_unimported
  const parts = [
    <span key="total">Total {total}:</span>,
    part("Imported", c.imported),
    part("Waiting for you", c.waiting, "waiting"),
    ...(c.reader_fix ? [part("Waiting for a reader fix", c.reader_fix, "reader")] : []),
    ...(c.filled ? [part("Details filled automatically", c.filled, "filled")] : []),
    ...(c.ready ? [part("Ready to import", c.ready, "ready")] : []),
    part("Copies set aside", c.copies, "copies"),
    part("Couldn't read", c.unreadable + c.unreadable_files, "unreadable"),
    ...(c.saving ? [part("Importing now", c.saving)] : []),
    ...(c.rechecking ? [part("Being rechecked", c.rechecking)] : []),
    ...(c.left_unimported ? [part("Left out by you", c.left_unimported)] : []),
  ]
  return (
    <div className="flex flex-wrap items-center gap-2">
      <p className="text-sm" aria-label="Statement status">
        {parts.map((value, index) => (
          <span key={index}>
            {index > 1 && " · "}{index === 1 && " "}
            {value}
          </span>
        ))}
      </p>
      {onSaveReady && ready > 0 && (
        <div className="flex basis-full flex-wrap items-center gap-2 rounded border p-2 text-sm">
          <Button size="sm" disabled={saving} onClick={onSaveReady}>
            {saving
              ? "Importing…"
              : `Import ${ready} ready ${ready === 1 ? "statement" : "statements"}`}
          </Button>
          <span>
            Ready means {ready === 1 ? "it passed" : "they passed"} every check (balances add up, account, holder,
            currency and dates are known) and {ready === 1 ? "needs" : "need"} nothing from you. Importing adds{" "}
            {ready === 1 ? "it" : "them"} to the ledger and {ready === 1 ? "it moves" : "they move"} to Imported.
            Each is checked once more first; anything that no longer passes stays here with its reason.
          </span>
        </div>
      )}
    </div>
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
  const { canEdit } = useFinancialAccess()
  const [saving, setSaving] = useState("")
  const [saveResult, setSaveResult] = useState<QueueSaveResult | null>(null)
  const [saveError, setSaveError] = useState("")
  // Saves straight from the queue, across batches, with the batch save's
  // admission checks; the result is one line: N imported, M held: reason.
  const saveReady = async () => {
    const data = query.data
    if (!data || !(data.ready.length || data.filled.length) || saving) return
    setSaveError("")
    setSaveResult(null)
    setSaving("Checking the ready statements…")
    try {
      setSaveResult(await fillAndSaveReady(caseId, data, { onProgress: setSaving }))
    } catch (error) {
      setSaveError(
        `${error instanceof Error ? error.message : "Saving could not start."} Statements already accepted keep saving on the server; refresh the queue to see where each one stands.`
      )
    } finally {
      setSaving("")
      void client.invalidateQueries({ queryKey: ["financial-review-queue", caseId] })
      void client.invalidateQueries({ queryKey: ["financial-review-status", caseId] })
    }
  }
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
            proposals: active.proposals,
            also: active.also,
            fixMakesReady: active.fix_makes_ready,
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
            : list === "filled"
              ? "Details filled automatically"
              : list === "reader"
                ? "Waiting for a reader fix"
              : list === "unreadable"
              ? "Couldn't read"
              : list === "ready"
                ? "Ready to import"
              : "Waiting for you"}
        </h3>
        <p className="text-sm text-muted-foreground">
          {list === "reader"
            ? "Files Loupe cannot read reliably yet: most of their statements fail on reading or on the account's identity, and no single field would make one ready. Nothing needs reviewing by hand; they are re-read when the reader is fixed. Their statements are listed below each file and can still be opened."
            : list === "filled"
            ? "Statements whose only missing details were found with certainty in the same account's saved statements. Saving fills them as System (each change is kept in the file's account-detail history) and the statement is saved only if everything else checks out. To use another value, open the statement and change it before or after saving."
            : list === "copies"
            ? "Statements that are copies of another statement in this case. Copies the system set aside count nothing; possible copies wait for you to compare them with the original."
            : list === "unreadable"
              ? "Statements or files where nothing usable could be read. Open one to see its pages."
              : list === "ready"
                ? "Statements that passed every check and need nothing from you. Use Import above to add them to the ledger; open one to look at it first."
              : "Only statements that need a decision from you. Each says what to fix before you open it. Imported statements, copies and statements ready to import are not listed here."}
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
          <ReviewStatusLine
            data={query.data}
            onOpen={showList}
            onSaveReady={canEdit ? () => void saveReady() : undefined}
            saving={!!saving}
          />
          <ReadingProgress caseId={caseId} reading={query.data.reading} />
          {saving && <p role="status" className="text-sm">{saving}</p>}
          {saveError && <p role="alert" className="text-sm">{saveError}</p>}
          {saveResult && (
            <div
              role="status"
              aria-label="Result of importing ready statements"
              className={`space-y-1 rounded border p-3 text-sm ${saveResult.held.length ? "border-amber-500/60" : "border-teal-500/60"}`}
            >
              <p className="font-medium">{saveResult.message}</p>
              {saveResult.held.some((entry) => entry.filename) && (
                <details>
                  <summary className="cursor-pointer">Which statements were held</summary>
                  <ul className="mt-1 space-y-1">
                    {saveResult.held
                      .filter((entry) => entry.filename)
                      .map((entry, index) => (
                        <li key={`${entry.item_id}:${index}`}>
                          {entry.filename} ({entry.period_start || "?"} to {entry.period_end || "?"}): {entry.reason}
                        </li>
                      ))}
                  </ul>
                </details>
              )}
              <Button size="sm" variant="ghost" onClick={() => setSaveResult(null)}>
                Dismiss
              </Button>
            </div>
          )}
          {list !== "waiting" && (
            <Button variant="outline" size="sm" onClick={() => showList("waiting")}>
              Back to waiting for you ({query.data.counts.waiting})
            </Button>
          )}
          {list === "waiting" && query.data.counts.filled > 0 && (
            <Button variant="outline" size="sm" onClick={() => showList("filled")}>
              Details filled automatically ({query.data.counts.filled})
            </Button>
          )}
          {list === "waiting" && query.data.copies.length > 0 && (
            <Button variant="outline" size="sm" onClick={() => showList("copies")}>
              Review copies ({query.data.copies.length})
            </Button>
          )}
          {list === "waiting" && query.data.reader_files.length > 0 && (
            <Button variant="outline" size="sm" onClick={() => showList("reader")}>
              Waiting for a reader fix ({query.data.counts.reader_fix} in{" "}
              {query.data.reader_files.length}{" "}
              {query.data.reader_files.length === 1 ? "file" : "files"})
            </Button>
          )}
          {list === "reader" && (
            <ul className="space-y-2" aria-label="Files waiting for a reader fix">
              {query.data.reader_files.map((file) => (
                <li key={file.file_id} className="rounded border p-3 text-sm">
                  <p className="font-medium">{file.filename}</p>
                  <p>{file.message}</p>
                </li>
              ))}
            </ul>
          )}
          {list === "reader" ? (
            <details>
              <summary className="cursor-pointer text-sm">
                Show their {current.length} statements
              </summary>
              <ol className="divide-y rounded border" aria-label="Statements waiting for a reader fix">
                {current.map((entry) => (
                  <li key={entry.id} className="flex flex-wrap items-center justify-between gap-3 p-3 text-sm">
                    <div className="min-w-0 flex-1 basis-72">
                      <EntryLine entry={entry} />
                      {entry.issue && <p className="mt-1">{entry.issue}</p>}
                      {entry.also.length > 0 && <p>also: {entry.also.join("; ")}</p>}
                    </div>
                    {entry.batch_id && (
                      <Button size="sm" variant="outline" onClick={() => {
                        setOrder(current)
                        appliedOrder.current = orderKey
                        open(entry)
                      }}>
                        Open
                      </Button>
                    )}
                  </li>
                ))}
              </ol>
            </details>
          ) : current.length === 0 ? (
            <p role="status" className="rounded border p-3">
              {list === "waiting"
                ? "Nothing is waiting for you."
                : list === "copies"
                  ? "No copies."
                : list === "filled"
                  ? "No statement waits only for details found automatically."
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
                        {!entry.also.length &&
                          entry.other_problems > 0 &&
                          ` (and ${entry.other_problems} more ${entry.other_problems === 1 ? "check" : "checks"})`}
                      </p>
                    )}
                    {entry.issue && entry.also.length > 0 && (
                      <p className="text-sm" aria-label="Also to fix">
                        also: {entry.also.join("; ")}
                      </p>
                    )}
                    {entry.proposals && (list === "filled" || list === "waiting") && (
                      <ul className="mt-1 text-xs" aria-label="Details found automatically">
                        {Object.entries(entry.proposals).map(([field, proposal]) => (
                          <li key={field}>
                            {proposal.confirmed ? "Fills" : "Proposed"}{" "}
                            {FIELD_NAMES[field] ?? field}: <strong>{proposal.value}</strong>{" "}
                            ({proposal.label})
                          </li>
                        ))}
                      </ul>
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
                      {list === "copies" ? "Open copy" : list === "filled" ? "Open to change" : "Open"}
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
