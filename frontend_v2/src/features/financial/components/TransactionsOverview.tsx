import { useMemo, useState } from "react"
import { Info } from "lucide-react"
import type { LedgerTransaction } from "../api"
import { categoryName, useStatementNames } from "../hooks/use-payment-categories"
import {
  categoryTone,
  compactMoney,
  groupMoney,
  minorToNumber,
  monthSeries,
  type MoneyGroup,
} from "../lib/category-palette"
import { formatLedgerAmount } from "../lib/ledger-format"
import { paymentDay } from "../lib/investigator-workspace"

export type OverviewGroup = "category" | "holder" | "account" | "statement" | "month"

const GROUPS: [OverviewGroup, string][] = [
  ["category", "Category"],
  ["holder", "Person"],
  ["account", "Account"],
  ["statement", "Statement"],
  ["month", "Month"],
]
const SHOWN = 12
const heading = { fontFamily: "'Space Grotesk', ui-sans-serif, system-ui, sans-serif", letterSpacing: "-0.02em" }

const exact = (minor: bigint, currency: string) =>
  `${formatLedgerAmount(String(minor), currency).text} ${currency}`

const keyOf = (names: Map<string, string>): Record<Exclude<OverviewGroup, "category">, (row: LedgerTransaction) => [string, string]> => ({
  holder: (row) => [row.account_holder || "", row.account_holder || "Holder not identified"],
  account: (row) => [row.account_id, row.account_label || row.account_id.slice(0, 8)],
  statement: (row) => [row.source_document_id, names.get(row.source_document_id) || `Statement ${row.source_document_id.slice(0, 8)}`],
  month: (row) => {
    const month = paymentDay(row)?.slice(0, 7)
    return [month || "undated", month || "Undated"]
  },
})

/**
 * The headline of the Transactions view: money in, out and net for the current
 * filters, month by month with gaps shown, and where it went by category (or by
 * person, account, statement or month). Every tile and bar filters the list.
 */
