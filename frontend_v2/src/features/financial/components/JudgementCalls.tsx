import { Disclosure } from "./Disclosure"
import { useContext, useMemo, useState, type ReactNode } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { judgementKeys, useJudgementCounts, useJudgementRowMap, useJudgements } from "../hooks/use-judgements"
import { RowJudgements } from "../hooks/use-judgement-rows"
import { ChevronRight, CircleAlert, Clock3, Flag, Lightbulb } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/cn"
import { useFinancialAccess } from "../hooks/use-financial-access"
import {
  confirmJudgement,
  judgementLookup,
  previewJudgements,
  correctJudgement,
  countLine,
  PRIORITY_BADGE,
  PRIORITY_HELP,
  PRIORITY_LABELS,
  PRIORITY_ROW,
  statusLabel,
  strengthHelp,
  strengthLabel,
  type Judgement,
} from "../lib/judgements"
import type { LedgerTransaction } from "../api"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"

const PRIORITY_ICONS = { "1": CircleAlert, "2": Flag, "3": Clock3 } as const

/** A call's priority as text and icon (never colour alone); the reason is in the tooltip. */
export function PriorityLabel({ priority, reason, className }: { priority: number; reason?: string | null; className?: string }) {
  const key = String(priority || 1) as keyof typeof PRIORITY_ICONS
  const Icon = PRIORITY_ICONS[key] || CircleAlert
  return (
    <span
      data-testid="judgement-priority"
      data-priority={key}
      title={`${PRIORITY_LABELS[key]}: ${PRIORITY_HELP[key]}${reason ? ` Here, ${reason}.` : ""}`}
      className={cn("inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-semibold", PRIORITY_BADGE[key], className)}
    >
      <Icon aria-hidden="true" className="size-3" />
      {PRIORITY_LABELS[key]}
    </span>
  )
}

/** The row's background tint and left border for its tier. */
export function priorityRowClass(priority: number) {
  return PRIORITY_ROW[String(priority || 1)] || PRIORITY_ROW["1"]
}

/**
 * The legend at the top of a list of calls: each tier with its count, and a toggle that shows only that tier.
 * Counts come from the list's own source, so they move as calls are answered.
 */
export function PriorityLegend({
  counts,
  value,
  onChoose,
  label = "Priority",
  className,
}: {
  counts: Record<string, number> | undefined
  value: string
  onChoose?: (value: string) => void
  label?: string
  className?: string
}) {
  return (
    <div className={cn("flex flex-wrap items-center gap-1.5 text-sm", className)} role="group" aria-label={label}>
      <span className="w-20 shrink-0 font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{label}</span>
      {(["1", "2", "3"] as const).map((key) => {
        const on = value === key
        const Icon = PRIORITY_ICONS[key]
        const content = (
          <>
            <Icon aria-hidden="true" className="size-3.5" />
            {PRIORITY_LABELS[key]} ({counts?.[key] || 0})
          </>
        )
        const look = cn(
          "inline-flex items-center gap-1.5 rounded-full border-l-4 px-3 py-1.5 text-[13px] font-semibold",
          PRIORITY_BADGE[key],
          PRIORITY_ROW[key].split(" ").filter((c) => c.includes("border-l-[")).join(" "),
          on && "ring-2 ring-foreground ring-offset-1"
        )
        return onChoose ? (
          <button key={key} type="button" aria-pressed={on} title={PRIORITY_HELP[key]} className={look}
            onClick={() => onChoose(on ? "" : key)}>
            {content}
          </button>
        ) : (
          <span key={key} title={PRIORITY_HELP[key]} className={look}>{content}</span>
        )
      })}
      {onChoose && value && (
        <button type="button" className="text-[13px] underline" onClick={() => onChoose("")}>
          Every priority
        </button>
      )}
    </div>
  )
}

function tierCounts(items: { priority?: number }[]) {
  const counts: Record<string, number> = {}
  for (const item of items) counts[String(item.priority || 1)] = (counts[String(item.priority || 1)] || 0) + 1
  return counts
}

