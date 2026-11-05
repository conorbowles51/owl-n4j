import { useState } from "react"
import { Button } from "@/components/ui/button"
import { correctionMoney } from "../lib/correction-contract"
import type { PatternReview } from "../lib/pattern-review"
import { useWholeCasePage, useWholeCaseRun, type WholeCaseRequest } from "../lib/whole-case-run"
import { Disclosure } from "./Disclosure"
import { PatternCard } from "./FinancialPatternReview"
import { WholeCasePager, WholeCaseProgress } from "./WholeCaseProgress"

const PAGE = 10
const MEMBERS = 50
const n = (value: number) => value.toLocaleString("en-US")
const KIND_WORDS: Record<string, string> = {
  repeated_counterparty: "Repeated names",
  repeated_equal_amount: "Repeated equal amounts",
  equal_amount_in_and_out: "Equal amounts in and out",
  split_payment_threshold: "Smaller payments reaching the threshold",
  possible_transfer_chain: "Possible chains between accounts",
  possible_return_flow: "Possible returns to the starting account",
}

type Hypothesis = PatternReview["hypotheses"][number] & { sources_total: number; sources_start: number }
type Summary = Omit<PatternReview, "hypotheses" | "date_unavailable_ids"> & {
  by_kind: Record<string, number>
  date_unavailable_count: number
  paths_not_searched?: number
  paths_words?: string | null
}

/** Every pattern in a scope above one answer's size: stored, paged, by kind, each group opening to all its payments. */
export function WholeCasePatterns({
  caseId,
  request,
  onSource,
}: {
  caseId: string
  request: Omit<WholeCaseRequest, "kind">
  onSource: (key: string) => void
}) {
  const { run, error, again } = useWholeCaseRun<Summary>(caseId, { kind: "patterns", ...request })
  const [kind, setKind] = useState("")
  const [offset, setOffset] = useState(0)
  const page = useWholeCasePage<Hypothesis>(caseId, run, kind ? `hypotheses@${kind}` : "hypotheses", offset, PAGE)
  if (!run || run.status !== "completed" || !run.summary)
    return <WholeCaseProgress run={run} error={error} noun="pattern check" onAgain={again} />
  const summary = run.summary
  const total = run.counts?.hypotheses ?? 0
  return (
    <div className="space-y-3">
      <Disclosure className="text-sm" label="What these checks cover">
        <p>{summary.limitation}</p>
      </Disclosure>
      <p>
        {n(summary.reviewed_rows)} payments checked; {n(summary.date_unavailable_count)} payments need a date checked
        before they can be included. {n(total)} possible patterns.
      </p>
      {summary.paths_words && <p role="status">{summary.paths_words}</p>}
      <label className="flex items-center gap-1 text-sm">
        Show
        <select
          aria-label="Pattern kind"
          className="rounded border bg-background px-1 py-0.5"
          value={kind}
          onChange={(e) => {
            setKind(e.target.value)
            setOffset(0)
          }}
        >
          <option value="">Every kind ({n(total)})</option>
          {Object.entries(summary.by_kind).map(([name, count]) => (
            <option key={name} value={name}>
              {`${KIND_WORDS[name] ?? name} (${n(count)})`}
            </option>
          ))}
        </select>
      </label>
      {page.isError && <p role="alert">{page.error.message}</p>}
      {!total && (
        <p>No patterns matched these checks. Try a different account, date range or number of days between payments.</p>
      )}
      {page.data?.items.map((h) => (
        <div key={h.id} className="space-y-2">
          <PatternCard
            scope={{ ...summary, hypotheses: [h], date_unavailable_ids: [] }}
            hypothesis={h}
            onSource={onSource}
          />
          {h.sources_total > h.sources.length && (
            <GroupPayments caseId={caseId} run={run} hypothesis={h} onSource={onSource} />
          )}
        </div>
      ))}
      <WholeCasePager label="patterns" offset={offset} size={PAGE} total={page.data?.total ?? 0} onOffset={setOffset} />
    </div>
  )
}

function GroupPayments({
  caseId,
  run,
  hypothesis: h,
  onSource,
}: {
  caseId: string
  run: Parameters<typeof useWholeCasePage>[1]
  hypothesis: Hypothesis
  onSource: (key: string) => void
}) {
  const [offset, setOffset] = useState(MEMBERS)
  const page = useWholeCasePage<Hypothesis["sources"][number]>(caseId, run, "sources", h.sources_start + offset, MEMBERS)
  return (
    <Disclosure label={<>All {n(h.sources_total)} payments in this group</>}>
      <p className="text-sm">
        The first {n(h.sources.length)} are above. A saved explanation cites up to {n(h.sources.length)} payments, so
        narrow the dates to save this group; every payment can be opened here.
      </p>
      {page.data?.items.map((s, i) => (
        <div key={s.row.key}>
          <p>
            {s.row.account_label} · {s.row.chronology_date} · {s.row.direction === "credit" ? "Credit" : "Debit"} ·{" "}
            {correctionMoney(s.row.amount_minor, s.row.currency)} · {s.row.description}
          </p>
          <Button variant="outline" onClick={() => onSource(s.row.key)}>
            Open payment {offset + i + 1}
          </Button>
        </div>
      ))}
      <WholeCasePager label="payments" offset={offset} size={MEMBERS} total={h.sources_total} onOffset={setOffset} />
    </Disclosure>
  )
}
