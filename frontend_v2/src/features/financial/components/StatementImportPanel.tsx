import {
  PaymentCounterpartyPicker,
  type PaymentCounterpartyLink,
} from "./PaymentCounterpartyPicker"
import { CurrencyOptions } from "./CurrencyOptions"
import { currencyMinorUnits } from "../lib/ledger-format"
import { ImportedStatementDetails } from "./ImportedStatementDetails"
import { SavedStatementPayments } from "./SavedStatementPayments"
import { useStatementCoverageReview } from "../hooks/use-statement-coverage-review"
import { StatementCoverageReview } from "./StatementCoverageReview"
import { useBatchReview } from "../lib/batch-review-context"
import {
  useStatementFiles,
  usesPdfStatementReader,
} from "../hooks/use-statement-register"
import {
  StatementPeriodSelect,
  StatementSectionPicker,
} from "./StatementSectionPicker"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { statementRowLocator } from "../lib/statement-row-locator"
import { useStatementChecks } from "../hooks/use-statement-checks"
import { StatementArithmeticChecks } from "./StatementArithmeticChecks"
import { StatementReconciliationSummary } from "./StatementReconciliationSummary"
import { StatementDuplicateDecision } from "./StatementDuplicateDecision"
import {
  statementDuplicateDisposition,
  statementDuplicateResponse,
} from "../lib/statement-duplicate"
import {
  statementAssessment,
  statementBlocker,
} from "../lib/statement-assessment"
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
import { ApiError, fetchAPI } from "@/lib/api-client"
import { PdfReviewIntake } from "./PdfReviewIntake"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"
import { StatementSourceTools } from "./StatementSourceTools"
import { StatementRowEditor } from "./StatementRowEditor"
import { StatementRowCorrectionStatus } from "./StatementRowCorrectionStatus"
import {
  statementReviewSnapshot,
  statementRowSnapshot,
} from "../lib/statement-row-snapshot"
import {
  statementControlLabel,
  statementControlInputLabel,
} from "../lib/statement-control-label"
import { ManualTransactionPosition } from "./ManualTransactionPosition"
import { StatementCurrencyControl } from "./StatementCurrencyControl"
import { StatementBulkCorrections } from "./StatementBulkCorrections"
import { StatementRowAssignment } from "./StatementRowAssignment"
import { SavedReviewConflict } from "./SavedReviewConflict"
import { PreviousStatementReviews } from "./PreviousStatementReviews"
import { reviewRecoverySchema } from "../lib/review-recovery"
import { PrintedStatementTable } from "./PrintedStatementTable"
import { StatementRowReviewStatus } from "./StatementRowReviewStatus"
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
import { useFinancialDraft } from "../stores/financial-drafts"

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
  value_sources: z
    .record(
      z.string(),
      z.object({
        page_number: z.number(),
        table_index: z.number(),
        row_index: z.number(),
        source_cell: cell,
      })
    )
    .optional(),
  fields: z.record(z.string(), z.string()),
  issues: z.array(z.string()),
  excluded: z.boolean(),
  kind: z.string(),
})
const proposalSchema = z.object({
  recovered_saved_section: z.boolean().default(false),
  statement_page_numbers: z.array(z.number()).default([]),
  document_review: paymentDocumentProposal.optional(),
  reading_failure: z.string().nullish(),
  duplicate_disposition: statementDuplicateDisposition.nullish(),
  case_id: z.string(),
  evidence_file_id: z.string(),
  filename: z.string(),
  currency: z.string(),
  detected_currency: z.string().optional(),
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
  record_count: z.number().optional(),
  incomplete_count: z.number().optional(),
  can_import_balances: z.boolean().default(false),
  balance_basis: z.enum(["operation", "liquidation"]).nullish(),
  prior_period_settlement_pages: z
    .array(z.number().int().positive())
    .default([]),
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
        account_type: z.string().optional(),
        currency: z.string().optional(),
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
      record_count: z.number().optional(),
      incomplete_count: z.number().optional(),
      currency: z.string().nullable().optional(),
      refresh_available: z.boolean().optional(),
      refresh_review_required: z.boolean().optional(),
      refresh_transaction_count: z.number().optional(),
      refresh_admission: statementAssessment.nullish(),
      refresh_requires_reconciliation: z.boolean().optional(),
      refresh_currency_conflict: z
        .object({
          saved_currency: z.string(),
          reading_currency: z.string(),
          message: z.string(),
        })
        .nullish(),
      details: z
        .object({
          holder: z.string(),
          account_number: z.string(),
          institution: z.string(),
          period_start: z.string(),
          period_end: z.string(),
        })
        .optional(),
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
  record_count?: number
  incomplete_count?: number
  filename?: string
  account_closed_on?: string | null
}
type Proposal = z.infer<typeof proposalSchema>
type Edit = {
  id: string
  excluded: boolean
  manual_page?: number | null
  source_order_anchor?: { relation: "before" | "after"; row_id: string } | null
  date: string
  date_unprinted?: boolean
  date_values?: Partial<Record<DateRole, string>>
  description: string
  counterparty_link?: PaymentCounterpartyLink | null
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
  record_count: z.number().optional(),
  incomplete_count: z.number().optional(),
  source_document_id: z
    .string()
    .nullish()
    .transform((value) => value ?? undefined),
  account_id: z
    .string()
    .nullish()
    .transform((value) => value ?? undefined),
  applied: z.literal(true),
  outcome: z.string().optional(),
  ignored: z.boolean().optional(),
  duplicate_disposition: statementDuplicateDisposition.optional(),
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
  return currencyMinorUnits(currency) ?? 2
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

  if (!caseId) return null
  return (
    <section
      aria-label="Statement import"
      className="rounded-lg border bg-card p-4 space-y-3"
    >
      {!batchReview && (
        <div className="flex flex-wrap justify-between items-center gap-3">
          <div>
            <h2 className="font-semibold">Statement review</h2>
            <p className="text-sm text-muted-foreground">
              {canEdit
                ? "Check a statement against its PDF. Imported payments are available in Transactions; account and balance corrections can be saved here."
                : "Open a statement to compare its extracted values with the original PDF."}
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setOpen(!open)}>
              {open
                ? "All files & imports"
                : canEdit
                  ? "Import a statement"
                  : "Open statements"}
            </Button>
          </div>
        </div>
      )}
      <div hidden={!open && !batchReview}>
        {!batchReview && (
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
              PDF being reviewed
              <select
                aria-label="Uploaded statement"
                className="block border rounded bg-background p-2 w-full"
                value={fileId || ""}
                onChange={(e) => setFileId(e.target.value || null)}
              >
                <option value="">Choose a statement</option>
                {fileId &&
                  (!selectedFile || selectedFile.financial_removed) && (
                    <option value={fileId}>
                      {selectedFile
                        ? `${selectedFile.original_filename} · removed from Financial`
                        : `Selected source · ${fileId}`}
                    </option>
                  )}
                {files.data
                  ?.filter(
                    (f) => !f.financial_removed && usesPdfStatementReader(f)
                  )
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
        {fileId && files.isPending ? (
          <p role="status">Loading the selected source…</p>
        ) : fileId && selectedFile?.financial_removed ? (
          <div className="rounded border p-3 space-y-3" role="alert">
            <h3 className="font-semibold">
              This source was removed from Financial
            </h3>
            <p className="text-sm break-words">
              {selectedFile.original_filename}
            </p>
            <p className="text-sm">
              This retained source is not available for statement review here.
              Opening this link has not restored it or changed any saved work.
              Another upload with the same name is a separate source.
            </p>
            <p className="text-xs text-muted-foreground break-all">
              Source reference: {fileId}
            </p>
            <Button variant="outline" asChild>
              <a
                href={`/cases/${encodeURIComponent(caseId)}/evidence?file=${encodeURIComponent(fileId)}&from=financial`}
              >
                Open source location in Evidence
              </a>
            </Button>
          </div>
        ) : (
          fileId && (
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
          )
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
  const [detailsRequest, setDetailsRequest] = useState(0)
  const savedDetails = useRef<HTMLDivElement>(null)
  const [checkingSavedCurrency, setCheckingSavedCurrency] = useState(false)
  const recordedStatement = useRef<HTMLElement>(null)
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
    useStatementWorkspace
      .getState()
      .setReviewChoice(choiceKey, { statementId, currency: "" })
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
  useEffect(() => {
    if (checkingSavedCurrency && !query.isFetching && query.data) {
      setCheckingSavedCurrency(false)
      recordedStatement.current?.scrollIntoView({ block: "start" })
      recordedStatement.current?.focus({ preventScroll: true })
    }
  }, [checkingSavedCurrency, query.isFetching, query.data])
  if (query.isPending)
    return (
      <p role="status" className="py-4">
        Reading the statement and checking its transactions…
      </p>
    )
  if (query.isError) {
    const unavailable =
      query.error instanceof ApiError && [404, 410].includes(query.error.status)
    return (
      <div className="py-4 space-y-2">
        <h3 className="font-semibold">Statement review unavailable</h3>
        <p role="alert">{query.error.message}</p>
        <p className="text-xs text-muted-foreground break-all">
          Source reference: {fileId}
        </p>
        {unavailable && (
          <p className="text-sm">
            This exact source could not be found for review in this case. Check
            its location in Evidence or return to the processing batch. Another
            upload with the same name has not been substituted.
          </p>
        )}
        <Button onClick={() => void query.refetch()}>
          Retry statement review
        </Button>
        <Button variant="outline" asChild>
          <a
            href={`/cases/${encodeURIComponent(caseId)}/evidence?file=${encodeURIComponent(fileId)}&from=financial`}
          >
            Open source location in Evidence
          </a>
        </Button>
        {currency && (
          <Button variant="outline" onClick={() => setCurrency("")}>
            Change currency
          </Button>
        )}
        {!unavailable && (
          <ReprocessStatement
            key={fileId}
            caseId={caseId}
            fileId={fileId}
            onReady={onReprocessed}
          />
        )}
      </div>
    )
  }
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
        <p className="text-sm mt-3">
          Loupe could not identify the currency confidently. Choose it once for
          this statement.
        </p>
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
            <CurrencyOptions />
          </select>
        </label>
      </div>
    )
  return (
    <div className="space-y-3">
      <section
        aria-label="Current statement context"
        className="rounded-lg border bg-muted/20 p-4 space-y-2"
      >
        <p className="text-sm font-medium">
          {query.data.statement_choices.length > 1
            ? `This PDF contains ${query.data.statement_choices.length} account statements. You are viewing one account, currency and period below.`
            : "You are viewing one statement."}
        </p>
        <h3 className="text-lg font-semibold">
          {[
            query.data.current_import?.details?.holder ??
              query.data.metadata.holder,
            query.data.current_import?.details?.account_number ??
              query.data.metadata.account_number,
          ]
            .filter(Boolean)
            .join(" · ") || "Account details need review"}
        </h3>
        <p className="text-sm">
          {query.data.current_import?.details?.period_start ||
            query.data.metadata.period_start ||
            "Start date not recorded"}
          {" to "}
          {query.data.current_import?.details?.period_end ||
            query.data.metadata.period_end ||
            "End date not recorded"}
          {" · "}
          {query.data.current_import?.currency || query.data.currency}
        </p>
        <p className="text-sm">
          {query.data.current_import?.excluded_as_duplicate
            ? "This copy is excluded. Its payments are not counted in Transactions."
            : query.data.current_import?.transaction_count
              ? `Already imported: ${query.data.current_import.transaction_count} payments from this period are in Transactions. You do not need to import this period again.`
              : query.data.current_import &&
                  !query.data.current_import.incomplete_count
                ? "This period’s account and balances are saved. It has no imported payments."
                : query.data.can_import_balances &&
                    query.data.transaction_count === 0 &&
                    query.data.needs_attention === 0
                  ? "This statement records balances and no transactions. Save its account and balances below; no payments need to be added."
                  : "This period has no usable imported payments yet. Review its readings below, then save the payments to Transactions."}
        </p>
        {query.data.current_import &&
          query.data.current_import.transaction_count > 0 &&
          !query.data.current_import.excluded_as_duplicate && (
            <Button
              variant="primary"
              onClick={() =>
                onImported({
                  ...query.data.current_import!,
                  case_id: caseId,
                  account_id:
                    query.data.current_import!.account_id || undefined,
                  filename:
                    query.data.current_import!.filename || query.data.filename,
                })
              }
            >
              View {query.data.current_import.transaction_count} payments in
              Transactions for this period
            </Button>
          )}
      </section>
      {query.data.current_import &&
      !query.data.current_import.excluded_as_duplicate &&
      canEdit &&
      !batchReview?.readOnly ? (
        <div id="saved-statement-details" ref={savedDetails} tabIndex={-1}>
          <ImportedStatementDetails
            key={query.data.current_import.source_document_id}
            caseId={caseId}
            sourceId={query.data.current_import.source_document_id}
            withSource
            initiallyOpen
            focusField={detailsRequest ? "balances" : batchReview?.field}
            editRequest={detailsRequest}
          />
        </div>
      ) : (
        <StatementCurrencyControl
          currency={query.data.current_import?.currency || query.data.currency}
          detectedCurrency={query.data.detected_currency}
          disabled={
            !canEdit || !!batchReview?.readOnly || !!query.data.current_import
          }
          onChange={setCurrency}
        />
      )}
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
          <section
            className="rounded border p-4 space-y-3"
            aria-label="Recorded statement import"
            ref={recordedStatement}
            tabIndex={-1}
          >
            <h3 className="font-semibold">
              {query.data.current_import.transaction_count
                ? `${query.data.current_import.transaction_count} payments saved to Transactions`
                : query.data.current_import.incomplete_count
                  ? query.data.can_import_balances &&
                    query.data.transaction_count === 0 &&
                    query.data.needs_attention === 0
                    ? "The earlier import mistook statement information for payments"
                    : "These payments have not reached Transactions"
                  : "Statement balances saved"}
            </h3>
            <p>
              {query.data.current_import.transaction_count ||
              query.data.current_import.incomplete_count
                ? `${query.data.current_import.transaction_count} usable payments were saved.`
                : "The account, statement dates and printed balances are saved. No payments were added to Transactions."}
              {!!query.data.current_import.incomplete_count &&
                ` The earlier import also retained ${query.data.current_import.incomplete_count} readings with missing values.`}
              {query.data.current_import.transaction_count === 0 &&
                !!query.data.current_import.incomplete_count &&
                " The PDF is retained, but those readings are not payments in Transactions."}
            </p>
            {!!(
              query.data.current_import.transaction_count ||
              query.data.current_import.incomplete_count
            ) && (
              <SavedStatementPayments
                caseId={caseId}
                sourceId={query.data.current_import.source_document_id}
                hasIncomplete={!!query.data.current_import.incomplete_count}
              />
            )}
            {query.data.current_import.refresh_currency_conflict && (
              <section
                aria-label="Replacement currency review"
                className="rounded border border-amber-500 p-3 space-y-2"
              >
                <h4 className="font-semibold">
                  Check the replacement currency
                </h4>
                <p>
                  {query.data.current_import.refresh_currency_conflict.message}
                </p>
                <p>
                  Checking the reading in the saved currency does not convert
                  amounts or change your saved payments. The replacement must
                  still pass its reconciliation checks before it can be saved.
                </p>
                <Button
                  variant="outline"
                  disabled={query.isFetching}
                  onClick={() => {
                    const savedCurrency =
                      query.data.current_import!.refresh_currency_conflict!
                        .saved_currency
                    setCheckingSavedCurrency(true)
                    if (currency === savedCurrency) void query.refetch()
                    else setCurrency(savedCurrency)
                  }}
                >
                  Check this reading in saved{" "}
                  {
                    query.data.current_import.refresh_currency_conflict
                      .saved_currency
                  }
                </Button>
              </section>
            )}
            {canEdit &&
              query.data.current_import.evidence_file_id === fileId &&
              !query.data.current_import.refresh_currency_conflict &&
              (query.data.current_import.refresh_available ||
                query.data.current_import.refresh_review_required) && (
                <RefreshStoredReading
                  key={`${query.data.revision}:${query.data.current_import.revision}:${query.data.saved_review?.review_revision ?? ""}`}
                  data={query.data}
                  onImported={onImported}
                  checking={query.isFetching}
                  onRecheck={() => void query.refetch()}
                  onReviewDetails={() => {
                    setDetailsRequest((value) => value + 1)
                    savedDetails.current?.scrollIntoView({ block: "start" })
                    savedDetails.current?.focus({ preventScroll: true })
                  }}
                />
              )}
            {query.data.transaction_count !==
              query.data.current_import.transaction_count && (
              <p role="status">
                The current PDF reading found {query.data.transaction_count}{" "}
                payment readings; the saved import contains{" "}
                {query.data.current_import.transaction_count} payments. The new
                reading has not replaced those saved payments. Check the source
                before choosing to replace an import.
              </p>
            )}
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
          <h3 className="font-semibold">
            Compare this period with the original PDF
          </h3>
        )}
        {query.data.recovered_saved_section ? (
          <div className="space-y-3">
            <p>
              This section was separated from an earlier combined import. Edit
              its saved details or payments above; the original PDF remains
              available for comparison.
            </p>
            <TransactionSourceHighlight
              sourceDocumentId={fileId}
              locatorPayload={{
                kind: "page_only",
                page: query.data.page_numbers[0] || 1,
              }}
              wholePage
            />
          </div>
        ) : (
          <EditableStatement
            key={`${query.data.revision}:${batchReview?.draftRevision ?? "individual"}:${query.data.current_import?.revision ?? "unimported"}:${JSON.stringify(query.data.current_import?.details)}`}
            data={query.data}
            caseId={caseId}
            fileId={fileId}
            onImported={onImported}
          />
        )}
      </div>
    </div>
  )
}

function RefreshStoredReading({
  data,
  onImported,
  checking,
  onRecheck,
  onReviewDetails,
}: {
  data: Proposal
  onImported: (result?: StatementImportReceipt) => void
  checking: boolean
  onRecheck: () => void
  onReviewDetails: () => void
}) {
  const client = useQueryClient()
  const [compared, setCompared] = useState(false)
  const comparisonRequired = !!data.current_import?.refresh_review_required
  const priorDraft = serverStatementDraft(data.saved_review?.request)
  const paymentCount =
    data.current_import?.refresh_transaction_count ?? data.transaction_count
  const admission = data.current_import?.refresh_admission
  const requiresReconciliation =
    data.current_import?.refresh_requires_reconciliation ?? true
  const ready = !requiresReconciliation || admission?.can_import === true
  const update = useMutation({
    retry: false,
    mutationFn: async () => {
      const result = receipt.parse(
        await fetchAPI(
          `/api/financial/statement-import/sources/${data.current_import!.source_document_id}/refresh-reading?case_id=${data.case_id}`,
          {
            method: "POST",
            body: {
              expected_revision: data.current_import!.revision,
              expected_reading_revision: data.revision,
              currency: data.currency,
              ...(comparisonRequired && compared
                ? {
                    compared_review_revision:
                      data.saved_review?.review_revision,
                  }
                : {}),
            },
          }
        )
      )
      if (
        result.case_id !== data.case_id ||
        result.evidence_file_id !== data.evidence_file_id
      )
        throw Error("The updated reading does not belong to this statement.")
      return result
    },
    onSuccess: (result) => {
      void client.invalidateQueries()
      onImported({ ...result, filename: data.filename })
    },
  })
  return (
    <div
      className="rounded border p-3 space-y-2"
      role="region"
      aria-label="Replacement reading checks"
    >
      <p>
        {paymentCount
          ? `The current reading identifies ${paymentCount} payments in ${data.currency}. Its checks include your saved account details and balances.`
          : requiresReconciliation
            ? "The current reading contains selected payments that still need correction. Check them before saving to Transactions."
            : `This statement has printed balances in ${data.currency} and no usable payments. Saving balance observations does not confirm no activity.`}{" "}
        The earlier reading stays in history; this does not add duplicate
        payments.
      </p>
      <p role="status" className="font-medium">
        {checking
          ? "Checking the replacement reading against your saved details…"
          : !admission
            ? "Replacement checks are unavailable. Refresh them before saving payments."
            : admission.can_import
              ? "The replacement reading reconciles with your saved controls."
              : requiresReconciliation
                ? "Payments remain in review. Resolve these checks before saving to Transactions."
                : "Balances can be saved as unverified observations. Statement review is still required."}
      </p>
      <StatementReconciliationSummary
        calculation={admission?.calculation}
        pending={checking}
        controlBasis="saved"
        format={(value) =>
          `${displayAmount(value, exponent(data.currency))} ${data.currency}`
        }
      />
      {!checking && !!admission?.blockers.length && (
        <ul className="list-disc pl-5 space-y-1">
          {admission.blockers.map((blocker, index) => (
            <li key={blocker.reason_id || index}>{blocker.message}</li>
          ))}
        </ul>
      )}
      {(!admission || !admission.can_import) && (
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={onReviewDetails}>
            Review saved details and balances
          </Button>
          <Button variant="outline" disabled={checking} onClick={onRecheck}>
            Refresh replacement checks
          </Button>
        </div>
      )}
      {comparisonRequired && priorDraft && (
        <>
          <SavedReviewConflict
            draft={priorDraft}
            checked={compared}
            onChecked={setCompared}
            formatAmount={(value) =>
              `${displayAmount(value, exponent(data.currency))} ${data.currency}`
            }
          />
          <p className="text-sm">
            Saving uses the current PDF reading instead of the earlier
            unfinished draft. Your saved account details and balances are kept;
            the earlier draft remains in history.
          </p>
        </>
      )}
      <Button
        disabled={
          update.isPending ||
          checking ||
          !ready ||
          (comparisonRequired && !compared)
        }
        onClick={() => update.mutate()}
      >
        {update.isPending
          ? "Updating saved reading…"
          : paymentCount
            ? `Save ${paymentCount} payments to Transactions`
            : requiresReconciliation
              ? "Save reviewed payments to Transactions"
              : "Save statement balances and open account"}
      </Button>
      {update.isError && <p role="alert">{update.error.message}</p>}
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
  const [pendingSaveSnapshot, setPendingSaveSnapshot] = useState("")
  const [savedServerSnapshot, setSavedServerSnapshot] = useState("")
  const [savedRowSnapshots, setSavedRowSnapshots] = useState(() => {
    const draft = batchReview
      ? batchReview.draft
      : serverStatementDraft(data.saved_review?.request)
    return new Map(
      draft?.revision === data.revision
        ? draft.rows.map((row) => [row.id, statementRowSnapshot(row)])
        : []
    )
  })
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
      const submittedSnapshot = JSON.stringify(request)
      setPendingSaveSnapshot(submittedSnapshot)
      if (batchReview)
        return {
          result: await batchReview.save(request),
          submittedSnapshot,
          acknowledgedSnapshot: submittedSnapshot,
          acknowledgedDraft: serverStatementDraft(request),
        }
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
      const acknowledgedDraft = serverStatementDraft(result.request)
      if (!acknowledgedDraft || acknowledgedDraft.revision !== data.revision)
        throw Error(
          "The save response did not confirm this reading. Keep your edits and retry Save progress."
        )
      setProgressRevision(result.review_revision)
      client.setQueriesData<Proposal>(
        { queryKey: ["statement-import", caseId, fileId] },
        (cached) =>
          cached?.revision === data.revision
            ? { ...cached, saved_review: result }
            : cached
      )
      return {
        result,
        submittedSnapshot,
        acknowledgedSnapshot:
          statementReviewSnapshot(result.request) ===
          statementReviewSnapshot(request)
            ? submittedSnapshot
            : JSON.stringify(result.request),
        acknowledgedDraft,
      }
    },
    onSuccess: async ({ acknowledgedSnapshot, acknowledgedDraft }, mode) => {
      setSavedServerSnapshot(acknowledgedSnapshot)
      if (acknowledgedDraft)
        setSavedRowSnapshots(
          new Map(
            acknowledgedDraft.rows.map((row) => [
              row.id,
              statementRowSnapshot(row),
            ])
          )
        )
      if (acknowledgedSnapshot !== currentRequestSnapshot.current) return
      if (mode === "previous") await batchReview!.previousProblem?.()
      else if (mode === "next") await batchReview!.nextProblem?.()
      else if (mode === "done") batchReview!.saved()
    },
  })
  const { canEdit: caseCanEdit } = useFinancialAccess()
  const [localDuplicate, setLocalDuplicate] =
    useState<z.infer<typeof statementDuplicateDisposition>>()
  const duplicateDecision = localDuplicate ?? data.duplicate_disposition
  const [duplicateActionBusy, setDuplicateActionBusy] = useState(false)
  const excludedCopy = !!data.current_import?.excluded_as_duplicate
  const importedHere = data.current_import?.evidence_file_id === fileId
  const importedDetails = importedHere
    ? data.current_import?.details
    : undefined
  const canEdit =
    caseCanEdit &&
    !excludedCopy &&
    !importedHere &&
    !batchReview?.readOnly &&
    !(batchReview && data.current_import)
  useEffect(() => {
    const navigation = batchReview?.beforeNavigate
    if (!navigation) return
    navigation.current = canEdit
      ? async () => {
          const result = await saveBatchReview.mutateAsync("progress")
          if (result.acknowledgedSnapshot !== currentRequestSnapshot.current)
            throw Error(
              "There are newer edits that were not saved. Save progress before leaving this statement."
            )
          return result
        }
      : null
    return () => {
      navigation.current = null
    }
  })
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
  const [browserDraft] = useState(() =>
    readStatementDraft(draftKey, data.revision)
  )
  const [saved] = useState(() =>
    importedHere
      ? null
      : (browserDraft ??
        (batchReview?.draft?.revision === data.revision
          ? batchReview.draft
          : !batchReview && recovered?.revision === data.revision
            ? recovered
            : null))
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
  const balanceControls = useRef<HTMLDivElement>(null)
  const balancePages = data.statement_page_numbers.length
    ? data.statement_page_numbers
    : data.page_numbers.length
      ? data.page_numbers
      : [...new Set(data.rows.map((row) => row.page_number))]
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
    [holder, setHolder] = useState(
      importedDetails?.holder ?? saved?.holder ?? data.metadata.holder
    ),
    [account, setAccount] = useState(
      importedDetails?.account_number ??
        saved?.account ??
        data.metadata.account_number
    )
  const [focus, setFocus] = useState<{
    rowId: string
    locator: unknown
  } | null>({
    rowId:
      data.rows.find((row) => !row.excluded && row.page_number === initialPage)
        ?.id ?? "",
    locator: statementRowLocator(
      data.rows.find((row) => !row.excluded && row.page_number === initialPage),
      initialPage
    ),
  })
  const [reviewFilters, setReviewFilters] = useFinancialDraft(
    caseId,
    `review-filters:${fileId}:${data.statement_id || "default"}`,
    { showExcluded: false, onlyIssues: false }
  )
  const { showExcluded, onlyIssues } = reviewFilters
  const setShowExcluded = (value: boolean) =>
    setReviewFilters((previous) => ({ ...previous, showExcluded: value }))
  const setOnlyIssues = (value: boolean) =>
    setReviewFilters((previous) => ({ ...previous, onlyIssues: value }))
  const [activeRows, setActiveRows] = useState<Set<string>>(() => new Set())
  const keepRowVisible = (id: string) =>
    setActiveRows((previous) =>
      previous.has(id) ? previous : new Set([...previous, id])
    )
  const [amountText, setAmountText] = useState<Record<string, string>>(
    saved?.amountText ?? {}
  )
  const [institution, setInstitution] = useState(
    importedDetails?.institution ??
      saved?.institution ??
      data.metadata.institution
  )
  const [periodStart, setPeriodStart] = useState(
      importedDetails?.period_start ??
        saved?.periodStart ??
        data.metadata.period_start
    ),
    [periodEnd, setPeriodEnd] = useState(
      importedDetails?.period_end ??
        saved?.periodEnd ??
        data.metadata.period_end
    ),
    [detailsReason, setDetailsReason] = useState(saved?.detailsReason ?? "")
  const [balanceException, setBalanceException] = useState(
    saved?.balanceException ?? { revision: "", reason: "" }
  )
  const [noActivityRevision, setNoActivityRevision] = useState(
    saved?.noActivityRevision ?? ""
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
      holder,
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
  const duplicateBlocked = coverageBlocked && coverage.data?.matching_statement
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
      fields:
        added.id === "manual:opening-balance" ||
        added.id === "manual:closing-balance"
          ? {
              description:
                added.id === "manual:opening-balance"
                  ? "Opening Balance"
                  : "Closing Balance",
            }
          : {},
      issues: added.excluded
        ? []
        : ["Manually added transaction. Record the source page."],
      excluded: added.excluded,
      kind:
        added.id === "manual:opening-balance" ||
        added.id === "manual:closing-balance"
          ? "balance"
          : "manual_entry",
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
      const initial = initialById.get(r.id)
      if (!initial) return true
      return (
        Boolean(r.date_unprinted) !== Boolean(initial.date_unprinted) ||
        JSON.stringify(r.date_values ?? {}) !==
          JSON.stringify(initial.date_values ?? {}) ||
        [
          "excluded",
          "date",
          "description",
          "counterparty",
          "counterparty_link",
          "amount_minor",
          "direction",
          "balance_minor",
        ].some((k) => r[k as keyof Edit] !== initial[k as keyof Edit])
      )
    },
    [initialById]
  )
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
        originals.get(r.id)?.kind === "statement_total"
          ? `Enter a valid ${statementControlLabel("statement_total", originals.get(r.id)?.fields).toLowerCase()} from the source. Clearing an identified total does not resolve its check.`
          : "Enter a valid printed balance, or clear it if none is printed."
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
      if (r.counterparty.length > 512)
        problems.push(
          "The party name is too long. Check it against the original."
        )
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
  const hasStatementBalance = emptyStatementBalances.some(
    (r) =>
      r.balance_minor !== null &&
      /^-?\d+$/.test(r.balance_minor) &&
      BigInt(r.balance_minor) >=
        (data.metadata.balance_convention === "liability_owed"
          ? -9223372036854775807n
          : -9223372036854775808n) &&
      BigInt(r.balance_minor) <= 9223372036854775807n
  )
  const emptyEntries = rows.filter((r) => {
    const original = originals.get(r.id)
    return (
      !r.excluded &&
      original?.kind === "unresolved" &&
      !r.manual_page &&
      !r.date &&
      !r.date_unprinted &&
      !Object.values(r.date_values ?? {}).some(Boolean) &&
      !r.description.trim() &&
      !r.counterparty.trim() &&
      !r.amount_minor &&
      !r.direction &&
      r.balance_minor === null
    )
  })
  const [setAsideIds, setSetAsideIds] = useState<string[]>([])
  const setAsideEmptyEntries = () => {
    const ids = new Set(emptyEntries.map((r) => r.id))
    setRows((current) =>
      current.map((r) => (ids.has(r.id) ? { ...r, excluded: true } : r))
    )
    setSetAsideIds([...ids])
    setCorrectionPage(0)
  }
  const detailProblems: { message: string; field?: string }[] = []
  if (coverageBlocked)
    detailProblems.push({
      message: duplicateBlocked
        ? "A matching statement needs a duplicate decision before import. Compare the existing statement below."
        : "Another statement covers these dates. You can compare the statements now or after importing.",
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
      message:
        "Enter the account holder shown on the statement before importing payments.",
      field: "Account holder",
    })
  if (!account.trim())
    detailProblems.push({
      message:
        "Enter the account number shown on the statement before importing payments.",
      field: "Account number",
    })
  if (Boolean(periodStart) !== Boolean(periodEnd))
    detailProblems.push({
      message:
        "The statement period is incomplete. Its coverage will stay unknown until corrected.",
      field: periodStart ? "Period end" : "Period start",
    })
  else if (periodStart > periodEnd)
    detailProblems.push({
      message: "The period end must be on or after the start.",
      field: "Period end",
    })
  if (data.current_import) {
    if (data.current_import.refresh_currency_conflict)
      detailProblems.push({
        message: data.current_import.refresh_currency_conflict.message,
      })
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
      if (!detailsReason.trim())
        detailProblems.push({
          message:
            "Explain why this reading should replace the previous import.",
          field: "Reason for detail corrections",
        })
    }
  }
  if (
    included.length === 0 &&
    !data.can_record_account_closure &&
    !hasStatementBalance
  )
    detailProblems.push({
      message:
        "Enter at least one printed opening or closing balance to save a statement without transactions.",
      field: "Statement balances",
    })
  const focusDetail = (field: string) => {
    if (importedHere) {
      const panel = document.getElementById("saved-statement-details")
      const label = `Saved ${field.toLowerCase()}`
      const input = panel?.querySelector<HTMLElement>(`[aria-label="${label}"]`)
      ;(input || panel)?.focus({ preventScroll: true })
      ;(input || panel)?.scrollIntoView({ block: "center", behavior: "smooth" })
      return
    }
    if (field === "Statement balances") {
      const control =
        balanceControls.current?.querySelector<HTMLElement>("input,button")
      control?.focus({ preventScroll: true })
      balanceControls.current?.scrollIntoView({
        block: "center",
        behavior: "smooth",
      })
      return
    }
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
    no_activity_confirmed: !!noActivityRevision,
    no_activity_revision: noActivityRevision || null,
    rows: rows.map((r) => ({
      ...r,
      direction: r.direction || null,
      amount_minor: r.excluded && !r.amount_minor ? "0" : r.amount_minor,
    })),
  })
  currentRequestSnapshot.current = JSON.stringify(importRequest())
  const renderSnapshot = currentRequestSnapshot.current
  const initialReviewSnapshot = useRef(renderSnapshot)
  const duplicateCheckDirty =
    savedServerSnapshot !== renderSnapshot &&
    (renderSnapshot !== initialReviewSnapshot.current || !!browserDraft)
  const duplicateIgnored =
    !!duplicateDecision?.current &&
    duplicateDecision.status === "ignored" &&
    !duplicateCheckDirty
  const automaticDuplicateSnapshot = useRef<string | null>(null)
  const duplicateCheck = useMutation({
    retry: false,
    mutationFn: async (snapshot: string) => {
      const result = statementDuplicateResponse.parse(
        await fetchAPI(
          `/api/financial/statement-import/${fileId}/duplicate-disposition?${new URLSearchParams({ case_id: caseId })}`,
          {
            method: "POST",
            body: {
              action: "check",
              expected_reading_revision: data.revision,
              statement_id: data.statement_id ?? null,
              currency: data.currency,
            },
          }
        )
      )
      if (
        result.case_id !== caseId ||
        result.evidence_file_id !== fileId ||
        (result.statement_id || null) !== (data.statement_id || null) ||
        result.duplicate_disposition.reading_revision !== data.revision
      )
        throw Error(
          "The duplicate check no longer matches this review. Reopen this statement to inspect its saved decision."
        )
      return { snapshot, decision: result.duplicate_disposition }
    },
    onSuccess: ({ snapshot, decision }) => {
      if (snapshot === currentRequestSnapshot.current)
        setLocalDuplicate(decision)
      void client.invalidateQueries({
        queryKey: ["statement-import-status", caseId],
      })
      void client.invalidateQueries({ queryKey: ["financial-batch", caseId] })
    },
  })
  const checkDuplicate = duplicateCheck.mutate
  const automaticDuplicateEligible =
    !!coverage.data?.matching_statement &&
    !duplicateDecision &&
    !saved &&
    !detailsChanged &&
    !rows.some((row) => changed(row) || row.reason) &&
    !data.current_import &&
    caseCanEdit
  useEffect(() => {
    if (
      !automaticDuplicateEligible ||
      automaticDuplicateSnapshot.current !== null
    )
      return
    automaticDuplicateSnapshot.current = currentRequestSnapshot.current
    checkDuplicate(currentRequestSnapshot.current)
  }, [automaticDuplicateEligible, checkDuplicate])
  const confirm = useMutation({
    retry: false,
    mutationFn: async () => {
      const result = receipt.parse(
        await (batchReview?.confirm
          ? batchReview.confirm(importRequest())
          : fetchAPI(
              `/api/financial/statement-import/${fileId}/confirm?${new URLSearchParams({ case_id: caseId })}`,
              {
                method: "POST",
                body: importRequest(),
                timeout: 120000,
              }
            ))
      )
      if (
        result.case_id !== caseId ||
        result.evidence_file_id !== fileId ||
        (!result.ignored &&
          (result.record_count ?? result.transaction_count) !== included.length)
      )
        throw Error("The import result does not match the reviewed statement.")
      return result
    },
    onSuccess: (result) => {
      void client.invalidateQueries()
      if (result.ignored && result.duplicate_disposition) {
        setLocalDuplicate(result.duplicate_disposition)
        return
      }
      onImported({ ...result, filename: data.filename })
    },
  })
  useEffect(() => {
    if ((confirm.isSuccess && !confirm.data.ignored) || importedHere) {
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
      noActivityRevision,
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
    noActivityRevision,
    coverageDecision,
    amountText,
    confirm.isSuccess,
    confirm.data?.ignored,
    importedHere,
  ])
  const serverChecks = useStatementChecks(caseId, fileId, {
    expected_revision: data.revision,
    statement_id: data.statement_id ?? null,
    currency: data.currency,
    holder,
    institution,
    account_number: account,
    period_start: periodStart,
    period_end: periodEnd,
    no_activity_confirmed: !!noActivityRevision,
    no_activity_revision: noActivityRevision || null,
    rows: rows.map((r) => ({
      id: r.id,
      excluded: r.excluded,
      manual_page: r.manual_page ?? null,
      source_order_anchor: r.source_order_anchor ?? null,
      date: r.date,
      date_unprinted: Boolean(r.date_unprinted),
      date_values: r.date_values || {},
      description: r.description,
      counterparty: r.counterparty,
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
  const unresolvedDifference = balanceMismatch
  const incompleteCount = data.currency
    ? blockedRows.filter(({ row }) => !row.excluded).length
    : included.length
  const importDisabled =
    !canEdit ||
    !holder.trim() ||
    !account.trim() ||
    serverChecks.pending ||
    !!serverChecks.error ||
    !serverChecks.admission?.can_import ||
    !!data.current_import?.refresh_currency_conflict ||
    duplicateIgnored ||
    duplicateCheck.isPending ||
    duplicateActionBusy ||
    duplicateBlocked ||
    confirm.isPending ||
    saveBatchReview.isPending ||
    assignmentSaving ||
    (data.review_recovery?.required && !recoveryCompared) ||
    (savedReadingChanged && (!previousReviewChecked || !!data.saved_review)) ||
    (!!data.current_import && !replacePrevious) ||
    (replacePrevious && !detailsReason.trim()) ||
    !!data.reading_failure ||
    (!included.length &&
      !hasStatementBalance &&
      !data.can_record_account_closure)
  const submitImport = () => {
    if (
      batchReview &&
      !confirm.isPending &&
      !saveBatchReview.isPending &&
      canEdit
    ) {
      saveBatchReview.mutate("done")
      return
    }
    if (importDisabled) return
    if (batchReview) saveBatchReview.mutate("done")
    else confirm.mutate()
  }
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
        originals.get(r.id)?.kind === "balance") &&
      (!onlyIssues ||
        changed(r) ||
        rowProblems(r).length > 0 ||
        (!!originals.get(r.id)?.issues.length && !r.reason && !changed(r)))
  )
  const currentCorrectionPage = Math.min(
    correctionPage,
    Math.max(0, Math.ceil(visible.length / 50) - 1)
  )
  const pageRows = visible.slice(
    currentCorrectionPage * 50,
    (currentCorrectionPage + 1) * 50
  )
  // Active inputs are not derived from a changing filter or page projection.
  // Keep them mounted until the investigator explicitly finishes that row.
  const correctionRows = [
    ...pageRows,
    ...rows.filter(
      (r) => activeRows.has(r.id) && !pageRows.some((p) => p.id === r.id)
    ),
  ]
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
    original.value_sources?.balance?.source_cell.locator ??
    original.source_cells.find(
      (cell) => String(cell.column_index) === original.fields.balance_column
    )?.locator ?? { kind: "page_only", page: original.page_number }
  const editBalance = (id: string) => {
    const original = originals.get(id)
    if (!original) return
    keepRowVisible(id)
    const balanceRows = rows.filter(
      (row) =>
        showExcluded ||
        !row.excluded ||
        originals.get(row.id)?.kind === "balance"
    )
    setCorrectionPage(
      Math.max(
        0,
        Math.floor(balanceRows.findIndex((row) => row.id === id) / 50)
      )
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
    if (original.kind === "statement_total") {
      openInlineRow(id)
      return
    }
    keepRowVisible(id)
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
    if (
      !original.source_cells.length &&
      !original.id.startsWith("manual:") &&
      original.kind !== "statement_total"
    ) {
      reviewRow(id)
      return
    }
    setSourcePage(original.page_number)
    setFocus({
      rowId: id,
      locator:
        original.kind === "statement_total"
          ? balanceLocator(original)
          : statementRowLocator(original, original.page_number),
    })
    setInlineRowId(id)
    requestAnimationFrame(() => {
      const editor = printedControls.current?.querySelector<HTMLElement>(
        '[aria-label="Edit selected statement row"]'
      )
      editor?.scrollIntoView({ block: "nearest", behavior: "smooth" })
      editor?.focus({ preventScroll: true })
      if (original.kind === "statement_total") {
        const name = statementControlInputLabel(original.kind, original.fields)
        const input = Array.from(
          editor?.querySelectorAll<HTMLInputElement>("input") ?? []
        ).find((node) => node.getAttribute("aria-label") === name)
        input?.focus({ preventScroll: true })
      }
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
            : [check.row_id, ...(check.contributing_row_ids ?? [])].filter(
                (id): id is string => !!id
              )
        ),
    ]),
  ]
  const inspectBlocker = (problem: z.infer<typeof statementBlocker>) => {
    const target = problem.target
    const id = target?.row_id || problem.row_id
    if (id) {
      if (originals.get(id)?.kind === "statement_total") openInlineRow(id)
      else if (target?.kind === "balance") editBalance(id)
      else {
        openInlineRow(id)
        const field = target?.field || problem.field
        requestAnimationFrame(() => {
          const names: Record<string, string> = {
            date: "Corrected transaction date",
            description: "Corrected description",
            counterparty: "Corrected paid by or paid to",
            balance_minor: statementControlInputLabel(
              originals.get(id)?.kind || "",
              originals.get(id)?.fields
            ),
            balance: statementControlInputLabel(
              originals.get(id)?.kind || "",
              originals.get(id)?.fields
            ),
            amount:
              editsById.get(id)?.direction === "credit"
                ? "Corrected credit"
                : "Corrected debit",
            direction:
              editsById.get(id)?.direction === "credit"
                ? "Corrected credit"
                : "Corrected debit",
            amount_minor:
              editsById.get(id)?.direction === "credit"
                ? "Corrected credit"
                : "Corrected debit",
            source_order_anchor: `Printed position ${id}`,
          }
          const name = names[field || ""]
          const element = [
            ...(printedControls.current?.querySelectorAll<HTMLElement>(
              "[aria-label]"
            ) ?? []),
          ].find((node) => node.getAttribute("aria-label") === name)
          element?.focus({ preventScroll: true })
          element?.scrollIntoView({ block: "nearest", behavior: "smooth" })
        })
      }
      return
    }
    if (target?.kind === "statement_field") {
      const labels: Record<string, string> = {
        holder: "Account holder",
        account_number: "Account number",
        institution: "Bank",
        period_start: "Period start",
        period_end: "Period end",
      }
      const label = labels[target.field || ""]
      if (label) {
        focusDetail(label)
        return
      }
    }
    if (target?.kind === "no_activity") {
      const input = document.querySelector<HTMLElement>(
        '[aria-label="Confirm no activity for this statement"]'
      )
      input?.focus({ preventScroll: true })
      input?.scrollIntoView({ block: "center", behavior: "smooth" })
      return
    }
    if (target?.kind === "balance") {
      focusDetail("Statement balances")
      return
    }
    if (target?.page && data.page_numbers.includes(target.page))
      showPage(target.page)
    printedControls.current?.scrollIntoView({
      block: "start",
      behavior: "smooth",
    })
    if (!target || target.kind === "saved_review") editValues()
  }
  const problemIndex = problemIds.indexOf(focus?.rowId ?? "")
  const savedRowsById = useMemo(() => {
    const draft = savedServerSnapshot
      ? serverStatementDraft(JSON.parse(savedServerSnapshot))
      : batchReview
        ? batchReview.draft
        : serverStatementDraft(data.saved_review?.request)
    return new Map(
      draft?.revision === data.revision
        ? draft.rows.map((row) => [row.id, row])
        : []
    )
  }, [
    savedServerSnapshot,
    data.saved_review?.request,
    data.revision,
    batchReview,
  ])
  const pendingRowSnapshots = useMemo(() => {
    const draft =
      saveBatchReview.isPending && pendingSaveSnapshot
        ? serverStatementDraft(JSON.parse(pendingSaveSnapshot))
        : null
    return new Map(
      draft?.rows.map((row) => [row.id, statementRowSnapshot(row)]) || []
    )
  }, [saveBatchReview.isPending, pendingSaveSnapshot])
  const blockersByRow = useMemo(() => {
    const result = new Map<string, z.infer<typeof statementBlocker>[]>()
    for (const blocker of serverChecks.admission?.blockers || []) {
      const id = blocker.target?.row_id || blocker.row_id
      if (!id) continue
      const messages = result.get(id) || []
      messages.push(blocker)
      result.set(id, messages)
    }
    return result
  }, [serverChecks.admission?.blockers])
  const rowTools = (id: string) => {
    if (!canEdit || (data.current_import && !replacePrevious)) return null
    const edit = editsById.get(id)
    const original = originals.get(id)
    if (
      !edit ||
      !original ||
      ![
        "transaction",
        "unresolved",
        "balance",
        "statement_total",
        "manual_entry",
      ].includes(original.kind)
    )
      return null
    const balanceChanged =
      edit.balance_minor !== (original.fields.balance ?? null) ||
      (savedRowsById.has(id) &&
        savedRowsById.get(id)?.balance_minor !==
          (original.fields.balance ?? null))
    const showBalanceCorrection =
      balanceChanged && ["transaction", "unresolved"].includes(original.kind)
    const balanceValueValid =
      edit.balance_minor === null || /^-?\d+$/.test(edit.balance_minor)
    const rowIssues = showBalanceCorrection
      ? [
          ...new Set([
            ...rowProblems(edit),
            ...(blockersByRow.get(id) || []).map((blocker) => blocker.message),
          ]),
        ]
      : []
    const rowReview =
      original.issues.length > 0 || (blockersByRow.get(id)?.length ?? 0) > 0 ? (
        <StatementRowReviewStatus
          rowId={id}
          originalIssues={original.issues}
          blockers={blockersByRow.get(id) || []}
          localProblems={rowProblems(edit)}
          pending={serverChecks.pending}
          error={serverChecks.error}
          assessed={!!serverChecks.admission}
          reviewed={changed(edit) || !!edit.reason}
          excluded={
            edit.excluded &&
            ["transaction", "unresolved"].includes(original.kind)
          }
          saved={savedRowSnapshots.get(id) === statementRowSnapshot(edit)}
          saving={saveBatchReview.isPending}
          failed={saveBatchReview.isError}
          canMarkChecked={
            !edit.excluded &&
            original.issues.length > 0 &&
            !edit.reason &&
            !changed(edit) &&
            rowProblems(edit).length === 0
          }
          onMarkChecked={() =>
            update(id, { reason: "Checked against the original statement." })
          }
          onInspect={inspectBlocker}
        />
      ) : null
    const correction = showBalanceCorrection ? (
      <StatementRowCorrectionStatus
        rowId={id}
        original={
          original.value_sources?.balance?.source_cell.expected_text ||
          original.source_cells.find(
            (cell) =>
              String(cell.column_index) === original.fields.balance_column
          )?.expected_text ||
          original.fields.balance ||
          "Not read"
        }
        reviewed={
          edit.balance_minor === null
            ? "Not entered"
            : balanceValueValid
              ? `${amountText[`balance:${id}`] ?? displayAmount(edit.balance_minor, digits)} ${data.currency}`
              : `Not a valid amount${amountText[`balance:${id}`] ? ` (entered: ${amountText[`balance:${id}`]})` : ""}`
        }
        saved={
          balanceValueValid &&
          savedRowSnapshots.get(id) === statementRowSnapshot(edit)
        }
        saving={saveBatchReview.isPending}
        newer={
          pendingRowSnapshots.has(id) &&
          pendingRowSnapshots.get(id) !== statementRowSnapshot(edit)
        }
        failed={saveBatchReview.isError}
        pendingChecks={serverChecks.pending}
        checksError={!!serverChecks.error}
        canImport={
          serverChecks.admission?.can_import === true && rowIssues.length === 0
        }
        problems={rowIssues}
      />
    ) : null
    if (focus?.rowId !== id)
      return rowReview || correction || changed(edit) || edit.reason ? (
        <div className="space-y-2">
          {rowReview}
          {correction}
          <Button
            size="sm"
            variant="ghost"
            className="text-teal-700 dark:text-teal-300"
            onClick={() => openInlineRow(id)}
          >
            {changed(edit)
              ? "View correction"
              : edit.reason
                ? "View recorded check"
                : "Edit this row"}
          </Button>
        </div>
      ) : null
    if (inlineRowId !== id)
      return (
        <div className="space-y-2">
          {rowReview}
          {correction}
          <Button size="sm" variant="outline" onClick={() => openInlineRow(id)}>
            {correction
              ? "View correction"
              : edit.reason
                ? "View recorded check"
                : "Edit this row"}
          </Button>
        </div>
      )
    return (
      <>
        {rowReview}
        {correction}
        {edit.manual_page && (
          <ManualTransactionPosition
            rowId={id}
            page={edit.manual_page}
            value={edit.source_order_anchor}
            rows={data.rows}
            statementPages={
              data.statement_page_numbers.length
                ? data.statement_page_numbers
                : data.page_numbers
            }
            disabled={!canEdit || edit.excluded}
            onChange={(source_order_anchor) =>
              update(id, { source_order_anchor })
            }
          />
        )}
        <StatementRowEditor
          caseId={caseId}
          row={edit}
          statementEnd={periodEnd}
          additionalPrintedDate={original.fields.additional_printed_date}
          kind={original.kind}
          saveProgress={{
            save: () => saveBatchReview.mutate("progress"),
            pending: saveBatchReview.isPending,
            disabled:
              assignmentSaving ||
              saveBatchReview.isPending ||
              confirm.isPending ||
              (savedReadingChanged && !previousReviewChecked),
            error: saveBatchReview.isError
              ? saveBatchReview.error.message
              : undefined,
          }}
          controlContext={
            original.kind === "statement_total"
              ? {
                  label: statementControlLabel(original.kind, original.fields),
                  originalValue: /^-?\d+$/.test(original.fields.balance || "")
                    ? displayAmount(original.fields.balance, digits)
                    : original.fields.balance || "Not read",
                  currency: data.currency,
                  page: original.page_number,
                  row: original.row_index + 1,
                }
              : undefined
          }
          problems={rowProblems(edit)}
          update={(patch) => update(id, patch)}
          close={() => {
            setInlineRowId(null)
            setActiveRows((current) => {
              const next = new Set(current)
              next.delete(id)
              return next
            })
          }}
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
      </>
    )
  }
  const initialBatchRow = useRef(batchReview?.rowId)
  const initialBatchField = useRef(batchReview?.field)
  useEffect(() => {
    if (initialBatchRow.current) {
      openInlineRow(initialBatchRow.current)
      initialBatchRow.current = undefined
    }
    if (initialBatchField.current) {
      const label = {
        holder: "Account holder",
        account_number: "Account number",
        period: "Period start",
      }[initialBatchField.current]
      if (label) focusDetail(label)
      initialBatchField.current = undefined
    }
    // Apply the requested problem once, without reopening it after each edit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const statementDetails = (
    <section aria-label="Statement details" className="space-y-3 my-4">
      <div
        hidden={data.assignment_only || (!!data.current_import && !canEdit)}
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
          <p>
            {data.current_import
              ? "Currency in this reading"
              : "Statement currency"}
          </p>
          <strong>{data.currency}</strong>
          <p className="text-sm">{data.metadata.period}</p>
        </div>
      </div>
      <div
        className={
          data.assignment_only || (!!data.current_import && !canEdit)
            ? "hidden"
            : "flex flex-wrap gap-3"
        }
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
            {replacePrevious
              ? "Reason for replacing the previous import"
              : "Note about detail changes (optional)"}
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
      {!data.assignment_only &&
        canEdit &&
        (!data.current_import || replacePrevious) && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
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
              {saveBatchReview.isPending
                ? "Saving details…"
                : "Save account details"}
            </Button>
            <span className="text-muted-foreground">
              Saves these details and your current corrections to the case.
              Import also saves them.
            </span>
            {saveBatchReview.isSuccess &&
              savedServerSnapshot === currentRequestSnapshot.current && (
                <p role="status">Account details saved to the case.</p>
              )}
          </div>
        )}
    </section>
  )
  return (
    <div ref={statementControls} className="space-y-4 pt-4">
      {!data.current_import &&
        (duplicateDecision || coverage.data?.matching_statement) && (
          <StatementDuplicateDecision
            caseId={caseId}
            fileId={fileId}
            statementId={data.statement_id}
            currency={data.currency}
            readingRevision={data.revision}
            decision={duplicateDecision}
            canEdit={caseCanEdit && !duplicateCheck.isPending}
            canCheck={!duplicateCheckDirty}
            checkDisabledReason="Save your current corrections with Save progress before checking duplicates. Your unfinished edits stay here."
            onBusy={setDuplicateActionBusy}
            onDecision={(decision) => {
              if (renderSnapshot !== currentRequestSnapshot.current) return
              setLocalDuplicate(decision)
              confirm.reset()
              void client.invalidateQueries({
                queryKey: ["financial-batch", caseId],
              })
              void client.invalidateQueries({
                queryKey: ["statement-import-status", caseId],
              })
            }}
          />
        )}
      {duplicateCheck.isPending && (
        <p role="status">
          Checking whether this statement is already represented. No
          transactions are being imported.
        </p>
      )}
      {duplicateCheck.isError && (
        <p role="alert">
          {duplicateCheck.error.message} Use Check duplicate status above to try
          again.
        </p>
      )}
      <header>
        <h3 className="text-lg font-semibold">Review {data.filename}</h3>

        {draftSaved && canEdit && !saveBatchReview.isSuccess && (
          <p className="text-xs text-muted-foreground" role="status">
            Recent edits are saved in this browser tab. Use Save progress to
            keep unfinished work in the case before leaving.
          </p>
        )}
        {savedReadingChanged &&
          !data.current_import?.refresh_review_required && (
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
            : importedHere
              ? "The account details below are the saved values. Use Edit account and balances above to change them. The original extracted rows remain below for comparison."
              : "Review values beside the original and save your progress. Import becomes available when the statement is reconciled."}
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
                        : !serverChecks.admission?.can_import
                          ? "Reconciliation needed before import"
                          : "Ready to confirm"}
              </h4>
              <p>
                {included.length
                  ? `${included.length} records selected`
                  : hasStatementBalance
                    ? "Statement balances only"
                    : "No transactions identified"}
                {incompleteCount
                  ? ` · ${incompleteCount} with missing or invalid fields`
                  : ""}
                .
              </p>
              <p>
                {!included.length &&
                !hasStatementBalance &&
                !data.can_record_account_closure
                  ? "Add a printed opening or closing balance below to save this statement."
                  : serverChecks.pending
                    ? "Checking these values. You can keep reviewing the PDF while this runs."
                    : attentionCount || unresolvedDifference
                      ? "Save your progress while you correct the statement. Payments stay in review until reconciliation is complete."
                      : "Confirm once to import this statement. You do not need to accept each line separately."}
              </p>
            </div>
            <Button
              disabled={!!importDisabled}
              onClick={() => {
                if (batchReview && !batchReview.confirm) submitImport()
                else if (!importDisabled) confirm.mutate()
              }}
            >
              {confirm.isPending || saveBatchReview.isPending
                ? "Saving statement…"
                : batchReview && !batchReview.confirm
                  ? "Save and return to batch"
                  : included.length
                    ? `Import ${included.length - incompleteCount} payments and view Transactions`
                    : data.can_record_account_closure
                      ? "Save closure now"
                      : "Save balances now"}
            </Button>
            {batchReview?.confirm && (
              <Button
                variant="outline"
                disabled={!canEdit || saveBatchReview.isPending}
                onClick={() => saveBatchReview.mutate("done")}
              >
                Save draft and return to batch
              </Button>
            )}
            {!included.length &&
              hasStatementBalance &&
              !data.current_import &&
              !serverChecks.admission?.can_import &&
              canEdit && (
                <Button
                  variant="outline"
                  disabled={
                    confirm.isPending ||
                    saveBatchReview.isPending ||
                    serverChecks.pending ||
                    !!data.reading_failure
                  }
                  onClick={() => confirm.mutate()}
                >
                  Save balances for review
                </Button>
              )}
            {!included.length &&
              hasStatementBalance &&
              !serverChecks.admission?.can_import && (
                <p className="w-full text-sm">
                  You can retain the printed dates and balances in Financial
                  while reviewing this period. This creates no transactions and
                  does not mark it as having no activity.
                </p>
              )}
            {confirm.isError && (
              <p className="w-full" role="alert">
                {confirm.error.message}
              </p>
            )}
            {serverChecks.error && (
              <div role="alert" className="w-full">
                <p>{serverChecks.error}</p>
                <Button variant="outline" onClick={serverChecks.retry}>
                  Retry statement checks
                </Button>
              </div>
            )}
            <div className="w-full">
              <StatementReconciliationSummary
                calculation={serverChecks.admission?.calculation}
                pending={serverChecks.pending}
                format={(value) =>
                  `${displayAmount(value, digits)} ${data.currency}`
                }
              />
              {serverChecks.admission && !serverChecks.admission.can_import && (
                <div className="rounded border p-3 space-y-2" role="status">
                  <p className="font-semibold">
                    Reconciliation needed before import
                  </p>
                  {serverChecks.admission.blockers.map((problem, index) => (
                    <div key={index} className="flex items-center gap-2">
                      <span>
                        {problem.message}
                        {problem.expected_format && (
                          <span className="block text-xs text-muted-foreground">
                            Expected: {problem.expected_format}
                          </span>
                        )}
                      </span>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => inspectBlocker(problem)}
                      >
                        {originals.get(
                          problem.target?.row_id || problem.row_id || ""
                        )?.kind === "statement_total"
                          ? `Review ${statementControlLabel("statement_total", originals.get(problem.target?.row_id || problem.row_id || "")?.fields).toLowerCase()}`
                          : `Review ${problem.row_id ? "row" : "statement details"}`}
                      </Button>
                    </div>
                  ))}
                </div>
              )}
              {!included.length && !importedHere && (
                <label className="block p-3 border rounded mt-2">
                  <input
                    type="checkbox"
                    aria-label="Confirm no activity for this statement"
                    checked={
                      !!noActivityRevision &&
                      noActivityRevision === serverChecks.admission?.revision
                    }
                    disabled={
                      !canEdit ||
                      serverChecks.pending ||
                      !serverChecks.admission?.revision
                    }
                    onChange={(e) =>
                      setNoActivityRevision(
                        e.target.checked ? serverChecks.admission!.revision : ""
                      )
                    }
                  />{" "}
                  I checked every page of this period: there are no
                  transactions. Save its dates and balances in Financial.
                </label>
              )}
              <StatementArithmeticChecks
                checks={serverChecks.checks}
                format={(value) =>
                  `${displayAmount(value, digits)} ${data.currency}`
                }
                onInspect={openInlineRow}
                editable={canEdit && (!data.current_import || replacePrevious)}
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
                      Your explanation is saved with your review. The difference
                      must still be resolved before payments can be imported.
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
              onClick={() => {
                const balanceProblem = detailProblems.find(
                  (problem) => problem.field === "Statement balances"
                )
                const field =
                  balanceProblem?.field ??
                  detailProblems.find((problem) => problem.field)?.field
                if (field && canEdit) focusDetail(field)
                else if (blockedRows.length && canEdit)
                  reviewRow(blockedRows[0].row.id)
                else
                  confirmationControls.current?.scrollIntoView({
                    block: "start",
                    behavior: "smooth",
                  })
              }}
            >
              {attentionCount ? "Show items to check" : "Go to confirmation"}
            </Button>
          </div>
        </section>
      )}
      {canEdit &&
        (!data.current_import || replacePrevious) &&
        (emptyEntries.length > 0 || setAsideIds.length > 0) && (
          <section
            aria-label="Blank transaction rows"
            className="rounded border bg-card p-3 space-y-2 text-sm"
          >
            {emptyEntries.length > 0 && (
              <>
                <p>
                  {emptyEntries.length} rows have no transaction values entered.
                  Exclude them together if their original text is not a payment.
                  Partly filled rows stay selected.
                </p>
                <Button
                  variant="outline"
                  onClick={setAsideEmptyEntries}
                  disabled={
                    confirm.isPending ||
                    saveBatchReview.isPending ||
                    assignmentSaving
                  }
                >
                  Exclude {emptyEntries.length} blank rows from import
                </Button>
              </>
            )}
            {setAsideIds.length > 0 && (
              <div className="flex flex-wrap items-center gap-2" role="status">
                <span>
                  {setAsideIds.length} blank rows excluded. Their original text
                  is kept under Show excluded rows.
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={
                    confirm.isPending ||
                    saveBatchReview.isPending ||
                    assignmentSaving
                  }
                  onClick={() => {
                    const ids = new Set(setAsideIds)
                    setRows((current) =>
                      current.map((r) =>
                        ids.has(r.id) ? { ...r, excluded: false } : r
                      )
                    )
                    setSetAsideIds([])
                  }}
                >
                  Undo excluding blank rows
                </Button>
              </div>
            )}
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
                  : data.current_import.transaction_count
                    ? "Open imported transactions"
                    : data.current_import.incomplete_count
                      ? "Review saved incomplete records"
                      : "View saved account and balances"
                : "Edit import values"}
            </Button>
          )}
      </div>
      <fieldset
        disabled={
          assignmentSaving ||
          duplicateActionBusy ||
          duplicateIgnored ||
          confirm.isPending ||
          confirm.isSuccess ||
          saveBatchReview.isPending
        }
        className="space-y-4"
      >
        <div
          className={`grid gap-4 ${focus ? "lg:grid-cols-[minmax(300px,0.8fr)_minmax(0,1.2fr)]" : ""}`}
        >
          {focus && (
            <aside className="min-w-0 lg:sticky lg:top-0 self-start rounded border p-3">
              <div className="flex justify-between items-center mb-2">
                <h4 className="font-semibold">Original statement</h4>
                <Button variant="ghost" onClick={() => setFocus(null)}>
                  Close source
                </Button>
              </div>
              <StatementSourceTools
                fileId={fileId}
                page={currentPage}
                text={data.rows
                  .filter((r) => r.page_number === currentPage)
                  .map((r) =>
                    r.source_cells.map((c) => c.expected_text).join("\t")
                  )
                  .join("\n")}
              />
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
            {!importedHere && (
              <div className="sticky top-0 z-10 bg-background pb-2">
                {data.current_import && (
                  <div className="mb-2 text-sm">
                    <h4 className="font-semibold">
                      Current PDF reading · {data.currency}
                    </h4>
                    <p>
                      This reading has not replaced the saved statement. Its
                      values and currency may differ from your saved
                      corrections.
                    </p>
                  </div>
                )}
                <StatementReconciliationSummary
                  calculation={serverChecks.admission?.calculation}
                  pending={serverChecks.pending}
                  compact
                  format={(value) =>
                    `${displayAmount(value, digits)} ${data.currency}`
                  }
                />
              </div>
            )}
            {!importedHere && statementDetails}
            {!excludedCopy && !importedHere && !data.assignment_only && (
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  const page =
                    (focus
                      ? originals.get(focus.rowId)?.page_number
                      : undefined) ?? sourcePage
                  if (!page) return
                  const id = `manual:${newReviewId()}`
                  setInlineRowId(id)
                  setCorrectionsOpen(true)
                  keepRowVisible(id)
                  setCorrectionPage(Math.floor(visible.length / 50))
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
                  requestAnimationFrame(() => {
                    printedControls.current?.scrollIntoView({
                      block: "nearest",
                      behavior: "smooth",
                    })
                    printedControls.current
                      ?.querySelector<HTMLInputElement>(
                        '[aria-label="Corrected transaction date"]'
                      )
                      ?.focus({ preventScroll: true })
                  })
                }}
                disabled={!canEdit || !data.page_numbers.length}
              >
                Add a missed transaction
              </Button>
            )}
            {inlineRowId?.startsWith("manual:") && (
              <div className="mt-3">
                <p className="text-sm">
                  Adding a payment for {holder || "this holder"} ·{" "}
                  {account || "this account"} · {data.currency}. It stays in
                  your draft until you save or import.
                </p>
                <label className="text-sm">
                  Payment source page{" "}
                  <select
                    aria-label="Manual payment source page"
                    value={
                      editsById.get(inlineRowId)?.manual_page || currentPage
                    }
                    onChange={(event) => {
                      const page = Number(event.target.value)
                      update(inlineRowId, {
                        manual_page: page,
                        source_order_anchor: null,
                      })
                      setFocus({
                        rowId: inlineRowId,
                        locator: { kind: "page_only", page },
                      })
                    }}
                  >
                    {data.page_numbers.map((page) => (
                      <option key={page}>{page}</option>
                    ))}
                  </select>
                </label>
                {rowTools(inlineRowId)}
              </div>
            )}
            <h4 className="font-semibold">Extracted statement</h4>
            <p className="text-sm text-muted-foreground mb-3">
              Select a printed value to locate it in the PDF, or use Previous
              and Next transaction to move through the payments.
              {canEdit &&
                " Select Edit this row to correct a value beside its original."}
            </p>
            <PrintedStatementTable
              balanceOnly={
                data.can_import_balances &&
                data.transaction_count === 0 &&
                data.needs_attention === 0
              }
              selectedRowId={focus?.rowId}
              rows={data.rows.filter((row) => row.page_number === currentPage)}
              onCell={(rowId, locator) =>
                setFocus({
                  rowId:
                    originals.get(rowId)?.fields.parent_transaction_id || rowId,
                  locator,
                })
              }
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
                        "Printed balance / total",
                        "Actions",
                      ].map((s) => (
                        <th
                          key={s}
                          scope="col"
                          className="text-left p-2 border-b"
                        >
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
                          onFocusCapture={() => keepRowVisible(r.id)}
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
                            {activeRows.has(r.id) && (
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() =>
                                  setActiveRows((previous) => {
                                    const next = new Set(previous)
                                    next.delete(r.id)
                                    return next
                                  })
                                }
                              >
                                Done editing row
                              </Button>
                            )}
                            {original.kind === "manual_entry" &&
                              !data.rows.some(
                                (source) => source.id === r.id
                              ) && (
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => {
                                    setRows((current) =>
                                      current.filter((row) => row.id !== r.id)
                                    )
                                    setInlineRowId((current) =>
                                      current === r.id ? null : current
                                    )
                                    setActiveRows((current) => {
                                      const next = new Set(current)
                                      next.delete(r.id)
                                      return next
                                    })
                                    setAmountText((current) => {
                                      const next = { ...current }
                                      delete next[r.id]
                                      delete next[`balance:${r.id}`]
                                      return next
                                    })
                                  }}
                                >
                                  Discard added row
                                </Button>
                              )}
                          </td>
                          <td className="p-2 border-b align-top">
                            <label
                              htmlFor={`review-date-${r.id}`}
                              className="block text-xs mb-1"
                            >
                              {dateLabels[primaryDateRole(original.fields)]}
                            </label>
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
                              id={`review-date-${r.id}`}
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
                            <label
                              htmlFor={`review-description-${r.id}`}
                              className="block text-xs mb-1"
                            >
                              Description
                            </label>
                            <input
                              id={`review-description-${r.id}`}
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
                            <PaymentCounterpartyPicker
                              caseId={caseId}
                              value={r.counterparty_link}
                              direction={r.direction}
                              disabled={r.excluded}
                              onChange={(link) =>
                                update(r.id, { counterparty_link: link })
                              }
                            />
                            {(!r.reason && !changed(r)
                              ? original.issues
                              : []
                            ).map((s, i) => (
                              <p
                                key={i}
                                className="text-amber-700 dark:text-amber-300 mt-1"
                              >
                                {s}
                              </p>
                            ))}
                            {!r.excluded &&
                              original.issues.length > 0 &&
                              !r.reason &&
                              !changed(r) &&
                              rowProblems(r).length === 0 && (
                                <Button
                                  variant="outline"
                                  size="sm"
                                  className="mt-2"
                                  onClick={() =>
                                    update(r.id, {
                                      reason:
                                        "Checked against the original statement.",
                                    })
                                  }
                                >
                                  Mark checked
                                </Button>
                              )}
                            {r.manual_page && (
                              <ManualTransactionPosition
                                rowId={r.id}
                                page={r.manual_page}
                                value={r.source_order_anchor}
                                rows={data.rows}
                                statementPages={
                                  data.statement_page_numbers.length
                                    ? data.statement_page_numbers
                                    : data.page_numbers
                                }
                                disabled={!canEdit || r.excluded}
                                onChange={(source_order_anchor) =>
                                  update(r.id, { source_order_anchor })
                                }
                              />
                            )}
                            {r.manual_page && (
                              <label className="block mt-2">
                                Source page
                                <select
                                  aria-label={`Source page ${r.id}`}
                                  value={r.manual_page}
                                  onChange={(e) => {
                                    update(r.id, {
                                      manual_page: Number(e.target.value),
                                      source_order_anchor: null,
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
                            {(changed(r) || !!r.reason) && (
                              <label className="block mt-2">
                                Note about this change (optional)
                                <input
                                  aria-label={`Reason ${r.id}`}
                                  value={r.reason}
                                  onChange={(e) =>
                                    update(r.id, { reason: e.target.value })
                                  }
                                  className="border rounded p-1 w-full bg-background"
                                />
                              </label>
                            )}
                            {(focus?.rowId === r.id ||
                              original.kind === "unresolved") && (
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
                              <label
                                htmlFor={`review-${direction}-${r.id}`}
                                className="block text-xs mb-1"
                              >
                                {direction === "credit" ? "Credit" : "Debit"}{" "}
                                {data.currency}
                              </label>
                              <input
                                id={`review-${direction}-${r.id}`}
                                aria-label={`${direction === "credit" ? "Credit" : "Debit"} ${r.id}`}
                                disabled={
                                  r.excluded ||
                                  (!!r.amount_minor &&
                                    r.amount_minor !== "0" &&
                                    !!r.direction &&
                                    r.direction !== direction)
                                }
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
                              {!r.excluded &&
                                r.direction &&
                                r.direction !== direction &&
                                r.amount_minor &&
                                r.amount_minor !== "0" && (
                                  <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    className="block mt-2 whitespace-normal"
                                    onClick={() => update(r.id, { direction })}
                                  >
                                    Move amount to{" "}
                                    {direction === "credit"
                                      ? "Credit / money in"
                                      : "Debit / money out"}
                                  </Button>
                                )}
                            </td>
                          ))}
                          <td className="p-2 border-b align-top whitespace-nowrap">
                            <label
                              htmlFor={`review-balance-${r.id}`}
                              className="block text-xs mb-1"
                            >
                              {statementControlLabel(
                                original.kind,
                                original.fields
                              )}{" "}
                              {data.currency}
                            </label>
                            <input
                              id={`review-balance-${r.id}`}
                              aria-label={
                                original.kind === "statement_total"
                                  ? `${statementControlLabel(original.kind, original.fields)} ${r.id}`
                                  : `Balance ${r.id}`
                              }
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
                                    original.fields.balance_column !==
                                      undefined ||
                                    original.value_sources?.balance
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
                {data.current_import.refresh_currency_conflict
                  ? "Check the replacement currency above before saving this reading. Your saved statement has not changed."
                  : data.current_import.refresh_available ||
                      data.current_import.refresh_review_required
                    ? data.current_import.refresh_requires_reconciliation !==
                        false &&
                      !data.current_import.refresh_admission?.can_import
                      ? "The replacement reading still needs review. Resolve the replacement checks above before saving payments to Transactions."
                      : (data.current_import.refresh_transaction_count ??
                          data.transaction_count)
                        ? "Use Save payments above to add the current reading to Transactions."
                        : "Use Save statement balances above to update this account. No payments will be added."
                    : data.current_import.transaction_count
                      ? "Open Transactions to work with the saved payments."
                      : "The saved account, balances and original PDF remain available in this statement."}
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
                  : data.current_import?.evidence_file_id === fileId
                    ? "payment readings in the current PDF"
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
        {data.balance_basis && (
          <div
            className="rounded border bg-muted/20 p-3 text-sm space-y-1"
            role="note"
            aria-label="Balance basis"
          >
            <p className="font-medium">
              Balance check:{" "}
              {data.balance_basis === "operation"
                ? "operation balances"
                : "liquidation balances"}
            </p>
            <p>
              {data.balance_basis === "operation"
                ? "The opening and closing values below use Saldo de Operación Inicial and Saldo de Operación Final, matching the Operación balance column. The separately printed liquidation balances are retained in the PDF and are not mixed into this check."
                : "The opening and closing values below use Saldo de Liquidación Inicial and Saldo Final (+), matching the Liquidación balance column. Operation and liquidation dates remain separate on each payment."}
            </p>
            {data.prior_period_settlement_pages.length > 0 && (
              <p>
                The statement also lists transactions from earlier periods that
                settled in this period (PDF pages{" "}
                {data.prior_period_settlement_pages.join(", ")}). These are
                retained with the original statement and are excluded from this
                period’s imported payments and totals.
              </p>
            )}
          </div>
        )}
        {importedHere && (
          <p className="text-sm font-medium">
            Original extracted balances for comparison. The current saved
            balances and their correction controls are above.
          </p>
        )}
        <div
          ref={balanceControls}
          role="group"
          aria-label="Statement balances"
          className="flex flex-wrap gap-5 text-sm"
        >
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
                ) : canEdit ? (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      const id = `manual:${role}-balance`
                      const pages = balancePages
                      setRows((current) => [
                        ...current,
                        {
                          id,
                          excluded: true,
                          manual_page: pages.includes(currentPage)
                            ? currentPage
                            : pages[0],
                          date: "",
                          description: `${role} balance`,
                          counterparty: "",
                          amount_minor: "0",
                          direction: "",
                          balance_minor: null,
                          reason: "",
                        },
                      ])
                      requestAnimationFrame(() =>
                        focusDetail(`Statement ${role} balance`)
                      )
                    }}
                  >
                    Add {role} balance
                  </Button>
                ) : (
                  <span className="text-muted-foreground">Not identified</span>
                )}
                {canEdit &&
                  controls.map((control) => (
                    <div key={`input-${control.id}`} className="space-y-1">
                      <label className="block text-sm capitalize">
                        {role} balance {data.currency}
                        <input
                          aria-label={`Statement ${role} balance${controls.length > 1 ? ` ${control.id}` : ""}`}
                          className="block border rounded bg-background p-2"
                          inputMode="decimal"
                          value={
                            amountText[`balance:${control.id}`] ??
                            (control.balance_minor === null
                              ? ""
                              : displayAmount(control.balance_minor, digits))
                          }
                          onChange={(event) => {
                            const value = event.target.value
                            setAmountText((previous) => ({
                              ...previous,
                              [`balance:${control.id}`]: value,
                            }))
                            const parsed = minorAmount(
                              value.replace(/^-/, ""),
                              digits
                            )
                            update(control.id, {
                              balance_minor:
                                value === ""
                                  ? null
                                  : parsed
                                    ? `${value.startsWith("-") && parsed !== "0" ? "-" : ""}${parsed}`
                                    : "invalid",
                            })
                          }}
                        />
                      </label>
                      {control.manual_page && (
                        <label className="block text-sm">
                          Printed on page{" "}
                          <select
                            aria-label={`${role} balance source page`}
                            className="border rounded bg-background p-2"
                            value={control.manual_page}
                            onChange={(event) => {
                              const page = Number(event.target.value)
                              update(control.id, { manual_page: page })
                              showPage(page)
                            }}
                          >
                            {balancePages.map((page) => (
                              <option key={page}>{page}</option>
                            ))}
                          </select>
                        </label>
                      )}
                    </div>
                  ))}
              </div>
            )
          })}
        </div>
        <p className="text-sm text-muted-foreground">
          {canEdit
            ? "Enter balances here, then save the review or import. Leave an unknown balance blank; a printed zero is 0.00."
            : "Select an opening or closing amount to check its source."}
        </p>

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
          !importedHere &&
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
                  : included.length === 0
                    ? "Save the account, statement period and printed balances without adding transactions. Enter any missing printed balance in Statement balances above."
                    : batchReview
                      ? `Save these ${included.length} records to the batch for import together. Issues can be checked later.`
                      : `Import ${included.length} records with their originals. You can correct values later. Incomplete records stay visible outside calculated totals.`}
              </p>
              <Button
                disabled={!!importDisabled}
                aria-describedby={
                  blockedRows.length || detailProblems.length
                    ? "statement-import-blockers"
                    : undefined
                }
                onClick={submitImport}
              >
                {batchReview
                  ? saveBatchReview.isPending
                    ? "Saving checked statement…"
                    : included.length === 0
                      ? data.can_record_account_closure
                        ? "Save account closure"
                        : "Save statement balances"
                      : "Save for bulk import"
                  : confirm.isPending
                    ? "Importing statement…"
                    : data.can_record_account_closure && included.length === 0
                      ? "Save account closure"
                      : included.length === 0
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
                  These values leave a balance difference. Save your progress
                  and resolve the difference before importing.
                </p>
              )}
              {(blockedRows.length > 0 || detailProblems.length > 0) && (
                <section
                  id="statement-import-blockers"
                  aria-label="Statement issues and edits"
                  className="rounded border border-amber-500/50 bg-amber-50/60 dark:bg-amber-950/20 p-3 space-y-3"
                >
                  <h4 className="font-semibold">Issues and edits</h4>
                  <p className="text-sm">
                    {duplicateBlocked
                      ? "This possible duplicate is held from import. Compare the existing statement and record why both are needed, or leave this copy unimported. Your corrections remain available."
                      : "New payments can be imported only after the statement reconciles. Follow the checks below to resolve missing or conflicting values. Original readings and saved corrections remain available."}
                  </p>
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
      {confirm.isSuccess && (
        <p role="status">
          {confirm.data.ignored
            ? "Duplicate - Ignored by system. No transactions were added; the original and your review are retained."
            : confirm.data.account_closed_on
              ? "Account closure recorded. Open Review accounts in Statements to inspect its source."
              : confirm.data.transaction_count === 0
                ? "Statement balances saved. Use Review accounts in Statements to see its coverage."
                : `Imported ${confirm.data.transaction_count} transactions. Open Transactions to investigate them.`}
        </p>
      )}
    </div>
  )
}
