import { paymentInventory } from "../lib/payment-inventory"
import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { accountParties } from "../lib/account-parties"
import { AccountHistory } from "./AccountHistory"
import { AccountConsolidation } from "./AccountConsolidation"
import { useInvestigatorPayments } from "../hooks/use-investigator-payments"
import { useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import { useFinancialDraft } from "../stores/financial-drafts"
import {
  paymentProfiles,
  paymentGroup,
  minorAmount,
} from "../lib/investigator-workspace"
import { PaymentTotals } from "./InvestigationTransactionTable"
import {
  InvestigationReadState,
  WorkspaceHeading,
  WorkspaceScope,
} from "./InvestigationWorkspaceParts"
import { LedgerCounterpartiesAnalysis } from "./LedgerCounterpartiesAnalysis"
import type { FinancialMainView } from "../stores/financial.store"
import { useFinancialStore } from "../stores/financial.store"
import { useFinancialFindingIndex } from "../hooks/use-financial-finding-index"
import { LedgerRowBrowser } from "./LedgerRowBrowser"
import { LedgerSourceDialog } from "./LedgerSourceDialog"
import { unidentifiedGroups } from "../lib/unidentified-payments"
import type { LedgerTransaction } from "../api"

function UnidentifiedBreakdown({
  rows,
  detail = false,
}: {
  rows: LedgerTransaction[]
  detail?: boolean
}) {
  const groups = new Map<
    string,
    { label: string; reason: string; count: number }
  >()
  for (const group of unidentifiedGroups(rows)) {
    const previous = groups.get(group.kind)
    groups.set(group.kind, {
      label: group.label,
      reason: group.reason,
      count: (previous?.count ?? 0) + group.rows.length,
    })
  }
  return (
    <div className="rounded border bg-muted/20 p-3 text-sm space-y-2">
      <p className="font-medium">Why names are missing</p>
      <ul className="space-y-2">
        {[...groups.values()]
          .sort((a, b) => b.count - a.count)
          .map((group) => (
            <li key={group.label}>
              <span>
                {group.label}: <strong>{group.count}</strong>
              </span>
              {detail && (
                <p className="text-xs text-muted-foreground">{group.reason}</p>
              )}
            </li>
          ))}
      </ul>
      <p className="text-xs text-muted-foreground">
        These payments do not represent one person or business.
      </p>
    </div>
  )
}

export function InvestigatorPeople({ caseId }: { caseId: string }) {
  const data = useInvestigatorPayments(caseId)
  const directory = useQuery({
    queryKey: ["financial-ledger", caseId, "account-parties"],
    queryFn: async () => {
      const result = accountParties.parse(
        await fetchAPI(
          `/api/financial/account-parties?${new URLSearchParams({ case_id: caseId })}`
        )
      )
      if (result.case_id !== caseId)
        throw Error(
          "These account relationships belong to another case. Reload the directory."
        )
      return result
    },
  })
  const [source, setSource] = useState<string | null>(null)
  const [returnPath, , clearReturn] = useFinancialDraft<{
    view: FinancialMainView
    people: Record<string, unknown>
  } | null>(caseId, "people-return", null)
  const [view, setView] = useFinancialDraft(caseId, "investigator-people", {
    search: "",
    kind: "all",
    sort: "count",
    selected: "",
    page: 0,
    currencyGroup: "",
    profileScope: "owned_accounts",
    parentProfile: "",
  })
  const [, setFindingsView] = useFinancialDraft(caseId, "findings-list", {
    search: "",
    page: 0,
  })
  const currencyGroups = [...new Set(data.rows.map(paymentGroup))].sort()
  const scopedRows = useMemo(
    () =>
      data.rows.filter(
        (row) => !view.currencyGroup || paymentGroup(row) === view.currencyGroup
      ),
    [data.rows, view.currencyGroup]
  )
  const profiles = useMemo(
    () => paymentProfiles(scopedRows, directory.data?.accounts),
    [scopedRows, directory.data]
  )
  const total = (rows: typeof data.rows) =>
    rows.reduce((sum, row) => sum + (minorAmount(row.amount_minor) ?? 0n), 0n)
  const selectedAccount = view.selected.startsWith("account:")
    ? scopedRows.find((row) =>
        [row.account_id, ...(row.account_alias_ids ?? [])].includes(
          view.selected.slice(8)
        )
      )
    : undefined
  const selected = profiles.find(
    (profile) =>
      profile.id ===
      (selectedAccount?.canonical_account_id
        ? `account:${selectedAccount.canonical_account_id}`
        : view.selected)
  )
  const activeRows = selected
    ? view.profileScope === "counterparty_payments" && selected.kind !== "name"
      ? selected.counterpartyRows
      : selected.rows
    : []
  const activeInventory = paymentInventory(activeRows)
  const recentFindings = useFinancialFindingIndex(caseId)
  const selectedIds = new Set(activeRows.map((row) => row.key))
  const linked =
    recentFindings.data?.filter((entry) =>
      entry.payment_ids.some((id) => selectedIds.has(id))
    ) ?? []
  const filtered = profiles
    .filter(
      (profile) =>
        (view.kind === "all"
          ? !profile.nestedUnderOwner || profile.kind !== "account"
          : profile.kind === view.kind) &&
        profile.name.toLowerCase().includes(view.search.toLowerCase())
    )
    .sort((a, b) =>
      view.sort === "amount" && view.currencyGroup
        ? total(a.rows) > total(b.rows)
          ? -1
          : total(a.rows) < total(b.rows)
            ? 1
            : a.name.localeCompare(b.name)
        : view.sort === "name"
          ? a.name.localeCompare(b.name)
          : view.sort === "recent"
            ? (b.last || "").localeCompare(a.last || "")
            : b.rows.length - a.rows.length || a.name.localeCompare(b.name)
    )
  const page = Math.min(
    view.page,
    Math.max(0, Math.ceil(filtered.length / 30) - 1)
  )
  return (
    <div className="space-y-5 p-5">
      <WorkspaceHeading
        title="People & businesses"
        description="Follow a recorded name from its payments to the accounts, statements and findings behind it."
      />
      <WorkspaceScope caseId={caseId} />
      <AccountConsolidation caseId={caseId} />
      {directory.isPending && (
        <p role="status">Loading all accounts and confirmed relationships…</p>
      )}
      {directory.isError && (
        <p role="alert">
          The complete account directory could not be loaded.{" "}
          <Button variant="link" onClick={() => void directory.refetch()}>
            Reload accounts
          </Button>
        </p>
      )}
      {directory.isSuccess && (
        <InvestigationReadState data={data}>
          {selected ? (
            <>
              {returnPath && (
                <Button
                  variant="outline"
                  onClick={() => {
                    if (returnPath.view === "counterparties")
                      setView((current) => ({
                        ...current,
                        ...returnPath.people,
                      }))
                    useFinancialStore.getState().setMainView(returnPath.view)
                    clearReturn()
                  }}
                >
                  Back to{" "}
                  {returnPath.view === "transactions" ||
                  returnPath.view === "ledger"
                    ? "transactions"
                    : returnPath.view === "follow-money"
                      ? "Follow money"
                      : returnPath.view === "counterparties"
                        ? "previous name"
                        : returnPath.view}
                </Button>
              )}
              <Button
                variant="outline"
                onClick={() =>
                  setView((current) => ({
                    ...current,
                    selected: current.parentProfile || "",
                    parentProfile: "",
                    profileScope: "owned_accounts",
                  }))
                }
              >
                {view.parentProfile
                  ? "Back to person or business"
                  : "Back to names and accounts"}
              </Button>
              <div
                className="finance-panel rounded-xl border p-5 space-y-4"
                data-finance-tone={
                  selected.kind === "account" ? "info" : "work"
                }
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="finance-badge">
                      {selected.kind === "account"
                        ? "Account in these records"
                        : selected.kind === "owner"
                          ? "Reviewed account holder"
                          : selected.unidentified
                            ? "Payments to investigate"
                            : "Name as recorded in payments"}
                    </p>
                    <h3 className="mt-1 text-xl font-semibold">
                      {selected.unidentified
                        ? "Payments without an identified counterparty"
                        : selected.name}
                    </h3>
                  </div>
                  <Button
                    variant="outline"
                    onClick={() => {
                      setFindingsView({ search: selected.name, page: 0 })
                      useFinancialStore.getState().setMainView("findings")
                    }}
                  >
                    Search saved findings
                  </Button>
                </div>
                {selected.kind !== "name" && (
                  <div
                    className="flex flex-wrap gap-2"
                    aria-label="Profile payment scope"
                  >
                    <Button
                      variant={
                        view.profileScope !== "counterparty_payments"
                          ? "primary"
                          : "outline"
                      }
                      onClick={() =>
                        setView({ ...view, profileScope: "owned_accounts" })
                      }
                    >
                      Activity on{" "}
                      {selected.kind === "owner"
                        ? "owned accounts"
                        : "this account"}{" "}
                      ({selected.rows.length})
                    </Button>
                    <Button
                      variant={
                        view.profileScope === "counterparty_payments"
                          ? "primary"
                          : "outline"
                      }
                      onClick={() =>
                        setView({
                          ...view,
                          profileScope: "counterparty_payments",
                        })
                      }
                    >
                      As sender or beneficiary (
                      {selected.counterpartyRows.length})
                    </Button>
                  </div>
                )}
                <PaymentTotals
                  rows={activeRows}
                  label={
                    view.profileScope === "counterparty_payments" &&
                    selected.kind !== "name"
                      ? "Payments linked to this sender or beneficiary"
                      : selected.kind === "account"
                        ? "Activity on this account"
                        : selected.kind === "owner"
                          ? "Activity on linked accounts"
                          : selected.unidentified
                            ? "Payments with missing counterparty names"
                            : "Payments involving this recorded name"
                  }
                />
                <dl className="grid gap-4 text-sm sm:grid-cols-4">
                  <div>
                    <dt className="text-muted-foreground">
                      First dated payment
                    </dt>
                    <dd>{activeInventory.first || "Date not recorded"}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">
                      Last dated payment
                    </dt>
                    <dd>{activeInventory.last || "Date not recorded"}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">
                      Accounts with matching payments
                    </dt>
                    <dd>{activeInventory.accounts.length}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Source documents</dt>
                    <dd>
                      {
                        new Set(activeRows.map((row) => row.source_document_id))
                          .size
                      }
                    </dd>
                  </div>
                </dl>
                <AccountOwnershipReview
                  caseId={caseId}
                  accountIds={
                    selected.kind === "account" || selected.kind === "owner"
                      ? selected.accounts
                      : []
                  }
                  partyId={
                    selected.kind === "owner" ? selected.id.slice(6) : undefined
                  }
                  label="Review linked accounts"
                />
                {selected.kind === "owner" && (
                  <p className="rounded border p-3 text-sm">
                    {view.profileScope === "counterparty_payments"
                      ? "These entries link this person as sender or beneficiary. Amounts follow the original statement account's direction; they are not this person's account balance. The accounts where these payments were recorded are not ownership evidence."
                      : "This view includes activity within the recorded dates of confirmed holder relationships. Jointly held accounts can also appear on another holder’s profile; profiles are not additive."}
                  </p>
                )}
                {selected.unidentified && (
                  <UnidentifiedBreakdown rows={selected.rows} detail />
                )}
                {selected.kind === "name" && (
                  <p className="rounded border bg-muted/20 p-3 text-sm">
                    {selected.unidentified ? (
                      "These payments have no identified counterparty. They are not one person or business. Use the descriptions, references and originals to investigate each payment."
                    ) : (
                      <>
                        This name comes from the imported payment records. It
                        does not by itself identify the ultimate recipient, an
                        account owner or a verified person. Open the original
                        payment references before making that connection.
                      </>
                    )}
                  </p>
                )}
                {selected.kind === "owner" && (
                  <section
                    aria-label="Accounts belonging to this person or business"
                    className="space-y-2"
                  >
                    <h4 className="font-medium">
                      {selected.accountDetails.length} accounts linked to this
                      person or business
                    </h4>
                    <p className="text-xs text-muted-foreground">
                      All confirmed account links are listed, including accounts
                      with no matching payments. Account and date filters apply
                      to the activity below. Relationship dates remain visible.
                    </p>
                    {selected.accountDetails.map((account) => (
                      <div className="rounded border p-3" key={account.id}>
                        <Button
                          variant="link"
                          className="h-auto whitespace-normal break-words text-left justify-start"
                          onClick={() =>
                            setView({
                              ...view,
                              selected: `account:${account.id}`,
                              parentProfile: selected.id,
                              profileScope: "owned_accounts",
                            })
                          }
                        >
                          {account.label} ·{" "}
                          {account.currency || "Currency not recorded"}
                        </Button>
                        {account.relationships
                          .filter(
                            (link) =>
                              link.role === "holder" &&
                              link.party.id === selected.id.slice(6)
                          )
                          .map((link) => (
                            <p className="text-xs" key={link.id}>
                              Holder relationship:{" "}
                              {link.effective_from || "Start not specified"} to{" "}
                              {link.effective_to || "End not specified"}
                            </p>
                          ))}
                      </div>
                    ))}
                  </section>
                )}
                <details className="text-sm">
                  <summary className="cursor-pointer font-medium">
                    Accounts where these payments were recorded
                  </summary>
                  <ul className="space-y-2 pt-2">
                    {[
                      ...new Set(
                        activeRows.map(
                          (row) => row.canonical_account_id || row.account_id
                        )
                      ),
                    ].map((id) => (
                      <li key={id}>
                        {activeRows.find(
                          (row) =>
                            (row.canonical_account_id || row.account_id) === id
                        )?.account_label || "Account name not recorded"}
                      </li>
                    ))}
                  </ul>
                  {selected.kind !== "owner" && (
                    <p className="mt-2">
                      Recipient ownership and address: not established by this
                      grouping.
                    </p>
                  )}
                </details>
                {recentFindings.isError && (
                  <p role="alert" className="text-sm">
                    Saved finding links could not be loaded.{" "}
                    <button
                      className="underline"
                      onClick={() => void recentFindings.refetch()}
                    >
                      Reload finding links
                    </button>
                  </p>
                )}
                {linked.length > 0 && (
                  <div>
                    <h4 className="font-medium">
                      Findings linked to these payments
                    </h4>
                    <ul className="space-y-2 mt-2">
                      {linked.map((entry) => (
                        <li key={entry.id}>
                          <a
                            className="underline text-sm"
                            href={`/cases/${caseId}/workspace?view=casework&entry=${entry.id}`}
                          >
                            {entry.title || "Untitled finding"}
                          </a>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {recentFindings.isError && (
                  <p className="text-sm" role="alert">
                    Saved findings could not be checked. Open Findings to try
                    again.
                  </p>
                )}
              </div>
              {selected.kind === "account" && (
                <AccountHistory
                  caseId={caseId}
                  accountId={selected.id.slice(8)}
                />
              )}
              <LedgerRowBrowser
                key={`${selected.id}:${view.profileScope}`}
                investigation
                transactions={activeRows}
                exportContext={{
                  caseId,
                  params: data.params,
                  profile: {
                    id: selected.id,
                    group: view.currencyGroup,
                    scope:
                      selected.kind === "name"
                        ? undefined
                        : view.profileScope === "counterparty_payments"
                          ? "counterparty_payments"
                          : "owned_accounts",
                  },
                }}
                onSource={(row) => setSource(row.key)}
              />
              {source && (
                <LedgerSourceDialog
                  caseId={caseId}
                  transactionId={source}
                  onClose={() => setSource(null)}
                />
              )}
            </>
          ) : (
            <>
              <div className="flex flex-wrap gap-3 items-end">
                <label className="flex-1 min-w-52 text-sm">
                  Search names and accounts
                  <input
                    className="block w-full rounded border bg-card p-2"
                    value={view.search}
                    onChange={(e) =>
                      setView({ ...view, search: e.target.value, page: 0 })
                    }
                    placeholder="Name shown in a payment or account"
                  />
                </label>
                <label className="text-sm">
                  Show
                  <select
                    className="block rounded border bg-card p-2"
                    value={view.kind}
                    onChange={(e) =>
                      setView({ ...view, kind: e.target.value, page: 0 })
                    }
                  >
                    <option value="all">Names and accounts</option>
                    <option value="name">Payment names</option>
                    <option value="account">Accounts</option>
                    <option value="owner">Linked people and businesses</option>
                  </select>
                </label>
                <label className="text-sm">
                  Currency and account type
                  <select
                    aria-label="Profile currency and account type"
                    className="block rounded border bg-card p-2"
                    value={view.currencyGroup || ""}
                    onChange={(e) =>
                      setView({
                        ...view,
                        currencyGroup: e.target.value,
                        page: 0,
                      })
                    }
                  >
                    <option value="">All currencies and account types</option>
                    {currencyGroups.map((value) => (
                      <option key={value} value={value}>
                        {value.split(":")[0]} ·{" "}
                        {value.endsWith(":card")
                          ? "credit cards"
                          : "bank accounts"}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="text-sm">
                  Sort by
                  <select
                    className="block rounded border bg-card p-2"
                    value={view.sort}
                    onChange={(e) =>
                      setView({ ...view, sort: e.target.value, page: 0 })
                    }
                  >
                    <option value="count">Most payments</option>
                    <option value="amount" disabled={!view.currencyGroup}>
                      Largest total (one currency and type)
                    </option>
                    <option value="recent">Most recent activity</option>
                    <option value="name">Name</option>
                  </select>
                </label>
              </div>
              <p className="text-sm text-muted-foreground">
                {filtered.length} names and accounts. Account activity and
                payment names describe the same payments from different
                perspectives; their totals should not be added together.
              </p>
              {!filtered.length && (
                <div className="rounded border bg-card p-6">
                  <h3 className="font-semibold">
                    {data.rows.length
                      ? "No names match this search"
                      : "No imported payments in this scope"}
                  </h3>
                  <p className="mt-1 text-sm">
                    {data.rows.length
                      ? "Clear the search or change the accounts and dates."
                      : "Review a statement and confirm its import to start examining its payments."}
                  </p>
                </div>
              )}
              <div className="grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">
                {filtered.slice(page * 30, (page + 1) * 30).map((profile) => (
                  <button
                    key={profile.id}
                    onClick={() =>
                      setView((current) => ({
                        ...current,
                        selected: profile.id,
                        parentProfile: "",
                        profileScope:
                          profile.kind !== "name" &&
                          !profile.rows.length &&
                          profile.counterpartyRows.length
                            ? "counterparty_payments"
                            : "owned_accounts",
                      }))
                    }
                    className="finance-panel rounded-xl border p-4 text-left hover:border-primary focus-visible:outline-primary space-y-3"
                    data-finance-tone={
                      profile.kind === "account" ? "info" : "work"
                    }
                  >
                    <p className="finance-badge">
                      {profile.kind === "account"
                        ? "Account"
                        : profile.kind === "owner"
                          ? profile.accounts.length
                            ? "Reviewed account holder"
                            : "Linked person or business"
                          : profile.unidentified
                            ? "Payments to investigate"
                            : "Recorded payment name"}
                    </p>
                    <h3 className="text-base font-semibold break-words">
                      {profile.unidentified
                        ? "Counterparty not identified"
                        : profile.name}
                    </h3>
                    <p className="text-sm text-muted-foreground">
                      {profile.rows.length} payments · {profile.accounts.length}{" "}
                      {profile.accounts.length === 1 ? "account" : "accounts"} ·{" "}
                      {profile.sources.length} source documents
                    </p>
                    <PaymentTotals
                      expandAccounts={false}
                      rows={profile.rows}
                      label={
                        profile.kind === "owner"
                          ? "Activity on owned accounts"
                          : "Recorded amounts"
                      }
                    />
                    {profile.counterpartyRows.length > 0 && (
                      <p className="text-xs">
                        Also linked as sender or beneficiary on{" "}
                        {profile.counterpartyRows.length} payments. Open the
                        profile to view these separately.
                      </p>
                    )}
                    {profile.unidentified && (
                      <UnidentifiedBreakdown rows={profile.rows} />
                    )}
                    <p className="text-xs text-muted-foreground">
                      {profile.first || "Date unknown"} to{" "}
                      {profile.last || "date unknown"}
                    </p>
                    <span className="inline-block text-sm font-medium text-primary">
                      {profile.unidentified
                        ? "Investigate payments →"
                        : "Open profile →"}
                    </span>
                  </button>
                ))}
              </div>
              {filtered.length > 30 && (
                <div className="flex gap-3 items-center">
                  <Button
                    variant="outline"
                    disabled={!page}
                    onClick={() => setView({ ...view, page: page - 1 })}
                  >
                    Previous profiles
                  </Button>
                  <span>
                    {page * 30 + 1} to{" "}
                    {Math.min(filtered.length, (page + 1) * 30)} of{" "}
                    {filtered.length}
                  </span>
                  <Button
                    variant="outline"
                    disabled={(page + 1) * 30 >= filtered.length}
                    onClick={() => setView({ ...view, page: page + 1 })}
                  >
                    Next profiles
                  </Button>
                </div>
              )}
            </>
          )}
          <details className="rounded border bg-card p-4">
            <summary className="cursor-pointer font-medium">
              Link recorded names to a person or business
            </summary>
            <p className="mt-2 text-sm">
              Use the identity tools below when you have evidence that different
              names refer to the same person or business.
            </p>
            <LedgerCounterpartiesAnalysis caseId={caseId} />
          </details>
        </InvestigationReadState>
      )}
    </div>
  )
}
import { AccountOwnershipReview } from "./AccountOwnershipReview"
