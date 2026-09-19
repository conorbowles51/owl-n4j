import { BatchStatementImportChoice } from "./BatchStatementImportChoice"
import { coverageReview } from "../hooks/use-statement-coverage-review"
import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useSearchParams } from "react-router-dom"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useStatementWorkspace } from "../stores/statement-workspace"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { StatementImportPanel } from "./StatementImportPanel"
import { serverStatementDraft } from "../lib/statement-review-draft"
import { BatchReviewContext } from "../lib/batch-review-context"
import { resetPaymentTableView } from "../lib/payment-table-draft"
import { useInvestigationScopeStore } from "../stores/investigation-scope"
import { useFinancialStore } from "../stores/financial.store"
const itemSchema = z.object({
  id: z.string(),
  file_id: z.string(),
  statement_id: z.string().nullish(),
  status: z.string(),
  filename: z.string(),
  currency: z.string().optional(),
  holder: z.string().optional(),
  account: z.string().optional(),
  period_start: z.string().optional(),
  period_end: z.string().optional(),
  transaction_count: z.number(),
  record_count: z.number().optional(),
  incomplete_count: z.number().optional(),
  problem_count: z.number().optional(),
  can_import: z.boolean().optional(),
  balance_status: z.string().optional(),
  balance_exception: z.boolean().optional(),
  source_id: z.string(),
  review_revision: z.string().optional(),
  disposition_revision: z.string().optional(),
  coverage_review: coverageReview.optional(),
  import_decision: z
    .object({ action: z.string(), reason: z.string() })
    .optional(),
  review_request: z.record(z.string(), z.unknown()).nullish(),
  problems: z.array(
    z.object({
      message: z.string(),
      row_id: z.string().nullish(),
      page: z.number().nullish(),
    })
  ),
})
const batchSchema = z.object({
  id: z.string(),
  case_id: z.string(),
  status: z.string(),
  files: z.array(
    z.object({
      source_id: z.string(),
      file_id: z.string(),
      filename: z.string(),
      status: z.string(),
      error: z.string().optional(),
    })
  ),
  counts: z.record(z.string(), z.number()),
  available_statements: z.number().optional(),
  available_records: z.number().optional(),
  issues_count: z.number().optional(),
  ready_transactions: z.number(),
  ready_revision: z.string(),
  total: z.number(),
  items: z.array(itemSchema),
})
const listSchema = z.object({
  case_id: z.string(),
  batches: z.array(
    z.object({
      id: z.string(),
      status: z.string(),
      created_at: z.string(),
      file_count: z.number(),
    })
  ),
})
const labels: Record<string, string> = {
  ready: "Ready to import",
  attention: "Needs attention",
  pending_import: "Importing",
  imported: "Imported",
  skipped: "Left unimported",
  assigned: "Payments assigned",
}

