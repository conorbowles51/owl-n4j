import { useEffect, useLayoutEffect, useRef } from "react"
import { useLocation, useNavigate, useNavigationType, type NavigateFunction } from "react-router-dom"
import { useQueryClient, type QueryClient } from "@tanstack/react-query"
import { create } from "zustand"
import { useGraphStore } from "@/stores/graph.store"
import { useUIStore } from "@/stores/ui.store"
import { useTimelineStore } from "@/features/timeline/stores/timeline.store"
import { useFinancialDraftStore } from "@/features/financial/stores/financial-drafts"
import { useInvestigationScopeStore } from "@/features/financial/stores/investigation-scope"
import { historyAPI, stepsKey, type Step, type StepList } from "../api"
import { useDocumentStep } from "./document-step"
import {
  applyState,
  itemOf,
  labelFromCache,
  mergesInto,
  readState,
  screenOf,
  stepName,
  type Snapshot,
  type ViewState,
} from "./view-state"

/** Quiet time after the last change before a step is written: typing and scrolling settle into one step. */
export const SETTLE_MS = 1200
/** How long a returned-to step looks for its row and item before saying it is not there. */
export const FIND_MS = 15_000

interface Last {
  snapshot: Snapshot
  id: string | null
  at: number
  /** Reached by a click on the strip or browser Back/Forward: small changes stay local, not a rewrite. */
  returned: boolean
}

interface HistoryState {
  currentId: string | null
  last: Last | null
  /** A step being returned to, until its screen has drawn it. */
  returning: Step | null
  message: string | null
  setCurrent: (id: string | null) => void
  setLast: (last: Last | null) => void
  setReturning: (step: Step | null) => void
  say: (message: string | null) => void
}

export const useHistory = create<HistoryState>((set) => ({
  currentId: null,
  last: null,
  returning: null,
  message: null,
  setCurrent: (currentId) => set({ currentId }),
  setLast: (last) => set({ last }),
  setReturning: (returning) => set({ returning }),
  say: (message) => set({ message }),
}))

export function snapshotNow(caseId: string, pathname: string, search: string, qc: QueryClient): Snapshot {
  const state: ViewState = readState(caseId, pathname)
  const label = (id: string) => labelFromCache(qc, id)
  return {
    screen: screenOf(pathname).screen,
    path: pathname + search,
    state,
    item: itemOf(pathname, search, state, label),
    name: stepName({ pathname, search, state, label }),
  }
}

/** What to do with a new snapshot, given the last one (pure, for tests). */
export function decide(last: Last | null, next: Snapshot, now: number): "skip" | "local" | "merge" | "new" {
  if (last && JSON.stringify(last.snapshot) === JSON.stringify(next)) return "skip"
  if (last && mergesInto(last.snapshot, next, now - last.at)) return last.returned || !last.id ? "local" : "merge"
  return "new"
}

function putInList(qc: QueryClient, caseId: string, step: Step) {
  qc.setQueryData<StepList>([...stepsKey(caseId), "strip"], (old) => {
    if (!old) return old
    const rest = old.steps.filter((s) => s.id !== step.id)
    return { ...old, steps: [step, ...rest].slice(0, old.steps.length || 8), total: old.total + (step.merged ? 0 : 1) }
  })
  void qc.invalidateQueries({ queryKey: [...stepsKey(caseId), "all"] })
}

