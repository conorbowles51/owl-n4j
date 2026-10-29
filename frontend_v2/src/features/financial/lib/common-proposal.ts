/** What commonProposal reads of a listed statement. */
type ProposalStatement = {
  values: Record<string, string>
  proposals?: Record<string, { value: string; label: string }>
}

/** The one value proposed for a field to every listed statement that lacks it, or null. */
export function commonProposal(items: ProposalStatement[], field: string) {
  const lacking = items.filter((item) => !item.values[field]?.trim())
  if (!lacking.length) return null
  const proposals = lacking.map((item) => item.proposals?.[field])
  if (proposals.some((proposal) => !proposal)) return null
  const values = new Set(proposals.map((proposal) => proposal!.value))
  if (values.size !== 1) return null
  const labels = new Set(proposals.map((proposal) => proposal!.label))
  return {
    value: proposals[0]!.value,
    label: labels.size === 1 ? proposals[0]!.label : "the case's saved statements",
    statements: lacking.length,
  }
}
