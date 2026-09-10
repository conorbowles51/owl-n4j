import { sameTableView, type LedgerTableView } from "../lib/ledger-table-view"
import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { candidateUrl } from "../lib/candidate-contract"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"

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
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState("")
  const [marking, setMarking] = useState("unmarked")
  const [includeCaseHistory, setIncludeCaseHistory] = useState(false)
  const [includePdf, setIncludePdf] = useState(false)
  const [includeSourceFiles, setIncludeSourceFiles] = useState(false)
  const active = useRef<AbortController | null>(null)
  useEffect(() => () => active.current?.abort(), [])
  const download = async () => {
    if (active.current) return
    const controller = new AbortController()
    active.current = controller
    setBusy(true)
    setMessage("")
    let timedOut = false
    const timeout = setTimeout(() => {
      timedOut = true
      controller.abort()
    }, 120000)
    try {
      const search = new URLSearchParams()
      search.set("privilege_marking", marking)
      if (tableView) search.set("table_view", JSON.stringify(tableView))
      if (params.accountId) search.set("account_id", params.accountId)
      if (params.startDate) search.set("start_date", params.startDate)
      if (params.endDate) search.set("end_date", params.endDate)
      if (includeCaseHistory)
        search.set("include_case_financial_history", "true")
      if (includePdf) search.set("include_pdf", "true")
      if (includeSourceFiles) search.set("include_source_files", "true")
      const token = localStorage.getItem("authToken")
      const response = await fetch(
        `${candidateUrl("ledger-export", caseId)}&${search}`,
        {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          credentials: "include",
          signal: controller.signal,
        }
      )
      if (!response.ok) {
        const error = await response.json().catch(() => null)
        throw new Error(
          typeof error?.detail === "string"
            ? error.detail
            : `Export failed (${response.status}).`
        )
      }
      if (
        response.headers.get("X-Loupe-Case-Review-History") !==
          (includeCaseHistory ? "true" : "false") ||
        response.headers.get("X-Loupe-Privilege-Marking") !== marking ||
        !sameTableView(response.headers.get("X-Loupe-Table-View"), tableView) ||
        response.headers.get("content-type")?.split(";")[0] !==
          "application/zip" ||
        response.headers.get("X-Loupe-Case-Id") !== caseId ||
        response.headers.get("X-Loupe-Account-Id") !==
          (params.accountId ?? "") ||
        response.headers.get("X-Loupe-Start-Date") !==
          (params.startDate ?? "") ||
        response.headers.get("X-Loupe-End-Date") !== (params.endDate ?? "") ||
        (includePdf && response.headers.get("X-Loupe-PDF-Report") !== "true") ||
        (includeSourceFiles &&
          response.headers.get("X-Loupe-Source-Files") !== "true") ||
        (!includeSourceFiles &&
          response.headers.get("X-Loupe-Source-Files") === "true")
      )
        throw new Error(
          "Export returned for different filters or in an unexpected format."
        )
      const blob = await response.blob()
      if (controller.signal.aborted) return
      const url = URL.createObjectURL(blob),
        link = document.createElement("a")
      link.href = url
      link.download = tableView
        ? "loupe-ledger-table-view.zip"
        : "loupe-ledger-export.zip"
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      setMessage("Download started: ledger snapshot and manifest.")
    } catch (error) {
      if (timedOut)
        setMessage(
          "Export timed out. Retry with a narrower account/date scope."
        )
      else if (!controller.signal.aborted)
        setMessage(error instanceof Error ? error.message : "Export failed.")
    } finally {
      clearTimeout(timeout)
      active.current = null
      setBusy(false)
    }
  }
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
      including pending PDF readings)
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
            Includes recorded review methods and an inventory of available
            expert support. Missing validation, custody history and tracing
            material remain identified; this is not a complete expert packet.
          </p>
          <Button disabled={busy} onClick={() => void download()}>
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
        {message && <p role="status">{message}</p>}
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
          JSON and HTML report. Up to 2,000 captured readings per PDF.
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
        Includes recorded review methods and an inventory of available expert
        support. Missing validation, custody history and tracing material remain
        identified; this is not a complete expert packet.
      </p>
      <Button disabled={busy} onClick={() => void download()}>
        {busy
          ? "Preparing ledger export…"
          : tableView
            ? "Download this table view"
            : "Download ledger snapshot"}
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
      {message && <p role="status">{message}</p>}
    </section>
  )
}
