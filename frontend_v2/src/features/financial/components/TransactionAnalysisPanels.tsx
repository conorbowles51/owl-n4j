import { useState } from "react"
import { TransactionFilterCharts } from "./TransactionFilterCharts"
import type { LedgerTransaction } from "../api"
import { formatLedgerAmount } from "../lib/ledger-format"
import { chartRatio } from "../lib/investigator-workspace"
import {
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
    Number(!!filters.analysisDirection) +
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
      {filters.analysisDirection && (
        <button
          className="rounded-full border px-2 py-1"
          onClick={() => onChange({ analysisDirection: "" })}
        >
          {filters.analysisDirection === "credit"
            ? "Credits / money in"
            : "Debits / money out"}{" "}
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
  hideControls = false,
  rows,
  filters,
  panels,
  onChange,
}: {
  hideControls?: boolean
  rows: LedgerTransaction[]
  filters: AnalysisFilters
  panels: PanelState
  onChange: (value: Partial<AnalysisFilters & PanelState>) => void
}) {
  const flowRows = panels.flowOpen
    ? filterAnalysis(rows, {
        ...filters,
        flowKind: "",
        flowParty: "",
      })
    : []
  return (
    <section
      aria-label="Transaction analysis"
      className="rounded border bg-card"
    >
      {!hideControls && (
        <TransactionAnalysisControls
          filters={filters}
          panels={panels}
          onChange={onChange}
        />
      )}
      {panels.chartsOpen && (
        <div id="analysis-chartsOpen">
          <TransactionFilterCharts
            rows={rows}
            filters={filters}
            onChange={onChange}
          />
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

export function TransactionAnalysisControls({
  filters,
  panels,
  onChange,
}: {
  filters: AnalysisFilters
  panels: PanelState
  onChange: (value: Partial<AnalysisFilters & PanelState>) => void
}) {
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
  )
}
