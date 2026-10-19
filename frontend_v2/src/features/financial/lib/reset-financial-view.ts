import {
  financialDraftKey,
  useFinancialDraftStore,
} from "../stores/financial-drafts"
import { showAllImportedPayments } from "./payment-table-draft"

// Reset presentation state only. Never clear statement corrections, notes,
// unfinished finding/report editors or case records.
export function resetFinancialView(caseId: string, tab: string) {
  const prefixes: Record<string, string[]> = {
    transactions: [
      "payment-table:",
      "selected-payments",
      "open-payment:investigation",
    ],
    counterparties: ["investigator-people", "people-return", "payment-table:"],
    "follow-money": ["investigator-follow-money"],
    trends: ["investigation-trends-v2"],
    findings: ["findings-list"],
  }
  const store = useFinancialDraftStore.getState()
  const prefix = financialDraftKey(caseId, "")
  for (const key of Object.keys(store.drafts)) {
    if (!key.startsWith(prefix)) continue
    const name = key.slice(prefix.length)
    if (
      tab === "counterparties" &&
      name.startsWith("payment-table:") &&
      !name.includes(":profile:")
    )
      continue
    if (tab === "transactions" && name.includes(":profile:")) continue
    if ((prefixes[tab] ?? []).some((value) => name.startsWith(value)))
      store.remove(key)
  }
  if (tab === "transactions") showAllImportedPayments(caseId)
}
