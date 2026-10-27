import { createContext, useContext, useMemo, useState, type ReactNode } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { judgementKeys, useJudgements } from "../hooks/use-judgements"
import { Lightbulb } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { useFinancialAccess } from "../hooks/use-financial-access"
import {
  confirmJudgement,
  correctJudgement,
  countLine,
  statusLabel,
  strengthHelp,
  strengthLabel,
  type Judgement,
} from "../lib/judgements"
import type { LedgerTransaction } from "../api"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"

/**
 * The judgements on payment rows of the statement being shown, keyed by transaction id. The ledger table reads
 * this to put a marker under the payment's description; outside a provider it shows nothing.
 */
const RowJudgements = createContext<{
  caseId: string
  byTransaction: Map<string, Judgement[]>
  onCorrect?: (judgement: Judgement, transaction: LedgerTransaction) => void
} | null>(null)

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
    return { caseId, byTransaction, onCorrect }
  }, [caseId, query.data, onCorrect])
  return <RowJudgements.Provider value={value}>{children}</RowJudgements.Provider>
}

/** Under a payment's description: its judgement calls, if any. */
export function RowJudgementMarkers({ transaction }: { transaction: LedgerTransaction }) {
  const context = useContext(RowJudgements)
  const items = context?.byTransaction.get(transaction.key)
  if (!context || !items?.length) return null
  return (
    <div className="mt-1 space-y-1">
      {items.map((judgement) => (
        <JudgementMarker
          key={judgement.id}
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
}: {
  caseId: string
  judgement: Judgement
  onCorrect?: (judgement: Judgement) => void
  defaultOpen?: boolean
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
  return (
    <div className="text-xs" data-testid="judgement-marker" data-judgement-id={judgement.id}>
      <button
        type="button"
        className="inline-flex items-center gap-1"
        aria-expanded={open}
        title={`${judgement.rule_label}. ${strengthHelp(judgement)}`}
        onClick={() => setOpen(!open)}
      >
        <Badge
          variant={
            judgement.status === "corrected"
              ? "danger"
              : judgement.status === "confirmed"
                ? "success"
                : judgement.strength === "inferred"
                  ? "warning"
                  : "info"
          }
        >
          <Lightbulb aria-hidden="true" />
          {settled ? statusLabel(judgement) : strengthLabel(judgement)}
        </Badge>
        <span className="text-muted-foreground">{judgement.rule_label}</span>
      </button>
      {open && (
        <div
          role="region"
          aria-label="Judgement call"
          className="mt-1 max-w-xl space-y-2 rounded border bg-background p-2"
        >
          <p className="text-sm">{judgement.summary}</p>
          <p className="text-muted-foreground">
            {strengthHelp(judgement)}
            {judgement.origin === "agent" ? " Entered by the processing agent, not read automatically." : ""}
          </p>
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
          <p className="text-muted-foreground" title={`${judgement.rule_id} · ${judgement.rule_source}`}>
            Rule: {judgement.rule_label}
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

