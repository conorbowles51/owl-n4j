import { useState } from "react"
import type { LedgerTransaction } from "../api"
import { categoryName } from "../hooks/use-payment-categories"
import { useCategoryColors } from "../hooks/use-payment-category-library"
import { categoryTone, compactMoney, groupMoney, minorToNumber, type MoneyGroup } from "../lib/category-palette"
import { formatLedgerAmount } from "../lib/ledger-format"
import { paymentDay } from "../lib/investigator-workspace"
import { InfoTip } from "./InfoTip"

const heading = { fontFamily: "'Space Grotesk', ui-sans-serif, system-ui, sans-serif", letterSpacing: "-0.025em" }
const eyebrow = "font-mono text-[11px] uppercase tracking-[0.12em]"
const SHOWN = 6
/** SVG labels stay inside their column; the full name is in the band's title and label. */
const short = (label: string) => (label.length > 19 ? `${label.slice(0, 18)}…` : label)
const W = 1200
const TOP = 40
const H = 440
const GAP = 6
const LEFT = 270
const MID = 585
const MID_W = 20
const RIGHT = 920

type Band = { key: string; label: string; minor: bigint; rows: LedgerTransaction[]; color: string; hatch?: boolean; grey?: boolean }

/** Top categories on one side, then "Other categories" folding the rest (never a generated hue). */
function side(groups: MoneyGroup[], pick: (g: MoneyGroup) => bigint, colors: Map<string, string>): Band[] {
  const live = groups.filter((g) => pick(g) > 0n).sort((a, b) => (pick(b) > pick(a) ? 1 : pick(b) < pick(a) ? -1 : 0))
  const bands: Band[] = live.slice(0, SHOWN).map((g) => ({
    key: g.key,
    label: g.key === "Uncategorized" ? "No category yet" : g.label,
    minor: pick(g),
    rows: g.rows,
    color: categoryTone(g.key, colors.get(g.key.toLowerCase())).dot,
    hatch: g.key === "Uncategorized",
  }))
  const rest = live.slice(SHOWN)
  if (rest.length)
    bands.push({
      key: "__other",
      label: `Other ${rest.length} categories`,
      minor: rest.reduce((sum, g) => sum + pick(g), 0n),
      rows: rest.flatMap((g) => g.rows),
      color: "#8b8e98",
      grey: true,
    })
  return bands
}

/**
 * Follow the money's top layer: where the money in the current scope came
 * from and where it went, by category, as bands whose width is money. Every
 * band opens the payments behind it; the explorers below stay as tables.
 */
