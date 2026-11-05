import { sha256 } from "@noble/hashes/sha2.js"
import type { LedgerTableView } from "../lib/ledger-table-view"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { formatBytes } from "@/features/evidence/upload-progress"
import { isPdfSizeRefusal, useStartedRun, wholeCaseFileUrl, type ExportRunSummary } from "../lib/whole-case-run"
import { WholeCasePdf } from "./WholeCasePdf"
import { WholeCaseProgress } from "./WholeCaseProgress"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"
import { TraceSupportAssembly } from "./TraceSupportAssembly"
import { TraceSupportVerification } from "./TraceSupportVerification"
import { LedgerExportComparison } from "./LedgerExportComparison"
import { ExpertPacketResult } from "./ExpertPacketResult"
import { readExpertPacket } from "../lib/expert-packet"

const EXPERT_PACKET_NOTE =
  "Includes recorded review methods and the four parts of the expert packet: custody and decisions, components, measured validation and selected tracing. Each download states which parts are complete for that export."

export function LedgerExportButton({
  caseId,
  params,
  tableView,
}: {
  caseId: string
  params: LedgerQueryParams
  tableView?: LedgerTableView
}) {
  return (
    <ScopedExport
      key={JSON.stringify([
        caseId,
        params.accountId,
        params.accountIds,
        params.accountHolders,
        params.startDate,
        params.endDate,
        tableView,
      ])}
      caseId={caseId}
      params={params}
      tableView={tableView}
    />
  )
}
function ScopedExport({
  caseId,
  params,
  tableView,
}: {
  caseId: string
  params: LedgerQueryParams
  tableView?: LedgerTableView
}) {
  const [marking, setMarking] = useState("unmarked")
  const [includeCaseHistory, setIncludeCaseHistory] = useState(false)
  const [includePdf, setIncludePdf] = useState(false)
  const [includeSourceFiles, setIncludeSourceFiles] = useState(false)
  const request = {
    kind: "export",
    privilege_marking: marking,
    include_case_financial_history: includeCaseHistory,
    include_pdf: includePdf,
    include_source_files: includeSourceFiles,
    ...(tableView ? { table_view: JSON.stringify(tableView) } : {}),
    ...(params.accountId ? { account_id: params.accountId } : {}),
    ...(params.accountIds?.length ? { account_ids: params.accountIds } : {}),
    ...(params.accountHolders?.length ? { account_holders: params.accountHolders } : {}),
    ...(params.startDate ? { start_date: params.startDate } : {}),
    ...(params.endDate ? { end_date: params.endDate } : {}),
  }
  const storageKey = `loupe.ledger-export-run.${caseId}.${digest(JSON.stringify(request))}`
  // Each choice of scope and options has its own run; changing one shows that one's run.
  return (
    <ExportForm
      key={storageKey}
      caseId={caseId}
      params={params}
      tableView={tableView}
      request={request}
      storageKey={storageKey}
      options={{
        marking,
        setMarking,
        includeCaseHistory,
        setIncludeCaseHistory,
        includePdf,
        setIncludePdf,
        includeSourceFiles,
        setIncludeSourceFiles,
      }}
    />
  )
}

function digest(text: string) {
  return Array.from(sha256(new TextEncoder().encode(text)), (v) => v.toString(16).padStart(2, "0")).join("")
}

