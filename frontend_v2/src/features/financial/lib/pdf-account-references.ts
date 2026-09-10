export type AccountReferenceCell = {
  row: number
  column: number
  text: string
  locator: unknown
  reference: string
  partial: boolean
}
const labelPattern =
  /(?:^|\b)(account\s+(?:number|no\.?|ending(?:\s+in)?)|card\s+(?:number|no\.?|ending(?:\s+in)?))\s*[:#]?\s*$/i
const inlinePattern =
  /(?:^|\b)(account\s+(?:number|no\.?|ending(?:\s+in)?)|card\s+(?:number|no\.?|ending(?:\s+in)?))\s*[:#]?\s+([\dXx*][\dXx* -]*\d)\s*$/i
function supported(value: string) {
  return (
    /^[\dXx*][\dXx* -]*\d$/.test(value) &&
    value.replace(/[^\d]/g, "").length >= 4 &&
    value.replace(/[ -]/g, "").length <= 34
  )
}
export function proposePdfAccountReferences(
  rows: {
    row_index: number
    cells: { column_index: number; expected_text: string; locator: unknown }[]
  }[]
) {
  const references: AccountReferenceCell[] = []
  for (const row of rows.slice(0, 30))
    for (const cell of row.cells) {
      const inline = cell.expected_text.match(inlinePattern)
      const label = cell.expected_text.match(labelPattern)
      const next = label
        ? row.cells.find((c) => c.column_index === cell.column_index + 1)
        : undefined
      const value = inline?.[2]?.trim() ?? next?.expected_text.trim()
      if (!value || !supported(value)) continue
      const origin = inline ? cell : next!
      references.push({
        row: row.row_index,
        column: origin.column_index,
        text: origin.expected_text,
        locator: origin.locator,
        reference: value,
        partial:
          /ending/i.test(inline?.[1] ?? label?.[1] ?? "") ||
          /[Xx*]/.test(value) ||
          value.replace(/\D/g, "").length <= 4,
      })
    }
  return {
    references,
    checkedRows: Math.min(30, rows.length),
    hasMore: rows.length > 30,
    distinctReferences: new Set(
      references.map((r) => r.reference.replace(/[ -]/g, "").toUpperCase())
    ).size,
  }
}
