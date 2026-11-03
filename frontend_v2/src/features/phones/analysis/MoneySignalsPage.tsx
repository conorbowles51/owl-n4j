import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { instantWords } from "@/features/phones/lib/time-words"
import { CollectBar } from "@/features/pattern/components/CollectBar"
import { moneyAPI, type AnalysisResult, type AnalysisRun } from "./money-api"

/**
 * Approach 1, money signals on the phone (05 section 4), in the shared results layout (05 section 3.9, AP-1): what it
 * does, Run, the coverage sentence, results with the total, the records behind a result, Add to…, and confirm or
 * reject with a reason. Every reading is from the phone (p4); a matched ledger row is a link only.
 */
export const WHAT_IT_DOES =
  "Finds money the phones record (bank and payment alerts, texts from banks, bank emails and amounts named in messages) and checks each against the payments in the financial records. It also lists banks, cards and accounts the phones show that the financial records do not include. It does not show what a payment was for."

const OUTCOME_WORDS: Record<string, string> = {
  corroborated: "Matches a payment in the financial records",
  near_amount: "Matches a payment once a small difference in amount is allowed",
  unresolved: "No matching payment found in the financial records",
  not_tested: "Not checked against the financial records",
}
const REASON_WORDS: Record<string, string> = {
  no_anchor: "The message names no bank and no account, so there is nothing to check it against.",
  not_in_productions: "No account in the financial records fits.",
  institution_held_account_unseen: "The financial records hold this bank, but not an account that fits.",
  amount_or_currency_missing: "The amount or currency could not be read for certain.",
  outside_coverage: "The statements in the case do not cover these dates.",
  candidate_inconclusive: "A payment could be this one, and the records will not say.",
}
const STRENGTH_WORDS: Record<string, string> = {
  institution_template: "From a known bank, in its usual wording",
  institution_generic: "From a known bank",
  unattributed: "Sender not known",
  transactional: "Payment alerts",
  account: "Saved logins or card records",
  presence: "App, website or cookie only",
}
const KIND_TABS = [
  { kind: "money_reading", label: "Money on the phones" },
  { kind: "account_lead", label: "Accounts the financial records do not include" },
] as const

/** "USD 1,234.56" from integer minor units and the currency's exponent; the text as written when either is unknown. */
export function amountWords(m: Record<string, any>): string {
  if (m.amount_minor == null || !m.currency) return `${m.amount_text} (as written)`
  let exp = 2
  try {
    exp = new Intl.NumberFormat("en-US", { style: "currency", currency: m.currency }).resolvedOptions().maximumFractionDigits ?? 2
  } catch {
    return `${m.amount_text} (as written)`
  }
  const digits = String(m.amount_minor).padStart(exp + 1, "0")
  const whole = digits.slice(0, digits.length - exp).replace(/\B(?=(\d{3})+(?!\d))/g, ",")
  return `${m.currency} ${whole}${exp ? "." + digits.slice(-exp) : ""}`
}

function RunControl({ caseId, run, onRequested }: { caseId: string; run: AnalysisRun | null; onRequested: (r: AnalysisRun) => void }) {
  const [err, setErr] = useState<string | null>(null)
  const busy = run && (run.status === "queued" || run.status === "running")
  const request = useMutation({ mutationFn: () => moneyAPI.request(caseId), onSuccess: onRequested, onError: (e) => setErr(String((e as Error).message || e)) })
  const cancel = useMutation({ mutationFn: () => moneyAPI.cancel(caseId, run!.id), onSuccess: onRequested })
  const p = run?.progress || {}
  return (
    <section aria-label="Run" className="flex flex-wrap items-center gap-3 text-sm">
      <Button size="sm" onClick={() => request.mutate()} disabled={!!busy || request.isPending}>Run</Button>
      {busy && (
        <>
          <span role="status">{run!.status === "queued" ? "Waiting to start." : `Read ${(p.read ?? 0).toLocaleString("en-US")} of ${(p.total ?? 0).toLocaleString("en-US")} readings.`}</span>
          <Button size="sm" variant="outline" onClick={() => cancel.mutate()}>Cancel</Button>
        </>
      )}
      {run?.status === "completed" && run.finished_at && <span className="text-muted-foreground">Last run {instantWords(run.finished_at, "UTC")}.</span>}
      {run?.status === "failed" && <span role="alert" className="text-destructive">The last run stopped: {run.error}</span>}
      {err && <span role="alert" className="text-destructive">{err}</span>}
    </section>
  )
}

