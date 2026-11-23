import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react"
import { useNavigate } from "react-router-dom"
import { ArrowLeft, ArrowRight, ExternalLink, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { useSwitch } from "@/lib/ui-switches"
import { phoneLayersEnabled } from "@/features/phones/lib/phone-layers"
import { findTarget, TOURS } from "../tours"
import { CASE_KINDS, QUESTIONS } from "./catalogue"
import { stepImage, workflowsShown, type SwitchState } from "./available"
import type { TutorialStep, Workflow } from "./types"
import type { WorkflowPlace } from "./WorkflowHost"

function useSwitches(): SwitchState {
  const corroborate = useSwitch("corroborate-v2")
  return { "corroborate-v2": corroborate, phone_layers: phoneLayersEnabled() }
}

export default function WorkflowGuide({
  caseId,
  open,
  place,
  onPlace,
  onClose,
  onLeave,
}: {
  caseId: string
  open: boolean
  place: WorkflowPlace
  onPlace: (place: WorkflowPlace) => void
  onClose: () => void
  onLeave: (place: WorkflowPlace) => void
}) {
  const switches = useSwitches()
  const workflows = useMemo(() => workflowsShown(switches), [switches])
  const current = workflows.find((w) => w.id === place.id)
  const navigate = useNavigate()
  if (!open) {
    if (!current) return null
    const step = current.steps[Math.min(place.step, current.steps.length - 1)]
    return (
      <StepReturn
        workflow={current}
        index={Math.min(place.step, current.steps.length - 1)}
        step={step}
        onBack={() => onPlace(place)}
        onClose={onClose}
      />
    )
  }
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        data-testid="workflow-guide"
        className="flex h-[92dvh] w-[96vw] max-w-none flex-col gap-3 overflow-hidden p-3 sm:max-w-6xl sm:p-5"
      >
        {current ? (
          <Tutorial
            workflow={current}
            index={Math.min(place.step, current.steps.length - 1)}
            onStep={(step) => onPlace({ id: current.id, step })}
            onList={() => onPlace({ step: 0 })}
            onOpenScreen={(step) => {
              const s = current.steps[step]
              navigate(`/cases/${encodeURIComponent(caseId)}/${s.open.to}`)
              onLeave({ id: current.id, step })
            }}
          />
        ) : (
          <WorkflowList workflows={workflows} onPick={(id) => onPlace({ id, step: 0 })} />
        )}
      </DialogContent>
    </Dialog>
  )
}

type Grouping = "question" | "kind"

