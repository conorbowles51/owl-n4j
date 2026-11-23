import type { StartCounts } from "./api"

export const START_TIP = "start-here"

export interface StartStep {
  id: string
  text: string
  label: string
  to: string
  /** The step-by-step workflow that shows how (Guide, Workflows). */
  workflow?: string
}

const n = (v: number) => v.toLocaleString("en-US")
const plural = (v: number, one: string, many = `${one}s`) => `${n(v)} ${v === 1 ? one : many}`

/** "Start here" for a case, from what it has (pure, for tests). A step shows only when its target has something. */
export function startSteps(caseId: string, c: StartCounts): StartStep[] {
  const base = `/cases/${encodeURIComponent(caseId)}`
  const out: (StartStep | false)[] = [
    c.files === 0 && { id: "upload", text: "The case has no files yet. Upload the production to begin.", label: "Upload files", to: `${base}/evidence`, workflow: "bring-in" },
    (c.unprocessed ?? 0) > 0 && { id: "process", text: `${plural(c.unprocessed!, "file")} not processed yet. Processing finds the names, dates and payments in them.`, label: "Process files", to: `${base}/evidence`, workflow: "bring-in" },
    (c.payments ?? 0) > 0 && { id: "money", text: `${plural(c.payments!, "payment")} in the ledger. See what needs your attention first.`, label: "Open Financial", to: `${base}/financial?view=overview`, workflow: "money" },
    (c.phones ?? 0) > 0 && { id: "phones", text: `${plural(c.phones!, "phone")} in the case. See who each belongs to and who they talk to.`, label: "Open Phones", to: `${base}/phones`, workflow: "contact" },
    (c.files ?? 0) > (c.unprocessed ?? 0) && { id: "graph", text: "See who is linked to whom across the processed files.", label: "Open the graph", to: `${base}/graph`, workflow: "graph" },
    c.theories === 0 && (c.files ?? 0) > 0 && { id: "theory", text: "No theory yet. Write down what you think happened, then add the evidence for and against it.", label: "Start a theory", to: `${base}/workspace?view=casework&kind=theory`, workflow: "theory" },
  ]
  return out.filter((s): s is StartStep => !!s).slice(0, 4)
}
