import { useNavigate } from "react-router-dom"
import type { Step } from "../api"
import { returnTo } from "./recorder"

/** The steps of a trail in a theory, each reopening the view it was (lx-guide L). */
export function TrailSteps({ caseId, how, onBeforeNavigate }: { caseId: string; how: Record<string, unknown> | null | undefined; onBeforeNavigate?: () => boolean }) {
  const navigate = useNavigate()
  const steps = (Array.isArray(how?.steps) ? how!.steps : []) as Step[]
  if (!steps.length) return null
  return (
    <ol className="flex flex-col gap-1 text-sm" aria-label="The steps of this trail">
      {steps.map((s, i) => (
        <li key={s.id ?? i} className="flex items-center gap-2">
          <span className="w-5 shrink-0 text-right text-xs text-muted-foreground">{i + 1}.</span>
          <span className="min-w-0 flex-1 truncate">{s.name}</span>
          <button type="button" className="shrink-0 text-xs underline underline-offset-2" onClick={() => { if (onBeforeNavigate?.() !== false) returnTo(caseId, s, navigate) }}>
            Open this step
          </button>
        </li>
      ))}
    </ol>
  )
}
