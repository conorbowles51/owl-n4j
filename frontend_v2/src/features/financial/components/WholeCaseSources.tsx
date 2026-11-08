import { useState } from "react"
import { Button } from "@/components/ui/button"
import { correctionMoney } from "../lib/correction-contract"
import { useWholeCasePage, useWholeCaseRun } from "../lib/whole-case-run"
import { LedgerSourceDialog } from "./LedgerSourceDialog"
import { WholeCasePager, WholeCaseProgress } from "./WholeCaseProgress"

const PAGE = 25
const n = (value: number) => value.toLocaleString("en-US")

interface SourcesAccount {
  account_id: string
  label: string | null
  steps_back: number
  outside_credits: number
  outside_credits_minor: string
  transfers_in: number
  transfers_in_minor: string
  not_followed: number
  not_followed_minor: string
}
interface SourcesSummary {
  currency: string
  steps: number
  accounts: SourcesAccount[]
  outside_credits: number
  transfers_in: number
  not_followed: number
  stopped: boolean
  stop_words: string | null
  continue_with_steps: number | null
  limitations: string[]
}
interface SourceRow {
  key: string
  account_id: string
  account_label: string | null
  ordering_date: string
  amount_minor: string
  currency: string
  description: string | null
}
interface TransferIn {
  debit_id: string
  credit_id: string
  amount_minor: string
  currency: string
  from_account_label: string | null
  to_account_label: string | null
  debit_date: string
  credit_date: string
  steps_back: number
}

/**
 * Where the money came into the chosen accounts: a backward walk over the selected transfers, bounded by steps.
 * Every credit of a reached account is a followed transfer, a stop counted and stated, or an outside source.
 */
export function WholeCaseSources({
  caseId,
  accounts,
  snapshot,
  currency,
  start,
  end,
  population,
  tolerance,
  pairs,
  pairBasis,
}: {
  caseId: string
  accounts: { account_id: string; label: string | null; rows: number }[]
  snapshot: string
  currency: string
  start: string | null
  end: string | null
  population: string
  tolerance: number
  pairs: { debit_id: string; credit_id: string }[]
  pairBasis: string
}) {
  const [source, setSource] = useState<string | null>(null)
  const [chosen, setChosen] = useState<string[]>([])
  const [steps, setSteps] = useState(3)
  const [request, setRequest] = useState<Record<string, unknown> | null>(null)
  const walk = useWholeCaseRun<SourcesSummary>(caseId, request ?? {}, "whole-case-runs/trace-sources", request !== null)
  const run = walk.run?.status === "completed" ? walk.run : undefined
  const submit = (limit: number) => {
    setSteps(limit)
    setRequest({
      expected_snapshot_sha256: snapshot,
      population,
      tolerance_days: tolerance,
      start_date: start || null,
      end_date: end || null,
      currency,
      steps: limit,
      account_ids: [...chosen].sort(),
      pairs,
      basis: pairBasis,
    })
  }
  return (
    <section aria-label="Where the money came from" className="space-y-2 rounded border p-3">
      <h3 className="font-semibold">Where the money came from</h3>
      <p className="text-sm">
        Walks your {n(pairs.length)} selected transfers backward from the chosen accounts, a stated number of steps.
        Every money-in payment of a reached account is counted exactly once: a followed transfer, a transfer not
        followed past the step limit (counted and stated), or an outside source.
      </p>
      <ul className="space-y-1 text-sm">
        {accounts.map((account) => (
          <li key={account.account_id}>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                aria-label={`Sources account ${account.label ?? account.account_id}`}
                checked={chosen.includes(account.account_id)}
                onChange={() =>
                  setChosen(
                    chosen.includes(account.account_id)
                      ? chosen.filter((id) => id !== account.account_id)
                      : [...chosen, account.account_id]
                  )
                }
              />
              {account.label ?? `Account ${account.account_id.slice(0, 8)}`} ({n(account.rows)} payments)
            </label>
          </li>
        ))}
      </ul>
      <label className="block text-sm">
        Steps back
        <input
          aria-label="Steps back"
          type="number"
          min={0}
          max={25}
          className="block w-24 border bg-background p-1"
          value={steps}
          onChange={(e) => setSteps(Number(e.target.value))}
        />
      </label>
      <Button disabled={!chosen.length || (pairs.length > 0 && !pairBasis.trim())} onClick={() => submit(steps)}>
        Walk back {steps} {steps === 1 ? "step" : "steps"}
      </Button>
      {pairs.length > 0 && !pairBasis.trim() && (
        <p className="text-sm">Record why the selected payments are transfers (step 2 above) first.</p>
      )}
      {request && !run && <WholeCaseProgress run={walk.run} error={walk.error} noun="backward walk" onAgain={walk.again} />}
      {run && run.summary && (
        <div className="space-y-3">
          <p>
            {n(run.summary.transfers_in)} transfers followed in · {n(run.summary.outside_credits)} outside sources ·{" "}
            {n(run.summary.not_followed)} transfers not followed. {run.summary.limitations[0]}
          </p>
          {run.summary.stop_words && <p role="status">{run.summary.stop_words}</p>}
          {run.summary.continue_with_steps !== null && (
            <Button onClick={() => submit(run.summary!.continue_with_steps!)}>Continue one more step</Button>
          )}
          <ul className="space-y-1 text-sm">
            {run.summary.accounts.map((account) => (
              <li key={account.account_id}>
                {account.label ?? account.account_id} ({account.steps_back}{" "}
                {account.steps_back === 1 ? "step" : "steps"} back):{" "}
                {correctionMoney(account.transfers_in_minor, run.summary!.currency)} in over {n(account.transfers_in)}{" "}
                followed transfers · {correctionMoney(account.outside_credits_minor, run.summary!.currency)} in over{" "}
                {n(account.outside_credits)} outside sources
                {account.not_followed > 0 &&
                  ` · ${correctionMoney(account.not_followed_minor, run.summary!.currency)} over ${n(account.not_followed)} transfers not followed`}
              </li>
            ))}
          </ul>
          <TransfersIn caseId={caseId} run={run} onSource={setSource} />
          <OutsideSources caseId={caseId} run={run} onSource={setSource} />
        </div>
      )}
      {source && <LedgerSourceDialog caseId={caseId} transactionId={source} onClose={() => setSource(null)} />}
    </section>
  )
}

