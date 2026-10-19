import {
  PaymentCounterpartyPicker,
  type PaymentCounterpartyLink,
} from "./PaymentCounterpartyPicker"
import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { randomRequestId } from "@/lib/browser-crypto"
import { useFinancialDraft } from "../stores/financial-drafts"
import { correctionMinor } from "../lib/correction-contract"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"
import { ManualTransactionPosition } from "./ManualTransactionPosition"
import { savedStatementPosition } from "../lib/saved-statement-position"
import { sourceOrderAnchor } from "../lib/statement-review-draft"
import { statementBlocker } from "../lib/statement-assessment"

const context = savedStatementPosition.extend({
  revision: z.string(),
  currency: z.string().nullable(),
  details: z.object({
    holder: z.string(),
    account_number: z.string(),
    institution: z.string(),
  }),
})

export function AddSavedStatementPayment({
  caseId,
  sourceId,
  onSaved,
}: {
  caseId: string
  sourceId: string
  onSaved: (id: string) => void
}) {
  const [open, setOpen] = useState(false)
  const query = useQuery({
    queryKey: ["manual-statement-payment-context", caseId, sourceId],
    enabled: open,
    retry: false,
    refetchOnWindowFocus: false,
    queryFn: async () => {
      const value = context.parse(
        await fetchAPI(
          `/api/financial/statement-import/sources/${sourceId}/details?case_id=${caseId}&include_positions=true`
        )
      )
      if (value.case_id !== caseId || value.source_document_id !== sourceId)
        throw Error("This statement belongs to another case.")
      return value
    },
  })
  return (
    <section className="space-y-2">
      <Button variant="outline" onClick={() => setOpen(true)}>
        Add a missed transaction
      </Button>
      {open &&
        (query.isPending ? (
          <p role="status">Opening saved statement…</p>
        ) : query.isError ? (
          <div role="alert">
            {query.error.message}{" "}
            <Button onClick={() => void query.refetch()}>
              Retry loading statement
            </Button>
          </div>
        ) : (
          <PaymentForm
            data={query.data}
            onClose={() => setOpen(false)}
            onSaved={(id) => {
              setOpen(false)
              onSaved(id)
            }}
          />
        ))}
    </section>
  )
}

