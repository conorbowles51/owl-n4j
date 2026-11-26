import { useEffect, useMemo, useState } from "react"
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { recordPath } from "@/lib/record-links"
import { meaningPath } from "@/features/search/lib/open-hit"
import { openCorroborate } from "@/features/leads/open"
import { PhoneShape } from "../ui/PhoneChip"
import { askAPI, type Answer, type AskPhone, type AskRow, type ElsewhereRow, type Statement, type Step } from "./api"
import { corroborateStart, permissionLine } from "./ask-logic"

/**
 * Ask the phones a question (phones redesign, screen 7). The answer is separate statements, each citing the phone
 * records it rests on and followed by what the rest of the case says; then what was not found, what was searched,
 * next steps computed from the answer, and Corroborate. Everything the model wrote is labelled as such.
 */
const RELATION: Record<string, { words: string; cls: string }> = {
  agrees: { words: "Agrees", cls: "text-status-success" },
  disagrees: { words: "Disagrees", cls: "text-status-warning" },
  missing_here: { words: "Missing here", cls: "text-status-warning" },
  possible_match: { words: "Possible match, not confirmed", cls: "text-status-info" },
  nothing_found: { words: "Nothing found", cls: "text-muted-foreground" },
}
const SOURCE_CLS: Record<string, string> = {
  Financial: "bg-money-in-soft text-money-in",
  Documents: "bg-source-4-soft text-source-4",
  Timeline: "bg-status-warning-soft text-status-warning",
}

function phoneIndex(phones: AskPhone[], id: string | null | undefined): number {
  const i = phones.findIndex((p) => p.extraction_id === id)
  return i < 0 ? 0 : i
}

function Cite({ caseId, label, record, index }: { caseId: string; label: string; record: string; index: number }) {
  return (
    <Link to={recordPath(caseId, record)} className="inline-flex items-center gap-1 rounded-sm border bg-card px-1.5 py-0.5 font-mono text-xs text-foreground hover:bg-accent">
      <PhoneShape index={index} />
      {label}
    </Link>
  )
}

const ORDER: Record<string, number> = { disagrees: 0, missing_here: 1, agrees: 2, possible_match: 3, nothing_found: 4 }

function ElsewhereRowView({ caseId, r }: { caseId: string; r: ElsewhereRow }) {
  const rel = { words: r.relation_label || RELATION[r.relation]?.words || r.relation, cls: RELATION[r.relation]?.cls ?? "text-muted-foreground" }
  return (
    <div className="flex flex-wrap items-start gap-2.5">
      <span className={`w-24 shrink-0 rounded-full px-2 py-0.5 text-center text-xs font-semibold ${SOURCE_CLS[r.source] ?? "bg-source-1-soft text-source-1"}`}>{r.source}</span>
      <span className="min-w-0 flex-1 text-sm leading-snug">
        {r.text}{" "}
        {r.cite && r.cite_label && <Link to={meaningPath(caseId, r.cite)} className="rounded-sm border px-1 font-mono text-xs hover:bg-accent">{r.cite_label}</Link>}
        {r.reason && <span className="block text-xs text-muted-foreground">{r.reason}</span>}
      </span>
      <span className={`shrink-0 text-xs font-semibold ${rel.cls}`}>{rel.words}</span>
    </div>
  )
}

/** Rows that share source, relation and reason (a message's copies on another phone) are one group. */
function groupRows(rows: ElsewhereRow[]) {
  const groups = new Map<string, ElsewhereRow[]>()
  for (const r of rows) {
    const key = `${r.source}|${r.relation}|${r.reason ?? ""}`
    groups.set(key, [...(groups.get(key) ?? []), r])
  }
  return [...groups.entries()].map(([key, rs]) => ({ key, rows: rs }))
}

function RowGroup({ caseId, rows }: { caseId: string; rows: ElsewhereRow[] }) {
  const [open, setOpen] = useState(false)
  const shown = open || rows.length <= 2 ? rows : rows.slice(0, 1)
  return (
    <>
      {shown.map((r, i) => <ElsewhereRowView key={i} caseId={caseId} r={r} />)}
      {rows.length > 2 && (
        <button type="button" aria-expanded={open} onClick={() => setOpen((v) => !v)} className="self-start text-sm text-muted-foreground underline underline-offset-2 hover:text-foreground">
          {open ? "Show fewer" : `${(rows.length - 1).toLocaleString("en-US")} more like this (${rows[0].source}, ${(rows[0].relation_label || rows[0].relation).toLowerCase()})`}
        </button>
      )}
    </>
  )
}

