import { useState } from "react"
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
  open: boolean
  onOpenChange: (open: boolean) => void
  transaction: Transaction | null
  onSave: (newAmount: number, correctionReason: string) => void
  isPending?: boolean
}

export function AmountEditDialog({
  open,
  onOpenChange,
  transaction,
  onSave,
  isPending,
}: AmountEditDialogProps) {
  const [amount, setAmount] = useState("")
  const [reason, setReason] = useState("")

  const handleOpen = (isOpen: boolean) => {
    if (isOpen && transaction) {
      setAmount(String(transaction.amount))
      setReason("")
    }
    onOpenChange(isOpen)
  }

  const handleSave = () => {
    const parsed = parseFloat(amount)
    if (isNaN(parsed) || !reason.trim()) return
    onSave(parsed, reason.trim())
  }

  if (!transaction) return null

  return (
    <Dialog open={open} onOpenChange={handleOpen}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle className="text-sm">Correct Amount</DialogTitle>
          <DialogDescription className="text-xs">
            Update the transaction amount with an audit trail.
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
                  <CostBadge amount={transaction.original_amount ?? 0} />
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
            <CostBadge amount={transaction.amount} />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium">New Amount</label>
            <Input
              type="number"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="font-mono"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium">
              Correction Reason
            </label>
            <Input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why is this amount being corrected?"
              onKeyDown={(e) => e.key === "Enter" && handleSave()}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={handleSave}
            disabled={
              !amount ||
              !reason.trim() ||
              parseFloat(amount) === transaction.amount ||
              isPending
            }
          >
            {isPending ? "Saving..." : "Save Correction"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
