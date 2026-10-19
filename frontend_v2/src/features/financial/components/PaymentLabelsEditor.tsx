import { toast } from "sonner"
import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import { readSelectedPayments } from "../lib/selected-payment-source"
import { usePaymentCategoryLibrary } from "../hooks/use-payment-category-library"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { PaymentLabelOrigin } from "./PaymentLabelOrigin"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"

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
  const categories = usePaymentCategoryLibrary(caseId)
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
      const targets = new Set(ids)
      if (
        query.data.length !== ids.length ||
        query.data.some((row) => !targets.has(row.key))
      )
        throw Error(
          "The complete selection could not be loaded. Reload the selection before saving."
        )
      const result = await fetchAPI<{ case_id: string; updated: number }>(
        `/api/financial/ledger/payment-labels?${new URLSearchParams({ case_id: caseId })}`,
        {
          method: "PUT",
          body: {
            transactions: query.data.map((row) => ({
              id: row.key,
              version: row.label_version ?? 0,
            })),
            ...edits,
            ...(edits.category?.trim() &&
            !categories.data?.some(
              (item) =>
                item.name.toLocaleLowerCase() ===
                edits.category.trim().toLocaleLowerCase()
            )
              ? { add_to_library: true }
              : {}),
          },
        }
      )
      if (result.case_id !== caseId || result.updated !== ids.length)
        throw Error(
          "The full category change was not confirmed. Reload the selection before trying again."
        )
      return result
    },
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["financial-ledger", caseId] }),
        client.invalidateQueries({ queryKey: ["ledger-source", caseId] }),
        client.invalidateQueries({ queryKey: ["financial-category-library"] }),
        client.invalidateQueries({
          predicate: (query) =>
            ["financial-linked-payments", "selected-payment"].some((key) =>
              query.queryKey.includes(key)
            ),
        }),
      ])
      toast.success(
        `${names || counterparty ? "Saved changes" : "Category saved"} for ${ids.length} ${ids.length === 1 ? "transaction" : "transactions"}.`
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
      ...(categories.data ?? []).map((item) => item.name),
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
  const currentCategories = [
    ...new Set(query.data?.map((item) => item.category || "Uncategorized")),
  ]
  const selectedCategory =
    changes.category ?? (ids.length === 1 ? (row?.category ?? "") : "")
  const newCategory =
    changes.category?.trim() &&
    !suggestions.some(
      (name) =>
        name.toLocaleLowerCase() === changes.category.trim().toLocaleLowerCase()
    )
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !save.isPending) onClose()
      }}
    >
      <DialogContent className="max-w-xl max-h-[85vh] overflow-auto">
        <section
          aria-label="Edit payment categories and names"
          className="rounded-lg border bg-card p-4 space-y-3"
        >
          <DialogHeader>
            <DialogTitle>
              {names || counterparty
                ? "Edit names and category"
                : ids.length === 1
                  ? "Change transaction category"
                  : "Categorize transactions"}
            </DialogTitle>
            <DialogDescription>
              Applies to {ids.length} selected{" "}
              {ids.length === 1 ? "transaction" : "transactions"}, across all
              pages. Your category replaces any current category or automatic
              suggestion and stays saved when you return.
            </DialogDescription>
          </DialogHeader>
          {row && ids.length === 1 && (
            <p className="text-sm">
              {row.description || row.ref_id} · {row.ordering_date}
            </p>
          )}
          {!counterparty && query.data && (
            <p className="text-sm">
              Current{" "}
              {currentCategories.length === 1 ? "category" : "categories"}:{" "}
              {currentCategories.join(", ")}
            </p>
          )}
          {query.isPending && (
            <p role="status">Loading selected transactions…</p>
          )}
          {query.isError && (
            <p role="alert">
              {query.error.message}{" "}
              <button
                className="underline"
                onClick={() => void query.refetch()}
              >
                Reload selection
              </button>
            </p>
          )}
          {query.data && (
            <>
              {!counterparty && (
                <label className="block text-sm">
                  Choose category
                  <select
                    aria-label="Choose category"
                    className="mt-1 block w-full rounded border bg-background p-2"
                    value={
                      suggestions.includes(selectedCategory)
                        ? selectedCategory
                        : ""
                    }
                    disabled={save.isPending || query.isFetching}
                    onChange={(event) => {
                      if (event.target.value)
                        setChanges((current) => ({
                          ...current,
                          category: event.target.value,
                        }))
                    }}
                  >
                    <option value="">Choose an existing category</option>
                    {suggestions
                      .sort((a, b) => a.localeCompare(b))
                      .map((name) => (
                        <option key={name} value={name}>
                          {name}
                        </option>
                      ))}
                  </select>
                </label>
              )}
              <div className="flex flex-wrap gap-3">
                {fields.map(([field, label]) => (
                  <label className="text-sm" key={field}>
                    {label}
                    <input
                      aria-label={`Edit ${label}`}
                      autoFocus={field === fields[0][0]}
                      maxLength={field === "category" ? 120 : 512}
                      list={
                        field === "category"
                          ? "payment-category-names"
                          : undefined
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
                              row?.[
                                field as "from_name" | "to_name" | "category"
                              ] ?? ""
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
                    {ids.length === 1 &&
                      row &&
                      field !== "counterparty_name" && (
                        <PaymentLabelOrigin
                          row={row}
                          field={field as "from_name" | "to_name" | "category"}
                          detail
                        />
                      )}
                  </label>
                ))}
              </div>
            </>
          )}
          <datalist id="payment-category-names">
            {suggestions.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
          {!counterparty && (
            <p className="text-xs text-muted-foreground">
              Choose an existing category above or type a new name. New
              categories are added to the shared library for all cases. Choose
              Uncategorized to remove a category. Original statement values
              remain unchanged.
            </p>
          )}
          {newCategory && (
            <p role="status" className="text-sm">
              Saving will create “{changes.category.trim()}” and apply it to{" "}
              {ids.length} {ids.length === 1 ? "transaction" : "transactions"}.
            </p>
          )}
          {categories.isError && (
            <p role="alert">
              The category library could not be loaded.{" "}
              <button
                className="underline"
                onClick={() => void categories.refetch()}
              >
                Reload categories
              </button>
            </p>
          )}
          {save.isError && (
            <p role="alert">
              {save.error.message}{" "}
              <button
                className="underline"
                onClick={() => {
                  save.reset()
                  void query.refetch()
                }}
              >
                Reload selection
              </button>
            </p>
          )}
          <div className="flex gap-2">
            <Button
              disabled={
                !query.data ||
                query.isFetching ||
                !Object.keys(changes).length ||
                save.isPending ||
                (!counterparty && (categories.isPending || categories.isError))
              }
              onClick={() => save.mutate(changes)}
            >
              {save.isPending ? "Saving…" : "Save changes"}
            </Button>
            {Object.keys(suggested).length > 0 &&
              !Object.keys(changes).length && (
                <Button
                  disabled={
                    save.isPending ||
                    query.isFetching ||
                    categories.isPending ||
                    categories.isError
                  }
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
      </DialogContent>
    </Dialog>
  )
}