export function CategoryFlowDiagram({
  caseId,
  rows,
  onOpen,
  onTrace,
}: {
  caseId: string
  rows: LedgerTransaction[]
  onOpen: (ids: string[], title: string) => void
  onTrace?: () => void
}) {
  const colors = useCategoryColors(caseId)
  const counts = new Map<string, number>()
  for (const row of rows) counts.set(row.currency, (counts.get(row.currency) ?? 0) + 1)
  const currencies = [...counts.keys()].sort((a, b) => (counts.get(b) ?? 0) - (counts.get(a) ?? 0) || a.localeCompare(b))
  const [chosen, setChosen] = useState("")
  const currency = currencies.includes(chosen) ? chosen : currencies[0] || ""
  const inCurrency = rows.filter((row) => row.currency === currency)
  if (!inCurrency.length) return null
  const groups = groupMoney(inCurrency, (row) => [categoryName(row), categoryName(row)])
  const ins = side(groups, (g) => g.credit, colors).map((b) => ({ ...b, rows: b.rows.filter((r) => r.direction === "credit") }))
  const outs = side(groups, (g) => g.debit, colors).map((b) => ({ ...b, rows: b.rows.filter((r) => r.direction !== "credit") }))
  const totalIn = ins.reduce((s, b) => s + b.minor, 0n)
  const totalOut = outs.reduce((s, b) => s + b.minor, 0n)
  // The difference is drawn, never dropped: kept on the right, or drawn from the balance on the left.
  if (totalIn > totalOut) outs.push({ key: "__kept", label: "Kept", minor: totalIn - totalOut, rows: [], color: "#5c5f68", grey: true })
  if (totalOut > totalIn) ins.push({ key: "__drawn", label: "Drawn from the balance", minor: totalOut - totalIn, rows: [], color: "#5c5f68", grey: true })
  const total = totalIn > totalOut ? totalIn : totalOut
  const scale = (minor: bigint) => (total ? (Number(minor) / Number(total)) * H : 0)
  const money = (minor: bigint) => compactMoney(minorToNumber(minor, currency))
  const exact = (minor: bigint) => `${formatLedgerAmount(String(minor), currency).text} ${currency}`
  const layout = (bands: Band[]) => {
    const gaps = GAP * Math.max(0, bands.length - 1)
    const k = (H - gaps) / H
    let y = TOP
    let m = TOP
    return bands.map((band) => {
      const h = Math.max(2, scale(band.minor) * k)
      const hm = scale(band.minor)
      const placed = { band, y0: y, y1: y + h, m0: m, m1: m + hm }
      y += h + GAP
      m += hm
      return placed
    })
  }
  // Labels sit at their band's middle, pushed down so two never overlap.
  const labelled = <T extends { y0: number; y1: number }>(items: T[]) => {
    let last = -Infinity
    return items.map((item) => {
      const y = Math.max((item.y0 + item.y1) / 2, last + 50)
      last = y
      return { ...item, ly: y }
    })
  }
  const left = labelled(layout(ins))
  const right = labelled(layout(outs))
  const height = Math.max(TOP + H + 30, ...left.map((p) => p.ly + 34), ...right.map((p) => p.ly + 34))
  const path = (x0: number, a0: number, a1: number, x1: number, b0: number, b1: number) => {
    const c = (x0 + x1) / 2
    return `M${x0} ${a0} C${c} ${a0} ${c} ${b0} ${x1} ${b0} L${x1} ${b1} C${c} ${b1} ${c} ${a1} ${x0} ${a1} Z`
  }
  const biggest = inCurrency
    .filter((row) => row.direction === "credit")
    .reduce<LedgerTransaction | null>((best, row) => {
      try {
        return !best || BigInt(row.amount_minor) > BigInt(best.amount_minor) ? row : best
      } catch {
        return best
      }
    }, null)
  const accounts = new Set(inCurrency.map((row) => row.account_id)).size
  const band = (b: Band, d: string, direction: "in" | "out") => {
    const title = b.key.startsWith("__") && b.key !== "__other"
      ? `${b.label}: ${exact(b.minor)}`
      : `${b.label} ${direction === "in" ? "in" : "out"}: ${direction === "in" ? "+" : "−"}${exact(b.minor)}${b.rows.length ? ` · ${b.rows.length} payments` : ""}`
    const clickable = b.rows.length > 0
    return (
      <path
        key={`${direction}:${b.key}`}
        d={d}
        fill={b.hatch ? "url(#flow-hatch)" : b.color}
        opacity={b.grey ? 0.45 : 0.6}
        className={clickable ? "cursor-pointer outline-none transition-opacity hover:opacity-90 focus-visible:opacity-100" : undefined}
        role={clickable ? "button" : "img"}
        tabIndex={clickable ? 0 : undefined}
        aria-label={clickable ? `${title}. Open these payments` : title}
        onClick={clickable ? () => onOpen(b.rows.map((r) => r.key), `${b.label} · money ${direction}`) : undefined}
        onKeyDown={
          clickable
            ? (event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault()
                  onOpen(b.rows.map((r) => r.key), `${b.label} · money ${direction}`)
                }
              }
            : undefined
        }
      >
        <title>{title}</title>
      </path>
    )
  }
  return (
    <section
      aria-label="Where the money came from and went"
      className="space-y-4 rounded-2xl p-4 text-[#f7f7f8] sm:p-6"
      style={{ background: "radial-gradient(1100px 420px at 90% -20%, #3a1319 0%, #0b0c0f 62%)" }}
    >
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <span className={`${eyebrow} text-[#e33b4c]`}>Follow the money</span>
          <h3 className="text-2xl font-semibold leading-tight sm:text-[32px]" style={heading}>
            Where the money came from,
            <span className="block text-[#9a9da5]">and where it went</span>
          </h3>
        </div>
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
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
        <figure className="min-w-0 rounded-[14px] border border-[#292b32] bg-[#17181c] p-3 sm:p-4">
          <div className="grid grid-cols-3 px-1 text-[#9a9da5]">
            <span className={eyebrow}>Came from · +{money(totalIn)}</span>
            <span className={`${eyebrow} text-center`}>Through</span>
            <span className={`${eyebrow} text-right`}>Went to · −{money(totalOut)}</span>
          </div>
          <div className="overflow-x-auto">
            <svg
              viewBox={`0 0 ${W} ${height}`}
              className="min-w-[800px]"
              role="group"
              aria-label={`Money flow in ${currency}: ${money(totalIn)} in, ${money(totalOut)} out`}
            >
              <defs>
                <pattern id="flow-hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                  <rect width="8" height="8" fill="#e0a43a" opacity=".35" />
                  <rect width="4" height="8" fill="#e0a43a" opacity=".75" />
                </pattern>
              </defs>
              {left.map((p) => band(p.band, path(LEFT, p.y0, p.y1, MID, p.m0, p.m1), "in"))}
              {right.map((p) => band(p.band, path(MID + MID_W, p.m0, p.m1, RIGHT, p.y0, p.y1), "out"))}
              {left.map((p) => (
                <rect key={`ln:${p.band.key}`} x={LEFT - 14} y={p.y0} width={14} height={p.y1 - p.y0} rx={3} fill={p.band.hatch ? "#e0a43a" : p.band.color} />
              ))}
              {right.map((p) => (
                <rect key={`rn:${p.band.key}`} x={RIGHT} y={p.y0} width={14} height={p.y1 - p.y0} rx={3} fill={p.band.hatch ? "#e0a43a" : p.band.color} />
              ))}
              <rect x={MID} y={TOP} width={MID_W} height={scale(total)} rx={4} fill="#f7f7f8" />
              <text x={MID + MID_W / 2} y={TOP - 12} textAnchor="middle" fontSize="20" fontWeight="600" fill="#f7f7f8">
                {accounts} {accounts === 1 ? "account" : "accounts"} · {currency}
              </text>
              <g fontFamily="IBM Plex Sans, ui-sans-serif, sans-serif">
                {left.map((p) => (
                  <g key={`lt:${p.band.key}`} aria-hidden="true">
                    <text x={LEFT - 26} y={p.ly} textAnchor="end" fontSize="21" fontWeight="600" fill="#f7f7f8">
                      {short(p.band.label)}
                    </text>
                    <text x={LEFT - 26} y={p.ly + 23} textAnchor="end" fontSize="19" fill={p.band.hatch ? "#f2c46b" : "#5fd39a"}>
                      +{money(p.band.minor)}
                      {p.band.rows.length ? ` · ${p.band.rows.length.toLocaleString()}` : ""}
                    </text>
                  </g>
                ))}
                {right.map((p) => (
                  <g key={`rt:${p.band.key}`} aria-hidden="true">
                    <text x={RIGHT + 26} y={p.ly} fontSize="21" fontWeight="600" fill="#f7f7f8">
                      {short(p.band.label)}
                    </text>
                    <text x={RIGHT + 26} y={p.ly + 23} fontSize="19" fill={p.band.hatch ? "#f2c46b" : "#bfc1c8"}>
                      {p.band.key === "__kept" ? "+" : "−"}
                      {money(p.band.minor)}
                      {p.band.rows.length ? ` · ${p.band.rows.length.toLocaleString()}` : ""}
                    </text>
                  </g>
                ))}
              </g>
            </svg>
          </div>
          <figcaption className="flex flex-wrap justify-between gap-2 px-1 text-[13px] text-[#bfc1c8]">
            <span>
              Width = money. Click any band to open its payments.
              <InfoTip tone="dark" text="Each band is one category of payments in the current accounts, dates and filters, in the chosen currency. Money in on the left, money out on the right; the difference is drawn as Kept or Drawn from the balance. The six largest categories each side are drawn; the rest are folded into Other. The tables below show the same payments." />
            </span>
            <span>
              <span aria-hidden="true" className="mr-1.5 inline-block size-2.5 rounded-sm" style={{ background: "repeating-linear-gradient(135deg,#e0a43a 0 3px,#5c4415 3px 6px)" }} />
              Amber stripes = no category yet
            </span>
          </figcaption>
        </figure>
        <aside className="space-y-3">
          {biggest && (
            <div className="space-y-2 rounded-[14px] border border-[#292b32] bg-[#17181c] p-4">
              <span className={`${eyebrow} text-[#9a9da5]`}>Biggest single payment in</span>
              <p className="font-semibold">{biggest.from_name || biggest.counterparty_raw || biggest.description || "Payer not recorded"}</p>
              <p className="text-2xl font-semibold tabular-nums text-[#5fd39a]" style={heading}>
                +{formatLedgerAmount(biggest.amount_minor, currency).text}
              </p>
              <p className="text-[13px] text-[#bfc1c8]">
                {paymentDay(biggest) || biggest.ordering_date?.slice(0, 10)} · {biggest.account_label || "Account"}
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="rounded-lg border border-[#3b3d44] px-3 py-2 text-sm font-semibold hover:bg-[#202126]"
                  onClick={() => onOpen([biggest.key], "Biggest single payment in")}
                >
                  Open it
                </button>
                {onTrace && (
                  <button type="button" className="rounded-lg bg-[#b41624] px-3 py-2 text-sm font-semibold text-white hover:bg-[#9a121f]" onClick={onTrace}>
                    Trace where it went next →
                  </button>
                )}
              </div>
            </div>
          )}
          <a
            href="#follow-money-tables"
            className="block rounded-[14px] border border-[#292b32] bg-[#17181c] p-4 text-sm font-semibold hover:bg-[#202126]"
          >
            Show as table ↓
            <span className="block text-[13px] font-normal text-[#bfc1c8]">Flows by account and person, trails and timing comparisons</span>
          </a>
        </aside>
      </div>
    </section>
  )
}
