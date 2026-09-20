import { toast } from "sonner"
import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import { readSelectedPayments } from "../lib/selected-payment-source"
import { usePaymentCategories } from "../hooks/use-payment-categories"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { PaymentLabelOrigin } from "./PaymentLabelOrigin"

export function PaymentLabelsEditor({
  caseId,
  ids,
  names = false,
  counterparty = false,
  onClose,
}: {
  caseId: string
  ids: string[]
  names?: boolean
  counterparty?: boolean
  onClose: () => void
}) {
  const { canEdit } = useFinancialAccess()
  const client = useQueryClient()
  const categories = usePaymentCategories(caseId)
  const [changes, setChanges] = useState<Record<string, string>>({})
  const query = useQuery({
    queryKey: ["payment-label-edit", caseId, ids],
    staleTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: async () => {
      const rows = []
      for (let offset = 0; offset < ids.length; offset += 500)
        rows.push(
          ...(
            await readSelectedPayments(caseId, ids.slice(offset, offset + 500))
          ).map((source) => source.transaction)
        )
      return rows
    },
  })
  const save = useMutation({
    mutationFn: async (edits: Record<string, string>) => {
      if (!canEdit || !query.data || !Object.keys(edits).length)
        throw Error("Choose an edit first.")
      return fetchAPI(
        `/api/financial/ledger/payment-labels?${new URLSearchParams({ case_id: caseId })}`,
        {
          method: "PUT",
          body: {
            transactions: query.data.map((row) => ({
              id: row.key,
              version: row.label_version ?? 0,
            })),
            ...edits,
          },
        }
      )
    },
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["financial-ledger", caseId] }),
        client.invalidateQueries({ queryKey: ["ledger-source", caseId] }),
        client.invalidateQueries({
          predicate: (query) =>
            ["financial-linked-payments", "selected-payment"].some((key) =>
              query.queryKey.includes(key)
            ),
        }),
      ])
      toast.success(
        `Saved labels for ${ids.length} ${ids.length === 1 ? "transaction" : "transactions"}.`
      )
      onClose()
    },
  })
  if (!canEdit) return null
  const row = query.data?.[0]
  const fields = counterparty
    ? [["counterparty_name", "Person or business name"]]
    : names
      ? [
          ["from_name", "From"],
          ["to_name", "To"],
          ["category", "Category"],
        ]
      : [["category", "Category"]]
  const suggested = Object.fromEntries(
    fields
      .filter(
        ([field]) =>
          ids.length === 1 &&
          row?.label_sources?.[field as "from_name" | "to_name" | "category"]
            ?.source === "description"
      )
      .map(([field]) => [
        field,
        String(row?.[field as "from_name" | "to_name" | "category"] ?? ""),
      ])
  )
  const suggestions = [
    ...new Set([
      ...(categories.data ?? []),
      "Income",
      "Transfers",
      "Travel",
      "Meals",
      "Shopping",
      "Cash withdrawals",
      "Fees and interest",
      "Bank fees",
      "Interest income",
      "Interest charges",
      "Card payments",
      "Transport",
      "Groceries",
      "Subscriptions",
      "Uncategorized",
    ]),
  ]
  return (
    <section
      aria-label="Edit payment categories and names"
      className="rounded-lg border bg-card p-4 space-y-3"
    >
      <h3 className="font-semibold">
        {names || counterparty
          ? "Edit names and category"
          : "Categorize transactions"}
      </h3>
      <p className="text-sm">
        Applies to {ids.length} selected{" "}
        {ids.length === 1 ? "transaction" : "transactions"}. These are your
        investigation labels. The original statement text is kept.
      </p>
      {query.isPending && <p role="status">Loading selected transactions…</p>}
      {query.isError && (
        <p role="alert">
          {query.error.message}{" "}
          <button className="underline" onClick={() => void query.refetch()}>
            Reload selection
          </button>
        </p>
      )}
      {query.data && (
        <div className="flex flex-wrap gap-3">
          {fields.map(([field, label]) => (
            <label className="text-sm" key={field}>
              {label}
              <input
                aria-label={`Edit ${label}`}
                autoFocus={field === fields[0][0]}
                maxLength={field === "category" ? 120 : 512}
                list={
                  field === "category" ? "payment-category-names" : undefined
                }
                className="block rounded border bg-background p-2"
                placeholder={
                  field === "category"
                    ? "Choose or type a category"
                    : "Enter a name"
                }
                value={
                  changes[field] ??
                  (ids.length === 1 && field !== "counterparty_name"
                    ? String(
                        row?.[field as "from_name" | "to_name" | "category"] ??
                          ""
                      )
                    : "")
                }
                onChange={(event) =>
                  setChanges((current) => ({
                    ...current,
                    [field]: event.target.value,
                  }))
                }
                disabled={save.isPending || query.isFetching}
              />
              {ids.length === 1 && row && field !== "counterparty_name" && (
                <PaymentLabelOrigin
                  row={row}
                  field={field as "from_name" | "to_name" | "category"}
                  detail
                />
              )}
            </label>
          ))}
        </div>
      )}
      <datalist id="payment-category-names">
        {suggestions.map((name) => (
          <option key={name} value={name} />
        ))}
      </datalist>
      {save.isError && <p role="alert">{save.error.message}</p>}
      <div className="flex gap-2">
        <Button
          disabled={
            !query.data ||
            query.isFetching ||
            !Object.keys(changes).length ||
            save.isPending
          }
          onClick={() => save.mutate(changes)}
        >
          {save.isPending ? "Saving…" : "Save changes"}
        </Button>
        {Object.keys(suggested).length > 0 && !Object.keys(changes).length && (
          <Button
            disabled={save.isPending || query.isFetching}
            onClick={() => save.mutate(suggested)}
          >
            {Object.keys(suggested).length === 1
              ? "Confirm suggestion"
              : "Confirm suggestions"}
          </Button>
        )}
        <Button
          variant="outline"
          disabled={save.isPending || query.isFetching}
          onClick={onClose}
        >
          Cancel
        </Button>
      </div>
    </section>
  )
}