function TransfersIn({
  caseId,
  run,
  onSource,
}: {
  caseId: string
  run: NonNullable<ReturnType<typeof useWholeCaseRun<SourcesSummary>>["run"]>
  onSource: (key: string) => void
}) {
  const [offset, setOffset] = useState(0)
  const page = useWholeCasePage<TransferIn>(caseId, run, "transfers", offset, PAGE)
  return (
    <section aria-label="Transfers followed in" className="space-y-1">
      <h4 className="font-medium">Transfers followed in ({n(run.counts?.transfers ?? 0)})</h4>
      <ul className="space-y-1 text-sm">
        {page.data?.items.map((item, i) => (
          <li key={`${item.debit_id}:${item.credit_id}`} className="flex flex-wrap items-center gap-2">
            <span>
              {correctionMoney(item.amount_minor, item.currency)} · {item.from_account_label ?? "an account"} (
              {item.debit_date}) → {item.to_account_label ?? "an account"} ({item.credit_date}) · {item.steps_back}{" "}
              {item.steps_back === 1 ? "step" : "steps"} back
            </span>
            <Button size="sm" variant="outline" onClick={() => onSource(item.debit_id)}>
              Open paying side {offset + i + 1}
            </Button>
          </li>
        ))}
      </ul>
      <WholeCasePager label="transfers" offset={offset} size={PAGE} total={page.data?.total ?? 0} onOffset={setOffset} />
    </section>
  )
}

function OutsideSources({
  caseId,
  run,
  onSource,
}: {
  caseId: string
  run: NonNullable<ReturnType<typeof useWholeCaseRun<SourcesSummary>>["run"]>
  onSource: (key: string) => void
}) {
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState("")
  const page = useWholeCasePage<SourceRow>(caseId, run, "sources", offset, PAGE, search)
  return (
    <section aria-label="Outside sources" className="space-y-1">
      <h4 className="font-medium">Outside sources ({n(run.counts?.sources ?? 0)})</h4>
      <input
        aria-label="Search outside sources"
        placeholder="Name, date, description or amount"
        className="block w-full border bg-background p-1 text-sm"
        value={search}
        onChange={(e) => {
          setSearch(e.target.value)
          setOffset(0)
        }}
      />
      <ul className="space-y-1 text-sm">
        {page.data?.items.map((row, i) => (
          <li key={row.key} className="flex flex-wrap items-center gap-2">
            <span>
              {row.ordering_date} · {row.account_label ?? row.account_id} ·{" "}
              {correctionMoney(row.amount_minor, row.currency)} · {row.description ?? "No description"}
            </span>
            <Button size="sm" variant="outline" onClick={() => onSource(row.key)}>
              Open source {offset + i + 1}
            </Button>
          </li>
        ))}
      </ul>
      <WholeCasePager label="outside sources" offset={offset} size={PAGE} total={page.data?.total ?? 0} onOffset={setOffset} />
    </section>
  )
}
