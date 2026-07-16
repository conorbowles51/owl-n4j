import { useEffect, useState } from "react"

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("authToken")
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export class ProtectedFileError extends Error {
  status: number
  detail: unknown

  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `File request failed: ${status}`)
    this.name = "ProtectedFileError"
    this.status = status
    this.detail = detail
  }
}

export async function fetchProtectedBlob(
  url: string,
  signal?: AbortSignal
): Promise<Blob> {
  const response = await fetch(url, {
    headers: authHeaders(),
    credentials: "include",
    signal,
  })

  if (!response.ok) {
    let detail: unknown = null
    try {
      const body = await response.json()
      detail = body?.detail ?? body
    } catch {
      detail = `File request failed: ${response.status}`
    }
    throw new ProtectedFileError(response.status, detail)
  }

  return response.blob()
}

export function useProtectedObjectUrl(
  url: string | null | undefined,
  enabled = true
) {
  const activeUrl = enabled ? url ?? null : null
  const [result, setResult] = useState<{
    url: string
    objectUrl: string | null
    error: Error | null
  } | null>(null)

  useEffect(() => {
    if (!activeUrl) return

    const controller = new AbortController()
    let nextObjectUrl: string | null = null

    fetchProtectedBlob(activeUrl, controller.signal)
      .then((blob) => {
        nextObjectUrl = URL.createObjectURL(blob)
        setResult({ url: activeUrl, objectUrl: nextObjectUrl, error: null })
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setResult({
          url: activeUrl,
          objectUrl: null,
          error: err instanceof Error ? err : new Error("Failed to load file"),
        })
      })

    return () => {
      controller.abort()
      if (nextObjectUrl) URL.revokeObjectURL(nextObjectUrl)
    }
  }, [activeUrl])

  const hasCurrentResult = Boolean(activeUrl && result?.url === activeUrl)
  const objectUrl = hasCurrentResult ? result?.objectUrl ?? null : null
  const error = hasCurrentResult ? result?.error ?? null : null
  const loading = Boolean(activeUrl && !hasCurrentResult)
  return { objectUrl, loading, error }
}

export async function downloadProtectedFile(url: string, filename: string) {
  const blob = await fetchProtectedBlob(url)
  const objectUrl = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = objectUrl
  anchor.download = filename || "download"
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
}

export async function openProtectedFile(url: string) {
  const targetWindow = window.open("", "_blank")
  if (targetWindow) targetWindow.opener = null

  try {
    const blob = await fetchProtectedBlob(url)
    const objectUrl = URL.createObjectURL(blob)
    if (targetWindow) {
      targetWindow.location.href = objectUrl
    } else {
      window.open(objectUrl, "_blank", "noopener,noreferrer")
    }
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000)
  } catch (err) {
    targetWindow?.close()
    throw err
  }
}
