import { paymentPath } from "@/lib/citations"

/**
 * What to do next after an action completes (lx-guide A). One registry: each completed action, with the true numbers
 * from its result, gives a short title and up to four next steps, each a plain sentence with a button that goes
 * there. A step shows only when its target has something (never a step that leads nowhere): a count of 0 drops it,
 * and an action with no step left shows nothing.
 *
 * Pure: no React, no stores. The host (NextStepsHost) shows the card and runs a step's effect.
 */
export interface StepEffect {
  /** Graph entities to select before opening the graph or map. */
  selectGraph?: string[]
  /** A window event the target screen listens for (e.g. open the Deleted items list). */
  event?: string
}

export interface NextStep {
  id: string
  /** One plain sentence: what is there and why it is worth a look. */
  text: string
  /** The button's words. */
  label: string
  /** An address inside the app ("/cases/…"), or a file to download ("/api/…"). */
  to: string
  effect?: StepEffect
}

export interface NextStepsCard {
  /** The tip kind, for "Don't show tips like this". */
  kind: ActionKind
  title: string
  steps: NextStep[]
}

export type ActionFacts =
  | { kind: "document-processed"; files: number; names: number; links: number; failed?: number; fileName?: string; evidenceId?: string }
  | { kind: "statement-imported"; payments: number; needsLook: number; accounts?: number; fileName?: string }
  | { kind: "phone-imported"; title: string; href?: string | null; note?: string | null }
  | { kind: "media-read"; title: string; href?: string | null; note?: string | null }
  | { kind: "job-done"; title: string; href?: string | null; note?: string | null }
  | { kind: "merge-done"; name: string; entityKey?: string | null; merged: number }
  | { kind: "correction-saved"; what: string; count: number; paymentId?: string | null }
  | { kind: "confirmation-saved"; count: number; paymentId?: string | null }
  | { kind: "import-done"; corrected: number; failed: number; total: number }
  | { kind: "agent-run-done"; threadId?: string | null; payments: number; records: number }
  | { kind: "report-built"; fileName: string }
  | { kind: "theory-addition"; title: string; entryId: string; added: number; trail?: boolean }
  | { kind: "deleted"; count: number; noun: string; where: "evidence" | "graph" }
  | { kind: "export-done"; fileName: string; href?: string | null }

export type ActionKind = ActionFacts["kind"]

/** Every action the registry covers, for Settings and STATUS. */
export const ACTION_WORDS: Record<ActionKind, string> = {
  "document-processed": "Documents processed",
  "statement-imported": "Statements read into the ledger",
  "phone-imported": "Phone reports imported",
  "media-read": "Audio and images read",
  "job-done": "Other background work finished",
  "merge-done": "Entries merged",
  "correction-saved": "Corrections saved",
  "confirmation-saved": "Readings confirmed",
  "import-done": "Spreadsheet corrections imported",
  "agent-run-done": "Agent runs finished",
  "report-built": "Reports built",
  "theory-addition": "Added to a theory",
  deleted: "Moved to Deleted items",
  "export-done": "Exports ready",
}

const n = (v: number) => v.toLocaleString("en-US")
const plural = (v: number, one: string, many = `${one}s`) => `${n(v)} ${v === 1 ? one : many}`
const c = (caseId: string) => `/cases/${encodeURIComponent(caseId)}`

