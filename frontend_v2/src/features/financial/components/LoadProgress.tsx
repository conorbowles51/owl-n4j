import { opensWholeCaseRun } from "../lib/run-refusals"
import { useContext, useEffect, useLayoutEffect, useRef, useState } from "react"
import { QueryClientContext } from "@tanstack/react-query"
import { queryClient } from "@/lib/query-client"
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
  withWork,
  workPending,
  type PageWork,
} from "../lib/load-progress"

/**
 * The loading panel for a Financial view: from the moment the view opens until its data is on screen it says in
 * words what is happening now, how far along it is from true counts (parts of the page loaded of parts asked for,
 * and bytes received of the answer's own length when the server gives it) and, when it can be worked out, time
 * left worded as an estimate: from the rate this answer is arriving at, or from how long this view took on this
 * case last time in this browser. It redraws every half second; when nothing has moved for 3 s it says so; past
 * 10 s, or when a part fails, it names that part and offers to try again. The bar never goes backwards and never
 * reaches 100% before the data is shown (the last part is drawing the page). Nothing here runs on a timer alone:
 * every number comes from the reads the page made (lib/request-progress.ts) and from the steps of the page's own
 * work (`work`, e.g. a large graph being arranged: its true step count), which keeps the panel open until done.
 *
 * `caseId` null: a page that is not one case's (the case list). `since`: when the page opened, for a page that
 * shows the panel in more than one place while it loads (the graph: while its reads run, then over the canvas
 * while it is arranged); the bar keeps its position across them.
 */

interface LoadProgressProps {
  caseId: string | null | undefined
  page: string
  since?: number
  work?: PageWork | null
}

export function LoadProgress({ caseId, page, since, work }: LoadProgressProps) {
  if (caseId === undefined || caseId === "") return null
  const scope = caseId ?? "all"
  // A new view or case starts its own count from zero.
  return <ViewLoadProgress key={`${scope}:${page}:${since ?? ""}`} caseId={scope} page={page} opened={since} work={work ?? null} />
}

// The bar's position per opening (`since`), so a panel shown again for the same opening never starts lower.
const barShown = new Map<number, number>()
// Openings whose panel has closed (their time recorded): a panel mounted again for one (the graph switched from 3D
// back to 2D minutes later) counts afresh from its own mount, without the "last time" estimate and without saving.
const openingsDone = new Set<number>()
// When a mount sharing an opening went away while it was still open. The graph hands its panel from the loading
// view to the canvas in the same moment; a mount for the opening much later (3D chosen mid-layout, 2D again minutes
// on) is a new wait, not the old one.
const openingsLeft = new Map<number, number>()
const HANDOFF_MS = 1000
const openingOver = (opened: number) => {
  const left = openingsLeft.get(opened)
  return openingsDone.has(opened) || (left !== undefined && performance.now() - left > HANDOFF_MS)
}
function keepBar(since: number, fraction: number) {
  barShown.set(since, fraction)
  if (barShown.size > 20) barShown.delete(barShown.keys().next().value as number)
}

interface Clock {
  now: number
  fraction: number
  movedAt: number
  done: number
  unpacked: number
}

function nextClock(previous: Clock, since: number, work: PageWork | null, shared: boolean): Clock {
  const view = withWork(picture(requestsSince(since)), work)
  const at = performance.now()
  const unpacked = view.unpack?.done ?? 0
  const fraction = Math.min(0.99, Math.max(previous.fraction, view.done / view.total))
  if (shared) keepBar(since, fraction)
  return {
    now: at,
    fraction,
    done: view.done,
    unpacked,
    movedAt: view.done !== previous.done || unpacked !== previous.unpacked ? at : previous.movedAt,
  }
}

