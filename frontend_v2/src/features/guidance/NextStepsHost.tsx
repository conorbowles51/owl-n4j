import { useState } from "react"
import { useLocation, useNavigate } from "react-router-dom"
import { ArrowRight, Lightbulb, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useGraphStore } from "@/stores/graph.store"
import { useNextSteps, type Announced } from "./announce"
import type { NextStep } from "./next-steps"
import { useGuidance } from "./settings"

/**
 * Where the next steps after an action appear (lx-guide B, D): a small card above the history strip that stays until
 * the person acts on a step or dismisses it. With guidance off, or tips of this kind hidden, the card does not pop
 * up; it waits behind a quiet "Next steps" link instead, so nothing is lost.
 */
export function NextStepsHost({ caseId }: { caseId: string }) {
  const all = useNextSteps((s) => s.cards)
  const dismiss = useNextSteps((s) => s.dismiss)
  const g = useGuidance(caseId)
  const [opened, setOpened] = useState(false)
  const cards = all.filter((c) => c.caseId === caseId)
  if (!cards.length) return null
  const quiet = (c: Announced) => !g.on || g.tipHidden(c.kind)
  const popped = opened ? cards : cards.filter((c) => !quiet(c)).slice(0, 2)
  const waiting = cards.length - popped.length
  return (
    <div className="pointer-events-none absolute bottom-2 left-2 z-40 flex max-w-[min(26rem,calc(100%-1rem))] flex-col items-start gap-2">
      {popped.map((card) => (
        <NextStepsCardView key={card.id} card={card} onClose={() => dismiss(card.id)} />
      ))}
      {waiting > 0 && (
        <button
          type="button"
          className="pointer-events-auto rounded-full border border-border bg-card px-3 py-1 text-xs underline-offset-2 shadow-sm hover:underline"
          onClick={() => setOpened(true)}
        >
          Next steps ({waiting})
        </button>
      )}
      {opened && waiting === 0 && (
        <button type="button" className="pointer-events-auto text-xs underline underline-offset-2" onClick={() => setOpened(false)}>
          Hide the next steps
        </button>
      )}
    </div>
  )
}

export function NextStepsCardView({ card, onClose }: { card: Announced; onClose: () => void }) {
  const navigate = useNavigate()
  const here = useLocation()
  // a step to the screen the person is already on is left out: it would lead nowhere new
  const steps = card.steps.filter((st) => st.to !== here.pathname + here.search && st.to !== here.pathname)
  const g = useGuidance(card.caseId)
  const go = (step: NextStep) => {
    if (step.effect?.selectGraph?.length) useGraphStore.getState().selectNodes(step.effect.selectGraph)
    onClose()
    if (step.to.startsWith("/cases/")) navigate(step.to)
    else window.location.assign(step.to)
    if (step.effect?.event) {
      const name = step.effect.event
      // the target screen mounts first, then hears the event
      window.setTimeout(() => window.dispatchEvent(new Event(name)), 400)
    }
  }
  return (
    <section
      role="status"
      aria-label="Next steps"
      data-testid="next-steps-card"
      className="pointer-events-auto w-full rounded-lg border border-primary/40 border-l-4 border-l-primary bg-card p-3 text-sm shadow-lg"
    >
      <div className="flex items-start gap-2">
        <Lightbulb className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
        <p className="flex-1 font-medium">{card.title}</p>
        <button type="button" aria-label="Dismiss these next steps" className="rounded p-0.5 hover:bg-muted" onClick={onClose}>
          <X className="size-4" aria-hidden="true" />
        </button>
      </div>
      <ul className="mt-2 flex flex-col gap-1.5">
        {steps.map((step) => (
          <li key={step.id} className="flex items-center justify-between gap-2">
            <span className="text-xs text-muted-foreground">{step.text}</span>
            <Button size="sm" variant="outline" className="shrink-0" onClick={() => go(step)}>
              {step.label}
              <ArrowRight className="size-3.5" aria-hidden="true" />
            </Button>
          </li>
        ))}
      </ul>
      {g.on && (
        <div className="mt-2 flex gap-3 text-[11px] text-muted-foreground">
          <button type="button" className="underline underline-offset-2" disabled={g.saving} onClick={() => void g.hideTip(card.kind).then(onClose)}>
            Don&apos;t show tips like this
          </button>
          <button type="button" className="underline underline-offset-2" disabled={g.saving} onClick={() => void g.turn("off")}>
            Turn guidance off
          </button>
        </div>
      )}
    </section>
  )
}
