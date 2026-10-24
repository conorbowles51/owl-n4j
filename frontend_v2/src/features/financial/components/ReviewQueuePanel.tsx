import { useEffect, useMemo, useRef, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { BatchStatementReview, batchItemQuery } from "./FinancialBatchPanel"
import { statementReadingQuery } from "./StatementImportPanel"
import { useFinancialAccess } from "../hooks/use-financial-access"
import {
  entryBalances,
  entryPeriod,
  importOutcome,
  savedOutcome,
  fillAndSaveReady,
  heldReasons,
  readRetainedAfresh,
  checkUnreadableAgain,
  useReviewQueue,
  useReviewQueuePage,
  fetchReviewQueue,
  QUEUE_PAGE_SIZE,
  QUEUE_BULK_LIMIT,
  type QueuePageList,
  type QueueEntry,
  type QueueSaveResult,
  type ReviewQueue,
} from "../lib/review-queue"
import { ReadingProgress } from "./ReadingProgress"
import { BulkStatementDetails } from "./BulkStatementDetails"
import { QueueRowDetails, needsRowDetails } from "./QueueRowDetails"
import { QueueNoActivityConfirm } from "./QueueNoActivityConfirm"
import { QueueAnswerOnce } from "./QueueAnswerOnce"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import {
  HANDLED_PARTS,
  ISSUE_LABELS,
  filledMarks,
  groupEntries,
  groupGuidance,
  guidanceFor,
  handledCount,
  isGroup,
  issueLabel,
  needsCount,
  needsLabel,
  reasonProposal,
  type QueueGroup,
  type QueuePerson,
} from "../lib/queue-guidance"

type ListName = "waiting" | "ready" | "filled" | "reader" | "copies" | "unreadable" | "handled"
const PAGE_LISTS: Record<ListName, QueuePageList> = {
  waiting: "waiting",
  // The overview of what Loupe handles: counts only, its first list's page.
  handled: "ready",
  ready: "ready",
  filled: "filled",
  reader: "reader_fix",
  copies: "copies",
  unreadable: "unreadable",
}
const QUEUE_KEYS = ["queueItem", "queueList", "queueFiles", "queueIssue"]
export { ISSUE_LABELS }
// Issues one shared answer can fix for many statements at once.
const BULK_ISSUES = new Set(["currency", "institution", "holder", "account", "dates", "no_activity"])
// Reasons a value given once on the queue answers (single statement or a group).
const ANSWER_ONCE = new Set(["currency", "institution", "holder", "account", "no_activity"])
const HANDLED_LISTS = new Set<ListName>(["ready", "filled", "reader", "copies", "handled"])

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
      : name === "ready" || name === "handled"
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
    ...(c.removed_files ? [part("Files removed from Financial", c.removed_files, "unreadable")] : []),
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
              : c.filled
                ? `Import ${c.ready} ready, and ${c.filled} once ${c.filled === 1 ? "its details are" : "their details are"} filled`
                : `Import ${ready} ready ${ready === 1 ? "statement" : "statements"}`}
          </Button>
          <span>
            Ready means {ready === 1 ? "it passed" : "they passed"} every check (balances add up, account, holder,
            currency and dates are known) and {ready === 1 ? "needs" : "need"} nothing from you. Importing adds{" "}
            {ready === 1 ? "it" : "them"} to the ledger and {ready === 1 ? "it moves" : "they move"} to Imported.
            Each is checked once more first; anything that no longer passes stays here with its reason.
            {c.filled > 0 &&
              ` ${c.filled} of the ${ready} still ${c.filled === 1 ? "has" : "have"} details to fill: ${c.filled === 1 ? "it is" : "they are"} imported only if filling makes ${c.filled === 1 ? "it" : "them"} ready, and the result says which were not.`}
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
          entry.page ? `page ${entry.page}` : "",
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>
      {/* What the PDF prints on its first and last page: checkable at a glance without opening it. */}
      <p className="text-xs tabular-nums" aria-label="Period and printed balances">
        <span className="font-medium">{entryPeriod(entry)}</span> · {entryBalances(entry)}
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
  const issue = params.get("queueIssue") || ""
  // One page of the list on screen (counts stay whole-case). The page is not
  // in the URL: it starts again at the first page whenever the list, issue
  // or file filter changes.
  const pageScope = `${list}:${issue}:${fileIds.join(",")}`
  const [paging, setPaging] = useState({ scope: pageScope, offset: 0 })
  const offset = paging.scope === pageScope ? paging.offset : 0
  const setOffset = (value: number) => setPaging({ scope: pageScope, offset: Math.max(0, value) })
  const query = useReviewQueuePage(caseId, fileIds, {
    list: PAGE_LISTS[list],
    issue: list === "waiting" ? issue : "",
    offset,
  })
  const client = useQueryClient()
  const { canEdit, canUpload } = useFinancialAccess()
  const signedIn = useAuthStore((state) => state.user)
  const user: QueuePerson | null = signedIn ? { id: signedIn.id, name: signedIn.name } : null
  const [readingAfresh, setReadingAfresh] = useState(false)
  const [afreshResult, setAfreshResult] = useState("")
  const readAfresh = async () => {
    if (!query.data || readingAfresh) return
    setReadingAfresh(true)
    setAfreshResult("")
    try {
      setAfreshResult(await readRetainedAfresh(caseId, await fetchReviewQueue(caseId, fileIds)))
    } catch (error) {
      setAfreshResult(error instanceof Error ? error.message : "Reading afresh could not start.")
    } finally {
      setReadingAfresh(false)
      void client.invalidateQueries({ queryKey: ["financial-review-queue", caseId] })
      void client.invalidateQueries({ queryKey: ["financial-review-status", caseId] })
    }
  }
  const [checkingAgain, setCheckingAgain] = useState(false)
  const [checkAgainResult, setCheckAgainResult] = useState("")
  const checkAgain = async () => {
    if (!query.data || checkingAgain) return
    setCheckingAgain(true)
    setCheckAgainResult("")
    try {
      // Every unreadable statement, not only the page on screen.
      setCheckAgainResult(await checkUnreadableAgain(caseId, await fetchReviewQueue(caseId, fileIds)))
    } catch (error) {
      setCheckAgainResult(error instanceof Error ? error.message : "Checking again could not start.")
    } finally {
      setCheckingAgain(false)
      void client.invalidateQueries({ queryKey: ["financial-review-queue", caseId] })
      void client.invalidateQueries({ queryKey: ["financial-review-status", caseId] })
    }
  }
  const [saving, setSaving] = useState("")
  const [saveResult, setSaveResult] = useState<QueueSaveResult | null>(null)
  const [saveError, setSaveError] = useState("")
  // Saves straight from the queue, across batches, with the batch save's
  // admission checks; the result is one line: N imported, M held: reason.
  const saveReady = async () => {
    const counts = query.data?.counts
    if (!counts || !(counts.ready || counts.filled) || saving) return
    setSaveError("")
    setSaveResult(null)
    setSaving("Checking the ready statements…")
    try {
      // The save covers every ready statement, not the page on screen: it
      // reads the whole current queue first, as it always has.
      const data = await fetchReviewQueue(caseId, fileIds)
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
  // A server that pages says so (`page`); against one that does not, the
  // full list is paged here, so the screen never renders every entry at once.
  const serverPaged = !!query.data?.page
  const whole = listOf(query.data, list)
  const listed = useMemo(
    () => (serverPaged ? whole : whole.slice(offset, offset + QUEUE_PAGE_SIZE)),
    [serverPaged, whole, offset]
  )
  const pageTotal = query.data?.page?.total ?? whole.length
  const shownOffset = query.data?.page?.offset ?? offset
  const unreadableTotal = query.data?.totals?.unreadable ?? query.data?.unreadable.length ?? 0
  const issueCounts = useMemo(() => {
    const counts = new Map<string, number>()
    if (query.data?.issue_counts) for (const [reason, n] of Object.entries(query.data.issue_counts)) counts.set(reason, n)
    else
      for (const entry of whole)
        if (entry.issue_reason) counts.set(entry.issue_reason, (counts.get(entry.issue_reason) ?? 0) + 1)
    const rank = (reason: string) => {
      const position = Object.keys(ISSUE_LABELS).indexOf(reason)
      return position < 0 ? 99 : position
    }
    return [...counts.entries()].filter(([, n]) => n > 0).sort((a, b) => rank(a[0]) - rank(b[0]) || b[1] - a[1])
  }, [query.data?.issue_counts, whole])
  const allIssues = list === "waiting" ? (query.data?.totals?.waiting ?? whole.length) : whole.length
  const current = useMemo(
    () => (issue && list === "waiting" && !serverPaged ? listed.filter((entry) => entry.issue_reason === issue) : listed),
    [issue, list, listed, serverPaged]
  )
  // Without server paging an issue filter shortens the list after paging;
  // with it, the server filters first and says how many there are.
  const shownTotal = serverPaged || !(issue && list === "waiting")
    ? pageTotal
    : whole.filter((entry) => entry.issue_reason === issue).length
  // The issue a shared fix applies to: the chosen filter, or the only issue
  // listed (the filter buttons are not shown when there is just one kind).
  const bulkIssue =
    list === "waiting" ? issue || (issueCounts.length === 1 ? issueCounts[0][0] : "") : ""
  // A shared fix acts on every statement waiting for that issue, not the page
  // on screen: one read of all of them (capped, and said when capped).
  const bulkQuery = useReviewQueuePage(
    caseId,
    fileIds,
    { list: "waiting", issue: bulkIssue, limit: QUEUE_BULK_LIMIT },
    !!bulkIssue && canEdit
  )
  const bulkEntries = useMemo(
    () => (bulkQuery.data?.items ?? []).filter((entry) => entry.issue_reason === bulkIssue),
    [bulkIssue, bulkQuery.data]
  )
  const bulkTotal = bulkQuery.data?.page?.total ?? bulkEntries.length
  // Statements ticked for "no payments" confirmation together.
  const [quietChosen, setQuietChosen] = useState<Set<string>>(new Set())
  const chooseIssue = (value: string) =>
    setParams((previous) => {
      const next = new URLSearchParams(previous)
      if (value) next.set("queueIssue", value)
      else next.delete("queueIssue")
      next.delete("queueItem")
      return next
    })
  const orderKey = `${list}:${fileIds.join(",")}:${issue}:${offset}`
  const appliedOrder = useRef("")
  useEffect(() => {
    if (!query.data || query.isPlaceholderData) return
    if (!itemId || appliedOrder.current !== orderKey) {
      appliedOrder.current = orderKey
      setOrder(current)
    }
  }, [query.data, query.isPlaceholderData, itemId, orderKey, current])
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
  const [bulkOutcome, setBulkOutcome] = useState("")
  // The statement Next will open, loaded in the background while the current
  // one is reviewed, so moving on does not wait for it to be checked.
  const prefetchNext = (from: QueueEntry | undefined, list: QueueEntry[]) => {
    if (!from) return
    const position = list.findIndex((entry) => entry.id === from.id)
    const following = list.slice(position + 1).find((entry) => entry.batch_id)
    if (position < 0 || !following) return
    void client.prefetchQuery(batchItemQuery(caseId, following.batch_id!, following.id))
  }
  // Opening a statement asks for its batch item and its reading at once: the
  // review used to request the reading only after the item had arrived, and
  // each is a read of the statement on the server.
  const prefetchReading = (entry: QueueEntry) =>
    void client.prefetchQuery(
      statementReadingQuery(caseId, entry.file_id, entry.currency || "", entry.statement_id || "")
    )
  // Every save, fix and bulk save brings the queue and its totals up to date,
  // so the screen never needs reloading; with an entry, it says where that
  // statement now stands.
  const refresh = async (entry?: QueueEntry, keepOutcome = false) => {
    void client.invalidateQueries({ queryKey: ["financial-review-status", caseId] })
    // A detail saved from the list changes the statement's reading too.
    void client.invalidateQueries({ queryKey: ["statement-import", caseId], refetchType: "none" })
    // A save can change other statements' checks: copies loaded earlier are
    // reloaded when opened, and the next one is loaded again now.
    void client.invalidateQueries({ queryKey: ["financial-batch-item", caseId], refetchType: "none" })
    if (entry) prefetchNext(entry, entries)
    // Right after a change: wait for a queue built from the current data.
    const result = await query.refetchFresh()
    if (bulkIssue) void bulkQuery.refetchFresh()
    if (entry && result.data && !keepOutcome) setOutcome({ entry, ...savedOutcome(result.data, entry) })
    return result.data
  }
  /** After a shared fix: where the statements it covered stand now, from the refreshed queue. */
  const reportShared = (chosen: QueueEntry[], line: string) => {
    const ids = new Set(chosen.map((entry) => entry.id))
    void refresh().then((data) => {
      if (!data) return
      const left = data.items.filter((entry) => ids.has(entry.id)).length
      const ready = [...data.ready, ...data.filled].filter((entry) => ids.has(entry.id)).length
      setBulkOutcome(
        left
          ? `${line}. ${left} of ${ids.size} still need something; they stay listed below with what is left.${ready ? ` ${ready} ready to import.` : ""}`
          : `${line}. None of the ${ids.size} statements need anything more for this.${ready ? ` ${ready} ready to import.` : ""}`
      )
    })
  }
  const back = () => {
    // Every save made while the statement was open already refreshed the
    // queue (onChanged / onImported), and the queue polls by itself while
    // files are read or statements move: closing shows the list on screen
    // instead of reading the whole queue again.
    open(undefined)
  }
  const showList = (name: ListName) => {
    // Its order is taken from its first page when that arrives.
    setOrder([])
    appliedOrder.current = ""
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
  const onPage = index >= 0 ? entries[index] : current.find((e) => e.id === itemId)
  // A link to a statement that is not on the page on screen (from a batch, or
  // a later page): find it in the whole queue, once.
  const lookup = useReviewQueue(
    caseId,
    fileIds,
    !!itemId && !onPage && !!query.data && !query.isPlaceholderData
  )
  const active =
    onPage ??
    (lookup.data
      ? [lookup.data.items, lookup.data.ready, lookup.data.filled, lookup.data.reader_fix, lookup.data.copies, lookup.data.unreadable]
          .flat()
          .find((entry) => entry.id === itemId)
      : undefined)
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

  const activeGuide = active && (active.bucket === "waiting" || active.bucket === "unreadable" || list === "unreadable")
    ? guidanceFor(active, user, list === "unreadable" ? "unreadable" : active.bucket)
    : undefined
  if (itemId && active?.batch_id)
    return (
      <>
      <PrefetchNext entry={active} list={entries} prefetch={prefetchNext} reading={prefetchReading} />
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
            issue: activeGuide?.title ?? active.issue,
            steps: activeGuide?.steps,
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
              void refresh(active, true)
              step(1)
            },
            onChanged: () => void refresh(active),
          }}
        />
      </div>
      </>
    )

  return (
    <section aria-label="Review queue" className="space-y-4">
      <header className="space-y-1">
        <h3 className="text-lg font-semibold">
          {list === "copies"
            ? "Copies set aside"
            : list === "filled"
              ? "Details filled by Loupe"
              : list === "reader"
                ? "Waiting for a better reader"
              : list === "unreadable"
              ? "Nothing could be read"
              : list === "ready"
                ? "Ready to import"
              : list === "handled"
                ? "Loupe is handling"
              : needsLabel(user)}
        </h3>
        <p className="text-sm text-muted-foreground">
          {list === "reader"
            ? "Loupe cannot read these files reliably yet. Nothing needs doing by hand: they are read again when the reader improves. You can still open their statements below."
            : list === "filled"
            ? "The missing details were found in the same account's saved statements. Each value says where it came from. They are filled and imported when you press Import; change any value that is not right."
            : list === "copies"
            ? "Copies of statements already in the case. Copies set aside count nothing. A possible copy says so and asks you to compare it."
            : list === "unreadable"
              ? "Each item says which pages to look at and what to do."
              : list === "ready"
                ? "Every check passes. Press Import above to add them to the ledger; open one to look at it first."
              : list === "handled"
                ? "Nothing here needs you. Loupe moves these on by itself."
              : "Only what needs a person. Each item says what is wrong, where to look in the PDF and what to enter. It saves by itself once it checks out."}
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
          <QueueSplit
            counts={query.data.counts}
            user={user}
            handling={HANDLED_LISTS.has(list)}
            onNeeds={() => showList("waiting")}
            onHandled={() => showList("handled")}
          />
          {HANDLED_LISTS.has(list) && (
            <p role="note" className="rounded border border-dashed bg-muted/40 p-2 text-sm text-muted-foreground">
              Loupe is handling these. Nothing here needs you.
            </p>
          )}
          {list === "handled" && <HandledOverview counts={query.data.counts} onOpen={showList} />}
          <ReviewStatusLine
            data={query.data}
            onOpen={showList}
            onSaveReady={canEdit ? () => void saveReady() : undefined}
            saving={!!saving}
          />
          <ReadingProgress caseId={caseId} reading={query.data.reading} />
          {query.data.refreshing && (
            <p role="status" className="text-sm text-muted-foreground">
              Updating the numbers: this list was built moments ago and a current one is being prepared.
            </p>
          )}
          {saving && <p role="status" className="text-sm">{saving}</p>}
          {saveError && <p role="alert" className="text-sm">{saveError}</p>}
          {saveResult && (
            <div
              role="status"
              aria-label="Result of importing ready statements"
              className={`space-y-1 rounded border p-3 text-sm ${saveResult.held.length ? "border-amber-500/60" : "border-teal-500/60"}`}
            >
              <p className="font-medium">{saveResult.message}</p>
              {saveResult.held.length > 0 && (
                <details>
                  <summary className="cursor-pointer">
                    Which {saveResult.held.length} {saveResult.held.length === 1 ? "statement was" : "statements were"} held
                  </summary>
                  <ul className="mt-1 space-y-1">
                    {saveResult.held
                      .filter((entry) => entry.filename)
                      .map((entry, index) => (
                        <li key={`${entry.item_id}:${index}`}>
                          {entry.filename} ({entry.period_start || "?"} to {entry.period_end || "?"}): {entry.reason}
                        </li>
                      ))}
                    {saveResult.held.some((entry) => !entry.filename) && (
                      <li>
                        {saveResult.held.filter((entry) => !entry.filename).length} without a file name in the
                        server's answer:{" "}
                        {heldReasons(saveResult.held.filter((entry) => !entry.filename))}
                      </li>
                    )}
                  </ul>
                </details>
              )}
              {!!saveResult.notReady?.length && (
                <details>
                  <summary className="cursor-pointer">
                    Which {saveResult.notReady.length} were not imported after filling their details
                  </summary>
                  <ul className="mt-1 space-y-1" aria-label="Not ready after filling">
                    {saveResult.notReady.map((entry) => {
                      // Where it stands now, from the refreshed queue.
                      const now = query.data?.items.find((item) => item.id === entry.id)
                      return (
                        <li key={entry.id}>
                          {entry.filename} ({entryPeriod(entry)}):{" "}
                          {now ? `still needs: ${now.issue || "a check"}` : "no longer waiting; see the totals above"}
                        </li>
                      )
                    })}
                  </ul>
                </details>
              )}
              <Button size="sm" variant="ghost" onClick={() => setSaveResult(null)}>
                Dismiss
              </Button>
            </div>
          )}
          {list !== "waiting" && list !== "handled" && (
            <Button variant="outline" size="sm" onClick={() => showList(HANDLED_LISTS.has(list) ? "handled" : "waiting")}>
              {HANDLED_LISTS.has(list) ? "Back to Loupe is handling" : `Back to ${needsLabel(user)} (${query.data.counts.waiting})`}
            </Button>
          )}
          {list === "waiting" && query.data.counts.unreadable + query.data.counts.unreadable_files > 0 && (
            <Button variant="outline" size="sm" onClick={() => showList("unreadable")}>
              Nothing could be read ({query.data.counts.unreadable + query.data.counts.unreadable_files})
            </Button>
          )}
          {list === "waiting" && issueCounts.length > 1 && (
            <div className="flex flex-wrap items-center gap-2 text-sm" role="group" aria-label="Filter by issue">
              <span>Show:</span>
              <Button size="sm" variant={issue ? "outline" : "primary"} onClick={() => chooseIssue("")}>
                All issues ({allIssues})
              </Button>
              {issueCounts.map(([reason, count]) => (
                <Button
                  key={reason}
                  size="sm"
                  variant={issue === reason ? "primary" : "outline"}
                  aria-pressed={issue === reason}
                  onClick={() => chooseIssue(issue === reason ? "" : reason)}
                >
                  {issueLabel(reason)} ({count})
                </Button>
              ))}
            </div>
          )}
          {list === "waiting" && bulkIssue && canEdit && BULK_ISSUES.has(bulkIssue) && bulkEntries.length > 0 && (
            <div className="flex flex-wrap items-center gap-3 rounded border p-3 text-sm">
              <BulkStatementDetails
                // Kept by issue and file filter only: the queue refreshes while
                // files are read, and a refresh must not close the dialog or
                // drop the statements already selected in it.
                key={bulkIssue}
                scopeName={`queue:${bulkIssue}:${fileIds.join(",")}`}
                expected={bulkTotal}
                caseId={caseId}
                fileIds={[...new Set(bulkEntries.flatMap((entry) => [entry.file_id, ...entry.file_ids]))]}
                statements={bulkEntries.flatMap((entry) =>
                  [...new Set([entry.file_id, ...entry.file_ids])].map((file_id) => ({
                    file_id,
                    statement_id: entry.statement_id,
                  }))
                )}
                reviewGroup={bulkIssue}
                datesOnly={bulkIssue === "dates"}
                buttonLabel={`Fix all ${bulkTotal} together`}
                onSaved={() => reportShared(bulkEntries, "Saved")}
              />
              {bulkIssue === "no_activity" && (
                <QueueNoActivityConfirm
                  caseId={caseId}
                  entries={bulkEntries}
                  chosen={quietChosen}
                  onChoose={setQuietChosen}
                  onDone={(confirmed, line) => reportShared(confirmed, line)}
                />
              )}
              <span>
                Every statement listed below waits for the same detail. Choose them, enter the value once and check the
                preview before saving. Nothing is imported until each statement checks out.
              </span>
            </div>
          )}
          {bulkOutcome && (
            // Outside the shared-fix box: when the fix clears every statement
            // the box goes away, and the result must still be said.
            <div role="status" aria-label="Result of the shared fix"
              className="flex flex-wrap items-center justify-between gap-2 rounded border border-teal-500/60 p-3 text-sm font-medium">
              <span>{bulkOutcome}</span>
              <Button size="sm" variant="ghost" onClick={() => setBulkOutcome("")}>
                Dismiss
              </Button>
            </div>
          )}
          {list === "handled" ? null : list === "reader" && (
            <ul className="space-y-2" aria-label="Files waiting for a reader fix">
              {query.data.reader_files.map((file) => (
                <li key={file.file_id} className="rounded border p-3 text-sm">
                  <p className="font-medium">{file.filename}</p>
                  <p>{file.message}</p>
                </li>
              ))}
            </ul>
          )}
          {list === "handled" ? null : list === "reader" ? (
            <details>
              <summary className="cursor-pointer text-sm">
                Show their {shownTotal} statements
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
                ? "Nothing needs you. Loupe is handling the rest."
                : list === "copies"
                  ? query.data.copy_files.length > 0
                    ? "No statement is a copy; the files below are."
                    : "No copies."
                : list === "filled"
                  ? "No statement waits only for details found automatically."
                  : "Every statement could be read."}
            </p>
          ) : (
            <ol
              className={`divide-y rounded border ${HANDLED_LISTS.has(list) ? "border-dashed bg-muted/30 text-muted-foreground" : ""}`}
              aria-label="Statements to review"
            >
              {(list === "waiting" || list === "unreadable") && groupEntries(
                // Chosen together with the no-payments confirmation above, one tick each.
                current, bulkIssue === "no_activity" ? ["no_activity"] : []
              ).map((item, position) => {
                const openEntry = (entry: QueueEntry) => {
                  setOrder(current)
                  appliedOrder.current = orderKey
                  open(entry)
                }
                return isGroup(item) ? (
                  <GroupItem
                    key={item.key}
                    group={item}
                    user={user}
                    caseId={caseId}
                    canEdit={canEdit}
                    onOpen={openEntry}
                    onSaved={(entries, line) => reportShared(entries, line)}
                  />
                ) : (
                  <NeedsItem
                    key={item.id}
                    entry={item}
                    first={position === 0}
                    user={user}
                    caseId={caseId}
                    canEdit={canEdit}
                    bucket={list === "unreadable" ? "unreadable" : item.bucket}
                    onOpen={() => openEntry(item)}
                    onSaved={(saved) => void refresh(saved)}
                    noActivityPick={
                      canEdit && bulkIssue === "no_activity" && item.issue_reason === "no_activity"
                        ? {
                            checked: quietChosen.has(item.id),
                            onChange: (checked: boolean) => {
                              const next = new Set(quietChosen)
                              if (checked) next.add(item.id)
                              else next.delete(item.id)
                              setQuietChosen(next)
                            },
                          }
                        : undefined
                    }
                  />
                )
              })}
              {list !== "waiting" && list !== "unreadable" && current.map((entry, position) => (
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
                    {list === "filled" && (
                      <FilledMarks caseId={caseId} entry={entry} canEdit={canEdit} onSaved={(saved) => void refresh(saved)} />
                    )}
                    {canEdit && entry.batch_id && list === "filled" && (
                      <QueueRowDetails
                        key={entry.id}
                        caseId={caseId}
                        entry={entry}
                        onSaved={(saved) => void refresh(saved)}
                      />
                    )}
                    {list === "copies" && (
                      <p className="mt-1">
                        {entry.copy_reason === "same_file_read"
                          ? `Same file as ${entry.copy_of ?? "another upload"}, which was read. This upload's own reading is not used. It counts nothing.`
                          : entry.copy_reason === "same_pages_read"
                          ? `Every page is the same as ${entry.copy_of ?? "another upload"}, which was read. This upload's own reading is not used. It counts nothing.`
                          : entry.set_aside
                          ? `Set aside as a copy${entry.copy_of ? ` of ${entry.copy_of}` : ""}. It counts nothing.`
                          : `${needsLabel(user, entry)}: this may be a copy of another statement. Open it and compare it with the original; keep one.`}
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
          {shownTotal > QUEUE_PAGE_SIZE || offset > 0 ? (
            <nav aria-label="Pages of this list" className="flex flex-wrap items-center gap-2 text-sm">
              <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(offset - QUEUE_PAGE_SIZE)}>
                Previous {QUEUE_PAGE_SIZE}
              </Button>
              <span role="status" aria-label="Shown of this list">
                {/* From the page actually on screen (an earlier one stays while the next loads). */}
                Showing {current.length ? shownOffset + 1 : 0}–{shownOffset + current.length} of {shownTotal}
              </span>
              <Button
                size="sm"
                variant="outline"
                disabled={offset + QUEUE_PAGE_SIZE >= shownTotal}
                onClick={() => setOffset(offset + QUEUE_PAGE_SIZE)}
              >
                Next {QUEUE_PAGE_SIZE}
              </Button>
            </nav>
          ) : null}
          {list === "unreadable" && unreadableTotal > 0 && canEdit && (
            <div className="space-y-2 rounded border p-3 text-sm" aria-label="Check unreadable statements again">
              <p>
                The reader has improved since some of these files were prepared. Checking them again uses each file's
                saved reading with the current reader; reviews and imports are kept and nothing is imported.
              </p>
              <Button size="sm" variant="outline" disabled={checkingAgain} onClick={() => void checkAgain()}>
                {checkingAgain
                  ? "Starting…"
                  : `Check ${unreadableTotal} ${unreadableTotal === 1 ? "statement" : "statements"} again`}
              </Button>
              {checkAgainResult && <p role="status">{checkAgainResult}</p>}
            </div>
          )}
          {list === "copies" && query.data.copy_files.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium">Files set aside as copies</p>
              <ul className="divide-y rounded border">
                {query.data.copy_files.map((file) => (
                  <li
                    key={`${file.batch_id}:${file.source_id}`}
                    className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm"
                  >
                    <span>
                      {file.filename}:{" "}
                      {file.copy_reason === "same_pages_read" ? "every page is the same as" : "same file as"}{" "}
                      {file.copy_of ?? "another upload"}, which was read. This upload could not be prepared and
                      counts nothing.
                    </span>
                    <Button size="sm" variant="outline" onClick={() => onOpenBatch(file.batch_id)}>
                      Open its batch
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {list === "unreadable" && query.data.unreadable_files.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium">Files that could not be prepared</p>
              {(() => {
                const afresh = query.data.unreadable_files.filter((file) => file.read_afresh_revision).length
                if (!afresh) return null
                return (
                  <div className="space-y-2 rounded border p-3 text-sm" aria-label="Read removed PDFs afresh">
                    <p>
                      {afresh} {afresh === 1 ? "PDF's" : "PDFs'"} earlier imports were removed, and the copy they were to
                      be read again from is no longer in Evidence. Reading them afresh checks each PDF's bytes first;
                      the removals and earlier reviews stay in history.
                    </p>
                    {canEdit && canUpload && (
                      <Button size="sm" disabled={readingAfresh} onClick={() => void readAfresh()}>
                        {readingAfresh ? "Starting…" : `Read ${afresh} ${afresh === 1 ? "PDF" : "PDFs"} afresh`}
                      </Button>
                    )}
                    {afreshResult && <p role="status">{afreshResult}</p>}
                  </div>
                )
              })()}
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
          {list === "unreadable" && query.data.set_aside_files.length > 0 && (
            <details className="rounded border p-3 text-sm">
              <summary className="cursor-pointer">
                {query.data.set_aside_files.length}{" "}
                {query.data.set_aside_files.length === 1 ? "file is" : "files are"} not counted as
                {" "}couldn't read: removed from Financial, no longer in the case, or already read from an
                identical copy
              </summary>
              <ul className="mt-2 divide-y" aria-label="Files not counted as couldn't read">
                {query.data.set_aside_files.map((file) => (
                  <li key={`${file.batch_id}:${file.source_id}`} className="py-2">
                    {file.filename}: {file.message}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </section>
  )
}

/** Loads the statement after the open one once per opened statement. */
function PrefetchNext({
  entry,
  list,
  prefetch,
  reading,
}: {
  entry: QueueEntry
  list: QueueEntry[]
  prefetch: (from: QueueEntry, list: QueueEntry[]) => void
  reading: (entry: QueueEntry) => void
}) {
  useEffect(() => {
    reading(entry)
    prefetch(entry, list)
    // Once per opened statement; a save prefetches again through refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entry.id])
  return null
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

/** The two halves of the queue: what needs a person, and what Loupe moves on by itself. */
function QueueSplit({
  counts,
  user,
  handling,
  onNeeds,
  onHandled,
}: {
  counts: ReviewQueue["counts"]
  user: QueuePerson | null
  handling: boolean
  onNeeds: () => void
  onHandled: () => void
}) {
  const needs = needsCount(counts)
  const handled = handledCount(counts)
  return (
    <div role="tablist" aria-label="Queue" className="grid gap-2 sm:grid-cols-2">
      <button
        type="button"
        role="tab"
        aria-selected={!handling}
        onClick={onNeeds}
        className={`rounded-md border-2 p-3 text-left ${!handling ? "border-amber-500 bg-amber-50 dark:bg-amber-950/30" : "border-border"}`}
      >
        <span className="block text-base font-semibold">
          {needsLabel(user)} ({needs})
        </span>
        <span className="block text-xs text-muted-foreground">
          {needs ? "Each one says what to do and where to look." : "Nothing needs you right now."}
        </span>
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={handling}
        onClick={onHandled}
        className={`rounded-md border p-3 text-left text-muted-foreground ${handling ? "border-foreground/40 bg-muted" : "border-dashed bg-muted/30"}`}
      >
        <span className="block text-base font-semibold">Loupe is handling ({handled})</span>
        <span className="block text-xs">Filled, checked again, ready to import or set aside. You can ignore these.</span>
      </button>
    </div>
  )
}

function HandledOverview({
  counts,
  onOpen,
}: {
  counts: ReviewQueue["counts"]
  onOpen: (list: ListName) => void
}) {
  return (
    <ul className="divide-y rounded border bg-muted/30 text-sm text-muted-foreground" aria-label="What Loupe is handling">
      {HANDLED_PARTS.filter((part) => part.count(counts) > 0).map((part) => {
        const n = part.count(counts)
        const canList = part.list !== "rechecking" && part.list !== "saving"
        return (
          <li key={part.list} className="flex flex-wrap items-center justify-between gap-2 p-3">
            <span>
              <span className="font-medium text-foreground">
                {part.label} ({n})
              </span>
              {" · "}
              {part.line}
            </span>
            {canList && n > 0 && (
              <Button size="sm" variant="ghost" onClick={() => onOpen(part.list as ListName)}>
                Show them
              </Button>
            )}
          </li>
        )
      })}
    </ul>
  )
}

/** "Filled by Loupe from <where>": each value it filled, with a way to put in her own. */
function FilledMarks({
  caseId,
  entry,
  canEdit,
  onSaved,
}: {
  caseId: string
  entry: QueueEntry
  canEdit: boolean
  onSaved: (entry: QueueEntry) => void
}) {
  const marks = filledMarks(entry)
  const [undoing, setUndoing] = useState("")
  if (!marks.length) return null
  const reasonOf: Record<string, string> = { currency: "currency", institution: "institution", holder: "holder", account_number: "account" }
  return (
    <ul className="mt-1 space-y-1 text-xs" aria-label="Filled by Loupe">
      {marks.map((mark) => (
        <li key={mark.field} className="rounded border border-teal-500/50 bg-teal-50/60 px-2 py-1 dark:bg-teal-950/30">
          <span className="font-medium">
            {mark.name}: {mark.value}
          </span>{" "}
          <span className="text-muted-foreground">· filled by Loupe from {mark.basis}</span>
          {canEdit && undoing !== mark.field && (
            <Button size="sm" variant="ghost" className="ml-1 h-6 px-1" onClick={() => setUndoing(mark.field)}>
              Undo
            </Button>
          )}
          {undoing === mark.field && (
            <>
              <p>Enter the right value. Loupe uses yours instead of {mark.value}.</p>
              <QueueAnswerOnce
                caseId={caseId}
                reason={reasonOf[mark.field] ?? mark.field}
                entries={[entry]}
                actionLabel="Save"
                onSaved={() => onSaved(entry)}
              />
            </>
          )}
        </li>
      ))}
    </ul>
  )
}

/** One statement that needs a person: what is wrong, numbered steps, one button. */
function NeedsItem({
  entry,
  first,
  user,
  caseId,
  canEdit,
  bucket,
  onOpen,
  onSaved,
  noActivityPick,
}: {
  entry: QueueEntry
  first: boolean
  user: QueuePerson | null
  caseId: string
  canEdit: boolean
  bucket: string
  onOpen: () => void
  onSaved: (entry: QueueEntry) => void
  noActivityPick?: { checked: boolean; onChange: (checked: boolean) => void }
}) {
  const guide = guidanceFor(entry, user, bucket)
  const reason = entry.issue_reason || ""
  const proposal = reasonProposal(entry, reason)
  // One press (or one typed value) when that answer is all the identity lacks;
  // otherwise the row's detail fields, which take several values at once.
  const othersKnown = (["currency", "institution", "holder"] as const).every(
    (field) => field === reason || !!entry[field]
  )
  const answerHere =
    canEdit && bucket === "waiting" && ANSWER_ONCE.has(reason) && reason !== "no_activity" && othersKnown &&
    (reason === "account" || (!!proposal && !proposal.confirmed))
  const rowDetails = canEdit && bucket === "waiting" && !!entry.batch_id && !answerHere && needsRowDetails(entry)
  return (
    <li className="flex flex-wrap items-start justify-between gap-3 border-l-4 border-l-amber-500 p-3 text-sm">
      {noActivityPick && (
        <input
          type="checkbox"
          className="mt-1 self-start"
          aria-label={`Choose ${entry.filename} (${entryPeriod(entry)}) to confirm no payments`}
          checked={noActivityPick.checked}
          onChange={(event) => noActivityPick.onChange(event.target.checked)}
        />
      )}
      <div className="min-w-0 flex-1 basis-72 space-y-1">
        <p className="text-xs font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-400">
          {needsLabel(user, entry)}
        </p>
        <p className="text-base font-semibold" aria-label="What is wrong">
          {guide.title}
        </p>
        <ol className="list-decimal space-y-0.5 pl-5" aria-label="What to do">
          {guide.steps.map((text, index) => (
            <li key={index}>{text}</li>
          ))}
        </ol>
        <p className="text-xs text-muted-foreground" aria-label="What happens next">
          {guide.after}
        </p>
        {entry.also.length > 0 && (
          <p className="text-xs" aria-label="Also to fix">
            After that, also: {entry.also.join("; ")}
          </p>
        )}
        {!entry.also.length && entry.other_problems > 0 && (
          <p className="text-xs">
            After that, the statement shows {entry.other_problems} more {entry.other_problems === 1 ? "check" : "checks"}.
          </p>
        )}
        <div className="rounded bg-muted/40 p-2 text-xs">
          <EntryLine entry={entry} />
        </div>
        <FilledMarks caseId={caseId} entry={entry} canEdit={canEdit} onSaved={onSaved} />
        {answerHere && (
          <QueueAnswerOnce
            caseId={caseId}
            reason={reason}
            entries={[entry]}
            proposal={proposal && !proposal.confirmed ? { value: proposal.value, label: proposal.label } : undefined}
            actionLabel={guide.action}
            onSaved={() => onSaved(entry)}
          />
        )}
        {rowDetails && <QueueRowDetails key={entry.id} caseId={caseId} entry={entry} onSaved={(saved) => onSaved(saved)} />}
      </div>
      {entry.batch_id && (
        <Button size="sm" variant={first && !answerHere ? "primary" : "outline"} onClick={onOpen}>
          {answerHere ? "Open the PDF" : guide.action}
        </Button>
      )}
    </li>
  )
}

/** Several statements of one account answered at once: one item, one confirm. */
function GroupItem({
  group,
  user,
  caseId,
  canEdit,
  onOpen,
  onSaved,
}: {
  group: QueueGroup
  user: QueuePerson | null
  caseId: string
  canEdit: boolean
  onOpen: (entry: QueueEntry) => void
  onSaved: (entries: QueueEntry[], line: string) => void
}) {
  const guide = groupGuidance(group)
  return (
    <li className="space-y-1 border-l-4 border-l-amber-500 p-3 text-sm" aria-label="Same answer for several statements">
      <p className="text-xs font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-400">
        {needsLabel(user, group.entries[0])} · one answer for {group.entries.length} statements
      </p>
      <p className="text-base font-semibold" aria-label="What is wrong">
        {guide.title}
      </p>
      <ol className="list-decimal space-y-0.5 pl-5" aria-label="What to do">
        {guide.steps.map((text, index) => (
          <li key={index}>{text}</li>
        ))}
      </ol>
      <p className="text-xs text-muted-foreground" aria-label="What happens next">
        {guide.after}
      </p>
      {canEdit && (
        <QueueAnswerOnce
          caseId={caseId}
          reason={group.reason}
          entries={group.entries}
          proposal={group.proposal}
          actionLabel={guide.action}
          onSaved={(entries, line) => onSaved(entries, line)}
        />
      )}
      <details className="text-xs">
        <summary className="cursor-pointer">Which {group.entries.length} statements</summary>
        <ul className="mt-1 divide-y rounded border">
          {group.entries.map((entry) => (
            <li key={entry.id} className="flex flex-wrap items-center justify-between gap-2 p-2">
              <div className="min-w-0 flex-1">
                <EntryLine entry={entry} />
              </div>
              {entry.batch_id && (
                <Button size="sm" variant="outline" onClick={() => onOpen(entry)}>
                  Open the PDF
                </Button>
              )}
            </li>
          ))}
        </ul>
      </details>
    </li>
  )
}
