/** Spreadsheet statements: which files are read with a column mapping, and editing that mapping. */
import { SPREADSHEET_ROLES, type SpreadsheetLayout, type SpreadsheetRole } from "../api"

const SPREADSHEET_ENDINGS = [".csv", ".tsv", ".xlsx", ".xlsm", ".xls"]

/** A CSV or Excel file: read with a column mapping a person checks, not as a bank file format. */
export function isSpreadsheetName(name: string | null): boolean {
  const lowered = (name ?? "").toLowerCase()
  return SPREADSHEET_ENDINGS.some((ending) => lowered.endsWith(ending))
}

export const ROLE_LABELS: Record<SpreadsheetRole, string> = {
  date: "Date",
  posted_date: "Posting date",
  description: "Description",
  memo: "Note",
  amount: "Amount (one column, signed)",
  debit: "Money out",
  credit: "Money in",
  balance: "Balance",
  type: "Type",
  status: "Status",
  counterparty: "Other party",
  from_party: "Sender",
  to_party: "Receiver",
  reference: "Reference or check number",
  currency: "Currency",
  account: "Account",
}

/** The role a column has in a layout, or null when the column is not used. */
export function roleOfColumn(layout: SpreadsheetLayout, column: number): SpreadsheetRole | null {
  for (const role of SPREADSHEET_ROLES) {
    if (layout.columns[role] === column) return role
  }
  return null
}

/** The layout with one column given a role (taken from any column that had it), or no role. */
export function withColumnRole(
  layout: SpreadsheetLayout,
  column: number,
  role: SpreadsheetRole | null
): SpreadsheetLayout {
  const columns = { ...layout.columns }
  for (const r of SPREADSHEET_ROLES) {
    if (columns[r] === column) columns[r] = null
  }
  if (role) columns[role] = column
  return { ...layout, columns }
}