export function FinancialBatchPanel({ caseId }: { caseId: string }) {
  const [params, setParams] = useSearchParams()
  const batchId = params.get("batch"),
    itemId = params.get("batchItem")
  const [offset, setOffset] = useState(0),
    [onlyProblems, setOnlyProblems] = useState(false)
  const client = useQueryClient()
  const { canEdit, canUpload } = useFinancialAccess()
  const user = useAuthStore((state) => state.user)
  const [error, setError] = useState("")
  const prefix = `/api/financial/statement-import/batches`
  const query = useQuery({
    queryKey: ["financial-batch", caseId, batchId, offset, onlyProblems],
    enabled: !!batchId,
    queryFn: async () => {
      const result = batchSchema.parse(
        await fetchAPI(
          `${prefix}/${batchId}?case_id=${caseId}&offset=${offset}&only_problems=${onlyProblems}`
        )
      )
      if (result.case_id !== caseId || result.id !== batchId)
        throw Error("The batch belongs to another case.")
      return result
    },
    refetchInterval: (query) =>
      query.state.data?.status === "preparing" ? 3000 : false,
  })
  const importedCount = query.data?.counts.imported || 0
  const batchState = query.data?.status
  useEffect(() => {
    if (!importedCount || batchState === "preparing") return
    void client.invalidateQueries({
      predicate: (cached) =>
        cached.queryKey.includes(caseId) &&
        !String(cached.queryKey[0]).startsWith("financial-batch"),
    })
  }, [importedCount, batchState, caseId, client])
  const batches = useQuery({
    queryKey: ["financial-batches", caseId],
    enabled: !batchId,
    queryFn: async () => {
      const result = listSchema.parse(
        await fetchAPI(`${prefix}/list?case_id=${caseId}`)
      )
      if (result.case_id !== caseId) throw Error("Wrong case in batch list.")
      return result.batches
    },
    refetchInterval: 10000,
  })
  const change = (batch: string | null, item?: string, row?: string) => {
    if (batch !== batchId) setOffset(0)
    setParams((current) => {
      const next = new URLSearchParams(current)
      next.set("view", "statements")
      for (const key of ["batch", "batchItem", "batchRow"]) next.delete(key)
      if (batch) next.set("batch", batch)
      if (item) next.set("batchItem", item)
      if (row) next.set("batchRow", row)
      return next
    })
  }
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["financial-batch", caseId] })
    void client.invalidateQueries({
      queryKey: ["financial-batch-item", caseId],
    })
    void client.invalidateQueries({ queryKey: ["statement-import", caseId] })
    void client.invalidateQueries({
      queryKey: ["statement-import-status", caseId],
    })
  }
  const confirm = useMutation({
    retry: false,
    mutationFn: () =>
      fetchAPI(`${prefix}/${batchId}/confirm?case_id=${caseId}`, {
        method: "POST",
        body: { expected_ready_revision: query.data!.ready_revision },
      }),
    onSuccess: refresh,
  })
  const openImported = useMutation({
    mutationFn: async () => {
      const result = z
        .object({
          case_id: z.string(),
          batch_id: z.string(),
          revision: z.string(),
          source_document_ids: z.array(z.string()),
          account_ids: z.array(z.string()),
          statement_count: z.number(),
          transaction_count: z.number(),
          start_date: z.string().nullable(),
          end_date: z.string().nullable(),
        })
        .parse(
          await fetchAPI(
            `${prefix}/${batchId}/imported-transactions?case_id=${caseId}`
          )
        )
      if (result.case_id !== caseId || result.batch_id !== batchId)
        throw Error("The imported payments belong to another batch.")
      return result
    },
    onSuccess: (result) => {
      const scope = {
        accountId:
          result.account_ids.length === 1 ? result.account_ids[0] : undefined,
        startDate: result.start_date || undefined,
        endDate: result.end_date || undefined,
      }
      resetPaymentTableView(caseId, scope, result)
      useInvestigationScopeStore.getState().apply(caseId, scope)
      useFinancialStore.getState().setMode("transactions")
      setParams({ view: "transactions" })
    },
  })
  if (!batchId)
    return (
      <section
        className="rounded border p-3 space-y-2"
        aria-label="Financial processing batches"
      >
        <h3 className="font-semibold">Processing batches</h3>
        <p className="text-sm text-muted-foreground">
          Send files or folders from Evidence to prepare statements together and
          import the ready ones in one step.
        </p>
        {batches.isError && <p role="alert">{batches.error.message}</p>}
        {batches.data?.slice(0, 8).map((batch) => (
          <Button
            key={batch.id}
            variant="outline"
            size="sm"
            onClick={() => change(batch.id)}
          >
            {batch.file_count} files ·{" "}
            {new Date(batch.created_at).toLocaleString()} ·{" "}
            {batch.status === "preparing" ? "Processing" : "Open batch"}
          </Button>
        ))}
      </section>
    )
  if (itemId)
    return (
      <BatchStatementReview
        key={itemId}
        caseId={caseId}
        batchId={batchId}
        itemId={itemId}
        rowId={params.get("batchRow") ?? undefined}
        onBack={() => {
          refresh()
          change(batchId)
        }}
      />
    )
  if (query.isPending)
    return <p role="status">Loading the financial processing batch…</p>
  if (query.isError)
    return (
      <div>
        <p role="alert">{query.error.message}</p>
        <Button onClick={() => void query.refetch()}>Retry batch</Button>
        <Button variant="outline" onClick={() => change(null)}>
          Back to statements
        </Button>
      </div>
    )
  const batch = query.data
  const problems = batch.issues_count ?? batch.counts.attention ?? 0
  const available = batch.available_statements ?? batch.counts.ready ?? 0
  const availableRecords = batch.available_records ?? batch.ready_transactions
  return (
    <section aria-label="Financial processing batch" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">
            Prepare statements for import
          </h2>
          <p className="text-sm text-muted-foreground">
            Processing continues on the server. You can leave this page and
            return to the batch.
          </p>
        </div>
        <div className="flex gap-2">
          {importedCount > 0 && (
            <Button
              disabled={openImported.isPending}
              onClick={() => openImported.mutate()}
            >
              {openImported.isPending
                ? "Opening imported payments…"
                : "Open imported transactions"}
            </Button>
          )}
          <Button variant="outline" onClick={() => change(null)}>
            Back to all statements
          </Button>
        </div>
      </div>
      {openImported.isError && <p role="alert">{openImported.error.message}</p>}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          [
            "Files checked",
            `${batch.files.filter((f) => f.status === "checked").length} of ${batch.files.length}`,
          ],
          ["Available to import", available],
          ["Issues to check", problems],
          ["Imported", batch.counts.imported || 0],
        ].map(([title, value]) => (
          <div
            className={`rounded border p-3 ${title === "Issues to check" && problems ? "border-amber-400 bg-amber-50/60 dark:bg-amber-950/20" : "bg-card"}`}
            key={title}
          >
            <p className="text-sm text-muted-foreground">{title}</p>
            <p className="text-2xl font-semibold">{value}</p>
          </div>
        ))}
      </div>
      {!!batch.counts.skipped && (
        <p className="text-sm">
          {batch.counts.skipped} statements left unimported. Their files and
          saved reviews are retained below.
        </p>
      )}
      {!!batch.counts.assigned && (
        <p className="text-sm">
          {batch.counts.assigned}{" "}
          {batch.counts.assigned === 1
            ? "unassigned page review is"
            : "unassigned page reviews are"}{" "}
          complete. Check and import their payments in the destination
          statements.
        </p>
      )}
      <div className="rounded border bg-card p-4 flex flex-wrap gap-3 items-center justify-between">
        <div>
          <p className="font-medium">
            {available} {available === 1 ? "statement" : "statements"} available
            · {availableRecords} records
          </p>
          <p className="text-sm text-muted-foreground">
            Import now and return to any issues later. Incomplete records and
            their originals are retained; unreadable values stay out of totals.
          </p>
        </div>
        <Button
          disabled={!canEdit || !available || confirm.isPending}
          onClick={() => confirm.mutate()}
        >
          {confirm.isPending
            ? "Confirming…"
            : `Import ${availableRecords} records`}
        </Button>
      </div>
      {(confirm.isError || error) && (
        <p role="alert">{confirm.error?.message || error}</p>
      )}
      {!!batch.counts.pending_import && (
        <p role="status">
          Importing {batch.counts.pending_import} statements. Successfully
          imported statements are retained if another one needs attention.
        </p>
      )}
      <details
        open={batch.files.some((f) => f.status !== "checked")}
        className="rounded border p-3"
      >
        <summary className="cursor-pointer font-medium">
          File processing ({batch.files.length})
        </summary>
        <ul className="max-h-52 overflow-auto divide-y">
          {batch.files.map((file) => (
            <li key={file.source_id} className="py-2 text-sm">
              <strong>{file.filename}</strong> ·{" "}
              {{
                waiting: "Waiting to process",
                processing: "Reading and checking statements",
                checked: "Statements checked",
                error: "Needs attention",
              }[file.status] ?? file.status}
              {file.error && (
                <>
                  <p role="alert">{file.error}</p>
                  <div className="flex gap-2 mt-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        useStatementWorkspace
                          .getState()
                          .select(
                            `${user?.id || user?.username || "anonymous"}:${caseId}`,
                            file.file_id
                          )
                        change(null)
                      }}
                    >
                      Open file review
                    </Button>
                    {canEdit && canUpload && (
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={batch.status === "preparing"}
                        onClick={async () => {
                          setError("")
                          try {
                            await fetchAPI(
                              `${prefix}/${batchId}/files/${file.source_id}/retry?case_id=${caseId}`,
                              { method: "POST" }
                            )
                            refresh()
                          } catch (error) {
                            setError(
                              error instanceof Error
                                ? error.message
                                : "The file could not be retried."
                            )
                          }
                        }}
                      >
                        Retry this file
                      </Button>
                    )}
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      </details>
      <div className="flex items-center gap-3">
        <label className="text-sm">
          <input
            type="checkbox"
            checked={onlyProblems}
            onChange={(event) => {
              setOnlyProblems(event.target.checked)
              setOffset(0)
            }}
          />{" "}
          Show statements with issues only
        </label>
        <Button
          size="sm"
          variant="outline"
          onClick={() => void query.refetch()}
        >
          Refresh batch
        </Button>
      </div>
      <div className="space-y-2">
        {batch.items.map((item) => (
          <article
            key={item.id}
            className={`rounded border p-4 space-y-2 ${item.status === "attention" ? "border-amber-500/50" : "bg-card"}`}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="font-semibold">{item.filename}</h3>
                <p className="text-sm">
                  {[
                    item.holder,
                    item.account,
                    item.period_start &&
                      `${item.period_start} to ${item.period_end}`,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
                <p className="text-sm">
                  {item.can_import
                    ? "Available to import"
                    : (labels[item.status] ?? item.status)}
                  {!!(item.problem_count ?? item.problems.length) &&
                    ` · ${item.problem_count ?? item.problems.length} issues`}
                  {item.status !== "assigned" && (
                    <>
                      {" "}
                      · {item.record_count ??
                        item.transaction_count} records {item.currency}
                      {!!item.incomplete_count &&
                        ` · ${item.incomplete_count} with missing values`}
                    </>
                  )}
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                disabled={item.status === "pending_import"}
                onClick={() =>
                  change(
                    batchId,
                    item.id,
                    item.problems.find((p) => p.row_id)?.row_id ?? undefined
                  )
                }
              >
                {item.status === "attention"
                  ? "Review problems"
                  : "Open statement"}
              </Button>
            </div>
            {!item.currency && item.status === "attention" && canEdit && (
              <label className="block text-sm">
                Statement currency{" "}
                <select
                  aria-label={`Currency for ${item.filename}`}
                  className="rounded border bg-background p-2"
                  defaultValue=""
                  disabled={batch.status === "preparing"}
                  onChange={async (event) => {
                    if (!event.target.value) return
                    setError("")
                    try {
                      await fetchAPI(
                        `${prefix}/${batchId}/files/${item.source_id}/currency?case_id=${caseId}`,
                        {
                          method: "POST",
                          body: { currency: event.target.value },
                        }
                      )
                      refresh()
                    } catch (error) {
                      setError(
                        error instanceof Error
                          ? error.message
                          : "Currency could not be saved."
                      )
                    }
                  }}
                >
                  <option value="">Choose printed currency</option>
                  {(typeof Intl.supportedValuesOf === "function"
                    ? Intl.supportedValuesOf("currency")
                    : ["USD", "EUR", "GBP", "CAD", "AUD"]
                  ).map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
              </label>
            )}
            {item.balance_status === "matches" && (
              <p className="text-sm text-teal-700 dark:text-teal-300">
                Opening balance, transactions and closing balance agree.
              </p>
            )}
            {item.balance_exception && (
              <p className="text-sm text-amber-700 dark:text-amber-300">
                A balance difference remains. The reviewer's explanation is
                saved with these values.
              </p>
            )}
            {item.status !== "assigned" &&
              item.balance_status === "unavailable" &&
              item.currency && (
                <p className="text-sm text-muted-foreground">
                  Not enough readable balances for an automatic balance check.
                </p>
              )}
            {!!item.coverage_review?.candidates.length && (
              <p className="text-sm">
                Overlapping dates:{" "}
                {item.coverage_review.candidates
                  .map(
                    (other) =>
                      `${other.filename} (${other.period_start} to ${other.period_end})`
                  )
                  .join("; ")}
                . Open this statement to compare the originals.
              </p>
            )}
            {item.import_decision && (
              <p className="text-sm">
                {item.import_decision.action === "skip"
                  ? "Left unimported"
                  : "Restored to review"}
                : {item.import_decision.reason}
              </p>
            )}
            {canEdit &&
              item.disposition_revision &&
              !["imported", "pending_import", "assigned"].includes(
                item.status
              ) && (
                <BatchStatementImportChoice
                  caseId={caseId}
                  batchId={batchId}
                  itemId={item.id}
                  revision={item.disposition_revision}
                  skipped={item.status === "skipped"}
                  refresh={refresh}
                />
              )}
            {item.problems.map((problem, index) => (
              <div
                className="flex flex-wrap items-center gap-2 text-sm"
                key={index}
              >
                <span>
                  {problem.page ? `PDF page ${problem.page}: ` : ""}
                  {problem.message}
                </span>
                {problem.row_id && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => change(batchId, item.id, problem.row_id!)}
                  >
                    Go to this row
                  </Button>
                )}
              </div>
            ))}
          </article>
        ))}
      </div>
      {!batch.items.length && (
        <p>
          {batch.status === "preparing"
            ? "Statements will appear here as each file is checked."
            : onlyProblems
              ? "No statements need attention."
              : "No statements were prepared. Check the file errors above."}
        </p>
      )}
      <div className="flex gap-3 items-center">
        <Button
          variant="outline"
          disabled={!offset}
          onClick={() => setOffset(Math.max(0, offset - 100))}
        >
          Previous statements
        </Button>
        <span className="text-sm">
          {batch.total ? offset + 1 : 0}–{Math.min(offset + 100, batch.total)}{" "}
          of {batch.total}
        </span>
        <Button
          variant="outline"
          disabled={offset + 100 >= batch.total}
          onClick={() => setOffset(offset + 100)}
        >
          Next statements
        </Button>
      </div>
    </section>
  )
}

function BatchStatementReview({
  caseId,
  batchId,
  itemId,
  rowId,
  onBack,
}: {
  caseId: string
  batchId: string
  itemId: string
  rowId?: string
  onBack: () => void
}) {
  const [, setParams] = useSearchParams()
  const user = useAuthStore((state) => state.user),
    owner = user?.id || user?.username || "anonymous"
  const query = useQuery({
    queryKey: ["financial-batch-item", caseId, batchId, itemId],
    refetchOnWindowFocus: false,
    queryFn: async () =>
      itemSchema
        .extend({ review_revision: z.string() })
        .parse(
          await fetchAPI(
            `/api/financial/statement-import/batches/${batchId}/items/${itemId}?case_id=${caseId}`
          )
        ),
  })
  const item = query.data
  const [selected, setSelected] = useState(false)
  useEffect(() => {
    if (!item || query.isFetching) return
    const store = useStatementWorkspace.getState()
    store.select(`${owner}:${caseId}`, item.file_id)
    store.setReviewChoice(`${owner}:${caseId}:${item.file_id}`, {
      currency: item.currency || "",
      statementId: item.statement_id || "",
    })
    setSelected(true)
  }, [item, owner, caseId, query.isFetching])
  const client = useQueryClient()
  const reviewRevision = useRef(item?.review_revision)
  useEffect(() => {
    reviewRevision.current = item?.review_revision
  }, [item?.review_revision])
  const [navigationError, setNavigationError] = useState("")
  const nextProblem = async (direction: "next" | "previous" = "next") => {
    setNavigationError("")
    try {
      const result = z
        .object({
          case_id: z.string(),
          batch_id: z.string(),
          item_id: z.string().nullable(),
          row_id: z.string().nullable(),
        })
        .parse(
          await fetchAPI(
            `/api/financial/statement-import/batches/${batchId}/items/${itemId}/next-problem?case_id=${caseId}&direction=${direction}`
          )
        )
      if (result.case_id !== caseId || result.batch_id !== batchId)
        throw Error("The next statement belongs to a different batch.")
      if (!result.item_id) {
        onBack()
        return
      }
      setParams((current) => {
        const next = new URLSearchParams(current)
        next.set("batchItem", result.item_id!)
        if (result.row_id) next.set("batchRow", result.row_id)
        else next.delete("batchRow")
        return next
      })
    } catch (error) {
      setNavigationError(
        error instanceof Error
          ? error.message
          : "The next statement could not be opened."
      )
    }
  }
  const save = async (request: unknown) => {
    const result = z
      .object({ status: z.string(), review_revision: z.string() })
      .parse(
        await fetchAPI(
          `/api/financial/statement-import/batches/${batchId}/items/${itemId}?case_id=${caseId}`,
          {
            method: "PUT",
            body: { request, expected_review_revision: reviewRevision.current },
          }
        )
      )
    reviewRevision.current = result.review_revision
    void client.invalidateQueries({ queryKey: ["financial-batch", caseId] })
    return result
  }
  const raw = item?.review_request
  const draft = serverStatementDraft(raw ?? undefined)
  return (
    <div className="space-y-3">
      <Button variant="outline" onClick={onBack}>
        Back to bulk import
      </Button>
      {item?.status === "skipped" && (
        <p className="rounded border p-3">
          This statement was left unimported. Return to the batch and choose
          Restore to review to edit or import it. {item.import_decision?.reason}
        </p>
      )}
      {navigationError && <p role="alert">{navigationError}</p>}
      {query.isError ? (
        <p role="alert">{query.error.message}</p>
      ) : !item || !selected ? (
        <p role="status">Opening statement…</p>
      ) : (
        <BatchReviewContext.Provider
          value={{
            batchId,
            rowId,
            draftRevision: item.review_revision,
            save,
            saved: onBack,
            nextProblem,
            previousProblem: () => nextProblem("previous"),
            draft: draft ?? undefined,
            readOnly:
              item.status === "skipped" || item.status === "pending_import",
          }}
        >
          <StatementImportPanel
            caseId={caseId}
            onImported={(receipt) => {
              const scope = { accountId: receipt?.account_id }
              resetPaymentTableView(caseId, scope, receipt)
              useInvestigationScopeStore.getState().apply(caseId, scope)
              useFinancialStore.getState().setMode("transactions")
              setParams({ view: "transactions" })
            }}
          />
        </BatchReviewContext.Provider>
      )}
    </div>
  )
}
