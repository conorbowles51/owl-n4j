import { useState, type ReactNode } from "react"
import type { LedgerTransaction } from "../api"
import { useFinancialDraft } from "../stores/financial-drafts"
import {
  allocateReceipts,
  flowRows,
  impliedExchangeRate,
  receiptCluster,
  type FlowMethod,
} from "../lib/money-flow-scenarios"
import { minorAmount, paymentDay } from "../lib/investigator-workspace"
import { correctionMoney } from "../lib/correction-contract"
import { InvestigatorFindingEditor } from "./InvestigatorFindingEditor"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { Button } from "@/components/ui/button"

const money = (
  row: LedgerTransaction,
  amount = minorAmount(row.amount_minor)!
) => correctionMoney(amount.toString(), row.currency)
const label = (row: LedgerTransaction) =>
  `${paymentDay(row)} · ${row.description || row.ref_id} · ${money(row)} · ${row.account_label || row.account_id}`
export function MoneyFlowExplorer({
  caseId,
  rows,
  overview,
  onOpen,
}: {
  caseId: string
  rows: LedgerTransaction[]
  overview: ReactNode
  onOpen: (ids: string[], title: string) => void
}) {
  const [view, setView] = useFinancialDraft(
    caseId,
    "investigator-follow-money:concept",
    {
      concept: "overview",
      method: "fifo",
      receipt: "",
      sent: "",
      received: "",
      days: 7,
      basis: "",
      acknowledged: false,
    }
  )
  const change = (next: Partial<typeof view>) => setView({ ...view, ...next })
  const [saving, setSaving] = useState(false)
  const { canEdit } = useFinancialAccess()
  const eligible = flowRows(rows),
    credits = eligible.filter((r) => r.direction === "credit"),
    debits = eligible.filter((r) => r.direction === "debit")
  const receipt = credits.find((r) => r.key === view.receipt),
    sent = debits.find((r) => r.key === view.sent),
    received = credits.find((r) => r.key === view.received)
  const method = (
    view.concept === "lifo"
      ? "lifo"
      : view.concept === "fifo"
        ? "fifo"
        : view.method
  ) as FlowMethod
  const allocation = allocateReceipts(eligible, method)
  const selectedReceipt = view.concept === "fx" ? received : receipt
  const routes = allocation.allocations.filter(
    (a) => a.receipt.key === selectedReceipt?.key
  )
  const cluster = receipt ? receiptCluster(eligible, receipt, view.days) : []
  const fxRate = sent && received ? impliedExchangeRate(sent, received) : null
  const valid = view.concept === "fx" ? !!fxRate : !!receipt
  const applicable =
    view.concept === "cluster" ? cluster : routes.map((r) => r.payment)
  const calculationInputs =
    selectedReceipt && view.concept !== "cluster"
      ? eligible.filter(
          (row) =>
            row.account_id === selectedReceipt.account_id &&
            row.currency === selectedReceipt.currency
        )
      : []
  const supporting = [
    ...new Set([
      ...(selectedReceipt ? [selectedReceipt.key] : []),
      ...(view.concept === "fx" && sent ? [sent.key] : []),
      ...applicable.map((r) => r.key),
      ...calculationInputs.map((r) => r.key),
    ]),
  ]
  const select = (
    title: string,
    value: string,
    choices: LedgerTransaction[],
    onChange: (v: string) => void
  ) => (
    <label className="block text-sm">
      {title}
      <select
        className="mt-1 block w-full rounded border bg-background p-2"
        aria-label={title}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">Choose a transaction</option>
        {choices.map((r) => (
          <option key={r.key} value={r.key}>
            {label(r)}
          </option>
        ))}
      </select>
    </label>
  )
  const explanation =
    view.concept === "cluster"
      ? "Timing comparison: all smaller outgoing payments in this account and currency within the chosen window. A payment can appear in several receipt comparisons. These are candidates to investigate, not allocated or confirmed uses of that receipt."
      : `Conditional ${method.toUpperCase()} allocation: ${method === "fifo" ? "oldest" : "most recent"} available receipts are used first. This scenario assumes zero opening funds before the first imported payment in each account and currency. Same-day entries use source document and row order; that order may differ from the bank’s actual sequence. Missing records or opening funds can change the allocation.`
  const narrative = [
    explanation,
    view.concept === "fx" && sent && received
      ? `Selected exchange hypothesis: ${label(sent)} → ${label(received)}. Implied rate: 1 ${sent.currency} ≈ ${fxRate} ${received.currency}; derived from these recorded amounts, not a verified FX quote. Fees or other differences have not been assumed away.`
      : "",
    selectedReceipt ? `Receipt: ${label(selectedReceipt)}` : "",
    ...applicable.map(
      (r, i) =>
        `${label(r)}${view.concept !== "cluster" ? ` · ${money(r, routes[i].amount)} allocated under ${method.toUpperCase()}` : ""}`
    ),
    calculationInputs.length
      ? `Calculation input order (all scoped dated bank payments, including competing receipts and withdrawals):\n${calculationInputs.map((r) => `${r.key} · ${label(r)} · ${r.direction}`).join("\n")}`
      : "",
    `Investigator basis: ${view.basis}`,
  ]
    .filter(Boolean)
    .join("\n\n")
  return (
    <section aria-label="Money flow method" className="space-y-4">
      <div className="rounded-xl border bg-card p-4 space-y-3">
        <label className="block font-medium">
          What do you want to follow?
          <select
            aria-label="Money flow concept"
            className="mt-1 block w-full rounded border bg-background p-2"
            value={view.concept}
            onChange={(e) =>
              change({ concept: e.target.value, acknowledged: false })
            }
          >
            <option value="overview">
              Who paid in and out · recorded connections
            </option>
            <option value="fifo">First in, first out (FIFO)</option>
            <option value="lifo">Last in, first out (LIFO)</option>
            <option value="cluster">
              One receipt followed by several smaller payments
            </option>
            <option value="fx">Follow a transfer across currencies</option>
          </select>
        </label>
        {view.concept !== "overview" && (
          <>
            <p className="text-sm">{explanation}</p>
            <p className="text-sm text-muted-foreground">
              {rows.length - eligible.length} card, undated or unusable entries
              excluded. Calculations keep accounts and currencies separate.
            </p>
            {view.concept === "fx" ? (
              <>
                <p className="text-sm">
                  Choose the outgoing payment and the receipt you believe
                  represents its conversion. Loupe shows the rate implied by
                  those two amounts, then follows the received currency onwards.
                  Both original currencies remain visible. Add the reference or
                  evidence supporting the link before saving.
                </p>
                {select(
                  "Outgoing payment before conversion",
                  view.sent,
                  debits,
                  (v) => change({ sent: v })
                )}
                {select(
                  "Receipt after conversion",
                  view.received,
                  credits.filter(
                    (r) =>
                      !sent ||
                      (r.currency !== sent.currency &&
                        paymentDay(r)! >= paymentDay(sent)!)
                  ),
                  (v) => change({ received: v })
                )}
                <label className="block text-sm">
                  Onward allocation method
                  <select
                    className="ml-2 rounded border bg-background p-2"
                    value={view.method}
                    onChange={(e) => change({ method: e.target.value })}
                  >
                    <option value="fifo">FIFO · oldest receipt first</option>
                    <option value="lifo">LIFO · newest receipt first</option>
                  </select>
                </label>
                {sent && received && !fxRate && (
                  <p role="alert">
                    Choose different currencies with a receipt dated on or after
                    the outgoing payment.
                  </p>
                )}
                {fxRate && (
                  <p className="rounded border bg-muted/30 p-3 font-medium">
                    {money(sent!)} → {money(received!)} · Implied rate: 1{" "}
                    {sent!.currency} ≈ {fxRate} {received!.currency}. This ratio
                    may include fees; it is not a verified exchange rate.
                  </p>
                )}
              </>
            ) : (
              select("Receipt to follow", view.receipt, credits, (v) =>
                change({ receipt: v })
              )
            )}
            {view.concept === "cluster" && (
              <label className="block text-sm">
                Look ahead
                <select
                  aria-label="Cluster days"
                  className="ml-2 rounded border bg-background p-2"
                  value={view.days}
                  onChange={(e) => change({ days: Number(e.target.value) })}
                >
                  {[1, 3, 7, 14, 30].map((n) => (
                    <option key={n} value={n}>
                      {n} days
                    </option>
                  ))}
                </select>
              </label>
            )}
            {view.concept !== "cluster" && (
              <label className="flex gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={view.acknowledged}
                  onChange={(e) => change({ acknowledged: e.target.checked })}
                />
                Use the zero-opening and same-day source-order assumptions
                stated above.
              </label>
            )}
            {valid && (view.concept === "cluster" || view.acknowledged) && (
              <section
                aria-label="Money flow results"
                className="space-y-3 border-t pt-3"
              >
                <h3 className="font-semibold">
                  {view.concept === "cluster"
                    ? `${cluster.length} smaller payments to compare`
                    : `${routes.length} onward payments under ${method.toUpperCase()}`}
                </h3>
                <p className="text-sm">
                  {view.concept === "cluster"
                    ? `Combined outgoing amounts: ${money(
                        receipt!,
                        cluster.reduce(
                          (s, r) => s + minorAmount(r.amount_minor)!,
                          0n
                        )
                      )}. Receipt: ${money(receipt!)}. The difference alone does not establish a connection.`
                    : `Allocated from this receipt: ${money(
                        selectedReceipt!,
                        routes.reduce((s, r) => s + r.amount, 0n)
                      )}. Remaining from this receipt in this scenario: ${money(selectedReceipt!, minorAmount(selectedReceipt!.amount_minor)! - routes.reduce((s, r) => s + r.amount, 0n))}.`}
                </p>
                <div className="max-h-80 overflow-auto rounded border">
                  {applicable.map((r, i) => (
                    <button
                      key={r.key}
                      className="block w-full border-b p-3 text-left text-sm hover:bg-muted"
                      onClick={() =>
                        onOpen(
                          [
                            selectedReceipt!.key,
                            r.key,
                            ...(sent && view.concept === "fx"
                              ? [sent.key]
                              : []),
                          ],
                          "Payments supporting this flow"
                        )
                      }
                    >
                      <strong>{r.description || r.ref_id}</strong>
                      <span className="block">
                        {paymentDay(r)} · Outgoing {money(r)}
                        {view.concept !== "cluster"
                          ? ` · Allocated ${money(r, routes[i].amount)}`
                          : ""}
                      </span>
                      <span className="text-primary">
                        Open payments and originals →
                      </span>
                    </button>
                  ))}
                </div>
                {!applicable.length && (
                  <p>
                    No matching onward payments in the imported records and
                    selected filters. This does not establish that the money
                    remained in the account.
                  </p>
                )}
                {view.concept !== "cluster" && (
                  <p className="text-sm">
                    {
                      allocation.unfunded.filter(
                        (r) =>
                          r.payment.account_id ===
                            selectedReceipt!.account_id &&
                          r.payment.currency === selectedReceipt!.currency
                      ).length
                    }{" "}
                    withdrawals in this account exceed preceding imported
                    receipts in the zero-opening scenario. Their unexplained
                    funding is kept outside these allocations.
                  </p>
                )}
                <label className="block text-sm">
                  Basis for this interpretation
                  <textarea
                    aria-label="Flow interpretation basis"
                    className="mt-1 block w-full rounded border bg-background p-2"
                    value={view.basis}
                    onChange={(e) => change({ basis: e.target.value })}
                  />
                </label>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    onClick={() =>
                      onOpen(supporting, "Payments supporting this flow")
                    }
                  >
                    Review supporting payments
                  </Button>
                  {canEdit && (
                    <Button
                      disabled={!view.basis.trim()}
                      onClick={() => setSaving(true)}
                    >
                      Save flow as observation
                    </Button>
                  )}
                </div>
              </section>
            )}
          </>
        )}
      </div>
      {view.concept === "overview" && overview}
      {saving && (
        <InvestigatorFindingEditor
          caseId={caseId}
          ids={supporting}
          initial={{
            kind: "question",
            title:
              view.concept === "fx"
                ? "Cross-currency flow to investigate"
                : view.concept === "cluster"
                  ? "Receipt and smaller payments to investigate"
                  : `${method.toUpperCase()} receipt allocation`,
            explanation: narrative,
          }}
          draftContext={narrative}
          onClose={() => setSaving(false)}
        />
      )}
    </section>
  )
}
