import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { PhoneShape } from "../ui/PhoneChip"
import type { NextStep } from "./person-api"

/** A phone's mark with its label beside it, so colour is never the only cue. */
export function PhoneTag({ index, label, className }: { index: number; label: string; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 ${className ?? ""}`}>
      <PhoneShape index={index} />
      <span>{label}</span>
    </span>
  )
}

/** The ranked "Next steps" block (COMMON rule 4): each step a title, a why from this result, and one button. */
export function NextSteps({ steps, intro, act }: {
  steps: NextStep[]
  intro: string
  /** The step's action: a link (``to``) or a handler (``onClick``). */
  act: (s: NextStep) => { to?: string; onClick?: () => void }
}) {
  if (!steps.length) return null
  return (
    <section aria-labelledby="next-steps-h" className="rounded-xl border bg-card p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="next-steps-h" className="text-base font-bold">Next steps</h2>
        <p className="text-xs text-muted-foreground">{intro}</p>
      </div>
      <ol className="mt-2 flex flex-col">
        {steps.map((s, i) => {
          const a = act(s)
          return (
            <li key={s.code} className="flex flex-wrap items-center gap-3.5 border-t py-3">
              <span aria-hidden className="flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs">{s.rank}</span>
              <div className="min-w-0 flex-[1_1_420px]">
                <div className="text-sm font-semibold">{s.title}</div>
                <div className="mt-0.5 text-[13px] leading-snug text-muted-foreground">{s.why}</div>
              </div>
              {a.to ? (
                <Button asChild size="sm" variant={i === 0 ? "primary" : "outline"}>
                  <Link to={a.to}>{s.action}</Link>
                </Button>
              ) : (
                <Button size="sm" variant={i === 0 ? "primary" : "outline"} onClick={a.onClick}>
                  {s.action}
                </Button>
              )}
            </li>
          )
        })}
      </ol>
    </section>
  )
}
