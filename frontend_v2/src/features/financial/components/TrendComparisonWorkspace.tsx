import { useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import type { LedgerTransaction } from "../api"
import { useFinancialDraft } from "../stores/financial-drafts"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { amountGroupName } from "../lib/transaction-analysis"
import { paymentDay, paymentGroup } from "../lib/investigator-workspace"
import { formatLedgerAmount } from "../lib/ledger-format"
import {
  TREND_RULES,
  changeDrivers,
  changePercent,
  daysIn,
  defaultTrendRanges,
  investigateTrends,
  monthRange,
  rangeError,
  type CoverageInput,
  type DateRange,
  type TrendObservation,
} from "../lib/investigation-trends"
import { PaymentComparison } from "./PaymentComparison"
import { InvestigatorFindingEditor } from "./InvestigatorFindingEditor"

interface Evidence {
  title: string
  explanation: string
  rows: LedgerTransaction[]
}
const idsOf = (rows: LedgerTransaction[]) => [
  ...new Set(rows.map((row) => row.key)),
]
const kinds = [
  {
    kind: "first-seen",
    title: "Counterparties first seen in these records",
    description:
      "Names appearing in the later period with no earlier occurrence in the loaded account/date scope. A suggested name is not a confirmed identity.",
    empty:
      "No first-seen names found. This requires earlier dated records and an identified counterparty.",
  },
  {
    kind: "recurring",
    title: "Recurring payments",
    description:
      "Equal amounts in one account to/from the same displayed name, with at least three weekly or monthly dates. Checks all loaded history up to the later period, including payments in that period.",
    empty:
      "No matching weekly or monthly schedule found. At least three dated, named, equal-amount payments are needed.",
  },
  {
    kind: "larger",
    title: "Payments larger than the earlier pattern",
    description:
      "More than three times the earlier median and larger than the earlier maximum, using at least five payments in the same account and direction.",
    empty:
      "No later payments met this rule, or fewer than five earlier payments were available for the account and direction.",
  },
  {
    kind: "return",
    title: "Transfer returns with matching references",
    description:
      "Explicitly returned transfers matched to a single outgoing entry by account, amount and reference within seven days. Both entries remain in totals.",
    empty:
      "No unambiguous returned-transfer matches were found in the later period.",
  },
] as const

export function TrendComparisonWorkspace({
  caseId,
  rows,
  coverage,
  loadedStart,
  loadedEnd,
  onCoverageRetry,
}: {
  caseId: string
  rows: LedgerTransaction[]
  coverage: CoverageInput
  loadedStart?: string
  loadedEnd?: string
  onCoverageRetry: () => void
}) {
  const { canEdit } = useFinancialAccess()
  const [view, setView] = useFinancialDraft(caseId, "investigation-trends-v2", {
    group: "",
    earlier: null as DateRange | null,
    later: null as DateRange | null,
    direction: "debit",
    by: "name" as "name" | "category",
    driverCount: 8,
  })
  const [open, setOpen] = useState<Evidence | null>(null),
    [finding, setFinding] = useState<Evidence | null>(null)
  const [expanded, setExpanded] = useState<Record<string, number>>({})
  const groups = useMemo(() => {
    const counts = new Map<string, number>()
    for (const row of rows)
      counts.set(paymentGroup(row), (counts.get(paymentGroup(row)) || 0) + 1)
    return [...counts]
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .map(([g]) => g)
  }, [rows])
  const group = groups.includes(view.group) ? view.group : groups[0] || ""
  const scoped = useMemo(
    () => rows.filter((row) => paymentGroup(row) === group),
    [rows, group]
  )
  const defaults = useMemo(() => defaultTrendRanges(scoped), [scoped])
  const earlier = view.earlier ?? defaults.earlier,
    later = view.later ?? defaults.later
  const error =
    rangeError(earlier, later) ||
    ((loadedStart && earlier.start < loadedStart) ||
    (loadedEnd && later.end > loadedEnd)
      ? "These periods extend beyond the loaded date filter. Broaden Accounts and dates above to include both periods."
      : null)
  const result = useMemo(
    () =>
      !error && scoped.length
        ? investigateTrends(scoped, group, earlier, later, coverage)
        : null,
    [scoped, group, earlier, later, coverage, error]
  )
  const drivers = useMemo(
    () =>
      result
        ? changeDrivers(result.before, result.after, view.direction, view.by)
        : [],
    [result, view.direction, view.by]
  )
  const currency = group.split(":")[0],
    card = group.endsWith(":card")
  const money = (value: bigint) =>
    `${formatLedgerAmount(value.toString(), currency).text} ${currency}`
  const signed = (value: bigint) => `${value > 0n ? "+" : ""}${money(value)}`
  const directionLabel = (direction: string) =>
    card
      ? direction === "credit"
        ? "Card credits"
        : "Card charges"
      : direction === "credit"
        ? "Money in"
        : "Money out"
  const periodText = `Earlier: ${earlier.start} to ${earlier.end}. Later: ${later.start} to ${later.end}. ${amountGroupName(group)}.`
  const limitation = result
    ? `${result.comparable ? "Recorded statement dates cover both ranges; this does not by itself prove extraction completeness." : "The comparison has incomplete coverage or unreadable dates/amounts. Differences describe the available records, not proven changes in all account activity."} ${result.unknownDates.length} payments have no usable transaction date; ${result.invalidAmounts.length} have no usable amount. Analysis is limited to the loaded account/date/category scope.`
    : ""
  const evidence = (
    title: string,
    explanation: string,
    payments: LedgerTransaction[]
  ): Evidence => ({
    title,
    explanation: `${periodText}\n${explanation}\n${limitation}`,
    rows: payments,
  })
  const actions = (item: Evidence) => (
    <div className="flex flex-wrap gap-2">
      <Button
        size="sm"
        variant="outline"
        disabled={!item.rows.length}
        onClick={() => setOpen(item)}
      >
        View {idsOf(item.rows).length} supporting payments
      </Button>
      {canEdit && (
        <Button
          size="sm"
          variant="ghost"
          disabled={!item.rows.length}
          onClick={() => setFinding(item)}
        >
          Record observation
        </Button>
      )}
    </div>
  )
  const download = () => {
    if (!result) return
    const payload = {
      schema: "loupe.financial.trends/1",
      case_id: caseId,
      created_at: new Date().toISOString(),
      rules: TREND_RULES,
      group,
      earlier,
      later,
      loaded_date_filter: { start: loadedStart, end: loadedEnd },
      limitation,
      coverage: result.coverage,
      totals: result.totals,
      observations: result.observations,
      drivers: { by: view.by, direction: view.direction, entries: drivers },
      transactions: scoped,
    }
    const blob = new Blob(
      [
        JSON.stringify(
          payload,
          (_key, value) =>
            typeof value === "bigint" ? value.toString() : value,
          2
        ),
      ],
      { type: "application/json" }
    )
    const url = URL.createObjectURL(blob),
      a = document.createElement("a")
    a.href = url
    a.download = "loupe-trends-comparison.json"
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  const updateRange = (
    side: "earlier" | "later",
    part: "start" | "end",
    value: string
  ) =>
    setView({
      ...view,
      [side]: { ...(side === "earlier" ? earlier : later), [part]: value },
      driverCount: 8,
    })
  const observationCard = (item: TrendObservation) => {
    const detail = item.baseline
      ? `${item.explanation} Earlier median: ${money(item.baseline.medianTwice / 2n)}${item.baseline.medianTwice % 2n ? " plus half a minor currency unit" : ""}; earlier maximum: ${money(item.baseline.maximum)}.`
      : item.explanation
    const ev = evidence(
      item.title,
      `${money(item.amount)}${item.kind === "recurring" ? " per payment" : ""}. ${detail}`,
      [...item.earlierRows, ...item.rows]
    )
    return (
      <article
        key={item.id}
        className="rounded-lg border bg-card p-4 space-y-2"
      >
        <div className="flex flex-wrap justify-between gap-2">
          <h4 className="font-semibold text-sm break-words min-w-0">
            {item.title}
          </h4>
          <strong className="text-sm tabular-nums shrink-0">
            {money(item.amount)}
            {item.kind === "recurring" ? " each" : ""}
          </strong>
        </div>
        <p className="text-xs text-muted-foreground">
          {directionLabel(item.direction)}
          {item.suggested
            ? " · Includes a name suggested from the description"
            : ""}
        </p>
        <p className="text-sm">{detail}</p>
        <p className="text-xs text-muted-foreground">
          {item.rows.length} supporting entries
          {item.earlierRows.length
            ? ` + ${item.earlierRows.length} earlier comparison entries`
            : ""}
        </p>
        {actions(ev)}
      </article>
    )
  }
  if (!scoped.some((row) => paymentDay(row)))
    return (
      <section className="rounded-lg border p-5 space-y-2">
        <h3 className="font-semibold">No dated payments in this scope</h3>
        <p>
          Trends needs dated transactions to compare periods. Import statements
          or broaden Accounts and dates above.
        </p>
        {scoped.length > 0 && (
          <p>
            {scoped.length} payments have no usable transaction date and cannot
            establish a time pattern.
          </p>
        )}
      </section>
    )
  return (
    <div className="space-y-5" aria-label="Investigative trends">
      <section
        className="rounded-xl border bg-card p-4 space-y-4"
        aria-label="Comparison periods"
      >
        <div className="flex flex-wrap items-end justify-between gap-3">
          <label className="text-sm font-medium">
            Currency and account type
            <select
              className="block rounded border bg-background p-2 mt-1"
              value={group}
              onChange={(e) =>
                setView({
                  ...view,
                  group: e.target.value,
                  earlier: null,
                  later: null,
                  driverCount: 8,
                })
              }
            >
              {groups.map((g) => (
                <option key={g} value={g}>
                  {amountGroupName(g)}
                </option>
              ))}
            </select>
          </label>
          <Button
            size="sm"
            variant="outline"
            onClick={() =>
              setView({ ...view, earlier: null, later: null, driverCount: 8 })
            }
          >
            Latest month vs previous month
          </Button>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          {(["earlier", "later"] as const).map((side) => (
            <fieldset key={side} className="rounded border p-3 min-w-0">
              <legend className="px-1 font-semibold text-sm">
                {side === "earlier" ? "Earlier period" : "Later period"}
              </legend>
              <label className="text-xs text-muted-foreground">
                Choose a month
                <input
                  type="month"
                  aria-label={`${side} month`}
                  className="ml-2 rounded border bg-background p-1"
                  value={(side === "earlier" ? earlier : later).start.slice(
                    0,
                    7
                  )}
                  onChange={(e) =>
                    setView({
                      ...view,
                      [side]: monthRange(e.target.value),
                      driverCount: 8,
                    })
                  }
                />
              </label>
              <div className="mt-3 flex flex-wrap gap-3">
                {(["start", "end"] as const).map((part) => (
                  <label key={part} className="text-sm">
                    {part === "start" ? "From" : "To"}
                    <input
                      aria-label={`${side} ${part}`}
                      type="date"
                      className="block rounded border bg-background p-2"
                      value={(side === "earlier" ? earlier : later)[part]}
                      onChange={(e) => updateRange(side, part, e.target.value)}
                    />
                  </label>
                ))}
              </div>
            </fieldset>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">
          Amounts are compared within one currency and account type. Names and
          categories use current readings, suggestions and investigator edits.
        </p>
      </section>
      {error && (
        <p role="alert" className="rounded border p-4">
          {error}
        </p>
      )}
      {result && (
        <>
          <section
            aria-label="Comparison coverage"
            className="rounded-xl border p-4 space-y-3 bg-muted/20"
          >
            <div className="flex flex-wrap justify-between gap-2">
              <h3 className="font-semibold">
                {result.comparable
                  ? "Statement dates cover both comparison periods"
                  : "Comparison uses incomplete records"}
              </h3>
              <Button size="sm" variant="outline" onClick={download}>
                Download comparison and evidence
              </Button>
            </div>
            <p className="text-sm">{limitation}</p>
            {daysIn(earlier) !== daysIn(later) && (
              <p className="text-sm">
                The periods have different lengths: {daysIn(earlier)} and{" "}
                {daysIn(later)} days. Totals are not adjusted to a daily rate.
              </p>
            )}
            {!coverage.available && (
              <Button size="sm" variant="outline" onClick={onCoverageRetry}>
                Retry statement coverage
              </Button>
            )}
            {coverage.truncated && (
              <p className="text-sm">
                The statement register is truncated; complete coverage cannot be
                established.
              </p>
            )}
            <details>
              <summary className="cursor-pointer text-sm font-medium">
                Coverage by account ({result.accounts.length})
              </summary>
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left mt-2">
                  <thead>
                    <tr>
                      <th className="p-2">Account</th>
                      <th className="p-2">Earlier statement days</th>
                      <th className="p-2">Later statement days</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.accounts.map((account) => (
                      <tr key={account.id} className="border-t">
                        <th className="p-2 font-normal">{account.label}</th>
                        {(["earlier", "later"] as const).map((side) => {
                          const d = result.coverage[side].details.find(
                            (x) => x.id === account.id
                          )!
                          return (
                            <td className="p-2" key={side}>
                              {coverage.available
                                ? `${d.coveredDays} of ${d.totalDays} days`
                                : "Unavailable"}
                              {d.incomplete
                                ? " · import has incomplete records"
                                : ""}
                            </td>
                          )
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
            {result.unknownDates.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  setOpen(
                    evidence(
                      "Payments with no usable transaction date",
                      "These records are omitted from date-based comparisons.",
                      result.unknownDates
                    )
                  )
                }
              >
                Review {result.unknownDates.length} undated payments
              </Button>
            )}
          </section>
          <section aria-label="What changed" className="space-y-3">
            <h3 className="text-lg font-semibold">What changed?</h3>
            <div className="grid gap-3 md:grid-cols-2">
              {result.totals.map((total) => (
                <article
                  key={total.direction}
                  className="rounded-lg border p-4 space-y-3 finance-tint"
                  data-finance-tone={total.direction}
                >
                  <h4 className="font-semibold">
                    {directionLabel(total.direction)}
                  </h4>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <p>Earlier · {total.beforeCount} payments</p>
                      <strong className="block tabular-nums mt-1">
                        {money(total.before)}
                      </strong>
                    </div>
                    <div>
                      <p>Later · {total.afterCount} payments</p>
                      <strong className="block tabular-nums mt-1">
                        {money(total.after)}
                      </strong>
                    </div>
                  </div>
                  <p className="font-semibold">
                    Recorded difference: {signed(total.after - total.before)}
                    {result.comparable &&
                    changePercent(total.before, total.after) !== null
                      ? ` (${changePercent(total.before, total.after)})`
                      : ""}
                  </p>
                  {total.before === 0n && (
                    <p className="text-xs">
                      No recorded amount in the earlier period; no percentage
                      increase is calculated.
                    </p>
                  )}
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      setView({
                        ...view,
                        direction: total.direction,
                        driverCount: 8,
                      })
                    }
                  >
                    Explain {directionLabel(total.direction).toLowerCase()}{" "}
                    change
                  </Button>
                </article>
              ))}
            </div>
          </section>
          <section
            aria-label="What drove the change"
            className="rounded-xl border bg-card p-4 space-y-3"
          >
            <h3 className="text-lg font-semibold">What drove the change?</h3>
            <div className="flex flex-wrap gap-3 text-sm">
              <label>
                Compare
                <select
                  className="ml-2 rounded border p-2 bg-background"
                  value={view.direction}
                  onChange={(e) =>
                    setView({
                      ...view,
                      direction: e.target.value,
                      driverCount: 8,
                    })
                  }
                >
                  <option value="debit">{directionLabel("debit")}</option>
                  <option value="credit">{directionLabel("credit")}</option>
                </select>
              </label>
              <label>
                Explain by
                <select
                  className="ml-2 rounded border p-2 bg-background"
                  value={view.by}
                  onChange={(e) =>
                    setView({
                      ...view,
                      by: e.target.value as "name" | "category",
                      driverCount: 8,
                    })
                  }
                >
                  <option value="name">Counterparty</option>
                  <option value="category">Category</option>
                </select>
              </label>
            </div>
            <p className="text-sm text-muted-foreground">
              Largest differences first. Changes by{" "}
              {view.by === "name" ? "counterparty" : "category"} add up to the
              recorded difference; these are alternative views of the same
              payments.
            </p>
            {drivers.length ? (
              <>
                <p className="rounded-lg bg-muted/30 p-3 text-sm">
                  {drivers[0].delta === 0n ? (
                    "Each group's recorded total is unchanged between these periods."
                  ) : (
                    <>
                      Largest difference: <strong>{drivers[0].name}</strong>,{" "}
                      {signed(drivers[0].delta)} ({money(drivers[0].before)} to{" "}
                      {money(drivers[0].after)}).
                    </>
                  )}
                  {view.by === "name" && drivers.some((d) => d.unknown)
                    ? " Payments without names may involve different counterparties."
                    : ""}
                </p>
                <div className="overflow-x-auto">
                  <table
                    className="w-full text-left text-sm"
                    aria-label="Change drivers"
                  >
                    <thead>
                      <tr>
                        {[
                          view.by === "name" ? "Counterparty" : "Category",
                          "Earlier",
                          "Later",
                          "Difference",
                          "Evidence",
                        ].map((t) => (
                          <th key={t} className="p-2 border-b">
                            {t}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {drivers.slice(0, view.driverCount).map((driver) => (
                        <tr key={driver.key} className="border-b align-top">
                          <th className="p-2 font-medium">
                            <span className="block">{driver.name}</span>
                            {driver.suggested && (
                              <span className="block text-xs text-muted-foreground">
                                Includes suggested labels
                              </span>
                            )}
                          </th>
                          <td className="p-2 whitespace-nowrap">
                            {money(driver.before)}
                            <span className="block text-xs text-muted-foreground">
                              {driver.earlier.length} payments
                            </span>
                          </td>
                          <td className="p-2 whitespace-nowrap">
                            {money(driver.after)}
                            <span className="block text-xs text-muted-foreground">
                              {driver.later.length} payments
                            </span>
                          </td>
                          <td className="p-2 whitespace-nowrap font-semibold">
                            {signed(driver.delta)}
                          </td>
                          <td className="p-2">
                            {actions(
                              evidence(
                                `${driver.name}: change in ${directionLabel(view.direction).toLowerCase()}`,
                                `Earlier ${money(driver.before)} across ${driver.earlier.length} payments; later ${money(driver.after)} across ${driver.later.length} payments. Recorded difference ${signed(driver.delta)}.${driver.unknown && view.by === "name" ? " These unnamed payments are not assumed to be one counterparty." : ""}`,
                                [...driver.earlier, ...driver.later]
                              )
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {drivers.length > view.driverCount && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      setView({ ...view, driverCount: view.driverCount + 20 })
                    }
                  >
                    Show more drivers ({drivers.length - view.driverCount}{" "}
                    remaining)
                  </Button>
                )}
                <p className="text-xs">
                  Across all {drivers.length} groups:{" "}
                  {signed(drivers.reduce((sum, d) => sum + d.delta, 0n))}.
                </p>
              </>
            ) : (
              <p>
                No payments with usable dates and amounts in these periods for
                this direction.
              </p>
            )}
          </section>
          <div className="space-y-4">
            {kinds.map((section) => {
              const items = result.observations.filter(
                  (item) => item.kind === section.kind
                ),
                count = expanded[section.kind] || 4
              return (
                <section
                  key={section.kind}
                  className="rounded-xl border p-4 space-y-3"
                  aria-label={section.title}
                >
                  <h3 className="font-semibold text-lg">
                    {section.title}{" "}
                    <span className="text-sm font-normal text-muted-foreground">
                      ({items.length})
                    </span>
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    {section.description}
                  </p>
                  {items.length ? (
                    <>
                      <div className="grid gap-3 xl:grid-cols-2">
                        {items.slice(0, count).map(observationCard)}
                      </div>
                      {items.length > count && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            setExpanded({
                              ...expanded,
                              [section.kind]: count + 8,
                            })
                          }
                        >
                          Show more ({items.length - count} remaining)
                        </Button>
                      )}
                    </>
                  ) : (
                    <p className="text-sm">{section.empty}</p>
                  )}
                </section>
              )
            })}
          </div>
          <p className="text-xs text-muted-foreground">
            These are reproducible observations about imported records. Check
            their significance against the originals and case context. No
            observation is automatically saved as a finding.
          </p>
        </>
      )}
      {open && (
        <PaymentComparison
          caseId={caseId}
          ids={idsOf(open.rows)}
          title={open.title}
          onClose={() => setOpen(null)}
        />
      )}
      {finding && (
        <InvestigatorFindingEditor
          caseId={caseId}
          ids={idsOf(finding.rows)}
          draftContext={JSON.stringify({
            group,
            earlier,
            later,
            loadedStart,
            loadedEnd,
          })}
          initial={{
            kind: "observation",
            title: finding.title.slice(0, 255),
            explanation: finding.explanation,
          }}
          onClose={() => setFinding(null)}
        />
      )}
    </div>
  )
}
