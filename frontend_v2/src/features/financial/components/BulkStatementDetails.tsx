import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { fetchAPI } from "@/lib/api-client"
import { CurrencyOptions } from "./CurrencyOptions"
import { useFinancialDraft } from "../stores/financial-drafts"
import { useInvestigationScope } from "../stores/investigation-scope"
import { newReviewId } from "../lib/statement-review-id"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { statementMonth } from "../lib/statement-month"

const fields = [
  ["holder", "Account holder"],
  ["account_number", "Account number"],
  ["institution", "Bank"],
  ["currency", "Currency"],
  ["period_start", "Statement start date"],
  ["period_end", "Statement end date"],
] as const
type Field = (typeof fields)[number][0]
const statement = z.object({
  key: z.string(),
  file_id: z.string(),
  source_id: z.string().nullable(),
  statement_id: z.string().nullable(),
  revision: z.string(),
  filename: z.string(),
  status: z.string(),
  values: z.record(z.string(), z.string()),
})
type Statement = z.infer<typeof statement>
const listing = z.object({
  case_id: z.string(),
  items: z.array(statement),
  notices: z.array(z.object({ filename: z.string(), message: z.string() })),
})
const changes = z.record(
  z.string(),
  z.object({ before: z.string(), after: z.string() })
)
const previewSchema = z.object({
  case_id: z.string(),
  preview_revision: z.string(),
  updated: z.number(),
  items: z.array(
    statement.extend({ after: z.record(z.string(), z.string()), changes })
  ),
})
const receiptSchema = z.object({
  case_id: z.string(),
  updated: z.number(),
  unchanged: z.number(),
  imported: z.number(),
  drafts: z.number(),
  items: z.array(
    z.object({
      key: z.string(),
      filename: z.string(),
      status: z.string(),
      changes,
    })
  ),
  account_changes: z.array(z.object({ before: z.string(), after: z.string() })),
})
type Draft = {
  selected: Record<string, Statement>
  values: Partial<Record<Field, string>>
  mode: "fill_missing" | "replace"
  requestId: string
  open: boolean
}
type Props = {
  caseId: string
  fileIds?: string[]
  batchId?: string
  onSaved: () => void
  datesOnly?: boolean
  statementId?: string | null
}

export function BulkStatementDetails(props: Props) {
  const owner = useAuthStore(
    (state) => state.user?.id || state.user?.username || "anonymous"
  )
  const key = [
    props.batchId || [...(props.fileIds || [])].sort().join(","),
    props.datesOnly ? "dates" : "details",
    props.statementId === undefined ? "all" : props.statementId || "single",
  ].join(":")
  return (
    <Editor
      key={`${owner}:${props.caseId}:${key}`}
      {...props}
      scopeKey={`${owner}:${key}`}
    />
  )
}