function Decide({ caseId, result, onDone }: { caseId: string; result: AnalysisResult; onDone: () => void }) {
  const [reason, setReason] = useState("")
  const [err, setErr] = useState<string | null>(null)
  const m = useMutation({
    mutationFn: (d: "confirmed" | "rejected") => moneyAPI.decide(caseId, result.id, d, reason.trim()),
    onSuccess: () => { setReason(""); onDone() },
    onError: (e) => setErr(String((e as Error).message || e)),
  })
  function go(d: "confirmed" | "rejected") {
    if (!reason.trim()) { setErr("Say why, in your own words."); return }
    setErr(null)
    m.mutate(d)
  }
  return (
    <div className="mt-2 space-y-1" aria-label="Confirm or reject">
      {result.decisions.map((d, i) => (
        <p key={i} className="text-xs">{d.decision === "confirmed" ? "Confirmed" : "Rejected"} by {d.by}: {d.reason}</p>
      ))}
      <Textarea aria-label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} className="h-14 text-xs" placeholder="Why" />
      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={() => go("confirmed")}>Confirm</Button>
        <Button size="sm" variant="outline" onClick={() => go("rejected")}>Reject</Button>
      </div>
      {err && <p role="alert" className="text-xs text-destructive">{err}</p>}
    </div>
  )
}

function Behind({ caseId, result }: { caseId: string; result: AnalysisResult }) {
  const q = useQuery({ queryKey: ["money-detail", caseId, result.id], queryFn: () => moneyAPI.detail(caseId, result.id) })
  if (!q.data) return <p className="text-xs text-muted-foreground">Loading the records behind it.</p>
  const recs = q.data.records
  const phone = recs.filter((r) => r.record_uid)
  const ledger = recs.filter((r) => r.ledger_transaction_id)
  return (
    <div className="space-y-1 text-xs" aria-label="Records behind it">
      {phone.map((r) => (
        <div key={r.record_uid!}>
          <Link className="underline" to={`/cases/${caseId}/records/${r.record_uid}`}>Open the phone record</Link>
        </div>
      ))}
      {ledger.map((r) => (
        <div key={r.ledger_transaction_id!}>
          <Link className="underline" to={`/cases/${caseId}/financial?payment=${r.ledger_transaction_id}`}>Open payment {r.ledger_ref_id}</Link>
        </div>
      ))}
      <CollectBar caseId={caseId} noun="record" origin="phone-money"
        links={phone.map((r) => ({ target_type: "phone_record", target_id: r.record_uid!, label: result.measures.sentence || "Phone money reading", source_anchor: { kind: "phone_record", record_uid: r.record_uid } }))} />
    </div>
  )
}

function ReadingRow({ caseId, r, onChanged }: { caseId: string; r: AnalysisResult; onChanged: () => void }) {
  const [open, setOpen] = useState(false)
  const m = r.measures
  const when = m.event_instant ? instantWords(m.event_instant, m.device_zone || "UTC") : "Time not recorded"
  const title = r.kind === "money_reading"
    ? `${amountWords(m)} ${m.direction === "debit" ? "out" : m.direction === "credit" ? "in" : ""}`.trim()
    : `${m.institution?.name || "Card or account"}${m.account_ref ? `, ${m.account_ref}` : ""}`
  return (
    <li className="rounded border p-2 text-sm" data-testid="money-result">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="rounded bg-muted px-1 text-xs">{r.label}</span>
        <button className="font-medium underline-offset-2 hover:underline" onClick={() => setOpen(!open)} aria-expanded={open}>{title}</button>
        {r.kind === "money_reading" && <span className="text-xs text-muted-foreground">{m.source} on {m.phone_label}, {when}. From the phone, not a statement.</span>}
        <span className="text-xs">{STRENGTH_WORDS[r.strength] || r.strength}</span>
        {r.decision && <span className="text-xs">{r.decision === "confirmed" ? "Confirmed" : "Rejected"}</span>}
      </div>
      {r.kind === "money_reading" && (
        <p className="text-xs">
          {OUTCOME_WORDS[m.outcome] || m.outcome}
          {m.reason && REASON_WORDS[m.reason] ? `. ${REASON_WORDS[m.reason]}` : "."}
          {m.institution && ` ${m.institution.name}.`}
          {m.account_ref && ` Account ${m.account_ref}.`}
        </p>
      )}
      {r.kind === "account_lead" && <p className="text-xs">{m.sentence}</p>}
      {open && (
        <div className="mt-2 space-y-2">
          {r.directions.undercuts.length > 0 && (
            <ul className="list-disc pl-4 text-xs" aria-label="What weakens it">{r.directions.undercuts.map((d, i) => <li key={i}>{d.detail}</li>)}</ul>
          )}
          <Behind caseId={caseId} result={r} />
          <Decide caseId={caseId} result={r} onDone={onChanged} />
        </div>
      )}
    </li>
  )
}

