import { useStatementCoverageReview } from "../hooks/use-statement-coverage-review"
import { StatementCoverageReview } from "./StatementCoverageReview"
import { useBatchReview } from "../lib/batch-review-context"
import { useStatementFiles } from "../hooks/use-statement-register"
import {
  StatementPeriodSelect,
  StatementSectionPicker,
} from "./StatementSectionPicker"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { statementRowLocator } from "../lib/statement-row-locator"
import { useStatementChecks } from "../hooks/use-statement-checks"
import { StatementArithmeticChecks } from "./StatementArithmeticChecks"
import { ReprocessStatement } from "./ReprocessStatement"
import { newReviewId } from "../lib/statement-review-id"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import {
  readStatementDraft,
  saveStatementDraft,
  serverStatementDraft,
} from "../lib/statement-review-draft"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { PdfReviewIntake } from "./PdfReviewIntake"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"
import { StatementRowEditor } from "./StatementRowEditor"
import { StatementBulkCorrections } from "./StatementBulkCorrections"
import { StatementRowAssignment } from "./StatementRowAssignment"
import { SavedReviewConflict } from "./SavedReviewConflict"
import { PreviousStatementReviews } from "./PreviousStatementReviews"
import { reviewRecoverySchema } from "../lib/review-recovery"
import { PrintedStatementTable } from "./PrintedStatementTable"
import { PaymentDocumentReview } from "./PaymentDocumentReview"
import { paymentDocumentProposal } from "../lib/payment-document"
import {
  additionalDateValues,
  dateLabels,
  primaryDateRole,
  sourceDateRoles,
  type DateRole,
} from "../lib/statement-date-fields"
import { useStatementWorkspace } from "../stores/statement-workspace"
import { useUIStore } from "@/stores/ui.store"

const cell = z.object({
  column_index: z.number(),
  expected_text: z.string(),
  locator: z.unknown(),
})
const row = z.object({
  id: z.string(),
  page_number: z.number(),
  table_index: z.number(),
  row_index: z.number(),
  source_cells: z.array(cell),
  fields: z.record(z.string(), z.string()),
  issues: z.array(z.string()),
  excluded: z.boolean(),
  kind: z.string(),
})
const proposalSchema = z.object({
  document_review: paymentDocumentProposal.optional(),
  reading_failure: z.string().nullish(),
  case_id: z.string(),
  evidence_file_id: z.string(),
  filename: z.string(),
  currency: z.string(),
  revision: z.string(),
  review_recovery: reviewRecoverySchema.nullish(),
  row_assignments: z
    .array(
      z.object({
        row_id: z.string(),
        original_statement_id: z.string(),
        target_statement_id: z.string(),
      })
    )
    .default([]),
  saved_review: z
    .object({
      review_revision: z.string(),
      request: z.record(z.string(), z.unknown()),
      saved_at: z.string(),
      saved_by: z.object({ name: z.string() }),
    })
    .nullish(),
  previous_saved_review: z
    .object({
      request: z.record(z.string(), z.unknown()),
      evidence_file_id: z.string(),
      filename: z.string(),
    })
    .nullish(),
  metadata: z.object({
    account_closure: z
      .object({
        date: z.string(),
        page_number: z.number().int().positive(),
        table_index: z.number().int().nonnegative(),
        row_index: z.number().int(),
        source_cells: z.array(
          z.object({ expected_text: z.string(), locator: z.unknown() })
        ),
      })
      .optional(),
    account_type: z.string().optional(),
    balance_convention: z.enum(["asset_balance", "liability_owed"]).optional(),
    institution: z.string(),
    holder: z.string(),
    account_number: z.string(),
    period: z.string(),
    period_start: z.string(),
    period_end: z.string(),
  }),
  rows: z.array(row),
  issues: z.array(z.string()),
  transaction_count: z.number(),
  can_import_balances: z.boolean().default(false),
  can_record_account_closure: z.boolean().default(false),
  assignment_only: z.boolean().default(false),
  printed_main_account: z.string().default(""),
  needs_attention: z.number(),
  page_numbers: z.array(z.number()).default([]),
  unassigned_page_numbers: z.array(z.number()).default([]),
  information_pages: z
    .array(z.object({ page_number: z.number(), kind: z.string() }))
    .default([]),
  statement_id: z.string().nullable().optional(),
  statement_choices: z
    .array(
      z.object({
        id: z.string(),
        institution: z.string(),
        layout_id: z.string().optional(),
        account_reference: z.string(),
        account_label: z.string().optional(),
        assignment_only: z.boolean().optional(),
        document_kind: z.literal("deposit_receipt").optional(),
        statement_date: z.string().optional(),
        printed_statement_date: z.string().optional(),
        period_start: z.string(),
        period_end: z.string(),
        page_numbers: z.array(z.number()),
        checks: z
          .object({
            balance_status: z.enum(["matches", "difference", "unavailable"]),
            flagged_rows: z.number(),
            has_difference: z.boolean().optional(),
            transaction_count: z.number().optional(),
          })
          .optional(),
      })
    )
    .default([]),
  current_import: z
    .object({
      source_document_id: z.string(),
      evidence_file_id: z.string(),
      account_id: z.string().nullable().optional(),
      filename: z.string().nullable().optional(),
      revision: z.string(),
      transaction_count: z.number(),
      excluded_as_duplicate: z.boolean().default(false),
      retained_filename: z.string().nullable().optional(),
      details_reason: z.string().default(""),
      review_decisions: z
        .array(
          z.object({
            description: z.string(),
            date: z.string(),
            excluded: z.boolean(),
            reason: z.string(),
          })
        )
        .default([]),
    })
    .nullable()
    .optional(),
})
export type StatementImportReceipt = {
  case_id: string
  evidence_file_id: string
  source_document_id?: string
  account_id?: string
  transaction_count: number
  filename?: string
  account_closed_on?: string | null
}
type Proposal = z.infer<typeof proposalSchema>
type Edit = {
  id: string
  excluded: boolean
  manual_page?: number | null
  date: string
  date_unprinted?: boolean
  date_values?: Partial<Record<DateRole, string>>
  description: string
  counterparty: string
  amount_minor: string
  direction: "credit" | "debit" | ""
  balance_minor: string | null
  reason: string
}
const receipt = z.object({
  case_id: z.string(),
  evidence_file_id: z.string(),
  transaction_count: z.number(),
  source_document_id: z.string().optional(),
  account_id: z
    .string()
    .nullish()
    .transform((value) => value ?? undefined),
  applied: z.literal(true),
  account_closed_on: z.string().nullable().optional(),
})

function initialRows(data: Proposal): Edit[] {
  return data.rows.map((r) => ({
    id: r.id,
    excluded: r.excluded,
    date: r.fields.date || r.fields.booking_date || r.fields.value_date || "",
    date_unprinted: r.fields.date_basis === "statement_end_ordering_only",
    date_values: additionalDateValues(r.fields),
    description: r.fields.description || "",
    counterparty: r.fields.counterparty || "",
    amount_minor: r.fields.amount_minor || (r.excluded ? "0" : ""),
    direction:
      r.fields.direction === "debit" || r.fields.direction === "credit"
        ? r.fields.direction
        : "",
    balance_minor: r.fields.balance ?? null,
    reason: "",
  }))
}
function exponent(currency: string) {
  return (
    new Intl.NumberFormat("en", {
      style: "currency",
      currency,
    }).resolvedOptions().maximumFractionDigits ?? 2
  )
}
function displayAmount(value: string, digits: number) {
  if (!/^-?\d+$/.test(value)) return value
  const sign = value.startsWith("-") ? "-" : "",
    raw = value.replace("-", "").padStart(digits + 1, "0")
  return (
    sign + (digits ? raw.slice(0, -digits) + "." + raw.slice(-digits) : raw)
  )
}
function minorAmount(value: string, digits: number) {
  if (!new RegExp(`^\\d+(?:\\.\\d{0,${digits}})?$`).test(value)) return ""
  const [whole, fraction = ""] = value.split(".")
  return BigInt(whole + fraction.padEnd(digits, "0")).toString()
}

export function StatementImportPanel({
  caseId,
  onImported,
}: {
  caseId: string | undefined
  onImported: (result?: StatementImportReceipt) => void
}) {
  const batchReview = useBatchReview()
  const { canEdit, canUpload } = useFinancialAccess()
  const owner = useAuthStore(
    (state) => state.user?.id || state.user?.username || "anonymous"
  )
  const scope = `${owner}:${caseId}`
  const open = useStatementWorkspace(
    (state) => state.selections[scope]?.open ?? false
  )
  const fileId = useStatementWorkspace(
    (state) => state.selections[scope]?.fileId ?? null
  )
  const setOpen = (value: boolean) =>
    useStatementWorkspace.getState().setOpen(scope, value)
  const setFileId = (value: string | null) =>
    useStatementWorkspace.getState().select(scope, value)
  const [upload, setUpload] = useState(false)
  const files = useStatementFiles(caseId, false, [], true, open)
  const selectedFile = files.data?.find((file) => file.id === fileId)

  useEffect(() => {
    if (selectedFile?.financial_removed) {
      useStatementWorkspace.getState().select(scope, null)
      useStatementWorkspace.getState().setOpen(scope, false)
    }
  }, [scope, selectedFile?.financial_removed])
  if (!caseId) return null
  return (
    <section
      aria-label="Statement import"
      className="rounded-lg border bg-card p-4 space-y-3"
    >
      {!batchReview && (
        <div className="flex flex-wrap justify-between items-center gap-3">
          <div>
            <h2 className="font-semibold">Bank statements</h2>
            <p className="text-sm text-muted-foreground">
              {canEdit
                ? "Add a statement, check any problems, then import its transactions."
                : "Open a statement to compare its extracted values with the original PDF."}
            </p>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => useUIStore.getState().expandGraphPanelTo("detail")}
            >
              Statement files
            </Button>
            <Button onClick={() => setOpen(!open)}>
              {open
                ? "Close statement review"
                : canEdit
                  ? "Import a statement"
                  : "Open statements"}
            </Button>
          </div>
        </div>
      )}
      <div hidden={!open && !batchReview}>
        {open && !batchReview && (
          <div className="space-y-3">
            {canUpload && (
              <Button variant="outline" onClick={() => setUpload((v) => !v)}>
                Upload a statement
              </Button>
            )}
            {upload && (
              <PdfReviewIntake
                caseId={caseId}
                automaticReview
                onReady={(id) => {
                  if (id) {
                    setFileId(id)
                    setUpload(false)
                    void files.refetch()
                  }
                }}
              />
            )}
            {files.isError && (
              <p role="alert">
                Statements could not be loaded. {files.error.message}
              </p>
            )}
            <label className="block text-sm">
              Or open an uploaded statement
              <select
                aria-label="Uploaded statement"
                className="block border rounded bg-background p-2 w-full"
                value={fileId || ""}
                onChange={(e) => setFileId(e.target.value || null)}
              >
                <option value="">Choose a statement</option>
                {files.data
                  ?.filter((f) => !f.financial_removed)
                  .map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.original_filename}
                      {(files.data?.filter(
                        (other) =>
                          other.original_filename === f.original_filename
                      ).length ?? 0) > 1
                        ? ` · added ${f.created_at ? new Date(f.created_at).toLocaleString() : "at unknown time"} · ${f.id.slice(-6)}`
                        : ""}
                      {f.status !== "processed" ? ` (${f.status})` : ""}
                    </option>
                  ))}
              </select>
            </label>
          </div>
        )}
        {fileId && (
          <StatementReview
            key={`${caseId}:${fileId}`}
            caseId={caseId}
            fileId={fileId}
            onReprocessed={(id) => {
              setFileId(id)
              void files.refetch()
            }}
            onImported={(result) => {
              setOpen(false)
              onImported(result)
            }}
          />
        )}
      </div>
    </section>
  )
}

