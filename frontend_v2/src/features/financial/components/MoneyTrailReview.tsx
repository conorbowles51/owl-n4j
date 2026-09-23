import { useState } from "react"
import { randomRequestId } from "@/lib/browser-crypto"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { fetchAPI } from "@/lib/api-client"
import { financialAPI, type LedgerTransaction } from "../api"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { useFinancialDraft } from "../stores/financial-drafts"
import { correctionMinor, correctionMoney } from "../lib/correction-contract"
import {
  savedTrail,
  savedTrails,
  trailPreview,
  trailNarrative,
  type SavedTrail,
  type TrailPreview,
} from "../lib/money-trails"
import { LedgerSourceDialog } from "./LedgerSourceDialog"
import { InvestigatorFindingEditor } from "./InvestigatorFindingEditor"
import { AccountOwnershipReview } from "./AccountOwnershipReview"
import { AddToTimelineDialog } from "@/features/timeline/components/AddToTimelineDialog"

type Draft = {
  id: string
  revision: number
  kind: "transfer" | "allocation"
  debit: string
  credit: string
  payments: Record<string, string>
  fx: boolean
  reason: string
  reference: boolean
  bank: string
  identifier: string
  holder: string
}
const paymentLabel = (
  p: Pick<
    LedgerTransaction,
    | "ordering_date"
    | "description"
    | "ref_id"
    | "amount_minor"
    | "currency"
    | "account_id"
  > & { account_label?: string | null }
) =>
  `${p.ordering_date} · ${p.description || p.ref_id} · ${correctionMoney(String(p.amount_minor), p.currency)} · ${p.account_label || p.account_id}`

