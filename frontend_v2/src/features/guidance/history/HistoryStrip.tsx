import { useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { History, ListTree, X } from "lucide-react"
import { cn } from "@/lib/cn"
import { historyAPI, stepsKey, type Step } from "../api"
import { returnTo, useHistory } from "./recorder"
import { AllStepsDialog } from "./AllSteps"
import { keepInView, STRIP_STEPS, when } from "./time-words"

/**
 * The slender history strip (lx-guide H): the last 8 steps in this case, oldest on the left, the current one
 * highlighted. A click returns to exactly that view. All steps opens the full, searchable list.
 */
export function HistoryStrip({ caseId }: { caseId: string }) {
  const navigate = useNavigate()
  const currentId = useHistory((s) => s.currentId)
  const message = useHistory((s) => s.message)
  const say = useHistory((s) => s.say)
  const [all, setAll] = useState(false)
  const list = useQuery({
    queryKey: [...stepsKey(caseId), "strip"],
    queryFn: () => historyAPI.list(caseId, { limit: STRIP_STEPS }),
    staleTime: 60_000,
  })
  const steps = [...(list.data?.steps ?? [])].reverse()
  const row = useRef<HTMLOListElement>(null)
  const order = steps.map((s) => s.id).join(",")
  // On a narrow screen the strip scrolls: keep the current step in view, never only the oldest ones.
  useEffect(() => {
    const ol = row.current
    const el = ol?.querySelector<HTMLElement>('[aria-current="step"]')
    if (ol && el) keepInView(ol, el)
  }, [order, currentId])
  const go = (step: Step) => returnTo(caseId, step, navigate)
  return (
    <>
      <div data-guide="history-strip" className="flex min-w-0 flex-1 items-center gap-1">
        <History className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
        {list.isError && <span role="alert" className="text-[11px]">Your steps could not be read. They are still being kept.</span>}
        {list.data && steps.length === 0 && <span className="text-[11px] text-muted-foreground">Your steps in this case appear here.</span>}
        <ol ref={row} aria-label="Your last steps in this case" className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto [scrollbar-width:none]">
          {steps.map((step, i) => {
            const current = step.id === currentId || (!currentId && i === steps.length - 1)
            return (
              <li key={step.id} className="flex shrink-0 items-center">
                {i > 0 && <span aria-hidden="true" className="px-0.5 text-[10px] text-muted-foreground">›</span>}
                <button
                  type="button"
                  aria-current={current ? "step" : undefined}
                  title={`${step.name} · ${when(step.at)}`}
                  onClick={() => go(step)}
                  className={cn(
                    "max-w-[14rem] truncate rounded px-1.5 py-0.5 text-[11px] leading-4",
                    current ? "bg-primary text-primary-foreground" : "text-foreground/80 hover:bg-muted"
                  )}
                >
                  {step.name}
                </button>
              </li>
            )
          })}
        </ol>
        {list.data && list.data.total > 0 && (
          <button type="button" onClick={() => setAll(true)} className="flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[11px] hover:bg-muted">
            <ListTree className="size-3.5" aria-hidden="true" />
            All steps ({list.data.total.toLocaleString("en-US")})
          </button>
        )}
      </div>
      {message && (
        <p role="status" className="absolute bottom-full left-2 right-2 mb-1 flex items-start gap-2 rounded-md border border-border bg-card px-3 py-2 text-xs shadow-md">
          <span className="flex-1">{message}</span>
          <button type="button" aria-label="Close this message" onClick={() => say(null)}>
            <X className="size-3.5" aria-hidden="true" />
          </button>
        </p>
      )}
      {all && <AllStepsDialog caseId={caseId} onClose={() => setAll(false)} onOpen={(s) => { setAll(false); go(s) }} />}
    </>
  )
}

