/** Claims drawn from a file that were never checked against its text (backend routers/claim_checks.py). */
export interface UncheckedClaims {
  case_id: string
  unchecked: number
  files: { evidence_file_id: string; filename: string | null; unchecked: number }[]
}

export function uncheckedClaimsText(count: number) {
  return count === 1
    ? "1 claim drawn from this file was not checked against its text, so it is not in the graph."
    : `${count.toLocaleString()} claims drawn from this file were not checked against their text, so they are not in the graph.`
}

/** A claim that passes the later check joins the graph on the people and things its file already placed, when the
 * check ends (evidence-engine services/checked_claims_graph.py). */
export const CHECKED_NOT_IN_GRAPH = "Claims that pass are added to the graph when the check ends."
