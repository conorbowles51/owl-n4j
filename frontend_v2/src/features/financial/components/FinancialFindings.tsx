import type { CaseworkEntry } from "@/features/workspace/casework-api"
import { InvestigatorFindingEditor } from "./InvestigatorFindingEditor"
import { findingDraft, findingPaymentIds } from "../lib/investigator-finding"
import { useFinancialStore } from "../stores/financial.store"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { FinancialReportBuilder } from "./FinancialReportBuilder"
import { SavedFinancialReport } from "./SavedFinancialReport"
import { useFinancialDraft } from "../stores/financial-drafts"
import {
  emptyReportDraft,
  reportDraftName,
  type FinancialReportDraft,
} from "../lib/financial-report"
import { SavedIndirectFinding } from "./SavedIndirectFinding"
import { indirectWorkpaperSchema } from "../lib/saved-indirect"
import { savedAnalysisSummary } from "../lib/saved-analysis-summary"
import { SavedTraceFinding } from "./SavedTraceFinding"
import { FindingReportBundle } from "./FindingReportBundle"
import { useGraphStore } from "@/stores/graph.store"
import { useUIStore } from "@/stores/ui.store"
import { findingReport } from "../lib/finding-report"
import { useState } from "react"
import { useCaseworkEntries } from "@/features/workspace/hooks/use-casework"
import { Button } from "@/components/ui/button"
import { LedgerSourceDialog } from "./LedgerSourceDialog"
import { formatLedgerAmount } from "../lib/ledger-format"
import { transactionDetail } from "../lib/transaction-detail"
import { SavedPaymentDocument } from "./PaymentDocumentReview"
import { paymentDocumentSchema } from "../lib/payment-document"

