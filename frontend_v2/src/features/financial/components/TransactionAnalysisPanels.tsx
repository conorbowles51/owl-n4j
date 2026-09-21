import { useState } from "react"
import type { LedgerTransaction } from "../api"
import { formatLedgerAmount } from "../lib/ledger-format"
import { paymentGroup, chartRatio } from "../lib/investigator-workspace"
import {
  activitySeries,
  amountGroupName,
  emptyAnalysisFilters,
  filterAnalysis,
  partyName,
  partySummaries,
  perspectiveSummary,
  type AnalysisFilters,
  type PartySummary,
} from "../lib/transaction-analysis"

type PanelState = {
  chartsOpen: boolean
  partiesOpen: boolean
  flowOpen: boolean
}
const money = (value: bigint, group: string) =>
  `${formatLedgerAmount(value.toString(), group.split(":")[0]).text} ${group.split(":")[0]}`
const colors = [
  "#257e70",
  "#4777b9",
  "#ab536c",
  "#a97020",
  "#785caa",
  "#328393",
  "#a75132",
  "#6b7b34",
]
const toggleName = (names: string[], name: string) =>
  names.includes(name) ? names.filter((n) => n !== name) : [...names, name]

function PartyList({
  title,
  entries,
  selected,
  onChange,
}: {
  title: string
  entries: PartySummary[]
  selected: string[]
  onChange: (names: string[]) => void
}) {
  const [search, setSearch] = useState(""),
    [sort, setSort] = useState("count"),
    [page, setPage] = useState(0)
  const groups = [
    ...new Set(entries.flatMap((e) => [...e.amounts.keys()])),
  ].sort()
  const items = entries
    .filter((e) => e.name.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => {
      if (sort === "name") return a.name.localeCompare(b.name)
      if (sort.startsWith("amount:")) {
        const group = sort.slice(7),
          left = a.amounts.get(group) ?? 0n,
          right = b.amounts.get(group) ?? 0n
        return left === right
          ? a.name.localeCompare(b.name)
          : left > right
            ? -1
            : 1
      }
      return b.count - a.count || a.name.localeCompare(b.name)
    })
  const index = Math.min(page, Math.max(0, Math.ceil(items.length / 50) - 1))
  return (
    <section className="min-w-0 rounded border" aria-label={title}>
      <div className="flex items-center justify-between gap-2 border-b p-2 text-sm">
        <h4 className="font-medium">
          {title}{" "}
          <span className="text-muted-foreground">
            · {entries.length.toLocaleString()} names
          </span>
        </h4>
        {selected.length > 0 && (
          <button className="text-xs underline" onClick={() => onChange([])}>
            Clear {title.toLowerCase()}
          </button>
        )}
      </div>
      <div className="flex flex-wrap gap-2 p-2">
        <input
          className="min-w-0 flex-1 rounded border bg-background px-2 py-1 text-xs"
          aria-label={`Search ${title.toLowerCase()}`}
          placeholder="Search names…"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setPage(0)
          }}
        />
        <select
          className="max-w-52 rounded border bg-background p-1 text-xs"
          aria-label={`Sort ${title.toLowerCase()}`}
          value={sort}
          onChange={(e) => {
            setSort(e.target.value)
            setPage(0)
          }}
        >
          <option value="count">Most transactions</option>
          <option value="name">Name A–Z</option>
          {groups.map((g) => (
            <option key={g} value={`amount:${g}`}>
              Largest volume · {amountGroupName(g)}
            </option>
          ))}
        </select>
      </div>
      <div className="max-h-64 overflow-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-card text-left">
            <tr>
              <th className="p-2">Name</th>
              <th className="p-2 text-right">Entries</th>
              <th className="p-2 text-right">Volume by currency / type</th>
            </tr>
          </thead>
          <tbody>
            {items.slice(index * 50, (index + 1) * 50).map((e) => (
              <tr
                key={e.key}
                className={
                  selected.includes(e.key)
                    ? "border-t bg-primary/10"
                    : "border-t"
                }
              >
                <td className="p-2">
                  <button
                    aria-pressed={selected.includes(e.key)}
                    className="text-left hover:underline"
                    onClick={() => onChange(toggleName(selected, e.key))}
                  >
                    {selected.includes(e.key) ? "✓ " : ""}
                    {e.name}
                  </button>
                  {e.suggested > 0 && (
                    <span
                      title={`${e.suggested} entries use a name suggested from the description`}
                      className="ml-1 text-muted-foreground"
                    >
                      · suggested
                    </span>
                  )}
                </td>
                <td className="p-2 text-right tabular-nums">
                  {e.count.toLocaleString()}
                </td>
                <td className="p-2 text-right tabular-nums">
                  {[...e.amounts].map(([g, v]) => (
                    <div key={g} title={amountGroupName(g)}>
                      {money(v, g)}{" "}
                      <span className="text-muted-foreground">
                        {g.endsWith(":card") ? "card" : "bank"}
                      </span>
                    </div>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!items.length && (
          <p className="p-3 text-sm text-muted-foreground">
            No names match these filters.
          </p>
        )}
      </div>
      {items.length > 50 && (
        <div className="flex items-center justify-between gap-2 border-t p-2 text-xs">
          <button disabled={!index} onClick={() => setPage(index - 1)}>
            Previous names
          </button>
          <span>
            {index * 50 + 1}–{Math.min((index + 1) * 50, items.length)} of{" "}
            {items.length}
          </span>
          <button
            disabled={(index + 1) * 50 >= items.length}
            onClick={() => setPage(index + 1)}
          >
            Next names
          </button>
        </div>
      )}
    </section>
  )
}

function Charts({
  rows,
  filters,
  onChange,
}: {
  rows: LedgerTransaction[]
  filters: AnalysisFilters
  onChange: (value: Partial<AnalysisFilters>) => void
}) {
  const groups = [...new Set(rows.map(paymentGroup))].sort()
  const [choice, setChoice] = useState("")
  const group = groups.includes(choice) ? choice : (groups[0] ?? "")
  const chartRows = rows.filter((row) => paymentGroup(row) === group)
  const data = activitySeries(chartRows)
  const maximum = data.months.reduce(
    (max, m) => (m.credit + m.debit > max ? m.credit + m.debit : max),
    0n
  )
  const volume = data.categories.reduce(
    (sum, c) => sum + c.credit + c.debit,
    0n
  )
  let position = 0
  const segments = data.categories.map((c, i) => {
    const start = position
    position += chartRatio(c.credit + c.debit, volume) * 100
    return `${colors[i % colors.length]} ${start}% ${position}%`
  })
  return (
    <div className="space-y-3 p-3">
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <label>
          Chart currency and account type{" "}
          <select
            aria-label="Chart currency and account type"
            className="ml-2 rounded border bg-background p-1"
            value={group}
            onChange={(e) => setChoice(e.target.value)}
          >
            {groups.map((g) => (
              <option key={g} value={g}>
                {amountGroupName(g)}
              </option>
            ))}
          </select>
        </label>
        <span>
          {chartRows.length.toLocaleString()} transactions before month/category
          selection. Click a month or category to filter the table.
        </span>
      </div>
      {!chartRows.length ? (
        <p>No transactions to chart.</p>
      ) : (
        <div className="grid gap-4 xl:grid-cols-[3fr_2fr]">
          <section className="min-w-0" aria-label="Monthly transaction volume">
            <h4 className="text-sm font-medium">
              Monthly volume · {amountGroupName(group)}
            </h4>
            <p className="text-xs text-muted-foreground">
              Total credits and debits shown separately; no currency conversion.
              {data.omittedEmptyMonths &&
                " Only months with transactions are shown because the date span exceeds 50 years."}
            </p>
            <div
              className="mt-2 flex gap-1 overflow-x-auto border-b pb-1"
              style={{ height: 176 }}
            >
              {data.months.map((m) => (
                <button
                  key={m.month}
                  aria-label={`${m.month}: ${m.count} transactions, credits ${money(m.credit, group)}, debits ${money(m.debit, group)}`}
                  aria-pressed={
                    filters.analysisPeriod === m.month &&
                    filters.analysisGroup === group
                  }
                  title={`${m.month}: credits ${money(m.credit, group)}; debits ${money(m.debit, group)}`}
                  className={`flex min-w-9 flex-1 flex-col justify-end rounded-t px-1 text-[10px] hover:bg-muted ${filters.analysisPeriod === m.month ? "bg-primary/10 ring-1 ring-inset ring-primary" : ""}`}
                  onClick={() =>
                    onChange({
                      analysisGroup: group,
                      analysisPeriod:
                        filters.analysisPeriod === m.month ? "" : m.month,
                    })
                  }
                >
                  <span
                    className="mx-auto flex w-full max-w-10 flex-col-reverse overflow-hidden rounded-t"
                    style={{
                      height: Math.max(
                        m.count ? 2 : 0,
                        chartRatio(m.credit + m.debit, maximum) * 125
                      ),
                    }}
                  >
                    <span
                      style={{
                        height: `${chartRatio(m.credit, m.credit + m.debit) * 100}%`,
                        background: "var(--finance-credit)",
                      }}
                    />
                    <span
                      style={{
                        height: `${chartRatio(m.debit, m.credit + m.debit) * 100}%`,
                        background: "var(--finance-debit)",
                      }}
                    />
                  </span>
                  <span className="mt-1 whitespace-nowrap">{m.month}</span>
                </button>
              ))}
            </div>
            <div className="mt-2 flex flex-wrap gap-3 text-xs">
              <span style={{ color: "var(--finance-credit)" }}>
                ● Credits / money in
              </span>
              <span style={{ color: "var(--finance-debit)" }}>
                ● Debits / money out
              </span>
              {data.undated > 0 && (
                <button
                  className="underline"
                  onClick={() =>
                    onChange({
                      analysisGroup: group,
                      analysisPeriod: "undated",
                    })
                  }
                >
                  {data.undated} transactions without a printed date
                </button>
              )}
            </div>
          </section>
          <section className="min-w-0" aria-label="Category distribution">
            <h4 className="text-sm font-medium">
              Category distribution · {amountGroupName(group)}
            </h4>
            <p className="text-xs text-muted-foreground">
              Share of total volume (credits + debits), not net movement.
            </p>
            <div className="mt-2 flex items-start gap-3">
              <div
                role="img"
                aria-label={`Category volume ${money(volume, group)}; exact amounts listed alongside`}
                className="mt-3 flex h-28 w-28 shrink-0 items-center justify-center rounded-full"
                style={{
                  background: volume
                    ? `conic-gradient(${segments.join(",")})`
                    : "var(--muted)",
                }}
              >
                <span className="flex h-20 w-20 items-center justify-center rounded-full bg-card text-xs">
                  {data.categories.length} categories
                </span>
              </div>
              <div className="max-h-48 min-w-0 flex-1 overflow-auto text-xs">
                {data.categories.map((c, i) => (
                  <button
                    key={c.category}
                    aria-pressed={filters.analysisCategories.includes(
                      c.category
                    )}
                    className={`flex w-full items-center justify-between gap-2 rounded p-1.5 text-left hover:bg-muted ${filters.analysisCategories.includes(c.category) ? "bg-primary/10" : ""}`}
                    onClick={() =>
                      onChange({
                        analysisGroup: group,
                        analysisCategories: toggleName(
                          filters.analysisCategories,
                          c.category
                        ),
                      })
                    }
                  >
                    <span>
                      <span style={{ color: colors[i % colors.length] }}>
                        ●{" "}
                      </span>
                      {c.category}{" "}
                      <span className="text-muted-foreground">({c.count})</span>
                    </span>
                    <span className="whitespace-nowrap tabular-nums">
                      {money(c.credit + c.debit, group)}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}

function FlowChart({
  rows,
  filters,
  onChange,
}: {
  rows: LedgerTransaction[]
  filters: AnalysisFilters
  onChange: (value: Partial<AnalysisFilters>) => void
}) {
  const result = perspectiveSummary(rows, filters.perspectiveNames)
  const [limit, setLimit] = useState(12)
  return (
    <div className="min-w-0 space-y-3">
      {!filters.perspectiveNames.length ? (
        <p className="rounded border border-dashed p-6 text-sm">
          Select one or more names to see what came into that group, what went
          out, and what stayed within it.
        </p>
      ) : !result.totals.length ? (
        <p>No transactions connect these names within the current filters.</p>
      ) : (
        result.totals.map((total) => {
          const items = [
            ...(result.counterparties.get(total.group)?.values() ?? []),
          ].sort((a, b) => {
            const left = a.incoming + a.outgoing,
              right = b.incoming + b.outgoing
            return left === right
              ? a.name.localeCompare(b.name)
              : left > right
                ? -1
                : 1
          })
          const maximum = items.reduce(
            (m, e) =>
              e.incoming > m
                ? e.outgoing > e.incoming
                  ? e.outgoing
                  : e.incoming
                : e.outgoing > m
                  ? e.outgoing
                  : m,
            0n
          )
          return (
            <section
              key={total.group}
              className="space-y-2 rounded border p-2"
              aria-label={`Money flow ${amountGroupName(total.group)}`}
            >
              <h4 className="text-sm font-medium">
                {amountGroupName(total.group)}
              </h4>
              <div className="grid grid-cols-2 gap-2 text-xs lg:grid-cols-4">
                {(["incoming", "outgoing", "internal"] as const).map((kind) => (
                  <button
                    key={kind}
                    aria-pressed={filters.flowKind === kind}
                    className={`rounded border p-2 text-left ${filters.flowKind === kind ? "ring-1 ring-primary" : ""}`}
                    style={{
                      backgroundColor: `color-mix(in srgb, var(--finance-${kind === "incoming" ? "credit" : kind === "outgoing" ? "debit" : "info"}) 8%, transparent)`,
                    }}
                    onClick={() =>
                      onChange({
                        analysisGroup: total.group,
                        flowKind: filters.flowKind === kind ? "" : kind,
                        flowParty: "",
                      })
                    }
                  >
                    {kind === "incoming"
                      ? "Inflow to group"
                      : kind === "outgoing"
                        ? "Outflow from group"
                        : "Internal entries"}
                    <strong className="block tabular-nums">
                      {money(total[kind], total.group)}
                    </strong>
                    <span className="text-muted-foreground">
                      {total[`${kind}Count`]} entries
                    </span>
                  </button>
                ))}
                <div className="rounded border p-2">
                  Net external flow
                  <strong className="block tabular-nums">
                    {money(total.incoming - total.outgoing, total.group)}
                  </strong>
                  <span className="text-muted-foreground">
                    Inflow − outflow
                  </span>
                </div>
              </div>
              {total.group.endsWith(":card") && (
                <p className="text-xs text-muted-foreground">
                  Card entries represent charges and credits, not movements in a
                  bank cash balance.
                </p>
              )}
              <p className="text-xs text-muted-foreground">
                Group flow before direction/counterparty selection. Outflow is
                left, inflow right; click a bar to see its transactions.
              </p>
              {items.slice(0, limit).map((item) => (
                <div
                  key={item.key}
                  className="grid grid-cols-[minmax(80px,1fr)_2fr] items-center gap-2 text-xs"
                >
                  <span className="truncate" title={item.name}>
                    {item.name}
                  </span>
                  <div className="grid grid-cols-2 items-center border-x">
                    <button
                      disabled={!item.outgoing}
                      aria-label={`Outflow to ${item.name}: ${money(item.outgoing, total.group)}`}
                      title={`Outflow to ${item.name}: ${money(item.outgoing, total.group)}`}
                      className="flex h-6 items-center justify-end border-r hover:bg-muted"
                      onClick={() =>
                        onChange({
                          analysisGroup: total.group,
                          flowParty: item.key,
                          flowKind: "outgoing",
                        })
                      }
                    >
                      <span
                        style={{
                          width: `${chartRatio(item.outgoing, maximum) * 100}%`,
                          minWidth: item.outgoing ? 2 : 0,
                          background: "var(--finance-debit)",
                          height: 14,
                        }}
                      />
                    </button>
                    <button
                      disabled={!item.incoming}
                      aria-label={`Inflow from ${item.name}: ${money(item.incoming, total.group)}`}
                      title={`Inflow from ${item.name}: ${money(item.incoming, total.group)}`}
                      className="flex h-6 items-center hover:bg-muted"
                      onClick={() =>
                        onChange({
                          analysisGroup: total.group,
                          flowParty: item.key,
                          flowKind: "incoming",
                        })
                      }
                    >
                      <span
                        style={{
                          width: `${chartRatio(item.incoming, maximum) * 100}%`,
                          minWidth: item.incoming ? 2 : 0,
                          background: "var(--finance-credit)",
                          height: 14,
                        }}
                      />
                    </button>
                  </div>
                </div>
              ))}
              {items.length > limit && (
                <button
                  className="text-xs underline"
                  onClick={() => setLimit(limit + 24)}
                >
                  Show more counterparties ({items.length - limit} remaining;{" "}
                  {money(
                    items
                      .slice(limit)
                      .reduce((sum, e) => sum + e.incoming + e.outgoing, 0n),
                    total.group
                  )}{" "}
                  combined volume)
                </button>
              )}
            </section>
          )
        })
      )}
    </div>
  )
}

export function AnalysisFilterChips({
  filters,
  onChange,
}: {
  filters: AnalysisFilters
  onChange: (value: Partial<AnalysisFilters>) => void
}) {
  const active =
    filters.fromNames.length +
    filters.toNames.length +
    filters.perspectiveNames.length +
    filters.analysisCategories.length +
    Number(!!filters.analysisGroup) +
    Number(!!filters.analysisPeriod) +
    Number(!!filters.flowParty) +
    Number(!!filters.flowKind)
  if (!active) return null
  return (
    <div
      className="flex flex-wrap items-center gap-1.5 text-xs"
      aria-label="Active analysis filters"
    >
      {(["fromNames", "toNames", "perspectiveNames"] as const).flatMap((key) =>
        filters[key].map((name) => (
          <button
            key={`${key}:${name}`}
            className="rounded-full border bg-primary/5 px-2 py-1"
            onClick={() =>
              onChange({
                [key]: filters[key].filter((n) => n !== name),
                ...(key === "perspectiveNames"
                  ? { flowParty: "", flowKind: "" }
                  : {}),
              })
            }
          >
            {key === "fromNames"
              ? "From"
              : key === "toNames"
                ? "To"
                : "Perspective"}
            : {partyName(name)} ×
          </button>
        ))
      )}
      {filters.analysisGroup && (
        <button
          className="rounded-full border px-2 py-1"
          onClick={() => onChange({ analysisGroup: "" })}
        >
          {amountGroupName(filters.analysisGroup)} ×
        </button>
      )}
      {filters.analysisPeriod && (
        <button
          className="rounded-full border px-2 py-1"
          onClick={() => onChange({ analysisPeriod: "" })}
        >
          {filters.analysisPeriod === "undated"
            ? "No printed date"
            : filters.analysisPeriod}{" "}
          ×
        </button>
      )}
      {filters.analysisCategories.map((c) => (
        <button
          key={c}
          className="rounded-full border px-2 py-1"
          onClick={() =>
            onChange({
              analysisCategories: filters.analysisCategories.filter(
                (n) => n !== c
              ),
            })
          }
        >
          Category: {c} ×
        </button>
      ))}
      {filters.flowKind && (
        <button
          className="rounded-full border px-2 py-1"
          onClick={() => onChange({ flowKind: "", flowParty: "" })}
        >
          {filters.flowKind === "internal"
            ? "Internal entries"
            : filters.flowKind === "incoming"
              ? "Inflow to group"
              : "Outflow from group"}{" "}
          ×
        </button>
      )}
      {filters.flowParty && (
        <button
          className="rounded-full border px-2 py-1"
          onClick={() => onChange({ flowParty: "" })}
        >
          Counterparty: {partyName(filters.flowParty)} ×
        </button>
      )}
      <button
        className="px-2 underline"
        onClick={() => onChange(emptyAnalysisFilters)}
      >
        Clear analysis filters
      </button>
    </div>
  )
}

export function TransactionAnalysisPanels({
  rows,
  filters,
  panels,
  onChange,
}: {
  rows: LedgerTransaction[]
  filters: AnalysisFilters
  panels: PanelState
  onChange: (value: Partial<AnalysisFilters & PanelState>) => void
}) {
  const visible = panels.chartsOpen
    ? filterAnalysis(rows, {
        ...filters,
        analysisPeriod: "",
        analysisCategories: [],
      })
    : []
  const flowRows = panels.flowOpen
    ? filterAnalysis(rows, {
        ...filters,
        flowKind: "",
        flowParty: "",
      })
    : []
  const panel = (key: keyof PanelState, label: string) => (
    <button
      className={`rounded px-3 py-2 text-sm ${panels[key] ? "bg-primary/10 font-medium" : "hover:bg-muted"}`}
      aria-expanded={panels[key]}
      aria-controls={`analysis-${key}`}
      onClick={() => onChange({ [key]: !panels[key] })}
    >
      {panels[key] ? "▾" : "▸"} {label}
    </button>
  )
  return (
    <section
      aria-label="Transaction analysis"
      className="rounded border bg-card"
    >
      <div className="flex flex-wrap gap-1 border-b p-1">
        {panel("chartsOpen", "Charts")}
        {panel(
          "partiesOpen",
          `From & To${filters.fromNames.length + filters.toNames.length ? ` (${filters.fromNames.length + filters.toNames.length} selected)` : ""}`
        )}
        {panel(
          "flowOpen",
          `Money flow${filters.perspectiveNames.length ? ` (${filters.perspectiveNames.length} selected)` : ""}`
        )}
      </div>
      {panels.chartsOpen && (
        <div id="analysis-chartsOpen">
          <Charts rows={visible} filters={filters} onChange={onChange} />
        </div>
      )}
      {panels.partiesOpen && (
        <div id="analysis-partiesOpen" className="space-y-2 border-t p-3">
          <p className="text-xs text-muted-foreground">
            Choose senders and recipients to filter the table and charts.
            Multiple names on one side mean “any of these”; From and To
            selections apply together.
          </p>
          <div className="grid gap-3 lg:grid-cols-2">
            <PartyList
              title="Senders (From)"
              entries={partySummaries(
                filterAnalysis(rows, filters, "from"),
                "from"
              )}
              selected={filters.fromNames}
              onChange={(fromNames) => onChange({ fromNames })}
            />
            <PartyList
              title="Recipients (To)"
              entries={partySummaries(
                filterAnalysis(rows, filters, "to"),
                "to"
              )}
              selected={filters.toNames}
              onChange={(toNames) => onChange({ toNames })}
            />
          </div>
        </div>
      )}
      {panels.flowOpen && (
        <div id="analysis-flowOpen" className="space-y-2 border-t p-3">
          <p className="text-xs text-muted-foreground">
            View transactions from the perspective of selected names. Internal
            entries have both From and To inside the group; each entry is
            counted once. Names are grouped by their displayed text, including
            marked suggestions. Unidentified senders and recipients can be
            filtered in From &amp; To.
          </p>
          {(filters.fromNames.length > 0 || filters.toNames.length > 0) && (
            <p className="rounded border bg-muted p-2 text-xs">
              Your From / To filters also apply to this perspective.
            </p>
          )}
          <div className="grid items-start gap-3 xl:grid-cols-[minmax(260px,2fr)_3fr]">
            <PartyList
              title="Perspective names"
              entries={partySummaries(
                filterAnalysis(rows, filters, "perspective")
              ).filter((entry) => entry.key.startsWith("name:"))}
              selected={filters.perspectiveNames}
              onChange={(perspectiveNames) =>
                onChange({ perspectiveNames, flowKind: "", flowParty: "" })
              }
            />
            <FlowChart rows={flowRows} filters={filters} onChange={onChange} />
          </div>
        </div>
      )}
    </section>
  )
}
