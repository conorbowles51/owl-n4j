import type { QueryClient } from "@tanstack/react-query"
import type { LedgerTransaction } from "../api"

type Cached = { transactions?: LedgerTransaction[]; rows?: LedgerTransaction[] }

/**
 * Replace rows where they stand in every cached ledger read of this case: the full list (`transactions`) and the
 * large-ledger first view (`rows`). ``byOldKey`` maps the key on screen to the row that replaces it (a corrected
 * payment is a new row with a new key). Nothing is read again here.
 */
export function replaceLedgerRows(client: QueryClient, caseId: string, byOldKey: Map<string, LedgerTransaction>) {
  client.setQueriesData<Cached>({ queryKey: ["financial-ledger", caseId] }, (data) => {
    if (!data || typeof data !== "object") return data
    const swap = (list?: LedgerTransaction[]) => list?.map((row) => byOldKey.get(row.key) ?? row)
    return {
      ...data,
      ...(Array.isArray(data.transactions) ? { transactions: swap(data.transactions) } : {}),
      ...(Array.isArray(data.rows) ? { rows: swap(data.rows) } : {}),
    }
  })
}

/** Replace rows in every cached ledger read of this case, so the table and counts follow a save at once. */
export function patchLedger(client: QueryClient, caseId: string, replacements: LedgerTransaction[]) {
  replaceLedgerRows(client, caseId, new Map(replacements.map((row) => [row.key, row])))
}
