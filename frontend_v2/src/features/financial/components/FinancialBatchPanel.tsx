import { statementAssessment } from "../lib/statement-assessment"
import { statementDuplicateDisposition } from "../lib/statement-duplicate"
import { StatementReconciliationSummary } from "./StatementReconciliationSummary"
import { formatLedgerAmount } from "../lib/ledger-format"
import { BatchReadingJobs } from "./BatchReadingJobs"
import { FinancialRemovalAction } from "./FinancialRemovalAction"
import { BatchStatementImportChoice } from "./BatchStatementImportChoice"
import { BatchCurrencyEditor } from "./BatchCurrencyEditor"
import { BatchReviewSummary } from "./BatchReviewSummary"
import { batchReviewSummarySchema } from "../lib/batch-review-summary"
import { BulkStatementDetails } from "./BulkStatementDetails"
import { coverageReview } from "../hooks/use-statement-coverage-review"
import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useSearchParams } from "react-router-dom"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { randomRequestId } from "@/lib/browser-crypto"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useStatementWorkspace } from "../stores/statement-workspace"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { StatementImportPanel } from "./StatementImportPanel"
import { serverStatementDraft } from "../lib/statement-review-draft"
import { BatchReviewContext } from "../lib/batch-review-context"
import { resetPaymentTableView } from "../lib/payment-table-draft"
import { useInvestigationScopeStore } from "../stores/investigation-scope"
import { useFinancialStore } from "../stores/financial.store"
import { useFinancialDraft } from "../stores/financial-drafts"
import type { EvidenceJob } from "@/types/evidence.types"
const recoveryReceipt = z.object({
  attempt_id: z.string().optional(),
  action: z.string().optional(),
  stage: z.string().optional(),
  message: z.string().optional(),
  review_file_id: z.string().nullish(),
  reading_file_id: z.string().nullish(),
})
const operationSchema = z.object({
  id: z.string(),
  status: z.string(),
  created_at: z.string(),
  statement_count: z.number(),
  pending: z.number(),
  failed: z.number(),
  imported: z.number(),
  already_present: z.number(),
  duplicate_ignored: z.number().default(0),
  transaction_count: z.number(),
  incomplete_count: z.number(),
  outcomes: z.array(
    z.object({
      item_id: z.string(),
      filename: z.string(),
      status: z.string(),
      period_start: z.string().default(""),
      period_end: z.string().default(""),
      message: z.string().optional(),
    })
  ),
})
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
  unclassified_count: z.number().optional(),
  problem_count: z.number().optional(),
  can_import: z.boolean().optional(),
  admission: statementAssessment.nullish(),
  duplicate_disposition: statementDuplicateDisposition.nullish(),
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
      field: z.string().optional(),
      kind: z.string().optional(),
      review_reason: z.string().optional(),
    })
  ),
})
function reviewProblems(item: z.infer<typeof itemSchema>, group: string) {
  if (!group || group === "blocked") return item.problems
  return [...item.problems].sort(
    (a, b) =>
      Number(b.review_reason === group) - Number(a.review_reason === group)
  )
}
const batchSchema = z.object({
  id: z.string(),
  case_id: z.string(),
  status: z.string(),
  reading_job_ids: z.array(z.string()).default([]),
  files: z.array(
    z.object({
      source_id: z.string(),
      file_id: z.string(),
      review_file_id: z.string().nullable().optional(),
      filename: z.string(),
      status: z.string(),
      error: z.string().optional(),
      last_progress_at: z.string().optional(),
      last_checked_at: z.string().optional(),
      recovery: recoveryReceipt.nullish(),
    })
  ),
  counts: z.record(z.string(), z.number()),
  available_statements: z.number().optional(),
  available_records: z.number().optional(),
  available_transactions: z.number().optional(),
  available_incomplete: z.number().optional(),
  issues_count: z.number().optional(),
  statements_with_issues: z.number().optional(),
  review_summary: batchReviewSummarySchema.optional(),
  review_group: z.string().nullish(),
  review_group_label: z.string().nullish(),
  operations: z.array(operationSchema).default([]),
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
      created_by: z.string().optional(),
      filenames: z.array(z.string()).optional(),
      checked_files: z.number().optional(),
      failed_files: z.number().optional(),
      completed: z.boolean().default(false),
      available_statements: z.number().optional(),
      statements_with_checks: z.number().optional(),
    })
  ),
})
const labels: Record<string, string> = {
  ready: "Ready to import",
  attention: "Needs attention",
  pending_import: "Import accepted · waiting for completion",
  imported: "Imported",
  duplicate_ignored: "Duplicate - Ignored by system",
  superseded_reading: "Earlier reading retained in history",
  skipped: "Left unimported",
  assigned: "Payments assigned",
}

