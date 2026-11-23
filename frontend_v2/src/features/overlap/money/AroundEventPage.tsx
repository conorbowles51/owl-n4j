import { LearnMore } from "@/components/ui/learn-more"
import { useQuery } from "@tanstack/react-query"
import { useMemo, useState } from "react"
import { Link, useParams, useSearchParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { useSwitch } from "@/lib/ui-switches"
import { overlapAPI, type AroundEvent, type MoneyCell, type MoneyColumn } from "../api"
import { askCorroborate } from "../corroborate"

const SOURCE: Record<MoneyCell["source"], string> = { bank_and_phone: "BANK + PHONE", phone_only: "PHONE ONLY", bank_only: "BANK ONLY" }
const day = (iso: string) => new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" })
const money = (minor: number) => `$${(minor / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const ISO = /^\d{4}-\d{2}-\d{2}$/

/**
 * Money around chosen events (lx-overlapviews-b C, design screen 6): from each event's day to a week after, one column
 * per payment pattern; each payment says whether a bank row and a phone both hold it; a phone-only payment names the
 * statement pages not in the case; the last row counts the same patterns in every other week.
 */
export default function AroundEventPage() {
  const { id: caseId = "" } = useParams()
  const on = useSwitch("corroborate-v2")
  const [params, setParams] = useSearchParams()
  const dates = useMemo(() => (params.get("dates") ?? "").split(",").filter((d) => ISO.test(d)).sort(), [params])
  const setDates = (ds: string[]) => {
    const next = new URLSearchParams(params)
    if (ds.length) next.set("dates", [...new Set(ds)].sort().join(","))
    else next.delete("dates")
    setParams(next, { replace: true })
  }
  const choices = useQuery({ queryKey: ["around-event-choices", caseId], queryFn: () => overlapAPI.eventChoices(caseId), enabled: on && !!caseId })
  const table = useQuery({
    queryKey: ["around-event", caseId, dates],
    queryFn: () => overlapAPI.aroundEvent(caseId, dates.map((d) => ({ date: d }))),
    enabled: on && !!caseId && dates.length > 0,
    staleTime: 60_000,
  })
  if (!on) {
    return <p className="p-4 text-sm">This view is not turned on for this browser.</p>
  }
  return (
    <div className="h-full overflow-auto bg-canvas p-3 text-sm" data-testid="around-event">
      <nav className="mb-2 text-xs text-muted-foreground">
        <Link className="underline" to={`/cases/${caseId}/financial`}>Financial</Link> / Around an event
      </nav>
      <h1 className="text-base font-semibold">Money around each event <LearnMore term="Money around an event" /></h1>
      <p className="text-xs text-muted-foreground">
        Bank rows and payment alerts on the phones, from each event's day to a week after. A payment found in a bank
        statement and on a phone shows <b>BANK + PHONE</b>; one only a phone shows is <b>PHONE ONLY</b>.
      </p>
      <Chooser dates={dates} setDates={setDates} choices={choices.data?.choices ?? []} />
      {dates.length === 0 && <p className="pt-3">Choose one or more events to see the money around them.</p>}
      {table.isLoading && <p role="status" className="pt-3">Reading the ledger and the phones…</p>}
      {table.isError && (
        <div role="alert" className="pt-3">
          The table could not be read: {table.error instanceof Error ? table.error.message : "the server did not answer"}.{" "}
          <Button size="sm" variant="outline" onClick={() => void table.refetch()}>Try again</Button>
        </div>
      )}
      {table.data && <Table caseId={caseId} t={table.data} />}
    </div>
  )
}

function Chooser({ dates, setDates, choices }: { dates: string[]; setDates: (d: string[]) => void; choices: { date: string; label: string; from: string; reading?: string | null }[] }) {
  const [typed, setTyped] = useState("")
  return (
    <section aria-label="Choose events" className="mt-2 space-y-1 rounded border border-border bg-card p-2 text-xs">
      <h2 className="font-semibold">Choose events</h2>
      <p className="flex flex-wrap gap-1">
        {dates.map((d) => (
          <span key={d} className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5">
            {day(d)} {d.slice(0, 4)}
            <button type="button" aria-label={`Remove ${d}`} onClick={() => setDates(dates.filter((x) => x !== d))}>×</button>
          </span>
        ))}
      </p>
      <form className="flex flex-wrap items-center gap-1" onSubmit={(e) => { e.preventDefault(); if (ISO.test(typed)) { setDates([...dates, typed]); setTyped("") } }}>
        <label className="flex items-center gap-1">Add a date <input type="date" className="h-7 rounded border border-border bg-background px-1" value={typed} onChange={(e) => setTyped(e.target.value)} /></label>
        <Button size="sm" variant="outline" type="submit" disabled={!ISO.test(typed)} disabledReason="Pick a whole date first">Add</Button>
      </form>
      {choices.length > 0 && (
        <details>
          <summary className="cursor-pointer">Dates the case states ({choices.length})</summary>
          <ul className="space-y-0.5 pt-1">
            {choices.map((c, i) => (
              <li key={`${c.date}-${i}`}>
                <label className="flex items-start gap-1">
                  <input type="checkbox" checked={dates.includes(c.date)} onChange={(e) => setDates(e.target.checked ? [...dates, c.date] : dates.filter((x) => x !== c.date))} />
                  <span>{c.date}: {c.label} <span className="text-muted-foreground">({c.from}{c.reading ? `, ${c.reading}` : ""})</span></span>
                </label>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}

function Cell({ items }: { items: MoneyCell[] }) {
  if (items.length === 0) return <span className="text-muted-foreground">none</span>
  return (
    <div className="space-y-1">
      {items.map((c) => (
        <div key={c.records.join()} data-testid="money-cell">
          <div className="font-medium">{c.amount}</div>
          <div className="text-[11px] text-muted-foreground">{day(c.day)}{c.check ? ` · check ${c.check}` : ""}</div>
          <span className={`inline-block rounded px-1 text-[10px] font-semibold ${c.source === "bank_and_phone" ? "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-100" : c.source === "phone_only" ? "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-100" : "bg-muted"}`}>
            {SOURCE[c.source]}
          </span>
          {c.banks.length > 0 && <div className="text-[10px] text-muted-foreground">{c.banks.join("; ")}</div>}
          {c.gap && <div className="mt-0.5 rounded border border-dashed border-amber-500 p-1 text-[11px]" data-testid="money-gap">{c.gap.words}</div>}
        </div>
      ))}
    </div>
  )
}

function Table({ caseId, t }: { caseId: string; t: AroundEvent }) {
  const around = t.columns.filter((c) => !c.ordinary)
  const ordinary = t.columns.filter((c) => c.ordinary)
  const gaps = [...new Map(t.rows.flatMap((r) => Object.values(r.cells).flat()).filter((c) => c.gap).map((c) => [c.gap!.words, c.gap!])).values()]
  const members = t.rows.flatMap((r) => around.flatMap((c) => r.cells[c.id] ?? []))
    .flatMap((c) => c.records.map((ref) => { const [type, id] = ref.split(":"); return { type, id, label: `${c.amount} ${c.day}` } }))
  return (
    <section className="mt-3 space-y-3">
      <ColumnsTable t={t} columns={around} title="Money around each event" />
      {around.length === 0 && <p>No payment pattern follows two or more of these events.</p>}
      {gaps.length > 0 && (
        <section aria-label="Pages to ask for" className="rounded border border-amber-500 p-2 text-xs">
          <h3 className="font-semibold">Missing statement pages</h3>
          <ul className="list-disc pl-4">{gaps.map((g) => <li key={g.words}>{g.words}</li>)}</ul>
        </section>
      )}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={members.length === 0} onClick={() => askCorroborate({
          caseId, screen: "financial", label: `Money around ${t.events.length} events`,
          members,
          period: { from: t.events[0].date, to: t.events[t.events.length - 1].date },
        })}>Corroborate this</Button>
      </div>
      {ordinary.length > 0 && (
        <details>
          <summary className="cursor-pointer text-xs">Ordinary money, as common in other weeks ({ordinary.length} {ordinary.length === 1 ? "pattern" : "patterns"})</summary>
          <ColumnsTable t={t} columns={ordinary} title="Ordinary money" />
        </details>
      )}
      {t.one_off.length > 0 && (
        <details>
          <summary className="cursor-pointer text-xs">Payments after only one event ({t.one_off.length})</summary>
          <Cell items={t.one_off} />
        </details>
      )}
      <p className="text-xs text-muted-foreground">{t.rule} Times are read in {t.zone}.</p>
    </section>
  )
}

function ColumnsTable({ t, columns, title }: { t: AroundEvent; columns: MoneyColumn[]; title: string }) {
  if (columns.length === 0) return null
  const ow = t.other_weeks
  return (
    <div className="overflow-x-auto rounded border border-border bg-card">
      <table className="min-w-full border-collapse text-xs" aria-label={title}>
        <thead>
          <tr className="text-left align-bottom">
            <th className="p-2">Event</th>
            {columns.map((c) => (
              <th key={c.id} className="p-2">
                <div className="text-[10px] uppercase text-muted-foreground">{c.usual_day === 0 ? "same day" : `day ${c.usual_day} after`}</div>
                <div>{c.title}</div>
                <div className="text-[10px] font-normal text-muted-foreground">
                  after {c.events} of {c.of} · {money(c.total_minor)} in all{c.checks ? ` · checks ${c.checks[0]} to ${c.checks[1]}` : ""}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {t.rows.map((r, i) => (
            <tr key={r.date} className="border-t border-border align-top">
              <th className="p-2 text-left font-medium">{i + 1} · {day(r.date)} {r.date.slice(0, 4)}{r.label ? <div className="font-normal">{r.label}</div> : null}</th>
              {columns.map((c) => <td key={c.id} className="p-2"><Cell items={r.cells[c.id] ?? []} /></td>)}
            </tr>
          ))}
          {ow && (
            <tr className="border-t-2 border-border align-top" data-testid="money-other-weeks">
              <th className="p-2 text-left font-medium">Every other week<div className="font-normal text-muted-foreground">{ow.weeks} weeks{ow.from ? `, ${ow.from} to ${ow.to}` : ""}</div></th>
              {columns.map((c) => (
                <td key={c.id} className="p-2">
                  {(ow.found[c.id] ?? []).length === 0 ? "none" : `${ow.found[c.id].length} ${ow.found[c.id].length === 1 ? "payment" : "payments"}`}
                </td>
              ))}
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
