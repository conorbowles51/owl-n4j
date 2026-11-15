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

/** Said until checked claims are written to the graph: a claim that passes the later check is marked checked, and
 * nothing adds it to the graph yet (followups 15 Nov: 1,812 passed in the Verification case, none in the graph). */
export const CHECKED_NOT_IN_GRAPH = "Claims that pass are marked checked, but are not added to the graph yet."
