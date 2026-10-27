/** The Table view's optional columns, off by default; every value is also in the row's Details and the drawer. */
export const OPTIONAL_COLUMNS = [
  ["reference", "Reference"],
  ["bank_reference", "Bank reference"],
  ["account", "Account"],
  ["balance", "Printed balance"],
  ["statement", "Statement"],
  ["proof", "How it was read"],
  ["currency", "Currency"],
] as const
export type OptionalColumn = (typeof OPTIONAL_COLUMNS)[number][0]
const COLUMNS_KEY = "financial-transactions-table-columns"
export function readTableColumns(): OptionalColumn[] {
  try {
    const saved = JSON.parse(localStorage.getItem(COLUMNS_KEY) || "[]")
    return Array.isArray(saved) ? OPTIONAL_COLUMNS.map(([key]) => key).filter((key) => saved.includes(key)) : []
  } catch {
    return []
  }
}
export function storeTableColumns(columns: OptionalColumn[]) {
  try {
    localStorage.setItem(COLUMNS_KEY, JSON.stringify(columns))
  } catch {
    // The choice still applies for this visit.
  }
}

