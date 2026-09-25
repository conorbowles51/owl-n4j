import { useFinancialStore } from "../stores/financial.store"
import { useLedgerAccountDirectory } from "../hooks/use-ledger-account-directory"
import { holderKey } from "../lib/account-holder"
import {
  selectedAccountIds,
  bankKey,
  type AccountSelection,
} from "../lib/account-selection"
import { AccountMultiSelect } from "./AccountMultiSelect"
import { AccountOwnershipReview } from "./AccountOwnershipReview"
import { Button } from "@/components/ui/button"

export function TransactionAccountFilters({
  caseId,
  selection,
  onChange,
}: {
  caseId: string
  selection: AccountSelection
  onChange: (values: AccountSelection) => void
}) {
  const query = useLedgerAccountDirectory(caseId)
  const holders = new Map<string, string>()
  const accounts = new Map<string, string>()
  const banks = new Map<string, string>()
  const unresolved = new Map<string, string>()
  const selectedBanks = (selection.accountHolders ?? []).filter((value) =>
    value.startsWith("bank:")
  )
  const selectedPeople = (selection.accountHolders ?? []).filter(
    (value) => !value.startsWith("bank:")
  )
  for (const account of query.data?.items ?? []) {
    if (account.institution)
      banks.set(
        `bank:${bankKey(account.institution)}`,
        account.institution.trim()
      )
    const holder = holderKey(account.holder ?? undefined)
    if (holder) holders.set(holder, account.holder!.trim().replace(/\s+/g, " "))
    if (account.party)
      holders.set(
        `party:${account.party.id}`,
        `${account.party.name} · linked accounts`
      )
    for (const party of account.holder_parties)
      holders.set(`party:${party.id}`, `${party.name} · reviewed holder`)
    const canonicalId = account.canonical_id || account.id
    if (canonicalId !== account.id) continue
    if (
      selectedBanks.length &&
      !selectedBanks.includes(`bank:${bankKey(account.institution)}`) &&
      !selectedAccountIds(selection).includes(account.id)
    )
      continue
    const destination =
      account.provisional || !account.identifier ? unresolved : accounts
    destination.set(
      account.id,
      [
        [
          account.institution || "Bank not identified",
          account.identifier || "Account number not identified",
          account.holder,
        ]
          .filter(Boolean)
          .join(" · "),
        account.provisional
          ? `Details need review · ${account.id.slice(0, 8)}`
          : "",
        account.currency,
      ]
        .filter(Boolean)
        .join(" · ")
    )
  }
  for (const item of query.data?.pending ?? []) {
    if (!holders.has(holderKey(item.name)))
      holders.set(
        holderKey(item.name),
        `${item.name} · statements awaiting import`
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
          selected={selectedPeople}
          onChange={(accountHolders) =>
            onChange({
              ...selection,
              accountHolders: [...accountHolders, ...selectedBanks],
            })
          }
        />
        <AccountMultiSelect
          label="Bank"
          allLabel="All banks"
          options={options(banks)}
          selected={selectedBanks}
          onChange={(values) =>
            onChange({
              ...selection,
              accountHolders: [...selectedPeople, ...values],
            })
          }
        />
        <AccountMultiSelect
          label="Bank account"
          allLabel="All accounts, across banks"
          options={options(accounts)}
          selected={[
            ...new Set(
              selectedAccountIds(selection).map(
                (id) =>
                  query.data?.items.find((a) => a.id === id)?.canonical_id || id
              )
            ),
          ]}
          onChange={(accountIds) =>
            onChange({ ...selection, accountId: undefined, accountIds })
          }
        />
      </div>
      {!!unresolved.size && (
        <details>
          <summary>{unresolved.size} accounts need identifying</summary>
          <p className="text-xs">
            These records do not yet have a confirmed account number. Review
            their statement details before merging.
          </p>
          <AccountMultiSelect
            label="Accounts needing identification"
            allLabel="All unresolved accounts"
            options={options(unresolved)}
            selected={selectedAccountIds(selection).filter((id) =>
              unresolved.has(id)
            )}
            onChange={(ids) =>
              onChange({
                ...selection,
                accountId: undefined,
                accountIds: [
                  ...selectedAccountIds(selection).filter(
                    (id) => !unresolved.has(id)
                  ),
                  ...ids,
                ],
              })
            }
          />
        </details>
      )}
      {!!query.data?.pending.length && (
        <p className="text-xs text-muted-foreground">
          Some companies have statements awaiting import. Selecting them may
          show no payments yet.{" "}
          <Button
            variant="link"
            size="sm"
            onClick={() =>
              useFinancialStore.getState().setMainView("statements")
            }
          >
            Review statements
          </Button>
        </p>
      )}
      {query.data?.pendingTruncated && (
        <p role="status">
          More statements await review than can be listed here. Open Statements
          & accounts to review the complete batches.
        </p>
      )}
      <Button
        variant="ghost"
        size="sm"
        disabled={
          !selection.accountHolders?.length &&
          !selectedAccountIds(selection).length
        }
        onClick={() =>
          onChange({
            ...selection,
            accountId: undefined,
            accountIds: [],
            accountHolders: [],
          })
        }
      >
        Clear account filters
      </Button>
      <AccountOwnershipReview
        caseId={caseId}
        accountIds={selectedAccountIds(selection)}
        onChoose={(partyId) =>
          onChange({
            ...selection,
            accountId: undefined,
            accountIds: [],
            accountHolders: [`party:${partyId}`, ...selectedBanks],
          })
        }
      />
      {selection.accountHolders?.length ||
      selectedAccountIds(selection).length ? (
        <p className="text-xs text-muted-foreground">
          Matches the selected people or companies, banks and accounts together.
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