export function WorkflowList({ workflows, onPick }: { workflows: Workflow[]; onPick: (id: string) => void }) {
  const [query, setQuery] = useState("")
  const [by, setBy] = useState<Grouping>("question")
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean)
  const matches = workflows.filter((w) => {
    const hay = [w.title, w.useWhen, ...w.areas.map((a) => TOURS[a].name), ...w.steps.map((s) => s.title)].join(" ").toLowerCase()
    return words.every((word) => hay.includes(word))
  })
  const groups = by === "question" ? QUESTIONS : CASE_KINDS
  return (
    <>
      <DialogHeader className="shrink-0 pr-8 text-left">
        <DialogTitle>Workflows</DialogTitle>
        <DialogDescription>
          Step-by-step guides to each line of enquiry, shown on the demo case. Pick one, then follow its steps in your own
          case.
        </DialogDescription>
      </DialogHeader>
      <div className="flex shrink-0 flex-wrap items-center gap-2">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Find a workflow: money, phone, theory…"
          aria-label="Find a workflow"
          className="h-9 max-w-md flex-1 basis-56"
        />
        <div role="group" aria-label="Group the workflows" className="flex gap-1">
          <Button size="sm" variant={by === "question" ? "secondary" : "ghost"} aria-pressed={by === "question"} onClick={() => setBy("question")}>
            By question
          </Button>
          <Button size="sm" variant={by === "kind" ? "secondary" : "ghost"} aria-pressed={by === "kind"} onClick={() => setBy("kind")}>
            By kind of case
          </Button>
        </div>
        <span className="text-xs text-muted-foreground" role="status">
          {matches.length} of {workflows.length} workflows
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto pr-1" data-testid="workflow-list">
        {matches.length === 0 && <p className="p-4 text-sm text-muted-foreground">No workflow matches “{query}”. Try fewer words.</p>}
        {groups.map((g) => {
          const inGroup = matches.filter((w) => (by === "question" ? (w.questions as string[]) : (w.kinds as string[])).includes(g.id))
          if (!inGroup.length) return null
          return (
            <section key={g.id} aria-labelledby={`wf-group-${g.id}`} className="mb-4">
              <h3 id={`wf-group-${g.id}`} className="mb-2 text-sm font-semibold text-primary">
                {g.label}
              </h3>
              <ul className="grid gap-2 sm:grid-cols-2">
                {inGroup.map((w) => (
                  <li key={w.id}>
                    <button
                      type="button"
                      data-workflow-id={w.id}
                      onClick={() => onPick(w.id)}
                      className="flex h-full w-full flex-col items-start gap-1 rounded-md border border-border bg-card p-3 text-left hover:border-primary/60 hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <span className="font-medium">{w.title}</span>
                      <span className="text-xs text-muted-foreground">{w.useWhen}</span>
                      <span className="text-[11px] text-muted-foreground">
                        {w.steps.length} steps · {w.areas.map((a) => TOURS[a].name).join(", ")}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )
        })}
      </div>
    </>
  )
}

export function Tutorial({
  workflow,
  index,
  onStep,
  onList,
  onOpenScreen,
}: {
  workflow: Workflow
  index: number
  onStep: (step: number) => void
  onList: () => void
  onOpenScreen: (step: number) => void
}) {
  const steps = workflow.steps
  const step = steps[index]
  const last = index >= steps.length - 1
  const heading = useRef<HTMLHeadingElement>(null)
  const moved = useRef(false)
  // a move to another step puts the reader at its heading, so a screen reader reads the new step
  useEffect(() => {
    if (moved.current) heading.current?.focus()
  }, [index])
  const go = (to: number) => {
    if (to < 0 || to >= steps.length) return
    moved.current = true
    onStep(to)
  }
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const t = e.target as HTMLElement
    if (t.closest("input, textarea, select, [contenteditable='true']")) return
    if (e.key === "ArrowRight") {
      e.preventDefault()
      go(index + 1)
    } else if (e.key === "ArrowLeft") {
      e.preventDefault()
      go(index - 1)
    }
  }
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3" onKeyDown={onKeyDown} data-testid="workflow-tutorial">
      <DialogHeader className="shrink-0 pr-8 text-left">
        <div>
          <Button size="sm" variant="ghost" className="-ml-2 h-7 px-2 text-xs" onClick={onList}>
            <ArrowLeft className="size-3.5" aria-hidden="true" />
            All workflows
          </Button>
        </div>
        <DialogTitle>{workflow.title}</DialogTitle>
        <DialogDescription>
          {workflow.useWhen}
          <span className="hidden sm:inline"> Use the arrow keys to move between steps.</span>
        </DialogDescription>
      </DialogHeader>
      {/* at phone width the steps are a strip of numbers above the step */}
      <nav aria-label="Steps" className="shrink-0 sm:hidden">
        <ol className="flex gap-1 overflow-x-auto pb-1">
          {steps.map((s, i) => (
            <li key={i}>
              <button
                type="button"
                aria-label={`Step ${i + 1}: ${s.title}`}
                aria-current={i === index ? "step" : undefined}
                onClick={() => go(i)}
                className={`size-8 shrink-0 rounded-full border text-xs ${i === index ? "border-primary bg-primary text-primary-foreground" : "border-border bg-card"}`}
              >
                {i + 1}
              </button>
            </li>
          ))}
        </ol>
      </nav>
      <div className="grid min-h-0 flex-1 gap-4 sm:grid-cols-[15rem_1fr]">
        <nav aria-label="Steps" className="hidden min-h-0 overflow-y-auto sm:block">
          <ol className="flex flex-col gap-1">
            {steps.map((s, i) => (
              <li key={i}>
                <button
                  type="button"
                  aria-current={i === index ? "step" : undefined}
                  onClick={() => go(i)}
                  className={`flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-sm ${i === index ? "bg-primary/10 font-medium text-foreground ring-1 ring-primary/50" : "text-muted-foreground hover:bg-muted"}`}
                >
                  <span className={`mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full text-[11px] ${i === index ? "bg-primary text-primary-foreground" : "bg-muted"}`}>{i + 1}</span>
                  <span>{s.title}</span>
                </button>
              </li>
            ))}
          </ol>
        </nav>
        <section aria-live="polite" className="flex min-h-0 flex-col gap-3 overflow-y-auto pr-1">
          <p className="text-xs font-medium uppercase tracking-wide text-primary">
            Step {index + 1} of {steps.length}
          </p>
          <h3 ref={heading} tabIndex={-1} className="text-lg font-semibold outline-none">
            {step.title}
          </h3>
          <p className="text-sm">{step.body}</p>
          <div className="rounded-md border-l-4 border-primary bg-muted/40 p-2 text-sm">
            <span className="font-medium">On the demo case you should see: </span>
            {step.expect}
          </div>
          <StepPicture step={step} />
          <div className="flex flex-wrap items-center gap-2 pb-1">
            <Button size="sm" variant="outline" onClick={() => onOpenScreen(index)}>
              <ExternalLink className="size-3.5" aria-hidden="true" />
              Open this screen
            </Button>
            <span className="flex-1" />
            <Button size="sm" variant="ghost" disabled={index === 0} disabledReason="This is the first step." onClick={() => go(index - 1)}>
              <ArrowLeft className="size-3.5" aria-hidden="true" />
              Previous
            </Button>
            {last ? (
              <Button size="sm" onClick={onList}>
                Done: all workflows
              </Button>
            ) : (
              <Button size="sm" onClick={() => go(index + 1)}>
                Next
                <ArrowRight className="size-3.5" aria-hidden="true" />
              </Button>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}

function StepPicture({ step }: { step: TutorialStep }) {
  const [failed, setFailed] = useState<string | null>(null)
  if (failed === step.shot) return <p className="rounded border border-dashed p-3 text-xs text-muted-foreground">The picture for this step could not load. The words above still describe the step.</p>
  return (
    <picture>
      <source media="(max-width: 640px)" srcSet={stepImage(step.shot, 390)} />
      <img
        key={step.shot}
        src={stepImage(step.shot, 1440)}
        alt={step.alt}
        loading="lazy"
        decoding="async"
        data-shot={step.shot}
        onError={() => setFailed(step.shot)}
        className="w-full rounded-md border border-border"
      />
    </picture>
  )
}

/** After "Open this screen": a ring round the step's control while it is on screen, and the way back to the step. */
function StepReturn({
  workflow,
  index,
  step,
  onBack,
  onClose,
}: {
  workflow: Workflow
  index: number
  step: TutorialStep
  onBack: () => void
  onClose: () => void
}) {
  const [ring, setRing] = useState<{ top: number; left: number; width: number; height: number } | null>(null)
  const [missing, setMissing] = useState(false)
  useEffect(() => {
    const targets = step.open.target ?? []
    if (!targets.length) return
    let scrolled = false
    const started = Date.now()
    const look = () => {
      const el = findTarget(targets)
      if (!el) {
        setRing(null)
        // the screen may still be loading; after 20 seconds say so rather than ring nothing
        if (Date.now() - started > 20_000) setMissing(true)
        return
      }
      setMissing(false)
      if (!scrolled) {
        el.scrollIntoView?.({ block: "center" })
        scrolled = true
      }
      const r = el.getBoundingClientRect()
      setRing({ top: r.top - 4, left: r.left - 4, width: r.width + 8, height: r.height + 8 })
    }
    look()
    const t = window.setInterval(look, 500)
    return () => window.clearInterval(t)
  }, [step])
  return (
    <>
      {ring && (
        <div
          aria-hidden="true"
          data-testid="workflow-ring"
          className="pointer-events-none fixed z-[45] rounded-md ring-2 ring-primary ring-offset-2 ring-offset-background"
          style={ring}
        />
      )}
      <div
        role="region"
        aria-label="Workflow step"
        className="fixed bottom-9 left-1/2 z-[46] flex w-[min(34rem,calc(100vw-1rem))] -translate-x-1/2 items-center gap-2 rounded-lg border border-primary/50 bg-card p-2 text-xs shadow-xl"
      >
        <span className="min-w-0 flex-1">
          <span className="font-medium">
            {workflow.title} · step {index + 1} of {workflow.steps.length}:
          </span>{" "}
          {step.title}
          {missing && <span className="block text-muted-foreground">The marked control is not on this screen in your case yet.</span>}
        </span>
        <Button size="sm" variant="outline" className="h-7 shrink-0" onClick={onBack}>
          Back to the step
        </Button>
        <Button size="icon" variant="ghost" className="size-7 shrink-0" aria-label="Close the workflow" onClick={onClose}>
          <X className="size-3.5" aria-hidden="true" />
        </Button>
      </div>
    </>
  )
}

