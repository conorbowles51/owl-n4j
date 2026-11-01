import { useEffect, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { requestsSince, subscribeRequests } from "@/lib/request-progress"
import { whenSettled } from "../lib/page-speed"
import {
  picture,
  recordedMs,
  saveMs,
  seconds,
  sizeWords,
  SHOW_AFTER_MS,
  SLOW_MS,
  STALL_MS,
  TICK_MS,
  unpackWords,
} from "../lib/load-progress"

/**
 * The loading panel for a Financial view: from the moment the view opens until its data is on screen it says in
 * words what is happening now, how far along it is from true counts (parts of the page loaded of parts asked for,
 * and bytes received of the answer's own length when the server gives it) and, when it can be worked out, time
 * left worded as an estimate: from the rate this answer is arriving at, or from how long this view took on this
 * case last time in this browser. It redraws every half second; when nothing has moved for 3 s it says so; past
 * 10 s, or when a part fails, it names that part and offers to try again. The bar never goes backwards and never
 * reaches 100% before the data is shown (the last part is drawing the page). Nothing here runs on a timer alone:
 * every number comes from the reads the page made (lib/request-progress.ts).
 */

export function LoadProgress({ caseId, page }: { caseId: string | undefined; page: string }) {
  if (!caseId) return null
  // A new view or case starts its own count from zero.
  return <ViewLoadProgress key={`${caseId}:${page}`} caseId={caseId} page={page} />
}

function ViewLoadProgress({ caseId, page }: { caseId: string; page: string }) {
  const client = useQueryClient()
  // Taken at first render, before the view's own requests start in their effects.
  const [since] = useState(() => performance.now())
  const [settled, setSettled] = useState(false)
  // Moved only by the tick and by each read's change: the bar's position never goes backwards, and the time the
  // count last moved says when nothing has changed for a while.
  const [clock, setClock] = useState({ now: since, fraction: 0, movedAt: since, done: 0, unpacked: 0 })

  useEffect(() => {
    const signal = { cancelled: false }
    const frame = requestAnimationFrame(() => {
      void whenSettled(client, signal).then((end) => {
        if (end === null || signal.cancelled) return
        if (!requestsSince(since).some((read) => read.failed)) saveMs(caseId, page, end - since)
        setSettled(true)
      })
    })
    return () => {
      signal.cancelled = true
      cancelAnimationFrame(frame)
    }
  }, [caseId, page, since, client])

  const open = !settled
  // After the data is shown only the reads matter (a failed part being asked again); while loading, the tick too.
  const [, setReadsSeen] = useState(0)
  useEffect(() => {
    if (open) return
    return subscribeRequests(() => setReadsSeen((n) => n + 1))
  }, [open])
  useEffect(() => {
    if (!open) return
    const tick = () =>
      setClock((previous) => {
        const view = picture(requestsSince(since))
        const at = performance.now()
        const unpacked = view.unpack?.done ?? 0
        return {
          now: at,
          fraction: Math.min(0.99, Math.max(previous.fraction, view.done / view.total)),
          done: view.done,
          unpacked,
          movedAt: view.done !== previous.done || unpacked !== previous.unpacked ? at : previous.movedAt,
        }
      })
    const timer = setInterval(tick, TICK_MS)
    const unsubscribe = subscribeRequests(tick)
    return () => {
      clearInterval(timer)
      unsubscribe()
    }
  }, [open, since])

  const { now, fraction, movedAt } = clock
  const reads = requestsSince(since)
  const elapsed = now - since
  const view = picture(reads)
  const failures = view.failed
  const retry = () => {
    void client.refetchQueries({ type: "active", predicate: (query) => query.state.status === "error" })
  }

  if (!open) {
    // Data is on screen. A part that failed stays named, with a retry, until it loads.
    if (!failures.length) return null
    return (
      <div role="alert" className="mx-4 my-2 flex flex-wrap items-center gap-3 rounded border border-destructive/40 px-3 py-2 text-sm text-destructive" data-testid="load-progress-failed">
        <span>
          {failures.map((read) => `Loading ${read.what} failed: ${read.failed}.`).join(" ")} The rest of the page is shown.
        </span>
        <Button size="sm" variant="outline" onClick={retry}>Try again</Button>
      </div>
    )
  }

  const percent = Math.floor(fraction * 100)
  const usual = recordedMs(caseId, page)
  const stalled = now - movedAt >= STALL_MS
  const longerThanUsual = usual !== null && elapsed > usual * 1.25 + 1000

  let left: string | null = null
  if (view.bytes && view.current?.answered != null && view.bytes.received > 0) {
    const rate = view.bytes.received / Math.max(1, now - view.current.answered)
    const remaining = (view.bytes.total - view.bytes.received) / rate
    if (Number.isFinite(remaining)) left = `about ${seconds(remaining)} s left for this part`
  } else if (usual !== null && elapsed < usual) {
    left = `about ${seconds(usual - elapsed)} s left (this page took ${seconds(usual)} s last time)`
  }

  if (elapsed < SHOW_AFTER_MS && !failures.length) return null
  const sentence = stalled
    ? `Still ${view.step.charAt(0).toLowerCase()}${view.step.slice(1)}${longerThanUsual ? " — taking longer than usual" : ` — no change for ${seconds(now - movedAt)} s`}`
    : view.step
  const slow = elapsed >= SLOW_MS
  return (
    <div className="mx-4 my-2 rounded border px-3 py-2 text-sm" data-testid="load-progress">
      <p role="status" aria-live="polite" className="flex flex-wrap items-baseline gap-x-2">
        <span className="font-medium">{sentence}…</span>
        {view.bytes && (
          <span>
            {sizeWords(view.bytes.received)} of {sizeWords(view.bytes.total)}
          </span>
        )}
        {view.unpack && <span>{unpackWords(view.unpack)}</span>}
        <span className="text-muted-foreground">
          {view.partsDone} of {view.partsAsked} {view.partsAsked === 1 ? "part" : "parts"} loaded · {percent}% · {seconds(elapsed)} s
          {left && ` · ${left}`}
        </span>
      </p>
      <div
        role="progressbar"
        aria-label="Page loading"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="mt-1.5 h-1.5 w-full overflow-hidden rounded bg-muted"
      >
        <div className="h-full bg-primary transition-[width] duration-300" style={{ width: `${percent}%` }} />
      </div>
      {(failures.length > 0 || slow) && (
        <div role={failures.length ? "alert" : undefined} className="mt-1.5 flex flex-wrap items-center gap-3">
          <span className={failures.length ? "text-destructive" : undefined}>
            {failures.length
              ? failures.map((read) => `Loading ${read.what} failed: ${read.failed}.`).join(" ")
              : `${view.current ? `${view.step} has taken ${seconds(now - view.current.started)} s.` : `This page has taken ${seconds(elapsed)} s.`} You can keep waiting or try again.`}
          </span>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              if (failures.length) return retry()
              // Ask again for every part still loading (a stuck read is dropped and started fresh).
              const loading = client.getQueryCache().findAll({ fetchStatus: "fetching" })
              void Promise.all(loading.map((query) => client.cancelQueries({ queryKey: query.queryKey, exact: true }))).then(() =>
                Promise.all(loading.map((query) => client.refetchQueries({ queryKey: query.queryKey, exact: true })))
              )
            }}
          >
            Try again
          </Button>
        </div>
      )}
    </div>
  )
}