export function FinancialBatchPanel({ caseId }: { caseId: string }) {
  const [params, setParams] = useSearchParams()
  const batchId = params.get("batch"),
    itemId = params.get("batchItem")
  const reviewGroup = params.get("batchCheck") || ""
  const statementList = useRef<HTMLHeadingElement>(null)
  const readingJobs = useRef<HTMLDivElement>(null)
  const focusStatementList = useRef(false)
  const [offset, setOffset] = useState(0),
    [onlyProblems, setOnlyProblems] = useState(false)
  const client = useQueryClient()
  const { canEdit, canUpload } = useFinancialAccess()
  const user = useAuthStore((state) => state.user)
  const [error, setError] = useState("")
  const [visibleBatches, setVisibleBatches] = useState(8)
  const [showCompleted, setShowCompleted] = useState(false)
  const [selectedBatches, setSelectedBatches] = useState<string[]>([])
  const [submission, setSubmission, clearSubmission] = useFinancialDraft<{
    request_id: string
    expected_ready_revision: string
  } | null>(caseId, `batch-import:${batchId}`, null)
  const [lastRequestId, setLastRequestId] = useFinancialDraft<string | null>(
    caseId,
    `batch-import-result:${batchId}`,
    null
  )
  const [retryingFile, setRetryingFile] = useState<string | null>(null)
  const [retryMessage, setRetryMessage] = useState("")
  const [retryError, setRetryError] = useState("")
  const retryInFlight = useRef(false)
  const prefix = `/api/financial/statement-import/batches`
  const query = useQuery({
    queryKey: [
      "financial-batch",
      caseId,
      batchId,
      offset,
      onlyProblems,
      reviewGroup,
    ],
    enabled: !!batchId,
    queryFn: async () => {
      const result = batchSchema.parse(
        await fetchAPI(
          `${prefix}/${batchId}?case_id=${caseId}&offset=${offset}&only_problems=${onlyProblems}${reviewGroup ? `&review_group=${encodeURIComponent(reviewGroup)}` : ""}`
        )
      )
      if (result.case_id !== caseId || result.id !== batchId)
        throw Error("The batch belongs to another case.")
      return result
    },
    refetchInterval: (query) =>
      ["preparing", "pausing"].includes(query.state.data?.status ?? "") ||
      query.state.data?.operations.some((operation) => operation.pending > 0)
        ? 3000
        : false,
  })
  useEffect(() => {
    if (
      query.data &&
      !query.isFetching &&
      offset > 0 &&
      offset >= query.data.total
    ) {
      setOffset(Math.max(0, Math.ceil(query.data.total / 100) - 1) * 100)
    }
  }, [query.data, query.isFetching, offset])
  useEffect(() => {
    if (
      focusStatementList.current &&
      !query.isFetching &&
      query.data &&
      (query.data.review_group || "") === reviewGroup &&
      !itemId
    ) {
      focusStatementList.current = false
      statementList.current?.focus({ preventScroll: true })
      statementList.current?.scrollIntoView({
        block: "start",
        behavior: "smooth",
      })
    }
  }, [query.data, query.isFetching, reviewGroup, itemId])
  const selectReviewGroup = (group: string) => {
    setOffset(0)
    setOnlyProblems(false)
    focusStatementList.current = true
    setParams((current) => {
      const next = new URLSearchParams(current)
      if (group) next.set("batchCheck", group)
      else next.delete("batchCheck")
      return next
    })
  }
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
      for (const key of [
        "batch",
        "batchItem",
        "batchRow",
        "files",
        "reviewFile",
        "returnBatch",
        "returnBatchCheck",
      ])
        next.delete(key)
      if (batch !== batchId) next.delete("batchCheck")
      if (batch) next.set("batch", batch)
      if (item) next.set("batchItem", item)
      if (row) next.set("batchRow", row)
      return next
    })
  }
  const openStatementFiles = (fileId?: string) => {
    const workspace = useStatementWorkspace.getState()
    const scope = `${user?.id || user?.username || "anonymous"}:${caseId}`
    if (fileId) workspace.select(scope, fileId)
    else workspace.setOpen(scope, false)
    setParams((current) => {
      const next = new URLSearchParams(current)
      next.set("view", "statements")
      next.set("files", "1")
      for (const key of [
        "batch",
        "batchItem",
        "batchRow",
        "batchCheck",
        "reviewFile",
        "returnBatch",
        "returnBatchCheck",
      ])
        next.delete(key)
      if (fileId) {
        next.set("reviewFile", fileId)
        if (batchId) next.set("returnBatch", batchId)
        if (reviewGroup) next.set("returnBatchCheck", reviewGroup)
      }
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
  const control = useMutation({
    mutationFn: (action: "pause" | "resume") =>
      fetchAPI(`${prefix}/${batchId}/control/${action}?case_id=${caseId}`, {
        method: "POST",
      }),
    onSettled: refresh,
  })
  const paused = ["paused", "pausing"].includes(batchState ?? "")
  const retryFile = async (
    file: z.infer<typeof batchSchema>["files"][number]
  ) => {
    if (!canEdit || !canUpload || paused || retryInFlight.current) return
    retryInFlight.current = true
    setError("")
    setRetryError("")
    setRetryMessage("")
    setRetryingFile(file.source_id)
    try {
      const result = z
        .object({ queued: z.boolean(), status: z.string() })
        .merge(recoveryReceipt)
        .parse(
          await fetchAPI(
            `${prefix}/${batchId}/files/${file.source_id}/retry?case_id=${caseId}`,
            { method: "POST" }
          )
        )
      setRetryMessage(
        result.message
          ? `${file.filename}: ${result.message}`
          : result.queued
            ? `Retry accepted for ${file.filename}. Its progress will appear here.`
            : result.status === "checked"
              ? `${file.filename} has already been read. Open its statement review below.`
              : `${file.filename} is already queued or being read. Its progress will appear here.`
      )
    } catch (failure) {
      setRetryError(
        failure instanceof Error
          ? failure.message
          : "The file could not be retried."
      )
    } finally {
      // A lost response can follow a saved server receipt; reread both the
      // batch and its engine jobs before the investigator decides to retry.
      refresh()
      void client.invalidateQueries({ queryKey: ["evidence-jobs", caseId] })
      retryInFlight.current = false
      setRetryingFile(null)
    }
  }
  const retrySource = (job: EvidenceJob) => {
    if (job.case_id !== caseId || !job.evidence_file_id) return undefined
    const matches =
      query.data?.files.filter((file) =>
        [file.source_id, file.file_id, file.recovery?.reading_file_id].includes(
          job.evidence_file_id!
        )
      ) ?? []
    return matches.length === 1 ? matches[0] : undefined
  }
  const checkImport = useMutation({
    retry: false,
    mutationFn: async () => {
      const requestId = submission?.request_id || lastRequestId
      if (!requestId) return null
      const result = z
        .object({
          case_id: z.string(),
          batch_id: z.string(),
          request_id: z.string(),
          operation: operationSchema.nullable(),
        })
        .parse(
          await fetchAPI(
            `${prefix}/${batchId}/operations/${requestId}?case_id=${caseId}`
          )
        )
      if (
        result.case_id !== caseId ||
        result.batch_id !== batchId ||
        result.request_id !== requestId
      )
        throw Error(
          "The import receipt does not match this request. Your saved review is retained."
        )
      return result.operation
    },
    onSuccess: (operation) => {
      if (operation) clearSubmission()
      refresh()
    },
  })
  const confirm = useMutation({
    retry: false,
    mutationFn: () => {
      const request = submission ?? {
        request_id: randomRequestId(),
        expected_ready_revision: query.data!.ready_revision,
      }
      setSubmission(request)
      setLastRequestId(request.request_id)
      checkImport.reset()
      return fetchAPI(`${prefix}/${batchId}/confirm?case_id=${caseId}`, {
        method: "POST",
        body: request,
      })
    },
    onSuccess: () => {
      clearSubmission()
      refresh()
    },
    onError: refresh,
  })
  const updateStatements = useMutation({
    retry: false,
    mutationFn: () =>
      fetchAPI(`${prefix}/${batchId}/refresh-statements?case_id=${caseId}`, {
        method: "POST",
      }),
    onSuccess: refresh,
  })
  const openImported = useMutation({
    mutationFn: async (operationId?: string) => {
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
            `${prefix}/${batchId}/imported-transactions?case_id=${caseId}${operationId ? `&operation_id=${operationId}` : ""}`
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
  const listedBatches = batches.data?.filter(
    (batch) => showCompleted || !batch.completed
  )
  if (!batchId)
    return (
      <section
        className="rounded border p-3 space-y-2"
        aria-label="Financial processing batches"
      >
        <h3 className="font-semibold">Processing batches</h3>
        <p className="text-sm text-muted-foreground">
          Each batch is a separate preparation run. Open a batch to continue its
          saved review. The most recent run is first.
        </p>
        <label className="block text-sm">
          <input
            type="checkbox"
            checked={showCompleted}
            onChange={(e) => {
              setShowCompleted(e.target.checked)
              setVisibleBatches(8)
            }}
          />{" "}
          Show completed batches (history)
        </label>
        {listedBatches?.length === 0 && (
          <p>No active batches. Completed work remains in history.</p>
        )}
        {canEdit && (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={!batches.data?.length}
              onClick={() =>
                setSelectedBatches(
                  listedBatches?.slice(0, visibleBatches).map((b) => b.id) ?? []
                )
              }
            >
              Select all shown batches
            </Button>
            <Button
              variant="ghost"
              size="sm"
              disabled={!selectedBatches.length}
              onClick={() => setSelectedBatches([])}
            >
              Clear batch selection
            </Button>
            <FinancialRemovalAction
              caseId={caseId}
              batchIds={selectedBatches.filter((id) =>
                batches.data?.some((b) => b.id === id)
              )}
              label={`Remove ${selectedBatches.length} selected batches`}
              onRemoved={() => setSelectedBatches([])}
            />
          </div>
        )}
        {batches.isError && <p role="alert">{batches.error.message}</p>}
        {listedBatches?.slice(0, visibleBatches).map((batch, index) => (
          <div
            key={batch.id}
            className="flex flex-wrap items-center justify-between gap-3 rounded border p-3"
          >
            {batch.completed && (
              <span className="text-sm">Completed · retained in history</span>
            )}
            {batch.available_statements !== undefined && (
              <span className="text-sm">
                {batch.available_statements} statements ready to import ·{" "}
                {batch.statements_with_checks || 0} with checks to review
              </span>
            )}
            {canEdit && (
              <input
                type="checkbox"
                aria-label={`Select batch ${batch.id.slice(0, 8)}`}
                checked={selectedBatches.includes(batch.id)}
                onChange={(event) =>
                  setSelectedBatches((ids) =>
                    event.target.checked
                      ? [...ids, batch.id]
                      : ids.filter((id) => id !== batch.id)
                  )
                }
              />
            )}
            <div className="min-w-0 space-y-1">
              <p className="font-medium">
                {batch.file_count} files ·{" "}
                {new Date(batch.created_at).toLocaleString()}
                {index === 0 && (
                  <span className="ml-2 text-xs text-muted-foreground">
                    Latest batch
                  </span>
                )}
              </p>
              <p className="text-sm text-muted-foreground">
                Batch {batch.id.slice(0, 8)}
                {batch.created_by
                  ? ` · Started by ${batch.created_by}`
                  : ""} ·{" "}
                {batch.status === "preparing"
                  ? "Processing continues"
                  : batch.status === "paused"
                    ? "Paused — progress saved"
                    : batch.status === "pausing"
                      ? "Pausing after the current statement"
                      : "Available for review"}
              </p>
              {batch.checked_files !== undefined && (
                <p className="text-sm">
                  {batch.checked_files} of {batch.file_count} files checked
                  {batch.failed_files
                    ? ` · ${batch.failed_files} files could not be read`
                    : ""}
                </p>
              )}
              {!!batch.filenames?.length && (
                <p className="max-w-3xl break-words text-xs text-muted-foreground">
                  {batch.filenames.join(" · ")}
                  {batch.file_count > batch.filenames.length
                    ? ` · and ${batch.file_count - batch.filenames.length} more`
                    : ""}
                </p>
              )}
            </div>
            <Button
              variant="outline"
              size="sm"
              aria-label={`Open batch ${batch.id.slice(0, 8)}`}
              onClick={() => change(batch.id)}
            >
              Open batch
            </Button>
          </div>
        ))}
        {batches.data && batches.data.length > visibleBatches && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setVisibleBatches((count) => count + 8)}
          >
            Show older batches
          </Button>
        )}
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
        <Button variant="outline" onClick={() => openStatementFiles()}>
          Back to statement files
        </Button>
      </div>
    )
  const batch = query.data
  const displayItems = batch.items
    .filter((item) => !["removed", "superseded_reading"].includes(item.status))
    .map((item) => ({
      ...item,
      problems: reviewProblems(item, reviewGroup),
    }))
  const problems = batch.issues_count ?? batch.counts.attention ?? 0
  const available = batch.available_statements ?? batch.counts.ready ?? 0
  const availableRecords = batch.available_records ?? batch.ready_transactions
  const availablePayments = batch.available_transactions ?? availableRecords
  const incompleteRecords = batch.available_incomplete ?? 0
  return (
    <section aria-label="Financial processing batch" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">
            Prepare statements for import
          </h2>
          <p className="text-sm text-muted-foreground">
            {batch.status === "paused"
              ? "Batch preparation and imports are paused. Saved progress and pending imports will continue when you resume."
              : batch.status === "pausing"
                ? "Pausing after the current statement finishes. No further statements or imports will start."
                : "Preparation and imports continue on the server. You can leave this page and return to the batch."}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canEdit &&
            ["preparing", "pausing", "paused"].includes(batch.status) && (
              <Button
                variant="outline"
                disabled={control.isPending || batch.status === "pausing"}
                onClick={() =>
                  control.mutate(batch.status === "paused" ? "resume" : "pause")
                }
              >
                {batch.status === "paused"
                  ? "Resume batch preparation"
                  : batch.status === "pausing"
                    ? "Finishing current statement…"
                    : "Pause batch preparation"}
              </Button>
            )}
          <FinancialRemovalAction
            caseId={caseId}
            batchIds={[batchId]}
            label="Remove this batch / imports"
          />
          {importedCount > 0 && (
            <Button
              disabled={openImported.isPending}
              onClick={() => openImported.mutate(undefined)}
            >
              {openImported.isPending
                ? "Opening imported payments…"
                : "Open imported transactions"}
            </Button>
          )}
          <Button variant="outline" onClick={() => openStatementFiles()}>
            Back to all statements
          </Button>
        </div>
      </div>
      {control.isError && <p role="alert">{control.error.message}</p>}
      {paused && (
        <p role="status" className="rounded border p-3">
          {batch.status === "pausing"
            ? "Pause requested. The current statement is finishing safely."
            : "Paused. No pending imports will start until you resume."}{" "}
          You can still review statements. PDF readings already running have
          separate pause controls below.
        </p>
      )}
      <div ref={readingJobs}>
        <BatchReadingJobs
          caseId={caseId}
          jobIds={batch.reading_job_ids}
          canEdit={canEdit}
          canRetryJob={(job) => !!retrySource(job)}
          onRetry={
            canUpload
              ? (job) => {
                  const source = retrySource(job)
                  if (source) void retryFile(source)
                  else
                    setRetryError(
                      "This reading is no longer linked to one file in this batch. Refresh the batch before retrying."
                    )
                }
              : undefined
          }
          retrying={!!retryingFile}
          retryDisabledReason={
            paused
              ? "Resume batch preparation before retrying a file."
              : undefined
          }
          retryMessage={retryMessage}
          retryError={retryError}
        />
      </div>
      {openImported.isError && <p role="alert">{openImported.error.message}</p>}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          [
            "PDFs read",
            `${batch.files.filter((f) => f.status === "checked").length} of ${batch.files.length}`,
          ],
          ["Statement periods available to import", available],
          [
            batch.review_summary ? "Cannot import yet" : "Review checks",
            batch.review_summary
              ? String(batch.review_summary.blocked_statements)
              : `${problems}${batch.statements_with_issues !== undefined ? ` across ${batch.statements_with_issues} statements` : ""}`,
          ],
          ["Statement periods imported", batch.counts.imported || 0],
        ].map(([title, value]) => (
          <div
            className={`rounded border p-3 ${(title === "Review checks" && problems) || (title === "Cannot import yet" && batch.review_summary?.blocked_statements) ? "border-amber-400 bg-amber-50/60 dark:bg-amber-950/20" : "bg-card"}`}
            key={title}
          >
            <p className="text-sm text-muted-foreground">{title}</p>
            <p className="text-2xl font-semibold">{value}</p>
          </div>
        ))}
      </div>
      {batch.review_summary && (
        <BatchReviewSummary
          summary={batch.review_summary}
          selected={reviewGroup}
          onSelect={selectReviewGroup}
        />
      )}
      {canEdit && (
        <div className="flex flex-wrap items-center gap-3 rounded border p-3">
          <BulkStatementDetails
            caseId={caseId}
            batchId={batchId}
            onSaved={refresh}
          />
          <p className="text-sm text-muted-foreground">
            Select statements from this batch to fill or correct account details
            together. Preview changes before saving.
          </p>
        </div>
      )}
      <p className="text-sm text-muted-foreground">
        Reading a PDF prepares its statements. Importing saves their payments to
        Transactions. An imported statement may still have checks to review;
        these are separate counts.
      </p>
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
      {(reviewGroup || onlyProblems) && (
        <p className="text-sm">
          Import covers all available statements in this batch, including
          statements outside the review filter.
        </p>
      )}
      <div className="rounded border bg-card p-4 flex flex-wrap gap-3 items-center justify-between">
        <div>
          <p className="font-medium">
            {available} {available === 1 ? "statement" : "statements"} available
            · {availablePayments} transactions
            {incompleteRecords
              ? ` · ${incompleteRecords} incomplete records`
              : ""}
          </p>
          <p className="text-sm text-muted-foreground">
            {incompleteRecords
              ? "Incomplete records will be saved separately for review and kept outside totals."
              : "Account details, statement balances and transaction sources will be saved together."}{" "}
            Text not identified as a payment stays with the original statement.
          </p>
        </div>
        <Button
          disabled={!canEdit || !available || confirm.isPending || paused}
          onClick={() => confirm.mutate()}
        >
          {confirm.isPending
            ? "Submitting import…"
            : !available
              ? "No new statements to import"
              : !availableRecords
                ? `Save ${available} ${available === 1 ? "statement" : "statements"}`
                : incompleteRecords
                  ? `Import ${availablePayments} transactions and ${incompleteRecords} incomplete records`
                  : `Import ${availablePayments} transactions`}
        </Button>
      </div>
      {(confirm.isError || error) && (
        <div role="alert">
          <p>{confirm.error?.message || error}</p>
          {confirm.isError && (
            <>
              <p>
                Check the import results below before trying again. Your PDFs
                and saved reviews are retained.
              </p>
            </>
          )}
        </div>
      )}
      {(lastRequestId || submission || confirm.isError) && (
        <div
          className="rounded border p-3 space-y-2"
          aria-label="Check the last import"
        >
          <Button
            variant="outline"
            disabled={checkImport.isPending || confirm.isPending}
            onClick={() => checkImport.mutate()}
          >
            {checkImport.isPending ? "Checking import…" : "Check import result"}
          </Button>
          {checkImport.isError && (
            <p role="alert">
              The import result could not be checked:{" "}
              {checkImport.error.message} Your request is retained. Check again
              before submitting another import.
            </p>
          )}
          {checkImport.isSuccess && (
            <p role="status">
              {!checkImport.data
                ? "No accepted import was found for this request. Your saved review is retained; you can submit it again."
                : checkImport.data.pending
                  ? `Import accepted: ${checkImport.data.pending} statements are still being processed. ${checkImport.data.imported} imported so far.`
                  : checkImport.data.failed
                    ? `Import finished: ${checkImport.data.imported} imported and ${checkImport.data.failed} need review. Open the affected statements in Import results below.`
                    : `Import complete: ${checkImport.data.imported} imported, ${checkImport.data.already_present} already included, ${checkImport.data.duplicate_ignored} duplicates ignored. ${checkImport.data.transaction_count} transactions saved.`}
            </p>
          )}
          {checkImport.isSuccess &&
            !checkImport.data &&
            submission &&
            submission.expected_ready_revision !== batch.ready_revision && (
              <Button
                variant="outline"
                onClick={() => {
                  clearSubmission()
                  checkImport.reset()
                  refresh()
                }}
              >
                Review the updated import selection
              </Button>
            )}
        </div>
      )}
      {batch.operations.length > 0 && (
        <section
          aria-label="Import results"
          className="rounded border bg-card p-4 space-y-3"
        >
          <h3 className="font-semibold">Import results</h3>
          <p className="text-sm">
            The latest 20 import receipts are shown here. They are saved with
            the batch when you leave this page.
          </p>
          {batch.operations.map((operation, index) => (
            <details
              key={operation.id}
              open={index === 0}
              className="rounded border p-3"
            >
              <summary className="cursor-pointer font-medium">
                {operation.status === "in_progress"
                  ? "Import accepted — still running"
                  : operation.status === "needs_review"
                    ? "Import finished with statements to review"
                    : "Import complete"}{" "}
                · {new Date(operation.created_at).toLocaleString()}
              </summary>
              <p
                role={operation.pending ? "status" : undefined}
                className="my-2 text-sm"
              >
                {operation.statement_count} statements submitted ·{" "}
                {operation.duplicate_ignored > 0 && (
                  <>{operation.duplicate_ignored} duplicates ignored · </>
                )}
                {operation.imported} imported · {operation.already_present}{" "}
                already included · {operation.pending} pending ·{" "}
                {operation.failed} need review. {operation.transaction_count}{" "}
                saved transactions · {operation.incomplete_count} incomplete
                readings outside totals.
              </p>
              {(operation.imported > 0 || operation.already_present > 0) && (
                <Button
                  variant="outline"
                  disabled={openImported.isPending}
                  onClick={() => openImported.mutate(operation.id)}
                >
                  View transactions from this import
                </Button>
              )}
              <ul className="mt-2 max-h-64 overflow-auto divide-y">
                {operation.outcomes.map((outcome) => (
                  <li key={outcome.item_id} className="py-2 text-sm">
                    <span>
                      {outcome.filename} ·{" "}
                      {outcome.period_start || "Start unknown"} to{" "}
                      {outcome.period_end || "End unknown"} ·{" "}
                      {{
                        queued: "Accepted — waiting for import",
                        importing: "Importing",
                        imported: "Imported",
                        duplicate_ignored: "Duplicate - Ignored by system",
                        already_present:
                          "Already included — no duplicate added",
                        failed: "Not imported — review required",
                      }[outcome.status] || outcome.status}
                    </span>
                    {outcome.message && <p>{outcome.message}</p>}
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => change(batchId, outcome.item_id)}
                    >
                      {outcome.status === "failed"
                        ? "Review and retry this statement"
                        : "Open statement"}
                    </Button>
                  </li>
                ))}
              </ul>
            </details>
          ))}
        </section>
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
                checked: "PDF read — see statement import status below",
                error: "Needs attention",
              }[file.status] ?? file.status}
              {file.last_progress_at && (
                <p className="text-xs text-muted-foreground">
                  Last stage change:{" "}
                  {new Date(file.last_progress_at).toLocaleString()}
                  {file.status === "processing"
                    ? ". Waiting for the PDF reading to finish; this is not import completion."
                    : ""}
                </p>
              )}
              {file.recovery?.message && (
                <p className="mt-1 text-sm" role="status">
                  {file.recovery.message}
                </p>
              )}
              <>
                {file.error && <p role="alert">{file.error}</p>}
                <div className="flex gap-2 mt-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={file.review_file_id === null}
                    onClick={() => {
                      openStatementFiles(
                        file.recovery?.review_file_id ||
                          file.review_file_id ||
                          file.file_id
                      )
                    }}
                  >
                    Open file review
                  </Button>
                  {canEdit && canUpload && (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={!!retryingFile || paused}
                      onClick={() => void retryFile(file)}
                    >
                      {retryingFile === file.source_id
                        ? "Requesting retry…"
                        : file.error
                          ? file.recovery?.action === "source_unavailable"
                            ? "Check source again"
                            : "Retry this file"
                          : "Check reading"}
                    </Button>
                  )}
                  {file.recovery?.action === "source_unavailable" && (
                    <Button variant="outline" size="sm" asChild>
                      <Link
                        to={`/cases/${encodeURIComponent(caseId)}/evidence`}
                      >
                        Find source in Evidence
                      </Link>
                    </Button>
                  )}
                  {file.recovery?.action === "resume_reading" && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        const details =
                          readingJobs.current?.querySelector("details")
                        if (details) details.open = true
                        const summary = details?.querySelector("summary")
                        summary?.focus({ preventScroll: true })
                        summary?.scrollIntoView({
                          block: "center",
                          behavior: "smooth",
                        })
                      }}
                    >
                      Open reading jobs to resume
                    </Button>
                  )}
                </div>
              </>
            </li>
          ))}
        </ul>
        {retryMessage && <p role="status">{retryMessage}</p>}
        {retryError && <p role="alert">{retryError}</p>}
        {paused && (
          <p className="text-sm">Resume PDF reading before retrying a file.</p>
        )}
      </details>
      <div className="flex flex-wrap items-center gap-3">
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
        {canEdit && (
          <Button
            variant="outline"
            size="sm"
            disabled={
              query.data.status === "preparing" ||
              paused ||
              updateStatements.isPending
            }
            onClick={() => updateStatements.mutate()}
          >
            {updateStatements.isPending
              ? "Updating statement list…"
              : "Check for additional statement periods"}
          </Button>
        )}
        {updateStatements.isError && (
          <p role="alert">{updateStatements.error.message}</p>
        )}
      </div>
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h3
            ref={statementList}
            tabIndex={-1}
            className="font-semibold scroll-mt-24"
          >
            {reviewGroup
              ? `Statements: ${batch.review_group_label || (reviewGroup === "blocked" ? "Cannot be imported yet" : batch.review_summary?.groups.find((g) => g.id === reviewGroup)?.label || "Selected review reason")}`
              : "Statements in this batch"}
          </h3>
          {reviewGroup && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => selectReviewGroup("")}
            >
              Clear reason filter
            </Button>
          )}
        </div>
        {canEdit && (
          <BulkStatementDetails
            caseId={caseId}
            batchId={batchId}
            datesOnly
            onSaved={refresh}
          />
        )}
        {canEdit && (
          <BatchCurrencyEditor
            key={batchId}
            caseId={caseId}
            batchId={batchId}
            onSaved={refresh}
          />
        )}
        {displayItems.map((item) => (
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
                    ` · ${item.problem_count ?? item.problems.length} checks`}
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
                    (reviewGroup && reviewGroup !== "blocked"
                      ? item.problems.find(
                          (p) => p.review_reason === reviewGroup
                        )?.row_id
                      : item.problems.find((p) => p.row_id)?.row_id) ??
                      undefined
                  )
                }
              >
                {item.status === "attention"
                  ? "Review problems"
                  : "Open statement"}
              </Button>
              {canEdit &&
                !["pending_import", "assigned"].includes(item.status) && (
                  <BulkStatementDetails
                    caseId={caseId}
                    fileIds={[item.file_id]}
                    statementId={item.statement_id || null}
                    datesOnly
                    onSaved={refresh}
                  />
                )}
              {canEdit &&
                item.currency &&
                !["pending_import", "skipped", "assigned"].includes(
                  item.status
                ) && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => change(batchId, item.id)}
                  >
                    Edit account, dates, currency and balances
                  </Button>
                )}
            </div>
            {!item.currency && item.status === "attention" && canEdit && (
              <label className="block text-sm">
                Statement currency{" "}
                <select
                  aria-label={`Currency for ${item.filename}`}
                  className="rounded border bg-background p-2"
                  defaultValue=""
                  disabled={batch.status === "preparing" || paused}
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
            {item.duplicate_disposition?.status === "ignored" && (
              <p className="text-sm">
                {item.duplicate_disposition.reason}{" "}
                {item.duplicate_disposition.retained && (
                  <>
                    Retained statement:{" "}
                    <strong>
                      {item.duplicate_disposition.retained.filename}
                    </strong>
                    . Open this review to inspect or restore the copy.
                  </>
                )}
              </p>
            )}
            {item.admission?.calculation &&
              item.status !== "duplicate_ignored" && (
                <StatementReconciliationSummary
                  calculation={item.admission.calculation}
                  compact
                  format={(minor) =>
                    `${formatLedgerAmount(minor, item.currency || "").text} ${item.currency || ""}`
                  }
                />
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
              ![
                "imported",
                "pending_import",
                "assigned",
                "duplicate_ignored",
              ].includes(item.status) && (
                <BatchStatementImportChoice
                  caseId={caseId}
                  batchId={batchId}
                  itemId={item.id}
                  revision={item.disposition_revision}
                  skipped={item.status === "skipped"}
                  refresh={refresh}
                />
              )}
            {!!item.unclassified_count && (
              <p className="text-sm text-muted-foreground">
                {item.unclassified_count} lines of other extracted text are
                retained with the statement, outside the transaction count. Open
                the statement to inspect them or add a missed payment.
              </p>
            )}
            {item.problems.length > 0 && (
              <>
                {item.problems.length > 3 && (
                  <p className="text-sm">{item.problems[0].message}</p>
                )}
                <details open={item.problems.length <= 3} className="text-sm">
                  <summary className="cursor-pointer font-medium">
                    {item.problems.every(
                      (problem) => problem.kind === "statement_detail"
                    ) && item.problems.length
                      ? "Missing account details — statement can still be imported"
                      : !item.currency
                        ? "Choose currency to prepare this statement"
                        : `${item.problem_count ?? item.problems.length} checks · ${item.can_import ? "import is available" : "open review for the next step"}`}
                  </summary>
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
                          onClick={() =>
                            change(batchId, item.id, problem.row_id!)
                          }
                        >
                          Go to this row
                        </Button>
                      )}
                      {!problem.row_id &&
                        ["holder", "account_number", "period"].includes(
                          problem.field || ""
                        ) && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => change(batchId, item.id)}
                          >
                            Edit{" "}
                            {problem.field === "holder"
                              ? "account holder"
                              : problem.field === "account_number"
                                ? "account number"
                                : "statement dates"}
                          </Button>
                        )}
                    </div>
                  ))}
                  {(item.problem_count ?? 0) > item.problems.length && (
                    <p>Open the statement to review the remaining checks.</p>
                  )}
                </details>
              </>
            )}
          </article>
        ))}
      </div>
      {!batch.items.length && (
        <p>
          {batch.status === "preparing"
            ? "Statements will appear here as each file is checked."
            : reviewGroup
              ? "No statements match this reason now. Clear the reason filter to see the rest of the batch."
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
  const [params, setParams] = useSearchParams()
  const reviewGroup = params.get("batchCheck") || ""
  const reviewGroupQuery = reviewGroup
    ? `&review_group=${encodeURIComponent(reviewGroup)}`
    : ""
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
  const [savedBalances, setSavedBalances] = useState(false)
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
  const beforeNavigate = useRef<(() => Promise<unknown>) | null>(null)
  const [navigating, setNavigating] = useState(false)
  const [navigationStatus, setNavigationStatus] = useState("")
  const adjacentStatement = async (direction: "next" | "previous") => {
    setNavigating(true)
    setNavigationError("")
    setNavigationStatus("")
    try {
      await beforeNavigate.current?.()
      const result = z
        .object({
          case_id: z.string(),
          batch_id: z.string(),
          item_id: z.string().nullable(),
          position: z.number(),
          total: z.number(),
        })
        .parse(
          await fetchAPI(
            `/api/financial/statement-import/batches/${batchId}/items/${itemId}/next-statement?case_id=${caseId}&direction=${direction}${reviewGroupQuery}`
          )
        )
      if (result.case_id !== caseId || result.batch_id !== batchId)
        throw Error("The statement belongs to another batch.")
      if (!result.item_id) {
        setNavigationStatus(
          reviewGroup
            ? "No further statements match this review reason. Return to the batch to see the updated checks."
            : `You are at the ${direction === "next" ? "last" : "first"} statement (${result.position} of ${result.total}).`
        )
        return
      }
      setParams((current) => {
        const next = new URLSearchParams(current)
        next.set("batchItem", result.item_id!)
        next.delete("batchRow")
        return next
      })
    } catch (error) {
      setNavigationError(
        error instanceof Error
          ? error.message
          : "The next statement could not be opened. Your edits are retained."
      )
    } finally {
      setNavigating(false)
    }
  }
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
            `/api/financial/statement-import/batches/${batchId}/items/${itemId}/next-problem?case_id=${caseId}&direction=${direction}${reviewGroupQuery}`
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
      <div
        className="flex flex-wrap gap-2 items-center sticky top-0 z-10 bg-background p-2 border rounded"
        aria-label="Review batch statements"
      >
        <Button
          variant="outline"
          disabled={!item || navigating}
          onClick={() => void adjacentStatement("previous")}
        >
          Previous statement
        </Button>
        <Button
          variant="outline"
          disabled={!item || navigating}
          onClick={() => void adjacentStatement("next")}
        >
          Next statement
        </Button>
        <span className="text-sm">
          {navigating
            ? "Saving review and opening statement…"
            : "Review drafts are saved before moving. Save changes separately when editing an imported statement."}
        </span>
        {navigationStatus && <p role="status">{navigationStatus}</p>}
      </div>
      {reviewGroup && (
        <p className="text-sm">
          Previous and next stay within the selected review reason. Return to
          the batch to change or clear this filter.
        </p>
      )}
      {item?.status === "skipped" && (
        <p className="rounded border p-3">
          This statement was left unimported. Return to the batch and choose
          Restore to review to edit or import it. {item.import_decision?.reason}
        </p>
      )}
      {navigationError && <p role="alert">{navigationError}</p>}
      {savedBalances && (
        <p role="status" className="rounded border p-3">
          Statement balances saved. This statement has no payments to show in
          Transactions. You can check its saved account and balances below or
          return to the batch.
        </p>
      )}
      {query.isError ? (
        <p role="alert">{query.error.message}</p>
      ) : !item || !selected ? (
        <p role="status">Opening statement…</p>
      ) : (
        <BatchReviewContext.Provider
          value={{
            batchId,
            beforeNavigate,
            rowId,
            field: !rowId
              ? (reviewProblems(item, reviewGroup).find(
                  (problem) =>
                    (!reviewGroup ||
                      reviewGroup === "blocked" ||
                      problem.review_reason === reviewGroup) &&
                    ["holder", "account_number", "period"].includes(
                      problem.field || ""
                    )
                )?.field as "holder" | "account_number" | "period" | undefined)
              : undefined,
            draftRevision: item.review_revision,
            save,
            confirm: (request) =>
              fetchAPI(
                `/api/financial/statement-import/batches/${batchId}/items/${itemId}/confirm?case_id=${caseId}`,
                {
                  method: "POST",
                  body: {
                    request,
                    expected_review_revision: reviewRevision.current,
                  },
                  timeout: 120000,
                }
              ),
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
              if ((receipt?.record_count ?? receipt?.transaction_count) === 0) {
                setSavedBalances(true)
                void client.invalidateQueries()
                return
              }
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