export function TransactionsOverview({
  caseId,
  rows,
  monthRows,
  tileRows,
  colors,
  categories,
  onCategories,
  activeMonth,
  onMonth,
  onGroup,
  onCategorise,
  modeSwitch,
  show = {},
}: {
  caseId: string
  /** Payments matching every filter: the totals and months. */
  rows: LedgerTransaction[]
  /** Payments matching every filter except the chosen month: the month chart. */
  monthRows: LedgerTransaction[]
  /** Payments matching every filter except category: the tiles. */
  tileRows: LedgerTransaction[]
  colors: Map<string, string>
  categories: string[]
  onCategories: (next: string[]) => void
  activeMonth: string
  onMonth: (month: string) => void
  onGroup: (kind: Exclude<OverviewGroup, "category" | "month">, group: MoneyGroup) => void
  onCategorise?: (rows: LedgerTransaction[]) => void
  modeSwitch?: React.ReactNode
  /** Which parts are on the page (the control panel's switches); every part is shown unless switched off. */
  show?: { totals?: boolean; months?: boolean; breakdown?: boolean }
}) {
  const { totals: showTotals = true, months: showMonths = true, breakdown: showBreakdown = true } = show
  // Sums over every matching payment: worked out again only when those payments change.
  const { currencies, counts } = useMemo(() => {
    const counts = new Map<string, number>()
    for (const row of tileRows) counts.set(row.currency, (counts.get(row.currency) ?? 0) + 1)
    const currencies = [...counts.keys()]
    currencies.sort((a, b) => (counts.get(b) ?? 0) - (counts.get(a) ?? 0) || a.localeCompare(b))
    return { currencies, counts }
  }, [tileRows])
  const [chosen, setChosen] = useState("")
  const currency = currencies.includes(chosen) ? chosen : currencies[0] || ""
  const [group, setGroup] = useState<OverviewGroup>("category")
  const [all, setAll] = useState(false)
  const statementNameData = useStatementNames(group === "statement" ? caseId : "none").data
  const { inCurrency, total, months, groups } = useMemo(() => {
    const statementNames = statementNameData ?? new Map<string, string>()
    const inCurrency = rows.filter((row) => row.currency === currency)
    const tilesIn = tileRows.filter((row) => row.currency === currency)
    return {
      inCurrency,
      total: groupMoney(inCurrency, () => ["all", "all"])[0],
      months: monthSeries(monthRows.filter((row) => row.currency === currency)),
      groups:
        group === "category"
          ? groupMoney(tilesIn, (row) => [categoryName(row), categoryName(row)])
          : groupMoney(inCurrency, keyOf(statementNames)[group]),
    }
  }, [rows, tileRows, monthRows, currency, group, statementNameData])
  const credit = total?.credit ?? 0n
  const debit = total?.debit ?? 0n
  const peak = months.reduce((max, m) => Math.max(max, m.group ? minorToNumber(m.group.credit, currency) : 0, m.group ? minorToNumber(m.group.debit, currency) : 0), 1)
  const money = (minor: bigint) => compactMoney(minorToNumber(minor, currency))
  const uncategorized = group === "category" ? groups.find((g) => g.key === "Uncategorized") : undefined
  const tiles = groups.filter((g) => g !== uncategorized)
  const toggle = (name: string) =>
    onCategories(categories.includes(name) ? categories.filter((n) => n !== name) : [...categories, name])
  if (!showTotals && !showMonths && !showBreakdown) return null
  return (
    <div className="space-y-6">
      {(showTotals || showMonths) && (
      <section
        aria-label="This view at a glance"
        // Totals on their own (no month chart) take one compact band.
        className={`rounded-2xl text-[#f7f7f8] ${showMonths ? "p-5 sm:p-7" : "flex flex-wrap items-center gap-x-8 gap-y-2 px-5 py-3"}`}
        style={{ background: "radial-gradient(1200px 400px at 85% -10%, #2a1216 0%, #0b0c0f 60%)" }}
      >
        <div className="flex flex-wrap items-center gap-3">
          {currencies.length > 1 && (
            <div role="group" aria-label="Currency" className="inline-flex rounded-lg border border-[#292b32] bg-[#17181c] p-[3px]">
              {currencies.map((code) => (
                <button
                  key={code}
                  type="button"
                  aria-pressed={code === currency}
                  onClick={() => setChosen(code)}
                  className={`rounded-md px-3 py-1.5 text-[13px] font-semibold ${code === currency ? "bg-[#f7f7f8] text-[#0b0c0f]" : "text-[#bfc1c8] hover:text-white"}`}
                >
                  {code} · {(counts.get(code) ?? 0).toLocaleString()}
                </button>
              ))}
            </div>
          )}
          <span className="flex-1" />
          {modeSwitch}
        </div>
        {showTotals && (
        <div className={`flex flex-wrap gap-y-2 ${showMonths ? "mt-5 gap-x-10" : "gap-x-8"}`} aria-label={`Totals in ${currency}`}>
          {[
            ["Money in", `+${money(credit)}`, "text-[#5fd39a]", credit],
            ["Money out", `−${money(debit)}`, "text-[#f7f7f8]", debit],
            ["Net", `${credit >= debit ? "+" : "−"}${money(credit >= debit ? credit - debit : debit - credit)}`, "text-[#bfc1c8]", credit - debit],
          ].map(([label, text, tone, minor]) => (
            <div key={label as string} title={exact(minor as bigint, currency)}>
              <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-[#9a9da5]">
                {label as string} · {currency}
              </span>
              <div className={`font-semibold tabular-nums ${showMonths ? "text-4xl sm:text-[44px]" : "text-2xl sm:text-3xl"} ${tone}`} style={heading}>
                {text as string}
              </div>
            </div>
          ))}
          {/* In the compact band each currency's tab already says how many payments it holds. */}
          {(showMonths || currencies.length < 2) && (
          <div>
            <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-[#9a9da5]">Payments</span>
            <div className={`font-semibold tabular-nums text-[#bfc1c8] ${showMonths ? "text-4xl sm:text-[44px]" : "text-2xl sm:text-3xl"}`} style={heading}>
              {inCurrency.length.toLocaleString()}
            </div>
          </div>
          )}
        </div>
        )}
        {showMonths && months.length > 0 && (
          <figure className="mt-6 overflow-x-auto" aria-label={`Money in and out per month in ${currency}`}>
            <div
              className="grid items-end gap-1.5"
              style={{ gridTemplateColumns: `repeat(${months.length}, minmax(22px, 1fr))`, height: 150, minWidth: months.length * 26 }}
            >
              {months.map(({ month, group: m }) => {
                const active = activeMonth === month
                if (!m)
                  return (
                    <span
                      key={month}
                      title={`${month}: no payments read`}
                      className="flex h-full items-center justify-center rounded-md border-[1.5px] border-dashed border-[#e0a43a] px-0.5 text-center text-[10px] leading-3 text-[#f2c46b]"
                    >
                      none
                    </span>
                  )
                const h = (minor: bigint) => `${Math.max(3, Math.round((minorToNumber(minor, currency) / peak) * 66))}px`
                return (
                  <button
                    key={month}
                    type="button"
                    aria-pressed={active}
                    title={`${month}: ${exact(m.credit, currency)} in, ${exact(m.debit, currency)} out, ${m.count} payments. Click to show this month.`}
                    onClick={() => onMonth(active ? "" : month)}
                    className={`flex h-full flex-col justify-end gap-[3px] rounded-md ${active ? "outline outline-2 outline-[#f7f7f8]" : "hover:bg-white/5"}`}
                  >
                    <span style={{ height: h(m.credit), background: "linear-gradient(180deg,#7ee2ad,#2fae6c)", borderRadius: "5px 5px 2px 2px" }} />
                    <span style={{ height: h(m.debit), background: "linear-gradient(180deg,#8b8e98,#5c5f68)", borderRadius: "2px 2px 5px 5px" }} />
                  </button>
                )
              })}
            </div>
            <div className="mt-2 grid gap-1.5" style={{ gridTemplateColumns: `repeat(${months.length}, minmax(22px, 1fr))`, minWidth: months.length * 26 }}>
              {months.map(({ month }) => (
                <span key={month} className="text-center font-mono text-[10px] uppercase text-[#9a9da5]">
                  {months.length > 14 ? month.slice(2).replace("-", "/") : new Date(`${month}-01T00:00:00Z`).toLocaleString("en", { month: "short", timeZone: "UTC" })}
                </span>
              ))}
            </div>
            <figcaption className="mt-2 flex flex-wrap gap-4 text-xs text-[#bfc1c8]">
              <span><span className="mr-1.5 inline-block size-2 rounded-full bg-[#5fd39a]" />Money in</span>
              <span><span className="mr-1.5 inline-block size-2 rounded-full bg-[#8b8e98]" />Money out</span>
              <span><span className="mr-1.5 inline-block size-2 rounded-sm border border-dashed border-[#e0a43a]" />No payments read that month</span>
              <span className="ml-auto">Click a month to show its payments</span>
            </figcaption>
          </figure>
        )}
      </section>
      )}

      {showBreakdown && (
      <section aria-label="Where the money went" className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-2xl font-semibold" style={heading}>
            Where it went
            <Info
              role="img"
              aria-label="Tiles are sized by money in and out under the current filters. Click a tile to show its payments; click again to clear."
              className="ml-2 inline size-4 align-middle text-muted-foreground"
            >
              <title>Tiles are sized by money in and out under the current filters. Click a tile to show its payments; click again to clear.</title>
            </Info>
          </h2>
          <div role="group" aria-label="Break down by" className="inline-flex max-w-full flex-wrap rounded-lg bg-muted p-[3px]">
            {GROUPS.map(([key, label]) => (
              <button
                key={key}
                type="button"
                aria-pressed={group === key}
                onClick={() => {
                  setGroup(key)
                  setAll(false)
                }}
                className={`rounded-md px-3 py-1.5 text-[13px] ${group === key ? "bg-background font-semibold shadow-sm" : "font-medium text-muted-foreground hover:text-foreground"}`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        {!groups.length ? (
          <p className="text-sm text-muted-foreground">No payments in {currency || "this view"} match these filters.</p>
        ) : group === "category" ? (
          <CategoryTiles
            tiles={tiles}
            uncategorized={uncategorized}
            colors={colors}
            selected={categories}
            onToggle={toggle}
            onCategorise={onCategorise}
            money={money}
            exact={(minor) => exact(minor, currency)}
            all={all}
            onAll={setAll}
          />
        ) : (
          <GroupBars
            groups={groups}
            colors={colors}
            money={money}
            exact={(minor) => exact(minor, currency)}
            all={all}
            onAll={setAll}
            onPick={(g) => (group === "month" ? onMonth(activeMonth === g.key ? "" : g.key) : onGroup(group as "holder" | "account" | "statement", g))}
            onCategory={toggle}
          />
        )}
      </section>
      )}
    </div>
  )
}

function CategoryTiles({
  tiles,
  uncategorized,
  colors,
  selected,
  onToggle,
  onCategorise,
  money,
  exact,
  all,
  onAll,
}: {
  tiles: MoneyGroup[]
  uncategorized?: MoneyGroup
  colors: Map<string, string>
  selected: string[]
  onToggle: (name: string) => void
  onCategorise?: (rows: LedgerTransaction[]) => void
  money: (minor: bigint) => string
  exact: (minor: bigint) => string
  all: boolean
  onAll: (value: boolean) => void
}) {
  const big = tiles.slice(0, uncategorized ? 1 : 2)
  const mid = tiles.slice(big.length, big.length + 2)
  const small = tiles.slice(big.length + mid.length, big.length + mid.length + 2)
  const rest = tiles.slice(big.length + mid.length + small.length)
  const tile = (g: MoneyGroup, size: "big" | "mid" | "small") => {
    const tone = categoryTone(g.key, colors.get(g.key.toLowerCase()))
    const pressed = selected.includes(g.key)
    return (
      <button
        key={g.key}
        type="button"
        aria-pressed={pressed}
        title={`${g.key}: ${exact(g.credit)} in, ${exact(g.debit)} out, ${g.count} payments`}
        onClick={() => onToggle(g.key)}
        className={`flex min-h-24 flex-col justify-between gap-2 rounded-xl p-4 text-left text-white transition-transform hover:-translate-y-0.5 focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-offset-2 ${pressed ? "ring-4 ring-foreground/70" : ""} ${size === "big" ? "col-span-6 row-span-2 sm:col-span-3" : size === "mid" ? "col-span-3 sm:col-span-2" : "col-span-3 sm:col-span-1"}`}
        style={{ background: tone.dot }}
      >
        <span className="font-mono text-[11px] uppercase tracking-[0.1em] text-white/85">
          {g.key} · {g.count.toLocaleString()}
        </span>
        <span>
          <span className={`block font-semibold tabular-nums ${size === "big" ? "text-4xl" : size === "mid" ? "text-2xl" : "text-xl"}`} style={heading}>
            {money(g.credit + g.debit)}
          </span>
          {size === "big" && (
            <span className="text-sm text-white/85">
              {money(g.credit)} in · {money(g.debit)} out
            </span>
          )}
        </span>
      </button>
    )
  }
  return (
    <>
      <div className="grid auto-rows-[96px] grid-cols-6 gap-2.5">
        {big.map((g) => tile(g, "big"))}
        {uncategorized && (
          <div
            className={`col-span-6 row-span-2 flex flex-col justify-between gap-2 rounded-xl border-2 border-dashed border-[#d99a2b] p-4 text-[#6b4100] sm:col-span-3 ${selected.includes("Uncategorized") ? "ring-4 ring-foreground/70" : ""}`}
            style={{ background: "repeating-linear-gradient(135deg,#fdf0d5 0 14px,#f8e6bf 14px 28px)" }}
          >
            <button type="button" aria-pressed={selected.includes("Uncategorized")} onClick={() => onToggle("Uncategorized")} className="text-left font-mono text-[11px] uppercase tracking-[0.1em] text-[#8a5300] hover:underline">
              Needs a category · {uncategorized.count.toLocaleString()}
            </button>
            <span className="flex flex-wrap items-end justify-between gap-3">
              <span title={`${exact(uncategorized.credit)} in, ${exact(uncategorized.debit)} out`}>
                <span className="block text-4xl font-semibold tabular-nums" style={heading}>{money(uncategorized.credit + uncategorized.debit)}</span>
                <span className="text-sm">{money(uncategorized.credit)} in · {money(uncategorized.debit)} out</span>
              </span>
              {onCategorise && (
                <button type="button" onClick={() => onCategorise(uncategorized.rows)} className="rounded-md bg-[#b41624] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#9c1220]">
                  Categorise {uncategorized.count.toLocaleString()} →
                </button>
              )}
            </span>
          </div>
        )}
        {mid.map((g) => tile(g, "mid"))}
        {small.map((g) => tile(g, "small"))}
      </div>
      {rest.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[13px]">
          {(all ? rest : rest.slice(0, SHOWN)).map((g) => {
            const tone = categoryTone(g.key, colors.get(g.key.toLowerCase()))
            return (
              <button
                key={g.key}
                type="button"
                aria-pressed={selected.includes(g.key)}
                onClick={() => onToggle(g.key)}
                title={`${exact(g.credit)} in, ${exact(g.debit)} out`}
                className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 hover:bg-muted ${selected.includes(g.key) ? "bg-muted font-semibold" : ""}`}
              >
                <span className="size-2 rounded-full" style={{ background: tone.dot }} />
                {g.key} · {g.count.toLocaleString()} · {money(g.credit + g.debit)}
              </button>
            )
          })}
          {rest.length > SHOWN && (
            <button type="button" className="text-[#1d4aa6] underline-offset-2 hover:underline dark:text-blue-300" onClick={() => onAll(!all)}>
              {all ? "Show fewer" : `+${rest.length - SHOWN} more categories`}
            </button>
          )}
        </div>
      )}
    </>
  )
}

function GroupBars({
  groups,
  colors,
  money,
  exact,
  all,
  onAll,
  onPick,
  onCategory,
}: {
  groups: MoneyGroup[]
  colors: Map<string, string>
  money: (minor: bigint) => string
  exact: (minor: bigint) => string
  all: boolean
  onAll: (value: boolean) => void
  onPick: (group: MoneyGroup) => void
  onCategory: (name: string) => void
}) {
  const peak = groups.reduce((max, g) => (g.credit + g.debit > max ? g.credit + g.debit : max), 1n)
  return (
    <div className="space-y-2">
      {(all ? groups : groups.slice(0, SHOWN)).map((g) => {
        const parts = groupMoney(g.rows, (row) => [categoryName(row), categoryName(row)])
        const width = Number(((g.credit + g.debit) * 1000n) / peak) / 10
        return (
          <div key={g.key} className="grid grid-cols-1 items-center gap-1 rounded-xl bg-card px-4 py-3 shadow-sm sm:grid-cols-[minmax(0,16rem)_minmax(0,1fr)_auto] sm:gap-4">
            <button type="button" onClick={() => onPick(g)} className="truncate text-left font-semibold hover:underline" title={`Show the payments of ${g.label}`}>
              {g.label}
              <span className="ml-2 text-xs font-normal text-muted-foreground">{g.count.toLocaleString()} payments</span>
            </button>
            <div className="flex h-4 overflow-hidden rounded" style={{ width: `${Math.max(width, 2)}%` }} aria-label={`Categories of ${g.label}`}>
              {parts.map((part) => (
                <button
                  key={part.key}
                  type="button"
                  title={`${part.key}: ${exact(part.credit)} in, ${exact(part.debit)} out, ${part.count} payments. Click to filter.`}
                  aria-label={`${part.key} in ${g.label}`}
                  onClick={() => onCategory(part.key)}
                  style={{ flex: `${Number(part.credit + part.debit) || 1} 1 0`, background: categoryTone(part.key, colors.get(part.key.toLowerCase())).dot }}
                />
              ))}
            </div>
            <span className="text-right text-sm tabular-nums" title={`${exact(g.credit)} in, ${exact(g.debit)} out`}>
              <span className="font-semibold text-[#12784a] dark:text-[#5fd39a]">+{money(g.credit)}</span>
              <span className="text-muted-foreground"> · −{money(g.debit)}</span>
            </span>
          </div>
        )
      })}
      {groups.length > SHOWN && (
        <button type="button" className="text-sm text-[#1d4aa6] hover:underline dark:text-blue-300" onClick={() => onAll(!all)}>
          {all ? "Show fewer" : `+${groups.length - SHOWN} more`}
        </button>
      )}
    </div>
  )
}
