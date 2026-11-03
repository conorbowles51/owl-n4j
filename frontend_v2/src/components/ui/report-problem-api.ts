import { fetchAPI } from "@/lib/api-client"
import type { ReportSender } from "./report-problem"

/**
 * Report a problem (07 section 9): a button on every phone screen. The report holds the screen, the scope as kinds
 * and counts, the action chosen from a list, whether a refresh changes it, the build, the last request id, the
 * window size and the component ids of the area, plus an optional "What did you expect?". No screenshot is taken.
 * The text stays in the case's records; the team is told only ids, kinds, counts and the build.
 */

export const ACTIONS: { id: string; words: string }[] = [
  { id: "reading", words: "Reading records" },
  { id: "searching", words: "Searching" },
  { id: "filtering", words: "Filtering or choosing dates" },
  { id: "selecting", words: "Selecting rows" },
  { id: "adding-to", words: "Adding to a dossier, finding or note" },
  { id: "deciding", words: "Confirming or correcting" },
  { id: "copying", words: "Copying" },
  { id: "exporting", words: "Exporting" },
  { id: "opening-a-record", words: "Opening a record" },
  { id: "waiting", words: "Waiting for something to load" },
  { id: "other", words: "Something else" },
]

export function buildId(): string {
  const meta = typeof document !== "undefined" ? document.querySelector('meta[name="loupe-build"]')?.getAttribute("content") : null
  return meta && /^([0-9a-f]{7,64}|dev)$/.test(meta) ? meta : "dev"
}

export const sendReport: ReportSender = (caseId, report) =>
  fetchAPI(`/api/cases/${caseId}/ui-problem-reports`, { method: "POST", body: report })
