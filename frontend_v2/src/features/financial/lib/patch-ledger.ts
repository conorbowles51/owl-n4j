import type { QueryClient } from "@tanstack/react-query"
import type { LedgerTransaction } from "../api"

/** Replace rows in every cached ledger read of this case, so the table and counts follow a save at once. */
export function patchLedger(client: QueryClient, caseId: string, replacements: LedgerTransaction[]) {
  const byId = new Map(replacements.map((row) => [row.key, row]))
  client.setQueriesData<{ transactions: LedgerTransaction[] }>({ queryKey: ["financial-ledger", caseId] }, (data) =>
    data?.transactions ? { ...data, transactions: data.transactions.map((row) => byId.get(row.key) ?? row) } : data
  )
}
