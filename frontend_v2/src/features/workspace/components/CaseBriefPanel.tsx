import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, CheckCircle2, History, Loader2, RefreshCw } from "lucide-react"
import { useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { correctionMoney } from "@/features/financial/lib/correction-contract"

/** One section list: the full count, the items shown, and how many are not shown. */
interface Clipped<T> { count: number; items: T[]; not_shown: number }
interface Sentence { sentence: string; kind?: string; account_id?: string; reference?: string }
interface CurrencyTotals { rows: number; credits_minor: string; debits_minor: string; net_minor: string }
interface TotalsLine {
  population: "verified" | "working"
  currency: string
  before: CurrencyTotals | null
  after: CurrencyTotals | null
  changed: boolean
  rows_change: number
}
interface ConclusionChange { kind: string; id: string; title: string; sentence: string; rows: { id: string }[] }

export interface CaseBrief {
  id: string
  created_at: string
  checked_at: string
  trigger: string
  ledger_revision: string
  out_of_date?: boolean
  out_of_date_sentence?: string | null
  newest_evidence_at?: string | null
  changes: {
    first: boolean
    something_changed: boolean
    leads_closed: Clipped<Sentence>
    leads_opened: Clipped<Sentence>
    open_leads: { accounts_not_read: number; missing_periods: number; missing_days: number; missing_accounts: number; phone_leads: number }
    newly_testable: {
      spans: Clipped<Sentence & { days: number }>
      days: number
      phone_outcomes_before: Record<string, number> | null
      phone_outcomes_after: Record<string, number>
      phone_unresolved_change: number
      phone_contradicted_change: number
      phone_corroborated_change: number
    }
    totals: {
      before_revision: string | null
      after_revision: string
      available: boolean
      reason: string | null
      before_unavailable?: boolean
      basis: string
      verified_rows: number | null
      working_rows: number | null
      outside_verified_rows: number | null
      currencies: TotalsLine[]
      changed: number
    }
    judgement_calls: { open: number; open_before: number | null; added_open: number; resolved: number; added_by_rule: Record<string, number> }
    conclusions_changed: Clipped<ConclusionChange>
    conclusions: { total: number; hypotheses_open: number; citing_rows: number; rows_cited: number }
  }
  coverage: {
    statements_admitted: number
    accounts: number
    accounts_read: number
    ledger_rows_verified: number | null
    ledger_rows_working: number | null
    phones: number
    conclusions: number
    importing: number
    not_read: string[]
    questions: string[]
  }
  cost: { seconds: number; model_calls: number }
}

interface LatestResponse { brief: CaseBrief | null; requested_at: string | null }

const when = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" })
const fmt = (v: string | null | undefined) => (v ? when.format(new Date(v)) : "never")
const plural = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString()} ${n === 1 ? one : many}`
const short = (rev: string | null) => (rev ? rev.slice(0, 8) : "none")

function List({ title, items, notShown, empty }: { title: string; items: string[]; notShown: number; empty: string }) {
  return (
    <div>
      <h3 className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">{title}</h3>
      {items.length ? (
        <ul className="mt-1.5 space-y-1 text-xs leading-relaxed">
          {items.map((s, i) => <li key={i}>{s}</li>)}
          {notShown ? <li className="text-muted-foreground">{plural(notShown, "more item")} not shown here.</li> : null}
        </ul>
      ) : <p className="mt-1.5 text-xs text-muted-foreground">{empty}</p>}
    </div>
  )
}

function money(minor: string | undefined, currency: string) {
  return minor === undefined ? "none" : correctionMoney(minor, currency)
}

export function CaseBriefPanel({ caseId, canEdit }: { caseId: string; canEdit: boolean }) {
  const qc = useQueryClient()
  const [asked, setAsked] = useState(false)
  const latest = useQuery({
    queryKey: ["case-brief", caseId],
    queryFn: () => fetchAPI<LatestResponse>(`/api/case-briefs/latest?case_id=${encodeURIComponent(caseId)}`),
    refetchInterval: (q) => (q.state.data?.requested_at || asked ? 20_000 : false),
  })
  const run = useMutation({
    mutationFn: () => fetchAPI<{ requested: boolean }>("/api/case-briefs/run", { method: "POST", body: { case_id: caseId } }),
    onSuccess: () => { setAsked(true); void qc.invalidateQueries({ queryKey: ["case-brief", caseId] }) },
  })

  const header = (
    <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
      <div>
        <div className="flex items-center gap-2"><History className="size-4 text-muted-foreground" /><h2 id="case-brief-heading" className="text-sm font-semibold">What changed</h2></div>
        <p className="mt-0.5 text-xs text-muted-foreground">A dated brief written when statements arrive, and each night: leads closed, what can now be tested, verified totals before and after, judgement calls, and conclusions whose cited payments changed.</p>
      </div>
      {canEdit ? (
        <Button type="button" variant="ghost" size="sm" disabled={run.isPending} onClick={() => run.mutate()}>
          {run.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />} Check now
        </Button>
      ) : null}
    </div>
  )

  if (latest.isLoading) {
    return <section className="overflow-hidden rounded-xl border border-border bg-card shadow-sm" aria-labelledby="case-brief-heading">{header}<p className="px-4 py-4 text-xs text-muted-foreground"><Loader2 className="mr-1 inline size-3 animate-spin" />Reading the latest brief for this case.</p></section>
  }
  if (latest.isError) {
    return <section className="overflow-hidden rounded-xl border border-border bg-card shadow-sm" aria-labelledby="case-brief-heading">{header}<p className="px-4 py-4 text-xs text-status-error">The brief could not be loaded: {latest.error instanceof Error ? latest.error.message : "unknown error"}.</p></section>
  }
  const brief = latest.data?.brief
  const pending = latest.data?.requested_at || asked
  if (!brief) {
    return (
      <section className="overflow-hidden rounded-xl border border-border bg-card shadow-sm" aria-labelledby="case-brief-heading">
        {header}
        <p className="px-4 py-4 text-xs text-muted-foreground">
          {pending ? "The first brief for this case is being prepared; it appears here within a few minutes." : "No brief yet. The first one is written after the next statement import, the nightly check, or when you choose Check now."}
        </p>
      </section>
    )
  }
  const c = brief.changes
  const cov = brief.coverage
  const totals = c.totals.currencies
  return (
    <section className="overflow-hidden rounded-xl border border-border bg-card shadow-sm" aria-labelledby="case-brief-heading" data-testid="case-brief">
      {header}
      <div className="space-y-4 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
          <span>Brief of {fmt(brief.created_at)}</span>
          <span>· last checked {fmt(brief.checked_at)}</span>
          <span>· ledger revision {short(brief.ledger_revision)}</span>
          {brief.out_of_date ? (
            <Badge variant="warning"><AlertTriangle className="size-3" /> Out of date</Badge>
          ) : (
            <Badge variant="success"><CheckCircle2 className="size-3" /> Current</Badge>
          )}
          {pending ? <Badge variant="outline"><Loader2 className="size-3 animate-spin" /> New brief being prepared</Badge> : null}
        </div>
        {brief.out_of_date && brief.out_of_date_sentence ? (
          <p className="rounded-md border border-status-warning/50 bg-status-warning-soft px-3 py-2 text-xs text-status-warning">{brief.out_of_date_sentence}</p>
        ) : null}
        {cov.not_read.length ? (
          <p className="rounded-md border border-status-warning/50 bg-status-warning-soft px-3 py-2 text-xs text-status-warning">
            This brief is incomplete. Not read: {cov.not_read.join("; ")}.
          </p>
        ) : null}
        {c.first ? (
          <p className="text-xs">This is the first brief for this case: it records the starting point. Later briefs compare against it.</p>
        ) : null}

        <div className="grid gap-4 md:grid-cols-2">
          <List
            title={`Leads closed (${c.leads_closed.count})`}
            items={c.leads_closed.items.map((l) => l.sentence)}
            notShown={c.leads_closed.not_shown}
            empty={c.first ? "Nothing to compare yet." : "No lead closed since the last brief."}
          />
          <List
            title={`New leads (${c.leads_opened.count})`}
            items={c.leads_opened.items.map((l) => l.sentence)}
            notShown={c.leads_opened.not_shown}
            empty={c.first ? "Nothing to compare yet." : "No new lead since the last brief."}
          />
        </div>
        <p className="text-xs text-muted-foreground">
          Open now{c.open_leads.accounts_not_read ? ` (${plural(c.open_leads.accounts_not_read, "account")} could not be read and ${c.open_leads.accounts_not_read === 1 ? "is" : "are"} not counted)` : ""}: {plural(c.open_leads.missing_periods, "missing statement period")} ({plural(c.open_leads.missing_days, "day")}), {plural(c.open_leads.missing_accounts, "account")} named in payments with no statement in the case{cov.phones ? `, ${plural(c.open_leads.phone_leads, "phone account lead")}` : ""}.
        </p>

        <List
          title={`Now testable (${plural(c.newly_testable.days, "newly covered day")})`}
          items={[
            ...c.newly_testable.spans.items.map((s) => s.sentence),
            ...(c.newly_testable.phone_unresolved_change < 0
              ? [`Phone money readings that cannot yet be decided: ${c.newly_testable.phone_outcomes_before?.unresolved ?? 0} → ${c.newly_testable.phone_outcomes_after.unresolved ?? 0}. With a matching payment: ${c.newly_testable.phone_outcomes_before?.corroborated ?? 0} → ${c.newly_testable.phone_outcomes_after.corroborated ?? 0}. With no matching payment in a covered period: ${c.newly_testable.phone_outcomes_before?.contradicted ?? 0} → ${c.newly_testable.phone_outcomes_after.contradicted ?? 0}.`]
              : []),
          ]}
          notShown={c.newly_testable.spans.not_shown}
          empty={c.first ? "Nothing to compare yet." : "No newly covered days since the last brief."}
        />

        <div>
          <h3 className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">Totals</h3>
          {c.totals.before_unavailable ? (
            <p className="mt-1.5 text-xs text-status-warning">The previous brief could not calculate totals, so no before figures are shown.</p>
          ) : null}
          {!c.totals.available ? (
            <p className="mt-1.5 text-xs text-status-warning">Verified totals were not calculated: {c.totals.reason}</p>
          ) : totals.length ? (
            <table className="mt-1.5 w-full text-xs">
              <thead className="text-left text-[11px] text-muted-foreground">
                <tr><th className="py-1 font-medium">Totals</th><th className="font-medium">Currency</th><th className="font-medium">Money in, before → after</th><th className="font-medium">Money out, before → after</th><th className="font-medium">Payments</th></tr>
              </thead>
              <tbody className="divide-y divide-border">
                {totals.map((t) => (
                  <tr key={`${t.population}-${t.currency}`} className={t.changed && !c.first ? "font-medium" : undefined}>
                    <td className="py-1">{t.population === "verified" ? "Verified" : "Working"}</td>
                    <td>{t.currency}</td>
                    <td>{c.first ? money(t.after?.credits_minor, t.currency) : `${money(t.before?.credits_minor, t.currency)} → ${money(t.after?.credits_minor, t.currency)}`}</td>
                    <td>{c.first ? money(t.after?.debits_minor, t.currency) : `${money(t.before?.debits_minor, t.currency)} → ${money(t.after?.debits_minor, t.currency)}`}</td>
                    <td>{(t.after?.rows ?? 0).toLocaleString()}{!c.first && t.rows_change ? ` (${t.rows_change > 0 ? "+" : ""}${t.rows_change.toLocaleString()})` : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p className="mt-1.5 text-xs text-muted-foreground">No payments in this case.</p>}
          {c.totals.available && !(c.totals.verified_rows ?? 0) && (c.totals.working_rows ?? 0) ? (
            <p className="mt-1 text-xs">No payment in this case is in the verified totals yet: all {plural(c.totals.working_rows ?? 0, "payment")} were accepted after review and count in the working totals only.</p>
          ) : null}
          <p className="mt-1 text-[11px] text-muted-foreground">
            {c.first ? `Ledger revision ${short(c.totals.after_revision)}.` : `Ledger revision ${short(c.totals.before_revision)} → ${short(c.totals.after_revision)}.`} {c.totals.basis}
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">Judgement calls</h3>
            <p className="mt-1.5 text-xs">
              {plural(c.judgement_calls.open, "open call")}
              {c.first ? "." : `; ${c.judgement_calls.added_open.toLocaleString()} added and ${c.judgement_calls.resolved.toLocaleString()} confirmed or corrected since the last brief.`}
            </p>
          </div>
          <List
            title={`Conclusions whose cited payments changed (${c.conclusions_changed.count})`}
            items={c.conclusions_changed.items.map((x) => x.sentence)}
            notShown={c.conclusions_changed.not_shown}
            empty={`None. ${plural(c.conclusions.total, "finding, hypothesis or assessment", "findings, hypotheses and assessments")} checked; ${c.conclusions.citing_rows.toLocaleString()} cite ledger payments.`}
          />
        </div>

        <details className="rounded-md border border-border/70 px-3 py-2 text-[11px] text-muted-foreground">
          <summary className="cursor-pointer">Coverage and cost of this brief</summary>
          <p className="mt-1">
            Read {plural(cov.statements_admitted, "statement")}, {cov.accounts_read} of {plural(cov.accounts, "account")}, {plural(cov.ledger_rows_working ?? 0, "payment")} ({(cov.ledger_rows_verified ?? 0).toLocaleString()} verified){cov.phones ? `, ${plural(cov.phones, "phone")}` : ""} and {plural(cov.conclusions, "conclusion")}.
            Questions re-run: {cov.questions.join("; ")}.
          </p>
          {cov.not_read.length ? null : <p className="mt-1">Nothing was left unread.</p>}
          <p className="mt-1">Took {brief.cost.seconds.toFixed(1)} s of database work; no AI model was used ({brief.cost.model_calls} calls). Written after: {brief.trigger.replace(/_/g, " ")}.</p>
        </details>
      </div>
    </section>
  )
}
