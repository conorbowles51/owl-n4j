import { useEffect, useState } from "react"
import { mediaObjectUrl } from "../api"

/** A file's bytes shown in the page, fetched only when asked for (visible, or opened). */
export function useObjectUrl(caseId: string, fileUid: string | null, enabled: boolean, variant: "content" | "thumbnail" | "converted" = "content") {
  const [state, setState] = useState<{ url: string; type: string } | { error: string } | null>(null)
  useEffect(() => {
    if (!fileUid || !enabled) return
    const ctrl = new AbortController()
    let made: string | null = null
    mediaObjectUrl(caseId, fileUid, ctrl.signal, variant)
      .then((r) => {
        made = r.url
        setState(r)
      })
      .catch((e: unknown) => {
        if (!ctrl.signal.aborted) setState({ error: e instanceof Error ? e.message : "This file could not be shown." })
      })
    return () => {
      ctrl.abort()
      if (made) URL.revokeObjectURL(made)
      setState(null)
    }
  }, [caseId, fileUid, enabled, variant])
  return state
}
