import { useRef, useState } from "react"
import { useFinancialDraft } from "../stores/financial-drafts"
import { AlertCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { CostBadge } from "@/components/ui/cost-badge"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog"
import type { Transaction } from "../api"

interface AmountEditDialogProps {
  caseId: string
  open: boolean
  onOpenChange: (open: boolean) => void
  transaction: Transaction | null
  onSave: (newAmount: number, correctionReason: string) => Promise<unknown>
  isPending?: boolean
}

function AmountEditForm({
  caseId,
  open,
  onOpenChange,
  transaction,
  onSave,
  isPending,
}: AmountEditDialogProps & { transaction: Transaction }) {
  const [draft, setDraft, clearDraft] = useFinancialDraft(
    caseId,
    `evidence-amount:${JSON.stringify([transaction.key, transaction.amount, transaction.currency, transaction.correction_reason])}`,
    { amount: String(transaction.amount), reason: "" }
  )
  const { amount, reason } = draft
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const lock = useRef(false)
  const busy = saving || isPending
  const parsed = Number(amount)
  const valid =
    amount.trim() !== "" &&
    Number.isFinite(parsed) &&
    parsed !== 0 &&
    /^[-+]?(?:\d+(?:\.\d{0,2}0*)?|\.\d{1,2}0*)$/.test(amount) &&
    parsed !== transaction.amount &&
    reason.trim() !== ""
  const handleSave = async () => {
    if (lock.current || busy || !valid) return
    lock.current = true
    setSaving(true)
    setError("")
    try {
      await onSave(parsed, reason.trim())
      clearDraft()
      onOpenChange(false)
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "The correction could not be saved. Your draft is retained."
      )
    } finally {
      lock.current = false
      setSaving(false)
    }
  }
  const money = (value: number) =>
    transaction.currency && /^[A-Z]{3}$/.test(transaction.currency) ? (
      <CostBadge amount={value} currency={transaction.currency} />
    ) : (
      <span>
        {value.toLocaleString("en-IE", { maximumFractionDigits: 8 })} (currency
        not recorded)
      </span>
    )

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!lock.current && !busy) onOpenChange(next)
      }}
    >
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle className="text-sm">Correct Amount</DialogTitle>
          <DialogDescription className="text-xs">
            Change the amount read from this evidence. The original value and
            the latest explanation are retained with this record.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {transaction.amount_corrected && (
            <div className="flex items-center gap-2 rounded-md bg-amber-500/10 px-3 py-2">
              <AlertCircle className="size-4 text-amber-500 shrink-0" />
              <div className="text-xs">
                <p>Previously corrected</p>
                <p className="text-muted-foreground">
                  Original:{" "}
                  {transaction.original_amount == null
                    ? "Not recorded"
                    : money(transaction.original_amount)}
                </p>
                {transaction.correction_reason && (
                  <p className="text-muted-foreground italic">
                    "{transaction.correction_reason}"
                  </p>
                )}
              </div>
            </div>
          )}

          <div>
            <label className="mb-1 block text-xs font-medium">
              Current Amount
            </label>
            {money(transaction.amount)}
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium">New Amount</label>
            <Input
              type="number"
              aria-label="New amount"
              step="any"
              value={amount}
              disabled={busy}
              onChange={(e) =>
                setDraft((current) => ({ ...current, amount: e.target.value }))
              }
              aria-describedby="amount-correction-help"
              className="font-mono"
            />
            <p
              id="amount-correction-help"
              className="mt-1 text-xs text-muted-foreground"
            >
              Use up to two decimal places. Zero cannot be saved as a financial
              amount here.
            </p>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium">
              Correction Reason
            </label>
            <Input
              aria-label="Correction reason"
              value={reason}
              disabled={busy}
              maxLength={4000}
              onChange={(e) =>
                setDraft((current) => ({ ...current, reason: e.target.value }))
              }
              placeholder="Why is this amount being corrected?"
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault()
                  void handleSave()
                }
              }}
            />
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          Your unfinished correction is kept in this browser tab. Reopen this
          record to continue, or save it to update the case.
        </p>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}

        <DialogFooter>
          <Button
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={() => onOpenChange(false)}
          >
            Close
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={handleSave}
            disabled={!valid || busy}
          >
            {busy ? "Saving..." : "Save Correction"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function AmountEditDialog(props: AmountEditDialogProps) {
  if (!props.transaction || !props.open) return null
  return (
    <AmountEditForm
      key={JSON.stringify([
        props.caseId,
        props.transaction.key,
        props.transaction.amount,
        props.transaction.currency,
        props.transaction.correction_reason,
      ])}
      {...props}
      transaction={props.transaction}
    />
  )
}
