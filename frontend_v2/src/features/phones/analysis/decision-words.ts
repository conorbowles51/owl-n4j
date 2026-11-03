import type { AnalysisDecisionKind } from "./money-api"

/** The words a person's decision on an analysis result shows, in its history and on the result row. "Not pursued" is
 * a decision not to act (07 section 14): the lead may be right and is not being followed, for the reason given. */
export const DECISION_WORDS: Record<AnalysisDecisionKind, string> = {
  confirmed: "Confirmed", rejected: "Rejected", not_pursued: "Not pursued",
}
