import { useState } from "react"
import { Button } from "@/components/ui/button"
import type { TimelineResponse } from "@/features/timeline/api"
import { correctionMoney } from "../lib/correction-contract"
import { chronologyLabels, type LedgerTimeline } from "../lib/ledger-timeline"
import { useWholeCasePage, useWholeCaseRun, wholeCaseFileUrl } from "../lib/whole-case-run"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"
import { Disclosure } from "./Disclosure"
import { SavePaymentSelection } from "./SavePaymentSelection"
import { WholeCasePager, WholeCaseProgress } from "./WholeCaseProgress"

const PAGE = 50
const n = (value: number) => value.toLocaleString("en-US")

interface Month {
  month: string
  payments: number
  credits: number
  debits: number
  totals: Record<string, { credits_minor: string; debits_minor: string }>
}
interface Summary {
  snapshot_sha256: string
  digest_covers?: string
  excluded_rows: number
  limitation: string
  months: Month[]
}

/**
 * Every payment in a scope above one answer's size, month by month: each month's count opens to its payments, and
 * a search reads the whole stored timeline. Case events are shown beside the month they fall in.
 */
export function WholeCaseTimeline({
  caseId,
  params,
  population,
  events,
  onSource,
}: {
  caseId: string
  params: LedgerQueryParams
  population: string
  events: TimelineResponse | null
  onSource: (key: string) => void
}) {
  const { run, error, again } = useWholeCaseRun<Summary>(caseId, {
    kind: "timeline",
    population,
    ...(params.accountId ? { account_id: params.accountId } : {}),
    ...(params.accountIds?.length ? { account_ids: params.accountIds } : {}),
    ...(params.accountHolders?.length ? { account_holders: params.accountHolders } : {}),
    ...(params.startDate ? { start_date: params.startDate } : {}),
    ...(params.endDate ? { end_date: params.endDate } : {}),
  })
  const [month, setMonth] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<string[]>([])
  const section = month ? `rows@${month}` : "rows"
  const open = Boolean(month || search.trim())
  const page = useWholeCasePage<LedgerTimeline["rows"][number]>(caseId, open ? run : undefined, section, offset, PAGE, search)
  if (!run || run.status !== "completed" || !run.summary)
    return <WholeCaseProgress run={run} error={error} noun="timeline" onAgain={again} />
  const summary = run.summary
  const monthEvents = (key: string) => (events?.events ?? []).filter((e) => e.date?.slice(0, 7) === key)
  return (
    <div className="space-y-3">
      <p>
        {n(run.counts?.rows ?? 0)} payments; {n(summary.excluded_rows)} excluded, across {n(summary.months.length)} months.
        Open a month to read its payments, or search them all. The account filter applies to payments. Case events use
        the selected dates.
      </p>
      <Disclosure label="How the timeline was assembled">
        <p>{summary.limitation}</p>
      </Disclosure>
      <label>
        Search every payment in this timeline{" "}
        <input
          aria-label="Search every payment"
          className="border bg-background p-2"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setOffset(0)
          }}
        />
      </label>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left">
            <th>Month</th>
            <th>Payments</th>
            <th>In</th>
            <th>Out</th>
            <th>Case events</th>
          </tr>
        </thead>
        <tbody>
          {summary.months.map((m) => (
            <tr key={m.month} className="border-t">
              <td>{m.month}</td>
              <td>
                <Button
                  size="sm"
                  variant={month === m.month ? "primary" : "outline"}
                  aria-label={`Open ${n(m.payments)} payments in ${m.month}`}
                  onClick={() => {
                    setMonth(month === m.month ? null : m.month)
                    setOffset(0)
                  }}
                >
                  {n(m.payments)}
                </Button>
              </td>
              <td>{Object.entries(m.totals).map(([c, t]) => correctionMoney(t.credits_minor, c)).join(" · ")}</td>
              <td>{Object.entries(m.totals).map(([c, t]) => correctionMoney(t.debits_minor, c)).join(" · ")}</td>
              <td>{n(monthEvents(m.month).length)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {open && (
        <section aria-label={month ? `Payments in ${month}` : "Search results"} className="space-y-2">
          <p role="status">
            {page.isPending ? "Reading…" : `${n(page.data?.total ?? 0)} payments ${month ? `in ${month}` : ""}${search.trim() ? ` matching “${search.trim()}”` : ""}.`}
          </p>
          {page.isError && <p role="alert">{page.error.message}</p>}
          {month && monthEvents(month).length > 0 && (
            <Disclosure label={<>Case events in {month} ({n(monthEvents(month).length)})</>}>
              <ul className="space-y-1 text-sm">
                {monthEvents(month).map((e) => (
                  <li key={e.key}>
                    {e.date?.slice(0, 10)} · {e.name} · {e.type}
                  </li>
                ))}
              </ul>
            </Disclosure>
          )}
          <ol className="space-y-3">
            {page.data?.items.map((row) => (
              <li key={row.key} className="border-l-2 border-primary pl-4">
                <label className="mb-2 flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    aria-label={`Select ${row.description || "payment"} on ${row.chronology_date}`}
                    checked={selected.includes(row.key)}
                    onChange={(e) =>
                      setSelected((previous) =>
                        e.target.checked ? [...new Set([...previous, row.key])] : previous.filter((key) => key !== row.key)
                      )
                    }
                  />
                  Include in my observation
                </label>
                <p className="font-semibold">{row.chronology_date} · Payment</p>
                <p>
                  {row.account_label} · {row.direction} {correctionMoney(row.amount_minor, row.currency)}
                </p>
                <p>{chronologyLabels[row.chronology_basis]}</p>
                <p>{row.description}</p>
                <Button variant="outline" onClick={() => onSource(row.key)}>
                  Open payment
                </Button>
              </li>
            ))}
          </ol>
          <WholeCasePager label="timeline items" offset={offset} size={PAGE} total={page.data?.total ?? 0} onOffset={setOffset} />
        </section>
      )}
      <p className="text-sm">{selected.length} payments selected across every month.</p>
      <SavePaymentSelection
        caseId={caseId}
        ids={selected}
        analysis={{
          kind: "payment-event-observation",
          summary: "Saves the selected payments together with your explanation. Nearby dates alone do not establish a connection.",
          details: {
            snapshot_sha256: summary.snapshot_sha256,
            digest_covers: summary.digest_covers,
            captured_at: run.created_at,
            whole_case_run: run.id,
            population,
            scope: params,
          },
        }}
      />
      <a className="text-sm underline" href={wholeCaseFileUrl(caseId, run.id, "rows.jsonl")} download>
        Download every payment in this timeline ({n(run.counts?.rows ?? 0)})
      </a>
    </div>
  )
}