function ElsewhereBlock({ caseId, st }: { caseId: string; st: Statement }) {
  const [showEmpty, setShowEmpty] = useState(false)
  const rows = st.elsewhere?.rows
  const found = (rows ?? []).filter((r) => r.relation !== "nothing_found").sort((x, y) => (ORDER[x.relation] ?? 9) - (ORDER[y.relation] ?? 9))
  const empty = (rows ?? []).filter((r) => r.relation === "nothing_found")
  const where = [...new Set(empty.map((r) => r.source))]
  return (
    <div className="flex flex-col gap-2 border-t pt-3">
      <div className="text-xs text-muted-foreground">What the rest of the case says</div>
      {(rows == null || st.elsewhere?.note) && <p className="text-sm text-muted-foreground">{st.elsewhere?.note ?? "The rest of the case was not checked for this statement."}</p>}
      {rows != null && rows.length === 0 && <p className="text-sm text-muted-foreground">Nothing in the other phones, financial records, documents or timeline bears on it.</p>}
      {groupRows(found).map((g) => <RowGroup key={g.key} caseId={caseId} rows={g.rows} />)}
      {empty.length > 0 && (
        <div className="text-sm text-muted-foreground">
          <button type="button" className="underline underline-offset-2 hover:text-foreground" aria-expanded={showEmpty} onClick={() => setShowEmpty((v) => !v)}>
            {`Nothing found in ${empty.length.toLocaleString("en-US")} ${empty.length === 1 ? "check" : "checks"}: ${where.join(", ")}`}
          </button>
          {showEmpty && <div className="mt-2 flex flex-col gap-2">{empty.map((r, i) => <ElsewhereRowView key={i} caseId={caseId} r={r} />)}</div>}
        </div>
      )}
    </div>
  )
}

