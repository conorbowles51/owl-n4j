import { CategoryBreakdownTable } from "./ScopedCategoryBreakdown"
import { categoryTotals } from "../lib/category-totals"
import { Disclosure } from "./Disclosure"
import { paymentInventory } from "../lib/payment-inventory"
import { ProfileStatementSummary } from "./ProfileStatementSummary"
import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { accountParties } from "../lib/account-parties"
import { AccountHistory } from "./AccountHistory"
import { AccountConsolidation } from "./AccountConsolidation"
import { useInvestigatorPayments } from "../hooks/use-investigator-payments"
import { useEffect, useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import { downloadProtectedFile } from "@/lib/protected-file"
import { useFinancialDraft } from "../stores/financial-drafts"
import {
  paymentProfiles,
  paymentGroup,
  profileAccountGroup,
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
import { useLedgerPeopleView } from "../hooks/use-ledger-people-view"
import {
  profileCard,
  serverProfileCards,
  unidentifiedBreakdown,
  type ProfileCard,
} from "../lib/people-first-view"
import { PaymentTotalsView } from "./InvestigationTransactionTable"
import { ProfileStatementSummaryView } from "./ProfileStatementSummary"

function UnidentifiedBreakdown({
  groups,
  detail = false,
  caseId,
}: {
  /** unidentifiedBreakdown of the payments. */
  groups: { label: string; reason: string; count: number }[]
  detail?: boolean
  caseId?: string
}) {
  const [downloadError, setDownloadError] = useState<string | null>(null)
  return (
    <div className="rounded border bg-muted/20 p-3 text-sm space-y-2">
      <p className="font-medium">Why names are missing</p>
      <ul className="space-y-2">
        {[...groups]
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
      {caseId && (
        <div className="space-y-1">
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setDownloadError(null)
              void downloadProtectedFile(
                `/api/financial/ask-the-bank?${new URLSearchParams({ case_id: caseId })}`,
                `ask-the-bank-${caseId.slice(0, 8)}.csv`
              ).catch(() =>
                setDownloadError("The list could not be prepared. Try again.")
              )
            }}
          >
            Download what to ask the bank for
          </Button>
          <p className="text-xs text-muted-foreground">
            Every payment in this case with no name for the other side, with the line as printed and what the bank holds
            that the statement does not show.
          </p>
          {downloadError && <p className="text-xs text-destructive">{downloadError}</p>}
        </div>
      )}
    </div>
  )
}

type PeopleView = {
  search: string
  kind: string
  sort: string
  selected: string
  page: number
  currencyGroup: string
  profileScope: string
  parentProfile: string
}

/** The list of names and accounts: search, filters, sort and one card per profile (from the server's answer or the
 * browser's own grouping, the same cards). `pending`: a new choice is being worked out; its cards are not shown. */
function ProfileList({
  cards,
  rowCount,
  currencyGroups,
  view,
  setView,
  pending = false,
}: {
  cards: ProfileCard[]
  rowCount: number
  currencyGroups: string[]
  view: PeopleView
  setView: (next: PeopleView | ((previous: PeopleView) => PeopleView)) => void
  pending?: boolean
}) {
  const filtered = pending
    ? []
    : cards
        .filter(
          (profile) =>
            (view.kind === "all"
              ? !profile.nestedUnderOwner || profile.kind !== "account"
              : profile.kind === view.kind) &&
            (!view.currencyGroup ||
              profile.payments > 0 ||
              profile.counterpartyPayments > 0 ||
              profile.accountDetails.some(
                (account) => profileAccountGroup(account) === view.currencyGroup
              )) &&
            profile.name.toLowerCase().includes(view.search.toLowerCase())
        )
        .sort((a, b) =>
          view.sort === "amount" && view.currencyGroup
            ? a.amount > b.amount
              ? -1
              : a.amount < b.amount
                ? 1
                : a.name.localeCompare(b.name)
            : view.sort === "name"
              ? a.name.localeCompare(b.name)
              : view.sort === "recent"
                ? (b.last || "").localeCompare(a.last || "")
                : b.payments - a.payments || a.name.localeCompare(b.name)
        )
  const page = Math.min(
    view.page,
    Math.max(0, Math.ceil(filtered.length / 30) - 1)
  )
  if (pending)
    return (
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
        <p role="status" className="text-sm text-muted-foreground">
          Working out names and accounts…
        </p>
      </>
    )
  return (
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
            {rowCount
              ? "No names match this search"
              : "No imported payments in this scope"}
          </h3>
          <p className="mt-1 text-sm">
            {rowCount
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
                  !profile.payments &&
                  profile.counterpartyPayments
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
                ? profile.accountDetails.some(
                    (account) => account.registered
                  )
                  ? "Account"
                  : "Account reference"
                : profile.kind === "owner"
                  ? profile.accounts
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
              {profile.payments} matching payments
              {profile.kind === "name" && (
                <>
                  {" "}
                  · {profile.accounts}{" "}
                  {profile.accounts === 1
                    ? "account"
                    : "accounts"}{" "}
                  · {profile.sources} source documents
                </>
              )}
            </p>
            {profile.kind !== "name" && (
              <ProfileStatementSummaryView facts={profile} />
            )}
            {profile.totals ? (
              <PaymentTotalsView
                expandAccounts={false}
                {...profile.totals}
                label={
                  profile.kind === "owner"
                    ? "Activity on owned accounts"
                    : "Recorded amounts"
                }
              />
            ) : (
              <p className="text-xs">
                No matching imported payments. Open this profile to
                inspect saved statements and account history.
              </p>
            )}
            {profile.counterpartyPayments > 0 && (
              <p className="text-xs">
                Also linked as sender or beneficiary on{" "}
                {profile.counterpartyPayments} payments. Open the
                profile to view these separately.
              </p>
            )}
            {profile.unidentified && (
              <UnidentifiedBreakdown groups={profile.unidentifiedGroups ?? []} />
            )}
            <p className="text-xs text-muted-foreground">
              Payment dates:{" "}
              {profile.payments
                ? profile.first
                  ? `${profile.first} to ${profile.last}`
                  : "Not recorded"
                : "No matching payments"}
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
  )
}

const NO_PROFILES: ReturnType<typeof paymentProfiles> = []

export function InvestigatorPeople({ caseId }: { caseId: string }) {
  const [view, setView] = useFinancialDraft<PeopleView>(caseId, "investigator-people", {
    search: "",
    kind: "all",
    sort: "count",
    selected: "",
    page: 0,
    currencyGroup: "",
    profileScope: "owned_accounts",
    parentProfile: "",
  })
  // The list of names and accounts is the server's answer for the same payments (d5b330d1: 2 MB instead of every
  // payment, 64 MB). Every payment is read when a profile is opened, or when the server cannot answer (then the
  // page groups them as before). Once this scope's payments are read the list is the browser's own grouping of them
  // again: a name saved in an opened profile patches those rows in place (PaymentNamingPanel) and does not ask the
  // server again, so only the rows show it at once.
  const [rowsWanted, setRowsWanted] = useState(false)
  const data = useInvestigatorPayments(caseId, rowsWanted || !!view.selected)
  const rowsRead = data.complete && !data.query.isPlaceholderData
  const people = useLedgerPeopleView(
    caseId,
    data.params,
    data.categories,
    view.currencyGroup,
    !rowsWanted && !rowsRead
  )
  const serverFailed =
    people.isError ||
    (!!people.data &&
      !people.isPlaceholderData &&
      (!people.data.available || !people.data.complete))
  useEffect(() => {
    if (serverFailed) setRowsWanted(true)
  }, [serverFailed])
  const serverView =
    !rowsWanted && !rowsRead && people.data?.available && people.data.complete
      ? people.data
      : null
  const serverCards = useMemo(
    () => (serverView ? serverProfileCards(serverView.profiles) : null),
    [serverView]
  )
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
    // The server's list already holds what the cards show from the directory; the directory itself is read with
    // every payment (a profile opened, the server could not answer, or the payments are already read).
    enabled: rowsWanted || !!view.selected || rowsRead,
  })
  const [source, setSource] = useState<string | null>(null)
  const [returnPath, , clearReturn] = useFinancialDraft<{
    view: FinancialMainView
    people: Record<string, unknown>
  } | null>(caseId, "people-return", null)
  const [, setFindingsView] = useFinancialDraft(caseId, "findings-list", {
    search: "",
    page: 0,
  })
  const currencyGroups = [
    ...new Set([
      ...data.rows.map(paymentGroup),
      ...(directory.data?.accounts || []).flatMap((account) => {
        const group = profileAccountGroup({
          currency: account.currency,
          accountType: account.account_type || null,
        })
        return group ? [group] : []
      }),
    ]),
  ].sort()
  const scopedRows = useMemo(
    () =>
      data.rows.filter(
        (row) => !view.currencyGroup || paymentGroup(row) === view.currencyGroup
      ),
    [data.rows, view.currencyGroup]
  )
  // Grouped in its own task after the page has drawn, not inside the render that first shows the payments: on
  // d5b330d1 that render was one 0.45-0.8 s step (paymentProfiles 193 ms of it; fin-speed sourcemapped profile,
  // 2026-11-01), as Follow money's grouping was before it moved out (378d70a9). Until the profiles for this row
  // list and directory are worked out the list says so.
  const directoryAccounts = directory.data?.accounts
  type Grouped = {
    rows: typeof scopedRows
    accounts: typeof directoryAccounts
    profiles: ReturnType<typeof paymentProfiles>
    error?: unknown
  }
  const [grouped, setGrouped] = useState<Grouped | null>(null)
  // Only the first grouping waits for its own task (that is the render that first shows the payments). Later
  // changes (a currency filter, a refetch) group in the render as before, so the filters stay on screen.
  // With no payments there is nothing slow to wait for: the directory's accounts are grouped in the render.
  const inputsLoaded = data.complete && directory.isSuccess
  const deferFirst = scopedRows.length > 0
  const ready = grouped !== null || !deferFirst
  // Nothing is grouped until every payment is read (the list is the server's until then).
  const regrouped = useMemo(
    () =>
      !data.complete
        ? null
        : grouped === null
        ? deferFirst
          ? null
          : paymentProfiles(scopedRows, directoryAccounts)
        : grouped.error !== undefined
          ? null
        : grouped.rows === scopedRows && grouped.accounts === directoryAccounts
          ? grouped.profiles
          : paymentProfiles(scopedRows, directoryAccounts),
    [data.complete, grouped, deferFirst, scopedRows, directoryAccounts]
  )
  // The first grouping waits for every payment and the account directory, so it is the one that matters.
  useEffect(() => {
    if (ready || !inputsLoaded) return
    const timer = setTimeout(() => {
      // A failure is raised in the render, as it was when grouping ran there (the page's error boundary shows it),
      // never left as "Grouping…" for ever.
      let next: Grouped
      try {
        next = {
          rows: scopedRows,
          accounts: directoryAccounts,
          profiles: paymentProfiles(scopedRows, directoryAccounts),
        }
      } catch (error) {
        next = { rows: scopedRows, accounts: directoryAccounts, profiles: NO_PROFILES, error: error ?? Error("Grouping failed") }
      }
      setGrouped(next)
    }, 0)
    return () => clearTimeout(timer)
  }, [ready, inputsLoaded, scopedRows, directoryAccounts])
  if (grouped?.error !== undefined) throw grouped.error
  const profiles = regrouped ?? NO_PROFILES
  const selectedAccount = view.selected.startsWith("account:")
    ? scopedRows.find((row) =>
        [row.account_id, ...(row.account_alias_ids ?? [])].includes(
          view.selected.slice(8)
        )
      )
    : undefined
  const selectedDirectoryAccount = directory.data?.accounts.find(
    (account) => `account:${account.id}` === view.selected
  )
  const selected = profiles.find(
    (profile) =>
      profile.id ===
      (selectedDirectoryAccount?.canonical_id
        ? `account:${selectedDirectoryAccount.canonical_id}`
        : selectedAccount?.canonical_account_id
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
  // The browser's own cards, only where the list is drawn from them (the server could not answer).
  const browserList = !selected && !(serverCards && !view.selected)
  const browserCards = useMemo(
    () => (browserList ? profiles.map(profileCard) : []),
    [browserList, profiles]
  )
  const identityTools = (
    <Disclosure className="rounded border bg-card p-4" label="Link recorded names to a person or business">
      <p className="mt-2 text-sm">
        Use the identity tools below when you have evidence that different
        names refer to the same person or business.
      </p>
      <LedgerCounterpartiesAnalysis caseId={caseId} />
    </Disclosure>
  )
  return (
    <div className="space-y-5 p-5">
      <WorkspaceHeading
        title="People & businesses"
        description="Follow a recorded name from its payments to the accounts, statements and findings behind it."
      />
      <WorkspaceScope caseId={caseId} />
      <AccountConsolidation caseId={caseId} />
      {serverView && serverCards && !view.selected ? (
        <>
          <ProfileList
            cards={serverCards}
            rowCount={serverView.row_count}
            currencyGroups={[
              ...new Set([...serverView.row_groups, ...serverView.directory_groups]),
            ].sort()}
            view={view}
            setView={setView}
            pending={people.isPlaceholderData}
          />
          {identityTools}
        </>
      ) : !rowsWanted && !view.selected && !rowsRead ? (
        <p role="status" className="text-sm text-muted-foreground">
          Loading names and accounts…
        </p>
      ) : (
      <>
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
          {!ready ? (
            <p role="status" className="text-sm text-muted-foreground">
              Grouping {scopedRows.length.toLocaleString("en-US")}{" "}
              {scopedRows.length === 1 ? "payment" : "payments"} by name and
              account…
            </p>
          ) : selected ? (
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
                <div
                  className="-mx-5 -mt-5 flex flex-wrap items-start justify-between gap-3 rounded-t-xl p-5 text-white"
                  style={{
                    background:
                      "radial-gradient(1100px 420px at 90% -20%, #3a1319 0%, #0b0c0f 62%)",
                  }}
                >
                  <div>
                    <p className="finance-badge">
                      {selected.kind === "account"
                        ? selected.accountDetails.some(
                            (account) => account.registered
                          )
                          ? "Registered account"
                          : "Account reference"
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
                {selected.kind !== "name" && (
                  <ProfileStatementSummary profile={selected} />
                )}
                {activeRows.length > 0 ? (
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
                ) : (
                  <p className="rounded border p-3 text-sm">
                    No matching imported payments in this view.{" "}
                    {selected.kind === "owner"
                      ? selected.accountDetails.length
                        ? "Open one of the linked accounts below to inspect its saved statements and history."
                        : "No owned accounts are linked to this person. Sender or beneficiary links can be viewed separately."
                      : "Saved statements can still record balances or activity awaiting review; inspect the account history below."}
                  </p>
                )}
                <dl className="grid gap-4 text-sm sm:grid-cols-4">
                  <div>
                    <dt className="text-muted-foreground">
                      First dated payment
                    </dt>
                    <dd>
                      {activeRows.length
                        ? activeInventory.first || "Date not recorded"
                        : "No matching payments"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">
                      Last dated payment
                    </dt>
                    <dd>
                      {activeRows.length
                        ? activeInventory.last || "Date not recorded"
                        : "No matching payments"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">
                      Accounts with matching payments
                    </dt>
                    <dd>{activeInventory.accounts.length}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">
                      Sources of matching payments
                    </dt>
                    <dd>
                      {
                        new Set(activeRows.map((row) => row.source_document_id))
                          .size
                      }
                    </dd>
                  </div>
                </dl>
                {activeRows.length > 0 && (
                  <CategoryBreakdownTable
                    title="Categories in these payments"
                    rows={categoryTotals(activeRows)}
                  />
                )}
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
                  <UnidentifiedBreakdown groups={unidentifiedBreakdown(selected.rows)} detail caseId={caseId} />
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
                <Disclosure className="text-sm" label={`Accounts where these payments were recorded (${new Set(activeRows.map((row) => row.canonical_account_id || row.account_id)).size})`}>
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
                </Disclosure>
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
            <ProfileList
              cards={browserCards}
              rowCount={data.rows.length}
              currencyGroups={currencyGroups}
              view={view}
              setView={setView}
            />
          )}
          {identityTools}
        </InvestigationReadState>
      )}
      </>
      )}
    </div>
  )
}
import { AccountOwnershipReview } from "./AccountOwnershipReview"