function ViewLoadProgress({ caseId, page, opened, work }: { caseId: string; page: string; opened?: number; work: PageWork | null }) {
  // The app's own client (app/providers) when a screen is drawn outside its provider (a component test).
  const client = useContext(QueryClientContext) ?? queryClient
  // Taken at first render, before the view's own requests start in their effects.
  // A panel that closed and opens again for new work of the page's own (a graph arranged afresh) counts from then.
  const [fresh] = useState(() => opened !== undefined && openingOver(opened))
  const [since, setSince] = useState(() => (opened !== undefined && !fresh ? opened : performance.now()))
  const [settledAt, setSettledAt] = useState<number | null>(null)
  const settled = settledAt !== null
  // Moved only by the tick and by each read's change: the bar's position never goes backwards, and the time the
  // count last moved says when nothing has changed for a while.
  const [clock, setClock] = useState<Clock>(() => {
    const at = performance.now()
    return { now: at, fraction: (opened !== undefined && !fresh && barShown.get(opened)) || 0, movedAt: at, done: 0, unpacked: 0 }
  })
  const workRef = useRef(work)
  const workSeen = useRef(false)
  useLayoutEffect(() => {
    workRef.current = work
    if (work) workSeen.current = true
  }, [work])

  useEffect(() => {
    const signal = { cancelled: false }
    const frame = requestAnimationFrame(() => {
      void whenSettled(client, signal).then((end) => {
        if (end === null || signal.cancelled) return
        setSettledAt(end)
      })
    })
    return () => {
      signal.cancelled = true
      cancelAnimationFrame(frame)
    }
  }, [caseId, page, since, client])

  // Open until the reads have settled and the page's own work is done.
  const open = !settled || workPending(work)
  const closed = useRef(false)
  const [restarted, setRestarted] = useState(fresh)
  useLayoutEffect(() => {
    if (!open) {
      closed.current = true
      return
    }
    if (!closed.current) return
    closed.current = false
    const at = performance.now()
    setSince(at)
    setRestarted(true)
    setClock({ now: at, fraction: 0, movedAt: at, done: 0, unpacked: 0 })
  }, [open])
  // A mount that shared the opening and goes away before it closed notes when (openingsLeft).
  const sharedOpen = useRef(false)
  useLayoutEffect(() => {
    sharedOpen.current = open && opened !== undefined && since === opened
  }, [open, opened, since])
  useEffect(
    () => () => {
      if (sharedOpen.current && opened !== undefined) {
        openingsLeft.set(opened, performance.now())
        if (openingsLeft.size > 50) openingsLeft.delete(openingsLeft.keys().next().value as number)
      }
    },
    [opened]
  )
  // Recorded once per opening: the page's load, not later work (that is not what "last time" estimates).
  const saved = useRef(false)
  useEffect(() => {
    if (open || settledAt === null || saved.current) return
    saved.current = true
    if (opened !== undefined) {
      openingsDone.add(opened)
      if (openingsDone.size > 50) openingsDone.delete(openingsDone.values().next().value as number)
    }
    if (restarted) return
    // The time recorded is until the data is on screen: the paint after the reads, or the end of the page's work.
    const end = workSeen.current ? Math.max(settledAt, performance.now()) : settledAt
    if (!requestsSince(since).some((read) => read.failed)) saveMs(caseId, page, end - since)
  }, [open, settledAt, caseId, page, since, opened, restarted])
  // After the data is shown only the reads matter (a failed part being asked again); while loading, the tick too.
  const [, setReadsSeen] = useState(0)
  useEffect(() => {
    if (open) return
    return subscribeRequests(() => setReadsSeen((n) => n + 1))
  }, [open])
  useEffect(() => {
    if (!open) return
    const tick = () => setClock((previous) => nextClock(previous, since, workRef.current, opened !== undefined && since === opened))
    tick()
    const timer = setInterval(tick, TICK_MS)
    const unsubscribe = subscribeRequests(tick)
    return () => {
      clearInterval(timer)
      unsubscribe()
    }
  }, [open, since, opened])
  // A step of the page's own work counts at once, as a read's change does.
  const workDone = work?.done
  useEffect(() => {
    if (!open || workDone === undefined) return
    setClock((previous) => nextClock(previous, since, workRef.current, opened !== undefined && since === opened))
  }, [open, since, workDone, opened])

  const { now, fraction, movedAt } = clock
  const reads = requestsSince(since).filter((read) => !opensWholeCaseRun(read.failed))
  const elapsed = now - since
  const view = withWork(picture(reads), work)
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
  const usual = restarted ? null : recordedMs(caseId, page)
  const stalled = now - movedAt >= STALL_MS
  const longerThanUsual = usual !== null && elapsed > usual * 1.25 + 1000

  let left: string | null = null
  if (view.unpack) {
    // All bytes are in: time left only from the measured rate of rows unpacked so far (none while the rows are
    // still being found, as there is no rate yet to go on).
    const spent = now - view.unpack.started
    if (view.unpack.unit === "rows" && view.unpack.done > 0 && view.unpack.done < view.unpack.total && spent > 0) {
      const remaining = ((view.unpack.total - view.unpack.done) * spent) / view.unpack.done
      if (Number.isFinite(remaining)) left = `about ${seconds(remaining)} s left for this part`
    }
  } else if (view.bytes && view.current?.answered != null && view.bytes.received > 0) {
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
          {view.partsAsked > 0 && `${view.partsDone} of ${view.partsAsked} ${view.partsAsked === 1 ? "part" : "parts"} loaded · `}
          {percent}% · {seconds(elapsed)} s
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
