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

export function FinancialFindings({ caseId }: { caseId: string | undefined }) {
  const selectNodes = useGraphStore((state) => state.selectNodes)
  const expand = useUIStore((state) => state.expandGraphPanelTo)
  const [page, setPage] = useState(0)
  const [search, setSearch] = useState("")
  const [error, setError] = useState("")
  const [source, setSource] = useState<string | null>(null)
  const query = useCaseworkEntries(caseId, {
    tag: "financial",
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
      <header>
        <h2 className="text-lg font-semibold">Findings and notes</h2>
        <p>
          Reopen observations, saved payment selections and analysis notes.
          These are also available in Workspace.
        </p>
      </header>
      <label className="block">
        Search saved work
        <input
          className="block w-full max-w-lg rounded border bg-background p-2"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setPage(0)
          }}
        />
      </label>
      {query.isPending && <p role="status">Loading saved work…</p>}
      {query.isError && (
        <p role="alert">
          Saved work could not be loaded. {query.error.message}
        </p>
      )}
      {!query.isPending && !query.isError && !entries.length && (
        <p>
          No financial notes match this view. Open a transaction to add a note,
          or select payments and save them together.
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      {entries.map((entry) => (
        <article
          key={entry.id}
          className="rounded border bg-card p-4 space-y-3"
        >
          <h3 className="font-semibold">{entry.title || "Untitled note"}</h3>
          <p className="text-xs text-muted-foreground">
            {entry.entry_type} ·{" "}
            {entry.author_name || entry.author_email || "Author not recorded"}
            {entry.updated_at
              ? ` · ${new Date(entry.updated_at).toLocaleString()}`
              : ""}
          </p>
          <p className="whitespace-pre-wrap">{entry.body}</p>
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
                <details open={ids.length <= 20}>
                  <summary className="cursor-pointer text-sm">
                    {ids.length} linked payments
                  </summary>
                  <div className="flex flex-wrap gap-2">
                    {ids.map((id, index) => {
                      const row = snapshots.find((row) => row.key === id)
                      return (
                        <Button
                          key={id}
                          className="h-auto whitespace-normal text-left justify-start"
                          variant="outline"
                          onClick={() => setSource(id)}
                        >
                          {row
                            ? `${row.ordering_date} · ${row.description || "Payment"} · ${formatLedgerAmount(row.amount_minor, row.currency).text} ${row.currency}`
                            : `Open transaction ${Array.isArray(link.source_anchor.financial_ref_ids) ? link.source_anchor.financial_ref_ids[index] || index + 1 : index + 1}`}
                        </Button>
                      )
                    })}
                  </div>
                </details>
              </div>
            )
          })}
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
          <a
            className="inline-block underline text-sm"
            href={`/cases/${caseId}/workspace?view=casework&entry=${entry.id}`}
          >
            Edit or review in Workspace
          </a>
        </article>
      ))}
      {(query.data?.total ?? 0) > 25 && (
        <div className="flex gap-2">
          <Button disabled={page === 0} onClick={() => setPage(page - 1)}>
            Previous notes
          </Button>
          <Button
            disabled={(page + 1) * 25 >= (query.data?.total ?? 0)}
            onClick={() => setPage(page + 1)}
          >
            Next notes
          </Button>
        </div>
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
