import { useState } from "react"
import { Split } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { formatEvidenceAmount } from "../lib/evidence-amounts"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { Transaction } from "../api"
import { formatFinancialDate } from "../lib/date-utils"
import { rankSubTransactionCandidates } from "../lib/sub-transaction-suggestions"

interface SubTransactionDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  parent: Transaction | null
  subTransactions: Transaction[]
  allTransactions: Transaction[]
  onLink: (childKey: string) => void
  onUnlink: (childKey: string) => void
}

export function SubTransactionDialog({
  open,
  onOpenChange,
  parent,
  subTransactions,
  allTransactions,
  onLink,
  onUnlink,
}: SubTransactionDialogProps) {
  const [search, setSearch] = useState("")
  const [shown, setShown] = useState(20)

  if (!parent) return null

  const knownAmounts =
    parent.amount !== null &&
    subTransactions.every(
      (t) => t.amount !== null && t.currency === parent.currency
    )
  const subTotal = subTransactions.reduce((sum, t) => sum + (t.amount ?? 0), 0)
  const remaining =
    knownAmounts && parent.amount !== null ? parent.amount - subTotal : null

  const fromName = parent.from_entity?.name || "Unknown"
  const toName = parent.to_entity?.name || "Unknown"

  const linkable = allTransactions.filter(
    (t) =>
      t.key !== parent.key &&
      !subTransactions.some((s) => s.key === t.key) &&
      !t.parent_transaction_key &&
      ((t.from_entity?.name || "")
        .toLowerCase()
        .includes(search.toLowerCase()) ||
        (t.to_entity?.name || "")
          .toLowerCase()
          .includes(search.toLowerCase()) ||
        (t.purpose || "").toLowerCase().includes(search.toLowerCase()))
  )

  // Suggested parts first, strongest first, by a stated rule; every match stays listed (paged with its count).
  const suggested = rankSubTransactionCandidates(parent, remaining, linkable)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-sm">
            <Split className="size-4" />
            Sub-Transactions
          </DialogTitle>
          <DialogDescription className="text-xs">
            Link child transactions to {fromName} → {toName}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {/* Parent info */}
          <div className="flex items-center justify-between rounded-md border border-border px-3 py-2">
            <span className="text-xs font-medium">Parent total</span>
            <span>{formatEvidenceAmount(parent.amount, parent.currency)}</span>
          </div>

          {/* Linked sub-transactions */}
          {subTransactions.length > 0 && (
            <div>
              <p className="mb-1 text-xs font-semibold">
                Linked ({subTransactions.length})
              </p>
              <ScrollArea className="max-h-32">
                <div className="space-y-1">
                  {subTransactions.map((sub) => (
                    <div
                      key={sub.key}
                      className="flex items-center gap-2 rounded-md border border-border px-2 py-1.5 text-xs"
                    >
                      <span className="flex-1 truncate">
                        {sub.from_entity?.name || "—"} →{" "}
                        {sub.to_entity?.name || "—"}
                      </span>
                      <span>
                        {formatEvidenceAmount(sub.amount, sub.currency)}
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onUnlink(sub.key)}
                        className="h-6 px-2 text-[10px]"
                      >
                        Unlink
                      </Button>
                    </div>
                  ))}
                </div>
              </ScrollArea>
              <div className="mt-1 flex items-center justify-between text-xs">
                <span className="text-muted-foreground">Remaining</span>
                <span>
                  {remaining === null
                    ? "Not totalled"
                    : formatEvidenceAmount(remaining, parent.currency)}
                </span>
              </div>
            </div>
          )}

          {/* Search to link */}
          <div>
            <p className="mb-1 text-xs font-semibold">Link transaction</p>
            <Input
              placeholder="Search transactions..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setShown(20)
              }}
              className="mb-2"
            />
            <p className="mb-1 text-xs text-muted-foreground">
              {suggested.length === 0
                ? "No transaction matches."
                : `Suggested first: ${Math.min(shown, suggested.length)} of ${suggested.length} shown, strongest first (amount fits what is left, close date, same sender or recipient).`}
            </p>
            <ScrollArea className="max-h-48">
              <div className="space-y-1">
                {suggested.slice(0, shown).map(({ tx, level, reasons }) => (
                  <button
                    key={tx.key}
                    onClick={() => onLink(tx.key)}
                    className="flex w-full flex-col rounded-md px-2 py-1.5 text-left text-xs hover:bg-muted"
                  >
                    <span className="flex w-full items-center gap-2">
                      <span className="rounded bg-muted px-1 text-[10px] font-semibold capitalize">
                        {level}
                      </span>
                      <span className="font-mono text-[10px] text-muted-foreground">
                        {formatFinancialDate(tx.date)}
                      </span>
                      <span className="flex-1 truncate">
                        {tx.from_entity?.name || "—"} →{" "}
                        {tx.to_entity?.name || "—"}
                      </span>
                      <span>{formatEvidenceAmount(tx.amount, tx.currency)}</span>
                    </span>
                    <span className="text-[10px] text-muted-foreground">{reasons}</span>
                  </button>
                ))}
              </div>
            </ScrollArea>
            {suggested.length > shown && (
              <Button
                variant="link"
                size="sm"
                onClick={() => setShown((n) => n + 20)}
              >
                Show 20 more of {suggested.length - shown} not shown
              </Button>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
          >
            Done
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
