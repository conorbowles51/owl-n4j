import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { ApiError, fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { readSelectedPayments } from "../lib/selected-payment-source"
import { usePaymentCategoryLibrary } from "../hooks/use-payment-category-library"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { correctionMoney } from "../lib/correction-contract"
import type { LedgerTransaction } from "../api"

const fields = [
  ["from_name", "From", "text"],
  ["to_name", "To", "text"],
  ["category", "Category", "text"],
  ["amount", "Amount", "text"],
  ["direction", "Money in or out", "direction"],
  ["transaction_date", "Transaction date", "date"],
  ["description", "Description", "text"],
  ["bank_reference", "Bank reference", "text"],
  ["running_balance", "Balance", "text"],
  ["posted_date", "Posted date", "date"],
  ["value_date", "Value date", "date"],
  ["effective_date", "Effective date", "date"],
  ["transaction_type", "Transaction type", "text"],
  ["counterparty_raw", "Recorded counterparty", "text"],
] as const
const labels: Record<string, string> = {
  ...Object.fromEntries(fields.map(([key, label]) => [key, label])),
  amount_minor: "Amount",
  running_balance_minor: "Balance",
}
const previewValue = (key: string, value: string | null, currency: string) =>
  value == null || value === ""
    ? "Empty"
    : key.endsWith("_minor")
      ? correctionMoney(value, currency)
      : value
const display = (row: LedgerTransaction, key: string) => {
  if (key === "amount" || key === "running_balance") {
    const value =
      key === "amount" ? row.amount_minor : row.running_balance_minor
    return value == null
      ? ""
      : correctionMoney(String(value), row.currency).split(" ")[0]
  }
  return String(row[key as keyof LedgerTransaction] ?? "")
}
type Preview = {
  case_id: string
  revision: string
  count: number
  fields: string[]
  examples: {
    id: string
    description: string
    currency: string
    before: Record<string, string | null>
    after: Record<string, string | null>
  }[]
}
const errorText = (error: Error) =>
  error instanceof ApiError &&
  (/^[{[]/.test(error.message) || error.message.length > 500)
    ? "The changes could not be accepted. Check the selected fields and values, then review again."
    : error.message

export function PaymentEditsEditor({
  caseId,
  ids,
  initialField,
  onClose,
  onSaved,
}: {
  caseId: string
  ids: string[]
  initialField?: string
  onClose: () => void
  onSaved: (replacements: { previous_id: string; id: string }[]) => void
}) {
  const { canEdit } = useFinancialAccess()
  const client = useQueryClient()
  const categories = usePaymentCategoryLibrary(caseId)
  const [enabled, setEnabled] = useState<string[]>(
    initialField ? [initialField] : []
  )
  const [changes, setChanges] = useState<Record<string, string>>({})
  const [preview, setPreview] = useState<Preview | null>(null)
  const query = useQuery({
    queryKey: ["payment-edit-selection", caseId, ids],
    staleTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: async () => {
      const rows: LedgerTransaction[] = []
      for (let offset = 0; offset < ids.length; offset += 500)
        rows.push(
          ...(
            await readSelectedPayments(caseId, ids.slice(offset, offset + 500))
          ).map((source) => source.transaction)
        )
      if (
        rows.length !== ids.length ||
        new Set(rows.map((row) => row.key)).size !== ids.length ||
        rows.some((row) => !ids.includes(row.key))
      )
        throw Error(
          "The complete selection could not be loaded. Reload before saving."
        )
      return rows
    },
  })
  const value = (key: string) =>
    changes[key] ??
    (query.data?.length === 1 ? display(query.data[0], key) : "")
  const body = () => ({
    transactions: query.data!.map((row) => ({
      id: row.key,
      version: row.label_version ?? 0,
    })),
    changes: Object.fromEntries(enabled.map((key) => [key, value(key)])),
  })
  const review = useMutation({
    mutationFn: async () => {
      const result = await fetchAPI<Preview>(
        `/api/financial/ledger/payment-edits/preview?${new URLSearchParams({ case_id: caseId })}`,
        { method: "POST", body: body() }
      )
      if (
        result.case_id !== caseId ||
        result.count !== ids.length ||
        !/^[a-f0-9]{64}$/.test(result.revision)
      )
        throw Error(
          "The preview did not match this selection. Reload before saving."
        )
      setPreview(result)
    },
  })
  const save = useMutation({
    mutationFn: async () => {
      if (!preview) throw Error("Review the changes first.")
      const result = await fetchAPI<{
        case_id: string
        updated: number
        replacements: { previous_id: string; id: string }[]
      }>(
        `/api/financial/ledger/payment-edits/confirm?${new URLSearchParams({ case_id: caseId })}`,
        {
          method: "POST",
          body: { ...body(), expected_revision: preview.revision },
        }
      )
      if (
        result.case_id !== caseId ||
        result.updated !== ids.length ||
        result.replacements.length !== ids.length ||
        new Set(result.replacements.map((row) => row.previous_id)).size !==
          ids.length ||
        result.replacements.some((row) => !ids.includes(row.previous_id))
      )
        throw Error(
          "The complete save was not confirmed. Reload the selection before trying again."
        )
      return result
    },
    onSuccess: async (result) => {
      await client.invalidateQueries({
        predicate: (query) =>
          /financial|ledger|payment|statement-import/.test(
            String(query.queryKey[0])
          ) &&
          (query.queryKey.includes(caseId) ||
            query.queryKey[0] === "financial-category-library"),
      })
      onSaved(result.replacements)
      toast.success(
        `Saved changes to ${result.updated} ${result.updated === 1 ? "transaction" : "transactions"}.`
      )
      onClose()
    },
  })
  if (!canEdit) return null
  const busy = review.isPending || save.isPending
  const error = save.error || review.error || query.error
  const currencies = [...new Set(query.data?.map((row) => row.currency))]
  const invalidMoney =
    enabled.some((key) => ["amount", "running_balance"].includes(key)) &&
    currencies.length !== 1
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !busy) onClose()
      }}
    >
      <DialogContent
        className="flex max-h-[calc(100dvh-2rem)] flex-col gap-0 overflow-hidden p-0 sm:max-w-3xl"
        showCloseButton={!busy}
      >
        <div className="shrink-0 space-y-2 p-5 pr-12">
          <DialogTitle>
            {ids.length === 1
              ? "Edit transaction"
              : `Edit ${ids.length} selected transactions`}
          </DialogTitle>
          <DialogDescription>
            Choose the fields to change. Other fields stay as they are. All
            selected rows are included, across pages. Original statement
            readings and edit history are retained.
          </DialogDescription>
        </div>
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 pb-5">
          {query.isPending && (
            <p role="status">Loading selected transactions…</p>
          )}
          {query.data && !preview && (
            <>
              <p className="text-sm">
                {ids.length} selected · {currencies.join(", ")}.{" "}
                {ids.length > 1 &&
                  "Each enabled value will be applied to every selected row."}
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                {fields.map(([key, label, type]) => (
                  <div
                    key={key}
                    className={`rounded border p-3 ${enabled.includes(key) ? "border-primary/50 bg-primary/5" : ""}`}
                  >
                    <label className="mb-2 flex items-center gap-2 text-sm font-medium">
                      <input
                        type="checkbox"
                        aria-label={`Change ${label}`}
                        checked={enabled.includes(key)}
                        onChange={(event) =>
                          setEnabled(
                            event.target.checked
                              ? [...enabled, key]
                              : enabled.filter((field) => field !== key)
                          )
                        }
                      />
                      {label}
                    </label>
                    {type === "direction" ? (
                      <select
                        aria-label={`Edit ${label}`}
                        disabled={!enabled.includes(key)}
                        value={value(key)}
                        onChange={(event) =>
                          setChanges({ ...changes, [key]: event.target.value })
                        }
                        className="w-full rounded border bg-background p-2 text-sm"
                      >
                        <option value="">Choose direction</option>
                        <option value="credit">Money in / card credit</option>
                        <option value="debit">Money out / card charge</option>
                      </select>
                    ) : (
                      <input
                        aria-label={`Edit ${label}`}
                        type={type}
                        disabled={!enabled.includes(key)}
                        value={value(key)}
                        maxLength={
                          key === "category"
                            ? 120
                            : key === "from_name" || key === "to_name"
                              ? 512
                              : 4000
                        }
                        list={
                          key === "category"
                            ? "transaction-edit-categories"
                            : undefined
                        }
                        placeholder={
                          enabled.includes(key) ? "Enter value" : "Unchanged"
                        }
                        onChange={(event) =>
                          setChanges({ ...changes, [key]: event.target.value })
                        }
                        className="w-full rounded border bg-background p-2 text-sm disabled:opacity-50"
                      />
                    )}
                  </div>
                ))}
              </div>
              <datalist id="transaction-edit-categories">
                {[
                  "Uncategorized",
                  ...(categories.data ?? []).map((category) => category.name),
                ].map((name) => (
                  <option key={name} value={name} />
                ))}
              </datalist>
              {invalidMoney && (
                <p role="alert">
                  Select rows in one currency to apply the same amount or
                  balance.
                </p>
              )}
              <p className="text-xs text-muted-foreground">
                Amounts use the displayed currency and decimal places, without
                commas or currency symbols. Use Money in or out to set
                direction. An enabled empty text or optional date field clears
                its value.
              </p>
            </>
          )}
          {preview && (
            <section
              aria-label="Review transaction changes"
              className="space-y-3"
            >
              <h3 className="font-semibold">
                Review changes to {preview.count}{" "}
                {preview.count === 1 ? "transaction" : "transactions"}
              </h3>
              <dl className="space-y-1 rounded border p-3">
                {enabled.map((key) => (
                  <div key={key}>
                    <dt className="inline font-medium">{labels[key]}: </dt>
                    <dd className="inline">
                      {value(key) || "Clear this field"}
                      {["amount", "running_balance"].includes(key)
                        ? ` ${currencies[0]}`
                        : ""}
                    </dd>
                  </div>
                ))}
              </dl>
              <p className="text-sm">
                Only these fields will change. Corrections to amounts and dates
                also update transaction totals and statement balance checks.
              </p>
              <details>
                <summary className="cursor-pointer">
                  Compare current and new values ({Math.min(preview.count, 50)}{" "}
                  shown)
                </summary>
                {preview.examples.map((example) => (
                  <div
                    className="mt-2 rounded border p-2 text-sm"
                    key={example.id}
                  >
                    <p className="font-medium">
                      {example.description || example.id} · {example.currency}
                    </p>
                    {Object.keys(example.before).map((key) => (
                      <p key={key}>
                        {labels[key] || key}:{" "}
                        {previewValue(
                          key,
                          example.before[key],
                          example.currency
                        )}{" "}
                        →{" "}
                        {previewValue(
                          key,
                          example.after[key],
                          example.currency
                        )}
                      </p>
                    ))}
                  </div>
                ))}
              </details>
            </section>
          )}
        </div>
        <div className="shrink-0 space-y-2 border-t bg-background p-4">
          {error && (
            <p
              role="alert"
              className="max-h-24 overflow-auto text-sm text-destructive"
            >
              {errorText(error)}{" "}
              <button
                type="button"
                className="underline"
                disabled={busy}
                onClick={() => {
                  setPreview(null)
                  review.reset()
                  save.reset()
                  void query.refetch()
                }}
              >
                Reload selection
              </button>
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            {preview ? (
              <>
                <Button
                  disabled={busy || query.isFetching}
                  onClick={() => save.mutate()}
                >
                  {save.isPending
                    ? "Saving…"
                    : `Save changes to ${ids.length} ${ids.length === 1 ? "transaction" : "transactions"}`}
                </Button>
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => {
                    setPreview(null)
                    save.reset()
                  }}
                >
                  Back to editing
                </Button>
              </>
            ) : (
              <Button
                disabled={
                  !query.data ||
                  query.isFetching ||
                  !enabled.length ||
                  busy ||
                  invalidMoney
                }
                onClick={() => review.mutate()}
              >
                {review.isPending ? "Checking changes…" : "Review changes"}
              </Button>
            )}
            <Button variant="outline" disabled={busy} onClick={onClose}>
              Cancel
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
