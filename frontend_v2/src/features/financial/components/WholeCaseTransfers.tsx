import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { LevelBadge } from "@/features/phones/analysis/MoneyPairings"
import { candidateUrl } from "../lib/candidate-contract"
import { correctionMoney } from "../lib/correction-contract"
import { useFinancialDraft } from "../stores/financial-drafts"
import {
  useWholeCasePage,
  useWholeCaseRun,
  verifyWholeCaseScenario,
  wholeCaseFileUrl,
} from "../lib/whole-case-run"
import { Disclosure } from "./Disclosure"
import { SavePaymentSelection } from "./SavePaymentSelection"
import { WholeCasePager, WholeCaseProgress } from "./WholeCaseProgress"

const PAGE = 25
const LEVELS = ["strong", "moderate", "weak", "faint"] as const
const n = (value: number) => value.toLocaleString("en-US")

interface Side {
  key: string
  account_id: string
  account_label: string | null
  ordering_date: string
  description: string | null
}
interface StoredPair {
  debit_id: string
  credit_id: string
  currency: string
  amount_minor: string
  debit: Side
  credit: Side
  outcome?: string
  match_basis?: string
  date_gap_days?: number | null
  gap_days?: number
  level?: (typeof LEVELS)[number]
  within_tolerance?: boolean
  reasons?: { match: string[]; substantiation: string[] }
}
interface Summary {
  snapshot_sha256: string
  digest_covers?: string
  excluded_rows: number
  limitation: string
  rule: string
  by_level: Record<string, number>
  left_out_words: string | null
  date_unavailable_count: number
}
interface Figure {
  currency: string
  posting_rows: number
  movement_count: number
  paired_transfers: number
  paired_amount_minor: string
  unpaired_credits_minor: string
  unpaired_debits_minor: string
}

