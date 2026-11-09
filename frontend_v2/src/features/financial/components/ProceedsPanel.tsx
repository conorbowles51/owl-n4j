import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { useFinancialAccess } from "../hooks/use-financial-access"
import {
  assumptionInput,
  assumptionText,
  confirmAssumption,
  createProceeds,
  getProceeds,
  listProceeds,
  proceedsKeys,
  proceedsMoney,
  setAssumption,
  type ProceedsAssumption,
  type ProceedsView,
} from "../lib/proceeds"

const heading = { fontFamily: "'Space Grotesk', ui-sans-serif, system-ui, sans-serif", letterSpacing: "-0.025em" }
const field = "rounded border bg-background px-2 py-1 text-sm"

function unitText(a: Pick<ProceedsAssumption, "kind" | "unit">, currency: string) {
  return a.kind === "money" ? currency : a.kind === "percent" ? "%" : a.unit
}

function AssumptionRow({ caseId, calc, a, canEdit }: { caseId: string; calc: ProceedsView; a: ProceedsAssumption; canEdit: boolean }) {
  const client = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [low, setLow] = useState(assumptionInput(a.kind, a.low, calc.currency))
  const [high, setHigh] = useState(assumptionInput(a.kind, a.high, calc.currency))
  const show = (raw: unknown) => assumptionText(a.kind, raw, calc.currency)
  const [source, setSource] = useState(a.source || "")
  const [reason, setReason] = useState("")
  const [history, setHistory] = useState(false)
  const done = (data: ProceedsView) => {
    client.setQueryData(proceedsKeys.one(caseId, calc.id), data)
    setEditing(false)
  }
  const save = useMutation({
    mutationFn: () => setAssumption(caseId, calc.id, a.key, { low, high, source, reason }),
    onSuccess: done,
  })
  const confirm = useMutation({
    mutationFn: (judgementId: string) => confirmAssumption(caseId, calc.id, a.key, judgementId),
    onSuccess: done,
  })
  const unit = unitText(a, calc.currency)
  return (
    <li className="space-y-1.5 border-t pt-2" data-testid="proceeds-assumption" data-key={a.key}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-semibold">{a.label}</span>
        {a.current ? (
          <span>
            {a.low === a.high ? show(a.low) : `${show(a.low)} to ${show(a.high)}`}{a.kind === "money" ? "" : ` ${unit}`}
          </span>
        ) : (
          <span className="text-muted-foreground">Not set</span>
        )}
      </div>
      {a.current && (
        <p className="text-[13px] text-muted-foreground">
          Set by {a.set_by || "a person"} · source: {a.source}
        </p>
      )}
      {a.proposed.map((p) => {
        const ev = (p.evidence || {}) as Record<string, unknown>
        return (
          <div key={p.id} className="rounded bg-[#f1eefb] p-2 text-[13px] dark:bg-[#2a2147]" data-testid="proceeds-proposed">
            Proposed by the case agent: {show(ev.low)} to {show(ev.high)}{a.kind === "money" ? "" : ` ${unit}`} · source: {String(ev.source || "")}
            {p.summary ? ` · ${p.summary}` : ""}
            {canEdit && (
              <Button size="sm" variant="outline" className="ml-2" disabled={confirm.isPending} onClick={() => confirm.mutate(p.id)}>
                Use this, under my name
              </Button>
            )}
          </div>
        )
      })}
      {canEdit && !editing && (
        <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
          {a.current ? "Change" : "Set"}
        </Button>
      )}
      {editing && (
        <form
          className="grid gap-2 sm:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault()
            save.mutate()
          }}
        >
          <label className="flex flex-col gap-1">
            Lowest ({unit})
            <input className={field} required value={low} onChange={(e) => setLow(e.target.value)} inputMode="decimal" />
          </label>
          <label className="flex flex-col gap-1">
            Highest ({unit})
            <input className={field} required value={high} onChange={(e) => setHigh(e.target.value)} inputMode="decimal" />
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            Where the value comes from
            <input className={field} required value={source} onChange={(e) => setSource(e.target.value)}
              placeholder="A cited source (txn://, doc://, rec://) or a named reference" />
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            Why (optional)
            <input className={field} value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <div className="flex gap-2 sm:col-span-2">
            <Button size="sm" type="submit" disabled={save.isPending || !low.trim() || !high.trim() || !source.trim()}>
              Save under my name
            </Button>
            <Button size="sm" variant="outline" type="button" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </div>
        </form>
      )}
      {(save.error || confirm.error) && <p role="alert">{(save.error || confirm.error)?.message}</p>}
      {!!a.history.length && (
        <div>
          <button type="button" className="text-[13px] text-muted-foreground hover:text-foreground" aria-expanded={history}
            onClick={() => setHistory(!history)}>
            {history ? "▾" : "▸"} Earlier values ({a.history.length})
          </button>
          {history && (
            <ul className="pl-4 text-[13px] text-muted-foreground">
              {a.history.map((h) => {
                const ev = (h.evidence || {}) as Record<string, unknown>
                return (
                  <li key={h.id}>
                    {show(ev.low)} to {show(ev.high)}{a.kind === "money" ? "" : ` ${unit}`} · {String(ev.source || "")} · {h.resolution_reason || ""}
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      )}
    </li>
  )
}

function Calculation({ caseId, id, canEdit }: { caseId: string; id: string; canEdit: boolean }) {
  const query = useQuery({ queryKey: proceedsKeys.one(caseId, id), queryFn: () => getProceeds(caseId, id) })
  if (query.isPending) return <p role="status">Loading the calculation…</p>
  if (query.isError) return <p role="alert">{query.error.message}</p>
  const calc = query.data
  const money = (minor: number) => proceedsMoney(minor, calc.currency)
  return (
    <div className="space-y-3" data-testid="proceeds-calculation">
      <p className="text-[13px] text-muted-foreground">
        {calc.title} · {calc.currency}
        {calc.period_start ? ` · ${calc.period_start} to ${calc.period_end || "?"}` : ""} · started by {calc.created_by}.
        Formula: {calc.formula}.
      </p>
      <ul className="space-y-2">
        {calc.assumptions.map((a) => (
          <AssumptionRow key={a.key} caseId={caseId} calc={calc} a={a} canEdit={canEdit} />
        ))}
      </ul>
      <div className="rounded-lg border p-3" data-testid="proceeds-result">
        <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-[#8a5300] dark:text-[#fbd38d]">{calc.label}</p>
        {calc.result ? (
          <>
            <p className="text-sm">
              Range: <strong>{money(calc.result.low_minor)}</strong> to <strong>{money(calc.result.high_minor)}</strong>
              {" "}(middle of every assumption: {money(calc.result.mid_minor)}). This range comes from the assumptions
              above. It is not a measured amount.
            </p>
            <table className="mt-2 w-full text-left text-[13px]" aria-label="How the result moves per assumption">
              <thead className="text-muted-foreground">
                <tr>
                  <th className="py-1 pr-3 font-medium">Assumption, the others at their middle</th>
                  <th className="py-1 pr-3 font-medium">At its lowest</th>
                  <th className="py-1 pr-3 font-medium">At its highest</th>
                  <th className="py-1 font-medium">Moves the result by</th>
                </tr>
              </thead>
              <tbody>
                {calc.result.moves.map((m) => (
                  <tr key={m.key} className="border-t">
                    <td className="py-1 pr-3">{m.label}</td>
                    <td className="py-1 pr-3">{money(m.at_low_minor)}</td>
                    <td className="py-1 pr-3">{money(m.at_high_minor)}</td>
                    <td className="py-1">{money(m.swing_minor)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : (
          <p className="text-sm">No range yet. Still to set: {calc.missing.join(", ")}.</p>
        )}
      </div>
      <p className="text-[13px]" data-testid="proceeds-deposits">
        Deposits beside it, measured from the ledger
        {calc.deposits.categories.length ? ` (${calc.deposits.categories.join(", ")})` : ""}:{" "}
        {!calc.deposits.categories.length
          ? ""
          : calc.deposits.verified_rows
            ? `${money(calc.deposits.verified_minor)} over ${calc.deposits.verified_rows.toLocaleString()} rows. `
            : "no verified deposit in these categories yet. "}
        {calc.deposits.note}
      </p>
    </div>
  )
}

/** Proceeds calculator: deterministic arithmetic over assumptions a named person sets, each with its source. */
export function ProceedsPanel({ caseId }: { caseId: string }) {
  const { canEdit } = useFinancialAccess()
  const client = useQueryClient()
  const list = useQuery({ queryKey: proceedsKeys.all(caseId), queryFn: () => listProceeds(caseId) })
  const raw = list.data?.items
  const items = Array.isArray(raw) ? raw : []
  const [chosen, setChosen] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [title, setTitle] = useState("")
  const [currency, setCurrency] = useState("")
  const [start, setStart] = useState("")
  const [end, setEnd] = useState("")
  const [categories, setCategories] = useState("")
  const create = useMutation({
    mutationFn: () =>
      createProceeds(caseId, {
        title,
        currency,
        period_start: start || null,
        period_end: end || null,
        deposit_categories: categories.split(",").map((c) => c.trim()).filter(Boolean),
      }),
    onSuccess: (data) => {
      setCreating(false)
      setChosen(data.id)
      return client.invalidateQueries({ queryKey: proceedsKeys.all(caseId) })
    },
  })
  const current = chosen || items[0]?.id || null
  return (
    <section
      aria-label="Proceeds calculator"
      className="space-y-3 rounded-[14px] p-4 text-sm shadow-[0_1px_0_#e4e3df,0_8px_24px_rgba(20,22,27,.05)] dark:border"
    >
      <h2 className="text-[15px] font-semibold" style={heading}>Proceeds calculator</h2>
      <p className="text-muted-foreground">
        Volume × share that are deals × deals per message × price. Each value is a judgement call a named person sets
        with its source; the result is an estimate, not measured.
      </p>
      {list.isError && <p role="alert">{list.error.message}</p>}
      {!!items.length && (
        <div className="flex flex-wrap gap-2" role="group" aria-label="Calculations">
          {items.map((item) => (
            <Button key={item.id} size="sm" variant={item.id === current ? "primary" : "outline"} aria-pressed={item.id === current}
              onClick={() => setChosen(item.id)}>
              {item.title}
            </Button>
          ))}
        </div>
      )}
      {canEdit && !creating && (
        <Button size="sm" variant="outline" onClick={() => setCreating(true)}>
          New calculation
        </Button>
      )}
      {creating && (
        <form
          className="grid gap-2 sm:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault()
            create.mutate()
          }}
        >
          <label className="flex flex-col gap-1">Name<input className={field} required value={title} onChange={(e) => setTitle(e.target.value)} /></label>
          <label className="flex flex-col gap-1">Currency (three letters)<input className={field} required maxLength={3} value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} /></label>
          <label className="flex flex-col gap-1">From<input className={field} type="date" value={start} onChange={(e) => setStart(e.target.value)} /></label>
          <label className="flex flex-col gap-1">To<input className={field} type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></label>
          <label className="flex flex-col gap-1 sm:col-span-2">Deposit categories to show beside it (comma separated, optional)<input className={field} value={categories} onChange={(e) => setCategories(e.target.value)} /></label>
          <div className="flex gap-2 sm:col-span-2">
            <Button size="sm" type="submit" disabled={create.isPending}>Start</Button>
            <Button size="sm" variant="outline" type="button" onClick={() => setCreating(false)}>Cancel</Button>
          </div>
          {create.error && <p role="alert" className="sm:col-span-2">{create.error.message}</p>}
        </form>
      )}
      {list.isSuccess && !items.length && !creating && <p className="text-muted-foreground">No calculation in this case yet.</p>}
      {current && <Calculation caseId={caseId} id={current} canEdit={canEdit} />}
    </section>
  )
}