function PaymentForm({
  data,
  onClose,
  onSaved,
}: {
  data: z.infer<typeof context>
  onClose: () => void
  onSaved: (id: string) => void
}) {
  const client = useQueryClient()
  const form = useRef<HTMLFormElement>(null)
  const [requestId] = useState(randomRequestId)
  const [draft, setDraft, clearDraft] = useFinancialDraft(
    data.case_id,
    `manual-payment:${data.source_document_id}`,
    {
      requestId,
      revision: data.revision,
      page: data.pages[0] || 1,
      source_order_anchor: null as z.infer<typeof sourceOrderAnchor> | null,
      date: "",
      description: "",
      counterparty: "",
      counterparty_link: null as PaymentCounterpartyLink | null,
      direction: "" as "" | "credit" | "debit",
      amount: "",
      balance: "",
      reason: "",
    }
  )
  useEffect(() => {
    form.current?.scrollIntoView({ block: "start", behavior: "smooth" })
    form.current
      ?.querySelector<HTMLInputElement>("input")
      ?.focus({ preventScroll: true })
  }, [])
  const save = useMutation({
    retry: false,
    mutationFn: async () => {
      const amount = correctionMinor(draft.amount, data.currency || "")
      const balance = draft.balance.trim()
        ? correctionMinor(draft.balance.replace(/^-/, ""), data.currency || "")
        : null
      if (!data.currency)
        throw Error("Set this statement's currency before adding a payment.")
      if (
        !draft.date ||
        !draft.direction ||
        !draft.description.trim() ||
        amount === null
      )
        throw Error(
          "Enter the transaction date, description, money in or out and printed amount."
        )
      if (draft.balance.trim() && balance === null)
        throw Error("Check the printed balance or leave it blank if unknown.")
      return z
        .object({
          transaction_id: z.string().nullable(),
          pending_reconciliation: z.boolean().optional(),
          blockers: z.array(statementBlocker).default([]),
        })
        .parse(
          await fetchAPI(
            `/api/financial/statement-import/sources/${data.source_document_id}/manual-payment?case_id=${data.case_id}`,
            {
              method: "POST",
              body: {
                request_id: draft.requestId,
                expected_revision: draft.revision,
                row: {
                  id: `manual:${draft.requestId}`,
                  manual_page: draft.page,
                  source_order_anchor: draft.source_order_anchor ?? null,
                  date: draft.date,
                  description: draft.description,
                  counterparty: draft.counterparty,
                  counterparty_link: draft.counterparty_link,
                  direction: draft.direction,
                  amount_minor: amount,
                  balance_minor:
                    balance !== null &&
                    draft.balance.startsWith("-") &&
                    balance !== "0"
                      ? `-${balance}`
                      : balance,
                  reason: draft.reason,
                },
              },
            }
          )
        )
    },
    onSuccess: (result) => {
      clearDraft()
      void client.invalidateQueries({
        predicate: (q) => q.queryKey.includes(data.case_id),
      })
      if (result.transaction_id) onSaved(result.transaction_id)
    },
  })
  if (save.isSuccess && !save.data.transaction_id)
    return (
      <div role="status" className="space-y-2 border rounded p-3">
        <p>
          Payment saved for review. It will enter Transactions when the complete
          statement reconciles. Continue adding missed payments or review the
          saved records and balances.
        </p>
        {!!save.data.blockers.length && (
          <ul className="list-disc pl-5">
            {save.data.blockers.map((blocker, index) => (
              <li key={index}>{blocker.message}</li>
            ))}
          </ul>
        )}
        <Button variant="outline" onClick={onClose}>
          Back to statement — payment saved
        </Button>
      </div>
    )
  return (
    <div
      className="grid gap-4 lg:grid-cols-2 rounded border p-3"
      aria-label="Add payment beside its original statement"
    >
      <div className="lg:sticky lg:top-3 lg:self-start">
        <label>
          PDF page{" "}
          <select
            aria-label="Missed payment PDF page"
            value={draft.page}
            onChange={(e) =>
              setDraft({
                ...draft,
                page: Number(e.target.value),
                source_order_anchor: null,
              })
            }
          >
            {data.pages.map((page) => (
              <option key={page} value={page}>
                {page}
              </option>
            ))}
          </select>
        </label>
        <TransactionSourceHighlight
          sourceDocumentId={data.evidence_file_id}
          locatorPayload={{ kind: "page_only", page: draft.page }}
          wholePage
        />
      </div>
      <form
        ref={form}
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault()
          save.mutate()
        }}
      >
        <h4 className="font-semibold">
          Add a missed transaction to this statement
        </h4>
        <p>
          {data.details.holder} · {data.details.institution} ·{" "}
          {data.details.account_number} · {data.currency || "Currency not set"}
        </p>
        <p className="text-sm">
          Save keeps this payment with the statement. It enters Transactions
          once the complete statement reconciles. Unfinished input is retained
          when you close this editor.
        </p>
        <fieldset disabled={save.isPending} className="space-y-3">
          <ManualTransactionPosition
            rowId={`manual:${draft.requestId}`}
            page={draft.page}
            value={draft.source_order_anchor}
            rows={data.source_position_rows}
            statementPages={data.pages}
            onChange={(source_order_anchor) =>
              setDraft({
                ...draft,
                source_order_anchor: source_order_anchor ?? null,
              })
            }
          />
          {data.requires_manual_position && (
            <p className="text-sm text-muted-foreground">
              Choose its printed position to check running balances. You can
              save an unfinished placement for review without importing the
              payment.
            </p>
          )}
          <label className="block">
            Transaction date
            <input
              aria-label="Missed payment date"
              type="date"
              value={draft.date}
              onChange={(e) => setDraft({ ...draft, date: e.target.value })}
              className="block w-full border rounded p-2 bg-background"
            />
          </label>
          <label className="block">
            Description
            <input
              value={draft.description}
              onChange={(e) =>
                setDraft({ ...draft, description: e.target.value })
              }
              className="block w-full border rounded p-2 bg-background"
            />
          </label>
          <label className="block">
            Money in or out
            <select
              value={draft.direction}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  direction: e.target.value as typeof draft.direction,
                })
              }
              className="block w-full border rounded p-2 bg-background"
            >
              <option value="">Choose direction</option>
              <option value="credit">Credit / money in</option>
              <option value="debit">Debit / money out</option>
            </select>
          </label>
          <label className="block">
            {draft.direction === "credit"
              ? "Paid by"
              : draft.direction === "debit"
                ? "Paid to"
                : "Counterparty"}
            <input
              value={draft.counterparty}
              onChange={(e) =>
                setDraft({ ...draft, counterparty: e.target.value })
              }
              className="block w-full border rounded p-2 bg-background"
            />
          </label>
          <PaymentCounterpartyPicker
            caseId={data.case_id}
            value={draft.counterparty_link}
            direction={draft.direction}
            onChange={(link) => setDraft({ ...draft, counterparty_link: link })}
          />
          <label className="block">
            Amount ({data.currency})
            <input
              inputMode="decimal"
              value={draft.amount}
              onChange={(e) => setDraft({ ...draft, amount: e.target.value })}
              className="block w-full border rounded p-2 bg-background"
            />
          </label>
          <label className="block">
            Printed balance (optional)
            <input
              inputMode="decimal"
              value={draft.balance}
              onChange={(e) => setDraft({ ...draft, balance: e.target.value })}
              className="block w-full border rounded p-2 bg-background"
            />
          </label>
          <label className="block">
            Note (optional)
            <textarea
              value={draft.reason}
              onChange={(e) => setDraft({ ...draft, reason: e.target.value })}
              className="block w-full border rounded p-2 bg-background"
            />
          </label>
          {save.isError && (
            <p role="alert">
              {save.error.message} Your draft is retained; retrying the same
              save will not add it twice.
            </p>
          )}
          <div className="flex gap-2">
            <Button type="submit">
              {save.isPending ? "Saving payment…" : "Save payment"}
            </Button>
            <Button type="button" variant="outline" onClick={onClose}>
              Close and keep draft
            </Button>
          </div>
        </fieldset>
      </form>
    </div>
  )
}
