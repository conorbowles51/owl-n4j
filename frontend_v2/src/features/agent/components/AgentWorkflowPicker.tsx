import { useEffect, useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import { agentAPI } from "../api"
import type { AgentWorkflow, AgentWorkflowCatalogue } from "../types"

const COUNT_WORDS: Record<string, string> = {
  ledger: "ledger rows",
  phones: "phones",
  documents: "documents (other than statements)",
  dossiers: "people",
  timeline: "timeline entries",
}

const SLOTS: Record<string, string> = {
  person: "Person",
  other: "Other person",
  date: "Date",
}

/** The {person}, {other} and {date} slots a starting question asks for, in order. */
export function workflowSlots(question: string): string[] {
  const found: string[] = []
  for (const match of question.matchAll(/\{(person|other|date)\}/g)) {
    if (!found.includes(match[1])) found.push(match[1])
  }
  return found
}

export function fillWorkflowQuestion(question: string, values: Record<string, string>): string {
  return question.replace(/\{(person|other|date)\}/g, (_, key: string) => values[key]?.trim() || `[${SLOTS[key]}]`)
}

function statusWords(workflow: AgentWorkflow): { label: string; tone: string } {
  const r = workflow.readiness
  if (!r) return { label: "", tone: "" }
  const toolSteps = r.steps.filter((s) => !s.by_person).length
  if (r.status === "ready") return { label: `Ready: all ${toolSteps} steps can run`, tone: "text-emerald-700 dark:text-emerald-300" }
  if (r.status === "partial")
    return { label: `Partly: ${r.steps_that_run} of ${toolSteps} steps can run`, tone: "text-amber-700 dark:text-amber-300" }
  return { label: "Not possible on this case", tone: "text-muted-foreground" }
}

function WorkflowRow({
  workflow,
  disabled,
  onStart,
}: {
  workflow: AgentWorkflow
  disabled: boolean
  onStart: (workflowId: string, question: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [values, setValues] = useState<Record<string, string>>({})
  const slots = useMemo(() => workflowSlots(workflow.starting_question), [workflow.starting_question])
  const r = workflow.readiness
  const status = statusWords(workflow)
  const blocked = r?.status === "not_possible"
  const question = fillWorkflowQuestion(workflow.starting_question, values)
  const unfilled = slots.some((slot) => !values[slot]?.trim())
  const notRun = r ? r.steps.filter((s) => !s.runs && !s.by_person) : []

  return (
    <li className="rounded-md border border-border bg-card p-3 text-left" data-testid={`workflow-${workflow.id}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-medium text-foreground">
            {workflow.number}. {workflow.title}
          </div>
          <div className="mt-0.5 text-xs text-muted-foreground">{workflow.question}</div>
          {status.label && <div className={`mt-1 text-xs ${status.tone}`}>{status.label}</div>}
          {blocked && r && r.reasons.length > 0 && (
            <ul className="mt-1 list-disc pl-4 text-xs text-muted-foreground">
              {r.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          )}
        </div>
        <Button
          size="sm"
          variant={open ? "secondary" : "outline"}
          onClick={() => setOpen(!open)}
          disabled={disabled || blocked}
          aria-expanded={open}
          aria-label={`Use workflow ${workflow.title}`}
        >
          {open ? "Close" : "Use"}
        </Button>
      </div>
      {open && (
        <div className="mt-3 space-y-2 border-t border-border pt-3">
          <ol className="list-decimal space-y-0.5 pl-5 text-xs text-muted-foreground">
            {(r?.steps ?? workflow.steps.map((tool) => ({ tool, why: "", runs: true, by_person: false, data_missing: [] as string[], in_build: true }))).map((step, index) => (
              <li key={`${step.tool}-${index}`}>
                <span className="font-mono text-foreground">{step.tool}</span>
                {step.why ? `: ${step.why}` : ""}
                {step.by_person
                  ? " (you do this on screen)"
                  : !step.in_build
                    ? " (not in this release: reported as not examined)"
                    : step.data_missing.length > 0
                      ? ` (no ${step.data_missing.map((k) => COUNT_WORDS[k] ?? k).join(", ")} in this case: reported as not examined)`
                      : ""}
              </li>
            ))}
          </ol>
          <div className="text-xs text-muted-foreground">
            Results come back as proposals for you to confirm ({workflow.person_confirms}), never as conclusions.
            {notRun.length > 0 && ` ${notRun.length} step${notRun.length === 1 ? "" : "s"} will be listed as not examined.`}
          </div>
          {slots.map((slot) => (
            <label key={slot} className="flex items-center gap-2 text-xs">
              <span className="w-24 shrink-0 text-muted-foreground">{SLOTS[slot]}</span>
              <input
                value={values[slot] ?? ""}
                onChange={(event) => setValues({ ...values, [slot]: event.target.value })}
                className="min-w-0 flex-1 rounded-md border border-border bg-background px-2 py-1 text-xs outline-none focus:border-amber-400"
                placeholder={slot === "date" ? "e.g. 14 March 2023" : "A name as it appears on People"}
                aria-label={`${workflow.title}: ${SLOTS[slot]}`}
              />
            </label>
          ))}
          <div className="rounded-md bg-muted/50 px-2 py-1.5 text-xs text-foreground">{question}</div>
          <Button
            size="sm"
            onClick={() => onStart(workflow.id, question)}
            disabled={disabled || unfilled}
            aria-label={`Start workflow ${workflow.title}`}
          >
            Start workflow
          </Button>
        </div>
      )}
    </li>
  )
}

/** The guided investigative workflows for this case, each with what the case holds for it (counts read from the
 * case, never assumed). Starting one sends its named question with the workflow, so the agent follows its steps
 * and returns proposals. */
export function AgentWorkflowPicker({
  caseId,
  disabled,
  onStart,
}: {
  caseId: string
  disabled: boolean
  onStart: (workflowId: string, question: string) => void
}) {
  const [catalogue, setCatalogue] = useState<AgentWorkflowCatalogue | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showMore, setShowMore] = useState(false)

  useEffect(() => {
    let live = true
    setCatalogue(null)
    setError(null)
    agentAPI
      .listWorkflows(caseId)
      .then((data) => live && setCatalogue(data))
      .catch((err: unknown) => live && setError(err instanceof Error ? err.message : "The workflows could not be read."))
    return () => {
      live = false
    }
  }, [caseId])

  if (error) return <div className="text-xs text-destructive">Workflows could not be read: {error}</div>
  if (!catalogue)
    return (
      <div className="text-xs text-muted-foreground">
        Reading this case's ledger, phones and documents to see which workflows can run...
      </div>
    )

  const main = catalogue.workflows.filter((w) => !w.extra)
  const extra = catalogue.workflows.filter((w) => w.extra)
  const counts = catalogue.counts ?? {}

  return (
    <div className="space-y-2 text-left" data-testid="agent-workflow-picker">
      <div className="text-xs text-muted-foreground">
        This case holds{" "}
        {Object.entries(COUNT_WORDS)
          .map(([key, words]) => `${(counts[key] ?? 0).toLocaleString()} ${words}`)
          .join(", ")}
        .
      </div>
      <ul className="space-y-2">
        {main.map((workflow) => (
          <WorkflowRow key={workflow.id} workflow={workflow} disabled={disabled} onStart={onStart} />
        ))}
      </ul>
      <Button size="sm" variant="ghost" onClick={() => setShowMore(!showMore)} aria-expanded={showMore}>
        {showMore ? "Hide" : "Show"} {extra.length} more workflows
      </Button>
      {showMore && (
        <ul className="space-y-2">
          {extra.map((workflow) => (
            <WorkflowRow key={workflow.id} workflow={workflow} disabled={disabled} onStart={onStart} />
          ))}
        </ul>
      )}
    </div>
  )
}
