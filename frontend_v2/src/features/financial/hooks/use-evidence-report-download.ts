import { useCallback, useEffect, useRef, useState } from "react"

export function useEvidenceReportDownload(caseId: string | undefined) {
  const [status, setStatus] = useState({ caseId, busy: false, error: "" })
  const request = useRef<AbortController | null>(null)
  const generation = useRef(0)
  useEffect(() => {
    const version = ++generation.current
    return () => {
      generation.current = version + 1
      request.current?.abort()
      request.current = null
    }
  }, [caseId])
  const download = useCallback(
    async (params: URLSearchParams) => {
      if (!caseId || request.current) return
      const version = generation.current
      const controller = new AbortController()
      const token = localStorage.getItem("authToken")
      request.current = controller
      setStatus({ caseId, busy: true, error: "" })
      const timeout = window.setTimeout(() => controller.abort(), 120000)
      try {
        const response = await fetch(`/api/financial/export/pdf?${params}`, {
          credentials: "include",
          signal: controller.signal,
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        })
        if (!response.ok) {
          const failure = await response.json().catch(() => null)
          throw Error(
            typeof failure?.detail === "string"
              ? failure.detail
              : `The report could not be downloaded (${response.status}).`
          )
        }
        const type = response.headers.get("content-type")?.split(";")[0]
        if (type !== "application/pdf" && type !== "text/html")
          throw Error("The server did not return a report. Try again.")
        const limit = 64 * 1024 * 1024
        if (Number(response.headers.get("content-length")) > limit) {
          await response.body?.cancel()
          throw Error(
            "The report is too large. Narrow the filters and download again."
          )
        }
        const reader = response.body?.getReader()
        if (!reader) throw Error("The report could not be read. Try again.")
        const chunks: Uint8Array<ArrayBuffer>[] = []
        let size = 0
        try {
          while (true) {
            const { done, value } = await reader.read()
            if (done) break
            size += value.byteLength
            if (size > limit)
              throw Error(
                "The report is too large. Narrow the filters and download again."
              )
            chunks.push(new Uint8Array(value))
          }
        } finally {
          await reader.cancel().catch(() => {})
          reader.releaseLock()
        }
        if (!size) throw Error("The returned report was empty. Try again.")
        if (
          version !== generation.current ||
          controller.signal.aborted ||
          localStorage.getItem("authToken") !== token
        )
          return
        const url = URL.createObjectURL(new Blob(chunks, { type }))
        const link = document.createElement("a")
        link.href = url
        link.download = `financial-records-${caseId}.${type === "application/pdf" ? "pdf" : "html"}`
        link.click()
        window.setTimeout(() => URL.revokeObjectURL(url), 1000)
      } catch (cause) {
        if (version === generation.current)
          setStatus({
            caseId,
            busy: false,
            error: controller.signal.aborted
              ? "The report took too long. Narrow the filters or try again."
              : cause instanceof Error
                ? cause.message
                : "The report could not be downloaded. Try again.",
          })
      } finally {
        window.clearTimeout(timeout)
        if (request.current === controller) request.current = null
        if (version === generation.current)
          setStatus((current) => ({ ...current, busy: false }))
      }
    },
    [caseId]
  )
  return {
    download,
    busy: status.caseId === caseId && status.busy,
    error: status.caseId === caseId ? status.error : "",
  }
}
