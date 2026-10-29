import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type KeyboardEvent } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { fetchAPI } from "@/lib/api-client"
import { useProtectedObjectUrl } from "@/lib/protected-file"
import { Button } from "@/components/ui/button"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { evidenceAPI } from "@/features/evidence/api"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import type { LedgerTransaction } from "../api"
import { formatLedgerAmount } from "../lib/ledger-format"
import {
  caseNames,
  cropWindow,
  lineBand,
  missingNameReason,
  modelReadingField,
  needsName,
  otherSide,
  showNextPageTop,
  similarPayments,
  withConfirmedName,
  withPersonName,
  type LineBand,
  type SimilarGroup,
} from "../lib/payment-naming"

export interface StatementPage {
  case_id: string
  transaction_id: string
  evidence_file_id: string
  filename: string
  locator: unknown
  locator_state: string
  page: number | null
  page_count: number | null
  last_on_page: boolean | null
  found: { kind: "amount" | "date"; text: string; rect: [number, number, number, number] }[]
  text_layer: boolean | null
}

const statementPageUrl = (caseId: string, id: string) =>
  `/api/financial/ledger/${encodeURIComponent(id)}/statement-page?${new URLSearchParams({ case_id: caseId })}`
const statementImageUrl = (caseId: string, id: string, page: number) =>
  `/api/financial/ledger/${encodeURIComponent(id)}/statement-page/${page}/image?${new URLSearchParams({ case_id: caseId, width: "1400" })}`

const pageQuery = (caseId: string, id: string) => ({
  queryKey: ["payment-statement-page", caseId, id],
  staleTime: 5 * 60_000,
  retry: false,
  queryFn: ({ signal }: { signal?: AbortSignal }) => fetchAPI<StatementPage>(statementPageUrl(caseId, id), { signal }),
})

/** Replace rows in every cached ledger read of this case, so the table and counts follow a save at once. */
function patchLedger(client: ReturnType<typeof useQueryClient>, caseId: string, replacements: LedgerTransaction[]) {
  const byId = new Map(replacements.map((row) => [row.key, row]))
  client.setQueriesData<{ transactions: LedgerTransaction[] }>({ queryKey: ["financial-ledger", caseId] }, (data) =>
    data?.transactions ? { ...data, transactions: data.transactions.map((row) => byId.get(row.key) ?? row) } : data
  )
}

/**
 * Name the other side of a payment while its statement line is on screen, beside the Transactions table.
 *
 * Shows the line highlighted on its page with the lines around it (and the next page's top when the line is the
 * page's last), the payment's facts and why it has no name; saves a typed name as a person's label through
 * PUT /ledger/payment-labels (origin "Named by <person> from the statement") and moves to the next payment
 * without a name. After a save it offers, never applies, the same name for similar payments.
 *
 * ``mode="confirm"`` works the names Claude read that no person has confirmed: the reading is shown with its
 * citation and filled in; Enter on the unchanged name confirms it (POST /ledger/payment-labels/confirm, the person
 * becomes its actor and the reading stays in the history), a changed name saves the person's correction.
 */
