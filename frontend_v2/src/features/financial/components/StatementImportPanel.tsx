import { StatementSectionPicker } from "./StatementSectionPicker"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { reviewSelectionBalance } from "../lib/statement-review-balance"
import { ReprocessStatement } from "./ReprocessStatement"
import { newReviewId } from "../lib/statement-review-id"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import {
  readStatementDraft,
  saveStatementDraft,
} from "../lib/statement-review-draft"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { PdfReviewIntake } from "./PdfReviewIntake"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"
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
  case_id: z.string(),
  evidence_file_id: z.string(),
  filename: z.string(),
  currency: z.string(),
  revision: z.string(),
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
  needs_attention: z.number(),
  page_numbers: z.array(z.number()).default([]),
  unassigned_page_numbers: z.array(z.number()).default([]),
  statement_id: z.string().nullable().optional(),
  statement_choices: z
    .array(
      z.object({
        id: z.string(),
        institution: z.string(),
        account_reference: z.string(),
        account_label: z.string().optional(),
        document_kind: z.literal("deposit_receipt").optional(),
        statement_date: z.string().optional(),
        printed_statement_date: z.string().optional(),
        period_start: z.string(),
        period_end: z.string(),
        page_numbers: z.array(z.number()),
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
  const files = useQuery({
    queryKey: ["statement-import-files", caseId],
    enabled: open && !!caseId,
    queryFn: async () =>
      z
        .object({
          files: z.array(
            z.object({
              id: z.string(),
              case_id: z.string(),
              original_filename: z.string(),
              created_at: z.string().optional(),
              status: z.string(),
            })
          ),
        })
        .parse(
          await fetchAPI(
            `/api/evidence?${new URLSearchParams({ case_id: caseId! })}`
          )
        )
        .files.filter(
          (f) =>
            f.case_id === caseId &&
            f.original_filename.toLowerCase().endsWith(".pdf")
        ),
  })
  if (!caseId) return null
  return (
    <section
      aria-label="Statement import"
      className="rounded-lg border bg-card p-4 space-y-3"
    >
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
      <div hidden={!open}>
        {open && (
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
                {files.data?.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.original_filename}
                    {(files.data?.filter(
                      (other) => other.original_filename === f.original_filename
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
        {query.data.statement_choices.length > 1 && (
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
        {query.data.statement_choices.length > 1 && (
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
      {query.data.statement_choices.length > 1 && (
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
        <ReprocessStatement
          key={fileId}
          caseId={caseId}
          fileId={fileId}
          onReady={onReprocessed}
        />
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
          key={query.data.revision}
          data={query.data}
          caseId={caseId}
          fileId={fileId}
          onImported={onImported}
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
  const { canEdit: caseCanEdit } = useFinancialAccess()
  const excludedCopy = !!data.current_import?.excluded_as_duplicate
  const canEdit = caseCanEdit && !excludedCopy
  const owner = useAuthStore((state) => state.user?.id || state.user?.username)
  const draftKey = owner
    ? `loupe-statement-review:${owner}:${caseId}:${fileId}:${data.revision}`
    : null
  const [saved] = useState(() => readStatementDraft(draftKey, data.revision))
  const [draftSaved, setDraftSaved] = useState(!!saved)
  const [correctionsOpen, setCorrectionsOpen] = useState(false)
  const [correctionPage, setCorrectionPage] = useState(0)
  const correctionControls = useRef<HTMLDivElement>(null)
  const pageKey = `${owner}:${caseId}:${fileId}:${data.revision}`
  const rememberedPage = useStatementWorkspace.getState().pages[pageKey]
  const initialPage = data.page_numbers.includes(rememberedPage)
    ? rememberedPage
    : data.rows[0]?.page_number || data.page_numbers[0] || 1
  const [sourcePage, setSourcePage] = useState(initialPage)
  const client = useQueryClient()
  const baseline = useMemo(() => initialRows(data), [data])
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
      rowId: "",
      locator: { kind: "page_only", page: initialPage },
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
  const [replacePrevious, setReplacePrevious] = useState(false)
  const detailsChanged =
    institution !== data.metadata.institution ||
    holder !== data.metadata.holder ||
    account !== data.metadata.account_number ||
    periodStart !== data.metadata.period_start ||
    periodEnd !== data.metadata.period_end
  const digits = exponent(data.currency),
    originals = new Map(data.rows.map((r) => [r.id, r]))
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
      current.map((r) => (r.id === id ? { ...r, ...patch } : r))
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
  const incomplete = rows.some(
    (r) =>
      (r.balance_minor !== null && !/^-?\d+$/.test(r.balance_minor)) ||
      (requiresReason(r) && !r.reason.trim()) ||
      (!r.excluded &&
        (!/^\d{4}-\d{2}-\d{2}$/.test(r.date) ||
          Object.values(r.date_values ?? {}).some(
            (value) => value && !/^\d{4}-\d{2}-\d{2}$/.test(value)
          ) ||
          !r.description.trim() ||
          !r.direction ||
          !/^\d+$/.test(r.amount_minor) ||
          BigInt(r.amount_minor || "0") <= 0n))
  )
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
  const total = (direction: Edit["direction"]) =>
    included
      .filter((r) => r.direction === direction && /^\d+$/.test(r.amount_minor))
      .reduce((n, r) => n + BigInt(r.amount_minor), 0n)
      .toString()
  const confirm = useMutation({
    retry: false,
    mutationFn: async () => {
      const result = receipt.parse(
        await fetchAPI(
          `/api/financial/statement-import/${fileId}/confirm?${new URLSearchParams({ case_id: caseId })}`,
          {
            method: "POST",
            body: {
              expected_revision: data.revision,
              statement_id: data.statement_id ?? null,
              ...(replacePrevious && data.current_import
                ? {
                    replaces_source_document_id:
                      data.current_import.source_document_id,
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
              rows: rows.map((r) => ({
                ...r,
                direction: r.direction || null,
                amount_minor:
                  r.excluded && !r.amount_minor ? "0" : r.amount_minor,
              })),
            },
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
    amountText,
    confirm.isSuccess,
  ])
  const selectionBalance = reviewSelectionBalance(
    rows,
    data.rows,
    data.metadata.account_type === "credit_card"
  )
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
  return (
    <div className="space-y-4 pt-4">
      <header>
        <h3 className="text-lg font-semibold">Review {data.filename}</h3>
        {draftSaved && !excludedCopy && (
          <p className="text-xs text-muted-foreground" role="status">
            Review saved in this browser tab. Reopening this statement after a
            refresh restores it. Closing the tab may discard it.
          </p>
        )}
        <p className="text-sm">
          Compare the extracted statement with the original PDF. Select printed
          text to locate it on the page.
          {canEdit &&
            " Corrections and import choices are separate below the table."}
        </p>
      </header>
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
        disabled={confirm.isPending || confirm.isSuccess}
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
          <div className="min-w-0 overflow-y-auto overflow-x-hidden max-h-[65vh]">
            <h4 className="font-semibold">Extracted statement</h4>
            <p className="text-sm text-muted-foreground mb-3">
              Compare each table with the PDF. Select any printed value to
              locate it on the page.
              {canEdit &&
                " Use Show corrections and import choices below to change what will be imported."}
            </p>
            <PrintedStatementTable
              rows={data.rows.filter((row) => row.page_number === currentPage)}
              onCell={(rowId, locator) => setFocus({ rowId, locator })}
              onReviewRow={
                canEdit && !data.current_import ? reviewRow : undefined
              }
            />
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
                                original.fields.balance_convention ===
                                "liability_owed"
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
                            {requiresReason(r) && (
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
                  checked={replacePrevious}
                  onChange={(e) => setReplacePrevious(e.target.checked)}
                />
                Replace the previous import when I confirm. Its original records
                and source remain in the history.
              </label>
            )}
          </div>
        )}
        <div className="grid sm:grid-cols-3 gap-3">
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
        <div className="flex flex-wrap gap-3">
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
        {data.issues.length > 0 && (
          <div className="rounded border border-amber-500 p-3">
            <h4 className="font-semibold">Check statement details</h4>
            {data.issues.map((s, i) => (
              <p key={i}>{s}</p>
            ))}
          </div>
        )}
        <div className="flex flex-wrap gap-5 text-sm">
          <span>
            {excludedCopy ? (
              "This copy contributes no transactions to the case totals."
            ) : (
              <>
                <strong>{included.length}</strong> transactions to import
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
        {!excludedCopy && (
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
              standard card terms. Check them for missed transactions before
              relying on complete coverage.
              {!excludedCopy &&
                " Use Add a missed transaction if you find one for this account and period."}
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
        {selectionBalance && (
          <div
            className={`rounded border p-3 text-sm ${selectionBalance.difference !== "0" ? "border-amber-500" : "border-border"}`}
            role="status"
          >
            <p className="font-medium">
              {selectionBalance.difference === "0"
                ? "Selected movements agree with the printed balance"
                : "Selected movements leave a balance difference"}
            </p>
            <p>
              {data.metadata.balance_convention === "liability_owed"
                ? "Opening amount owed plus charges minus payments gives "
                : "Opening balance plus the selected movements gives "}
              {displayAmount(selectionBalance.expected, digits)} {data.currency}
              . The{" "}
              {selectionBalance.independent
                ? data.metadata.balance_convention === "liability_owed"
                  ? "printed closing amount owed"
                  : "printed closing balance"
                : "last printed transaction balance"}{" "}
              is {displayAmount(selectionBalance.printed, digits)}. Difference:{" "}
              {displayAmount(selectionBalance.difference, digits)}.
            </p>
            <p>
              {selectionBalance.difference !== "0"
                ? "Check excluded payments, corrections and missing rows before confirming. "
                : ""}
              A matching balance cannot tell you whether any transactions were
              missed. Check any flagged rows against the PDF.
            </p>
            <Button
              variant="outline"
              onClick={() => {
                const original = originals.get(selectionBalance.sourceId)
                if (original) {
                  setFocus({
                    rowId: original.id,
                    locator: balanceLocator(original),
                  })
                }
              }}
            >
              Inspect compared balance
            </Button>
          </div>
        )}
        {!excludedCopy && (
          <div className="rounded border bg-muted/30 p-3 space-y-2">
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
                  : `Import adds ${included.length} transactions to the case. Original readings and your corrections are retained. Check the PDF for any missed transactions before confirming.`}
            </p>
            <Button
              disabled={
                !canEdit ||
                incomplete ||
                (!!data.current_import &&
                  (!replacePrevious || !detailsReason.trim())) ||
                (detailsChanged && !detailsReason.trim()) ||
                Boolean(periodStart) !== Boolean(periodEnd) ||
                periodStart > periodEnd ||
                !holder.trim() ||
                !account.trim() ||
                (included.length === 0 &&
                  !data.can_record_account_closure &&
                  (!data.can_import_balances || !matchingEmptyBalances))
              }
              onClick={() => {
                if (canEdit) confirm.mutate()
              }}
            >
              {confirm.isPending
                ? "Importing statement…"
                : data.can_record_account_closure && included.length === 0
                  ? "Save account closure"
                  : data.can_import_balances && included.length === 0
                    ? "Save statement balances"
                    : `Confirm import of ${included.length} transactions`}
            </Button>
            {data.can_import_balances &&
              included.length === 0 &&
              !matchingEmptyBalances && (
                <p className="text-sm">
                  Check the opening and closing balances. They must match when
                  there are no transactions.
                </p>
              )}
            {incomplete && (
              <p className="text-sm">
                Complete the flagged fields and record a reason for each
                correction or exception before importing.
              </p>
            )}
          </div>
        )}
      </fieldset>
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
