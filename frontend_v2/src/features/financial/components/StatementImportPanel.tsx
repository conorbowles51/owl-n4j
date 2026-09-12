import { reviewSelectionBalance } from "../lib/statement-review-balance"
import { ReprocessStatement } from "./ReprocessStatement"
import { newReviewId } from "../lib/statement-review-id"
import { useEffect, useRef, useState } from "react"
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
  case_id: z.string(),
  evidence_file_id: z.string(),
  filename: z.string(),
  currency: z.string(),
  revision: z.string(),
  metadata: z.object({
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
      revision: z.string(),
      transaction_count: z.number(),
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
}
type Proposal = z.infer<typeof proposalSchema>
type Edit = {
  id: string
  excluded: boolean
  manual_page?: number | null
  date: string
  description: string
  counterparty: string
  amount_minor: string
  direction: "credit" | "debit"
  balance_minor: string | null
  reason: string
}
const receipt = z.object({
  case_id: z.string(),
  evidence_file_id: z.string(),
  transaction_count: z.number(),
  source_document_id: z.string().optional(),
  account_id: z.string().optional(),
  applied: z.literal(true),
})

function initialRows(data: Proposal): Edit[] {
  return data.rows.map((r) => ({
    id: r.id,
    excluded: r.excluded,
    date: r.fields.date || r.fields.booking_date || r.fields.value_date || "",
    description: r.fields.description || "",
    counterparty: r.fields.counterparty || "",
    amount_minor: r.fields.amount_minor || "0",
    direction: r.fields.direction === "debit" ? "debit" : "credit",
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
            Add a statement, check any problems, then import its transactions.
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
            {open ? "Close statement review" : "Import a statement"}
          </Button>
        </div>
      </div>
      <div hidden={!open}>
        {open && (
          <div className="space-y-3">
            <Button variant="outline" onClick={() => setUpload((v) => !v)}>
              Upload a statement
            </Button>
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
            onReprocessed={setFileId}
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
  if (query.data.statement_choices.length > 1 && !query.data.statement_id)
    return (
      <section className="space-y-3 py-4" aria-label="Statements in this PDF">
        <h3 className="font-semibold">
          This PDF contains {query.data.statement_choices.length} statements
        </h3>
        <p>
          Choose a billing period to review its transactions. Page numbers refer
          to the original PDF.
        </p>
        <div className="grid sm:grid-cols-2 gap-2">
          {query.data.statement_choices.map((item) => (
            <Button
              variant="outline"
              className="h-auto whitespace-normal text-left justify-start p-3"
              key={item.id}
              onClick={() => setStatementId(item.id)}
            >
              {item.institution} ·{" "}
              {item.account_reference || "Account needs review"} ·{" "}
              {item.period_start
                ? `${item.period_start} to ${item.period_end}`
                : item.statement_date ||
                  `Check statement date: ${item.printed_statement_date || "unreadable"}`}{" "}
              · pages {item.page_numbers.join(", ")}
            </Button>
          ))}
        </div>
      </section>
    )
  if (!query.data.currency)
    return (
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
    )
  return (
    <div className="space-y-3">
      {query.data.statement_choices.length > 1 && (
        <Button variant="outline" onClick={() => setStatementId("")}>
          Choose another statement period
        </Button>
      )}
      <ReprocessStatement
        key={fileId}
        caseId={caseId}
        fileId={fileId}
        onReady={onReprocessed}
      />
      {query.data.current_import && (
        <Button variant="outline" onClick={() => onImported()}>
          Open imported transactions
        </Button>
      )}
      {query.data.current_import?.evidence_file_id === fileId && (
        <section
          className="rounded border p-4 space-y-3"
          aria-label="Recorded statement import"
        >
          <h3 className="font-semibold">
            This statement has already been imported
          </h3>
          <p>
            {query.data.current_import.transaction_count} current transactions
            remain in use. Select <strong>Open imported transactions</strong> to
            investigate them or correct a value against its source.
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
  const owner = useAuthStore((state) => state.user?.id || state.user?.username)
  const draftKey = owner
    ? `loupe-statement-review:${owner}:${caseId}:${fileId}:${data.revision}`
    : null
  const [saved] = useState(() => readStatementDraft(draftKey, data.revision))
  const [draftSaved, setDraftSaved] = useState(!!saved)
  const [correctionsOpen, setCorrectionsOpen] = useState(false)
  const correctionControls = useRef<HTMLDivElement>(null)
  const pageKey = `${owner}:${caseId}:${fileId}:${data.revision}`
  const rememberedPage = useStatementWorkspace.getState().pages[pageKey]
  const initialPage = data.page_numbers.includes(rememberedPage)
    ? rememberedPage
    : data.rows[0]?.page_number || data.page_numbers[0] || 1
  const [sourcePage, setSourcePage] = useState(initialPage)
  const client = useQueryClient()
  const [rows, setRows] = useState(() => saved?.rows ?? initialRows(data)),
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
  const initialById = new Map(initialRows(data).map((r) => [r.id, r]))
  const changed = (r: Edit) => {
    if (r.manual_page) return true
    const initial = initialById.get(r.id)!
    return [
      "excluded",
      "date",
      "description",
      "counterparty",
      "amount_minor",
      "direction",
      "balance_minor",
    ].some((k) => r[k as keyof Edit] !== initial[k as keyof Edit])
  }
  const requiresReason = (r: Edit) =>
    changed(r) || !!originals.get(r.id)?.issues.length
  const incomplete = rows.some(
    (r) =>
      (r.balance_minor !== null && !/^-?\d+$/.test(r.balance_minor)) ||
      (requiresReason(r) && !r.reason.trim()) ||
      (!r.excluded &&
        (!/^\d{4}-\d{2}-\d{2}$/.test(r.date) ||
          !r.description.trim() ||
          !/^\d+$/.test(r.amount_minor) ||
          BigInt(r.amount_minor || "0") <= 0n))
  )
  const included = rows.filter((r) => !r.excluded)
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
              rows,
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
      rows,
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
    return () => {
      window.clearTimeout(timer)
      saveStatementDraft(draftKey, draft)
    }
  }, [
    draftKey,
    data.revision,
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
      (showExcluded || !r.excluded || requiresReason(r)) &&
      (!onlyIssues || originals.get(r.id)?.issues.length || changed(r))
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
    setShowExcluded(true)
    setOnlyIssues(false)
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
  return (
    <div className="space-y-4 pt-4">
      <header>
        <h3 className="text-lg font-semibold">Review {data.filename}</h3>
        {draftSaved && (
          <p className="text-xs text-muted-foreground" role="status">
            Review saved in this browser tab. Reopening this statement after a
            refresh restores it. Closing the tab may discard it.
          </p>
        )}
        <p className="text-sm">
          Compare the extracted statement with the original PDF. Select printed
          text to locate it on the page. Corrections and import choices are
          separate below the table.
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
        <Button
          className="ml-auto"
          onClick={
            data.current_import?.evidence_file_id === fileId
              ? () => onImported()
              : editValues
          }
        >
          {data.current_import?.evidence_file_id === fileId
            ? "Edit imported transactions"
            : "Edit import values"}
        </Button>
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
              />
            </aside>
          )}
          <div className="overflow-auto max-h-[65vh]">
            <h4 className="font-semibold">Extracted statement</h4>
            <p className="text-sm text-muted-foreground mb-3">
              Compare each table with the PDF. Select any printed value to
              locate it on the page. Use “Show corrections and import choices”
              below to change what will be imported.
            </p>
            <PrintedStatementTable
              rows={data.rows.filter((row) => row.page_number === currentPage)}
              onCell={(rowId, locator) => setFocus({ rowId, locator })}
            />
            {!data.rows.some((row) => row.page_number === currentPage) && (
              <p className="my-3 text-sm">
                No extracted rows for this page in the selected statement. Check
                the original PDF alongside it.
              </p>
            )}
            <Button
              variant="outline"
              className="my-3"
              onClick={() => setCorrectionsOpen((value) => !value)}
            >
              {correctionsOpen
                ? "Hide corrections and import choices"
                : "Show corrections and import choices"}
            </Button>
            <div ref={correctionControls} hidden={!correctionsOpen}>
              <div className="flex flex-wrap gap-4 text-sm">
                <label>
                  <input
                    type="checkbox"
                    checked={onlyIssues}
                    onChange={(e) => setOnlyIssues(e.target.checked)}
                  />{" "}
                  Show problems and edits only
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={showExcluded}
                    onChange={(e) => setShowExcluded(e.target.checked)}
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
                  {visible.map((r) => {
                    const original = originals.get(r.id)!
                    return (
                      <tr key={r.id} className={r.excluded ? "opacity-70" : ""}>
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
                                if (!value && r.direction !== direction) return
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
                                      ? (v.startsWith("-") ? "-" : "") + parsed
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
              {visible.length === 0 && (
                <p className="p-4">No rows match these review filters.</p>
              )}
            </div>
          </div>
        </div>
        {data.current_import && (
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
              className="block border rounded p-2 w-full bg-background"
              value={holder}
              onChange={(e) => setHolder(e.target.value)}
            />
          </label>
          <label>
            Account number
            <input
              aria-label="Account number"
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
              className="block border rounded p-2 bg-background"
              value={periodEnd}
              onChange={(e) => setPeriodEnd(e.target.value)}
            />
          </label>
          {(detailsChanged || data.current_import) && (
            <label>
              Reason for detail corrections
              <input
                aria-label="Reason for detail corrections"
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
            <strong>{included.length}</strong> transactions to import
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
        <div className="flex flex-wrap gap-5 text-sm">
          {(["opening", "closing"] as const).map((role) => {
            const controls = rows.filter(
              (item) =>
                item.excluded &&
                originals.get(item.id)?.kind === "balance" &&
                originals
                  .get(item.id)
                  ?.fields.description?.trim()
                  .toLowerCase() === `${role} balance` &&
                item.balance_minor !== null
            )
            const control = controls.length === 1 ? controls[0] : null
            return (
              <div key={role}>
                <span className="capitalize">
                  {role}{" "}
                  {data.metadata.balance_convention === "liability_owed"
                    ? "amount owed"
                    : "balance"}
                  :{" "}
                </span>
                {control ? (
                  <button
                    className="underline"
                    type="button"
                    aria-label={`Edit ${role} ${data.metadata.balance_convention === "liability_owed" ? "amount owed" : "balance"}`}
                    onClick={() => editBalance(control.id)}
                  >
                    {displayAmount(control.balance_minor!, digits)}{" "}
                    {data.currency}
                  </button>
                ) : (
                  <span className="text-muted-foreground">Not identified</span>
                )}
              </div>
            )
          })}
        </div>
        <p className="text-sm text-muted-foreground">
          Select an opening or closing amount to check its source or correct it.
        </p>
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
            setRows((current) => [
              ...current,
              {
                id,
                excluded: false,
                manual_page: page,
                date: "",
                description: "",
                amount_minor: "0",
                direction: "debit",
                counterparty: "",
                balance_minor: null,
                reason: "",
              },
            ])
            setFocus({ rowId: id, locator: { kind: "page_only", page } })
          }}
          disabled={!data.page_numbers.length}
        >
          Add a missed transaction
        </Button>
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
              relying on complete coverage. Use Add a missed transaction if you
              find one for this account and period.
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
                  setShowExcluded(true)
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
        <div className="rounded border bg-muted/30 p-3 space-y-2">
          <p>
            Import adds {included.length} transactions to the case. Original
            readings and your corrections are retained. A matching running
            balance is an arithmetic check, not a guarantee that the PDF
            contained no missed transactions.
          </p>
          <Button
            disabled={
              incomplete ||
              (!!data.current_import &&
                (!replacePrevious || !detailsReason.trim())) ||
              (detailsChanged && !detailsReason.trim()) ||
              Boolean(periodStart) !== Boolean(periodEnd) ||
              periodStart > periodEnd ||
              !holder.trim() ||
              !account.trim() ||
              included.length === 0
            }
            onClick={() => confirm.mutate()}
          >
            {confirm.isPending
              ? "Importing statement…"
              : `Confirm import of ${included.length} transactions`}
          </Button>
          {incomplete && (
            <p className="text-sm">
              Complete the flagged fields and record a reason for each
              correction or exception before importing.
            </p>
          )}
        </div>
      </fieldset>
      {confirm.isError && <p role="alert">{confirm.error.message}</p>}
      {confirm.isSuccess && (
        <p role="status">
          Imported {confirm.data.transaction_count} transactions. Open
          Transactions to investigate them.
        </p>
      )}
    </div>
  )
}
