import { useContext, useMemo, useState, type ReactNode } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { judgementKeys, useJudgementCounts, useJudgementRowMap, useJudgements } from "../hooks/use-judgements"
import { RowJudgements } from "../hooks/use-judgement-rows"
import { ChevronRight, Lightbulb } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/cn"
import { useFinancialAccess } from "../hooks/use-financial-access"
import {
  confirmJudgement,
  judgementLookup,
  previewJudgements,
  correctJudgement,
  countLine,
  statusLabel,
  strengthHelp,
  strengthLabel,
  type Judgement,
} from "../lib/judgements"
import type { LedgerTransaction } from "../api"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"

export function JudgementRowProvider({
  caseId,
  sourceDocumentId,
  onCorrect,
  children,
}: {
  caseId: string
  sourceDocumentId: string
  onCorrect?: (judgement: Judgement, transaction: LedgerTransaction) => void
  children: ReactNode
}) {
  const query = useJudgements(caseId, { sourceDocumentId })
  const value = useMemo(() => {
    const byTransaction = new Map<string, Judgement[]>()
    for (const judgement of query.data || [])
      if (judgement.subject_type === "transaction")
        byTransaction.set(judgement.subject_id, [
          ...(byTransaction.get(judgement.subject_id) || []),
          judgement,
        ])
    return {
      caseId,
      lookup: (transaction: Pick<LedgerTransaction, "key">) => byTransaction.get(transaction.key) || [],
      onCorrect,
    }
  }, [caseId, query.data, onCorrect])
  return <RowJudgements.Provider value={value}>{children}</RowJudgements.Provider>
}

/** Every ledger payment touched by a judgement call shows its marker; one read for the whole case. */
export function CaseJudgementProvider({
  caseId,
  onCorrect,
  children,
}: {
  caseId: string | undefined
  onCorrect?: (judgement: Judgement, transaction: LedgerTransaction) => void
  children: ReactNode
}) {
  const query = useJudgementRowMap(caseId)
  const value = useMemo(
    () => (caseId ? { caseId, lookup: judgementLookup(query.data), onCorrect } : null),
    [caseId, query.data, onCorrect]
  )
  return <RowJudgements.Provider value={value}>{children}</RowJudgements.Provider>
}

/** Under a payment's description: its judgement calls, if any. */
export function RowJudgementMarkers({ transaction }: { transaction: LedgerTransaction }) {
  const context = useContext(RowJudgements)
  const items = context?.lookup(transaction)
  if (!context || !items?.length) return null
  return (
    <div className="mt-1 flex flex-wrap gap-1">
      {items.map((judgement) => (
        <JudgementMarker
          key={judgement.id}
          compact
          caseId={context.caseId}
          judgement={judgement}
          onCorrect={
            context.onCorrect
              ? (chosen) => context.onCorrect?.(chosen, transaction)
              : undefined
          }
        />
      ))}
    </div>
  )
}

/**
 * The marker on a value the processor chose. Clicking it shows the sentence and the page; Looks right is one
 * click; Correct it opens the value's existing correction and then asks why, which is kept with the call.
 */
