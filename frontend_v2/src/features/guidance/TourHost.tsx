import { useEffect, useLayoutEffect, useState } from "react"
import { useLocation } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { useGuidance } from "./settings"
import { findTarget, tourArea, TOURS, type TourArea } from "./tours"

/** Guide → "Take the tour of this screen" sends this, with the area in `detail`. */
export const START_TOUR = "loupe:start-tour"
/** The tip kind "Don't show tips like this" uses on a tour popup: no tour opens by itself again. */
export const TOUR_TIP = "tours"

const WAIT_MS = 1200
const W = 320

/**
 * The first-visit tour of the screen the person is on (lx-guide C): it opens by itself once per area while guidance is
 * on, resumes at the step where it was left, and can be skipped. Guide opens it again at any time, guidance on or off.
 */
export function TourHost({ caseId }: { caseId: string }) {
  const { pathname } = useLocation()
  const area = tourArea(pathname)
  const g = useGuidance(caseId)
  const [open, setOpen] = useState<{ area: TourArea; step: number; auto: boolean } | null>(null)
  const [ready, setReady] = useState<string | null>(null)

  // a short wait after each screen change, so the screen's controls are drawn before the first popup points at one;
  // a tour that opened by itself closes when the person moves to another screen (it resumes there next time)
  useEffect(() => {
    setReady(null)
    setOpen((o) => (o?.auto ? null : o))
    const t = window.setTimeout(() => setReady(pathname), WAIT_MS)
    return () => window.clearTimeout(t)
  }, [pathname])

  useEffect(() => {
    const start = (e: Event) => {
      const wanted = ((e as CustomEvent).detail as TourArea | undefined) ?? area
      if (wanted) setOpen({ area: wanted, step: 0, auto: false })
    }
    window.addEventListener(START_TOUR, start)
    return () => window.removeEventListener(START_TOUR, start)
  }, [area])

  const saved = area ? g.settings?.tours[area] : undefined
  const due = !!area && g.on && ready === pathname && !g.tipHidden(TOUR_TIP) && !saved?.state
  const resumeAt = saved?.step ?? 0
  useEffect(() => {
    if (!due || !area || document.querySelector("[role='dialog']")) return
    setOpen((o) => o ?? { area, step: Math.min(resumeAt, TOURS[area].steps.length - 1), auto: true })
  }, [due, area, resumeAt])

  if (!open) return null
  return (
    <TourPopup
      key={`${open.area}-${open.auto ? "auto" : "asked"}`}
      area={open.area}
      first={open.step}
      onStep={(step) => void g.tour(open.area, { step }).catch(() => undefined)}
      onEnd={(state) => {
        setOpen(null)
        void g.tour(open.area, { state }).catch(() => undefined)
      }}
      onHideTours={() => {
        setOpen(null)
        void g.hideTip(TOUR_TIP).catch(() => undefined)
      }}
      onGuidanceOff={() => {
        setOpen(null)
        void g.turn("off").catch(() => undefined)
      }}
      guidanceOn={g.on}
    />
  )
}

interface Place {
  top: number
  left: number
  ring: { top: number; left: number; width: number; height: number } | null
}

function place(el: HTMLElement | null): Place {
  const vw = window.innerWidth
  const vh = window.innerHeight
  if (!el) return { top: Math.max(16, vh / 2 - 100), left: Math.max(8, vw / 2 - W / 2), ring: null }
  const r = el.getBoundingClientRect()
  const ring = { top: r.top - 4, left: r.left - 4, width: r.width + 8, height: r.height + 8 }
  const width = Math.min(W, vw - 16)
  const left = Math.min(Math.max(8, r.left), vw - width - 8)
  // below the control when there is room, otherwise above it; a control taller than the screen gets the middle
  const below = r.bottom + 12
  const top = below + 200 < vh ? below : r.top - 212 > 8 ? r.top - 212 : Math.max(16, vh / 2 - 100)
  return { top, left, ring: r.height < vh * 0.8 ? ring : null }
}

export function TourPopup({
  area,
  first,
  onStep,
  onEnd,
  onHideTours,
  onGuidanceOff,
  guidanceOn,
}: {
  area: TourArea
  first: number
  onStep: (step: number) => void
  onEnd: (state: "done" | "skipped") => void
  onHideTours: () => void
  onGuidanceOff: () => void
  guidanceOn: boolean
}) {
  const tour = TOURS[area]
  const [index, setIndex] = useState(first)
  const step = tour.steps[index]
  const [where, setWhere] = useState<Place>(() => place(null))
  useLayoutEffect(() => {
    const target = findTarget(step.targets)
    target?.scrollIntoView?.({ block: "nearest" })
    const update = () => setWhere(place(target))
    update()
    window.addEventListener("resize", update)
    return () => window.removeEventListener("resize", update)
  }, [step])
  const last = index === tour.steps.length - 1
  const move = (to: number) => {
    setIndex(to)
    onStep(to)
  }
  return (
    <>
      {where.ring && (
        <div
          aria-hidden="true"
          className="pointer-events-none fixed z-[60] rounded-md ring-2 ring-primary ring-offset-2 ring-offset-background"
          style={where.ring}
        />
      )}
      <section
        role="dialog"
        aria-modal="false"
        aria-label={`${tour.name} tour, step ${index + 1} of ${tour.steps.length}`}
        data-testid="tour-popup"
        className="fixed z-[61] rounded-lg border border-primary/50 bg-card p-3 text-sm shadow-xl"
        style={{ top: where.top, left: where.left, width: Math.min(W, window.innerWidth - 16) }}
      >
        <p className="text-[11px] font-medium uppercase tracking-wide text-primary">
          {tour.name} · {index + 1} of {tour.steps.length}
        </p>
        <h2 className="mt-1 font-semibold">{step.title}</h2>
        <p className="mt-1 text-muted-foreground">{step.body}</p>
        <div className="mt-3 flex items-center gap-2">
          <Button size="sm" variant="ghost" onClick={() => onEnd("skipped")}>
            Skip tour
          </Button>
          <span className="flex-1" />
          {index > 0 && (
            <Button size="sm" variant="outline" onClick={() => move(index - 1)}>
              Back
            </Button>
          )}
          <Button size="sm" onClick={() => (last ? onEnd("done") : move(index + 1))}>
            {last ? "Done" : "Next"}
          </Button>
        </div>
        {guidanceOn && (
          <div className="mt-2 flex gap-3 text-[11px] text-muted-foreground">
            <button type="button" className="underline underline-offset-2" onClick={onHideTours}>
              Don&apos;t show tips like this
            </button>
            <button type="button" className="underline underline-offset-2" onClick={onGuidanceOff}>
              Turn guidance off
            </button>
          </div>
        )}
      </section>
    </>
  )
}