function ExportForm({
  caseId,
  params,
  tableView,
  request,
  storageKey,
  options: {
    marking,
    setMarking,
    includeCaseHistory,
    setIncludeCaseHistory,
    includePdf,
    setIncludePdf,
    includeSourceFiles,
    setIncludeSourceFiles,
  },
}: {
  caseId: string
  params: LedgerQueryParams
  tableView?: LedgerTableView
  request: Record<string, unknown>
  storageKey: string
  options: {
    marking: string
    setMarking: (value: string) => void
    includeCaseHistory: boolean
    setIncludeCaseHistory: (value: boolean) => void
    includePdf: boolean
    setIncludePdf: (value: boolean) => void
    includeSourceFiles: boolean
    setIncludeSourceFiles: (value: boolean) => void
  }
}) {
  const { run, startError, starting, start } = useStartedRun<ExportRunSummary>(caseId, request, storageKey)
  const busy = starting || run?.status === "queued" || run?.status === "running"
  const refusal = startError?.message ?? (run?.status === "failed" || run?.status === "stopped" ? run.error : undefined)
  const finished = run?.status === "completed" && run.summary ? run.summary : null
  // A PDF over one report's size is not a dead end: the numbered parts below replace the refusal.
  const numberedPdf = includePdf && isPdfSizeRefusal(refusal)
  const result = (
    <>
      {startError ? (
        <p role="alert">{startError.message}</p>
      ) : run && !finished && !numberedPdf ? (
        <WholeCaseProgress
          run={run}
          error={null}
          noun="ledger export"
          lead="The export is being prepared in the background. You can leave this page; it carries on and the file is offered here."
          againLabel="Prepare it again"
          onAgain={() => void start(true)}
        />
      ) : null}
      {finished && run && (
        <div className="space-y-1 text-sm" role="status">
          <p>
            Ready: {finished.rows.toLocaleString("en-US")} rows
            {finished.audit_events
              ? `, ${finished.audit_events.event_count.toLocaleString("en-US")} audit events`
              : ""}
            , read at {finished.generated_at.slice(0, 16).replace("T", " ")} UTC.
          </p>
          <a className="underline" href={wholeCaseFileUrl(caseId, run.id, finished.filename)} download>
            Download the export ({formatBytes(finished.archive_bytes)})
          </a>{" "}
          <Button size="sm" variant="outline" disabled={busy} onClick={() => void start(true)}>
            Read the rows again
          </Button>
          <ExpertPacketResult packet={readExpertPacket(JSON.stringify(finished.packet))} />
        </div>
      )}
    </>
  )
  const markingControl = (
    <label className="flex items-center gap-2 text-sm">
      {tableView ? "Table export marking" : "Export marking"}
      <select
        value={marking}
        disabled={busy}
        onChange={(event) => setMarking(event.target.value)}
      >
        <option value="unmarked">No privilege marking</option>
        <option value="confidential">Confidential</option>
        <option value="privileged_confidential">
          Privileged and confidential
        </option>
      </select>
    </label>
  )
  const historyControl = (
    <label className="flex items-start gap-2 text-sm">
      <input
        type="checkbox"
        checked={includeCaseHistory}
        disabled={busy}
        onChange={(event) => setIncludeCaseHistory(event.target.checked)}
      />
      Include wider case financial review history (all accounts and dates,
      including pending PDF readings and recorded case audit events)
    </label>
  )
  if (tableView)
    return (
      <section
        aria-label="Export this table view"
        className="space-y-2 rounded border p-3"
      >
        {markingControl}
        {historyControl}
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-sm">
            {EXPERT_PACKET_NOTE}
          </p>
          <Button disabled={busy} onClick={() => void start()}>
            {busy ? "Preparing table export…" : "Download this table view"}
          </Button>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={includePdf}
              disabled={busy}
              onChange={(e) => setIncludePdf(e.target.checked)}
            />
            Include a PDF in the table-view export
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={includeSourceFiles}
              disabled={busy}
              onChange={(e) => setIncludeSourceFiles(e.target.checked)}
            />
            Include originals in the table-view export
          </label>
        </div>
        <p className="text-sm">
          Preserves this search, filters and order for all matching rows across
          table pages, captured at export time. The bundle also retains the full
          applied account/date snapshot and source history; its main totals
          describe that full scope.
        </p>
        {includeSourceFiles && (
          <p className="text-sm">
            Originals are complete referenced files with fresh hash checks,
            including pages outside the table filters.
          </p>
        )}
        {result}
      </section>
    )
  return (
    <section
      className="space-y-2 rounded border p-3"
      aria-label={
        tableView ? "Export this table view" : "Export ledger analysis"
      }
    >
      {markingControl}
      {historyControl}
      <LedgerExportComparison key={caseId} caseId={caseId} />
      <TraceSupportVerification key={`support-${caseId}`} caseId={caseId} />
      <TraceSupportAssembly key={`assembly-${caseId}`} caseId={caseId} />
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          checked={includePdf}
          disabled={busy}
          onChange={(event) => setIncludePdf(event.target.checked)}
        />
        {tableView
          ? "Include a PDF in the table-view export"
          : "Include a paginated PDF report"}
      </label>
      {includePdf && (
        <p className="text-sm">
          The PDF uses the same captured readings, totals and history as the
          JSON and HTML report. Up to 2,000 captured readings per PDF; a
          larger scope is written in the background as numbered parts that
          together cover every reading.
        </p>
      )}
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          checked={includeSourceFiles}
          disabled={busy}
          onChange={(event) => setIncludeSourceFiles(event.target.checked)}
        />
        {tableView
          ? "Include originals in the table-view export"
          : "Include original source files with fresh hash checks"}
      </label>
      {includeSourceFiles && (
        <p className="text-sm">
          Includes complete referenced files, which may contain pages outside
          the selected dates or account. Up to 100 files and 64 MiB; missing or
          changed files stop the export.
        </p>
      )}
      <p className="text-sm">
        {EXPERT_PACKET_NOTE}
      </p>
      <Button disabled={busy} onClick={() => void start()}>
        {busy ? "Preparing ledger export…" : "Download ledger snapshot"}
      </Button>
      {tableView && (
        <p>
          Records this search, currency, direction, proof filter and display
          order for all matching rows, across every table page, at export time.
          The bundle also contains the full applied account/date snapshot and
          history. Its main totals describe that full scope.
        </p>
      )}
      <p>
        Downloads the applied account/date scope, exact rows and totals, source
        references and relevant decision history with a verification manifest
        and a readable report with section-specific exhibit assessments. Report
        amounts retain their exact minor units alongside currency formatting.
        PDF original readings, review history and finalization receipts for
        referenced files are included. Original files are included only when
        selected above; otherwise source hashes are recorded values rather than
        fresh file checks.
      </p>
      {result}
      {numberedPdf && (
        <WholeCasePdf caseId={caseId} params={params} marking={marking} />
      )}
    </section>
  )
}
