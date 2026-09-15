import { useCallback, useEffect, useRef, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"

/** Keep manually calculated results separate from refreshed case payments. */
export function useAnalysisFreshness(caseId: string) {
  const client = useQueryClient()
  const revision = useRef(0)
  const started = useRef(false)
  const [stale, setStale] = useState(false)
  // A disabled cache entry receives the same case-scoped invalidations as the
  // payment queries, even when the transaction table has not been opened.
  // It makes no request and carries no financial values.
  useQuery({
    queryKey: ["financial-ledger", caseId, "manual-analysis-refresh"],
    queryFn: () => null,
    enabled: false,
  })
  useEffect(() => {
    return client.getQueryCache().subscribe((event) => {
      if (
        event.type === "updated" &&
        event.action.type === "invalidate" &&
        event.query.queryKey[0] === "financial-ledger" &&
        event.query.queryKey[1] === caseId &&
        event.query.queryKey[2] === "manual-analysis-refresh"
      ) {
        revision.current++
        if (started.current) setStale(true)
      }
    })
  }, [client, caseId])
  const beginRead = useCallback(() => {
    const version = revision.current
    started.current = true
    setStale(false)
    // Permit the next invalidation to signal another change. Other open tools
    // retain their own stale state until their user reloads their inputs.
    client.setQueryData(
      ["financial-ledger", caseId, "manual-analysis-refresh"],
      null
    )
    return () => {
      if (revision.current !== version)
        throw Error(
          "Payments may have changed while loading. Load them again before continuing."
        )
    }
  }, [client, caseId])
  return { stale, beginRead }
}
