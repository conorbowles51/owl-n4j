import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { candidateUrl } from "../lib/candidate-contract"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"

export function LedgerExportButton({
  caseId,
  params,
}: {
  caseId: string
  params: LedgerQueryParams
}) {
  return (
    <ScopedExport
      key={JSON.stringify([
        caseId,
        params.accountId,
        params.startDate,
        params.endDate,
      ])}
      caseId={caseId}
      params={params}
    />
  )
}
function ScopedExport({
  caseId,
  params,
}: {
  caseId: string
  params: LedgerQueryParams
}) {
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState("")
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
      if (params.accountId) search.set("account_id", params.accountId)
      if (params.startDate) search.set("start_date", params.startDate)
      if (params.endDate) search.set("end_date", params.endDate)
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
        response.headers.get("content-type")?.split(";")[0] !==
          "application/zip" ||
        response.headers.get("X-Loupe-Case-Id") !== caseId ||
        response.headers.get("X-Loupe-Account-Id") !==
          (params.accountId ?? "") ||
        response.headers.get("X-Loupe-Start-Date") !==
          (params.startDate ?? "") ||
        response.headers.get("X-Loupe-End-Date") !== (params.endDate ?? "")
      )
        throw new Error(
          "Export returned for different filters or in an unexpected format."
        )
      const blob = await response.blob()
      if (controller.signal.aborted) return
      const url = URL.createObjectURL(blob),
        link = document.createElement("a")
      link.href = url
      link.download = "loupe-ledger-export.zip"
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
  return (
    <section
      className="space-y-2 rounded border p-3"
      aria-label="Export ledger analysis"
    >
      <Button disabled={busy} onClick={() => void download()}>
        {busy ? "Preparing ledger export…" : "Download ledger snapshot"}
      </Button>
      <p>
        Downloads the applied account/date scope, exact rows and totals, source
        references and relevant decision history with a verification manifest.
        Original source files and structured PDF review history are not bundled.
        Recorded source hashes are not fresh file checks.
      </p>
      {message && <p role="status">{message}</p>}
    </section>
  )
}
