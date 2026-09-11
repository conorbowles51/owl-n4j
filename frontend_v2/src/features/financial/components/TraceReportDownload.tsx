import { sha256Hex } from "@/lib/browser-crypto"
import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { candidateUrl } from "../lib/candidate-contract"
import {
  renderTraceReport,
  type TraceReportMarking,
  type VerifiedTrace,
} from "../lib/trace-report"
export function TraceReportDownload({ trace }: { trace: VerifiedTrace }) {
  const [marking, setMarking] = useState<TraceReportMarking>("unmarked")
  const [busy, setBusy] = useState<"report" | "audit" | null>(null),
    [error, setError] = useState("")
  const active = useRef(true),
    locked = useRef(false)
  const request = useRef<AbortController | null>(null)
  useEffect(() => {
    active.current = true
    return () => {
      active.current = false
      request.current?.abort()
    }
  }, [])
  const download = async () => {
    if (locked.current) return
    locked.current = true
    setBusy("report")
    setError("")
    try {
      const html = await renderTraceReport(trace, marking)
      if (!active.current) return
      const url = URL.createObjectURL(
        new Blob([html], { type: "text/html;charset=utf-8" })
      )
      const link = document.createElement("a")
      link.href = url
      link.download = "loupe-conditional-tracing-report.html"
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) {
      if (active.current)
        setError(e instanceof Error ? e.message : "Report creation failed.")
    } finally {
      locked.current = false
      if (active.current) setBusy(null)
    }
  }
  const downloadAudit = async () => {
    if (locked.current) return
    locked.current = true
    setBusy("audit")
    setError("")
    const controller = new AbortController()
    request.current = controller
    const timeout = setTimeout(() => controller.abort(), 120000)
    try {
      const token = localStorage.getItem("authToken")
      const response = await fetch(
        candidateUrl("trace-support-export", trace.envelope.case_id),
        {
          method: "POST",
          credentials: "include",
          signal: controller.signal,
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            scenarios: [trace.envelope.scenario_json],
            privilege_marking: marking,
          }),
        }
      )
      if (!response.ok)
        throw new Error(
          "Tracing audit bundle could not be prepared. The captured scenario may differ from recalculation."
        )
      if (
        response.headers.get("content-type")?.split(";")[0] !==
          "application/zip" ||
        response.headers.get("X-Loupe-Case-Id") !== trace.envelope.case_id ||
        response.headers.get("X-Loupe-Privilege-Marking") !== marking ||
        response.headers.get("X-Loupe-Scenario-Sha256") !==
          trace.envelope.scenario_sha256
      )
        throw new Error(
          "Tracing audit returned for a different scenario or marking."
        )
      const bytes = await response.arrayBuffer()
      if (bytes.byteLength > 64 * 1024 * 1024)
        throw new Error("Tracing audit exceeds the download limit.")
      const digest = await sha256Hex(bytes)
      if (digest !== response.headers.get("X-Loupe-Archive-Sha256"))
        throw new Error("Tracing audit integrity check failed.")
      if (!active.current || controller.signal.aborted) return
      const url = URL.createObjectURL(
        new Blob([bytes], { type: "application/zip" })
      )
      const link = document.createElement("a")
      link.href = url
      link.download = "loupe-tracing-audit.zip"
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) {
      if (active.current)
        setError(
          controller.signal.aborted
            ? "Tracing audit download timed out. Try again."
            : e instanceof Error
              ? e.message
              : "Tracing audit download failed."
        )
    } finally {
      clearTimeout(timeout)
      request.current = null
      locked.current = false
      if (active.current) setBusy(null)
    }
  }
  return (
    <div className="space-y-2">
      <label className="flex items-center gap-2 text-sm">
        Tracing report marking
        <select
          disabled={busy !== null}
          value={marking}
          onChange={(e) => setMarking(e.target.value as TraceReportMarking)}
        >
          <option value="unmarked">No privilege marking</option>
          <option value="confidential">Confidential</option>
          <option value="privileged_confidential">
            Privileged and confidential
          </option>
        </select>
      </label>
      <Button
        variant="outline"
        disabled={busy !== null}
        onClick={() => void download()}
      >
        {busy === "report"
          ? "Preparing readable report…"
          : "Download readable tracing report"}
      </Button>
      <Button
        variant="outline"
        disabled={busy !== null}
        onClick={() => void downloadAudit()}
      >
        {busy === "audit"
          ? "Preparing tracing audit…"
          : "Download tracing audit bundle"}
      </Button>
      <p className="text-sm">
        Includes method comparisons, captured assumptions and the source audit.
        Keep the original scenario JSON alongside it. The audit bundle also
        includes a recalculation check and recorded processing history. It
        covers this scenario, not the complete case history.
      </p>
      {error && <p role="alert">{error}</p>}
    </div>
  )
}
