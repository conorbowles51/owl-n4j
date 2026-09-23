import type { LedgerTransaction } from "../api"
import {
  financialDraftKey,
  useFinancialDraftStore,
} from "../stores/financial-drafts"
import { useFinancialStore } from "../stores/financial.store"

/** Open an observed name without changing the investigation's account/date scope. */
export function openPaymentParty(
  caseId: string,
  row: LedgerTransaction,
  side: "from" | "to"
) {
  const store = useFinancialDraftStore.getState()
  const peopleKey = financialDraftKey(caseId, "investigator-people")
  const previous = (store.drafts[peopleKey] ?? {}) as Record<string, unknown>
  const mainView = useFinancialStore.getState().mainView
  store.put(financialDraftKey(caseId, "people-return"), {
    view: mainView,
    people: previous,
  })
  const ownAccount =
    side === "from" ? row.direction === "debit" : row.direction === "credit"
  const name =
    (side === "from" ? row.from_name : row.to_name) ??
    row.counterparty_raw ??
    ""
  store.put(peopleKey, {
    search: "",
    kind: "all",
    sort: "count",
    page: 0,
    ...previous,
    currencyGroup: "",
    selected: ownAccount
      ? `account:${row.canonical_account_id || row.account_id}`
      : row.counterparty_link
        ? `${row.counterparty_link.kind === "party" ? "owner" : "account"}:${row.counterparty_link.id}`
        : `name:${name}`,
  })
  useFinancialStore.getState().setMainView("counterparties")
}