export function FinancialFindings({
  caseId,
  caseTitle = "",
}: {
  caseId: string | undefined
  caseTitle?: string
}) {
  const [reportDraft, setReportDraft] = useFinancialDraft<FinancialReportDraft>(
    caseId || "",
    reportDraftName,
    emptyReportDraft
  )
  const selectNodes = useGraphStore((state) => state.selectNodes)
  const expand = useUIStore((state) => state.expandGraphPanelTo)
  const [view, setView] = useFinancialDraft(caseId || "", "findings-list", {
    search: "",
    page: 0,
  })
  const { search, page } = view
  const setPage = (page: number) => setView((current) => ({ ...current, page }))
  const { canEdit } = useFinancialAccess()
  const [editing, setEditing] = useState<CaseworkEntry | "new" | null>(null)
  const [kind, setKind] = useState("financial")
  const [progress, setProgress] = useState("all")
  const [error, setError] = useState("")
  const [source, setSource] = useState<string | null>(null)
  const query = useCaseworkEntries(caseId, {
    tag:
      progress === "all" || kind === "financial-report"
        ? kind
        : kind === "financial"
          ? `financial-${progress}`
          : `${kind}-${progress}`,
    q: search,
    limit: 25,
    offset: page * 25,
  })
  if (!caseId) return <p>Choose a case to open its financial notes.</p>
  const entries =
    query.data?.entries.filter(
      (entry) => entry.case_id === caseId && entry.tags.includes("financial")
    ) ?? []
  return (
    <section
      className="space-y-4 p-4"
      aria-label="Financial findings and notes"
    >
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold">Findings</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Record what the evidence shows, what remains unknown and what needs
            to happen next.
          </p>
        </div>
        {canEdit && (
          <Button onClick={() => setEditing("new")}>Create finding</Button>
        )}
      </header>
      <div className="flex gap-3 flex-wrap">
        <label className="text-sm">
          Type
          <select
            aria-label="Finding type"
            className="block rounded border bg-card p-2"
            value={kind}
            onChange={(e) => {
              setKind(e.target.value)
              setPage(0)
            }}
          >
            <option value="financial">All saved work</option>
            <option value="financial-question">Questions</option>
            <option value="financial-observation">Observations</option>
            <option value="financial-conclusion">Conclusions</option>
            <option value="financial-report">Reports</option>
          </select>
        </label>
        <label className="text-sm">
          Progress
          <select
            aria-label="Progress"
            className="block rounded border bg-card p-2"
            value={progress}
            disabled={kind === "financial-report"}
            onChange={(e) => {
              setProgress(e.target.value)
              setPage(0)
            }}
          >
            <option value="all">All progress</option>
            <option value="open">Open</option>
            <option value="in-progress">In progress</option>
            <option value="complete">Complete</option>
          </select>
        </label>
      </div>
      <FinancialReportBuilder
        key={caseId}
        caseId={caseId}
        caseTitle={caseTitle}
      />
      <label className="block">
        Search saved work
        <input
          className="block w-full max-w-lg rounded border bg-background p-2"
          value={search}
          onChange={(e) => {
            setView({ search: e.target.value, page: 0 })
          }}
        />
      </label>
      {query.isPending && <p role="status">Loading saved work…</p>}
      {query.isError && (
        <div role="alert" className="space-y-2">
          <p>Saved work could not be loaded. {query.error.message}</p>
          <Button
            variant="outline"
            disabled={query.isFetching}
            onClick={() => void query.refetch()}
          >
            {query.isFetching ? "Retrying…" : "Try loading saved work again"}
          </Button>
        </div>
      )}
      {!query.isPending && !query.isError && !entries.length && (
        <section className="rounded-xl border bg-card p-8 space-y-3">
          <h3 className="text-lg font-semibold">
            {search || kind !== "financial"
              ? "No saved work matches these filters"
              : "Build the investigation record"}
          </h3>
          <p className="text-sm text-muted-foreground">
            Create a question to follow up, record an observation, or select
            payments to support a conclusion. Saved findings can be revised and
            included in a report.
          </p>
          <Button
            variant="outline"
            onClick={() =>
              useFinancialStore.getState().setMainView("transactions")
            }
          >
            Choose payments to investigate
          </Button>
        </section>
      )}
      {error && <p role="alert">{error}</p>}
      {entries.map((entry) => (
        <article
          key={entry.id}
          className="rounded border bg-card p-4 space-y-3"
        >
          <div className="flex justify-between items-start gap-3">
            <div>
              <p className="text-xs text-muted-foreground capitalize">
                {entry.tags.includes("financial-workspace")
                  ? `${findingDraft(entry).kind} · ${findingDraft(entry).progress.replace("-", " ")}`
                  : entry.tags.includes("financial-report")
                    ? "Saved report"
                    : "Saved note or analysis"}
                {findingPaymentIds(entry).length
                  ? ` · ${findingPaymentIds(entry).length} supporting payments`
                  : ""}
              </p>
              <h3 className="font-semibold text-lg mt-1">
                {entry.title || "Untitled note"}
              </h3>
            </div>
            {canEdit && !entry.tags.includes("financial-report") && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setEditing(entry)}
              >
                Edit finding
              </Button>
            )}
          </div>
          {canEdit && !entry.tags.includes("financial-report") && (
            <label className="flex gap-2 items-center text-sm">
              <input
                type="checkbox"
                aria-label={`Include ${entry.title || "Untitled note"} in report`}
                checked={reportDraft.selected.some(
                  (note) => note.id === entry.id
                )}
                disabled={query.isPlaceholderData}
                onChange={(event) =>
                  setReportDraft((current) => ({
                    ...current,
                    selected: event.target.checked
                      ? [
                          ...current.selected.filter(
                            (note) => note.id !== entry.id
                          ),
                          {
                            id: entry.id,
                            title: entry.title || "Untitled note",
                            version: entry.version,
                          },
                        ]
                      : current.selected.filter((note) => note.id !== entry.id),
                  }))
                }
              />
              Include in report
            </label>
          )}
          {entry.tags.includes("financial-report") && (
            <SavedFinancialReport
              key={entry.id + ":" + entry.version}
              caseId={caseId}
              entry={entry}
            />
          )}
          <p className="text-xs text-muted-foreground">
            {entry.entry_type} ·{" "}
            {entry.author_name || entry.author_email || "Author not recorded"}
            {entry.updated_at
              ? ` · ${new Date(entry.updated_at).toLocaleString()}`
              : ""}
          </p>
          {entry.links.some(
            (link) => link.metadata.schema === indirectWorkpaperSchema
          ) ? (
            <details>
              <summary className="cursor-pointer">
                Written explanation and recorded amounts
              </summary>
              <p className="whitespace-pre-wrap mt-2">{entry.body}</p>
            </details>
          ) : entry.tags.includes("financial-workspace") ? (
            <div className="space-y-3 text-sm">
              <p className="whitespace-pre-wrap">
                {findingDraft(entry).explanation}
              </p>
              {(findingDraft(entry).nextAction ||
                findingDraft(entry).owner) && (
                <div className="rounded border bg-muted/20 p-3">
                  {findingDraft(entry).nextAction && (
                    <h4 className="font-medium">Next action</h4>
                  )}
                  <p className="whitespace-pre-wrap">
                    {findingDraft(entry).nextAction}
                  </p>
                  {findingDraft(entry).owner && (
                    <p className="mt-2 text-muted-foreground">
                      Assigned to {findingDraft(entry).owner}
                    </p>
                  )}
                </div>
              )}
            </div>
          ) : (
            <p className="whitespace-pre-wrap">{entry.body}</p>
          )}
          {entry.links.map((link) => {
            const ids = Array.isArray(
              link.source_anchor?.financial_transaction_ids
            )
              ? link.source_anchor.financial_transaction_ids.filter(
                  (id): id is string => typeof id === "string"
                )
              : []
            const snapshots = Array.isArray(link.metadata?.transactions)
              ? link.metadata.transactions.flatMap((value) => {
                  const parsed = transactionDetail.safeParse(value)
                  return parsed.success && parsed.data.case_id === caseId
                    ? [parsed.data]
                    : []
                })
              : []
            return (
              <div key={link.id} className="space-y-2">
                <p className="text-sm font-medium">
                  {link.target_label || "Supporting record"}
                </p>
                {link.metadata.schema === paymentDocumentSchema && (
                  <SavedPaymentDocument
                    metadata={link.metadata}
                    caseId={caseId}
                    fileId={link.target_id}
                  />
                )}
                {link.metadata?.schema ===
                  "loupe.financial.event_context/1" && (
                  <>
                    <p className="text-sm">
                      {String(link.metadata.date || "Date not recorded")} ·{" "}
                      {String(link.metadata.summary || "")}
                    </p>
                    <Button
                      variant="outline"
                      onClick={() => {
                        selectNodes([link.target_id])
                        expand("detail")
                      }}
                    >
                      Open case event
                    </Button>
                  </>
                )}
                {link.metadata?.schema === indirectWorkpaperSchema && (
                  <SavedIndirectFinding
                    key={entry.id + ":" + entry.version}
                    entry={entry}
                    link={link}
                    caseId={caseId}
                  />
                )}
                {link.target_type === "entry" && (
                  <a
                    className="underline text-sm"
                    href={`/cases/${caseId}/workspace?view=casework&entry=${encodeURIComponent(link.target_id)}`}
                  >
                    Open linked note
                  </a>
                )}
                {savedAnalysisSummary(link.metadata?.analysis).map(
                  (line, index) => (
                    <p key={index} className="text-sm">
                      {line}
                    </p>
                  )
                )}
                {link.metadata?.schema === "loupe.financial.saved_trace/1" && (
                  <SavedTraceFinding
                    key={entry.id + ":" + entry.version}
                    caseId={caseId}
                    envelope={link.metadata.envelope}
                  />
                )}
                {!!link.metadata?.analysis &&
                  typeof link.metadata.analysis === "object" &&
                  "summary" in link.metadata.analysis && (
                    <p className="text-sm">
                      {String(link.metadata.analysis.summary)}
                    </p>
                  )}
                {ids.length > 0 && (
                  <SavedPaymentLinks
                    key={entry.id + ":" + link.id + ":" + entry.version}
                    ids={ids}
                    snapshots={snapshots}
                    refs={link.source_anchor.financial_ref_ids}
                    onOpen={setSource}
                  />
                )}
              </div>
            )
          })}
          {canEdit && !entry.tags.includes("financial-report") && (
            <details className="rounded border p-3 space-y-2">
              <summary className="cursor-pointer font-medium">
                Create a report from this note
              </summary>
              <p className="text-sm">
                Includes this note and any saved payment values and statement
                references attached to it. The original PDFs are not included.
                Open the downloaded HTML file to read it or print it to PDF.
              </p>
              <Button
                variant="outline"
                onClick={() => {
                  setError("")
                  try {
                    const url = URL.createObjectURL(
                      new Blob([findingReport(entry, caseId)], {
                        type: "text/html;charset=utf-8",
                      })
                    )
                    const link = document.createElement("a")
                    link.href = url
                    link.download = `financial-note-${entry.id}.html`
                    link.click()
                    setTimeout(() => URL.revokeObjectURL(url), 1000)
                  } catch (failure) {
                    setError(
                      failure instanceof Error
                        ? failure.message
                        : "The report could not be created."
                    )
                  }
                }}
              >
                Download this note and its payments
              </Button>
              <FindingReportBundle
                key={entry.id + ":" + entry.version}
                entry={entry}
                caseId={caseId}
              />
            </details>
          )}
          <a
            className="inline-block underline text-sm"
            href={`/cases/${caseId}/workspace?view=casework&entry=${entry.id}`}
          >
            {entry.tags.includes("financial-report")
              ? "Open report record in Workspace"
              : "Edit or review in Workspace"}
          </a>
        </article>
      ))}
      {(query.data?.total ?? 0) > 25 && (
        <div className="flex gap-2">
          <Button
            disabled={page === 0 || query.isPlaceholderData || query.isFetching}
            onClick={() => setPage(page - 1)}
          >
            Previous notes
          </Button>
          <Button
            disabled={
              query.isPlaceholderData ||
              query.isFetching ||
              (page + 1) * 25 >= (query.data?.total ?? 0)
            }
            onClick={() => setPage(page + 1)}
          >
            Next notes
          </Button>
        </div>
      )}
      {editing && (
        <InvestigatorFindingEditor
          key={editing === "new" ? "new" : `${editing.id}:${editing.version}`}
          caseId={caseId}
          entry={editing === "new" ? undefined : editing}
          onClose={() => setEditing(null)}
        />
      )}
      {source && (
        <LedgerSourceDialog
          key={source}
          caseId={caseId}
          transactionId={source}
          onClose={() => setSource(null)}
        />
      )}
    </section>
  )
}

