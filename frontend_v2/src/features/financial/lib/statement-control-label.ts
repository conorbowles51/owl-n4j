export function statementControlLabel(
  kind: string,
  fields: Record<string, string> = {}
) {
  if (kind !== "statement_total") return "Printed balance"
  if (fields.total_scope === "fee") return "Printed fee total"
  if (fields.total_scope === "interest") return "Printed interest total"
  if (fields.total_direction === "credit") return "Printed credit total"
  if (fields.total_direction === "debit") return "Printed debit total"
  return "Printed total"
}

export function statementControlInputLabel(
  kind: string,
  fields: Record<string, string> = {}
) {
  return `Corrected ${statementControlLabel(kind, fields).toLowerCase()}`
}