function AnswerView({ caseId, answer, onCorroborate, onAsk }: { caseId: string; answer: Answer; onCorroborate: (w: number | "all") => void; onAsk: (q: string) => void }) {
  const [showUsed, setShowUsed] = useState(false)
  const navigate = useNavigate()
  const c = `/cases/${encodeURIComponent(caseId)}`
  const act = (s: Step) => {
    const a = s.action
    if (a.kind === "corroborate") return onCorroborate(a.statement ?? 0)
    if (a.kind === "open_phone" && a.extraction_id) return navigate(`${c}/phones/${encodeURIComponent(a.extraction_id)}`)
    if (a.kind === "open_record" && a.record) return navigate(recordPath(caseId, a.record))
    if (a.kind === "open_timeline") return navigate(`${c}/timeline`)
    if (a.kind === "case_search") return navigate(`${c}/search?q=${encodeURIComponent(a.q ?? answer.question)}`)
    if (a.kind === "search") return navigate(`${c}/phones?q=${encodeURIComponent(a.q ?? answer.question)}`)
    if (a.kind === "open_settings") return navigate(`${c}/settings`)
    if (a.kind === "ask" && a.q) return onAsk(a.q)
  }
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full border border-status-model px-2.5 py-0.5 text-xs font-semibold text-status-model">{answer.label}</span>
          <span className="text-xs text-muted-foreground">{answer.searched}</span>
        </div>
        <Button variant="outline" size="sm" type="button" aria-expanded={showUsed} onClick={() => setShowUsed((v) => !v)}>
          {showUsed ? "Hide the records it used" : "Show every record it used"}
        </Button>
      </div>
      {answer.error && <p role="alert" className="rounded-md border border-status-warning bg-status-warning-soft p-3 text-sm">{answer.error}</p>}
      {answer.notes.map((n, i) => <p key={i} className="text-sm text-muted-foreground">{n}</p>)}
      {showUsed && (
        <section aria-label="Every record it used" className="rounded-xl border bg-card p-4">
          <p className="mb-2 text-sm">The answer read {answer.records_used.length.toLocaleString("en-US")} records; {answer.records_used.filter((r) => r.cited).length.toLocaleString("en-US")} are cited below.</p>
          <ul className="flex flex-wrap gap-1.5">
            {answer.records_used.map((r) => (
              <li key={r.record} className={r.cited ? "" : "opacity-80"}>
                <Cite caseId={caseId} record={r.record} label={`${r.label}${r.cited ? "" : " · not cited"}`} index={phoneIndex(answer.phones, r.extraction_id)} />
              </li>
            ))}
          </ul>
        </section>
      )}
      {answer.statements.map((st, i) => (
        <article key={i} aria-label={`Statement ${i + 1}`} className="flex flex-col gap-3 rounded-xl border bg-card px-4 py-4">
          <p className="text-[15px] leading-relaxed">{st.text}</p>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-muted-foreground">On the phones</span>
            {st.cite_labels.map((x) => <Cite key={x.record} caseId={caseId} record={x.record} label={x.label} index={phoneIndex(answer.phones, x.extraction_id)} />)}
          </div>
          <ElsewhereBlock caseId={caseId} st={st} />
          <div><Button variant="ghost" size="sm" type="button" onClick={() => onCorroborate(i)}>Corroborate this statement</Button></div>
        </article>
      ))}
      {answer.not_found.length > 0 && (
        <section aria-label="Not found" className="rounded-xl border bg-card px-4 py-3.5 text-sm leading-relaxed">
          <span className="font-semibold">Not found.</span>{" "}
          {answer.not_found.map((n, i) => <span key={i}>{n.text}{n.asked && !n.text.toLowerCase().includes(n.asked.toLowerCase()) ? ` (looked for: ${n.asked})` : ""}{" "}</span>)}
        </section>
      )}
      {answer.steps.length > 0 && (
        <section aria-label="Next steps" className="rounded-xl border bg-card p-5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-base font-bold">Next steps</h2>
            <p className="text-xs text-muted-foreground">Most useful first, from what this answer found and what it could not.</p>
          </div>
          <ol className="mt-2 flex flex-col">
            {answer.steps.map((s, i) => (
              <li key={s.n} className="flex flex-wrap items-center gap-3.5 border-t py-3">
                <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-muted font-mono text-xs">{s.n}</span>
                <div className="min-w-0 flex-[1_1_360px]">
                  <div className="text-sm font-semibold">{s.title}</div>
                  <div className="mt-0.5 text-[13px] leading-snug text-muted-foreground">{s.why}</div>
                </div>
                <Button variant={i === 0 ? "primary" : "outline"} size="sm" type="button" onClick={() => act(s)}>{s.action.label}</Button>
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  )
}

export function AskPage() {
  const { id: caseId = "" } = useParams()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const askId = params.get("ask")
  const phones = useMemo(() => (params.get("phones") ?? "").split(",").filter(Boolean), [params])
  const [draft, setDraft] = useState(params.get("q") ?? "")
  const [moreFrom, setMoreFrom] = useState(20)

  const row = useQuery({
    queryKey: ["phone-ask", caseId, askId],
    queryFn: () => askAPI.read(caseId, askId!),
    enabled: !!caseId && !!askId,
    refetchInterval: (q) => ((q.state.data as AskRow | undefined)?.status === "running" ? 3000 : false),
  })
  const earlier = useQuery({ queryKey: ["phone-ask-earlier", caseId, moreFrom], queryFn: () => askAPI.earlier(caseId, 0, moreFrom), enabled: !!caseId })
  useEffect(() => {
    if (row.data?.status && row.data.status !== "running") void qc.invalidateQueries({ queryKey: ["phone-ask-earlier", caseId] })
  }, [row.data?.status, qc, caseId])
  useEffect(() => {
    if (row.data?.question) setDraft(row.data.question)
  }, [row.data?.question])

  const ask = useMutation({
    mutationFn: (question: string) => askAPI.ask(caseId, question, phones),
    onSuccess: (r) => {
      const next = new URLSearchParams(params)
      next.set("ask", r.id)
      next.delete("q")
      setParams(next)
      void qc.invalidateQueries({ queryKey: ["phone-ask-earlier", caseId] })
    },
  })
  const submit = (q: string) => {
    const t = q.trim()
    if (t) ask.mutate(t)
  }
  const answer = row.data?.status === "done" ? row.data.answer : null
  const corroborate = (which: number | "all") => {
    if (!answer) return
    const start = corroborateStart(answer, which)
    if (!start.members.length) return
    const what = which === "all" ? "the answer" : `statement ${which + 1}`
    // the Corroborate page opens with the question filled from the cited records and their period; nothing runs
    // until the person presses Ask there (lx-corroredo A)
    openCorroborate({
      caseId, screen: "Ask the phones",
      label: `Records cited by ${what}${start.people.length ? ` (${start.people.slice(0, 3).join(", ")})` : ""}`,
      members: start.members, scope: start.scope,
      ...(start.scope.from && start.scope.to ? { period: { from: start.scope.from, to: start.scope.to } } : {}),
    })
  }
  const toWords = () => navigate(`/cases/${encodeURIComponent(caseId)}/phones?${new URLSearchParams({ ...(draft.trim() ? { q: draft.trim() } : {}), ...(phones.length ? { phones: phones.join(",") } : {}) })}`)
  const scopePhones = row.data?.answer?.phones

  return (
    <div className="flex min-h-full flex-col">
      <header className="flex flex-col gap-3 border-b px-7 pb-4 pt-5">
        <nav aria-label="Breadcrumb" className="text-xs text-muted-foreground"><Link className="underline-offset-2 hover:underline" to={`/cases/${encodeURIComponent(caseId)}/phones`}>Phones</Link> / Ask</nav>
        <form className="flex flex-wrap items-center gap-2.5" onSubmit={(e) => { e.preventDefault(); submit(draft) }}>
          <div role="radiogroup" aria-label="Search or ask" className="flex h-[52px] rounded-lg border bg-card p-[3px]">
            <button type="button" role="radio" aria-checked="false" onClick={toWords} className="rounded-md px-3.5 text-sm font-medium text-muted-foreground hover:text-foreground">Search words</button>
            <button type="button" role="radio" aria-checked="true" className="rounded-md bg-muted px-3.5 text-sm font-semibold text-foreground">Ask a question</button>
          </div>
          <label htmlFor="phone-ask" className="sr-only">Ask the phones a question</label>
          <input id="phone-ask" type="text" value={draft} maxLength={1000} onChange={(e) => setDraft(e.target.value)} placeholder="Did anyone talk about moving the money?" className="h-[52px] min-w-[240px] flex-1 rounded-xl border border-input bg-card px-4 text-[15px] font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
          <Button type="submit" className="h-[52px] px-5" disabled={!draft.trim() || ask.isPending || row.data?.status === "running"}>Ask</Button>
        </form>
        <p className="text-xs text-muted-foreground">
          {scopePhones ? permissionLine(scopePhones) : `Reads ${phones.length ? `the ${phones.length} ${phones.length === 1 ? "phone" : "phones"} in scope` : "every phone in the case"}, and checks what it finds against the financial records, the documents and the case timeline. Each answer takes about a minute.`}
        </p>
        {ask.error && <p role="alert" className="text-sm text-status-error">{ask.error instanceof Error ? ask.error.message : "The question could not be asked."}</p>}
      </header>

      <div className="flex flex-1 flex-wrap">
        <section aria-label="Answer" className="flex min-w-0 flex-[999_1_600px] flex-col gap-4 px-7 py-5">
          {!askId && <p className="text-sm text-muted-foreground">Ask about people, money, places or times in plain words. The answer lists what the phones say, each part with the records it rests on.</p>}
          {askId && row.isLoading && <p className="text-sm text-muted-foreground">Opening the question…</p>}
          {row.error && <p role="alert" className="text-sm text-status-error">{row.error instanceof Error ? row.error.message : "The question could not be opened."}</p>}
          {row.data?.status === "running" && <p role="status" className="text-sm">Reading the phones for “{row.data.question}”. This takes about a minute; the answer appears here.</p>}
          {row.data?.status === "failed" && <p role="alert" className="rounded-md border border-status-warning bg-status-warning-soft p-3 text-sm">{row.data.error ?? "The question could not be answered. Ask it again."}</p>}
          {answer && <AnswerView caseId={caseId} answer={answer} onCorroborate={corroborate} onAsk={(q) => { setDraft(q); submit(q) }} />}
        </section>

        <aside aria-label="Follow up" className="flex max-w-[380px] flex-[1_1_320px] flex-col gap-4 border-l bg-panel px-4.5 py-5">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Test it properly</h2>
          <p className="text-[13px] leading-normal">An answer is a reading. To weigh it against ordinary days with fixed rules, send it to Corroborate.</p>
          <Button type="button" disabled={!answer?.statements.length} onClick={() => corroborate("all")}>Corroborate this</Button>
          <h2 className="mt-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Earlier questions in this case</h2>
          {earlier.data && earlier.data.total === 0 && <p className="text-[13px] text-muted-foreground">No questions asked yet.</p>}
          {earlier.error && <p className="text-[13px] text-status-error">The earlier questions could not be read.</p>}
          <ul className="flex flex-col gap-2">
            {earlier.data?.items.map((e) => (
              <li key={e.id} className="text-[13px]">
                <Link className="text-foreground underline-offset-2 hover:underline" aria-current={e.id === askId ? "page" : undefined} to={`?${new URLSearchParams({ ask: e.id, ...(phones.length ? { phones: phones.join(",") } : {}) })}`}>{e.question}</Link>
                <span className="block text-xs text-muted-foreground">
                  {e.asked_by_name || "Someone"}{e.created_at ? `, ${new Date(e.created_at).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" })}` : ""}
                  {e.status === "done" ? ` · ${e.statements ?? 0} ${e.statements === 1 ? "statement" : "statements"}` : e.status === "running" ? " · being answered" : " · not answered"}
                </span>
              </li>
            ))}
          </ul>
          {earlier.data?.next_offset != null && (
            <Button variant="ghost" size="sm" type="button" onClick={() => setMoreFrom((n) => n + 20)}>Show more ({(earlier.data.total - earlier.data.shown).toLocaleString("en-US")} not shown)</Button>
          )}
        </aside>
      </div>
    </div>
  )
}

export default AskPage