export function JudgementMarker({
  caseId,
  judgement,
  onCorrect,
  defaultOpen = false,
  compact = false,
}: {
  caseId: string
  judgement: Judgement
  onCorrect?: (judgement: Judgement) => void
  defaultOpen?: boolean
  /** In a table row: icon, one word and the chevron; the panel opens below. */
  compact?: boolean
}) {
  const { canEdit } = useFinancialAccess()
  const client = useQueryClient()
  const [open, setOpen] = useState(defaultOpen)
  const [showPage, setShowPage] = useState(false)
  const [correcting, setCorrecting] = useState(false)
  const [reason, setReason] = useState("")
  const refresh = () => client.invalidateQueries({ queryKey: judgementKeys.all(caseId) })
  const confirm = useMutation({
    mutationFn: () => confirmJudgement(caseId, judgement.id),
    onSuccess: refresh,
  })
  const correct = useMutation({
    mutationFn: () => correctJudgement(caseId, judgement.id, reason.trim()),
    onSuccess: () => {
      setCorrecting(false)
      return refresh()
    },
  })
  const settled = judgement.status !== "open"
  const tone =
    judgement.status === "corrected"
      ? "border-red-500/50 text-red-700 dark:text-red-400"
      : judgement.status === "confirmed"
        ? "border-emerald-500/50 text-emerald-700 dark:text-emerald-400"
        : judgement.origin === "agent"
          ? "border-slate-500/50 text-slate-700 dark:text-slate-300"
          : judgement.strength === "inferred"
            ? "border-yellow-500/60 text-yellow-800 dark:text-yellow-400"
            : "border-blue-500/50 text-blue-700 dark:text-blue-400"
  const word = settled ? statusLabel(judgement) : strengthLabel(judgement)
  return (
    <div
      className={compact && !open ? "inline-block text-xs" : "text-xs"}
      data-testid="judgement-marker"
      data-judgement-id={judgement.id}
    >
      <button
        type="button"
        className={cn(
          "inline-flex max-w-full cursor-pointer items-center gap-1 rounded-md border bg-background px-2 py-0.5 text-left font-medium",
          "hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
          tone
        )}
        aria-expanded={open}
        title={`${judgement.rule_label}. ${strengthHelp(judgement)} Click for why.`}
        onClick={() => setOpen(!open)}
      >
        <Lightbulb aria-hidden="true" className="size-3 shrink-0" />
        <span>{word}</span>
        {!compact && (
          <span className="truncate font-normal text-muted-foreground">· {judgement.rule_label}</span>
        )}
        <span className="font-normal underline underline-offset-2">Why?</span>
        <ChevronRight
          aria-hidden="true"
          className={cn("size-3 shrink-0 transition-transform", open && "rotate-90")}
        />
      </button>
      {open && (
        <div
          role="region"
          aria-label="Judgement call"
          className="mt-1 max-w-xl space-y-2 rounded border bg-background p-2"
        >
          <p className="text-sm">{judgement.summary}</p>
          <p className="text-muted-foreground">{strengthHelp(judgement)}</p>
          {settled && (
            <p>
              {statusLabel(judgement)}
              {judgement.resolved_by ? ` · ${judgement.resolved_by}` : ""}
              {judgement.resolution_reason ? `: ${judgement.resolution_reason}` : ""}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            {judgement.page && judgement.evidence_file_id && (
              <Button size="sm" variant="outline" onClick={() => setShowPage(!showPage)}>
                {showPage ? "Hide page" : `Show page ${judgement.page}`}
              </Button>
            )}
            {canEdit && judgement.status === "open" && (
              <Button
                size="sm"
                variant="outline"
                disabled={confirm.isPending}
                onClick={() => confirm.mutate()}
              >
                Looks right
              </Button>
            )}
            {canEdit && judgement.status !== "corrected" && (
              <Button
                size="sm"
                variant="outline"
                aria-expanded={correcting}
                onClick={() => {
                  setCorrecting(true)
                  onCorrect?.(judgement)
                }}
              >
                Correct it
              </Button>
            )}
          </div>
          {showPage && judgement.page && judgement.evidence_file_id && (
            <TransactionSourceHighlight
              sourceDocumentId={judgement.evidence_file_id}
              locatorPayload={{ kind: "page_only", page: judgement.page }}
              wholePage
            />
          )}
          {correcting && (
            <form
              className="space-y-2"
              onSubmit={(event) => {
                event.preventDefault()
                if (reason.trim()) correct.mutate()
              }}
            >
              <p>
                {onCorrect
                  ? "Make the correction in the form that opened, save it, then say here why the processor was wrong."
                  : "Make the correction where this value is saved, then say here why the processor was wrong."}{" "}
                The reason is kept with this call and proposes a change to the rule.
              </p>
              <textarea
                aria-label="Why the processor was wrong"
                required
                className="w-full rounded border p-2 text-sm"
                rows={2}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
              <div className="flex gap-2">
                <Button size="sm" type="submit" disabled={!reason.trim() || correct.isPending}>
                  Record the correction
                </Button>
                <Button size="sm" variant="outline" type="button" onClick={() => setCorrecting(false)}>
                  Cancel
                </Button>
              </div>
            </form>
          )}
          {(confirm.error || correct.error) && (
            <p role="alert">{(confirm.error || correct.error)?.message}</p>
          )}
          {judgement.working_notes && (
            <details>
              <summary className="cursor-pointer text-muted-foreground">Working notes</summary>
              <p className="mt-1 whitespace-pre-wrap break-words text-muted-foreground">
                {judgement.working_notes}
              </p>
            </details>
          )}
          <p className="text-muted-foreground" title={`${judgement.rule_id} · ${judgement.rule_source}`}>
            {judgement.filename ? `${judgement.filename} · ` : ""}
            {judgement.category_label || judgement.rule_label}
          </p>
        </div>
      )}
    </div>
  )
}

/** One saved statement's judgement calls that are not on a payment row: balances, currency, account, copies. */
export function StatementJudgements({
  caseId,
  sourceDocumentId,
  onCorrect,
}: {
  caseId: string
  sourceDocumentId: string
  onCorrect?: (judgement: Judgement) => void
}) {
  const query = useJudgements(caseId, { sourceDocumentId })
  const items = query.data || []
  if (!items.length) return null
  const counts = {
    total: items.length,
    inferred: items.filter((j) => j.strength === "inferred").length,
    open: items.filter((j) => j.status === "open").length,
  }
  const statementLevel = items.filter((j) => j.subject_type !== "transaction")
  const onRows = items.length - statementLevel.length
  return (
    <div aria-label="Judgement calls in this statement" className="space-y-1 text-sm">
      <p className="font-medium">{countLine(counts)}</p>
      {statementLevel.map((judgement) => (
        <JudgementMarker
          key={judgement.id}
          caseId={caseId}
          judgement={judgement}
          onCorrect={onCorrect}
          defaultOpen={statementLevel.length <= 2}
        />
      ))}
      {onRows > 0 && (
        <p className="text-muted-foreground">
          {onRows} on payment rows: open the saved payments to see them beside each payment.
        </p>
      )}
    </div>
  )
}


/** In a list of statement periods: how many calls the period has; opening it shows each one in place. */
export function PeriodJudgements({ caseId, periodId }: { caseId: string; periodId: string }) {
  const counts = useJudgementCounts(caseId)
  const [open, setOpen] = useState(false)
  const tally = counts.data?.periods[periodId]
  const query = useJudgements(caseId, { statementPeriodId: periodId }, open)
  if (!tally?.total) return null
  return (
    <div className="mt-1 text-xs" aria-label="Judgement calls in this period">
      <button
        type="button"
        className="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <Lightbulb aria-hidden="true" className="size-3" />
        {countLine(tally)}
        <ChevronRight aria-hidden="true" className={cn("size-3 transition-transform", open && "rotate-90")} />
      </button>
      {open && (
        <div className="mt-1 space-y-1">
          {query.isPending && <p role="status">Loading…</p>}
          {(query.data || []).map((judgement) => (
            <JudgementMarker key={judgement.id} caseId={caseId} judgement={judgement} />
          ))}
        </div>
      )}
    </div>
  )
}

/** On an account: how many calls its statements carry, with a link to them all on the Judgement calls page. */
export function AccountJudgements({ caseId, accountId, label }: { caseId: string; accountId: string; label?: string }) {
  const counts = useJudgementCounts(caseId)
  const tally = counts.data?.accounts[accountId]
  if (!tally?.total) return null
  return (
    <p className="text-xs text-muted-foreground" aria-label="Judgement calls in this account">
      <Lightbulb aria-hidden="true" className="mr-1 inline size-3" />
      {label ? `${label}: ` : ""}
      {countLine(tally)} in this account's statements.{" "}
      <a
        className="underline"
        href={`/cases/${caseId}/financial?${new URLSearchParams({
          view: "statements",
          judgements: "1",
          jStatus: "all",
          jAccounts: accountId,
        })}`}
      >
        See them
      </a>
    </p>
  )
}

type ReadingRow = {
  id: string
  kind: string
  page_number: number
  excluded: boolean
  fields: Record<string, string>
  value_repairs?: Record<string, unknown>[]
  source_cells: { column_index: number; expected_text: string; locator: unknown }[]
}
type ReviewRow = { id: string; reason?: string; excluded?: boolean; manual_page?: number | null }

/**
 * Before saving (the review queue): the calls the rules make on this reading, from the same detection that
 * records them on save. Nothing is stored here; once saved, each can be confirmed or corrected.
 */
export function ReadingJudgements({
  caseId,
  statementId,
  revision,
  currency,
  readingRows,
  reviewRows,
}: {
  caseId: string
  statementId: string
  revision: string
  currency: string
  readingRows: ReadingRow[]
  reviewRows: ReviewRow[]
}) {
  // Only what the detection reads: each row's fields, repairs and cell text, and the review's reasons.
  const reading = useMemo(
    () =>
      readingRows.map((row) => ({
        id: row.id,
        kind: row.kind,
        page_number: row.page_number,
        excluded: row.excluded,
        fields: row.fields,
        value_repairs: row.value_repairs || [],
        source_cells: row.source_cells.map((cell) => ({
          column_index: cell.column_index,
          expected_text: cell.expected_text,
          locator: { page: (cell.locator as { page?: number } | null)?.page },
        })),
      })),
    [readingRows]
  )
  const review = reviewRows.filter((row) => row.reason || row.excluded || row.manual_page)
  const reviewKey = JSON.stringify(review.map((row) => [row.id, row.reason || "", !!row.excluded]))
  const query = useQuery({
    queryKey: ["financial-judgements", caseId, "preview", statementId, revision, currency, reviewKey],
    queryFn: () =>
      previewJudgements(caseId, {
        statement_id: statementId,
        currency,
        reading_rows: reading,
        review_rows: review,
      }),
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: 60_000,
  })
  const items = query.data || []
  if (!items.length) return null
  const inferred = items.filter((item) => item.strength === "inferred").length
  return (
    <details className="rounded border p-3 text-sm" aria-label="Judgement calls in this reading">
      <summary className="cursor-pointer font-medium">
        <Lightbulb aria-hidden="true" className="mr-1 inline size-3" />
        {countLine({ total: items.length, inferred })} in this reading
      </summary>
      <p className="mt-2 text-muted-foreground">
        Values the reader chose that the page does not print outright. Check any of them on the page before you
        save; nothing is held for them. Once saved, each can be marked Looks right or corrected.
      </p>
      <ul className="mt-2 space-y-2">
        {items.map((item, index) => (
          <li key={`${item.rule_id}:${item.row_id}:${item.target_key}:${index}`} className="space-y-1">
            <span
              className="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium"
              title={`${item.rule_id} · ${item.rule_source}`}
            >
              <Lightbulb aria-hidden="true" className="size-3" />
              {strengthLabel(item)} · {item.category_label}
            </span>
            <p>{item.summary}</p>
            <p className="text-xs text-muted-foreground">{strengthHelp(item)}</p>
          </li>
        ))}
      </ul>
    </details>
  )
}
