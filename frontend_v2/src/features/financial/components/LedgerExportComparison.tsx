import { useEffect, useRef, useState } from "react"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { candidateUrl } from "../lib/candidate-contract"

const changes = z.object({
  added: z.array(z.string()).max(25000),
  removed: z.array(z.string()).max(25000),
  changed: z
    .array(
      z.object({
        id: z.string(),
        changed_paths: z.array(z.string()).max(100),
        changed_path_count: z.number().int().nonnegative(),
        paths_truncated: z.boolean(),
      })
    )
    .max(25000),
})
const comparison = z
  .object({
    schema_version: z.literal("loupe.financial.export_comparison/1"),
    case_id: z.string(),
    status: z.enum([
      "scope_changed",
      "captured_content_changed",
      "same_captured_content",
    ]),
    readings: changes,
    decisions: changes,
    pdf_review_history: z.record(z.string(), changes),
    export_preparation_changed: z.boolean(),
    packaging_or_generation_changed: z.boolean(),
    limitation: z.string(),
  })
  .passthrough()
type Result = z.infer<typeof comparison>
const label = {
  scope_changed: "The selected filters or history scope changed",
  captured_content_changed: "The captured evidence or review content changed",
  same_captured_content: "The captured evidence and review content match",
}

export function LedgerExportComparison({ caseId }: { caseId: string }) {
  const [before, setBefore] = useState<File | null>(null),
    [after, setAfter] = useState<File | null>(null)
  const [result, setResult] = useState<Result | null>(null),
    [raw, setRaw] = useState("")
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("")
  const request = useRef<AbortController | null>(null)
  useEffect(() => () => request.current?.abort(), [])
  const changed = () => {
    request.current?.abort()
    setResult(null)
    setRaw("")
    setError("")
  }
  const compare = async () => {
    if (!before || !after || request.current) return
    if ([before, after].some((file) => file.size > 128 * 1024 * 1024)) {
      setError("Each export must be no larger than 128 MiB.")
      return
    }
    const controller = new AbortController()
    request.current = controller
    setBusy(true)
    setError("")
    setResult(null)
    setRaw("")
    let timedOut = false
    const timeout = setTimeout(() => {
      timedOut = true
      controller.abort()
    }, 120000)
    try {
      const body = new FormData()
      body.set("before", before)
      body.set("after", after)
      const token = localStorage.getItem("authToken")
      const response = await fetch(
        candidateUrl("ledger-export-comparison", caseId),
        {
          method: "POST",
          body,
          credentials: "include",
          signal: controller.signal,
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        }
      )
      if (!response.ok) {
        const problem = await response.json().catch(() => null)
        throw new Error(
          typeof problem?.detail === "string"
            ? problem.detail
            : "Exports could not be compared."
        )
      }
      const text = await response.text()
      if (new TextEncoder().encode(text).length > 16 * 1024 * 1024)
        throw new Error("Comparison report exceeds the display limit.")
      const parsed = comparison.parse(JSON.parse(text))
      if (parsed.case_id !== caseId)
        throw new Error("Comparison returned for a different case.")
      if (!controller.signal.aborted) {
        setResult(parsed)
        setRaw(text)
      }
    } catch (e) {
      if (timedOut)
        setError("Export comparison timed out. Try smaller exports.")
      else if (!controller.signal.aborted)
        setError(e instanceof Error ? e.message : "Comparison failed.")
    } finally {
      clearTimeout(timeout)
      if (request.current === controller) {
        request.current = null
        setBusy(false)
      }
    }
  }
  const download = () => {
    const url = URL.createObjectURL(
      new Blob([raw], { type: "application/json" })
    )
    const link = document.createElement("a")
    link.href = url
    link.download = "loupe-export-comparison.json"
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return (
    <details className="space-y-2 rounded border p-3">
      <summary>Compare saved ledger exports</summary>
      <p className="text-sm">
        Choose two Loupe export ZIPs from this case. Their captured records and
        file hashes are checked on the server; the files are not added to case
        evidence. Current ledger data is not changed.
      </p>
      <label className="block text-sm">
        Earlier ledger export
        <input
          type="file"
          accept=".zip,application/zip"
          disabled={busy}
          onChange={(e) => {
            changed()
            setBefore(e.target.files?.[0] ?? null)
          }}
        />
      </label>
      <label className="block text-sm">
        Later ledger export
        <input
          type="file"
          accept=".zip,application/zip"
          disabled={busy}
          onChange={(e) => {
            changed()
            setAfter(e.target.files?.[0] ?? null)
          }}
        />
      </label>
      <Button
        variant="outline"
        disabled={busy || !before || !after}
        onClick={() => void compare()}
      >
        {busy ? "Comparing saved exports…" : "Compare captured exports"}
      </Button>
      {error && <p role="alert">{error}</p>}
      {result && (
        <section aria-label="Saved export comparison" className="space-y-2">
          <p>{label[result.status]}.</p>
          {result.status === "scope_changed" && (
            <p>
              Different filters can change which readings appear without an edit
              to the evidence. Check the captured scopes in the comparison
              download.
            </p>
          )}
          <p>
            Readings: {result.readings.added.length} added to this capture,{" "}
            {result.readings.removed.length} absent from this capture,{" "}
            {result.readings.changed.length} changed.
          </p>
          <p>
            Recorded decisions: {result.decisions.added.length} added,{" "}
            {result.decisions.removed.length} absent,{" "}
            {result.decisions.changed.length} changed.
          </p>
          <p>
            Export preparation{" "}
            {result.export_preparation_changed ? "changed" : "matches"}. File
            packaging or generation metadata{" "}
            {result.packaging_or_generation_changed ? "changed" : "matches"}.
          </p>
          {result.readings.changed.length > 0 && (
            <details>
              <summary>Changed reading references (first 20)</summary>
              <ul>
                {result.readings.changed.slice(0, 20).map((row) => (
                  <li key={row.id} className="break-all">
                    {row.id}: {row.changed_path_count} changed captured fields.
                  </li>
                ))}
              </ul>
            </details>
          )}
          <p className="text-sm">{result.limitation}</p>
          <Button variant="outline" onClick={download}>
            Download full export comparison
          </Button>
        </section>
      )}
    </details>
  )
}
