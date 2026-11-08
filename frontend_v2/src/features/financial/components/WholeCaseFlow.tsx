import { useState } from "react"
import { Button } from "@/components/ui/button"
import { correctionMoney } from "../lib/correction-contract"
import { useWholeCasePage, useWholeCaseRun } from "../lib/whole-case-run"
import { Disclosure } from "./Disclosure"
import { WholeCasePager, WholeCaseProgress } from "./WholeCaseProgress"

const PAGE = 25
const n = (value: number) => value.toLocaleString("en-US")

interface FlowTotal {
  currency: string
  incoming_minor: string
  outgoing_minor: string
  internal_minor: string
  net_minor: string
  internal_count: number
  movement_count: number
}
interface FlowSummary {
  totals: FlowTotal[]
  movements: number
  groups: number
  selected_accounts: { account_id: string; label: string | null }[]
  limitation: string
}
interface Movement {
  kind: "incoming" | "outgoing" | "internal"
  currency: string
  amount_minor: string
  transaction_ids: string[]
  label: string
}
interface Group {
  id: string
  label: string
  currency: string
  credits_minor: string
  debits_minor: string
  net_minor: string
  transaction_ids: string[]
}

/**
 * The account-flow view for a scope above one answer's size: the same classification the browser computes below the
 * limit, run where the rows are and read a page at a time, with every figure reconciled against the selected
 * accounts' own postings before anything is shown.
 */
export function WholeCaseFlow({
  caseId,
  accounts,
  snapshot,
  start,
  end,
  population,
  tolerance,
  pairs,
  onSource,
}: {
  caseId: string
  accounts: { account_id: string; label: string | null; rows: number }[]
  snapshot: string
  start: string
  end: string
  population: string
  tolerance: number
  pairs: { debit_id: string; credit_id: string }[]
  onSource: (key: string) => void
}) {
  const [chosen, setChosen] = useState<string[]>([])
  const [request, setRequest] = useState<Record<string, unknown> | null>(null)
  const flow = useWholeCaseRun<FlowSummary>(caseId, request ?? {}, "whole-case-runs/flow", request !== null)
  const run = flow.run?.status === "completed" ? flow.run : undefined
  return (
    <section aria-label="Account flow" className="space-y-2 rounded border p-3">
      <h3 className="font-semibold">Account flow from selected accounts</h3>
      <p className="text-sm">
        Choose the accounts to look from. Your {n(pairs.length)} selected transfer pairs count once each; every other
        payment of a chosen account is listed under its recorded counterparty.
      </p>
      <ul className="space-y-1 text-sm">
        {accounts.map((account) => (
          <li key={account.account_id}>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                aria-label={`Flow account ${account.label ?? account.account_id}`}
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
      <Button
        disabled={!chosen.length}
        onClick={() =>
          setRequest({
            expected_snapshot_sha256: snapshot,
            population,
            tolerance_days: tolerance,
            start_date: start || null,
            end_date: end || null,
            account_ids: [...chosen].sort(),
            pairs,
          })
        }
      >
        Show account flow
      </Button>
      {request && !run && <WholeCaseProgress run={flow.run} error={flow.error} noun="flow view" onAgain={flow.again} />}
      {run && run.summary && (
        <div className="space-y-3">
          {run.summary.totals.map((total) => (
            <p key={total.currency}>
              {total.currency}: {correctionMoney(total.incoming_minor, total.currency)} in ·{" "}
              {correctionMoney(total.outgoing_minor, total.currency)} out ·{" "}
              {correctionMoney(total.internal_minor, total.currency)} within selected accounts ({n(total.internal_count)}{" "}
              transfers) · net {correctionMoney(total.net_minor, total.currency)} over {n(total.movement_count)} movements
            </p>
          ))}
          <Disclosure label="What this view can and cannot say">
            <p>{run.summary.limitation}</p>
          </Disclosure>
          <FlowGroups caseId={caseId} run={run} total={run.summary.groups} onSource={onSource} />
          <FlowMovements caseId={caseId} run={run} onSource={onSource} />
        </div>
      )}
    </section>
  )
}

function FlowGroups({
  caseId,
  run,
  total,
  onSource,
}: {
  caseId: string
  run: NonNullable<ReturnType<typeof useWholeCaseRun<FlowSummary>>["run"]>
  total: number
  onSource: (key: string) => void
}) {
  const [offset, setOffset] = useState(0)
  const page = useWholeCasePage<Group>(caseId, run, "groups", offset, PAGE)
  return (
    <section aria-label="Flow counterparties" className="space-y-2">
      <h4 className="font-medium">Counterparties ({n(total)})</h4>
      <ul className="space-y-1 text-sm">
        {page.data?.items.map((group) => (
          <li key={group.id} className="flex flex-wrap items-center gap-2">
            <span>
              {group.label} · in {correctionMoney(group.credits_minor, group.currency)} · out{" "}
              {correctionMoney(group.debits_minor, group.currency)} · net {correctionMoney(group.net_minor, group.currency)} ·{" "}
              {n(group.transaction_ids.length)} payments
            </span>
            <Button size="sm" variant="outline" onClick={() => onSource(group.transaction_ids[0])}>
              Open first payment
            </Button>
          </li>
        ))}
      </ul>
      <WholeCasePager label="counterparties" offset={offset} size={PAGE} total={page.data?.total ?? 0} onOffset={setOffset} />
    </section>
  )
}

function FlowMovements({
  caseId,
  run,
  onSource,
}: {
  caseId: string
  run: NonNullable<ReturnType<typeof useWholeCaseRun<FlowSummary>>["run"]>
  onSource: (key: string) => void
}) {
  const [kind, setKind] = useState("")
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState("")
  const page = useWholeCasePage<Movement>(caseId, run, kind ? `movements@${kind}` : "movements", offset, PAGE, search)
  const counts = run.counts ?? {}
  return (
    <section aria-label="Flow movements" className="space-y-2">
      <h4 className="font-medium">Every movement ({n(counts.movements ?? 0)})</h4>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <label className="flex items-center gap-1">
          Direction
          <select
            className="rounded border bg-background px-1 py-0.5"
            value={kind}
            onChange={(e) => {
              setKind(e.target.value)
              setOffset(0)
            }}
          >
            <option value="">All</option>
            {["incoming", "outgoing", "internal"].map((value) => (
              <option key={value} value={value}>
                {`${value[0].toUpperCase()}${value.slice(1)} (${n(counts[`movements@${value}`] ?? 0)})`}
              </option>
            ))}
          </select>
        </label>
        <input
          aria-label="Search movements"
          placeholder="Counterparty, account or amount"
          className="border bg-background p-1"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setOffset(0)
          }}
        />
      </div>
      {page.isError && <p role="alert">{page.error.message}</p>}
      <ul className="space-y-1 text-sm">
        {page.data?.items.map((movement, i) => (
          <li key={movement.transaction_ids.join(":")} className="flex flex-wrap items-center gap-2">
            <span>
              {movement.kind === "incoming" ? "In" : movement.kind === "outgoing" ? "Out" : "Internal"} ·{" "}
              {correctionMoney(movement.amount_minor, movement.currency)} · {movement.label}
            </span>
            <Button size="sm" variant="outline" onClick={() => onSource(movement.transaction_ids[0])}>
              Open movement {offset + i + 1}
            </Button>
          </li>
        ))}
      </ul>
      <WholeCasePager label="movements" offset={offset} size={PAGE} total={page.data?.total ?? 0} onOffset={setOffset} />
    </section>
  )
}