/** A short list of calls (one statement, one period, one reading): tier order, legend, tier filter, tinted rows. */
function TieredList<T extends { priority?: number }>({
  items,
  render,
  rowKey,
}: {
  items: T[]
  render: (item: T) => ReactNode
  rowKey: (item: T, index: number) => string
}) {
  const [tier, setTier] = useState("")
  const ordered = [...items].sort((a, b) => (a.priority || 1) - (b.priority || 1))
  const shown = tier ? ordered.filter((item) => String(item.priority || 1) === tier) : ordered
  const tiers = new Set(items.map((item) => item.priority || 1)).size
  return (
    <div className="space-y-1.5">
      {tiers > 1 && <PriorityLegend counts={tierCounts(items)} value={tier} onChoose={setTier} />}
      <ul className="space-y-1.5">
        {shown.map((item, index) => (
          <li key={rowKey(item, index)} className={cn("rounded-md py-1.5 pl-2 pr-1", priorityRowClass(item.priority || 1))}>
            {render(item)}
          </li>
        ))}
      </ul>
    </div>
  )
}

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
  const items = [...(context?.lookup(transaction) || [])].sort((a, b) => (a.priority || 1) - (b.priority || 1))
  if (!context || !items.length) return null
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
  hidePriority = false,
}: {
  caseId: string
  judgement: Judgement
  onCorrect?: (judgement: Judgement) => void
  defaultOpen?: boolean
  /** In a table row: icon, one word and the chevron; the panel opens below. */
  compact?: boolean
  /** The row around it already shows the tier. */
  hidePriority?: boolean
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
  // State colours follow the review queue's badges (spec tokens); the glyph carries the type without colour.
  const tone =
    judgement.status === "corrected"
      ? "border-transparent bg-[#fde6e8] text-[#a3142a]"
      : judgement.status === "confirmed"
        ? "border-transparent bg-[#e3f4ea] text-[#15653f]"
        : judgement.origin === "agent"
          ? "border-transparent bg-[#f1eefb] text-[#573199]"
          : judgement.strength === "inferred"
            ? "border-transparent bg-[#fdf0d5] text-[#8a5300]"
            : "border-transparent bg-[#e6efff] text-[#1f4fa8]"
  const word = settled ? statusLabel(judgement) : strengthLabel(judgement)
  const glyph =
    judgement.status === "corrected"
      ? "✕"
      : judgement.status === "confirmed"
        ? "✓"
        : judgement.origin === "agent"
          ? "✎"
          : judgement.strength === "inferred"
            ? "◐"
            : "●"
  const [notes, setNotes] = useState(false)
  const [technical, setTechnical] = useState(false)
  return (
    <div
      className={compact && !open ? "inline-block text-xs" : "text-xs"}
      data-testid="judgement-marker"
      data-judgement-id={judgement.id}
    >
      {!hidePriority && (
        <PriorityLabel priority={judgement.priority} reason={judgement.priority_reason} className="mr-1 align-middle" />
      )}
      <button
        type="button"
        className={cn(
          "inline-flex max-w-full cursor-pointer items-center gap-1 rounded-md border px-2 py-0.5 text-left font-semibold",
          "hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
          tone
        )}
        aria-expanded={open}
        title={`${judgement.rule_label}. ${strengthHelp(judgement)} Click for why.`}
        onClick={() => setOpen(!open)}
      >
        <span aria-hidden="true" className="shrink-0">{glyph}</span>
        <span>{word}</span>
        {!compact && (
          <span className="truncate font-normal text-muted-foreground">· {judgement.rule_label}</span>
        )}
        <span className="font-normal">· <span className="underline underline-offset-2">Why?</span></span>
        <ChevronRight
          aria-hidden="true"
          className={cn("size-3 shrink-0 transition-transform", open && "rotate-90")}
        />
      </button>
      {open && (
        <div
          role="region"
          aria-label="Judgement call"
          className="mt-1 max-w-xl space-y-2.5 rounded-xl bg-card p-3 text-[13px] shadow-[0_1px_0_#e4e3df,0_8px_24px_rgba(20,22,27,.08)] dark:border"
        >
          <div className="flex flex-wrap gap-1.5">
            <span className={cn("rounded-md px-2 py-0.5 font-semibold", tone)}>
              <span aria-hidden="true">{glyph} </span>
              {word}
            </span>
            <span className="rounded-md bg-muted px-2 py-0.5 font-medium">{judgement.category_label || judgement.rule_label}</span>
            <PriorityLabel priority={judgement.priority} reason={judgement.priority_reason} />
          </div>
          <div>
            <span className="block font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">Why Loupe did it</span>
            <p className="text-sm">{judgement.summary}</p>
          </div>
          <div>
            <span className="block font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">How sure</span>
            <p>{strengthHelp(judgement)}</p>
          </div>
          <div>
            <span className="block font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
              Why {PRIORITY_LABELS[String(judgement.priority || 1)]?.toLowerCase()}
            </span>
            <p>
              {PRIORITY_HELP[String(judgement.priority || 1)]}
              {judgement.priority_reason ? ` Here, ${judgement.priority_reason}.` : ""}
            </p>
          </div>
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
                className="bg-[#15653f] text-white hover:bg-[#0f5133]"
                disabled={confirm.isPending}
                onClick={() => confirm.mutate()}
              >
                <span aria-hidden="true">✓</span>Looks right
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
            <div>
              <button
                type="button"
                aria-expanded={notes}
                className="font-medium text-muted-foreground hover:text-foreground"
                onClick={() => setNotes(!notes)}
              >
                <span aria-hidden="true">{notes ? "▾ " : "▸ "}</span><span>Working notes</span>
              </button>
              {notes && (
                <p className="mt-1 whitespace-pre-wrap break-words text-muted-foreground">
                  {judgement.working_notes}
                </p>
              )}
            </div>
          )}
          <p className="text-muted-foreground" title={`${judgement.rule_id} · ${judgement.rule_source}`}>
            {judgement.filename ? `${judgement.filename} · ` : ""}
            {judgement.category_label || judgement.rule_label}
          </p>
          <div>
            <button
              type="button"
              aria-expanded={technical}
              className="font-medium text-muted-foreground hover:text-foreground"
              onClick={() => setTechnical(!technical)}
            >
              <span aria-hidden="true">{technical ? "▾ " : "▸ "}</span>
              <span>Technical details</span>
            </button>
            {technical && (
              <p className="mt-1 font-mono text-[12px] text-muted-foreground">
                Rule {judgement.rule_id}
                {judgement.rule_source ? ` · ${judgement.rule_source}` : ""}
              </p>
            )}
          </div>
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
      <TieredList
        items={statementLevel}
        rowKey={(judgement) => judgement.id}
        render={(judgement) => (
          <JudgementMarker
            caseId={caseId}
            judgement={judgement}
            onCorrect={onCorrect}
            defaultOpen={statementLevel.length <= 2}
          />
        )}
      />
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
          <TieredList
            items={query.data || []}
            rowKey={(judgement) => judgement.id}
            render={(judgement) => <JudgementMarker caseId={caseId} judgement={judgement} />}
          />
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
    <Disclosure className="rounded border p-3 text-sm" label={<><Lightbulb aria-hidden="true" className="mr-1 inline size-3" />
        {countLine({ total: items.length, inferred })} in this reading</>}>
      <p className="mt-2 text-muted-foreground">
        Values the reader chose that the page does not print outright. Check any of them on the page before you
        save; nothing is held for them. Once saved, each can be marked Looks right or corrected.
      </p>
      <div className="mt-2">
        <TieredList
          items={items}
          rowKey={(item, index) => `${item.rule_id}:${item.row_id}:${item.target_key}:${index}`}
          render={(item) => (
            <div className="space-y-1">
              <PriorityLabel priority={item.priority} className="mr-1" />
              <span
                className="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium"
                title={`${item.rule_id} · ${item.rule_source}`}
              >
                <Lightbulb aria-hidden="true" className="size-3" />
                {strengthLabel(item)} · {item.category_label}
              </span>
              <p>{item.summary}</p>
              <p className="text-xs text-muted-foreground">{strengthHelp(item)}</p>
            </div>
          )}
        />
      </div>
    </Disclosure>
  )
}
