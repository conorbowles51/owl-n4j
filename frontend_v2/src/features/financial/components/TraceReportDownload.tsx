import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import {
  renderTraceReport,
  type TraceReportMarking,
  type VerifiedTrace,
} from "../lib/trace-report"
export function TraceReportDownload({ trace }: { trace: VerifiedTrace }) {
  const [marking, setMarking] = useState<TraceReportMarking>("unmarked")
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("")
  const active = useRef(true),
    locked = useRef(false)
  useEffect(() => {
    active.current = true
    return () => {
      active.current = false
    }
  }, [])
  const download = async () => {
    if (locked.current) return
    locked.current = true
    setBusy(true)
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
      if (active.current) setBusy(false)
    }
  }
  return (
    <div className="space-y-2">
      <label className="flex items-center gap-2 text-sm">
        Tracing report marking
        <select
          disabled={busy}
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
      <Button variant="outline" disabled={busy} onClick={() => void download()}>
        {busy
          ? "Preparing readable report…"
          : "Download readable tracing report"}
      </Button>
      <p className="text-sm">
        Includes method comparisons, captured assumptions and the source audit.
        Keep the original scenario JSON alongside it.
      </p>
      {error && <p role="alert">{error}</p>}
    </div>
  )
}
