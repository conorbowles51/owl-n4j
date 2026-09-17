import { useInvestigatorPayments } from "../hooks/use-investigator-payments"
import { useMemo } from "react"
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
  PaymentSet,
  WorkspaceHeading,
  WorkspaceScope,
} from "./InvestigationWorkspaceParts"
import { LedgerCounterpartiesAnalysis } from "./LedgerCounterpartiesAnalysis"
import { useFinancialStore } from "../stores/financial.store"
import { useFinancialFindingIndex } from "../hooks/use-financial-finding-index"

export function InvestigatorPeople({ caseId }: { caseId: string }) {
  const data = useInvestigatorPayments(caseId)
  const [view, setView] = useFinancialDraft(caseId, "investigator-people", {
    search: "",
    kind: "all",
    sort: "count",
    selected: "",
    page: 0,
    currencyGroup: "",
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
  const profiles = useMemo(() => paymentProfiles(scopedRows), [scopedRows])
  const total = (rows: typeof data.rows) =>
    rows.reduce((sum, row) => sum + (minorAmount(row.amount_minor) ?? 0n), 0n)
  const selected = profiles.find((profile) => profile.id === view.selected)
  const recentFindings = useFinancialFindingIndex(caseId)
  const selectedIds = new Set(selected?.rows.map((row) => row.key))
  const linked =
    recentFindings.data?.filter((entry) =>
      entry.payment_ids.some((id) => selectedIds.has(id))
    ) ?? []
  const filtered = profiles
    .filter(
      (profile) =>
        (view.kind === "all" || profile.kind === view.kind) &&
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
      <InvestigationReadState data={data}>
        {selected ? (
          <>
            <Button
              variant="outline"
              onClick={() =>
                setView((current) => ({ ...current, selected: "" }))
              }
            >
              Back to names and accounts
            </Button>
            <div
              className="finance-panel rounded-xl border p-5 space-y-4"
              data-finance-tone={selected.kind === "account" ? "info" : "work"}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="finance-badge">
                    {selected.kind === "account"
                      ? "Account in these records"
                      : "Name as recorded in payments"}
                  </p>
                  <h3 className="mt-1 text-xl font-semibold">
                    {selected.name}
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
              <PaymentTotals
                rows={selected.rows}
                label={
                  selected.kind === "account"
                    ? "Activity on this account"
                    : "Payments involving this recorded name"
                }
              />
              <dl className="grid gap-4 text-sm sm:grid-cols-4">
                <div>
                  <dt className="text-muted-foreground">First dated payment</dt>
                  <dd>{selected.first || "Date not recorded"}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Last dated payment</dt>
                  <dd>{selected.last || "Date not recorded"}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Accounts involved</dt>
                  <dd>{selected.accounts.length}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Source documents</dt>
                  <dd>{selected.sources.length}</dd>
                </div>
              </dl>
              {selected.kind === "name" && (
                <p className="rounded border bg-muted/20 p-3 text-sm">
                  This name comes from the imported payment records. It does not
                  by itself identify the ultimate recipient, an account owner or
                  a verified person. Open the original payment references before
                  making that connection.
                </p>
              )}
              <details className="text-sm">
                <summary className="cursor-pointer font-medium">
                  Accounts and references in these payments
                </summary>
                <ul className="space-y-2 pt-2">
                  {selected.accounts.map((id) => (
                    <li key={id}>
                      {selected.rows.find((row) => row.account_id === id)
                        ?.account_label || "Account name not recorded"}
                    </li>
                  ))}
                </ul>
                <p className="mt-2">
                  Recipient ownership and address: not established by this
                  grouping.
                </p>
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
            <PaymentSet
              key={selected.id}
              caseId={caseId}
              rows={selected.rows}
              title={`Payments: ${selected.name}`}
            />
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
                </select>
              </label>
              <label className="text-sm">
                Currency and account type
                <select
                  aria-label="Profile currency and account type"
                  className="block rounded border bg-card p-2"
                  value={view.currencyGroup || ""}
                  onChange={(e) =>
                    setView({ ...view, currencyGroup: e.target.value, page: 0 })
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
              {filtered.length} names and accounts. Account activity and payment
              names describe the same payments from different perspectives;
              their totals should not be added together.
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
                    setView((current) => ({ ...current, selected: profile.id }))
                  }
                  className="finance-panel rounded-xl border p-4 text-left hover:border-primary focus-visible:outline-primary space-y-3"
                  data-finance-tone={
                    profile.kind === "account" ? "info" : "work"
                  }
                >
                  <p className="finance-badge">
                    {profile.kind === "account"
                      ? "Account"
                      : "Recorded payment name"}
                  </p>
                  <h3 className="text-base font-semibold break-words">
                    {profile.name}
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    {profile.rows.length} payments · {profile.accounts.length}{" "}
                    {profile.accounts.length === 1 ? "account" : "accounts"} ·{" "}
                    {profile.sources.length} source documents
                  </p>
                  <PaymentTotals rows={profile.rows} label="Recorded amounts" />
                  <p className="text-xs text-muted-foreground">
                    {profile.first || "Date unknown"} to{" "}
                    {profile.last || "date unknown"}
                  </p>
                  <span className="inline-block text-sm font-medium text-primary">
                    Open profile →
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
    </div>
  )
}
