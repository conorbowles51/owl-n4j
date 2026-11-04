import { useRef, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { CheckCircle2, MapPinOff, Search } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { ApiError } from "@/lib/api-client"
import { useGraphStore } from "@/stores/graph.store"
import { graphAPI } from "@/features/graph/api"
import { useMapStore } from "../stores/map.store"
import { useMapReviewQueue, type MapLocation } from "../hooks/use-map-data"
import {
  CONFIDENCE_TIER_BADGE_VARIANTS,
  CONFIDENCE_TIER_LABELS,
  canLookUp,
  getConfidenceTier,
  isUnconfirmedLookup,
  needsReview,
  reviewReason,
} from "@/lib/location-confidence"

interface NeedsReviewPanelProps {
  caseId: string
  locations: MapLocation[]
}

/** Addresses sent per request: the server sends one a second, so each request answers in about this many seconds. */
export const LOOKUP_CHUNK = 10
export const LOOKUP_SERVICE_WORDS = "the OpenStreetMap address service (outside this server)"

function lookupFailureWords(err: unknown): string {
  if (err instanceof ApiError && err.status === 403) {
    return "You can view this case but not change it, so its addresses cannot be looked up."
  }
  return `Look up stopped: ${err instanceof Error ? err.message : "the server did not answer"}`
}

function formatWhen(value?: string | null) {
  if (!value) return ""
  const when = new Date(value)
  return Number.isNaN(when.getTime()) ? value : when.toLocaleString()
}

/**
 * Review queue for the needs-review mode: low-confidence pins, pins placed by an address lookup and not yet
 * confirmed, and locations flagged at ingestion (which have no pin). Selecting an item opens the shared detail
 * panel, from which the relocate flow is reachable.
 *
 * Addresses from evidence are never sent anywhere on their own: a flagged address goes to the address service only
 * when a person clicks Look up (one address) or Look up all (each flagged address, one a second, with progress and
 * Stop). What a lookup places is a machine placement, shown "not confirmed" until a person confirms or moves it.
 */
export function NeedsReviewPanel({ caseId, locations }: NeedsReviewPanelProps) {
  const { data: flaggedQueue } = useMapReviewQueue(caseId)
  const selectNodes = useGraphStore((s) => s.selectNodes)
  const flyTo = useMapStore((s) => s.flyTo)
  const queryClient = useQueryClient()

  const [outcomes, setOutcomes] = useState<Record<string, string>>({})
  const [busyKeys, setBusyKeys] = useState<Set<string>>(new Set())
  const [askingAll, setAskingAll] = useState(false)
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null)
  const [summary, setSummary] = useState<string | null>(null)
  const stopRef = useRef(false)

  const reviewPins = locations.filter(needsReview)
  const flagged = (flaggedQueue ?? []).filter(needsReview)
  const lookable = flagged.filter(canLookUp)
  const total = reviewPins.length + flagged.length
  const running = progress !== null

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["map"] })

  const lookUp = async (keys: string[]) => {
    const result = await graphAPI.lookUpFlaggedAddresses(caseId, keys)
    setOutcomes((current) => {
      const next = { ...current }
      for (const item of result.results) next[item.key] = item.message
      return next
    })
    return result.counts
  }

  const lookUpOne = async (key: string) => {
    setBusyKeys((current) => new Set(current).add(key))
    try {
      await lookUp([key])
      await refresh()
    } catch (err) {
      setOutcomes((current) => ({ ...current, [key]: lookupFailureWords(err) }))
    } finally {
      setBusyKeys((current) => {
        const next = new Set(current)
        next.delete(key)
        return next
      })
    }
  }

  const lookUpAll = async () => {
    const keys = lookable.map((item) => item.key)
    setAskingAll(false)
    setSummary(null)
    stopRef.current = false
    setProgress({ done: 0, total: keys.length })
    const counts: Record<string, number> = {}
    let done = 0
    let stoppedWith: string | null = null
    for (let start = 0; start < keys.length; start += LOOKUP_CHUNK) {
      if (stopRef.current) break
      const chunk = keys.slice(start, start + LOOKUP_CHUNK)
      try {
        const chunkCounts = await lookUp(chunk)
        for (const [outcome, n] of Object.entries(chunkCounts)) counts[outcome] = (counts[outcome] ?? 0) + n
      } catch (err) {
        stoppedWith = lookupFailureWords(err)
        break
      }
      done += chunk.length
      setProgress({ done, total: keys.length })
      void refresh()
    }
    setProgress(null)
    const parts = [
      `${counts.placed ?? 0} placed (not confirmed)`,
      `${counts.no_match ?? 0} no match`,
      counts.unavailable ? `${counts.unavailable} not answered` : null,
      counts.skipped ? `${counts.skipped} skipped` : null,
    ].filter(Boolean)
    const head = stoppedWith ?? (stopRef.current ? `Stopped after ${done} of ${keys.length}` : `Looked up ${done}`)
    setSummary(`${head}: ${parts.join(", ")}.`)
    await refresh()
  }

  const confirm = async (key: string) => {
    setBusyKeys((current) => new Set(current).add(key))
    try {
      await graphAPI.confirmLookedUpLocation(key, caseId)
      setOutcomes((current) => ({ ...current, [key]: "Confirmed" }))
      await refresh()
    } catch (err) {
      setOutcomes((current) => ({
        ...current,
        [key]:
          err instanceof ApiError && err.status === 403
            ? "You can view this case but not change it."
            : `Not confirmed: ${err instanceof Error ? err.message : "the server did not answer"}`,
      }))
    } finally {
      setBusyKeys((current) => {
        const next = new Set(current)
        next.delete(key)
        return next
      })
    }
  }

  const minutes = Math.max(1, Math.ceil(lookable.length / 60))

  return (
    <div className="absolute right-3 top-14 z-10 flex max-h-[60%] w-80 flex-col rounded-lg border border-border bg-card/95 shadow-md backdrop-blur">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Needs review
        </span>
        <Badge variant="amber" className="ml-auto text-[9px]">
          {total}
        </Badge>
      </div>

      {(lookable.length > 0 || running || summary) && (
        <div className="space-y-1 border-b border-border px-3 py-2 text-[10px] text-muted-foreground">
          {running ? (
            <div className="flex items-center gap-2" role="status">
              <span>
                Looking up {progress.done} of {progress.total} addresses, one a second…
              </span>
              <button
                type="button"
                onClick={() => {
                  stopRef.current = true
                }}
                className="ml-auto rounded border border-border px-1.5 py-0.5 text-foreground hover:bg-muted"
              >
                Stop
              </button>
            </div>
          ) : askingAll ? (
            <div className="space-y-1">
              <p>
                Sends {lookable.length} address{lookable.length === 1 ? "" : "es"} from this case to{" "}
                {LOOKUP_SERVICE_WORDS}, one a second (about {minutes} min). Pins it finds are marked not confirmed.
              </p>
              <div className="flex gap-1.5">
                <button
                  type="button"
                  onClick={() => void lookUpAll()}
                  className="rounded border border-border bg-primary px-1.5 py-0.5 text-primary-foreground"
                >
                  Send {lookable.length}
                </button>
                <button
                  type="button"
                  onClick={() => setAskingAll(false)}
                  className="rounded border border-border px-1.5 py-0.5 text-foreground hover:bg-muted"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            lookable.length > 0 && (
              <div className="flex items-center gap-2">
                <span>{lookable.length} flagged addresses not placed. Nothing is looked up until you ask.</span>
                <button
                  type="button"
                  onClick={() => setAskingAll(true)}
                  className="ml-auto shrink-0 rounded border border-border px-1.5 py-0.5 text-foreground hover:bg-muted"
                >
                  Look up all {lookable.length}
                </button>
              </div>
            )
          )}
          {summary && !running && <p role="status">{summary}</p>}
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-1.5">
        {total === 0 && (
          <p className="px-2 py-3 text-center text-[11px] text-muted-foreground">
            No locations need review
          </p>
        )}

        {reviewPins.map((loc) => {
          const lookedUp = isUnconfirmedLookup(loc)
          return (
            <div key={loc.key} className="flex items-start gap-1 rounded-md hover:bg-muted">
              <button
                type="button"
                onClick={() => {
                  selectNodes([loc.key])
                  flyTo({ longitude: loc.longitude, latitude: loc.latitude })
                }}
                className="flex min-w-0 flex-1 flex-col gap-0.5 px-2 py-1.5 text-left"
              >
                <span className="flex items-center gap-1.5">
                  <span className="truncate text-xs font-medium">{loc.name}</span>
                  <Badge
                    variant={lookedUp ? "slate" : CONFIDENCE_TIER_BADGE_VARIANTS[getConfidenceTier(loc)]}
                    className="ml-auto shrink-0 text-[9px]"
                  >
                    {lookedUp ? "Looked up" : CONFIDENCE_TIER_LABELS[getConfidenceTier(loc)]}
                  </Badge>
                </span>
                <span className="truncate text-[10px] text-muted-foreground">
                  {reviewReason(loc)}
                  {loc.location_raw ? ` - "${loc.location_raw}"` : ""}
                </span>
                {lookedUp && (
                  <span className="truncate text-[10px] text-muted-foreground">
                    Asked by {loc.geocoding_requested_by_name || "a person"}
                    {loc.geocoding_requested_at ? ` on ${formatWhen(loc.geocoding_requested_at)}` : ""}
                  </span>
                )}
                {outcomes[loc.key] && <span className="text-[10px] text-foreground">{outcomes[loc.key]}</span>}
              </button>
              {lookedUp && (
                <button
                  type="button"
                  disabled={busyKeys.has(loc.key)}
                  onClick={() => void confirm(loc.key)}
                  title="Confirm this pin is where the address is; it then counts as placed by you"
                  className="mt-1.5 mr-1 flex shrink-0 items-center gap-1 rounded border border-border px-1.5 py-0.5 text-[10px] hover:bg-background disabled:opacity-50"
                >
                  <CheckCircle2 className="size-3" />
                  Confirm
                </button>
              )}
            </div>
          )
        })}

        {flagged.map((item) => (
          <div key={item.key} className="flex items-start gap-1 rounded-md hover:bg-muted">
            <button
              type="button"
              onClick={() => selectNodes([item.key])}
              className="flex min-w-0 flex-1 flex-col gap-0.5 px-2 py-1.5 text-left"
            >
              <span className="flex items-center gap-1.5">
                <MapPinOff className="size-3 shrink-0 text-muted-foreground" />
                <span className="truncate text-xs font-medium">{item.name}</span>
                <Badge
                  variant={CONFIDENCE_TIER_BADGE_VARIANTS[getConfidenceTier(item)]}
                  className="ml-auto shrink-0 text-[9px]"
                >
                  {CONFIDENCE_TIER_LABELS[getConfidenceTier(item)]}
                </Badge>
              </span>
              <span className="truncate text-[10px] text-muted-foreground">
                {reviewReason(item)}
                {item.location_raw ? ` - "${item.location_raw}"` : ""} - no pin
              </span>
              {outcomes[item.key] && <span className="text-[10px] text-foreground">{outcomes[item.key]}</span>}
            </button>
            {canLookUp(item) && (
              <button
                type="button"
                disabled={busyKeys.has(item.key) || running}
                onClick={() => void lookUpOne(item.key)}
                title={`Sends this address to ${LOOKUP_SERVICE_WORDS}`}
                className="mt-1.5 mr-1 flex shrink-0 items-center gap-1 rounded border border-border px-1.5 py-0.5 text-[10px] hover:bg-background disabled:opacity-50"
              >
                <Search className="size-3" />
                {busyKeys.has(item.key) ? "Looking up…" : "Look up"}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
