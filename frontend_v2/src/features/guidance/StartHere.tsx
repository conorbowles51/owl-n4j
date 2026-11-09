import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { ArrowRight, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { guidanceAPI } from "./api"
import { START_TIP, startSteps } from "./start-steps"
import { useGuidance } from "./settings"

/**
 * The first-visit card on the case home (lx-guide C): what to do first, from what the case has. It shows while
 * guidance is on and the person has not hidden it; Guide brings it back with "Show tips and tours again".
 */
export function StartHere({ caseId }: { caseId: string }) {
  const g = useGuidance(caseId)
  const navigate = useNavigate()
  const show = g.on && !g.tipHidden(START_TIP)
  const counts = useQuery({ queryKey: ["guidance-start", caseId], queryFn: () => guidanceAPI.start(caseId), enabled: show, staleTime: 60_000 })
  if (!show || !counts.data) return null
  const steps = startSteps(caseId, counts.data)
  if (!steps.length) return null
  return (
    <section
      data-guide="start-here"
      aria-label="Start here"
      className="pointer-events-auto absolute right-3 top-3 z-30 w-[min(24rem,calc(100%-1.5rem))] rounded-lg border border-primary/40 border-l-4 border-l-primary bg-card p-3 text-sm shadow-lg"
    >
      <div className="flex items-start gap-2">
        <h2 className="flex-1 font-semibold">Start here</h2>
        <button type="button" aria-label="Hide Start here" className="rounded p-0.5 hover:bg-muted" disabled={g.saving} onClick={() => void g.hideTip(START_TIP)}>
          <X className="size-4" aria-hidden="true" />
        </button>
      </div>
      <ul className="mt-2 flex flex-col gap-1.5">
        {steps.map((s) => (
          <li key={s.id} className="flex items-center justify-between gap-2">
            <span className="text-xs text-muted-foreground">{s.text}</span>
            <Button size="sm" variant="outline" className="shrink-0" onClick={() => navigate(s.to)}>
              {s.label}
              <ArrowRight className="size-3.5" aria-hidden="true" />
            </Button>
          </li>
        ))}
      </ul>
      {counts.data.unavailable.length > 0 && (
        <p className="mt-2 text-[11px] text-muted-foreground">Not counted, could not be read: {counts.data.unavailable.join(", ")}.</p>
      )}
    </section>
  )
}
