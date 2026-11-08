import { useEffect, useRef, useState, type KeyboardEvent } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { ApiError, fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import type { LedgerTransaction } from "../api"
import { usePaymentCategoryLibrary } from "../hooks/use-payment-category-library"
import { correctionAnswer, correctionMinor, correctionMoney, correctionPreview, type CorrectionPreview } from "../lib/correction-contract"
import { cardValues, fieldChanges, stopsClosing, whatChanges, type CardValues } from "../lib/card-edit"
import { otherSide, payerPayeeQuestion, withPersonName } from "../lib/payment-naming"
import { PaymentLabelOrigin } from "./PaymentLabelOrigin"

const plainMoney = (minor: string, currency: string) => correctionMoney(minor, currency).replace(` ${currency}`, "")

/**
 * The payment card's edit mode: the other side's name, category, date, amount, direction, printed description,
 * reference and a note, checked against the statement page shown above it. No new write path: names and category
 * go through PUT /ledger/payment-labels (the label history and the manual-change feed record them), the printed
 * values through the correction preview and record calls (a replacement row; the original reading is kept and
 * shown, and only the corrected value counts in totals). An amount, direction or date change says what it changes
 * before Save, and is refused when the statement's balances would stop closing unless the person marks the
 * statement itself as wrong.
 */
export function PaymentCardEdit({
  caseId,
  row,
  onCancel,
  onSaved,
}: {
  caseId: string
  row: LedgerTransaction
  onCancel: () => void
  /** After Save: the payment's id now (a corrected payment is a new row that replaces the old one). */
  onSaved: (id: string) => void
}) {
  const client = useQueryClient()
  const user = useAuthStore((state) => state.user)
  const categories = usePaymentCategoryLibrary(caseId)
  const side = otherSide(row)
  const linked = !!row.counterparty_link
  const start = cardValues(row)
  const [name, setName] = useState(row[side] ?? "")
  const [category, setCategory] = useState(row.category ?? "")
  const [note, setNote] = useState("")
  const [amount, setAmount] = useState(plainMoney(start.amount_minor, row.currency))
  const [direction, setDirection] = useState(start.direction)
  const [date, setDate] = useState(start.date)
  const [description, setDescription] = useState(start.description)
  const [reference, setReference] = useState(start.bank_reference)
  const [statementWrong, setStatementWrong] = useState(false)
  const first = useRef<HTMLInputElement>(null)
  useEffect(() => first.current?.focus({ preventScroll: true }), [])

  const minor = correctionMinor(amount, row.currency)
  const values: CardValues = { amount_minor: minor ?? start.amount_minor, direction, date, description, bank_reference: reference }
  const fields = fieldChanges(row, values)
  const valuesChanged =
    minor !== null && (minor !== start.amount_minor || direction !== start.direction || Object.keys(fields).length > 0)
  const cleanName = name.trim().replace(/\s+/g, " ")
  const nameChanged = !linked && cleanName !== (row[side] ?? "").trim() && cleanName !== ""
  const categoryChanged = category.trim() !== (row.category ?? "").trim()
  const labelsChanged = nameChanged || categoryChanged
  const consequences = valuesChanged ? whatChanges(row, values) : []
  const valuesKey = JSON.stringify([minor, direction, fields])

  // The correction preview runs as the values change, so the balance check is known before Save.
  const preview = useMutation({
    retry: false,
    mutationFn: async (key: string) => {
      const data = correctionPreview.parse(
        await fetchAPI<unknown>(
          `/api/financial/transactions/${encodeURIComponent(row.key)}/correction-preview?${new URLSearchParams({ case_id: caseId })}`,
          { method: "POST", body: { amount_minor: minor, direction, fields } }
        )
      )
      if (data.case_id !== caseId || data.transaction_id !== row.key || data.proposed.amount_minor !== minor)
        throw Error("The check does not match this payment. Reload the transactions.")
      return { key, data }
    },
  })
  useEffect(() => {
    if (!valuesChanged) {
      preview.reset()
      return
    }
    const timer = window.setTimeout(() => preview.mutate(valuesKey), 400)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [valuesKey, valuesChanged])
  const checked: CorrectionPreview | null = preview.data?.key === valuesKey ? preview.data.data : null
  const closesNoMore = stopsClosing(checked?.statement_identity)
  const refusal = checked && !checked.verification.can_record ? checked.verification.reason || "This correction cannot be recorded." : null

  const save = useMutation({
    retry: false,
    mutationFn: async () => {
      let current = row
      const who = user?.name || user?.username || "you"
      const today = new Date().toISOString().slice(0, 10)
      if (labelsChanged) {
        const known = categories.data?.some((item) => item.name.toLocaleLowerCase() === category.trim().toLocaleLowerCase())
        const result = await fetchAPI<{ case_id: string; updated: number }>(
          `/api/financial/ledger/payment-labels?${new URLSearchParams({ case_id: caseId })}`,
          {
            method: "PUT",
            body: {
              transactions: [{ id: row.key, version: row.label_version ?? 0 }],
              ...(nameChanged ? { counterparty_name: cleanName, named_from: "statement" } : {}),
              ...(categoryChanged ? { category: category.trim(), ...(category.trim() && !known ? { add_to_library: true } : {}) } : {}),
              ...(note.trim() ? { reason: note.trim() } : {}),
            },
          }
        )
        if (result.case_id !== caseId || result.updated !== 1)
          throw Error("The name and category were not saved. Reload the transactions before trying again.")
        const said = `Saved by ${who} on ${today}.${note.trim() ? ` Note: ${note.trim()}` : ""}`
        if (nameChanged) current = withPersonName(current, cleanName, `Named by ${who} from the statement on ${today}.`)
        if (categoryChanged)
          current = {
            ...current,
            category: category.trim(),
            label_sources: { ...current.label_sources, category: { source: "investigator", explanation: said } },
          }
      }
      if (valuesChanged) {
        if (!checked) throw Error("The change is still being checked against the statement. Try Save again in a moment.")
        if (refusal) throw Error(refusal)
        if (closesNoMore && !statementWrong)
          throw Error("The statement's balances would no longer close. Tick that the statement itself is wrong to save anyway.")
        const reason = [
          closesNoMore ? "The person marked the statement itself as wrong: its printed balances do not close with this correction." : "",
          note.trim(),
        ].filter(Boolean).join(" ")
        const answer = correctionAnswer.parse(
          await fetchAPI<unknown>(
            `/api/financial/transactions/${encodeURIComponent(row.key)}/correction?${new URLSearchParams({ case_id: caseId })}`,
            {
              method: "POST",
              body: {
                amount_minor: checked.proposed.amount_minor,
                direction: checked.proposed.direction,
                expected_revision: checked.document_revision,
                ...(Object.keys(fields).length ? { fields } : {}),
                reason,
              },
            }
          )
        )
        if (answer.case_id !== caseId || answer.transaction_id !== row.key || answer.replacement_id === row.key)
          throw Error("The response did not confirm this correction. Reload the transactions to see what is saved.")
        current = {
          ...current,
          ...Object.fromEntries(Object.entries(fields)),
          key: answer.replacement_id,
          ref_id: answer.replacement_ref_id,
          amount_minor: checked.proposed.amount_minor,
          direction: checked.proposed.direction,
          ledger_status: answer.ledger_status,
          proof_class: answer.proof_class,
        } as LedgerTransaction
      }
      return current
    },
    onSuccess: (current) => {
      // The row is replaced where it stands, so the list keeps its order and position; then the server's truth.
      client.setQueriesData<{ transactions: LedgerTransaction[] }>({ queryKey: ["financial-ledger", caseId] }, (data) =>
        data?.transactions ? { ...data, transactions: data.transactions.map((item) => (item.key === row.key ? current : item)) } : data
      )
      for (const key of ["financial-ledger", "ledger-source", "financial-decisions", "financial-proof-standing", "financial-linked-payments"])
        void client.invalidateQueries({ queryKey: [key, caseId] })
      if (categoryChanged) void client.invalidateQueries({ queryKey: ["financial-category-library"] })
      toast.success("Saved your changes. The statement's reading stays visible beside them.")
      onSaved(current.key)
    },
  })
  const busy = save.isPending
  const blocked =
    busy ||
    (!labelsChanged && !valuesChanged) ||
    minor === null ||
    (valuesChanged && (!checked || !!refusal || (closesNoMore && !statementWrong)))
  const keys = (event: KeyboardEvent<HTMLElement>) => {
    // The panel's own keys (arrows, S, Esc closes) wait while a person is editing.
    event.stopPropagation()
    if (event.key === "Escape" && !busy) {
      event.preventDefault()
      onCancel()
    }
  }
  const input = "mt-1 block w-full rounded border bg-background p-2 text-sm"
  return (
    <form
      aria-label="Edit this payment"
      className="space-y-3 rounded border border-primary/40 p-3"
      onKeyDown={keys}
      onSubmit={(event) => {
        event.preventDefault()
        if (!blocked) save.mutate()
      }}
    >
      <p className="text-xs text-muted-foreground">
        Check each value against the statement page above. Your edits are saved as corrections in your name: what the
        statement read stays visible, and only your corrected values count in totals, flows and searches.
      </p>
      <label className="block text-sm font-medium">
        <span>{payerPayeeQuestion(row)}</span>
        <input
          ref={first}
          aria-label={payerPayeeQuestion(row)}
          maxLength={512}
          className={input}
          value={name}
          disabled={busy || linked}
          onChange={(event) => setName(event.target.value)}
        />
        <span className="block text-xs font-normal text-muted-foreground">
          Statement read: {row.counterparty_raw || "no name printed"}
        </span>
        <PaymentLabelOrigin row={row} field={side} detail />
        {linked && (
          <span className="block text-xs font-normal">Linked to {row.counterparty_link?.label}: change the link in the payment details.</span>
        )}
      </label>
      <label className="block text-sm font-medium">
        Category
        <input
          aria-label="Category"
          list="payment-card-categories"
          maxLength={120}
          className={input}
          value={category}
          disabled={busy}
          onChange={(event) => setCategory(event.target.value)}
        />
        <datalist id="payment-card-categories">
          {(categories.data ?? []).map((item) => (
            <option key={item.name} value={item.name} />
          ))}
        </datalist>
      </label>
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="block text-sm font-medium">
          Amount ({row.currency})
          <input aria-label="Amount" inputMode="decimal" maxLength={32} className={input} value={amount} disabled={busy} onChange={(event) => setAmount(event.target.value)} />
        </label>
        <label className="block text-sm font-medium">
          Direction
          <select aria-label="Direction" className={input} value={direction} disabled={busy} onChange={(event) => setDirection(event.target.value as "credit" | "debit")}>
            <option value="debit">{row.account_type === "credit_card" ? "Card charge" : "Money out"}</option>
            <option value="credit">{row.account_type === "credit_card" ? "Card credit" : "Money in"}</option>
          </select>
        </label>
        <label className="block text-sm font-medium">
          Date
          <input aria-label="Date" type="date" className={input} value={date} disabled={busy} onChange={(event) => setDate(event.target.value)} />
        </label>
        <label className="block text-sm font-medium">
          Reference
          <input aria-label="Reference" maxLength={4000} className={input} value={reference} disabled={busy} onChange={(event) => setReference(event.target.value)} />
        </label>
      </div>
      <label className="block text-sm font-medium">
        Printed line (description)
        <input aria-label="Printed line" maxLength={4000} className={`${input} font-mono`} value={description} disabled={busy} onChange={(event) => setDescription(event.target.value)} />
      </label>
      <p className="text-xs text-muted-foreground">
        Account: {row.account_label || row.account_holder || row.account_id}. A payment stays on the statement it was
        printed on; correct the account's own details from the account.
      </p>
      <label className="block text-sm font-medium">
        Note (kept with your change)
        <textarea aria-label="Note" maxLength={4000} className={input} value={note} disabled={busy} onChange={(event) => setNote(event.target.value)} />
      </label>
      {minor === null && (
        <p role="alert" className="text-sm">
          Enter the amount without a sign or separators, using a decimal point, with no more decimals than {row.currency} has.
        </p>
      )}
      {consequences.length > 0 && (
        <div role="status" aria-label="What this changes" className="space-y-1 rounded border p-2 text-sm">
          {consequences.map((line) => (
            <p key={line}>{line}</p>
          ))}
          {preview.isPending && <p className="text-xs">Checking the statement's balances…</p>}
          {preview.isError && <p role="alert">The change could not be checked: {preview.error.message}</p>}
          {checked && !closesNoMore && !refusal && (
            <p className="text-xs">
              {checked.statement_identity
                ? `The statement's balances ${checked.statement_identity.proposed.status === "balanced" ? "still close" : `are ${checked.statement_identity.proposed.status.replace(/_/g, " ")}`} with this change.`
                : "This statement prints no balances to check against."}
            </p>
          )}
          {refusal && <p role="alert">Refused: {refusal}</p>}
          {closesNoMore && (
            <>
              <p role="alert">
                Refused: with this change the statement's opening balance plus its payments no longer equals its closing
                balance
                {checked?.statement_identity?.proposed.delta_minor != null
                  ? ` (off by ${correctionMoney(String(checked.statement_identity.proposed.delta_minor), row.currency)})`
                  : ""}
                . Check the amount against the page. If the statement itself is wrong, tick below to save anyway.
              </p>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={statementWrong} disabled={busy} onChange={(event) => setStatementWrong(event.target.checked)} />
                The statement itself is wrong: its printed balances do not add up
              </label>
            </>
          )}
        </div>
      )}
      {save.isError && (
        <p role="alert" className="text-sm">
          {save.error instanceof ApiError ? `Not saved: ${save.error.message}` : save.error.message}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={blocked}>
          {busy ? "Saving…" : "Save"}
        </Button>
        <Button type="button" variant="outline" disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  )
}