export function PaymentNamingPanel({
  caseId,
  rows,
  queue,
  currentId,
  onMove,
  onClose,
  onOpenDetails,
  readOnly = false,
  stickyTop = 0,
  mode = "name",
}: {
  caseId: string
  /** Every payment in view: names offered while typing and similar payments come from these. */
  rows: LedgerTransaction[]
  /** The payments without a name, in table order. */
  queue: LedgerTransaction[]
  currentId: string
  onMove: (id: string) => void
  onClose: () => void
  onOpenDetails?: (row: LedgerTransaction) => void
  /** A viewer of the case: the statement line, the queue and the keys, without the name field. */
  readOnly?: boolean
  /** Height in px of the sticky bar above the table; beside the table the panel's height leaves room for it. */
  stickyTop?: number
  /** "name": payments without a name; "confirm": names a model read that no person has confirmed. */
  mode?: "name" | "confirm"
}) {
  const client = useQueryClient()
  const user = useAuthStore((state) => state.user)
  const row = rows.find((item) => item.key === currentId)
  const confirming = mode === "confirm"
  const readField = row && confirming ? modelReadingField(row) : null
  const reading = row && readField ? row.label_sources?.[readField] : undefined
  const [name, setName] = useState("")
  // Set when a changed reading on the account's own side is submitted: that side is confirmed here, not renamed.
  const [ownSideNote, setOwnSideNote] = useState(false)
  const [offer, setOffer] = useState<{ source: LedgerTransaction; name: string; groups: SimilarGroup[]; ticked: Set<string> } | null>(null)
  const [last, setLast] = useState<{ originals: LedgerTransaction[]; name: string } | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const panel = useRef<HTMLElement>(null)
  const position = queue.findIndex((item) => item.key === currentId)
  const neighbour = (step: 1 | -1) => {
    if (position >= 0) return queue[position + step]?.key ?? null
    // The open payment is named (or filtered out): move to the nearest unnamed one in table order.
    const order = rows.map((item) => item.key)
    const here = order.indexOf(currentId)
    const ahead = queue.filter((item) => (order.indexOf(item.key) - here) * step > 0)
    return (step === 1 ? ahead[0] : ahead.at(-1))?.key ?? null
  }
  const next = neighbour(1)
  const previous = neighbour(-1)
  useEffect(() => {
    // In confirm mode the model's reading is filled in: Enter on it unchanged confirms it.
    setName(readField && row ? (row[readField] ?? "") : "")
    setOwnSideNote(false)
    // A viewer has no name field; the panel itself takes the keys.
    ;(readOnly ? panel.current : input.current)?.focus({ preventScroll: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentId, readOnly])
  useEffect(() => {
    if (next) void client.prefetchQuery(pageQuery(caseId, next))
  }, [client, caseId, next])

  const explanation = () =>
    `Named by ${user?.name || user?.username || "you"} from the statement on ${new Date().toISOString().slice(0, 10)}.`
  const save = useMutation({
    mutationFn: async ({ targets, value, sameAs }: { targets: LedgerTransaction[]; value: string; sameAs?: string }) => {
      const result = await fetchAPI<{ case_id: string; updated: number }>(
        `/api/financial/ledger/payment-labels?${new URLSearchParams({ case_id: caseId })}`,
        {
          method: "PUT",
          body: {
            transactions: targets.map((item) => ({ id: item.key, version: item.label_version ?? 0 })),
            counterparty_name: value,
            named_from: "statement",
            ...(sameAs ? { same_as: sameAs } : {}),
          },
        }
      )
      if (result.case_id !== caseId || result.updated !== targets.length)
        throw Error("Not every payment was confirmed as named. Reload the transactions before trying again.")
      return { targets, value, sameAs }
    },
    onSuccess: ({ targets, value, sameAs }) => {
      patchLedger(client, caseId, targets.map((item) => withPersonName(item, value, explanation())))
      void client.invalidateQueries({ queryKey: ["financial-ledger", caseId], refetchType: "none" })
      void client.invalidateQueries({ queryKey: ["ledger-source", caseId] })
      setLast({ originals: targets, name: value })
      if (sameAs) {
        setOffer(null)
        toast.success(`Named ${targets.length} similar ${targets.length === 1 ? "payment" : "payments"} ${value}.`)
        return
      }
      const groups = similarPayments(targets[0], rows)
      setOffer(
        groups.length
          ? {
              source: targets[0],
              name: value,
              groups,
              ticked: new Set(groups.filter((group) => group.preselected).flatMap((group) => group.rows.map((item) => item.key))),
            }
          : null
      )
    },
  })
  const undo = useMutation({
    mutationFn: async (originals: LedgerTransaction[]) => {
      const result = await fetchAPI<{ case_id: string; updated: number }>(
        `/api/financial/ledger/payment-labels/remove?${new URLSearchParams({ case_id: caseId })}`,
        {
          method: "POST",
          body: {
            transactions: originals.map((item) => ({ id: item.key, version: (item.label_version ?? 0) + 1 })),
            fields: ["counterparty_name"],
          },
        }
      )
      if (result.case_id !== caseId || result.updated !== originals.length)
        throw Error("Not every name was confirmed as removed. Reload the transactions to see what is saved.")
      return originals
    },
    onSuccess: (originals) => {
      // The save and the removal each count one edit on the server.
      patchLedger(client, caseId, originals.map((item) => ({ ...item, label_version: (item.label_version ?? 0) + 2 })))
      void client.invalidateQueries({ queryKey: ["financial-ledger", caseId], refetchType: "none" })
      void client.invalidateQueries({ queryKey: ["ledger-source", caseId] })
      setLast(null)
      setOffer(null)
      toast.success(`Removed the name from ${originals.length} ${originals.length === 1 ? "payment" : "payments"}.`)
    },
  })
  const confirmedText = () =>
    `Confirmed by ${user?.name || user?.username || "you"} from the statement on ${new Date().toISOString().slice(0, 10)}. Read first by ${reading?.origin?.model || "Claude"}.`
  const confirm = useMutation({
    mutationFn: async ({ target, field }: { target: LedgerTransaction; field: "from_name" | "to_name" }) => {
      const result = await fetchAPI<{ case_id: string; confirmed: number; skipped: number }>(
        `/api/financial/ledger/payment-labels/confirm?${new URLSearchParams({ case_id: caseId })}`,
        {
          method: "POST",
          body: { transactions: [{ id: target.key, version: target.label_version ?? 0 }], fields: [field] },
        }
      )
      if (result.case_id !== caseId || result.confirmed !== 1)
        throw Error("The name was not confirmed. Reload the transactions to see what is saved.")
      return { target, field }
    },
    onSuccess: ({ target, field }) => {
      patchLedger(client, caseId, [withConfirmedName(target, field, confirmedText())])
      void client.invalidateQueries({ queryKey: ["financial-ledger", caseId], refetchType: "none" })
      void client.invalidateQueries({ queryKey: ["ledger-source", caseId] })
      setOffer(null)
    },
  })
  const busy = save.isPending || undo.isPending || confirm.isPending
  const submit = () => {
    const value = name.trim().replace(/\s+/g, " ")
    if (readOnly || !row) return
    if (readField && value && !busy && value === (row[readField] ?? "").trim()) {
      confirm.mutate({ target: row, field: readField }, { onSuccess: () => next && onMove(next) })
      return
    }
    if (!value || busy || row.counterparty_link) return
    // A correction is saved on the other side; a reading on the account's own side can only be confirmed here.
    if (readField && readField !== otherSide(row)) {
      setOwnSideNote(true)
      return
    }
    if (value === (row[otherSide(row)] ?? "").trim()) {
      if (next) onMove(next)
      return
    }
    const target = row
    save.mutate({ targets: [target], value }, { onSuccess: () => next && onMove(next) })
  }
  const keys = (event: KeyboardEvent<HTMLElement>) => {
    const typing = event.target === input.current && name.length > 0
    const inField = event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement
    if (event.key === "Escape") {
      event.preventDefault()
      onClose()
    } else if (event.key === "Enter" && event.target === input.current) {
      event.preventDefault()
      submit()
    } else if ((event.key === "ArrowRight" || event.key === "ArrowLeft") && (!typing || event.altKey) && (!inField || event.target === input.current)) {
      const target = event.key === "ArrowRight" ? next : previous
      if (target) {
        event.preventDefault()
        onMove(target)
      }
    } else if ((event.key === "s" || event.key === "S") && !inField && !event.ctrlKey && !event.metaKey) {
      if (next) {
        event.preventDefault()
        onMove(next)
      }
    }
  }
  const names = caseNames(rows)
  const reason = row ? missingNameReason(row) : null
  const incoming = row?.direction === "credit"
  return (
    <aside
      ref={panel}
      tabIndex={-1}
      aria-label={readOnly ? "Statement lines of payments without a name" : "Name payments from the statement"}
      className="finance-panel min-w-0 space-y-3 overflow-auto rounded-lg border p-4 outline-none xl:max-h-[calc(100vh-var(--naming-top)-8px)]"
      style={{ "--naming-top": `${stickyTop + 8}px` } as CSSProperties}
      data-finance-tone="info"
      onKeyDown={keys}
    >
      <header className="flex items-start justify-between gap-2">
        <div>
          <h2 className="font-semibold">
            {readOnly ? "Payment without a name" : confirming ? "Confirm what Claude read" : "Name this payment"}
          </h2>
          <p className="text-xs text-muted-foreground" role="status">
            {queue.length === 0
              ? confirming
                ? "Every name in view is confirmed by a person."
                : "Every payment in view has a name."
              : position >= 0
                ? `${position + 1} of ${queue.length} ${confirming ? "not confirmed" : "without a name"} in view`
                : `${queue.length} ${confirming ? "not confirmed" : "without a name"} in view`}
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={onClose}>
          Close (Esc)
        </Button>
      </header>
      {!row ? (
        <p role="status">This payment is not in the current view. Choose another payment or close this panel.</p>
      ) : (
        <>
          {offer && !readOnly && (
            <SimilarOffer
              offer={offer}
              busy={busy}
              onToggle={(id, on) =>
                setOffer((current) => {
                  if (!current) return current
                  const ticked = new Set(current.ticked)
                  if (on) ticked.add(id)
                  else ticked.delete(id)
                  return { ...current, ticked }
                })
              }
              onApply={() => {
                // The rows as they are now: one named meanwhile is left alone, and versions are current.
                const fresh = new Map(rows.map((item) => [item.key, item]))
                const targets = offer.groups
                  .flatMap((group) => group.rows)
                  .filter((item) => offer.ticked.has(item.key))
                  .map((item) => fresh.get(item.key))
                  .filter((item): item is LedgerTransaction => !!item && needsName(item))
                if (targets.length) save.mutate({ targets, value: offer.name, sameAs: offer.source.key })
              }}
              onDismiss={() => setOffer(null)}
            />
          )}
          <section aria-label="Payment to name" className="space-y-1 text-sm">
            <p className="flex flex-wrap items-baseline gap-x-3">
              <strong className="tabular-nums">
                {incoming ? "+" : "−"}
                {formatLedgerAmount(row.amount_minor, row.currency).text} {row.currency}
              </strong>
              <span>{row.account_type === "credit_card" ? (incoming ? "Card credit" : "Card charge") : incoming ? "Money in" : "Money out"}</span>
              <span>{row.ordering_date_context === "statement_end_ordering_only" ? `Date not printed (statement ends ${row.ordering_date})` : row.ordering_date}</span>
            </p>
            <p className="text-xs text-muted-foreground">{row.account_label || row.account_holder || row.account_id}</p>
            <p className="break-words font-mono text-[13px]">{row.description || "No description recorded"}</p>
            {reading?.source === "model_reading" ? (
              <p className="rounded border border-[#e7c66b] bg-[#fdf6dd] p-2 text-xs text-[#5c3d00] dark:bg-amber-950 dark:text-amber-100" data-testid="model-reading">
                <span className="font-semibold">{reading.label || "Read by Claude · not confirmed"}: </span>
                {row[readField as "from_name" | "to_name"]}
                {reading.explanation ? <span className="mt-1 block">{reading.explanation}</span> : null}
              </p>
            ) : (
            <p className="text-xs">
              <span className="font-semibold">Why there is no name: </span>
              {reason
                ? `${reason.reason}${reason.explanation ? `. ${reason.explanation}` : ""}`
                : row[otherSide(row)]
                  ? `Named ${row[otherSide(row)]}.`
                  : "The printed line does not give a name the ledger could read. Check the statement below."}
            </p>
            )}
          </section>
          <StatementView key={row.key} caseId={caseId} row={row} />
          {readOnly ? (
            <div className="space-y-2">
              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="outline" disabled={!previous} onClick={() => previous && onMove(previous)}>
                  ← Previous
                </Button>
                <Button type="button" variant="outline" disabled={!next} onClick={() => next && onMove(next)}>
                  Next →
                </Button>
                {onOpenDetails && (
                  <Button type="button" variant="ghost" onClick={() => onOpenDetails(row)}>
                    Payment details
                  </Button>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                You can view this case but not change it, so there is no name field. ← and → (or S) move between the
                payments without a name, Esc closes. Someone with edit access to the case can name them here.
              </p>
            </div>
          ) : (
          <form
            className="space-y-2"
            onSubmit={(event) => {
              event.preventDefault()
              submit()
            }}
          >
            <label className="block text-sm font-medium">
              {incoming ? "Who paid this account" : "Who was paid"}
              <input
                ref={input}
                autoFocus
                aria-label={incoming ? "Name who paid this account" : "Name who was paid"}
                list="payment-naming-names"
                maxLength={512}
                className="mt-1 block w-full rounded border bg-background p-2"
                placeholder="Type the name printed on the statement"
                value={name}
                disabled={busy || !!row.counterparty_link}
                onChange={(event) => {
                  setName(event.target.value)
                  setOwnSideNote(false)
                }}
              />
            </label>
            <datalist id="payment-naming-names">
              {names.map((item) => (
                <option key={item} value={item} />
              ))}
            </datalist>
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={busy || !name.trim()}>
                {save.isPending || confirm.isPending
                  ? "Saving…"
                  : readField && row && name.trim().replace(/\s+/g, " ") === (row[readField] ?? "").trim()
                    ? "Confirm and next (Enter)"
                    : "Save and next (Enter)"}
              </Button>
              <Button type="button" variant="outline" disabled={!previous || busy} onClick={() => previous && onMove(previous)}>
                ← Previous
              </Button>
              <Button type="button" variant="outline" disabled={!next || busy} onClick={() => next && onMove(next)}>
                Skip (S)
              </Button>
              <Button type="button" variant="outline" disabled={!next || busy} onClick={() => next && onMove(next)}>
                Next →
              </Button>
              {onOpenDetails && (
                <Button type="button" variant="ghost" onClick={() => onOpenDetails(row)}>
                  Payment details
                </Button>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              {confirming
                ? "Check the name against the statement line. Enter on the name as read confirms it as yours; change it first to save your correction instead. Claude's reading stays in the payment's history. S skips when the cursor is outside the field, Esc closes; nothing else about the payment changes."
                : "Enter saves and opens the next payment without a name. ← and → move between them when the name field is empty, S skips when the cursor is outside the field, Esc closes. The name is saved as yours, marked as read from the statement; nothing else about the payment changes."}
            </p>
          </form>
)}
          {confirm.isError && (
            <p role="alert" className="text-sm">
              {confirm.error.message}
            </p>
          )}
          {ownSideNote && (
            <p role="alert" className="text-sm">
              This name is on the account's own side of the payment: here it can only be confirmed as Claude read it. Put
              the name back as read to confirm it; a different name for this side is not saved from this panel.
            </p>
          )}
          {save.isError && (
            <p role="alert" className="text-sm">
              {save.error.message}{" "}
              <button
                className="underline"
                onClick={() => {
                  save.reset()
                  void client.invalidateQueries({ queryKey: ["financial-ledger", caseId] })
                }}
              >
                Reload transactions
              </button>
            </p>
          )}
        </>
      )}
      {last && !readOnly && (
        <p className="flex flex-wrap items-center gap-2 border-t pt-2 text-sm" aria-label="Last saved name">
          Saved “{last.name}” on {last.originals.length} {last.originals.length === 1 ? "payment" : "payments"}.
          <Button size="sm" variant="outline" disabled={busy} onClick={() => undo.mutate(last.originals)}>
            {undo.isPending ? "Removing…" : "Undo"}
          </Button>
        </p>
      )}
      {undo.isError && (
        <p role="alert" className="text-sm">
          {undo.error.message}
        </p>
      )}
    </aside>
  )
}

function SimilarOffer({
  offer,
  busy,
  onToggle,
  onApply,
  onDismiss,
}: {
  offer: { source: LedgerTransaction; name: string; groups: SimilarGroup[]; ticked: Set<string> }
  busy: boolean
  onToggle: (id: string, on: boolean) => void
  onApply: () => void
  onDismiss: () => void
}) {
  const total = offer.groups.reduce((sum, group) => sum + group.rows.length, 0)
  const ticked = offer.ticked.size
  return (
    <section aria-label="Similar payments" className="space-y-2 rounded-md border border-[#c9d8f5] bg-[#e6efff] p-3 text-sm text-[#16213a]">
      <p className="font-semibold">
        Also name {total} similar {total === 1 ? "payment" : "payments"} “{offer.name}”?
      </p>
      <p className="text-xs">Tick the ones that are the same party. Nothing is saved until you choose Apply.</p>
      {offer.groups.map((group) => (
        <fieldset key={group.key} className="space-y-1">
          <legend className="text-xs font-semibold">
            {group.label} · {group.rows.length}
          </legend>
          <ul className="max-h-40 space-y-1 overflow-auto">
            {group.rows.map((item) => (
              <li key={item.key}>
                <label className="flex items-start gap-2">
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    aria-label={`Also name ${item.description || item.ref_id} on ${item.ordering_date}`}
                    checked={offer.ticked.has(item.key)}
                    onChange={(event) => onToggle(item.key, event.target.checked)}
                  />
                  <span className="min-w-0 break-words">
                    {item.ordering_date} · {formatLedgerAmount(item.amount_minor, item.currency).text} {item.currency} ·{" "}
                    <span className="font-mono text-[12px]">{item.description}</span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </fieldset>
      ))}
      <div className="flex gap-2">
        <Button size="sm" disabled={busy || !ticked} onClick={onApply}>
          Apply to {ticked} {ticked === 1 ? "payment" : "payments"}
        </Button>
        <Button size="sm" variant="outline" disabled={busy} onClick={onDismiss}>
          Not now
        </Button>
      </div>
    </section>
  )
}

/** The payment's line on its statement page, highlighted and zoomed, with the next page's top when it may continue. */
function StatementView({ caseId, row }: { caseId: string; row: LedgerTransaction }) {
  const meta = useQuery(pageQuery(caseId, row.key))
  const [viewFile, setViewFile] = useState(false)
  const [zoom, setZoom] = useState(200)
  const data = meta.data
  const band = data ? lineBand(data.locator) : null
  const page = data?.page ?? null
  return (
    <section aria-label="Statement line" className="space-y-2">
      {meta.isPending && <p role="status" className="text-xs">Loading the statement page…</p>}
      {meta.isError && (
        <p role="alert" className="text-xs">
          The statement page could not be loaded. {meta.error.message}{" "}
          <button className="underline" onClick={() => void meta.refetch()}>
            Try again
          </button>
        </p>
      )}
      {data && page === null && (
        <p className="text-xs">No page is stored for this payment. Open the statement file to find it.</p>
      )}
      {data && page !== null && (
        <>
          <div className="flex flex-wrap items-center gap-2 text-xs" role="group" aria-label="Statement zoom">
            <span>
              Page {page}
              {data.page_count ? ` of ${data.page_count}` : ""} · {data.filename}
            </span>
            <Button size="sm" variant="outline" aria-label="Zoom statement out" disabled={zoom <= 100} onClick={() => setZoom((z) => Math.max(100, z - 50))}>
              −
            </Button>
            <span aria-live="polite">{zoom}%</span>
            <Button size="sm" variant="outline" aria-label="Zoom statement in" disabled={zoom >= 400} onClick={() => setZoom((z) => Math.min(400, z + 50))}>
              +
            </Button>
          </div>
          {band ? (
            <>
              <PageImage caseId={caseId} id={row.key} page={page} zoom={zoom} band={band} height={300} label={`Statement page ${page}, this payment highlighted`} />
              {showNextPageTop(band, data.last_on_page, data.page_count) && (
                <div className="space-y-1">
                  <p className="text-xs font-medium">Top of page {page + 1}: the line may continue here</p>
                  <PageImage caseId={caseId} id={row.key} page={page + 1} zoom={zoom} height={170} left={band.left} label={`Top of statement page ${page + 1}`} />
                </div>
              )}
            </>
          ) : (
            <>
              <p className="text-xs">
                {data.found.length
                  ? `The exact line was not stored. The amount and date found on this page are marked: ${data.found.filter((f) => f.kind === "amount").length} amount, ${data.found.filter((f) => f.kind === "date").length} date.`
                  : data.text_layer === false
                    ? "The exact line was not stored and this page is a scanned image, so the amount could not be searched. The whole page is shown."
                    : "The exact line was not stored and the amount was not found printed on this page. The whole page is shown."}
              </p>
              <PageImage caseId={caseId} id={row.key} page={page} zoom={Math.max(100, zoom - 100)} found={data.found} height={480} label={`Statement page ${page}`} />
            </>
          )}
          <Button size="sm" variant="outline" onClick={() => setViewFile(true)}>
            Open full page / file
          </Button>
          <DocumentViewer
            caseId={caseId}
            evidenceId={data.evidence_file_id}
            open={viewFile}
            onOpenChange={setViewFile}
            documentUrl={evidenceAPI.getFileUrl(data.evidence_file_id)}
            documentName={data.filename}
            initialPage={page}
            navigationKey={`${caseId}:${row.key}:naming`}
          />
        </>
      )}
    </section>
  )
}

/** One rendered page in a scrolling window, scrolled to the highlighted line (or the first found amount). */
export function PageImage({
  caseId,
  id,
  page,
  zoom,
  height,
  label,
  band,
  left,
  found = [],
}: {
  caseId: string
  id: string
  page: number
  zoom: number
  height: number
  label: string
  band?: LineBand
  left?: number
  found?: StatementPage["found"]
}) {
  const image = useProtectedObjectUrl(statementImageUrl(caseId, id, page))
  const viewport = useRef<HTMLDivElement>(null)
  const amount = found.find((f) => f.kind === "amount")
  const focusBox = band ?? (amount ? { top: amount.rect[1], bottom: amount.rect[3] } : null)
  const focus = () => {
    const node = viewport.current
    const content = node?.firstElementChild as HTMLElement | null
    if (!node || !content) return
    node.scrollLeft = Math.max(0, content.offsetWidth * ((band?.left ?? left ?? 0) - 0.01))
    node.scrollTop = focusBox ? Math.max(0, content.offsetHeight * ((focusBox.top + focusBox.bottom) / 2) - node.clientHeight * 0.4) : 0
  }
  // Scroll to the line when the page arrives or the zoom changes, not on every keystroke in the name field.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useLayoutEffect(focus, [zoom, image.objectUrl])
  if (image.error)
    return (
      <p role="alert" className="text-xs">
        Page {page} could not be loaded. Use Open full page / file.
      </p>
    )
  const crop = band ? cropWindow(band) : null
  return (
    <div
      ref={viewport}
      role="region"
      aria-label={label}
      tabIndex={0}
      className="overflow-auto rounded border bg-white"
      style={{ height }}
    >
      <div className="relative" style={{ width: `${zoom}%` }}>
        {image.objectUrl ? (
          <img src={image.objectUrl} alt={label} className="block w-full" onLoad={focus} />
        ) : (
          <p role="status" className="p-3 text-xs text-muted-foreground">
            Loading page {page}…
          </p>
        )}
        {image.objectUrl && crop && band && (
          <>
            <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 bg-black/10" style={{ top: 0, height: `${crop.top * 100}%` }} />
            <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 bg-black/10" style={{ top: `${crop.bottom * 100}%`, bottom: 0 }} />
            <div
              data-testid="statement-line-highlight"
              aria-hidden="true"
              className="pointer-events-none absolute rounded-sm border-2 border-[#e0a100] bg-[#ffd54a]/30"
              style={{
                top: `${band.top * 100}%`,
                height: `${(band.bottom - band.top) * 100}%`,
                left: `${band.left * 100}%`,
                width: `${(band.right - band.left) * 100}%`,
              }}
            />
          </>
        )}
        {image.objectUrl &&
          found.map((box, index) => (
            <div
              key={index}
              data-testid={`statement-found-${box.kind}`}
              aria-hidden="true"
              title={box.kind === "amount" ? `Amount ${box.text}` : `Date ${box.text}`}
              className={`pointer-events-none absolute rounded-sm border-2 ${box.kind === "amount" ? "border-[#e0a100] bg-[#ffd54a]/30" : "border-[#3a6fd8] bg-[#3a6fd8]/15"}`}
              style={{
                left: `${box.rect[0] * 100}%`,
                top: `${box.rect[1] * 100}%`,
                width: `${(box.rect[2] - box.rect[0]) * 100}%`,
                height: `${(box.rect[3] - box.rect[1]) * 100}%`,
              }}
            />
          ))}
      </div>
    </div>
  )
}