function SavedPaymentLinks({
  ids,
  snapshots,
  refs,
  onOpen,
}: {
  ids: string[]
  snapshots: ReturnType<typeof transactionDetail.parse>[]
  refs: unknown
  onOpen: (id: string) => void
}) {
  const [page, setPage] = useState(0)
  const [open, setOpen] = useState(ids.length <= 20)
  const byId = new Map(snapshots.map((row) => [row.key, row]))
  return (
    <details
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="cursor-pointer text-sm">
        {ids.length} linked payments
      </summary>
      <div className="flex flex-wrap gap-2">
        {ids.slice(page * 50, (page + 1) * 50).map((id, offset) => {
          const row = byId.get(id),
            index = page * 50 + offset
          return (
            <Button
              key={id}
              className="h-auto whitespace-normal text-left justify-start"
              variant="outline"
              onClick={() => onOpen(id)}
            >
              {row
                ? `${row.ordering_date} · ${row.description || "Payment"} · ${formatLedgerAmount(row.amount_minor, row.currency).text} ${row.currency}`
                : `Open transaction ${Array.isArray(refs) ? refs[index] || index + 1 : index + 1}`}
            </Button>
          )
        })}
      </div>
      {ids.length > 50 && (
        <div className="flex flex-wrap items-center gap-2 mt-2">
          <Button
            variant="outline"
            disabled={!page}
            onClick={() => setPage(page - 1)}
          >
            Previous saved payments
          </Button>
          <label>
            Saved payment page{" "}
            <select
              aria-label="Saved payment page"
              className="border rounded bg-background p-2"
              value={page}
              onChange={(event) => setPage(Number(event.target.value))}
            >
              {Array.from(
                { length: Math.ceil(ids.length / 50) },
                (_, index) => (
                  <option key={index} value={index}>
                    {index + 1}
                  </option>
                )
              )}
            </select>
          </label>
          <span>
            {page * 50 + 1} to {Math.min((page + 1) * 50, ids.length)} of{" "}
            {ids.length} payments
          </span>
          <Button
            variant="outline"
            disabled={(page + 1) * 50 >= ids.length}
            onClick={() => setPage(page + 1)}
          >
            Next saved payments
          </Button>
        </div>
      )}
    </details>
  )
}
