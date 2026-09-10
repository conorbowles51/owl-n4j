/** Exact printed labels nominate source cells, never numeric readings or scope. */
const labels: Record<string, string[]> = {
  "opening balance": [
    "opening balance",
    "beginning balance",
    "previous balance",
    "balance brought forward",
  ],
  "closing balance": [
    "closing balance",
    "ending balance",
    "new balance",
    "balance carried forward",
  ],
  "total money in": [
    "total credits",
    "total deposits",
    "total money in",
    "total incoming",
  ],
  "total money out": [
    "total debits",
    "total withdrawals",
    "total money out",
    "total outgoing",
  ],
  "statement start": [
    "statement start",
    "statement start date",
    "period start",
    "statement period",
    "period covered",
  ],
  "statement end": [
    "statement end",
    "statement end date",
    "period end",
    "statement period",
    "period covered",
  ],
}
export function proposeStatementControls<
  T extends { column_index: number; expected_text: string; locator: unknown },
>(rows: Array<{ row_index: number; cells: T[] }>, role: string) {
  const accepted = labels[role] ?? []
  const proposals: Array<{ row: number; label: T; values: T[] }> = []
  for (const row of rows) {
    const matching = row.cells.filter((c) =>
      accepted.includes(
        c.expected_text
          .toLowerCase()
          .trim()
          .replace(/\s+/g, " ")
          .replace(/:$/, "")
      )
    )
    if (matching.length !== 1) continue
    const values: T[] = []
    for (const cell of [...row.cells].sort(
      (a, b) => a.column_index - b.column_index
    )) {
      if (cell.column_index <= matching[0].column_index) continue
      const text = cell.expected_text.trim()
      const possibleValue =
        /[0-9]/.test(text) &&
        (role.startsWith("statement ") || /^[\s$€£¥()+−\-=0-9.,]+$/.test(text))
      // Stop at another label; a horizontal line may span unrelated panels.
      if (!possibleValue) break
      values.push(cell)
    }
    if (values.length)
      proposals.push({ row: row.row_index, label: matching[0], values })
  }
  return proposals
}
