import { useEffect, useRef, useState, type KeyboardEvent } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import type { LedgerTransaction } from "../api"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { useReadingCheck } from "../hooks/reading-check-context"
import { otherSide, withConfirmedName, withPersonName } from "../lib/payment-naming"
import { patchLedger } from "../lib/patch-ledger"
import { StatementView } from "./PaymentNamingPanel"

type Field = "from_name" | "to_name"

/**
 * Check a name Claude read, right under the row it is on: the statement line it was read from, the reading with its
 * citation, and Confirm / Correct / Cancel. Both go through the check panel's own calls (POST
 * /ledger/payment-labels/confirm, PUT /ledger/payment-labels), so the person becomes the actor, the manual-change
 * feed records it and the reading stays in the history. Viewers see the line and who can confirm.
 */
export function InlineReadingCheck({
  row,
  field,
  citation,
  onDone,
}: {
  row: LedgerTransaction
  field: Field
  citation?: string
  /** Close the check and put focus back on the row's label. */
  onDone: () => void
}) {
  const caseId = row.case_id
  const client = useQueryClient()
  const user = useAuthStore((state) => state.user)
  const { canEdit } = useFinancialAccess()
  const { openPanel } = useReadingCheck()
  const read = row[field] ?? ""
  const model = row.label_sources?.[field]?.origin?.model || "Claude"
  const who = user?.name || user?.username || "you"
  const today = () => new Date().toISOString().slice(0, 10)
  const [correcting, setCorrecting] = useState(false)
  const [name, setName] = useState(read)
  const box = useRef<HTMLElement>(null)
  const input = useRef<HTMLInputElement>(null)
  // A correction is saved on the other side of the payment; a reading on the account's own side can only be confirmed,
  // and a payment linked to a party keeps its link.
  const correctable = field === otherSide(row) && !row.counterparty_link
  useEffect(() => {
    box.current?.focus({ preventScroll: true })
  }, [])
  useEffect(() => {
    if (correcting) input.current?.focus({ preventScroll: true })
  }, [correcting])

  const settle = (next: LedgerTransaction) => {
    patchLedger(client, caseId, [next])
    void client.invalidateQueries({ queryKey: ["financial-ledger", caseId], refetchType: "none" })
    void client.invalidateQueries({ queryKey: ["ledger-source", caseId] })
  }
  const confirm = useMutation({
    mutationFn: async () => {
      const result = await fetchAPI<{ case_id: string; confirmed: number; skipped: number }>(
        `/api/financial/ledger/payment-labels/confirm?${new URLSearchParams({ case_id: caseId })}`,
        { method: "POST", body: { transactions: [{ id: row.key, version: row.label_version ?? 0 }], fields: [field] } }
      )
      if (result.case_id !== caseId || result.confirmed !== 1)
        throw Error("The name was not confirmed. Reload the transactions to see what is saved.")
    },
    onSuccess: () => {
      settle(withConfirmedName(row, field, `Confirmed by ${who} from the statement on ${today()}. Read first by ${model}.`))
      onDone()
    },
  })
  const correct = useMutation({
    mutationFn: async (value: string) => {
      const result = await fetchAPI<{ case_id: string; updated: number }>(
        `/api/financial/ledger/payment-labels?${new URLSearchParams({ case_id: caseId })}`,
        {
          method: "PUT",
          body: {
            transactions: [{ id: row.key, version: row.label_version ?? 0 }],
            counterparty_name: value,
            named_from: "statement",
          },
        }
      )
      if (result.case_id !== caseId || result.updated !== 1)
        throw Error("The correction was not saved. Reload the transactions before trying again.")
      return value
    },
    onSuccess: (value) => {
      // The person's name replaces the reading on the row; what Claude read stays in the note, never lost.
      settle(
        withPersonName(row, value, `Corrected by ${who} from the statement on ${today()}. ${model} read: "${read}".`)
      )
      toast.success("Saved your correction. What Claude read stays in the history.")
      onDone()
    },
  })
  const busy = confirm.isPending || correct.isPending
  const error = confirm.error || correct.error
  const save = () => {
    const value = name.trim().replace(/\s+/g, " ")
    if (!value || busy) return
    if (value === read.trim()) confirm.mutate()
    else correct.mutate(value)
  }
  const keys = (event: KeyboardEvent<HTMLElement>) => {
    event.stopPropagation()
    if (event.key === "Escape") {
      event.preventDefault()
      onDone()
    } else if (event.key === "Enter" && canEdit && !correcting && !(event.target instanceof HTMLButtonElement) && !(event.target instanceof HTMLAnchorElement)) {
      event.preventDefault()
      if (!busy) confirm.mutate()
    }
  }

  return (
    <section
      ref={box}
      tabIndex={-1}
      role="group"
      aria-label="Check what Claude read"
      data-testid="inline-reading-check"
      className="mt-1 w-[min(36rem,85vw)] max-w-full space-y-2 rounded border bg-background p-2 text-left text-xs font-normal text-foreground outline-none"
      onKeyDown={keys}
      onClick={(event) => event.stopPropagation()}
    >
      <p>
        <span className="font-medium">{model} read:</span> <strong data-testid="inline-reading">{read}</strong>
      </p>
      {citation && <p className="text-muted-foreground">{citation}</p>}
      {!canEdit && <p role="note">An editor of this case can confirm this.</p>}
      {canEdit && !correcting && (
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" disabled={busy} onClick={() => confirm.mutate()}>
            Confirm
          </Button>
          {correctable && (
            <Button size="sm" variant="outline" disabled={busy} onClick={() => setCorrecting(true)}>
              Correct
            </Button>
          )}
          <Button size="sm" variant="ghost" disabled={busy} onClick={onDone}>
            Cancel
          </Button>
        </div>
      )}
      {canEdit && !correctable && (
        <p className="text-muted-foreground">
          {field !== otherSide(row)
            ? "This is the account's own side: it can be confirmed here, not renamed."
            : "This payment is linked to a party: confirm the name here, change the link in the details."}
        </p>
      )}
      {canEdit && correcting && (
        <div className="flex flex-wrap items-center gap-2">
          <input
            ref={input}
            aria-label="Correct the name"
            className="min-w-[14rem] flex-1 rounded border bg-background px-2 py-1"
            value={name}
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault()
                event.stopPropagation()
                save()
              }
            }}
          />
          <Button size="sm" disabled={busy || !name.trim()} onClick={save}>
            Save
          </Button>
          <Button size="sm" variant="ghost" disabled={busy} onClick={onDone}>
            Cancel
          </Button>
        </div>
      )}
      {error && <p role="alert">{error.message}</p>}
      {/* The buttons come first, so they are in view without moving the page; the line to check follows. */}
      <StatementView caseId={caseId} row={row} />
      {openPanel && (
        <button type="button" className="underline" onClick={() => openPanel(row.key)}>
          Open in the check panel
        </button>
      )}
    </section>
  )
}
