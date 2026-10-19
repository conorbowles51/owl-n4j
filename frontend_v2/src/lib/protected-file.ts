import { useEffect, useState } from "react"

function authHeaders(token: string | null): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function fetchProtectedBlob(
  url: string,
  signal?: AbortSignal
): Promise<Blob> {
  const token = localStorage.getItem("authToken")
  const response = await fetch(url, {
    headers: authHeaders(token),
    credentials: "include",
    signal,
  })

  if (!response.ok) {
    throw new Error(`File request failed: ${response.status}`)
  }

  const blob = await response.blob()
  if (signal?.aborted)
    throw new DOMException("File request was cancelled", "AbortError")
  if (localStorage.getItem("authToken") !== token)
    throw new Error("Your sign-in changed. Open this file again.")
  return blob
}

export function useProtectedObjectUrl(
  url: string | null | undefined,
  enabled = true
) {
  const activeUrl = enabled ? (url ?? null) : null
  const token = localStorage.getItem("authToken")
  const [result, setResult] = useState<{
    url: string
    token: string | null
    objectUrl: string | null
    error: Error | null
  } | null>(null)

  useEffect(() => {
    if (!activeUrl) {
      setResult(null)
      return
    }

    const controller = new AbortController()
    let nextObjectUrl: string | null = null

    fetchProtectedBlob(activeUrl, controller.signal)
      .then((blob) => {
        if (
          controller.signal.aborted ||
          localStorage.getItem("authToken") !== token
        )
          return
        nextObjectUrl = URL.createObjectURL(blob)
        setResult({
          url: activeUrl,
          token,
          objectUrl: nextObjectUrl,
          error: null,
        })
      })
      .catch((err: unknown) => {
        if (
          controller.signal.aborted ||
          localStorage.getItem("authToken") !== token
        )
          return
        setResult({
          url: activeUrl,
          token,
          objectUrl: null,
          error: err instanceof Error ? err : new Error("Failed to load file"),
        })
      })

    return () => {
      controller.abort()
      if (nextObjectUrl) URL.revokeObjectURL(nextObjectUrl)
    }
  }, [activeUrl, token])

  const hasCurrentResult = Boolean(
    activeUrl && result?.url === activeUrl && result.token === token
  )
  const objectUrl = hasCurrentResult ? (result?.objectUrl ?? null) : null
  const error = hasCurrentResult ? (result?.error ?? null) : null
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

export async function openProtectedFile(url: string, page?: number) {
  const targetWindow = window.open("", "_blank")
  if (!targetWindow)
    throw new Error(
      "Your browser blocked the new tab. Allow pop-ups for Loupe, then try again. Your work is kept here."
    )
  targetWindow.opener = null

  try {
    const blob = await fetchProtectedBlob(url)
    const objectUrl = URL.createObjectURL(blob)
    targetWindow.location.href =
      objectUrl +
      (page && Number.isInteger(page) && page > 0 ? `#page=${page}` : "")
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000)
  } catch (err) {
    targetWindow?.close()
    throw err
  }
}