/** Records the person's steps through the case while it is open. Mounted once, in the case layout. */
export function useStepRecorder(caseId: string) {
  const qc = useQueryClient()
  const location = useLocation()
  const navType = useNavigationType()
  const timer = useRef<number | null>(null)
  const place = useRef({ pathname: location.pathname, search: location.search, pop: navType === "POP" })
  useLayoutEffect(() => {
    place.current = { pathname: location.pathname, search: location.search, pop: navType === "POP" }
  }, [location.pathname, location.search, navType])
  const writing = useRef(Promise.resolve())

  useEffect(() => {
    const fire = () => {
      timer.current = null
      const { pathname, search, pop } = place.current
      if (!pathname.startsWith(`/cases/${caseId}`)) return
      const h = useHistory.getState()
      if (h.returning) return // the step being returned to is drawn first
      const next = snapshotNow(caseId, pathname, search, qc)
      const now = Date.now()
      // browser Back/Forward to a view already in the strip: that step, not a new one
      if (pop && (!h.last || h.last.snapshot.path !== next.path)) {
        const list = qc.getQueryData<StepList>([...stepsKey(caseId), "strip"])
        const known = list?.steps.find((s) => s.path === next.path)
        if (known) {
          h.setCurrent(known.id)
          h.setLast({ snapshot: next, id: known.id, at: now, returned: true })
          return
        }
      }
      const what = decide(h.last, next, now)
      if (what === "skip") return
      if (what === "local") {
        h.setLast({ ...h.last!, snapshot: next, at: now })
        return
      }
      const replaces = what === "merge" ? h.last!.id : null
      h.setLast({ snapshot: next, id: replaces, at: now, returned: false })
      writing.current = writing.current.then(async () => {
        try {
          const step = await historyAPI.record(caseId, { ...next, state: next.state as Record<string, unknown>, replaces })
          const cur = useHistory.getState()
          if (cur.last?.snapshot === next) cur.setLast({ ...cur.last, id: step.id })
          cur.setCurrent(step.id)
          putInList(qc, caseId, step)
        } catch {
          // a step that could not be saved is not shown as saved; the next change tries again
          const cur = useHistory.getState()
          if (cur.last?.snapshot === next) cur.setLast(null)
        }
      })
    }
    const schedule = () => {
      if (timer.current) window.clearTimeout(timer.current)
      timer.current = window.setTimeout(fire, SETTLE_MS)
    }
    schedule()
    const unsubs = [
      useGraphStore.subscribe(schedule),
      useTimelineStore.subscribe(schedule),
      useFinancialDraftStore.subscribe(schedule),
      useInvestigationScopeStore.subscribe(schedule),
      useDocumentStep.subscribe(schedule),
      useUIStore.subscribe((s, p) => {
        if (s.graphPanelCollapsed !== p.graphPanelCollapsed || s.graphPanelTab !== p.graphPanelTab) schedule()
      }),
    ]
    let scrollAt = 0
    const onScroll = () => {
      const t = Date.now()
      if (t - scrollAt < 300) return
      scrollAt = t
      schedule()
    }
    document.addEventListener("scroll", onScroll, { capture: true, passive: true })
    return () => {
      if (timer.current) window.clearTimeout(timer.current)
      unsubs.forEach((u) => u())
      document.removeEventListener("scroll", onScroll, { capture: true })
    }
  }, [caseId, qc, location.key])
}

/** Returns to a step: puts its view state back, opens its address, then finds its row and item (useReturnCheck). */
export function returnTo(caseId: string, step: Step, navigate: NavigateFunction) {
  const h = useHistory.getState()
  h.say(null)
  h.setReturning(step)
  h.setCurrent(step.id)
  applyState(caseId, step.state as ViewState)
  navigate(step.path, { state: { historyStep: step.id } })
  // a step whose screen never arrives (an address that now redirects) stops waiting, so recording carries on
  window.setTimeout(() => {
    const cur = useHistory.getState()
    if (cur.returning?.id === step.id) {
      cur.setReturning(null)
      cur.say("That step's screen did not open as it was. This is the nearest view.")
    }
  }, FIND_MS + 5000)
}

const cssEscape = (v: string) => (typeof CSS !== "undefined" && CSS.escape ? CSS.escape(v) : v.replace(/["\\]/g, "\\$&"))

/** Where a returned-to step's row and item are looked for on screen. */
export function findOnScreen(key: string, root: ParentNode = document): HTMLElement | null {
  const k = cssEscape(key)
  return root.querySelector<HTMLElement>(`[data-row-key="${k}"], [data-node-key="${k}"], [data-evidence-file-id="${k}"], [data-event-key="${k}"]`)
}

/**
 * After a return: scrolls the step's first row back into view, and checks its item is still in the case. An item
 * that is not on screen and not in any loaded data within FIND_MS is reported in plain words, and the person stays
 * on the nearest view (the same screen with the same filters).
 */
export function useReturnCheck(caseId: string) {
  const qc = useQueryClient()
  const returning = useHistory((s) => s.returning)
  const location = useLocation()
  useEffect(() => {
    // the pathname decides: a screen may tidy its own search params on arrival
    if (!returning || location.pathname !== returning.path.split("?")[0]) return
    const state = returning.state as ViewState
    const item = returning.item
    const started = Date.now()
    let scrolled = !state.scrollKey
    let found = !item
    const tick = () => {
      if (!scrolled && state.scrollKey) {
        const row = findOnScreen(state.scrollKey)
        if (row) {
          row.scrollIntoView({ block: "start" })
          scrolled = true
        }
      }
      if (!found && item) found = !!findOnScreen(item.id) || !!labelFromCache(qc, item.id)
      if (scrolled && found) return finish(null)
      if (Date.now() - started > FIND_MS) {
        const what = item?.label ? `"${item.label}"` : "The item this step was on"
        const where = screenOf(returning.path.split("?")[0]).label
        if (!found && item) return finish(`${what} is not in the case any more: it may have been deleted or merged. This is the nearest view: ${where}, with the same filters.`)
        return finish(`The row this step was scrolled to is not on this screen now. ${where} is shown with the same filters, from the top.`)
      }
    }
    const finish = (message: string | null) => {
      window.clearInterval(handle)
      const h = useHistory.getState()
      h.say(message)
      const snap = snapshotNow(caseId, location.pathname, location.search, qc)
      h.setLast({ snapshot: snap, id: returning.id, at: Date.now(), returned: true })
      h.setReturning(null)
    }
    const handle = window.setInterval(tick, 250)
    tick()
    return () => window.clearInterval(handle)
  }, [returning, location.pathname, location.search, caseId, qc])
}

export { useNavigate }