function Editor({
  caseId,
  fileIds,
  batchId,
  onSaved,
  scopeKey,
  datesOnly = false,
  statementId,
}: Props & { scopeKey: string }) {
  const client = useQueryClient()
  const [scope, applyScope] = useInvestigationScope(caseId)
  const [draft, setDraft, clearDraft] = useFinancialDraft<Draft>(
    caseId,
    `bulk-account-details:${scopeKey}`,
    {
      selected: {},
      values: datesOnly ? { period_start: "", period_end: "" } : {},
      mode: "fill_missing",
      requestId: "",
      open: false,
    }
  )
  const [search, setSearch] = useState("")
  const [page, setPage] = useState(0)
  const [preview, setPreview] = useState<z.infer<typeof previewSchema> | null>(
    null
  )
  const [receipt, setReceipt] = useState<z.infer<typeof receiptSchema> | null>(
    null
  )
  const [refreshNotice, setRefreshNotice] = useState("")
  const endpoint = `/api/financial/statement-import/account-details`
  const query = useQuery({
    queryKey: ["bulk-statement-details", caseId, scopeKey],
    enabled: draft.open,
    retry: false,
    refetchOnWindowFocus: false,
    queryFn: async () => {
      const result = listing.parse(
        await fetchAPI(`${endpoint}/statements?case_id=${caseId}`, {
          method: "POST",
          body: batchId ? { batch_id: batchId } : { file_ids: fileIds },
        })
      )
      if (result.case_id !== caseId)
        throw Error("These statements belong to another case.")
      return statementId === undefined
        ? result
        : {
            ...result,
            items: result.items.filter(
              (item) => (item.statement_id || null) === statementId
            ),
          }
    },
  })
  const body = () => ({
    targets: Object.values(draft.selected).map(
      ({ file_id, source_id, statement_id, revision }) => ({
        file_id,
        source_id,
        statement_id,
        revision,
      })
    ),
    changes: draft.values,
    mode: draft.mode,
    request_id: draft.requestId,
  })
  const review = useMutation({
    retry: false,
    mutationFn: async () => {
      const result = previewSchema.parse(
        await fetchAPI(`${endpoint}/preview?case_id=${caseId}`, {
          method: "POST",
          body: body(),
        })
      )
      if (result.case_id !== caseId)
        throw Error("The preview belongs to another case.")
      return result
    },
    onSuccess: setPreview,
  })
  const save = useMutation({
    retry: false,
    mutationFn: async () => {
      const result = receiptSchema.parse(
        await fetchAPI(`${endpoint}/save?case_id=${caseId}`, {
          method: "POST",
          body: { ...body(), preview_revision: preview?.preview_revision },
        })
      )
      if (result.case_id !== caseId)
        throw Error("The save response belongs to another case.")
      return result
    },
    onSuccess: (result) => {
      setReceipt(result)
      setPreview(null)
      clearDraft()
      const currentIds = new Set([
        ...(scope.accountIds || []),
        ...(scope.accountId ? [scope.accountId] : []),
      ])
      const additions = result.account_changes
        .filter(
          (change) =>
            currentIds.has(change.before) && !currentIds.has(change.after)
        )
        .map((change) => change.after)
      if (additions.length)
        applyScope({
          ...scope,
          accountId: "",
          accountIds: [...new Set([...currentIds, ...additions])],
        })
      void client.invalidateQueries()
      onSaved()
    },
  })
  const busy = review.isPending || save.isPending
  const changeDraft = (value: Partial<Draft>) => {
    setDraft({ ...draft, ...value, requestId: newReviewId() })
    setPreview(null)
    review.reset()
    save.reset()
  }
  const refreshSelection = async () => {
    const result = await query.refetch()
    if (!result.data || result.isError) return
    const latest = new Map(result.data.items.map((item) => [item.key, item]))
    const retained = Object.keys(draft.selected).filter((key) =>
      latest.has(key)
    )
    const unavailable = selected.length - retained.length
    changeDraft({
      selected: Object.fromEntries(
        retained.map((key) => [key, latest.get(key)!])
      ),
    })
    setRefreshNotice(
      `Loaded the latest saved details for ${retained.length} selected statements. Your proposed values are kept; review the new before-and-after preview.${unavailable ? ` ${unavailable} statements are no longer editable here and were removed from this selection.` : ""}`
    )
  }
  const matching = (query.data?.items || []).filter((item) =>
    [item.filename, item.status, ...Object.values(item.values)]
      .join(" ")
      .toLowerCase()
      .includes(search.toLowerCase())
  )
  const selected = Object.values(draft.selected)
  const hidden = selected.filter(
    (item) => !matching.some((candidate) => candidate.key === item.key)
  ).length
  const valid =
    selected.length > 0 &&
    Object.keys(draft.values).length > 0 &&
    (draft.values.currency === undefined || !!draft.values.currency)
  const summary = (item: Statement) =>
    [
      item.values.holder || "Holder missing",
      item.values.institution || "Bank missing",
      item.values.account_number || "Account number missing",
      item.values.currency || "Currency missing",
      `${item.values.period_start || "Start missing"} – ${item.values.period_end || "End missing"}`,
      item.status,
    ].join(" · ")
  const labels = Object.fromEntries(fields)
  return (
    <>
      <Button
        variant="outline"
        disabled={!batchId && !fileIds?.length}
        onClick={() => {
          setReceipt(null)
          setDraft({
            ...draft,
            open: true,
            requestId: draft.requestId || newReviewId(),
          })
        }}
      >
        {datesOnly
          ? statementId === undefined
            ? "Set dates for selected statements"
            : "Set statement dates"
          : "Edit account details"}
      </Button>
      {receipt && (
        <p role="status" className="text-sm w-full">
          Account details saved for {receipt.updated} statements:{" "}
          {receipt.imported} imported statements updated; {receipt.drafts} saved
          for later import. {receipt.unchanged} unchanged.
          <Button
            variant="link"
            onClick={() =>
              setDraft({
                ...draft,
                selected: {},
                open: true,
                requestId: newReviewId(),
              })
            }
          >
            Review saved details
          </Button>
        </p>
      )}
      <Dialog
        open={draft.open}
        onOpenChange={(open) => {
          if (!busy) setDraft({ ...draft, open })
        }}
      >
        <DialogContent
          className="sm:max-w-4xl max-h-[90dvh] flex flex-col overflow-hidden"
          showCloseButton={!busy}
        >
          <DialogHeader>
            <DialogTitle>
              {datesOnly
                ? "Set statement dates"
                : "Edit account details for statements"}
            </DialogTitle>
            <DialogDescription>
              Select one or several statement periods, choose the fields to
              change, then review before saving. Imported statements update
              immediately; other statements keep these details for import.
            </DialogDescription>
          </DialogHeader>
          <div className="min-h-0 overflow-y-auto space-y-4 pr-1">
            {preview ? (
              <>
                <h3 className="font-semibold">
                  Review changes to {preview.updated} of {preview.items.length}{" "}
                  selected statements
                </h3>
                <p className="text-sm">
                  Only the fields below will change. Original readings and
                  correction history are retained. Saving does not import
                  additional transactions.
                </p>
                {draft.mode === "fill_missing" && !preview.updated && (
                  <div
                    className="rounded border p-3 space-y-2 text-sm"
                    role="status"
                  >
                    <p>
                      These fields already contain values. Fill missing details
                      only keeps them. To correct previously entered
                      information, choose Replace selected fields and review the
                      changes.
                    </p>
                    <Button
                      variant="outline"
                      onClick={() => changeDraft({ mode: "replace" })}
                    >
                      Correct existing details instead
                    </Button>
                  </div>
                )}
                {preview.items.map((item) => (
                  <article
                    key={item.key}
                    className="rounded border p-3 text-sm space-y-1"
                  >
                    <strong>{item.filename}</strong>
                    <p>{summary(item)}</p>
                    {!Object.keys(item.changes).length ? (
                      <p>No changes — existing details kept.</p>
                    ) : (
                      <ul className="list-disc pl-5">
                        {Object.entries(item.changes).map(([field, value]) => (
                          <li key={field}>
                            {labels[field]}: {value.before || "Missing"} →{" "}
                            <strong>{value.after || "Clear value"}</strong>
                          </li>
                        ))}
                      </ul>
                    )}
                  </article>
                ))}
              </>
            ) : (
              <>
                <h3 className="font-semibold">1. Choose statement periods</h3>
                {query.isPending ? (
                  <p role="status">Loading statement periods…</p>
                ) : query.isError ? (
                  <p role="alert">{query.error.message}</p>
                ) : (
                  <>
                    <label className="block text-sm">
                      Find statements
                      <input
                        aria-label="Find statements for account details"
                        className="block border rounded bg-background p-2 w-full"
                        value={search}
                        onChange={(event) => {
                          setSearch(event.target.value)
                          setPage(0)
                        }}
                      />
                    </label>
                    <div className="flex flex-wrap gap-2 items-center">
                      <Button
                        variant="outline"
                        disabled={busy || !matching.length}
                        onClick={() =>
                          changeDraft({
                            selected: {
                              ...draft.selected,
                              ...Object.fromEntries(
                                matching.map((item) => [item.key, item])
                              ),
                            },
                          })
                        }
                      >
                        Select all {matching.length} matching statements
                      </Button>
                      <Button
                        variant="ghost"
                        disabled={busy || !selected.length}
                        onClick={() => changeDraft({ selected: {} })}
                      >
                        Clear statement selection
                      </Button>
                      <span className="text-sm">
                        {selected.length} selected
                        {hidden ? ` · ${hidden} hidden by search` : ""}
                      </span>
                    </div>
                    <fieldset
                      disabled={busy}
                      className="divide-y max-h-56 overflow-y-auto"
                    >
                      {matching
                        .slice(page * 25, (page + 1) * 25)
                        .map((item) => (
                          <label
                            key={item.key}
                            className="flex gap-3 py-2 text-sm items-start"
                          >
                            <input
                              type="checkbox"
                              aria-label={`Select ${item.filename} ${item.values.period_start || item.key}`}
                              checked={!!draft.selected[item.key]}
                              onChange={(event) => {
                                const next = { ...draft.selected }
                                if (event.target.checked) next[item.key] = item
                                else delete next[item.key]
                                changeDraft({ selected: next })
                              }}
                            />
                            <span>
                              <strong>{item.filename}</strong>
                              <span className="block text-muted-foreground">
                                {summary(item)}
                              </span>
                            </span>
                          </label>
                        ))}
                    </fieldset>
                    {!matching.length && (
                      <p>
                        No editable statement periods found. Files must finish
                        reading before their account details can be set.
                      </p>
                    )}
                    {matching.length > 25 && (
                      <div className="flex gap-2 items-center">
                        <Button
                          variant="outline"
                          disabled={!page}
                          onClick={() => setPage(page - 1)}
                        >
                          Previous statements
                        </Button>
                        <span>
                          {page * 25 + 1}–
                          {Math.min((page + 1) * 25, matching.length)} of{" "}
                          {matching.length}
                        </span>
                        <Button
                          variant="outline"
                          disabled={(page + 1) * 25 >= matching.length}
                          onClick={() => setPage(page + 1)}
                        >
                          Next statements
                        </Button>
                      </div>
                    )}
                    {!!query.data?.notices.length && (
                      <details>
                        <summary>
                          {query.data.notices.length} statements or files need
                          individual review
                        </summary>
                        <ul className="text-sm list-disc pl-5">
                          {query.data.notices.map((notice, i) => (
                            <li key={i}>
                              {notice.filename}: {notice.message}
                            </li>
                          ))}
                        </ul>
                      </details>
                    )}
                  </>
                )}
                <h3 className="font-semibold">2. Choose fields to change</h3>
                <fieldset disabled={busy} className="space-y-3">
                  <label className="block text-sm">
                    Whole-month shortcut (optional)
                    <input
                      type="month"
                      aria-label="Statement month and year"
                      className="block border rounded bg-background p-2"
                      onChange={(event) => {
                        const dates = statementMonth(event.target.value)
                        if (dates)
                          changeDraft({ values: { ...draft.values, ...dates } })
                      }}
                    />
                    <span className="block text-muted-foreground mt-1">
                      Sets the first and last calendar day for the selected
                      statements. Check the preview; use custom dates below for
                      other periods. Transaction dates stay unchanged.
                    </span>
                  </label>
                  <label className="block text-sm">
                    How to apply changes
                    <select
                      aria-label="How to apply account details"
                      className="block border rounded bg-background p-2 w-full"
                      value={draft.mode}
                      onChange={(event) =>
                        changeDraft({
                          mode: event.target.value as Draft["mode"],
                        })
                      }
                    >
                      <option value="fill_missing">
                        Fill missing details only
                      </option>
                      <option value="replace">
                        Replace selected fields, including existing values
                      </option>
                    </select>
                  </label>
                  <p className="text-sm">
                    Tick each field you want to change. Unticked fields keep
                    their existing values. To fix an earlier entry, choose
                    Replace selected fields above.
                  </p>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {fields
                      .filter(
                        ([field]) => !datesOnly || field.startsWith("period_")
                      )
                      .map(([field, label]) => (
                        <div key={field} className="space-y-1">
                          <label className="flex items-center gap-2 text-sm">
                            <input
                              type="checkbox"
                              aria-label={`Change ${label.toLowerCase()}`}
                              checked={draft.values[field] !== undefined}
                              onChange={(event) => {
                                const values = { ...draft.values }
                                if (event.target.checked) values[field] = ""
                                else delete values[field]
                                changeDraft({ values })
                              }}
                            />
                            {label}
                          </label>
                          {draft.values[field] !== undefined &&
                            (field === "currency" ? (
                              <select
                                aria-label="New currency"
                                className="border rounded bg-background p-2 w-full"
                                value={draft.values[field]}
                                onChange={(event) =>
                                  changeDraft({
                                    values: {
                                      ...draft.values,
                                      [field]: event.target.value,
                                    },
                                  })
                                }
                              >
                                <option value="">Choose currency</option>
                                <CurrencyOptions />
                              </select>
                            ) : (
                              <input
                                type={
                                  field.startsWith("period_") ? "date" : "text"
                                }
                                maxLength={128}
                                aria-label={`New ${label.toLowerCase()}`}
                                className="border rounded bg-background p-2 w-full"
                                value={draft.values[field]}
                                onChange={(event) =>
                                  changeDraft({
                                    values: {
                                      ...draft.values,
                                      [field]: event.target.value,
                                    },
                                  })
                                }
                              />
                            ))}
                        </div>
                      ))}
                  </div>
                  {draft.mode === "replace" && (
                    <p className="text-sm">
                      A ticked field left blank clears that value. Only apply an
                      account number to statements for that account.
                    </p>
                  )}
                  {draft.values.currency !== undefined && (
                    <p className="text-sm">
                      Currency correction keeps printed amounts unchanged. No
                      exchange-rate conversion is applied.
                    </p>
                  )}
                  {(draft.values.period_start !== undefined ||
                    draft.values.period_end !== undefined) && (
                    <p className="text-sm">
                      Statement dates describe coverage; transaction dates stay
                      unchanged. Check the dates for each selected period in the
                      preview.
                    </p>
                  )}
                </fieldset>
              </>
            )}
            {(review.error || save.error) && (
              <div className="space-y-2">
                <p role="alert">
                  {(review.error || save.error)?.message} Your selection and
                  edits are kept.
                </p>
                <Button
                  variant="outline"
                  disabled={busy || query.isFetching}
                  onClick={() => void refreshSelection()}
                >
                  Load latest details and keep my changes
                </Button>
              </div>
            )}
            {refreshNotice && (
              <p role="status" className="text-sm">
                {refreshNotice}
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-2 border-t pt-3 shrink-0">
            {preview ? (
              <>
                <Button
                  disabled={busy || !preview.updated}
                  onClick={() => save.mutate()}
                >
                  {save.isPending
                    ? "Saving account details…"
                    : `Save changes to ${preview.updated} statements`}
                </Button>
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => {
                    setPreview(null)
                    save.reset()
                  }}
                >
                  Back to selection and fields
                </Button>
              </>
            ) : (
              <>
                <Button
                  disabled={busy || !valid || !query.data}
                  onClick={() => review.mutate()}
                >
                  {review.isPending
                    ? "Preparing preview…"
                    : `Review changes for ${selected.length} statements`}
                </Button>
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => {
                    setPage(0)
                    void refreshSelection()
                  }}
                >
                  Refresh statements
                </Button>
              </>
            )}
            <Button
              variant="ghost"
              disabled={busy}
              onClick={() => setDraft({ ...draft, open: false })}
            >
              Close — keep draft
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