export function MoneyTrailReview({
  caseId,
  transactionIds = [],
  label = "Review saved transfers and money trails",
  initialOpen = false,
  trailId,
  onClose,
}: {
  caseId: string
  transactionIds?: string[]
  label?: string
  initialOpen?: boolean
  trailId?: string
  onClose?: () => void
}) {
  const [open, setOpen] = useState(initialOpen)
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) onClose?.()
      }}
    >
      {!initialOpen && (
        <DialogTrigger asChild>
          <Button variant="outline">{label}</Button>
        </DialogTrigger>
      )}
      <DialogContent className="sm:max-w-4xl max-h-[90dvh] overflow-auto">
        <DialogHeader>
          <DialogTitle>Transfers and money trails</DialogTitle>
          <DialogDescription>
            Link the two statement entries of a transfer, then record any
            allocation to later payments. Saved links stay with this case.
          </DialogDescription>
        </DialogHeader>
        {open && (
          <TrailEditor
            caseId={caseId}
            transactionIds={transactionIds}
            trailId={trailId}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function TrailEditor({
  caseId,
  transactionIds,
  trailId,
}: {
  caseId: string
  transactionIds: string[]
  trailId?: string
}) {
  const { canEdit } = useFinancialAccess()
  const client = useQueryClient()
  const [id] = useState(randomRequestId)
  const [search, setSearch] = useState("")
  const [chooserLimit, setChooserLimit] = useState(200)
  const [source, setSource] = useState<string | null>(null)
  const [timeline, setTimeline] = useState<SavedTrail | null>(null)
  const [finding, setFinding] = useState<{
    trail: SavedTrail
    kind: "observation" | "question"
  } | null>(null)
  const [preview, setPreview] = useState<TrailPreview | null>(null)
  const [receipt, setReceipt] = useState<SavedTrail | null>(null)
  const [removing, setRemoving] = useState<SavedTrail | null>(null)
  const [removeReason, setRemoveReason] = useState("")
  const [draft, setDraft] = useFinancialDraft<Draft>(
    caseId,
    `money-trail-review:${[...transactionIds].sort().join(":")}`,
    {
      id,
      revision: 0,
      kind: "transfer",
      debit: "",
      credit: "",
      payments: {},
      fx: false,
      reason: "",
      reference: false,
      bank: "",
      identifier: "",
      holder: "",
    }
  )
  const qs = new URLSearchParams({ case_id: caseId })
  const url = `/api/financial/money-trails?${qs}`
  const key = ["financial-ledger", caseId, "money-trails"]
  const trails = useQuery({
    queryKey: key,
    queryFn: async () => {
      const result = savedTrails.parse(await fetchAPI(url))
      if (result.case_id !== caseId)
        throw Error("The saved trails belong to another case.")
      return result
    },
    retry: false,
  })
  const ledger = useQuery({
    queryKey: ["financial-ledger", caseId, "money-trail-all-payments"],
    queryFn: async () => {
      const result = await financialAPI.getLedgerTransactions({ caseId })
      if (
        result.case_id !== caseId ||
        result.total !== result.transactions.length ||
        result.transactions.some((p) => p.case_id !== caseId)
      )
        throw Error("The complete case payment list could not be loaded.")
      return result.transactions.filter((p) => p.account_type !== "credit_card")
    },
    retry: false,
  })
  const rows = ledger.data ?? []
  const patch = (p: Partial<Draft>) => {
    setDraft((d) => ({ ...d, ...p }))
    setPreview(null)
    setReceipt(null)
  }
  const changed = () =>
    client.invalidateQueries({ queryKey: ["financial-ledger", caseId] })
  const body = () => ({
    id: draft.id,
    expected_revision: draft.revision,
    kind: draft.kind,
    debit_id: draft.kind === "transfer" ? draft.debit || null : null,
    credit_id: draft.credit || null,
    reason: draft.reason,
    allow_fx: draft.kind === "transfer" && draft.fx,
    referenced_account:
      draft.kind === "transfer" && draft.reference
        ? {
            institution: draft.bank,
            identifier: draft.identifier,
            holder: draft.holder || null,
          }
        : null,
    payments:
      draft.kind === "allocation"
        ? Object.entries(draft.payments).map(([transaction_id, value]) => ({
            transaction_id,
            amount_minor:
              correctionMinor(
                value,
                rows.find((p) => p.key === transaction_id)?.currency || ""
              ) || "invalid",
          }))
        : [],
  })
  const assess = useMutation({
    mutationFn: async () => {
      const result = trailPreview.parse(
        await fetchAPI(`/api/financial/money-trails/preview?${qs}`, {
          method: "POST",
          body: body(),
        })
      )
      if (result.case_id !== caseId)
        throw Error("The preview belongs to another case.")
      return result
    },
    onSuccess: setPreview,
    retry: false,
  })
  const save = useMutation({
    mutationFn: async () => {
      if (!preview || !canEdit) throw Error("Review the preview before saving.")
      const result = savedTrail.parse(
        await fetchAPI(url, {
          method: "POST",
          body: {
            ...body(),
            expected_source_revision: preview.source_revision,
          },
        })
      )
      if (result.case_id !== caseId || result.id !== draft.id)
        throw Error("The saved trail could not be confirmed.")
      return result
    },
    onSuccess: async (result) => {
      setReceipt(result)
      setPreview(null)
      setDraft((d) => ({ ...d, revision: result.revision }))
      await changed()
    },
    retry: false,
  })
  const remove = useMutation({
    mutationFn: async () => {
      if (!removing) throw Error("Choose a saved link.")
      return savedTrail.parse(
        await fetchAPI(
          `/api/financial/money-trails/${removing.id}/remove?${qs}`,
          {
            method: "POST",
            body: {
              expected_revision: removing.revision,
              reason: removeReason,
            },
          }
        )
      )
    },
    onSuccess: async () => {
      setRemoving(null)
      setRemoveReason("")
      await changed()
    },
    retry: false,
  })
  const busy = save.isPending || assess.isPending || remove.isPending
  const choose = (
    title: string,
    value: string,
    direction: string,
    change: (value: string) => void
  ) => {
    const visible = rows.filter(
      (p) =>
        p.direction === direction &&
        (p.key === value ||
          paymentLabel(p).toLowerCase().includes(search.toLowerCase()))
    )
    return (
      <label className="block">
        {title}
        <select
          className="block w-full rounded border bg-background p-2"
          value={value}
          onChange={(e) => change(e.target.value)}
        >
          <option value="">Choose a payment</option>
          {value && !rows.some((p) => p.key === value) && (
            <option value={value}>
              Earlier reading is unavailable — choose its current payment
            </option>
          )}
          {visible
            .filter((p, i) => i < chooserLimit || p.key === value)
            .map((p) => (
              <option key={p.key} value={p.key}>
                {paymentLabel(p)}
              </option>
            ))}
        </select>
        {visible.length > chooserLimit && (
          <span>
            Showing the first {chooserLimit} of {visible.length} matches. Refine
            the search or{" "}
            <button
              type="button"
              className="underline"
              onClick={() => setChooserLimit((n) => n + 200)}
            >
              show 200 more
            </button>
            .
          </span>
        )}
      </label>
    )
  }
  const loadSaved = (trail: SavedTrail) => {
    const input = trail.details.input as {
      debit_id?: string
      credit_id?: string
      payments: { transaction_id: string; amount_minor: string }[]
      allow_fx: boolean
      reason: string
      referenced_account?: {
        institution: string
        identifier: string
        holder?: string
      }
    }
    patch({
      id: trail.id,
      revision: trail.revision,
      kind: trail.kind,
      debit: input.debit_id || "",
      credit: input.credit_id || "",
      fx: input.allow_fx,
      reason: input.reason,
      payments: Object.fromEntries(
        (input.payments || []).map((p) => [
          p.transaction_id,
          correctionMoney(
            p.amount_minor,
            trail.details.payments.find((r) => r.key === p.transaction_id)!
              .currency
          ).split(" ")[0],
        ])
      ),
      reference: !!input.referenced_account,
      bank: input.referenced_account?.institution || "",
      identifier: input.referenced_account?.identifier || "",
      holder: input.referenced_account?.holder || "",
    })
    document
      .getElementById(`trail-editor-${id}`)
      ?.scrollIntoView({ block: "start", behavior: "smooth" })
  }
  const showSaved = (trail: SavedTrail) => (
    <div key={trail.id} className="rounded border p-3 space-y-2">
      <h4 className="font-semibold">
        {trail.kind === "allocation"
          ? "Onward allocation"
          : trail.details.internal_transfer
            ? "Internal transfer — reviewed common holder"
            : "Transfer between accounts"}
      </h4>
      {trail.status === "source_changed" && (
        <p role="alert">
          Source changed — review this trail. Its saved explanation and original
          readings remain below.
        </p>
      )}
      <p>{String(trail.details.input.reason)}</p>
      {trail.details.payments.map((p) => (
        <Button
          key={p.key}
          variant="outline"
          className="h-auto whitespace-normal text-left"
          onClick={() => setSource(p.key)}
        >
          {paymentLabel(p)}
        </Button>
      ))}
      {trail.details.implied_exchange_rate && (
        <p>
          Implied exchange rate: {trail.details.implied_exchange_rate}. Both
          original currency amounts are retained.
        </p>
      )}
      {trail.details.warnings.map((w) => (
        <p key={w} className="text-muted-foreground">
          {w}
        </p>
      ))}
      <div className="flex flex-wrap gap-2">
        {canEdit && (
          <>
            <Button variant="outline" onClick={() => loadSaved(trail)}>
              Review or edit link
            </Button>
            {trail.kind === "transfer" && trail.details.input.credit_id && (
              <Button
                onClick={() => {
                  patch({
                    id: randomRequestId(),
                    revision: 0,
                    kind: "allocation",
                    credit: String(trail.details.input.credit_id),
                    debit: "",
                    payments: {},
                    reason: "",
                    fx: false,
                    reference: false,
                  })
                  document
                    .getElementById(`trail-editor-${id}`)
                    ?.scrollIntoView({ block: "start", behavior: "smooth" })
                }}
              >
                Follow this receipt
              </Button>
            )}
            <Button onClick={() => setFinding({ trail, kind: "observation" })}>
              Create finding
            </Button>
            <Button
              variant="outline"
              onClick={() => setFinding({ trail, kind: "question" })}
            >
              Create observation
            </Button>
            <Button
              variant="outline"
              disabled={trail.status !== "current"}
              onClick={() => setTimeline(trail)}
            >
              {trail.kind === "transfer"
                ? "Add transfer to Timeline"
                : "Add onward payments to Timeline"}
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                setRemoving(trail)
                setRemoveReason("")
              }}
            >
              Remove link…
            </Button>
          </>
        )}
        <Button
          variant="outline"
          onClick={() => {
            const link = document.createElement("a"),
              url = URL.createObjectURL(
                new Blob([JSON.stringify(trail, null, 2)], {
                  type: "application/json",
                })
              )
            link.href = url
            link.download = "loupe-money-trail.json"
            link.click()
            setTimeout(() => URL.revokeObjectURL(url), 1000)
          }}
        >
          Download trail and sources
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Revision {trail.revision} · {trail.history.length} recorded decisions.
        Both source postings remain in their accounts.
      </p>
    </div>
  )
  return (
    <div className="space-y-4 text-sm">
      {(ledger.isPending || trails.isPending) && (
        <p role="status">Loading case payments and saved links…</p>
      )}
      {(ledger.error || trails.error) && (
        <p role="alert">{ledger.error?.message || trails.error?.message}</p>
      )}
      <Button
        variant="outline"
        disabled={busy}
        onClick={() => {
          save.reset()
          assess.reset()
          remove.reset()
          void ledger.refetch()
          void trails.refetch()
        }}
      >
        Reload payments and saved links
      </Button>
      {receipt && (
        <section role="status" className="rounded border p-3">
          <p>
            Saved to this case. Open the link from either payment or Follow
            money.
          </p>
          {showSaved(receipt)}
        </section>
      )}
      {canEdit && ledger.data && (
        <fieldset
          id={`trail-editor-${id}`}
          disabled={busy}
          className="space-y-3 rounded border p-3 scroll-mt-3"
        >
          <legend className="font-semibold">
            {draft.revision ? "Review saved link" : "Create a link"}
          </legend>
          <p>
            The chooser searches bank-account payments across this case,
            including accounts hidden by your current filters. Closing this
            review returns to your previous view.
          </p>
          <AccountOwnershipReview
            caseId={caseId}
            accountIds={[
              ...new Set(
                rows
                  .filter(
                    (p) => p.key === draft.debit || p.key === draft.credit
                  )
                  .map((p) => p.account_id)
              ),
            ]}
            label="Review ownership of these accounts"
          />
          {transactionIds.length > 0 && (
            <Button
              variant="outline"
              onClick={() => {
                const selected = rows.filter((p) =>
                    transactionIds.includes(p.key)
                  ),
                  credit = selected.find((p) => p.direction === "credit"),
                  debits = selected.filter((p) => p.direction === "debit")
                const allocation =
                  credit &&
                  debits.length &&
                  debits.every(
                    (p) =>
                      p.account_id === credit.account_id &&
                      p.currency === credit.currency
                  )
                patch({
                  kind: allocation ? "allocation" : "transfer",
                  credit: credit?.key || "",
                  debit: allocation ? "" : debits[0]?.key || "",
                  payments: allocation
                    ? Object.fromEntries(
                        debits.map((p) => [
                          p.key,
                          correctionMoney(
                            String(p.amount_minor),
                            p.currency
                          ).split(" ")[0],
                        ])
                      )
                    : {},
                })
              }}
            >
              Use selected transactions ({transactionIds.length})
            </Button>
          )}
          <label className="block">
            Relationship
            <select
              className="block rounded border bg-background p-2"
              value={draft.kind}
              disabled={!!draft.revision}
              onChange={(e) =>
                patch({
                  kind: e.target.value as Draft["kind"],
                  debit: "",
                  payments: {},
                  reference: false,
                  fx: false,
                })
              }
            >
              <option value="transfer">Two entries of the same transfer</option>
              <option value="allocation">
                Receipt allocated to later payments
              </option>
            </select>
          </label>
          <label className="block">
            Find payments
            <input
              className="block w-full rounded border bg-background p-2"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setChooserLimit(200)
              }}
              placeholder="Description, account, date or amount"
            />
          </label>
          {draft.kind === "transfer" &&
            choose("Sending account’s debit", draft.debit, "debit", (debit) =>
              patch({ debit })
            )}
          {choose(
            "Receiving account’s receipt",
            draft.credit,
            "credit",
            (credit) => patch({ credit, payments: {} })
          )}
          {draft.kind === "transfer" ? (
            <>
              <label className="block">
                <input
                  type="checkbox"
                  checked={draft.reference}
                  onChange={(e) => patch({ reference: e.target.checked })}
                />{" "}
                The other account’s statement is missing
              </label>
              {draft.reference && (
                <div className="space-y-2">
                  <p>
                    Choose only the available entry above. These details
                    describe a referenced account, without inventing another
                    transaction.
                  </p>
                  <label className="block">
                    Referenced bank
                    <input
                      className="block w-full rounded border bg-background p-2"
                      value={draft.bank}
                      onChange={(e) => patch({ bank: e.target.value })}
                    />
                  </label>
                  <label className="block">
                    Referenced account identifier
                    <input
                      className="block w-full rounded border bg-background p-2"
                      value={draft.identifier}
                      onChange={(e) => patch({ identifier: e.target.value })}
                    />
                  </label>
                  <label className="block">
                    Referenced holder (optional)
                    <input
                      className="block w-full rounded border bg-background p-2"
                      value={draft.holder}
                      onChange={(e) => patch({ holder: e.target.value })}
                    />
                  </label>
                </div>
              )}
              <label className="block">
                <input
                  type="checkbox"
                  checked={draft.fx}
                  onChange={(e) => patch({ fx: e.target.checked })}
                />{" "}
                Record an exchange hypothesis if these currencies differ
              </label>
            </>
          ) : (
            <fieldset className="max-h-60 overflow-auto rounded border p-2">
              <legend>Allocate receipt to outgoing payments</legend>
              {rows
                .filter(
                  (p) =>
                    p.direction === "debit" &&
                    p.account_id ===
                      rows.find((r) => r.key === draft.credit)?.account_id &&
                    p.currency ===
                      rows.find((r) => r.key === draft.credit)?.currency &&
                    (p.key in draft.payments ||
                      paymentLabel(p)
                        .toLowerCase()
                        .includes(search.toLowerCase()))
                )
                .map((p) => (
                  <div key={p.key} className="my-2">
                    <label>
                      <input
                        type="checkbox"
                        checked={p.key in draft.payments}
                        onChange={(e) => {
                          const payments = { ...draft.payments }
                          if (e.target.checked)
                            payments[p.key] = correctionMoney(
                              String(p.amount_minor),
                              p.currency
                            ).split(" ")[0]
                          else delete payments[p.key]
                          patch({ payments })
                        }}
                      />{" "}
                      {paymentLabel(p)}
                    </label>
                    {p.key in draft.payments && (
                      <label className="block">
                        Allocated amount ({p.currency})
                        <input
                          aria-label={`Allocation for ${p.ref_id}`}
                          inputMode="decimal"
                          className="rounded border bg-background p-2"
                          value={draft.payments[p.key]}
                          onChange={(e) =>
                            patch({
                              payments: {
                                ...draft.payments,
                                [p.key]: e.target.value,
                              },
                            })
                          }
                        />
                      </label>
                    )}
                  </div>
                ))}
              <p>
                Allocations are your interpretation. The preview checks
                available amounts; it does not assume an empty opening balance
                or prove which receipt funded a payment.
              </p>
            </fieldset>
          )}
          <label className="block">
            Reason and supporting evidence
            <textarea
              className="block w-full rounded border bg-background p-2"
              maxLength={4000}
              value={draft.reason}
              onChange={(e) => patch({ reason: e.target.value })}
            />
          </label>
          <Button
            disabled={busy || !draft.reason.trim()}
            onClick={() => {
              save.reset()
              assess.mutate()
            }}
          >
            {assess.isPending ? "Checking sources…" : "Preview link"}
          </Button>
          {assess.error && <p role="alert">{assess.error.message}</p>}
          {preview && (
            <section
              aria-label="Money trail preview"
              className="rounded border p-3 space-y-2"
            >
              <h4 className="font-semibold">
                {preview.internal_transfer
                  ? "Transfer between accounts with a reviewed common holder"
                  : preview.kind === "allocation"
                    ? "Manual onward allocation"
                    : "Transfer — ownership not established"}
              </h4>
              {preview.payments.map((p) => (
                <p key={p.key}>{paymentLabel(p)}</p>
              ))}
              {preview.receipt_unallocated_minor !== null && (
                <p>
                  Receipt remaining after saved allocations:{" "}
                  {correctionMoney(
                    preview.receipt_unallocated_minor,
                    preview.payments.find((p) => p.direction === "credit")!
                      .currency
                  )}
                </p>
              )}
              {preview.account_context && (
                <details>
                  <summary>
                    Opening balance and surrounding payments (
                    {preview.account_context.payment_count})
                  </summary>
                  <p>
                    Statement opening balance{" "}
                    {preview.account_context.period_start ||
                      "(date not recorded)"}
                    :{" "}
                    {preview.account_context.opening_balance_minor === null
                      ? "Not recorded"
                      : correctionMoney(
                          preview.account_context.opening_balance_minor,
                          preview.account_context.currency
                        )}{" "}
                    · {preview.account_context.opening_balance_source}
                  </p>
                  <p>{preview.account_context.limitation}</p>
                  <div className="max-h-60 overflow-auto">
                    {preview.account_context.payments.map((p) => (
                      <p key={p.key}>
                        <button
                          type="button"
                          className="underline"
                          onClick={() => setSource(p.key)}
                        >
                          {p.ordering_date} · {p.description || p.ref_id}
                        </button>{" "}
                        · {p.direction}{" "}
                        {correctionMoney(
                          p.amount_minor,
                          preview.account_context!.currency
                        )}{" "}
                        · Printed balance:{" "}
                        {p.running_balance_minor === null
                          ? "Not recorded"
                          : correctionMoney(
                              p.running_balance_minor,
                              preview.account_context!.currency
                            )}
                      </p>
                    ))}
                  </div>
                  {preview.account_context.payment_count > 100 && (
                    <p>
                      The first 100 entries are shown here. The complete
                      sequence is checked for changes; inspect the full account
                      in Transactions.
                    </p>
                  )}
                </details>
              )}
              {preview.warnings.map((w) => (
                <p key={w}>{w}</p>
              ))}
              <Button
                disabled={busy || save.isError}
                onClick={() => save.mutate()}
              >
                {save.isPending ? "Saving…" : "Save reviewed link"}
              </Button>
            </section>
          )}
          {save.error && (
            <p role="alert">
              {save.error.message} Reload to check whether the save completed
              before retrying.
            </p>
          )}
        </fieldset>
      )}
      {removing && (
        <section className="rounded border p-3 space-y-2">
          <h4>Remove this saved link?</h4>
          <p>
            Payments and originals stay in the case. The link and its history
            remain available as removed.
          </p>
          <label className="block">
            Reason for removal
            <textarea
              className="block w-full rounded border bg-background p-2"
              value={removeReason}
              onChange={(e) => setRemoveReason(e.target.value)}
            />
          </label>
          <Button
            disabled={busy || !removeReason.trim()}
            onClick={() => remove.mutate()}
          >
            Remove reviewed link
          </Button>
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => setRemoving(null)}
          >
            Cancel removal
          </Button>
          {remove.error && <p role="alert">{remove.error.message}</p>}
        </section>
      )}
      <section aria-label="Saved money trails" className="space-y-3">
        <h3 className="font-semibold">Saved transfers and allocations</h3>
        {(
          trails.data?.trails.filter(
            (t) =>
              t.active &&
              (!trailId || t.id === trailId) &&
              (transactionIds.length === 0 ||
                t.details.payments.some((p) => transactionIds.includes(p.key)))
          ) ?? []
        ).map(showSaved)}
        {trails.data && !trails.data.trails.some((t) => t.active) && (
          <p>No links have been saved yet.</p>
        )}
        <details>
          <summary>
            Removed links (
            {trails.data?.trails.filter((t) => !t.active).length ?? 0})
          </summary>
          {trails.data?.trails
            .filter((t) => !t.active)
            .map((t) => (
              <p key={t.id}>
                {t.kind} · {String(t.details.input.reason)} · {t.history.length}{" "}
                history entries
              </p>
            ))}
        </details>
      </section>
      {source && (
        <LedgerSourceDialog
          caseId={caseId}
          transactionId={source}
          onClose={() => setSource(null)}
        />
      )}
      {timeline && (
        <AddToTimelineDialog
          caseId={caseId}
          sourceKind={
            timeline.kind === "transfer" ? "money_trail" : "transaction"
          }
          ids={
            timeline.kind === "transfer"
              ? [timeline.id]
              : timeline.details.payments
                  .filter((p) => p.direction === "debit")
                  .map((p) => p.key)
          }
          title={
            timeline.kind === "transfer"
              ? "One transfer, supported by both statement entries"
              : "Onward payments; allocation remains an investigator interpretation"
          }
          onClose={() => setTimeline(null)}
        />
      )}
      {finding && (
        <InvestigatorFindingEditor
          caseId={caseId}
          ids={finding.trail.details.payments.map((p) => p.key)}
          draftContext={`trail:${finding.trail.id}:${finding.trail.revision}`}
          initial={{
            kind: finding.kind,
            title:
              finding.trail.kind === "transfer"
                ? "Reviewed account transfer"
                : "Onward payment allocation",
            explanation: trailNarrative(finding.trail),
          }}
          onClose={() => setFinding(null)}
        />
      )}
    </div>
  )
}
