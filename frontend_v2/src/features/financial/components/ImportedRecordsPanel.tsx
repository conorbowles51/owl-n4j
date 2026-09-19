import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { useFinancialAccess } from "../hooks/use-financial-access"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"
import { correctionMinor, correctionMoney } from "../lib/correction-contract"
import { useFinancialDraft } from "../stores/financial-drafts"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"

const recordSchema = z.object({
  id: z.string(),
  source_document_id: z.string(),
  evidence_file_id: z.string(),
  filename: z.string(),
  currency: z.string(),
  page_number: z.number().nullish(),
  locator: z.unknown(),
  original_text: z.string(),
  missing_fields: z.array(z.string()),
  version: z.number(),
  fields: z.object({
    id: z.string(),
    excluded: z.boolean(),
    manual_page: z.number().nullish(),
    date: z.string(),
    date_unprinted: z.boolean().optional(),
    date_values: z.record(z.string(), z.string()).optional(),
    description: z.string(),
    counterparty: z.string(),
    amount_minor: z.string(),
    direction: z.string().nullable(),
    balance_minor: z.string().nullable(),
    reason: z.string(),
  }),
})
type ImportedRecord = z.infer<typeof recordSchema>

export function ImportedRecordsPanel({
  caseId,
  params,
  onOpen,
}: {
  caseId: string
  params: LedgerQueryParams
  onOpen: (id: string) => void
}) {
  const [active, setActive] = useState<ImportedRecord | null>(null)
  const [page, setPage] = useState(0)
  const query = useQuery({
    queryKey: ["financial-incomplete-records", caseId, params, page],
    queryFn: async () => {
      const search = new URLSearchParams({
        case_id: caseId,
        offset: String(page * 50),
        limit: "50",
      })
      if (params.accountId) search.set("account_id", params.accountId)
      if (params.startDate) search.set("start_date", params.startDate)
      if (params.endDate) search.set("end_date", params.endDate)
      return z
        .object({ records: z.array(recordSchema), total: z.number() })
        .parse(
          await fetchAPI(
            `/api/financial/statement-import/incomplete-records?${search}`
          )
        )
    },
  })
  if (query.isPending)
    return (
      <p className="text-sm text-muted-foreground">
        Checking imported records…
      </p>
    )
  if (query.isError)
    return (
      <p role="alert">
        Incomplete records could not be loaded.{" "}
        <Button variant="link" onClick={() => void query.refetch()}>
          Retry
        </Button>
      </p>
    )
  if (!query.data.total) return null
  return (
    <section
      className="rounded-lg border border-amber-500/40 bg-amber-50/50 p-3 dark:bg-amber-950/15"
      aria-label="Imported records with missing values"
    >
      <details open={!!active}>
        <summary className="cursor-pointer text-sm font-medium">
          {query.data.total} imported{" "}
          {query.data.total === 1 ? "record has" : "records have"} missing
          values · kept outside totals
        </summary>
        <div className="mt-3 space-y-3">
          <p className="text-sm text-muted-foreground">
            The originals are retained. You can investigate other payments and
            return here later. This list follows the account and date scope,
            including undated records. Payment search and category filters apply
            to the transaction table below.
          </p>
          {!active ? (
            <div className="divide-y">
              {query.data.records.map((r) => (
                <div
                  key={`${r.source_document_id}:${r.id}`}
                  className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm"
                >
                  <div>
                    <p>
                      {r.fields.date || "Date unreadable"} ·{" "}
                      {r.fields.description || "Description unreadable"}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {r.filename} · page {r.page_number ?? "unknown"} · Check{" "}
                      {r.missing_fields.join(", ")}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setActive(r)}
                  >
                    Open record
                  </Button>
                </div>
              ))}
            </div>
          ) : (
            <ImportedRecordEditor
              key={`${active.source_document_id}:${active.id}`}
              caseId={caseId}
              record={active}
              onClose={() => setActive(null)}
              onOpen={(id) => {
                setPage(0)
                onOpen(id)
              }}
            />
          )}
          {!active && query.data.total > 50 && (
            <div className="flex items-center gap-3">
              <Button
                variant="outline"
                disabled={!page}
                onClick={() => setPage(page - 1)}
              >
                Previous records
              </Button>
              <span>
                {page * 50 + 1}–{Math.min((page + 1) * 50, query.data.total)} of{" "}
                {query.data.total}
              </span>
              <Button
                variant="outline"
                disabled={(page + 1) * 50 >= query.data.total}
                onClick={() => setPage(page + 1)}
              >
                Next records
              </Button>
            </div>
          )}
        </div>
      </details>
    </section>
  )
}

