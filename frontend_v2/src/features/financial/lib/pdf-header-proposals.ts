// Exact vocabulary matches are suggestions, never transaction/header classification.
const labels: Record<string, [string, string]> = {
  amount: ["amount", "Amount"],
  debit: ["debit", "Money out"],
  debits: ["debit", "Money out"],
  credit: ["credit", "Money in"],
  credits: ["credit", "Money in"],
  date: ["date", "Date (type not identified)"],
  "trans date": ["transaction_date", "Transaction date"],
  "post date": ["booking_date", "Booking date"],
  "booking date": ["booking_date", "Booking date"],
  "posting date": ["booking_date", "Booking date"],
  "posted date": ["booking_date", "Booking date"],
  "value date": ["value_date", "Value date"],
  "transaction date": ["transaction_date", "Transaction date"],
  description: ["description", "Description"],
  reference: ["reference", "Reference"],
  balance: ["balance", "Balance"],
  currency: ["currency", "Currency"],
  "account number": ["account", "Account"],
}
export function proposePdfHeaders(
  rows: {
    row_index: number
    cells: { column_index: number; expected_text: string }[]
  }[]
) {
  const found: {
    row: number
    column: number
    text: string
    meaning: string
    label: string
  }[] = []
  const seen = new Set<string>()
  for (const row of rows.slice(0, 10)) {
    for (const cell of row.cells) {
      const normalized = cell.expected_text
        .trim()
        .toLowerCase()
        .replace(/\s+/g, " ")
      // Do not repair OCR or search substrings such as "opening balance".
      if (!Object.hasOwn(labels, normalized)) continue
      const [meaning, label] = labels[normalized]
      const key = `${cell.column_index}:${meaning}`
      if (seen.has(key)) continue
      seen.add(key)
      found.push({
        row: row.row_index,
        column: cell.column_index,
        text: cell.expected_text,
        meaning,
        label,
      })
    }
  }
  return {
    proposals: found,
    checkedRows: Math.min(rows.length, 10),
    hasMore: rows.length > 10,
  }
}