export default function MoneySignalsPage() {
  const { id: caseId = "" } = useParams()
  const qc = useQueryClient()
  const [run, setRun] = useState<AnalysisRun | null>(null)
  const [kind, setKind] = useState<string>("money_reading")
  const [strength, setStrength] = useState("")
  const [offset, setOffset] = useState(0)
  const runs = useQuery({ queryKey: ["money-runs", caseId], queryFn: () => moneyAPI.runs(caseId), enabled: !!caseId })
  const coverage = useQuery({ queryKey: ["money-coverage", caseId], queryFn: () => moneyAPI.coverage(caseId), enabled: !!caseId })
  useEffect(() => {
    const items = runs.data?.items || []
    setRun((cur) => cur ?? items.find((r) => r.status === "completed") ?? items[0] ?? null)
  }, [runs.data])
  const active = run && (run.status === "queued" || run.status === "running")
  useEffect(() => {
    if (!active || !run) return
    const t = window.setInterval(async () => {
      const next = await moneyAPI.run(caseId, run.id)
      setRun(next)
      if (next.status === "completed") qc.invalidateQueries({ queryKey: ["money-results", caseId] })
    }, 2000)
    return () => window.clearInterval(t)
  }, [active, run, caseId, qc])
  const done = run?.status === "completed" ? run : null
  const results = useQuery({
    queryKey: ["money-results", caseId, done?.id, kind, strength, offset],
    queryFn: () => moneyAPI.results(caseId, done!.id, kind, strength, offset),
    enabled: !!done,
  })
  const total = results.data?.total ?? 0
  const shown = results.data?.items.length ?? 0
  return (
    <div className="space-y-4 p-4" data-testid="money-signals-page">
      <h1 className="text-lg font-semibold">Money on the phones</h1>
      <p data-part="what">{WHAT_IT_DOES}</p>
      <div data-part="run"><RunControl caseId={caseId} run={run} onRequested={setRun} /></div>
      <p data-part="coverage" className="text-sm">{done?.coverage?.sentence || coverage.data?.sentence}</p>
      <section data-part="results" aria-label="Results" className="space-y-2">
        <div className="flex flex-wrap gap-2" role="tablist">
          {KIND_TABS.map((t) => (
            <Button key={t.kind} size="sm" role="tab" aria-selected={kind === t.kind} variant={kind === t.kind ? "default" : "outline"}
              onClick={() => { setKind(t.kind); setStrength(""); setOffset(0) }}>{t.label}</Button>
          ))}
          <select aria-label="Strength" className="rounded border px-1 text-xs" value={strength} onChange={(e) => { setStrength(e.target.value); setOffset(0) }}>
            <option value="">Any source</option>
            {Object.entries(STRENGTH_WORDS).filter(([k]) => kind === "money_reading" ? k.startsWith("institution") || k === "unattributed" : !k.startsWith("institution") && k !== "unattributed")
              .map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        {!done && !active && <p className="text-sm">Not run yet in this case. Press Run.</p>}
        {done && (
          <p className="text-sm" data-testid="money-total">
            {total.toLocaleString("en-US")} {total === 1 ? "result" : "results"}
            {shown < total ? `, showing ${(offset + 1).toLocaleString("en-US")} to ${(offset + shown).toLocaleString("en-US")}` : ""}.
          </p>
        )}
        <ul className="space-y-2">
          {(results.data?.items || []).map((r) => (
            <ReadingRow key={r.id} caseId={caseId} r={r} onChanged={() => qc.invalidateQueries({ queryKey: ["money-results", caseId] })} />
          ))}
        </ul>
        {done && (offset > 0 || offset + shown < total) && (
          <div className="flex gap-2">
            <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 100))}>Earlier</Button>
            <Button size="sm" variant="outline" disabled={offset + shown >= total} onClick={() => setOffset(offset + 100)}>Later</Button>
          </div>
        )}
      </section>
    </div>
  )
}