function ImportedRecordEditor({
  caseId,
  record,
  onClose,
  onOpen,
}: {
  caseId: string
  record: ImportedRecord
  onClose: () => void
  onOpen: (id: string) => void
}) {
  const { canEdit } = useFinancialAccess()
  const cache = useQueryClient()
  const [draft, setDraft, clearDraft] = useFinancialDraft(
    caseId,
    `incomplete:${record.source_document_id}:${record.id}:${record.version}`,
    {
      fields: record.fields,
      currency: record.currency,
      amount: "",
      balance: "",
      changeBalance: false,
    }
  )
  const { fields, currency, amount, balance, changeBalance } = draft
  const setFields = (update: (previous: typeof fields) => typeof fields) =>
    setDraft((previous) => ({ ...previous, fields: update(previous.fields) }))
  const setCurrency = (currency: string) =>
    setDraft((previous) => ({ ...previous, currency }))
  const setAmount = (amount: string) =>
    setDraft((previous) => ({ ...previous, amount }))
  const setBalance = (balance: string) =>
    setDraft((previous) => ({ ...previous, balance }))
  const setChangeBalance = (changeBalance: boolean) =>
    setDraft((previous) => ({ ...previous, changeBalance }))
  const change = (values: Partial<typeof fields>) =>
    setFields((previous) => ({ ...previous, ...values }))
  const save = useMutation({
    mutationFn: async () => {
      const minor = amount.trim()
        ? correctionMinor(amount, currency)
        : fields.amount_minor
      const magnitude = correctionMinor(
        balance.trim().replace(/^-/, ""),
        currency
      )
      const correctedBalance = changeBalance
        ? balance.trim()
          ? magnitude === null
            ? null
            : balance.trim().startsWith("-")
              ? `-${magnitude}`
              : magnitude
          : null
        : fields.balance_minor
      if (minor === null || !minor || correctedBalance === undefined)
        throw Error("Enter the amount shown on the original.")
      if (changeBalance && balance.trim() && correctedBalance === null)
        throw Error("Check the balance against the original.")
      return z.object({ transaction_id: z.string() }).parse(
        await fetchAPI(
          `/api/financial/statement-import/sources/${record.source_document_id}/complete-record?case_id=${caseId}`,
          {
            method: "POST",
            body: {
              row: {
                ...fields,
                amount_minor: minor,
                balance_minor: correctedBalance,
              },
              currency,
              version: record.version,
            },
          }
        )
      )
    },
    onSuccess: async (result) => {
      await cache.invalidateQueries({
        predicate: (q) =>
          q.queryKey.includes(caseId) &&
          /financial|statement-import/.test(String(q.queryKey[0])),
      })
      clearDraft()
      onClose()
      onOpen(result.transaction_id)
    },
  })
  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-medium">
          {record.filename} · page {record.page_number}
        </h3>
        <Button variant="ghost" size="sm" onClick={onClose}>
          Back to records
        </Button>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="min-w-0">
          <TransactionSourceHighlight
            sourceDocumentId={record.evidence_file_id}
            locatorPayload={
              record.locator ?? { kind: "page_only", page: record.page_number }
            }
            wholePage
          />
          <p className="mt-2 text-xs text-muted-foreground">
            Original reading: {record.original_text}
          </p>
        </div>
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            if (canEdit) save.mutate()
          }}
        >
          <label className="block text-sm">
            Date
            <input
              className="mt-1 block w-full rounded border bg-background p-2"
              type="date"
              value={fields.date}
              disabled={!canEdit}
              onChange={(e) =>
                change({ date: e.target.value, date_unprinted: false })
              }
            />
          </label>
          {Object.entries(fields.date_values ?? {}).map(([role, value]) => (
            <label key={role} className="block text-sm">
              {role.replaceAll("_", " ")}
              <input
                type="date"
                value={value}
                disabled={!canEdit}
                className="mt-1 block w-full rounded border bg-background p-2"
                onChange={(e) =>
                  change({
                    date_values: {
                      ...fields.date_values,
                      [role]: e.target.value,
                    },
                  })
                }
              />
            </label>
          ))}
          <label className="block text-sm">
            Description
            <input
              className="mt-1 block w-full rounded border bg-background p-2"
              value={fields.description}
              disabled={!canEdit}
              required
              onChange={(e) => change({ description: e.target.value })}
            />
          </label>
          <label className="block text-sm">
            Name on the statement
            <input
              className="mt-1 block w-full rounded border bg-background p-2"
              value={fields.counterparty}
              maxLength={512}
              disabled={!canEdit}
              onChange={(e) => change({ counterparty: e.target.value })}
            />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm">
              Currency
              <input
                className="mt-1 block w-full rounded border bg-background p-2"
                value={currency}
                maxLength={3}
                disabled={!canEdit}
                required
                onChange={(e) => setCurrency(e.target.value.toUpperCase())}
              />
            </label>
            <label className="block text-sm">
              Amount
              <input
                className="mt-1 block w-full rounded border bg-background p-2"
                inputMode="decimal"
                value={amount}
                placeholder={
                  /^\d+$/.test(fields.amount_minor)
                    ? correctionMoney(fields.amount_minor, currency)
                    : "Amount on original"
                }
                disabled={!canEdit}
                onChange={(e) => setAmount(e.target.value)}
              />
            </label>
          </div>
          <label className="block text-sm">
            Printed amount column
            <select
              className="mt-1 block w-full rounded border bg-background p-2"
              value={fields.direction ?? ""}
              disabled={!canEdit}
              required
              onChange={(e) => change({ direction: e.target.value })}
            >
              <option value="">Choose a column</option>
              <option value="credit">Credit / money in</option>
              <option value="debit">Debit / money out</option>
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={changeBalance}
              disabled={!canEdit}
              onChange={(e) => setChangeBalance(e.target.checked)}
            />
            Correct or clear the printed balance
          </label>
          {changeBalance && (
            <label className="block text-sm">
              Printed balance (leave blank if absent)
              <input
                className="mt-1 block w-full rounded border bg-background p-2"
                inputMode="decimal"
                value={balance}
                disabled={!canEdit}
                onChange={(e) => setBalance(e.target.value)}
              />
            </label>
          )}
          <label className="block text-sm">
            Reason for correction
            <textarea
              className="mt-1 block w-full rounded border bg-background p-2"
              value={fields.reason}
              disabled={!canEdit}
              required
              onChange={(e) => change({ reason: e.target.value })}
            />
          </label>
          {save.isError && (
            <p role="alert" className="text-sm text-destructive">
              {save.error.message}
            </p>
          )}
          {canEdit && (
            <Button type="submit" disabled={save.isPending}>
              {save.isPending
                ? "Saving…"
                : "Save correction and open transaction"}
            </Button>
          )}
        </form>
      </div>
    </div>
  )
}
