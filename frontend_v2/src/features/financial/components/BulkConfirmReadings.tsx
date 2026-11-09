import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import type { LedgerTransaction } from "../api"
import { patchLedger } from "../lib/patch-ledger"
import { needsConfirm, withConfirmedName } from "../lib/payment-naming"

const FIELDS = ["from_name", "to_name"] as const

/**
 * Confirm the names Claude read on the selected payments in one step, through the same call as confirming one
 * (POST /ledger/payment-labels/confirm): each payment gets its own label-history entry and manual-change record
 * with the person and the time, and Claude's reading stays in the history. The call has no undo, so the count and
 * that fact are shown before anything is saved. Selected payments not loaded in this view are named, not dropped.
 */
export function BulkConfirmReadings({
  caseId,
  rows,
  notLoaded,
}: {
  caseId: string
  /** The selected payments loaded in this view. */
  rows: LedgerTransaction[]
  /** Selected payments this view has not loaded: they are not sent, and the person is told. */
  notLoaded: number
}) {
  const client = useQueryClient()
  const user = useAuthStore((state) => state.user)
  const [asking, setAsking] = useState(false)
  const targets = rows.filter(needsConfirm)
  const who = user?.name || user?.username || "you"
  const confirm = useMutation({
    mutationFn: async (chosen: LedgerTransaction[]) => {
      const result = await fetchAPI<{ case_id: string; confirmed: number; skipped: number }>(
        `/api/financial/ledger/payment-labels/confirm?${new URLSearchParams({ case_id: caseId })}`,
        {
          method: "POST",
          body: { transactions: chosen.map((row) => ({ id: row.key, version: row.label_version ?? 0 })), fields: [...FIELDS] },
        }
      )
      if (result.case_id !== caseId || result.confirmed + result.skipped !== chosen.length)
        throw Error("The confirmations were not all accounted for. Reload the transactions to see what is saved.")
      return { chosen, result }
    },
    onSuccess: ({ chosen, result }) => {
      const today = new Date().toISOString().slice(0, 10)
      patchLedger(
        client,
        caseId,
        chosen.map((row) =>
          FIELDS.reduce(
            (next, field) =>
              row.label_sources?.[field]?.source === "model_reading"
                ? withConfirmedName(
                    next,
                    field,
                    `Confirmed by ${who} from the statement on ${today}. Read first by ${row.label_sources?.[field]?.origin?.model || "Claude"}.`
                  )
                : next,
            row
          )
        )
      )
      // Marked stale only: the rows are already right on screen, and the whole ledger is not read again.
      void client.invalidateQueries({ queryKey: ["financial-ledger", caseId], refetchType: "none" })
      setAsking(false)
      toast.success(
        `Confirmed ${result.confirmed} ${result.confirmed === 1 ? "payment" : "payments"}` +
          (result.skipped ? `; ${result.skipped} had nothing left to confirm.` : ".")
      )
    },
  })
  if (!targets.length && !notLoaded) return null
  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Confirm the selected payments">
      {!asking ? (
        <Button size="sm" variant="outline" disabled={!targets.length} onClick={() => setAsking(true)}>
          Confirm selected ({targets.length})
        </Button>
      ) : (
        <>
          <span role="status">
            Confirm the names Claude read on {targets.length} selected{" "}
            {targets.length === 1 ? "payment" : "payments"}? Each is saved as confirmed by {who} today; Claude's reading
            stays in the history. There is no undo for a confirmation: to change a name afterwards, correct it.
          </span>
          <Button size="sm" disabled={confirm.isPending} onClick={() => confirm.mutate(targets)}>
            {confirm.isPending ? "Confirming…" : `Confirm ${targets.length}`}
          </Button>
          <Button size="sm" variant="ghost" disabled={confirm.isPending} onClick={() => setAsking(false)}>
            Cancel
          </Button>
        </>
      )}
      {notLoaded > 0 && (
        <span className="text-xs">
          {notLoaded} selected {notLoaded === 1 ? "payment is" : "payments are"} not loaded in this view and{" "}
          {notLoaded === 1 ? "is" : "are"} not included. Choose “Show only these” to load them.
        </span>
      )}
      {confirm.isError && <span role="alert">{confirm.error.message}</span>}
    </div>
  )
}
