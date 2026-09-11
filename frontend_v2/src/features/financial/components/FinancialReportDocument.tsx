import { useEffect, useRef, useState, type ReactNode } from "react"
import { Button } from "@/components/ui/button"
import {
  financialReportDownload,
  type FinancialReport,
} from "../lib/financial-report"

function download(bytes: BlobPart, type: string, filename: string) {
  const url = URL.createObjectURL(new Blob([bytes], { type }))
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
export function FinancialReportDocument({
  report,
  saveAction,
}: {
  report: FinancialReport
  saveAction?: ReactNode
}) {
  const [includePdfs, setIncludePdfs] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const request = useRef<AbortController | null>(null)
  useEffect(() => () => request.current?.abort(), [])
  return (
    <section
      className="space-y-3"
      aria-label="Financial report preview and downloads"
    >
      <div className="rounded border p-3 space-y-2 text-sm">
        <p>
          <strong>{report.data.notes.length} saved notes</strong> in the order
          shown below. Their saved payment values and calculations are included.
        </p>
        <ol className="list-decimal pl-5">
          {report.data.notes.map((note) => (
            <li key={note.id}>
              {note.title || "Untitled note"} · version {note.version}
            </li>
          ))}
        </ol>
        <p>
          A payment can appear in more than one note. Totals are provided per
          note, with accounts and currencies kept separate.
        </p>
        <details>
          <summary className="cursor-pointer">
            Supporting file references ({report.files.length})
          </summary>
          <ul className="list-disc pl-5">
            {report.files.map((file) => (
              <li key={file.id}>{file.label}</li>
            ))}
          </ul>
        </details>
        <label className="flex gap-2 items-start">
          <input
            type="checkbox"
            checked={includePdfs}
            disabled={busy || !report.files.length || report.files.length > 20}
            onChange={(event) => setIncludePdfs(event.target.checked)}
          />
          Include the supporting PDFs in the download package
        </label>
        {includePdfs && (
          <p>
            Includes the whole files listed above, even if they contain other
            payments or periods. Each file is checked against its recorded hash
            before download.
          </p>
        )}
        {report.files.length > 20 && (
          <p>
            This report references more than 20 files. Download the report
            without PDFs and obtain any required originals from Evidence.
          </p>
        )}
        <p>
          Saving keeps the report in this case. Downloading saves a copy to your
          computer.
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        {saveAction}
        <Button
          variant="outline"
          disabled={busy}
          onClick={() =>
            download(
              report.html,
              "text/html;charset=utf-8",
              "financial-report.html"
            )
          }
        >
          Download readable report
        </Button>
        <Button
          variant="outline"
          disabled={busy}
          onClick={async () => {
            if (request.current) return
            const controller = new AbortController()
            request.current = controller
            setBusy(true)
            setError("")
            const timer = setTimeout(() => controller.abort(), 120000)
            try {
              const bytes = await financialReportDownload(
                report,
                includePdfs,
                controller.signal
              )
              if (!controller.signal.aborted)
                download(
                  bytes,
                  "application/zip",
                  "financial-report-package.zip"
                )
            } catch (failure) {
              setError(
                controller.signal.aborted
                  ? "Report preparation was cancelled or timed out. Try again."
                  : failure instanceof Error
                    ? failure.message
                    : "The report package could not be prepared."
              )
            } finally {
              clearTimeout(timer)
              request.current = null
              setBusy(false)
            }
          }}
        >
          {busy
            ? "Preparing download…"
            : includePdfs
              ? "Download report package with PDFs"
              : "Download report and saved data"}
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        Open the readable HTML report to print it or save it as a PDF. The
        package also contains the saved report data and a list of file hashes.
      </p>
      {error && <p role="alert">{error}</p>}
      <iframe
        title="Financial report preview"
        sandbox=""
        srcDoc={report.html}
        className="h-[60vh] min-h-80 w-full rounded border bg-white"
      />
    </section>
  )
}