function phoneLinks(caseId: string, href: string | null | undefined): NextStep[] {
  if (!href) return []
  const steps: NextStep[] = [{ id: "open", text: "The phone's summary shows who it belongs to and what it holds.", label: "Open the phone", to: href }]
  const extraction = /\/phones\/([^/?#]+)/.exec(href)?.[1]
  if (extraction)
    steps.push({ id: "conversations", text: "Read its messages, grouped by conversation.", label: "Read the conversations", to: `${c(caseId)}/phones/${extraction}/records/conversations` })
  return steps
}

export function nextSteps(caseId: string, facts: ActionFacts): NextStepsCard | null {
  const base = c(caseId)
  let title = ""
  let steps: (NextStep | false | null | undefined | "")[] = []
  switch (facts.kind) {
    case "document-processed": {
      const what = facts.files === 1 && facts.fileName ? facts.fileName : plural(facts.files, "file")
      title =
        facts.names > 0
          ? `${what} processed: ${plural(facts.names, "name")} and ${plural(facts.links, "link")} between them found.`
          : `${what} processed. No names were found.`
      if (facts.failed) title += ` ${plural(facts.failed, "file")} stopped with an error; the Jobs list says why.`
      steps = [
        facts.names > 0 && { id: "names", text: `Check the ${plural(facts.names, "name")} found, one row each.`, label: "Review the names", to: `${base}/table` },
        facts.links > 0 && { id: "graph", text: `See the ${plural(facts.links, "link")} between them as a network.`, label: "Open the graph", to: `${base}/graph` },
        facts.names > 0 && { id: "timeline", text: "Look for dated events from the files on the case timeline.", label: "See the timeline", to: `${base}/timeline` },
        facts.names > 0 && { id: "agent", text: "Ask the case agent what the new files say and how they fit.", label: "Ask the agent", to: `${base}/agent` },
        facts.evidenceId && { id: "file", text: `Read ${facts.fileName || "the file"} with what was found in it.`, label: "Open the file", to: `${base}/evidence?file=${encodeURIComponent(facts.evidenceId)}` },
      ]
      break
    }
    case "statement-imported":
      title = `${facts.fileName ? `${facts.fileName}: ` : ""}${plural(facts.payments, "payment")} added to the ledger.`
      steps = [
        facts.payments > 0 && { id: "payments", text: `See the ${plural(facts.payments, "payment")} with their dates, amounts and other side.`, label: "See the payments", to: `${base}/financial?view=transactions` },
        facts.needsLook > 0 && { id: "queue", text: `${plural(facts.needsLook, "line")} could not be read with certainty; check them against the statement.`, label: "Check the lines", to: `${base}/financial?view=statements&queue=1` },
        facts.payments > 0 && { id: "follow", text: "Follow where the money went, account to account.", label: "Follow the money", to: `${base}/financial?view=follow-money` },
      ]
      break
    case "phone-imported":
      title = `${facts.title}: imported.${facts.note ? ` ${facts.note}` : ""}`
      steps = phoneLinks(caseId, facts.href)
      break
    case "media-read":
    case "job-done":
      title = `${facts.title}: done.${facts.note ? ` ${facts.note}` : ""}`
      steps = [facts.href && { id: "open", text: "See the result where the work was asked for.", label: "Open the result", to: facts.href }]
      break
    case "merge-done":
      title = `${plural(facts.merged, "entry", "entries")} merged into ${facts.name}.`
      steps = [
        facts.entityKey && { id: "graph", text: `See ${facts.name} with every link the merged entries had.`, label: "Open on the graph", to: `${base}/graph`, effect: { selectGraph: [facts.entityKey] } },
        facts.entityKey && { id: "timeline", text: `See ${facts.name}'s dated events in one line.`, label: "See the timeline", to: `${base}/timeline`, effect: { selectGraph: [facts.entityKey] } },
        { id: "table", text: "Look for other names that may be the same person or company.", label: "Review the names", to: `${base}/table` },
      ]
      break
    case "correction-saved":
      title = `${facts.what} saved${facts.count > 1 ? ` on ${plural(facts.count, "payment")}` : ""}. The original stays visible beside it.`
      steps = [
        facts.paymentId && { id: "payment", text: "See the payment with its correction and the statement line it came from.", label: "See the payment", to: paymentPath(caseId, facts.paymentId) },
        { id: "payments", text: "Go back to the payments to check or correct the next one.", label: "See the payments", to: `${base}/financial?view=transactions` },
        { id: "follow", text: "See how the corrected figures change the money flows.", label: "Follow the money", to: `${base}/financial?view=follow-money` },
      ]
      break
    case "confirmation-saved":
      title = `${plural(facts.count, "reading")} confirmed. ${facts.count === 1 ? "It counts" : "They count"} as a person's reading from now on.`
      steps = [
        facts.paymentId && { id: "payment", text: "See the payment with the confirmed reading.", label: "See the payment", to: paymentPath(caseId, facts.paymentId) },
        { id: "next", text: "Go back to the payments to confirm the next name Claude read.", label: "See the payments", to: `${base}/financial?view=transactions` },
      ]
      break
    case "import-done":
      title = `${plural(facts.corrected, "payment")} of ${n(facts.total)} corrected from the spreadsheet.${facts.failed ? ` ${plural(facts.failed, "line")} could not be applied; the import window lists why.` : ""}`
      steps = [
        facts.corrected > 0 && { id: "payments", text: "See the corrected payments, each with its original beside it.", label: "See the payments", to: `${base}/financial?view=transactions` },
        facts.corrected > 0 && { id: "follow", text: "See how the corrections change the money flows.", label: "Follow the money", to: `${base}/financial?view=follow-money` },
      ]
      break
    case "agent-run-done":
      title = `The agent finished.${facts.payments + facts.records > 0 ? ` Its answer cites ${plural(facts.payments, "payment")} and ${plural(facts.records, "other record")}.` : ""}`
      steps = [
        { id: "theory", text: "Keep what it found: add the answer to a theory or finding.", label: "Open theories", to: `${base}/workspace?view=casework&kind=theory` },
        facts.payments > 0 && { id: "payments", text: "Check the cited payments against their statements.", label: "See the payments", to: `${base}/financial?view=transactions` },
      ]
      break
    case "report-built":
      title = `Report ready: ${facts.fileName}.`
      steps = [
        { id: "reports", text: "Build another report or check what each one holds.", label: "Open Reports", to: `${base}/reports` },
        { id: "workspace", text: "Add findings to the case work so the next report carries them.", label: "Open the case work", to: `${base}/workspace` },
      ]
      break
    case "theory-addition":
      title = `${facts.trail ? "Trail of steps" : plural(facts.added, "item")} added to ${facts.title}.`
      steps = [
        facts.added > 0 && { id: "theory", text: `Read ${facts.title} with what was added and why.`, label: "Open the theory", to: `${base}/workspace?view=casework&kind=theory&entry=${encodeURIComponent(facts.entryId)}` },
        facts.added > 0 && { id: "agent", text: "Ask the agent whether the theory holds up against the evidence.", label: "Ask the agent", to: `${base}/agent` },
      ]
      break
    case "deleted":
      title = `${plural(facts.count, facts.noun)} moved to Deleted items. Nothing is lost until it is deleted from there.`
      steps = [
        facts.count > 0 && facts.where === "evidence" && { id: "undo", text: "Changed your mind? Restore from Deleted items.", label: "Undo from Deleted items", to: `${base}/evidence`, effect: { event: OPEN_DELETED_ITEMS } },
        facts.count > 0 && facts.where === "graph" && { id: "undo", text: "Changed your mind? Restore from the graph's recycle bin.", label: "Open the recycle bin", to: `${base}/graph`, effect: { event: OPEN_RECYCLE_BIN } },
      ]
      break
    case "export-done":
      title = `Export ready: ${facts.fileName}.`
      steps = [facts.href && { id: "download", text: "The file stays listed under the case's exports.", label: "Download", to: facts.href }]
      break
  }
  const kept = steps.filter((s): s is NextStep => !!s && !!s.to)
  if (!kept.length) return null
  return { kind: facts.kind, title, steps: kept.slice(0, 4) }
}

/** Window events a target screen listens for. */
export const OPEN_DELETED_ITEMS = "loupe:open-deleted-items"
export const OPEN_RECYCLE_BIN = "loupe:open-recycle-bin"
