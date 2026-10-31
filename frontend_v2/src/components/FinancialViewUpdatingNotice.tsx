import { useEffect, useRef, useSyncExternalStore } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useMatch } from "react-router-dom"
import { RefreshCw } from "lucide-react"
import { fetchAPI } from "@/lib/api-client"
import {
  noteViewAnswer,
  nextRequestNumber,
  subscribeUpdatingViews,
  updatingViews,
} from "@/lib/financial-view-updates"

/** How often the views answered as updating are asked for again until they answer current. */
export const UPDATING_POLL_MS = 5000

function asOfText(asOf: string) {
  const time = asOf ? new Date(asOf) : null
  return time && !Number.isNaN(time.getTime())
    ? time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : "an earlier time"
}

/**
 * Says plainly, on every page, that figures shown are a previous copy being recomputed after a change
 * (lib/financial-view-updates.ts), and asks for those views again until they answer current; the page's queries
 * are then refetched, so the current figures replace the previous ones.
 */
export function FinancialViewUpdatingNotice() {
  const views = useSyncExternalStore(subscribeUpdatingViews, updatingViews)
  const caseId = useMatch("/cases/:id/*")?.params.id
  const queryClient = useQueryClient()
  const shown = [...views].filter(([endpoint]) => !caseId || endpoint.includes(caseId))
  const endpoints = shown.map(([endpoint]) => endpoint).sort().join("\n")
  const polling = useRef(false)

  useEffect(() => {
    if (!endpoints) return
    const controller = new AbortController()
    const timer = window.setInterval(async () => {
      if (polling.current) return
      polling.current = true
      try {
        const current: string[] = []
        for (const endpoint of endpoints.split("\n")) {
          if (controller.signal.aborted) return
          const request = nextRequestNumber()
          let asOf: string | undefined = ""
          try {
            await fetchAPI(endpoint, { signal: controller.signal, onViewAnswer: (value) => (asOf = value) })
          } catch {
            // A refusal is answered like any view; the page's own query shows it once fetched again.
          }
          if (asOf === undefined) current.push(endpoint)
          else if (asOf) noteViewAnswer(endpoint, asOf, request)
        }
        if (current.length === 0 || controller.signal.aborted) return
        // The page's copies are replaced before the notice goes: queries not on screen are dropped (fetched anew
        // when shown), those on screen are fetched again and awaited. Only then is the address recorded current.
        const started = nextRequestNumber()
        queryClient.removeQueries({ type: "inactive" })
        await queryClient.refetchQueries({ type: "active" })
        for (const endpoint of current) noteViewAnswer(endpoint, undefined, started)
      } finally {
        polling.current = false
      }
    }, UPDATING_POLL_MS)
    return () => {
      controller.abort()
      window.clearInterval(timer)
    }
  }, [endpoints, queryClient])

  if (shown.length === 0) return null
  const earliest = shown.map(([, asOf]) => asOf).sort()[0]
  return (
    <div
      role="status"
      data-testid="financial-view-updating"
      className="fixed bottom-4 left-1/2 z-50 flex max-w-xl -translate-x-1/2 items-start gap-2 rounded-md border border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-950 shadow-lg dark:border-amber-700 dark:bg-amber-950 dark:text-amber-50"
    >
      <RefreshCw aria-hidden="true" className="mt-0.5 size-4 shrink-0 animate-spin" />
      <span>
        Updating after a recent change. Some figures on this page are from {asOfText(earliest)} and are being
        recomputed; they refresh here automatically.
      </span>
    </div>
  )
}
