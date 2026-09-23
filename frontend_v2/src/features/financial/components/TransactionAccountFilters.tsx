import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { holderKey } from "../lib/account-holder"
import {
  selectedAccountIds,
  type AccountSelection,
} from "../lib/account-selection"
import {
  candidateAccounts,
  candidateUrl,
  assertCandidateScope,
} from "../lib/candidate-contract"
import { AccountMultiSelect } from "./AccountMultiSelect"
import { AccountOwnershipReview } from "./AccountOwnershipReview"

export function TransactionAccountFilters({
  caseId,
  selection,
  onChange,
}: {
  caseId: string
  selection: AccountSelection
  onChange: (values: AccountSelection) => void
}) {
  const query = useQuery({
    queryKey: ["financial-ledger", caseId, "account-filter-directory"],
    queryFn: async () => {
      const items = []
      let offset = 0
      for (;;) {
        const data = candidateAccounts.parse(
          await fetchAPI(
            `${candidateUrl("ledger-accounts", caseId)}&offset=${offset}`
          )
        )
        assertCandidateScope(data, caseId)
        items.push(...data.items)
        if (!data.has_more) return items
        if (!data.items.length)
          throw Error("The account list could not be fully loaded.")
        offset += data.items.length
      }
    },
  })
  const holders = new Map<string, string>()
  const accounts = new Map<string, string>()
  for (const account of query.data ?? []) {
    const holder = holderKey(account.holder ?? undefined)
    if (holder) holders.set(holder, account.holder!.trim().replace(/\s+/g, " "))
    if (account.party) holders.set(`party:${account.party.id}`, `${account.party.name} · linked accounts`)
    for (const party of account.holder_parties) holders.set(`party:${party.id}`, `${party.name} · reviewed holder`)
    accounts.set(
      account.id,
      [
        account.display_label ||
          [account.holder, account.institution, account.identifier]
            .filter(Boolean)
            .join(" · ") ||
          account.id,
        account.currency,
      ]
        .filter(Boolean)
        .join(" · ")
    )
  }
  const options = (values: Map<string, string>) =>
    [...values]
      .sort((a, b) => a[1].localeCompare(b[1]))
      .map(([value, label]) => ({ value, label }))
  return (
    <section aria-label="Filter imported accounts" className="w-full space-y-2">
      <div className="flex flex-wrap items-start gap-3">
        <AccountMultiSelect
          label="Person or company"
          allLabel="All account holders"
          options={options(holders)}
          selected={selection.accountHolders ?? []}
          onChange={(accountHolders) =>
            onChange({ ...selection, accountHolders })
          }
        />
        <AccountMultiSelect
          label="Bank account"
          allLabel="All accounts, across banks"
          options={options(accounts)}
          selected={selectedAccountIds(selection)}
          onChange={(accountIds) =>
            onChange({ ...selection, accountId: undefined, accountIds })
          }
        />
      </div>
      <AccountOwnershipReview caseId={caseId} accountIds={selectedAccountIds(selection)} onChoose={partyId =>
        onChange({...selection, accountId:undefined, accountIds:[], accountHolders:[`party:${partyId}`]})} />
      {selection.accountHolders?.length ||
      selectedAccountIds(selection).length ? (
        <p className="text-xs text-muted-foreground">
          Matches any selected person or company and any selected account.
          People include their accounts across banks. These account filters
          follow you across Financial.
        </p>
      ) : null}
      {query.isPending && <p role="status">Loading accounts…</p>}
      {query.isError && (
        <p role="alert">
          The account list could not be loaded.{" "}
          <button
            type="button"
            className="underline"
            onClick={() => void query.refetch()}
          >
            Try again
          </button>
        </p>
      )}
    </section>
  )
}