/** The comparison of every payment in a scope above one answer's size: stored, paged, with true counts. */
export function WholeCaseTransfers({
  caseId,
  start,
  end,
  population,
  tolerance,
  onSource,
}: {
  caseId: string
  start: string
  end: string
  population: "working" | "verified"
  tolerance: number
  onSource: (key: string) => void
}) {
  const { run, error, again } = useWholeCaseRun<Summary>(caseId, {
    kind: "transfers",
    population,
    tolerance_days: tolerance,
    ...(start ? { start_date: start } : {}),
    ...(end ? { end_date: end } : {}),
  })
  const [offset, setOffset] = useState(0)
  const candidates = useWholeCasePage<StoredPair>(caseId, run, "candidates", offset, PAGE)
  const [draft, setDraft] = useFinancialDraft(caseId, `transfer-whole:${start}:${end}:${population}:${tolerance}`, {
    snapshot: "",
    pairs: [] as { debit_id: string; credit_id: string }[],
    basis: "",
  })
  const summary = run?.summary
  const chosen = summary && draft.snapshot === summary.snapshot_sha256 ? draft.pairs : []
  const basis = summary && draft.snapshot === summary.snapshot_sha256 ? draft.basis : ""
  const used = new Set(chosen.flatMap((p) => [p.debit_id, p.credit_id]))
  const scenario = useMutation({
    retry: false,
    mutationFn: async () => {
      const raw = await fetchAPI<{
        case_id: string
        scenario_json: string
        scenario_sha256: string
        scenario_byte_count: number
        figures: Figure[]
      }>(candidateUrl(`whole-case-runs/${run!.id}/transfer-scenario`, caseId), {
        method: "POST",
        read: true,
        body: {
          expected_snapshot_sha256: summary!.snapshot_sha256,
          population,
          tolerance_days: tolerance,
          start_date: start || null,
          end_date: end || null,
          pairs: chosen,
          basis: basis.trim(),
        },
      })
      return verifyWholeCaseScenario(raw, caseId, chosen)
    },
  })
  if (!run || run.status !== "completed" || !summary)
    return <WholeCaseProgress run={run} error={error} noun="comparison" onAgain={again} />
  const counts = run.counts ?? {}
  const write = (pairs: typeof chosen, text = basis) =>
    setDraft({ snapshot: summary.snapshot_sha256, pairs, basis: text })
  const download = () => {
    const url = URL.createObjectURL(new Blob([scenario.data!.scenario_json], { type: "application/json" }))
    const a = document.createElement("a")
    a.href = url
    a.download = "loupe-transfer-scenario.json"
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return (
    <div className="space-y-3">
      <p>
        {n(counts.rows ?? 0)} payments · {n(summary.excluded_rows)} excluded · {n(counts.candidates ?? 0)} possible
        pairs. Every payment in this scope was compared.
      </p>
      <Disclosure label="How possible transfers are matched">
        <p>{summary.limitation}</p>
      </Disclosure>
      {summary.date_unavailable_count > 0 && (
        <p>{n(summary.date_unavailable_count)} payments have no transaction date and were not compared by date.</p>
      )}
      {(counts.reference_evidence ?? 0) > 0 && (
        <ReferenceEvidence caseId={caseId} run={run} onSource={onSource} />
      )}
      {!counts.candidates && <p>No pair within the chosen date tolerance. Every possible pair is listed below.</p>}
      <ul className="space-y-3">
        {candidates.data?.items.map((pair, i) => {
          const key = `${pair.debit_id}:${pair.credit_id}`
          const checked = chosen.some((p) => `${p.debit_id}:${p.credit_id}` === key)
          return (
            <li key={key} className="space-y-2 rounded border p-3">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  aria-label={`Pair transfer ${offset + i + 1}`}
                  checked={checked}
                  disabled={!checked && (used.has(pair.debit_id) || used.has(pair.credit_id))}
                  onChange={() => {
                    scenario.reset()
                    write(
                      checked
                        ? chosen.filter((p) => `${p.debit_id}:${p.credit_id}` !== key)
                        : [...chosen, { debit_id: pair.debit_id, credit_id: pair.credit_id }]
                    )
                  }}
                />
                <strong>{correctionMoney(pair.amount_minor, pair.currency)}</strong>
                <span>
                  {pair.outcome === "ambiguous"
                    ? "More than one possible match. Compare the alternatives."
                    : pair.match_basis === "exact_reference"
                      ? "Matching payment reference"
                      : "Matching amount and nearby date"}
                </span>
              </label>
              <PairSides pair={pair} label={String(offset + i + 1)} onSource={onSource} />
            </li>
          )
        })}
      </ul>
      <WholeCasePager
        label="transfer pairs"
        offset={offset}
        size={PAGE}
        total={candidates.data?.total ?? 0}
        onOffset={setOffset}
      />
      <GradedList caseId={caseId} run={run} summary={summary} onSource={onSource} />
      {(counts.candidates ?? 0) > 0 && (
        <fieldset className="space-y-2 rounded border p-3">
          <legend>Explain your selected transfers</legend>
          <p>{chosen.length} pairs selected. Each payment can belong to only one selected pair.</p>
          <label className="block">
            Why do you think these payments are transfers?
            <textarea
              aria-label="Basis for transfer pairings"
              className="block w-full rounded border bg-background p-2"
              maxLength={4096}
              value={basis}
              onChange={(e) => {
                scenario.reset()
                write(chosen, e.target.value)
              }}
            />
          </label>
          <Button disabled={!chosen.length || !basis.trim() || scenario.isPending} onClick={() => scenario.mutate()}>
            Compare totals using these transfers
          </Button>
        </fieldset>
      )}
      {scenario.isError && <p role="alert">Scenario unavailable. {scenario.error.message}</p>}
      {scenario.data && (
        <section aria-label="Paired transfer scenario" className="space-y-2 rounded border p-3">
          <h3 className="font-semibold">Totals using your selected transfers</h3>
          <p>Selected pairs count once here. These assumptions do not change ledger totals or verify a transfer.</p>
          {scenario.data.figures.map((f) => (
            <p key={f.currency}>
              {f.currency}: {n(f.posting_rows)} payments represented as {n(f.movement_count)} movements, including{" "}
              {f.paired_transfers} selected transfers. Paired amount: {correctionMoney(f.paired_amount_minor, f.currency)}{" "}
              · Unpaired credits: {correctionMoney(f.unpaired_credits_minor, f.currency)} · Unpaired debits:{" "}
              {correctionMoney(f.unpaired_debits_minor, f.currency)}
            </p>
          ))}
          <SavePaymentSelection
            caseId={caseId}
            ids={[...used]}
            analysis={{
              kind: "transfer-comparison",
              summary: `Saves ${chosen.length} selected transfer pairs, your explanation and the calculated totals.`,
              details: {
                snapshot_sha256: summary.snapshot_sha256,
                digest_covers: summary.digest_covers,
                scenario_sha256: scenario.data.scenario_sha256,
                whole_case_run: run.id,
                pairs: chosen,
                basis,
                figures: scenario.data.figures,
                start_date: start || null,
                end_date: end || null,
                tolerance_days: tolerance,
                population,
              },
            }}
          />
          <Button onClick={download}>Download scenario with source references</Button>
        </section>
      )}
      <a className="text-sm underline" href={wholeCaseFileUrl(caseId, run.id, "graded.jsonl")} download>
        Download every graded pair ({n(counts.graded ?? 0)})
      </a>
    </div>
  )
}

function PairSides({
  pair,
  label,
  onSource,
}: {
  pair: StoredPair
  label: string
  onSource: (key: string) => void
}) {
  return (
    <div className="grid items-center gap-3 md:grid-cols-[1fr_auto_1fr]">
      {[
        ["Money out", "debit", pair.debit],
        ["Money in", "credit", pair.credit],
      ].map(([title, name, side], i) => {
        const s = side as Side
        return (
          <div key={String(name)} className={i ? "md:col-start-3" : ""}>
            <p>
              {String(title)} · {s.account_label || `account ${s.account_id.slice(0, 8)}`}
            </p>
            <p>
              {s.ordering_date} · {s.description ?? "No description"}
            </p>
            <Button size="sm" variant="outline" onClick={() => onSource(s.key)}>
              Open {String(name)} source {label}
            </Button>
          </div>
        )
      })}
    </div>
  )
}

function GradedList({
  caseId,
  run,
  summary,
  onSource,
}: {
  caseId: string
  run: NonNullable<ReturnType<typeof useWholeCaseRun<Summary>>["run"]>
  summary: Summary
  onSource: (key: string) => void
}) {
  const [level, setLevel] = useState("")
  const [offset, setOffset] = useState(0)
  const page = useWholeCasePage<StoredPair>(caseId, run, level ? `graded@${level}` : "graded", offset, PAGE)
  const total = run.counts?.graded ?? 0
  return (
    <section aria-label="Every possible pair, graded" className="space-y-2 rounded border p-3">
      <h3 className="font-semibold">Every possible pair, graded ({n(total)})</h3>
      <p className="text-sm">
        {LEVELS.map((lv) => `${n(summary.by_level[lv] ?? 0)} ${lv}`).join(" · ")}
        {summary.left_out_words ? ` · ${summary.left_out_words}` : ""}
      </p>
      <Disclosure label="How the strength is set">
        <p>{summary.rule}</p>
      </Disclosure>
      <label className="flex items-center gap-1 text-sm">
        Strength
        <select
          value={level}
          onChange={(e) => {
            setLevel(e.target.value)
            setOffset(0)
          }}
          className="rounded border bg-background px-1 py-0.5"
        >
          <option value="">Every strength</option>
          {LEVELS.map((lv) => (
            <option key={lv} value={lv}>
              {`${lv[0].toUpperCase()}${lv.slice(1)} (${n(summary.by_level[lv] ?? 0)})`}
            </option>
          ))}
        </select>
      </label>
      {page.isError && <p role="alert">{page.error.message}</p>}
      <ul className="space-y-2">
        {page.data?.items.map((p, i) => (
          <li key={`${p.debit_id}:${p.credit_id}`} className="space-y-1 rounded border p-2 text-sm" aria-label={`Graded pair ${offset + i + 1}`}>
            <p className="flex flex-wrap items-center gap-2">
              {p.level && <LevelBadge level={p.level} />}
              <strong>{correctionMoney(p.amount_minor, p.currency)}</strong>
              <span>
                {p.debit.account_label ?? "an account"} ({p.debit.ordering_date}) → {p.credit.account_label ?? "an account"} (
                {p.credit.ordering_date})
              </span>
              {p.within_tolerance && <span className="text-xs">also in the candidates above</span>}
            </p>
            <p className="text-xs">How well matched: {p.reasons?.match.join("; ")}</p>
            <p className="text-xs">How substantiated: {p.reasons?.substantiation.join("; ") || "nothing beyond the match"}</p>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => onSource(p.debit_id)}>
                Open debit source (graded {offset + i + 1})
              </Button>
              <Button size="sm" variant="outline" onClick={() => onSource(p.credit_id)}>
                Open credit source (graded {offset + i + 1})
              </Button>
            </div>
          </li>
        ))}
      </ul>
      <WholeCasePager label="graded pairs" offset={offset} size={PAGE} total={page.data?.total ?? 0} onOffset={setOffset} />
    </section>
  )
}

function ReferenceEvidence({
  caseId,
  run,
  onSource,
}: {
  caseId: string
  run: NonNullable<ReturnType<typeof useWholeCaseRun<Summary>>["run"]>
  onSource: (key: string) => void
}) {
  const [offset, setOffset] = useState(0)
  const page = useWholeCasePage<{ left_id: string; right_id: string; reason: string; relation: string }>(
    caseId,
    run,
    "reference_evidence",
    offset,
    PAGE
  )
  return (
    <Disclosure label={<>Check repeated payment references ({n(run.counts?.reference_evidence ?? 0)})</>}>
      <ul className="space-y-2">
        {page.data?.items.map((item) => (
          <li key={`${item.left_id}:${item.right_id}:${item.relation}`} className="text-sm">
            <p>{item.reason}</p>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => onSource(item.left_id)}>
                Open first payment
              </Button>
              <Button size="sm" variant="outline" onClick={() => onSource(item.right_id)}>
                Open second payment
              </Button>
            </div>
          </li>
        ))}
      </ul>
      <WholeCasePager label="references" offset={offset} size={PAGE} total={page.data?.total ?? 0} onOffset={setOffset} />
    </Disclosure>
  )
}