function StatementReview({
  caseId,
  fileId,
  onImported,
  onReprocessed,
}: {
  caseId: string
  fileId: string
  onImported: (result?: StatementImportReceipt) => void
  onReprocessed: (id: string) => void
}) {
  const batchReview = useBatchReview()
  const { canEdit } = useFinancialAccess()
  const owner = useAuthStore(
    (state) => state.user?.id || state.user?.username || "anonymous"
  )
  const choiceKey = `${owner}:${caseId}:${fileId}`
  const currency = useStatementWorkspace(
    (state) => state.reviewChoices[choiceKey]?.currency ?? ""
  )
  const statementId = useStatementWorkspace(
    (state) => state.reviewChoices[choiceKey]?.statementId ?? ""
  )
  const setCurrency = (currency: string) =>
    useStatementWorkspace.getState().setReviewChoice(choiceKey, { currency })
  const setStatementId = (statementId: string) =>
    useStatementWorkspace.getState().setReviewChoice(choiceKey, { statementId })
  const query = useQuery({
    queryKey: ["statement-import", caseId, fileId, currency, statementId],
    retry: false,
    refetchOnWindowFocus: false,
    queryFn: async () => {
      const params = new URLSearchParams({ case_id: caseId })
      if (currency) params.set("currency", currency)
      if (statementId) params.set("statement_id", statementId)
      const data = proposalSchema.parse(
        await fetchAPI(`/api/financial/statement-import/${fileId}?${params}`)
      )
      if (data.case_id !== caseId || data.evidence_file_id !== fileId)
        throw Error("The review belongs to another statement.")
      return data
    },
  })
  if (query.isPending)
    return (
      <p role="status" className="py-4">
        Reading the statement and checking its transactions…
      </p>
    )
  if (query.isError)
    return (
      <div className="py-4 space-y-2">
        <p role="alert">{query.error.message}</p>
        <Button onClick={() => void query.refetch()}>
          Retry statement review
        </Button>
        {currency && (
          <Button variant="outline" onClick={() => setCurrency("")}>
            Change currency
          </Button>
        )}
        <ReprocessStatement
          key={fileId}
          caseId={caseId}
          fileId={fileId}
          onReady={onReprocessed}
        />
      </div>
    )
  if (query.data.reading_failure)
    return (
      <FailedStatementReading
        caseId={caseId}
        fileId={fileId}
        data={query.data}
        onReady={onReprocessed}
      />
    )
  const hasReceipts = query.data.statement_choices.some(
    (item) => item.document_kind === "deposit_receipt"
  )
  if (query.data.document_review) {
    const document = query.data.document_review
    if (document.case_id !== caseId || document.evidence_file_id !== fileId)
      return (
        <p role="alert">
          The document review does not match this case and file.
        </p>
      )
    return (
      <div className="space-y-3">
        {!batchReview && query.data.statement_choices.length > 1 && (
          <Button variant="outline" onClick={() => setStatementId("")}>
            Choose another statement or receipt
          </Button>
        )}
        <PaymentDocumentReview key={document.revision} data={document} />
      </div>
    )
  }
  if (query.data.statement_choices.length > 1 && !query.data.statement_id)
    return (
      <StatementSectionPicker
        choices={query.data.statement_choices}
        scope={choiceKey}
        onChoose={setStatementId}
      />
    )
  if (!query.data.currency)
    return (
      <div>
        {!batchReview && query.data.statement_choices.length > 1 && (
          <Button variant="outline" onClick={() => setStatementId("")}>
            {hasReceipts
              ? "Choose another statement or receipt"
              : "Choose another statement period"}
          </Button>
        )}
        <label className="block my-4">
          Statement currency
          <select
            aria-label="Statement currency"
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
            className="border p-2 bg-background"
          >
            <option value="">Choose currency</option>
            {Array.from(
              new Set([
                "EUR",
                "GBP",
                "USD",
                "CAD",
                "AUD",
                "JPY",
                "KWD",
                ...(typeof Intl.supportedValuesOf === "function"
                  ? Intl.supportedValuesOf("currency")
                  : []),
              ])
            ).map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </label>
      </div>
    )
  return (
    <div className="space-y-3">
      {!batchReview && query.data.statement_choices.length > 1 && (
        <StatementPeriodSelect
          choices={query.data.statement_choices}
          value={statementId}
          onChoose={setStatementId}
        />
      )}
      {!batchReview && query.data.statement_choices.length > 1 && (
        <Button variant="outline" onClick={() => setStatementId("")}>
          {hasReceipts
            ? "Choose another statement or receipt"
            : "Choose another statement period"}
        </Button>
      )}
      {query.data.current_import?.excluded_as_duplicate ? (
        <section
          className="rounded border p-4 space-y-3"
          aria-label="Excluded statement copy"
        >
          <h3 className="font-semibold">
            This copy was excluded as a duplicate
          </h3>
          <p>
            Its original statement is kept for reference. Its payments do not
            count in Transactions.
          </p>
          {query.data.current_import.retained_filename && (
            <p>Retained file: {query.data.current_import.retained_filename}</p>
          )}
          <p>
            Open the recorded decision to check why this copy was excluded or to
            restore it. Reopening this PDF does not import its payments again.
          </p>
          <Button asChild variant="outline">
            <a
              href={`/cases/${encodeURIComponent(caseId)}/financial?view=ledger`}
            >
              Review duplicate decision
            </a>
          </Button>
        </section>
      ) : (
        !batchReview && (
          <ReprocessStatement
            key={fileId}
            caseId={caseId}
            fileId={fileId}
            onReady={onReprocessed}
          />
        )
      )}
      {query.data.current_import &&
        !query.data.current_import.excluded_as_duplicate && (
          <Button
            variant="outline"
            onClick={() =>
              onImported({
                ...query.data.current_import!,
                case_id: caseId,
                account_id: query.data.current_import!.account_id || undefined,
                filename:
                  query.data.current_import!.filename || query.data.filename,
              })
            }
          >
            Open imported transactions
          </Button>
        )}
      {query.data.current_import?.evidence_file_id === fileId &&
        !query.data.current_import.excluded_as_duplicate && (
          <section
            className="rounded border p-4 space-y-3"
            aria-label="Recorded statement import"
          >
            <h3 className="font-semibold">
              This statement has already been imported
            </h3>
            <p>
              {query.data.current_import.transaction_count} current transactions
              remain in use. Select <strong>Open imported transactions</strong>{" "}
              to
              {canEdit
                ? "investigate them or correct a value against its source."
                : "inspect them against their sources."}
            </p>
            {query.data.current_import.details_reason && (
              <p>
                Account or statement detail decision:{" "}
                {query.data.current_import.details_reason}
              </p>
            )}
            {query.data.current_import.review_decisions.length > 0 && (
              <details>
                <summary>
                  Recorded import decisions (
                  {query.data.current_import.review_decisions.length})
                </summary>
                <ul className="space-y-3 mt-3">
                  {query.data.current_import.review_decisions.map(
                    (decision, index) => (
                      <li key={index} className="rounded border p-3">
                        <p className="font-medium">
                          {decision.date || "Date not recorded"} ·{" "}
                          {decision.description || "Description not recorded"}
                        </p>
                        <p>
                          {decision.excluded
                            ? "Excluded from this import"
                            : "Included after review"}
                          : {decision.reason}
                        </p>
                      </li>
                    )
                  )}
                </ul>
              </details>
            )}
          </section>
        )}
      <div>
        {query.data.current_import?.evidence_file_id === fileId && (
          <h3 className="font-semibold">Original extraction</h3>
        )}
        <EditableStatement
          key={`${query.data.revision}:${batchReview?.draftRevision ?? "individual"}`}
          data={query.data}
          caseId={caseId}
          fileId={fileId}
          onImported={onImported}
        />
      </div>
    </div>
  )
}

function FailedStatementReading({
  caseId,
  fileId,
  data,
  onReady,
}: {
  caseId: string
  fileId: string
  data: Proposal
  onReady: (id: string) => void
}) {
  const [page, setPage] = useState(data.page_numbers[0] ?? 1)
  return (
    <div className="space-y-4 py-4">
      <div
        className="rounded border border-amber-500/50 bg-amber-50/60 dark:bg-amber-950/20 p-4 space-y-2"
        role="alert"
      >
        <h3 className="font-semibold">
          The statements need to be separated before import
        </h3>
        <p>{data.reading_failure}</p>
        <p>You do not need to correct the summary or terms line by line.</p>
      </div>
      <ReprocessStatement
        caseId={caseId}
        fileId={fileId}
        onReady={onReady}
        initiallyOpen
      />
      <label className="block text-sm">
        Original PDF page{" "}
        <select
          aria-label="Original PDF page"
          value={page}
          onChange={(event) => setPage(Number(event.target.value))}
          className="rounded border bg-background p-2"
        >
          {data.page_numbers.map((number) => (
            <option key={number} value={number}>
              {number}
            </option>
          ))}
        </select>
      </label>
      <div className="max-w-3xl">
        <TransactionSourceHighlight
          sourceDocumentId={fileId}
          locatorPayload={{ kind: "page_only", page }}
          wholePage
        />
      </div>
    </div>
  )
}

function EditableStatement({
  data,
  caseId,
  fileId,
  onImported,
}: {
  data: Proposal
  caseId: string
  fileId: string
  onImported: (result?: StatementImportReceipt) => void
}) {
  const batchReview = useBatchReview()
  const currentRequestSnapshot = useRef("")
  const pendingSaveSnapshot = useRef("")
  const [savedServerSnapshot, setSavedServerSnapshot] = useState("")
  const [progressRevision, setProgressRevision] = useState(
    data.saved_review?.review_revision ?? "initial"
  )
  const [comparedRevision, setComparedRevision] = useState("")
  const [assignmentSaving, setAssignmentSaving] = useState(false)
  const recoveryCompared =
    !!data.review_recovery?.acknowledged ||
    comparedRevision === data.review_recovery?.revision
  const saveBatchReview = useMutation({
    retry: false,
    mutationFn: async (_mode: "progress" | "done" | "next" | "previous") => {
      void _mode
      const request = importRequest()
      pendingSaveSnapshot.current = JSON.stringify(request)
      if (batchReview) return batchReview.save(request)
      const result = z
        .object({
          case_id: z.string(),
          evidence_file_id: z.string(),
          review_revision: z.string(),
          saved_at: z.string(),
          saved_by: z.object({ name: z.string() }),
          request: z.record(z.string(), z.unknown()),
        })
        .parse(
          await fetchAPI(
            `/api/financial/statement-import/${fileId}/progress?case_id=${caseId}`,
            {
              method: "PUT",
              body: { request, expected_review_revision: progressRevision },
            }
          )
        )
      if (result.case_id !== caseId || result.evidence_file_id !== fileId)
        throw Error("The saved review does not belong to this statement.")
      setProgressRevision(result.review_revision)
      client.setQueriesData<Proposal>(
        { queryKey: ["statement-import", caseId, fileId] },
        (cached) =>
          cached?.revision === data.revision
            ? { ...cached, saved_review: result }
            : cached
      )
      return result
    },
    onSuccess: async (_result, mode) => {
      setSavedServerSnapshot(pendingSaveSnapshot.current)
      if (pendingSaveSnapshot.current !== currentRequestSnapshot.current) return
      if (mode === "previous") await batchReview!.previousProblem?.()
      else if (mode === "next") await batchReview!.nextProblem?.()
      else if (mode === "done") batchReview!.saved()
    },
  })
  const { canEdit: caseCanEdit } = useFinancialAccess()
  const excludedCopy = !!data.current_import?.excluded_as_duplicate
  const canEdit =
    caseCanEdit &&
    !excludedCopy &&
    !batchReview?.readOnly &&
    !(batchReview && data.current_import)
  const owner = useAuthStore((state) => state.user?.id || state.user?.username)
  const draftKey = owner
    ? `loupe-statement-review:${owner}:${caseId}:${fileId}:${data.revision}${batchReview ? `:batch:${batchReview.draftRevision || "initial"}` : progressRevision !== "initial" ? `:saved:${progressRevision}` : ""}`
    : null
  const recovered = useMemo(
    () =>
      serverStatementDraft(
        data.saved_review?.request ?? data.previous_saved_review?.request
      ),
    [data.saved_review?.request, data.previous_saved_review?.request]
  )
  const [saved] = useState(
    () =>
      readStatementDraft(draftKey, data.revision) ??
      (batchReview?.draft?.revision === data.revision
        ? batchReview.draft
        : !batchReview && recovered?.revision === data.revision
          ? recovered
          : null)
  )
  const savedReadingChanged =
    !batchReview &&
    !!recovered &&
    recovered.revision !== data.revision &&
    (!data.review_recovery || !!data.saved_review)
  const [previousReviewChecked, setPreviousReviewChecked] = useState(false)
  const [draftSaved, setDraftSaved] = useState(!!saved)
  const [correctionsOpen, setCorrectionsOpen] = useState(false)
  const [correctionPage, setCorrectionPage] = useState(0)
  const correctionControls = useRef<HTMLDivElement>(null)
  const statementControls = useRef<HTMLDivElement>(null)
  const printedControls = useRef<HTMLDivElement>(null)
  const confirmationControls = useRef<HTMLDivElement>(null)
  const pageKey = `${owner}:${caseId}:${fileId}:${data.revision}`
  const rememberedPage = useStatementWorkspace.getState().pages[pageKey]
  const initialPage = data.page_numbers.includes(rememberedPage)
    ? rememberedPage
    : data.rows.find((row) => !row.excluded)?.page_number ||
      data.rows[0]?.page_number ||
      data.page_numbers[0] ||
      1
  const [sourcePage, setSourcePage] = useState(initialPage)
  const client = useQueryClient()
  const baseline = useMemo(() => initialRows(data), [data])
  const hasUnassignedPayments =
    data.assignment_only &&
    data.rows.some((row) => ["transaction", "unresolved"].includes(row.kind))
  const printedDates = useMemo(() => {
    if (
      data.statement_choices.find((choice) => choice.id === data.statement_id)
        ?.layout_id !== "merrick-card"
    )
      return undefined
    return new Map(
      data.rows.flatMap((row) => {
        const printed = row.source_cells[0]?.expected_text.trim() || ""
        return ["transaction", "unresolved"].includes(row.kind) &&
          /^\d{1,2}\/\d{1,2}$/.test(printed)
          ? [[row.id, printed] as const]
          : []
      })
    )
  }, [data])
  const [rows, setRows] = useState(() => {
      if (!saved) return baseline
      if (saved.row_mode !== "changes") return saved.rows
      const edits = new Map(saved.rows.map((row) => [row.id, row]))
      return [
        ...baseline.map((row) => edits.get(row.id) ?? row),
        ...saved.rows.filter((row) => row.manual_page),
      ]
    }),
    [holder, setHolder] = useState(saved?.holder ?? data.metadata.holder),
    [account, setAccount] = useState(
      saved?.account ?? data.metadata.account_number
    )
  const [focus, setFocus] = useState<{
      rowId: string
      locator: unknown
    } | null>({
      rowId:
        data.rows.find(
          (row) => !row.excluded && row.page_number === initialPage
        )?.id ?? "",
      locator: statementRowLocator(
        data.rows.find(
          (row) => !row.excluded && row.page_number === initialPage
        ),
        initialPage
      ),
    }),
    [showExcluded, setShowExcluded] = useState(false),
    [onlyIssues, setOnlyIssues] = useState(false)
  const [amountText, setAmountText] = useState<Record<string, string>>(
    saved?.amountText ?? {}
  )
  const [institution, setInstitution] = useState(
    saved?.institution ?? data.metadata.institution
  )
  const [periodStart, setPeriodStart] = useState(
      saved?.periodStart ?? data.metadata.period_start
    ),
    [periodEnd, setPeriodEnd] = useState(
      saved?.periodEnd ?? data.metadata.period_end
    ),
    [detailsReason, setDetailsReason] = useState(saved?.detailsReason ?? "")
  const [balanceException, setBalanceException] = useState(
    saved?.balanceException ?? { revision: "", reason: "" }
  )
  const [coverageDecision, setCoverageDecision] = useState(
    saved?.coverageDecision ?? { revision: "", reason: "" }
  )
  const [replacePrevious, setReplacePrevious] = useState(false)
  const coverage = useStatementCoverageReview(
    caseId,
    fileId,
    {
      expected_revision: data.revision,
      statement_id: data.statement_id ?? null,
      currency: data.currency,
      institution,
      account_number: account,
      period_start: periodStart,
      period_end: periodEnd,
      ...(replacePrevious && data.current_import
        ? {
            replaces_source_document_id: data.current_import.source_document_id,
          }
        : {}),
    },
    !data.current_import || replacePrevious
  )
  const coverageBlocked =
    !!coverage.data?.candidates.length &&
    (coverageDecision.revision !== coverage.data.revision ||
      !coverageDecision.reason.trim())
  const detailsChanged =
    institution !== data.metadata.institution ||
    holder !== data.metadata.holder ||
    account !== data.metadata.account_number ||
    periodStart !== data.metadata.period_start ||
    periodEnd !== data.metadata.period_end
  const digits = exponent(data.currency),
    originals = new Map(data.rows.map((r) => [r.id, r]))
  const editsById = useMemo(
    () => new Map(rows.map((row) => [row.id, row])),
    [rows]
  )
  for (const added of rows.filter((r) => r.manual_page))
    originals.set(added.id, {
      id: added.id,
      page_number: added.manual_page!,
      table_index: 0,
      row_index: 0,
      source_cells: [],
      fields: {},
      issues: [
        "Manually added transaction. Record the source page and reason.",
      ],
      excluded: false,
      kind: "manual_entry",
    })
  const update = (id: string, patch: Partial<Edit>) =>
    setRows((current) =>
      current.map((r) =>
        r.id === id
          ? {
              ...r,
              ...patch,
              ...(patch.date !== undefined
                ? {
                    date_unprinted:
                      !patch.date &&
                      originals.get(id)?.fields.date_basis ===
                        "statement_end_ordering_only",
                  }
                : {}),
            }
          : r
      )
    )
  const initialById = useMemo(
    () => new Map(baseline.map((r) => [r.id, r])),
    [baseline]
  )
  const changed = useCallback(
    (r: Edit) => {
      if (r.manual_page) return true
      const initial = initialById.get(r.id)!
      return (
        Boolean(r.date_unprinted) !== Boolean(initial.date_unprinted) ||
        JSON.stringify(r.date_values ?? {}) !==
          JSON.stringify(initial.date_values ?? {}) ||
        [
          "excluded",
          "date",
          "description",
          "counterparty",
          "amount_minor",
          "direction",
          "balance_minor",
        ].some((k) => r[k as keyof Edit] !== initial[k as keyof Edit])
      )
    },
    [initialById]
  )
  const requiresReason = (r: Edit) =>
    changed(r) || !!originals.get(r.id)?.issues.length
  const validDate = (value: string) =>
    /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    Number(value.slice(0, 4)) > 0 &&
    !Number.isNaN(Date.parse(value)) &&
    new Date(value).toISOString().slice(0, 10) === value
  const rowProblems = (r: Edit) => {
    const problems: string[] = []
    if (
      r.balance_minor !== null &&
      (!/^-?\d+$/.test(r.balance_minor) ||
        BigInt(r.balance_minor) < -9223372036854775808n ||
        BigInt(r.balance_minor) > 9223372036854775807n)
    )
      problems.push(
        "Enter a valid printed balance, or clear it if none is printed."
      )
    if (!r.excluded) {
      if (r.date_unprinted) {
        if (
          r.date ||
          Object.values(r.date_values ?? {}).some(Boolean) ||
          originals.get(r.id)?.fields.date_basis !==
            "statement_end_ordering_only"
        )
          problems.push("Check this transaction's date against the PDF.")
        if (!validDate(periodEnd))
          problems.push(
            "Enter the statement end date for this undated interest charge."
          )
      } else if (!validDate(r.date))
        problems.push("Enter the transaction date.")
      if (
        Object.values(r.date_values ?? {}).some(
          (value) => value && !validDate(value)
        )
      )
        problems.push("Complete the other printed dates.")
      if (!r.description.trim()) problems.push("Enter the description.")
      if (!r.direction) problems.push("Choose Credit or Debit for the amount.")
      if (
        !/^\d+$/.test(r.amount_minor) ||
        BigInt(r.amount_minor || "0") <= 0n ||
        BigInt(r.amount_minor) > 9223372036854775807n
      )
        problems.push(
          "Enter an amount greater than zero and within the supported range."
        )
    }
    if (requiresReason(r) && !r.reason.trim())
      problems.push(
        changed(r)
          ? "Explain your correction or decision in the reason field."
          : r.excluded
            ? "Check why this row was left out, then record your decision."
            : "Check the flagged reading against the PDF and record your decision."
      )
    return problems
  }
  const blockedRows = rows
    .map((r) => ({ row: r, problems: rowProblems(r) }))
    .filter((item) => item.problems.length > 0)
  const included = rows.filter((r) => !r.excluded)
  const emptyStatementBalances = rows.filter((r) => {
    const original = originals.get(r.id)
    return (
      original?.kind === "balance" &&
      ["opening balance", "closing balance"].includes(
        original.fields.description?.toLowerCase()
      )
    )
  })
  const matchingEmptyBalances =
    emptyStatementBalances.length === 2 &&
    emptyStatementBalances[0].balance_minor !== null &&
    emptyStatementBalances[0].balance_minor ===
      emptyStatementBalances[1].balance_minor
  const detailProblems: { message: string; field?: string }[] = []
  if (coverageBlocked)
    detailProblems.push({
      message:
        "Open Compare overlapping statements. Record why both are needed, or leave this statement unimported.",
      field:
        coverageDecision.revision === coverage.data?.revision
          ? "Reason for importing overlapping statements"
          : "I have compared these files and need to import this statement too",
    })
  if (data.review_recovery?.required && !recoveryCompared)
    detailProblems.push({
      message:
        "Compare the earlier saved reviews for this file before importing. Open Earlier saved reviews above.",
    })
  if (savedReadingChanged && !previousReviewChecked)
    detailProblems.push({
      message:
        "The reading changed after your saved corrections. Compare your previous saved values before confirming.",
      field: "I have compared the previous saved review",
    })
  if (savedReadingChanged && previousReviewChecked && data.saved_review)
    detailProblems.push({
      message:
        "Use Save progress to keep your compared values before importing this new reading.",
    })
  if (!caseCanEdit)
    detailProblems.push({
      message: "You need editing access to this case to confirm an import.",
    })
  if (!holder.trim())
    detailProblems.push({
      message: "Enter the account holder.",
      field: "Account holder",
    })
  if (!account.trim())
    detailProblems.push({
      message: "Enter the account number.",
      field: "Account number",
    })
  if (Boolean(periodStart) !== Boolean(periodEnd))
    detailProblems.push({
      message: "Enter both the start and end of the statement period.",
      field: periodStart ? "Period end" : "Period start",
    })
  else if (periodStart > periodEnd)
    detailProblems.push({
      message: "The period end must be on or after the start.",
      field: "Period end",
    })
  if (detailsChanged && !detailsReason.trim())
    detailProblems.push({
      message: "Explain the account or statement details you changed.",
      field: "Reason for detail corrections",
    })
  if (data.current_import) {
    if (data.current_import.evidence_file_id === fileId)
      detailProblems.push({
        message:
          "This reading is already imported. Use Open imported transactions above to work with it.",
      })
    else {
      if (!replacePrevious)
        detailProblems.push({
          message:
            "Choose whether this reading should replace the previous import.",
          field: "Replace the previous import",
        })
      if (!detailsReason.trim() && !detailsChanged)
        detailProblems.push({
          message:
            "Explain why this reading should replace the previous import.",
          field: "Reason for detail corrections",
        })
    }
  }
  if (included.length === 0 && !data.can_record_account_closure) {
    if (!data.can_import_balances)
      detailProblems.push({
        message: "Select at least one transaction to import.",
      })
    else if (!matchingEmptyBalances)
      detailProblems.push({
        message:
          "Check the opening and closing balances. They must match when there are no transactions.",
      })
  }
  const focusDetail = (field: string) => {
    const input = Array.from(
      statementControls.current?.querySelectorAll<
        HTMLInputElement | HTMLTextAreaElement
      >("input,textarea") ?? []
    ).find((element) => element.getAttribute("aria-label") === field)
    input?.focus({ preventScroll: true })
    input?.scrollIntoView({ block: "center", behavior: "smooth" })
  }
  const total = (direction: Edit["direction"]) =>
    included
      .filter((r) => r.direction === direction && /^\d+$/.test(r.amount_minor))
      .reduce((n, r) => n + BigInt(r.amount_minor), 0n)
      .toString()
  const importRequest = () => ({
    expected_revision: data.revision,
    statement_id: data.statement_id ?? null,
    ...(replacePrevious && data.current_import
      ? {
          replaces_source_document_id: data.current_import.source_document_id,
          replacement_revision: data.current_import.revision,
        }
      : {}),
    currency: data.currency,
    holder,
    institution,
    account_number: account,
    period_start: periodStart,
    period_end: periodEnd,
    details_reason: detailsReason,
    coverage_review_reason: coverageDecision.reason,
    coverage_review_revision: coverageDecision.revision || null,
    balance_exception_reason: balanceException.reason,
    balance_exception_revision: balanceException.revision || null,
    rows: rows.map((r) => ({
      ...r,
      direction: r.direction || null,
      amount_minor: r.excluded && !r.amount_minor ? "0" : r.amount_minor,
    })),
  })
  currentRequestSnapshot.current = JSON.stringify(importRequest())
  const confirm = useMutation({
    retry: false,
    mutationFn: async () => {
      const result = receipt.parse(
        await fetchAPI(
          `/api/financial/statement-import/${fileId}/confirm?${new URLSearchParams({ case_id: caseId })}`,
          {
            method: "POST",
            body: importRequest(),
            timeout: 120000,
          }
        )
      )
      if (
        result.case_id !== caseId ||
        result.evidence_file_id !== fileId ||
        result.transaction_count !== included.length
      )
        throw Error("The import result does not match the reviewed statement.")
      return result
    },
    onSuccess: (result) => {
      void client.invalidateQueries()
      onImported({ ...result, filename: data.filename })
    },
  })
  useEffect(() => {
    if (confirm.isSuccess) {
      if (draftKey)
        try {
          sessionStorage.removeItem(draftKey)
        } catch {
          /* Storage may be disabled. */
        }
      return
    }
    const draft = {
      revision: data.revision,
      row_mode: "changes" as const,
      rows: rows.filter((row) => changed(row) || row.reason),
      holder,
      account,
      institution,
      periodStart,
      periodEnd,
      detailsReason,
      balanceException,
      coverageDecision,
      amountText,
    }
    const timer = window.setTimeout(
      () => setDraftSaved(saveStatementDraft(draftKey, draft)),
      300
    )
    // React cleanup does not run when the browser unloads the page. Flush the
    // latest committed edit before a refresh can discard the pending timer.
    const flush = () => saveStatementDraft(draftKey, draft)
    const onVisibilityChange = () => {
      if (document.visibilityState === "hidden") flush()
    }
    window.addEventListener("pagehide", flush)
    document.addEventListener("visibilitychange", onVisibilityChange)
    return () => {
      window.clearTimeout(timer)
      window.removeEventListener("pagehide", flush)
      document.removeEventListener("visibilitychange", onVisibilityChange)
      saveStatementDraft(draftKey, draft)
    }
  }, [
    draftKey,
    data.revision,
    changed,
    rows,
    holder,
    account,
    institution,
    periodStart,
    periodEnd,
    detailsReason,
    balanceException,
    coverageDecision,
    amountText,
    confirm.isSuccess,
  ])
  const serverChecks = useStatementChecks(caseId, fileId, {
    expected_revision: data.revision,
    statement_id: data.statement_id ?? null,
    currency: data.currency,
    rows: rows.map((r) => ({
      id: r.id,
      excluded: r.excluded,
      manual_page: r.manual_page ?? null,
      date: r.date,
      date_unprinted: Boolean(r.date_unprinted),
      description: r.description,
      amount_minor: r.amount_minor,
      direction: r.direction || null,
      balance_minor: r.balance_minor,
      reason: r.reason,
    })),
  })
  const statementWarnings = data.issues.filter(
    (message) =>
      !(message.startsWith("Check the account holder.") && holder.trim()) &&
      !(message.startsWith("Check the account number.") && account.trim())
  )
  const isStatementNote = (message: string) =>
    [
      "This is a credit-card statement.",
      "Reviewing ",
      "Some pages could not be assigned",
      "These statement pages are out of order",
      "The printed account label is VISA PAYMENT.",
    ].some((prefix) => message.startsWith(prefix))
  const statementNotes = statementWarnings.filter(isStatementNote)
  const warnings = statementWarnings.filter(
    (message) => !isStatementNote(message)
  )
  const attentionCount =
    blockedRows.length + detailProblems.length + warnings.length
  const balanceMismatch = serverChecks.checks.some(
    (check) => check.status === "difference"
  )
  const differenceAccepted =
    !!serverChecks.revision &&
    balanceException.revision === serverChecks.revision &&
    !!balanceException.reason.trim()
  const unresolvedDifference = balanceMismatch && !differenceAccepted
  const activeTransaction = included.findIndex((row) => row.id === focus?.rowId)
  const showTransaction = (index: number) => {
    const transaction = included[index]
    if (!transaction) return
    const original = originals.get(transaction.id)!
    setSourcePage(original.page_number)
    setFocus({
      rowId: transaction.id,
      locator: statementRowLocator(original, original.page_number),
    })
    requestAnimationFrame(() => {
      const element = Array.from(
        printedControls.current?.querySelectorAll<HTMLElement>(
          "[data-statement-row]"
        ) ?? []
      ).find((element) => element.dataset.statementRow === transaction.id)
      element?.scrollIntoView({ block: "nearest", behavior: "smooth" })
    })
  }
  const visible = rows.filter(
    (r) =>
      (showExcluded ||
        !r.excluded ||
        originals.get(r.id)?.kind === "balance" ||
        requiresReason(r)) &&
      (!onlyIssues || originals.get(r.id)?.issues.length || changed(r))
  )
  const currentCorrectionPage = Math.min(
    correctionPage,
    Math.max(0, Math.ceil(visible.length / 50) - 1)
  )
  const correctionRows = visible.slice(
    currentCorrectionPage * 50,
    (currentCorrectionPage + 1) * 50
  )
  const focusedPage = z.object({ page: z.number() }).safeParse(focus?.locator)
  const currentPage = focusedPage.success ? focusedPage.data.page : sourcePage
  useEffect(() => {
    useStatementWorkspace.getState().setPage(pageKey, currentPage)
  }, [pageKey, currentPage])
  const pageIndex = data.page_numbers.indexOf(currentPage)
  const showPage = (page: number) => {
    setSourcePage(page)
    setFocus({ rowId: "", locator: { kind: "page_only", page } })
  }
  const editValues = () => {
    setCorrectionsOpen(true)
    requestAnimationFrame(() =>
      correctionControls.current?.scrollIntoView({
        block: "start",
        behavior: "smooth",
      })
    )
  }
  const balanceLocator = (original: z.infer<typeof row>) =>
    original.source_cells.find(
      (cell) => String(cell.column_index) === original.fields.balance_column
    )?.locator ?? { kind: "page_only", page: original.page_number }
  const editBalance = (id: string) => {
    const original = originals.get(id)
    if (!original) return
    setOnlyIssues(false)
    const balanceRows = rows.filter(
      (row) =>
        showExcluded ||
        !row.excluded ||
        originals.get(row.id)?.kind === "balance" ||
        requiresReason(row)
    )
    setCorrectionPage(
      Math.floor(balanceRows.findIndex((row) => row.id === id) / 50)
    )
    setFocus({ rowId: id, locator: balanceLocator(original) })
    setCorrectionsOpen(true)
    requestAnimationFrame(() => {
      const input = correctionControls.current?.querySelector<HTMLInputElement>(
        `input[aria-label="Balance ${id}"]`
      )
      input?.focus({ preventScroll: true })
      input?.scrollIntoView({ block: "center", behavior: "smooth" })
    })
  }
  const reviewRow = (id: string) => {
    const original = originals.get(id)
    if (!original) return
    setOnlyIssues(false)
    setShowExcluded(true)
    setCorrectionPage(Math.floor(rows.findIndex((row) => row.id === id) / 50))
    setFocus({
      rowId: id,
      locator: original.source_cells[0]?.locator ?? {
        kind: "page_only",
        page: original.page_number,
      },
    })
    setCorrectionsOpen(true)
    requestAnimationFrame(() => {
      const input = Array.from(
        correctionControls.current?.querySelectorAll<HTMLInputElement>(
          "input"
        ) ?? []
      ).find(
        (element) => element.getAttribute("aria-label") === `Include row ${id}`
      )
      input?.focus({ preventScroll: true })
      input?.scrollIntoView({ block: "center", behavior: "smooth" })
    })
  }
  const [inlineRowId, setInlineRowId] = useState<string | null>(null)
  const openInlineRow = (id: string) => {
    const original = originals.get(id)
    if (!original) return
    if (!original.source_cells.length) {
      reviewRow(id)
      return
    }
    setSourcePage(original.page_number)
    setFocus({
      rowId: id,
      locator: statementRowLocator(original, original.page_number),
    })
    setInlineRowId(id)
    requestAnimationFrame(() => {
      const editor = printedControls.current?.querySelector<HTMLElement>(
        '[aria-label="Edit selected statement row"]'
      )
      editor?.scrollIntoView({ block: "nearest", behavior: "smooth" })
    })
  }
  const problemIds = [
    ...new Set([
      ...blockedRows.map(({ row }) => row.id),
      ...serverChecks.checks
        .filter((check) => check.status === "difference")
        .flatMap((check) =>
          check.kind === "running_balance"
            ? (check.findings ?? [])
                .map((item) => item.row_id)
                .filter((id): id is string => !!id)
            : check.row_id
              ? [check.row_id]
              : []
        ),
    ]),
  ]
  const problemIndex = problemIds.indexOf(focus?.rowId ?? "")
  const rowTools = (id: string) => {
    if (!canEdit || (data.current_import && !replacePrevious)) return null
    const edit = editsById.get(id)
    const original = originals.get(id)
    if (
      !edit ||
      !original ||
      !["transaction", "unresolved", "balance", "statement_total"].includes(
        original.kind
      )
    )
      return null
    if (focus?.rowId !== id)
      return changed(edit) || edit.reason ? (
        <Button
          size="sm"
          variant="ghost"
          className="text-teal-700 dark:text-teal-300"
          onClick={() => openInlineRow(id)}
        >
          {changed(edit) ? "View correction" : "View recorded check"}
        </Button>
      ) : null
    if (inlineRowId !== id)
      return (
        <Button size="sm" variant="outline" onClick={() => openInlineRow(id)}>
          Edit this row
        </Button>
      )
    return (
      <StatementRowEditor
        row={edit}
        statementEnd={periodEnd}
        additionalPrintedDate={original.fields.additional_printed_date}
        kind={original.kind}
        problems={rowProblems(edit)}
        update={(patch) => update(id, patch)}
        close={() => setInlineRowId(null)}
        text={(field) =>
          field === "balance"
            ? (amountText[`balance:${id}`] ??
              (edit.balance_minor === null
                ? ""
                : displayAmount(edit.balance_minor, digits)))
            : edit.direction === field
              ? (amountText[id] ?? displayAmount(edit.amount_minor, digits))
              : ""
        }
        amount={(direction, value) => {
          if (!value && edit.direction !== direction) return
          setAmountText((previous) => ({ ...previous, [id]: value }))
          update(id, { direction, amount_minor: minorAmount(value, digits) })
        }}
        balance={(value) => {
          setAmountText((previous) => ({
            ...previous,
            [`balance:${id}`]: value,
          }))
          const negative = value.startsWith("-")
          const minor = minorAmount(negative ? value.slice(1) : value, digits)
          update(id, {
            balance_minor: value
              ? minor
                ? `${negative ? "-" : ""}${minor}`
                : ""
              : null,
          })
        }}
      />
    )
  }
  const initialBatchRow = useRef(batchReview?.rowId)
  useEffect(() => {
    if (initialBatchRow.current) {
      openInlineRow(initialBatchRow.current)
      initialBatchRow.current = undefined
    }
    // Apply the requested problem once, without reopening it after each edit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return (
    <div ref={statementControls} className="space-y-4 pt-4">
      <header>
        <h3 className="text-lg font-semibold">Review {data.filename}</h3>
        {draftSaved && !excludedCopy && !saveBatchReview.isSuccess && (
          <p className="text-xs text-muted-foreground" role="status">
            Recent edits are saved in this browser tab. Use Save progress to
            keep unfinished work in the case before leaving.
          </p>
        )}
        {savedReadingChanged && (
          <SavedReviewConflict
            draft={recovered!}
            formatAmount={(value) =>
              `${displayAmount(value, digits)} ${data.currency}`
            }
            checked={previousReviewChecked}
            onChecked={setPreviousReviewChecked}
          />
        )}
        {data.review_recovery && (
          <PreviousStatementReviews
            caseId={caseId}
            fileId={fileId}
            canEdit={canEdit}
            recovery={{
              ...data.review_recovery,
              acknowledged: recoveryCompared,
            }}
            onCompared={(revision) => {
              setComparedRevision(revision)
              void client.invalidateQueries({
                queryKey: ["financial-batch", caseId],
              })
              client.setQueriesData<Proposal>(
                { queryKey: ["statement-import", caseId, fileId] },
                (cached) =>
                  cached?.review_recovery?.revision === revision
                    ? {
                        ...cached,
                        review_recovery: {
                          ...cached.review_recovery,
                          acknowledged: true,
                        },
                      }
                    : cached
              )
            }}
          />
        )}
        {!batchReview &&
          !data.saved_review &&
          data.previous_saved_review &&
          !savedReadingChanged && (
            <p className="text-sm">
              Saved corrections from the previous reading have been restored
              because the extracted values and source locations are unchanged.
              Check this review, then save or confirm it.
            </p>
          )}
        {!batchReview &&
          data.saved_review &&
          !savedReadingChanged &&
          !saveBatchReview.isSuccess && (
            <p className="text-sm text-muted-foreground">
              Last saved to the case by {data.saved_review.saved_by.name} on{" "}
              {new Date(data.saved_review.saved_at).toLocaleString()}. Save
              progress again after editing.
            </p>
          )}
        {canEdit && (!data.current_import || replacePrevious) && (
          <div className="flex flex-wrap items-center gap-2 py-2">
            <Button
              variant="outline"
              disabled={
                assignmentSaving ||
                saveBatchReview.isPending ||
                confirm.isPending ||
                (savedReadingChanged && !previousReviewChecked)
              }
              onClick={() => saveBatchReview.mutate("progress")}
            >
              {saveBatchReview.isPending ? "Saving progress…" : "Save progress"}
            </Button>
            {batchReview?.previousProblem && (
              <Button
                variant="outline"
                disabled={
                  assignmentSaving ||
                  saveBatchReview.isPending ||
                  confirm.isPending
                }
                onClick={() => saveBatchReview.mutate("previous")}
              >
                Save and open previous problem
              </Button>
            )}
            {batchReview?.nextProblem && (
              <Button
                variant="outline"
                disabled={
                  assignmentSaving ||
                  saveBatchReview.isPending ||
                  confirm.isPending
                }
                onClick={() => saveBatchReview.mutate("next")}
              >
                Save and open next problem
              </Button>
            )}
            <span className="text-xs text-muted-foreground">
              Saves unfinished corrections to the case. Transactions are
              imported separately.
            </span>
            {saveBatchReview.isSuccess && (
              <p role="status" className="w-full text-sm">
                {savedServerSnapshot === currentRequestSnapshot.current
                  ? "Progress saved to the case. You can reopen this statement on another device."
                  : "There are newer edits in this review. Save progress again before leaving."}
              </p>
            )}
            {saveBatchReview.isError && (
              <p role="alert" className="w-full text-sm">
                {saveBatchReview.error.message} Your edits remain in this
                review.
              </p>
            )}
          </div>
        )}
        <p className="text-sm">
          {data.assignment_only
            ? "Check which account owns these payments, then assign them to its statement. Select any value to compare it with the PDF."
            : "The system checks the extracted transactions and compares the balances where available. Review flagged items, then confirm the import. You can also select any value to check its source."}
        </p>
      </header>
      {data.assignment_only && (
        <section
          aria-label="Unassigned payments"
          className={`rounded border p-3 space-y-2 ${hasUnassignedPayments ? "border-amber-500/50 bg-amber-50/60 dark:bg-amber-950/20" : "border-teal-500/40 bg-teal-50/60 dark:bg-teal-950/20"}`}
        >
          <h4 className="font-semibold">
            {hasUnassignedPayments
              ? "Choose the account for these payments"
              : "All payments have been assigned"}
          </h4>
          <p className="text-sm">
            Printed main account: {data.printed_main_account}. Period:{" "}
            {data.metadata.period}.
          </p>
          <p className="text-sm">
            {hasUnassignedPayments
              ? "The savings or checking share could not be established. A preceding page may be missing. Compare the PDF, select the payments below and use Move to another account or period to choose their destination. This page cannot be imported on its own."
              : "Open the destination statement to finish checking and import these payments. Their original page locations and your assignment reason have been kept."}
          </p>
          {!data.statement_choices.some(
            (choice) => !choice.assignment_only && !choice.document_kind
          ) && (
            <p className="text-sm">
              No destination account was recognised in this PDF. Obtain the
              missing account page and process the complete file before
              assigning these payments.
            </p>
          )}
        </section>
      )}
      {!data.assignment_only && (!data.current_import || replacePrevious) && (
        <section
          aria-label="Statement checks"
          className={`rounded border p-3 text-sm ${attentionCount || unresolvedDifference ? "border-amber-500/50 bg-amber-50/60 dark:bg-amber-950/20" : "border-teal-500/40 bg-teal-50/60 dark:bg-teal-950/20"}`}
        >
          <div className="flex flex-wrap justify-between items-center gap-3">
            <div>
              <h4 className="font-semibold">
                {serverChecks.pending
                  ? "Checking current values…"
                  : serverChecks.error
                    ? "Statement checks could not finish"
                    : attentionCount
                      ? `${attentionCount} items need attention`
                      : unresolvedDifference
                        ? "Check the differences below"
                        : "Ready to confirm"}
              </h4>
              <p>{included.length} transactions selected.</p>
              <p>
                {serverChecks.pending
                  ? "Checking these values. You can keep reviewing the PDF while this runs."
                  : attentionCount || unresolvedDifference
                    ? "Open the flagged items to check them against the PDF."
                    : "Confirm once to import this statement. You do not need to accept each line separately."}
              </p>
            </div>
            {serverChecks.error && (
              <div role="alert" className="w-full">
                <p>{serverChecks.error}</p>
                <Button variant="outline" onClick={serverChecks.retry}>
                  Retry statement checks
                </Button>
              </div>
            )}
            <div className="w-full">
              <StatementArithmeticChecks
                checks={serverChecks.checks}
                format={(value) =>
                  `${displayAmount(value, digits)} ${data.currency}`
                }
                onInspect={openInlineRow}
              />
              {balanceMismatch && (
                <div className="mt-3 space-y-2 rounded border p-3">
                  <p>
                    If the numbers match the PDF but the statement itself does
                    not add up, keep the printed values and record the
                    difference.
                  </p>
                  <label className="block">
                    <input
                      type="checkbox"
                      checked={
                        balanceException.revision === serverChecks.revision
                      }
                      disabled={!canEdit || serverChecks.pending}
                      onChange={(event) =>
                        setBalanceException((previous) => ({
                          ...previous,
                          revision: event.target.checked
                            ? serverChecks.revision!
                            : "",
                        }))
                      }
                    />{" "}
                    I checked these differences against the PDF
                  </label>
                  {balanceException.revision === serverChecks.revision && (
                    <label className="block">
                      Why the difference remains
                      <textarea
                        aria-label="Why the difference remains"
                        className="block w-full rounded border bg-background p-2"
                        value={balanceException.reason}
                        disabled={!canEdit}
                        onChange={(event) =>
                          setBalanceException((previous) => ({
                            ...previous,
                            reason: event.target.value,
                          }))
                        }
                      />
                    </label>
                  )}
                  {differenceAccepted && (
                    <p>
                      Your explanation will be saved with the import. The
                      difference remains recorded.
                    </p>
                  )}
                </div>
              )}
            </div>
            {warnings.length > 0 && (
              <ul className="w-full list-disc pl-5">
                {warnings.map((message) => (
                  <li key={message}>{message}</li>
                ))}
              </ul>
            )}
            <Button
              variant="outline"
              onClick={() =>
                confirmationControls.current?.scrollIntoView({
                  block: "start",
                  behavior: "smooth",
                })
              }
            >
              {attentionCount ? "Show items to check" : "Go to confirmation"}
            </Button>
          </div>
        </section>
      )}
      {problemIds.length > 0 && (
        <div
          role="group"
          aria-label="Problem navigation"
          className="flex flex-wrap items-center gap-2 rounded border border-amber-500/30 bg-amber-50/40 dark:bg-amber-950/10 p-2"
        >
          <Button
            size="sm"
            variant="outline"
            disabled={problemIndex <= 0}
            onClick={() => openInlineRow(problemIds[problemIndex - 1])}
          >
            Previous problem
          </Button>
          <span className="text-sm">
            {problemIndex < 0
              ? `${problemIds.length} rows need attention`
              : `Problem ${problemIndex + 1} of ${problemIds.length}`}
          </span>
          <Button
            size="sm"
            variant="outline"
            disabled={problemIndex >= problemIds.length - 1}
            onClick={() => openInlineRow(problemIds[problemIndex + 1])}
          >
            {problemIndex < 0 ? "First problem" : "Next problem"}
          </Button>
        </div>
      )}
      {included.length > 0 && (
        <div
          role="group"
          aria-label="Transaction navigation"
          className="flex flex-wrap items-center gap-2 rounded border bg-muted/20 p-2"
          onKeyDown={(event) => {
            if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
              event.preventDefault()
              showTransaction(
                activeTransaction + (event.key === "ArrowLeft" ? -1 : 1)
              )
            }
          }}
        >
          <Button
            variant="outline"
            size="sm"
            disabled={activeTransaction <= 0}
            onClick={() => showTransaction(activeTransaction - 1)}
          >
            Previous transaction
          </Button>
          <span className="text-sm" aria-live="polite">
            {activeTransaction >= 0
              ? `Transaction ${activeTransaction + 1} of ${included.length}`
              : `${included.length} transactions`}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={activeTransaction >= included.length - 1}
            onClick={() => showTransaction(activeTransaction + 1)}
          >
            {activeTransaction < 0 ? "First transaction" : "Next transaction"}
          </Button>
          {activeTransaction >= 0 && (
            <span className="text-sm text-muted-foreground truncate max-w-md">
              {included[activeTransaction].description}
            </span>
          )}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          disabled={pageIndex <= 0}
          onClick={() => showPage(data.page_numbers[pageIndex - 1])}
        >
          Previous page
        </Button>
        <label className="text-sm">
          Page{" "}
          <select
            aria-label="Statement viewer page"
            value={currentPage}
            onChange={(event) => showPage(Number(event.target.value))}
            className="rounded border bg-background p-2"
          >
            {data.page_numbers.map((page) => (
              <option key={page} value={page}>
                {page}
              </option>
            ))}
          </select>{" "}
          of {data.page_numbers.length}
        </label>
        <Button
          variant="outline"
          disabled={pageIndex < 0 || pageIndex >= data.page_numbers.length - 1}
          onClick={() => showPage(data.page_numbers[pageIndex + 1])}
        >
          Next page
        </Button>
        {!excludedCopy &&
          (canEdit || data.current_import?.evidence_file_id === fileId) && (
            <Button
              className="ml-auto"
              onClick={
                data.current_import?.evidence_file_id === fileId
                  ? () =>
                      onImported({
                        ...data.current_import!,
                        case_id: caseId,
                        account_id:
                          data.current_import!.account_id || undefined,
                        filename:
                          data.current_import!.filename || data.filename,
                      })
                  : editValues
              }
            >
              {data.current_import?.evidence_file_id === fileId
                ? canEdit
                  ? "Edit imported transactions"
                  : "Open imported transactions"
                : "Edit import values"}
            </Button>
          )}
      </div>
      <fieldset
        disabled={
          assignmentSaving ||
          confirm.isPending ||
          confirm.isSuccess ||
          saveBatchReview.isPending
        }
        className="space-y-4"
      >
        <div
          className={`grid gap-4 ${focus ? "xl:grid-cols-[minmax(300px,0.8fr)_minmax(0,1.2fr)]" : ""}`}
        >
          {focus && (
            <aside className="min-w-0 xl:sticky xl:top-0 self-start rounded border p-3">
              <div className="flex justify-between items-center mb-2">
                <h4 className="font-semibold">Original statement</h4>
                <Button variant="ghost" onClick={() => setFocus(null)}>
                  Close source
                </Button>
              </div>
              <TransactionSourceHighlight
                sourceDocumentId={fileId}
                locatorPayload={focus.locator}
                wholePage={!focus.rowId || focus.rowId.startsWith("page:")}
              />
            </aside>
          )}
          <div
            ref={printedControls}
            className="min-w-0 overflow-y-auto overflow-x-hidden max-h-[65vh]"
          >
            <h4 className="font-semibold">Extracted statement</h4>
            <p className="text-sm text-muted-foreground mb-3">
              Select a printed value to locate it in the PDF, or use Previous
              and Next transaction to move through the payments.
              {canEdit &&
                " Select Edit this row to correct a value beside its original."}
            </p>
            <PrintedStatementTable
              selectedRowId={focus?.rowId}
              rows={data.rows.filter((row) => row.page_number === currentPage)}
              onCell={(rowId, locator) => setFocus({ rowId, locator })}
              onReviewRow={
                canEdit && !data.current_import ? openInlineRow : undefined
              }
              rowTools={rowTools}
            />
            {canEdit &&
              (!data.current_import || replacePrevious) &&
              (!data.assignment_only || hasUnassignedPayments) &&
              (!data.assignment_only ||
                data.statement_choices.some(
                  (choice) => !choice.assignment_only && !choice.document_kind
                )) && (
                <StatementBulkCorrections
                  printedDates={printedDates}
                  assignmentOnly={data.assignment_only}
                  reassign={
                    !data.current_import &&
                    data.statement_choices.some(
                      (choice) =>
                        choice.id !== data.statement_id &&
                        !choice.document_kind &&
                        !choice.assignment_only
                    )
                      ? (rowIds, reason) => (
                          <StatementRowAssignment
                            caseId={caseId}
                            fileId={fileId}
                            choices={data.statement_choices.filter(
                              (choice) =>
                                choice.id !== data.statement_id &&
                                !choice.document_kind &&
                                !choice.assignment_only
                            )}
                            request={importRequest()}
                            rowIds={rowIds}
                            reason={reason}
                            reviewRevision={
                              batchReview?.draftRevision ?? progressRevision
                            }
                            batchId={batchReview?.batchId}
                            onBusy={setAssignmentSaving}
                            onApplied={async () => {
                              try {
                                if (draftKey)
                                  sessionStorage.removeItem(draftKey)
                              } catch {
                                // The server has saved the move even if browser storage is unavailable.
                              }
                              await client.invalidateQueries({
                                queryKey: ["financial-batch-item", caseId],
                              })
                              await client.invalidateQueries({
                                queryKey: ["financial-batch", caseId],
                              })
                              await client.invalidateQueries({
                                queryKey: ["statement-import", caseId, fileId],
                              })
                            }}
                          />
                        )
                      : undefined
                  }
                  rows={rows.filter(
                    (row) =>
                      row.manual_page ||
                      ["transaction", "unresolved"].includes(
                        originals.get(row.id)?.kind ?? ""
                      )
                  )}
                  inspect={openInlineRow}
                  apply={(changes) => {
                    const corrected = new Map(
                      changes.map((change) => [change.before.id, change.after])
                    )
                    setRows((current) =>
                      current.map((row) => corrected.get(row.id) ?? row)
                    )
                  }}
                />
              )}
            {!!data.row_assignments.length && (
              <p className="text-sm my-3">
                Transactions have been reassigned between statements in this
                PDF. Moved transactions keep their original page locations and
                the reason for the move in their corrections.
              </p>
            )}
            {!data.rows.some((row) => row.page_number === currentPage) && (
              <p className="my-3 text-sm">
                No extracted rows for this page in the selected statement. Check
                the original PDF alongside it.
              </p>
            )}
            {canEdit && (
              <Button
                variant="outline"
                className="my-3"
                onClick={() => setCorrectionsOpen((value) => !value)}
              >
                {correctionsOpen
                  ? "Hide corrections and import choices"
                  : "Show corrections and import choices"}
              </Button>
            )}
            <div ref={correctionControls} hidden={!canEdit || !correctionsOpen}>
              <div className="flex flex-wrap gap-4 text-sm">
                <label>
                  <input
                    type="checkbox"
                    checked={onlyIssues}
                    onChange={(e) => {
                      setOnlyIssues(e.target.checked)
                      setCorrectionPage(0)
                    }}
                  />{" "}
                  Show problems and edits only
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={showExcluded}
                    onChange={(e) => {
                      setShowExcluded(e.target.checked)
                      setCorrectionPage(0)
                    }}
                  />{" "}
                  Show excluded rows
                </label>
              </div>

              <h4 className="font-semibold my-2">
                Corrections and import choices
              </h4>
              <p className="text-sm mb-3">
                These fields control the import. They do not replace the printed
                statement above. Paid by / paid to is an investigation field
                suggested from the description.
              </p>
              <div
                className="max-w-full overflow-x-auto"
                role="region"
                aria-label="Statement correction columns"
                tabIndex={0}
              >
                <table className="w-full text-sm border-collapse">
                  <thead className="sticky top-0 bg-card z-10">
                    <tr>
                      {[
                        "Use",
                        "Date",
                        "Description",
                        "Credit",
                        "Debit",
                        "Printed balance",
                        "Actions",
                      ].map((s) => (
                        <th key={s} className="text-left p-2 border-b">
                          {s}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {correctionRows.map((r) => {
                      const original = originals.get(r.id)!
                      return (
                        <tr
                          key={r.id}
                          className={r.excluded ? "opacity-70" : ""}
                        >
                          <td className="p-2 border-b align-top">
                            <input
                              aria-label={`Include row ${r.id}`}
                              type="checkbox"
                              checked={!r.excluded}
                              disabled={
                                original.kind === "balance" ||
                                original.kind === "statement_total"
                              }
                              onChange={(e) =>
                                update(r.id, { excluded: !e.target.checked })
                              }
                            />
                          </td>
                          <td className="p-2 border-b align-top">
                            {(sourceDateRoles(original.fields).length > 1 ||
                              primaryDateRole(original.fields) !== "date") && (
                              <span className="block text-xs mb-1">
                                {dateLabels[primaryDateRole(original.fields)]}
                              </span>
                            )}
                            {r.date_unprinted && (
                              <span className="block text-xs mb-1">
                                Date not printed
                              </span>
                            )}
                            {original.fields.additional_printed_date && (
                              <span className="block text-xs mb-1">
                                Also printed:{" "}
                                {original.fields.additional_printed_date}. The
                                first date on the row is used here.
                              </span>
                            )}
                            <input
                              aria-label={`Date ${r.id}`}
                              type="date"
                              disabled={r.excluded}
                              className="border rounded p-1 bg-background"
                              value={r.date}
                              onChange={(e) =>
                                update(r.id, { date: e.target.value })
                              }
                            />
                            {sourceDateRoles(original.fields)
                              .filter(
                                (role) =>
                                  role !== primaryDateRole(original.fields)
                              )
                              .map((role) => (
                                <label
                                  key={role}
                                  className="block mt-2 text-xs"
                                >
                                  {dateLabels[role]}
                                  <input
                                    aria-label={`${dateLabels[role]} ${r.id}`}
                                    type="date"
                                    disabled={r.excluded}
                                    className="block border rounded p-1 bg-background mt-1"
                                    value={
                                      r.date_values?.[role] ??
                                      original.fields[role] ??
                                      ""
                                    }
                                    onChange={(event) =>
                                      update(r.id, {
                                        date_values: {
                                          ...r.date_values,
                                          [role]: event.target.value,
                                        },
                                      })
                                    }
                                    onFocus={() => {
                                      const source = original.source_cells.find(
                                        (cell) =>
                                          String(cell.column_index) ===
                                          original.fields[role + "_column"]
                                      )
                                      if (source)
                                        setFocus({
                                          rowId: r.id,
                                          locator: source.locator,
                                        })
                                    }}
                                  />
                                </label>
                              ))}
                          </td>
                          <td className="p-2 border-b align-top min-w-56">
                            <input
                              aria-label={`Description ${r.id}`}
                              disabled={r.excluded}
                              className="border rounded p-1 bg-background w-full"
                              value={r.description}
                              onChange={(e) =>
                                update(r.id, { description: e.target.value })
                              }
                            />
                            <label className="block mt-2 text-xs">
                              Paid by / paid to
                              <input
                                aria-label={`Counterparty ${r.id}`}
                                disabled={r.excluded}
                                className="block border rounded p-1 bg-background w-full"
                                value={r.counterparty}
                                onChange={(e) =>
                                  update(r.id, { counterparty: e.target.value })
                                }
                              />
                            </label>
                            {original.issues.map((s, i) => (
                              <p
                                key={i}
                                className="text-amber-700 dark:text-amber-300 mt-1"
                              >
                                {s}
                              </p>
                            ))}
                            {r.manual_page && (
                              <label className="block mt-2">
                                Source page
                                <select
                                  aria-label={`Source page ${r.id}`}
                                  value={r.manual_page}
                                  onChange={(e) => {
                                    update(r.id, {
                                      manual_page: Number(e.target.value),
                                    })
                                    setFocus({
                                      rowId: r.id,
                                      locator: {
                                        kind: "page_only",
                                        page: Number(e.target.value),
                                      },
                                    })
                                  }}
                                  className="border rounded p-1 bg-background"
                                >
                                  {data.page_numbers.map((p) => (
                                    <option key={p} value={p}>
                                      {p}
                                    </option>
                                  ))}
                                </select>
                              </label>
                            )}
                            {(requiresReason(r) || !!r.reason) && (
                              <label className="block mt-2">
                                Reason for correction or decision
                                <input
                                  aria-label={`Reason ${r.id}`}
                                  value={r.reason}
                                  onChange={(e) =>
                                    update(r.id, { reason: e.target.value })
                                  }
                                  className="border rounded p-1 w-full bg-background"
                                />
                                {!changed(r) &&
                                  !r.excluded &&
                                  !r.reason.trim() &&
                                  rowProblems(r).length === 1 && (
                                    <Button
                                      variant="outline"
                                      size="sm"
                                      className="mt-2"
                                      onClick={() =>
                                        update(r.id, {
                                          reason:
                                            "Checked against the original PDF; the extracted values are correct.",
                                        })
                                      }
                                    >
                                      I checked this row against the PDF
                                    </Button>
                                  )}
                              </label>
                            )}
                            {focus?.rowId === r.id && (
                              <div className="flex flex-wrap gap-1 mt-2">
                                {original.source_cells.map((c) => (
                                  <Button
                                    key={c.column_index}
                                    size="sm"
                                    variant="outline"
                                    onClick={() =>
                                      setFocus({
                                        rowId: r.id,
                                        locator: c.locator,
                                      })
                                    }
                                  >
                                    {c.expected_text}
                                  </Button>
                                ))}
                              </div>
                            )}
                          </td>
                          {(["credit", "debit"] as const).map((direction) => (
                            <td
                              key={direction}
                              className="p-2 border-b align-top"
                            >
                              <input
                                aria-label={`${direction === "credit" ? "Credit" : "Debit"} ${r.id}`}
                                disabled={r.excluded}
                                inputMode="decimal"
                                className="border rounded p-1 bg-background w-28"
                                value={
                                  r.direction === direction
                                    ? (amountText[r.id] ??
                                      displayAmount(r.amount_minor, digits))
                                    : ""
                                }
                                onChange={(e) => {
                                  const value = e.target.value
                                  if (!value && r.direction !== direction)
                                    return
                                  setAmountText((previous) => ({
                                    ...previous,
                                    [r.id]: value,
                                  }))
                                  update(r.id, {
                                    direction,
                                    amount_minor: minorAmount(value, digits),
                                  })
                                }}
                              />
                            </td>
                          ))}
                          <td className="p-2 border-b align-top whitespace-nowrap">
                            <input
                              aria-label={`Balance ${r.id}`}
                              className="border rounded p-1 bg-background w-28"
                              inputMode="decimal"
                              value={
                                amountText[`balance:${r.id}`] ??
                                (r.balance_minor !== null
                                  ? displayAmount(r.balance_minor, digits)
                                  : "")
                              }
                              onChange={(e) => {
                                const v = e.target.value
                                setAmountText((x) => ({
                                  ...x,
                                  [`balance:${r.id}`]: v,
                                }))
                                const parsed = minorAmount(
                                  v.replace(/^-/, ""),
                                  digits
                                )
                                update(r.id, {
                                  balance_minor:
                                    v === ""
                                      ? null
                                      : parsed
                                        ? (v.startsWith("-") ? "-" : "") +
                                          parsed
                                        : "invalid",
                                })
                              }}
                            />
                          </td>
                          <td className="p-2 border-b align-top">
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() =>
                                setFocus({
                                  rowId: r.id,
                                  locator:
                                    original.fields.balance_column !== undefined
                                      ? balanceLocator(original)
                                      : (original.source_cells[0]?.locator ?? {
                                          kind: "page_only",
                                          page: original.page_number,
                                        }),
                                })
                              }
                            >
                              View source
                            </Button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              {visible.length > 50 && (
                <div className="flex flex-wrap items-center gap-2 my-3">
                  <Button
                    variant="outline"
                    disabled={!currentCorrectionPage}
                    onClick={() => setCorrectionPage(currentCorrectionPage - 1)}
                  >
                    Previous review rows
                  </Button>
                  <label>
                    Review page{" "}
                    <select
                      aria-label="Review page"
                      className="border rounded bg-background p-2"
                      value={currentCorrectionPage}
                      onChange={(event) =>
                        setCorrectionPage(Number(event.target.value))
                      }
                    >
                      {Array.from(
                        { length: Math.ceil(visible.length / 50) },
                        (_, index) => (
                          <option key={index} value={index}>
                            {index + 1}
                          </option>
                        )
                      )}
                    </select>
                  </label>
                  <span>
                    Rows {currentCorrectionPage * 50 + 1} to{" "}
                    {Math.min((currentCorrectionPage + 1) * 50, visible.length)}{" "}
                    of {visible.length}. Import includes all {included.length}{" "}
                    selected transactions.
                  </span>
                  <Button
                    variant="outline"
                    disabled={
                      (currentCorrectionPage + 1) * 50 >= visible.length
                    }
                    onClick={() => setCorrectionPage(currentCorrectionPage + 1)}
                  >
                    Next review rows
                  </Button>
                </div>
              )}
              {visible.length === 0 && (
                <p className="p-4">No rows match these review filters.</p>
              )}
            </div>
          </div>
        </div>
        {data.current_import && !excludedCopy && (
          <div className="rounded border p-3 space-y-2">
            <p>
              This statement already contributes{" "}
              {data.current_import.transaction_count} transactions to the case.
            </p>
            {data.current_import.evidence_file_id === fileId ? (
              <p>
                Open the transactions to work with this import. Reprocess the
                statement to prepare a replacement reading.
              </p>
            ) : (
              <label className="flex gap-2">
                <input
                  type="checkbox"
                  disabled={!canEdit}
                  aria-label="Replace the previous import"
                  checked={replacePrevious}
                  onChange={(e) => setReplacePrevious(e.target.checked)}
                />
                Replace the previous import when I confirm. Its original records
                and source remain in the history.
              </label>
            )}
          </div>
        )}
        <div
          hidden={data.assignment_only}
          className={
            data.assignment_only ? "hidden" : "grid sm:grid-cols-3 gap-3"
          }
        >
          <label>
            Account holder
            <input
              aria-label="Account holder"
              readOnly={!canEdit}
              className="block border rounded p-2 w-full bg-background"
              value={holder}
              onChange={(e) => setHolder(e.target.value)}
            />
          </label>
          <label>
            Account number
            <input
              aria-label="Account number"
              readOnly={!canEdit}
              className="block border rounded p-2 w-full bg-background"
              value={account}
              onChange={(e) => setAccount(e.target.value)}
            />
          </label>
          <div>
            <p>Statement currency</p>
            <strong>{data.currency}</strong>
            <p className="text-sm">{data.metadata.period}</p>
          </div>
        </div>
        <div
          className={data.assignment_only ? "hidden" : "flex flex-wrap gap-3"}
        >
          <label>
            Bank
            <input
              aria-label="Bank"
              readOnly={!canEdit}
              className="block border rounded p-2 bg-background"
              value={institution}
              onChange={(e) => setInstitution(e.target.value)}
            />
          </label>
          <label>
            Period start
            <input
              type="date"
              aria-label="Period start"
              readOnly={!canEdit}
              className="block border rounded p-2 bg-background"
              value={periodStart}
              onChange={(e) => setPeriodStart(e.target.value)}
            />
          </label>
          <label>
            Period end
            <input
              type="date"
              aria-label="Period end"
              readOnly={!canEdit}
              className="block border rounded p-2 bg-background"
              value={periodEnd}
              onChange={(e) => setPeriodEnd(e.target.value)}
            />
          </label>
          {!excludedCopy && (detailsChanged || data.current_import) && (
            <label>
              Reason for detail corrections
              <input
                aria-label="Reason for detail corrections"
                readOnly={!canEdit}
                className="block border rounded p-2 bg-background"
                value={detailsReason}
                onChange={(e) => setDetailsReason(e.target.value)}
              />
            </label>
          )}
        </div>
        {!data.assignment_only && warnings.length > 0 && (
          <div className="rounded border border-amber-500 p-3">
            <h4 className="font-semibold">Check statement details</h4>
            {warnings.map((message) => (
              <p key={message}>{message}</p>
            ))}
          </div>
        )}
        {statementNotes.length > 0 && (
          <details className="rounded border p-3 text-sm">
            <summary className="cursor-pointer font-medium">
              About this statement
            </summary>
            {statementNotes.map((message) => (
              <p key={message} className="mt-2">
                {message}
              </p>
            ))}
          </details>
        )}
        <div className="flex flex-wrap gap-5 text-sm">
          <span>
            {excludedCopy ? (
              "This copy contributes no transactions to the case totals."
            ) : (
              <>
                <strong>{included.length}</strong>{" "}
                {data.assignment_only
                  ? "transactions to assign"
                  : "transactions to import"}
              </>
            )}
          </span>
          <span>
            {data.metadata.account_type === "credit_card"
              ? "Credits"
              : "Money in"}
            :{" "}
            <strong>
              {displayAmount(total("credit"), digits)} {data.currency}
            </strong>
          </span>
          <span>
            {data.metadata.account_type === "credit_card"
              ? "Debits"
              : "Money out"}
            :{" "}
            <strong>
              {displayAmount(total("debit"), digits)} {data.currency}
            </strong>
          </span>
        </div>
        {included.some((row) => row.date_unprinted) && (
          <p className="text-sm text-muted-foreground">
            {included.filter((row) => row.date_unprinted).length} interest
            charges have no printed transaction date. They will be included with
            this statement and labelled “Date not printed” in Transactions.
          </p>
        )}
        {included.some(
          (r) => !r.direction || !/^\d+$/.test(r.amount_minor)
        ) && (
          <p
            className="text-sm text-amber-700 dark:text-amber-400"
            role="status"
          >
            Totals are incomplete. Check the flagged rows and enter each amount
            under Credit or Debit before importing.
          </p>
        )}
        <div className="flex flex-wrap gap-5 text-sm">
          {(["opening", "closing"] as const).map((role) => {
            const controls = rows.filter(
              (item) =>
                item.excluded &&
                originals.get(item.id)?.kind === "balance" &&
                originals
                  .get(item.id)
                  ?.fields.description?.trim()
                  .toLowerCase() === `${role} balance`
            )
            const label = `${role} ${data.metadata.balance_convention === "liability_owed" ? "amount owed" : "balance"}`
            return (
              <div key={role} className="space-y-1">
                <span className="capitalize">
                  {role}{" "}
                  {data.metadata.balance_convention === "liability_owed"
                    ? "amount owed"
                    : "balance"}
                  :{" "}
                </span>
                {controls.length > 1 && (
                  <p className="text-amber-700 dark:text-amber-400">
                    Found {controls.length} readings. Check each page. Clear any
                    repeated balance in Corrections and explain why.
                  </p>
                )}
                {controls.length ? (
                  controls.map((control) => (
                    <button
                      key={control.id}
                      className={
                        controls.length > 1 ? "block underline" : "underline"
                      }
                      type="button"
                      aria-label={`${canEdit ? "Edit" : "Inspect"} ${label}${controls.length > 1 ? ` on page ${originals.get(control.id)?.page_number}, row ${originals.get(control.id)!.row_index + 1}` : ""}`}
                      onClick={() => {
                        if (canEdit) editBalance(control.id)
                        else {
                          const original = originals.get(control.id)
                          if (original)
                            setFocus({
                              rowId: original.id,
                              locator: balanceLocator(original),
                            })
                        }
                      }}
                    >
                      {controls.length > 1 &&
                        `Page ${originals.get(control.id)?.page_number}: `}
                      {control.balance_minor === null
                        ? "Enter amount"
                        : `${displayAmount(control.balance_minor, digits)} ${data.currency}`}
                    </button>
                  ))
                ) : (
                  <span className="text-muted-foreground">Not identified</span>
                )}
              </div>
            )
          })}
        </div>
        <p className="text-sm text-muted-foreground">
          {canEdit
            ? "Select an opening or closing amount to check its source or correct it."
            : "Select an opening or closing amount to check its source."}
        </p>
        {!excludedCopy && !data.assignment_only && (
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              const page =
                (focus ? originals.get(focus.rowId)?.page_number : undefined) ??
                sourcePage
              if (!page) return
              const id = `manual:${newReviewId()}`
              setCorrectionsOpen(true)
              setOnlyIssues(false)
              setShowExcluded(true)
              setCorrectionPage(Math.floor(rows.length / 50))
              setRows((current) => [
                ...current,
                {
                  id,
                  excluded: false,
                  manual_page: page,
                  date: "",
                  description: "",
                  amount_minor: "0",
                  direction: "",
                  counterparty: "",
                  balance_minor: null,
                  reason: "",
                },
              ])
              setFocus({ rowId: id, locator: { kind: "page_only", page } })
            }}
            disabled={!canEdit || !data.page_numbers.length}
          >
            Add a missed transaction
          </Button>
        )}
        <details className="border rounded p-3 text-sm">
          <summary className="cursor-pointer">
            Inspect another page of the original PDF
            {data.unassigned_page_numbers.length
              ? ` (${data.unassigned_page_numbers.length} pages need a coverage check)`
              : ""}
          </summary>
          {data.unassigned_page_numbers.length > 0 && (
            <p>
              These pages were not assigned to a statement or recognised as
              information pages. Check them for missed transactions before
              relying on complete coverage.
              {!excludedCopy &&
                " Use Add a missed transaction if you find one for this account and period."}
            </p>
          )}
          {data.information_pages.length > 0 && (
            <p className="text-muted-foreground mt-2">
              {data.information_pages.length} information pages contain
              supporting material such as account forms, letters, notices and
              fee or interest summaries. They remain available below and have
              not been added as transactions.
            </p>
          )}
          <label className="block mt-2">
            Original PDF page
            <select
              aria-label="Original PDF page"
              className="ml-2 border rounded p-2 bg-background"
              value={
                (focus ? originals.get(focus.rowId)?.page_number : undefined) ??
                sourcePage
              }
              onChange={(event) => {
                const page = Number(event.target.value)
                setSourcePage(page)
                setFocus({
                  rowId: `page:${page}`,
                  locator: { kind: "page_only", page },
                })
              }}
            >
              {data.page_numbers.map((page) => (
                <option key={page} value={page}>
                  Page {page}
                  {data.unassigned_page_numbers.includes(page)
                    ? " · needs coverage check"
                    : data.information_pages.some(
                          (item) => item.page_number === page
                        )
                      ? " · information page"
                      : ""}
                </option>
              ))}
            </select>
          </label>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              const page =
                (focus ? originals.get(focus.rowId)?.page_number : undefined) ??
                sourcePage
              setFocus({
                rowId: `page:${page}`,
                locator: { kind: "page_only", page },
              })
            }}
          >
            Show selected page
          </Button>
        </details>
        {!excludedCopy &&
          !data.assignment_only &&
          !(batchReview && data.current_import) && (
            <div
              ref={confirmationControls}
              className="rounded border bg-muted/30 p-3 space-y-2"
            >
              {coverage.data && (
                <StatementCoverageReview
                  caseId={caseId}
                  review={coverage.data}
                  decision={coverageDecision}
                  change={setCoverageDecision}
                  canEdit={canEdit}
                  inBatch={!!batchReview}
                />
              )}
              {coverage.pending && (
                <p role="status">
                  Checking for other statements covering these dates…
                </p>
              )}
              {coverage.error && (
                <div role="alert">
                  <p>{coverage.error}</p>
                  <Button variant="outline" onClick={coverage.retry}>
                    Retry overlap check
                  </Button>
                </div>
              )}
              {data.metadata.account_closure && (
                <div className="space-y-2">
                  <p>
                    The statement records this account as closed on{" "}
                    {data.metadata.account_closure.date}. This is an account
                    notice, not a payment. An unprinted closing balance remains
                    unknown.
                  </p>
                  <Button
                    variant="outline"
                    onClick={() => {
                      const closure = data.metadata.account_closure!
                      setFocus({
                        rowId: `${closure.page_number}:${closure.table_index}:${closure.row_index}`,
                        locator: closure.source_cells[0]?.locator,
                      })
                    }}
                  >
                    View account closure in PDF
                  </Button>
                </div>
              )}
              <p>
                {data.can_record_account_closure && included.length === 0
                  ? "Save the account, statement period and printed closure notice. No transaction rows were found in this section. This does not supply a missing closing balance."
                  : data.can_import_balances && included.length === 0
                    ? "Save this account's statement period and its opening and closing balances. No transaction rows were found in this section. Check the original before saving."
                    : batchReview
                      ? `Save these ${included.length} checked transactions to the batch. Return to the batch to import all ready statements together.`
                      : `Import adds ${included.length} transactions to the case. Original readings and your corrections are retained. You can return to Transactions to correct a value after import.`}
              </p>
              <Button
                disabled={
                  !canEdit ||
                  confirm.isPending ||
                  saveBatchReview.isPending ||
                  blockedRows.length > 0 ||
                  detailProblems.length > 0 ||
                  coverage.pending ||
                  !!coverage.error ||
                  serverChecks.pending ||
                  !!serverChecks.error ||
                  unresolvedDifference
                }
                aria-describedby={
                  blockedRows.length || detailProblems.length
                    ? "statement-import-blockers"
                    : undefined
                }
                onClick={() => {
                  if (canEdit) {
                    if (batchReview) saveBatchReview.mutate("done")
                    else confirm.mutate()
                  }
                }}
              >
                {batchReview
                  ? saveBatchReview.isPending
                    ? "Saving checked statement…"
                    : "Save for bulk import"
                  : confirm.isPending
                    ? "Importing statement…"
                    : data.can_record_account_closure && included.length === 0
                      ? "Save account closure"
                      : data.can_import_balances && included.length === 0
                        ? "Save statement balances"
                        : `Confirm import of ${included.length} transactions`}
              </Button>
              {serverChecks.pending && (
                <p role="status">
                  Checking the current values before confirmation…
                </p>
              )}
              {!!serverChecks.error && (
                <p role="alert">
                  Statement checks could not finish. Use Retry statement checks
                  above.
                </p>
              )}
              {unresolvedDifference && (
                <p role="alert">
                  The current values leave a difference. Open Statement checks
                  above to correct it or record why it remains.
                </p>
              )}
              {(blockedRows.length > 0 || detailProblems.length > 0) && (
                <section
                  id="statement-import-blockers"
                  aria-label="What needs attention before import"
                  className="rounded border border-amber-500/50 bg-amber-50/60 dark:bg-amber-950/20 p-3 space-y-3"
                >
                  <h4 className="font-semibold">Before you can confirm</h4>
                  {detailProblems.map((problem, index) => (
                    <div
                      key={index}
                      className="flex flex-wrap items-center gap-2 text-sm"
                    >
                      <p>{problem.message}</p>
                      {problem.field && canEdit && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => focusDetail(problem.field!)}
                        >
                          Go to field
                        </Button>
                      )}
                    </div>
                  ))}
                  {blockedRows.length > 0 && (
                    <>
                      <p className="text-sm">
                        {blockedRows.length}{" "}
                        {blockedRows.length === 1 ? "row needs" : "rows need"}{" "}
                        your attention. Select Review row to open its fields
                        beside the PDF.
                      </p>
                      <ul className="space-y-3">
                        {blockedRows.slice(0, 8).map(({ row: r, problems }) => {
                          const original = originals.get(r.id)!
                          return (
                            <li key={r.id} className="text-sm">
                              <div className="flex flex-wrap items-center gap-2">
                                <strong>
                                  PDF page {original.page_number}, row{" "}
                                  {original.row_index + 1}
                                  {r.excluded ? " (not being imported)" : ""}
                                </strong>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => reviewRow(r.id)}
                                >
                                  Review row
                                </Button>
                              </div>
                              {r.description && <p>{r.description}</p>}
                              {problems.map((problem) => (
                                <p key={problem}>{problem}</p>
                              ))}
                            </li>
                          )
                        })}
                      </ul>
                      {blockedRows.length > 8 && (
                        <p className="text-sm">
                          Showing the first 8 rows. The next ones will appear as
                          these are resolved.
                        </p>
                      )}
                    </>
                  )}
                </section>
              )}
            </div>
          )}
      </fieldset>
      {saveBatchReview.isError && (
        <p role="alert">{saveBatchReview.error.message}</p>
      )}
      {confirm.isError && <p role="alert">{confirm.error.message}</p>}
      {confirm.isSuccess && (
        <p role="status">
          {confirm.data.account_closed_on
            ? "Account closure recorded. Open Review accounts in Statements to inspect its source."
            : confirm.data.transaction_count === 0
              ? "Statement balances saved. Use Review accounts in Statements to see its coverage."
              : `Imported ${confirm.data.transaction_count} transactions. Open Transactions to investigate them.`}
        </p>
      )}
    </div>
  )
}
