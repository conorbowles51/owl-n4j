import { useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import { LevelBadge } from "@/features/phones/analysis/MoneyPairings"
import { correctionMoney } from "../lib/correction-contract"
import type { TransferInputs } from "../lib/ledger-transfers"
import { Disclosure } from "./Disclosure"

const LEVELS = ["strong", "moderate", "weak", "faint"] as const
const PAGE = 25

/**
 * Every possible transfer pair in the scope, strongest first, each with its strength by a stated rule (never a
 * model) and its reasons in two parts: how well matched, how substantiated. Weak and faint pairs are listed, not
 * hidden; what the search bound leaves out is stated. A pair here is a possibility to check; only the candidates
 * above, inside the chosen date tolerance, can be selected for a scenario.
 */
export function GradedTransferPairs({
  data,
  onSource,
}: {
  data: TransferInputs
  onSource: (key: string) => void
}) {
  const graded = data.graded
  const [level, setLevel] = useState<"" | (typeof LEVELS)[number]>("")
  const [page, setPage] = useState(0)
  const rows = useMemo(() => new Map(data.rows.map((r) => [r.key, r])), [data.rows])
  if (!graded) return null
  const list = level ? graded.pairs.filter((p) => p.level === level) : graded.pairs
  const shown = list.slice(page * PAGE, page * PAGE + PAGE)
  return (
    <section aria-label="Every possible pair, graded" className="space-y-2 rounded border p-3">
      <h3 className="font-semibold">
        Every possible pair, graded ({graded.pairs.length.toLocaleString("en-US")})
      </h3>
      <p className="text-sm">
        {LEVELS.map((lv) => `${(graded.by_level[lv] ?? 0).toLocaleString("en-US")} ${lv}`).join(" · ")}
        {graded.left_out_words ? ` · ${graded.left_out_words}` : ""}
      </p>
      <Disclosure label="How the strength is set">
        <p>{graded.rule}</p>
      </Disclosure>
      <label className="flex items-center gap-1 text-sm">
        Strength
        <select
          value={level}
          onChange={(e) => {
            setLevel(e.target.value as "" | (typeof LEVELS)[number])
            setPage(0)
          }}
          className="rounded border bg-background px-1 py-0.5"
        >
          <option value="">Every strength</option>
          {LEVELS.map((lv) => (
            <option key={lv} value={lv}>
              {`${lv[0].toUpperCase()}${lv.slice(1)} (${graded.by_level[lv] ?? 0})`}
            </option>
          ))}
        </select>
      </label>
      {list.length === 0 && <p className="text-sm">No possible pair at this strength in this scope.</p>}
      <ul className="space-y-2">
        {shown.map((p, n) => {
          const debit = rows.get(p.debit_id)
          const credit = rows.get(p.credit_id)
          const at = page * PAGE + n + 1
          return (
            <li key={`${p.debit_id}:${p.credit_id}`} className="space-y-1 rounded border p-2 text-sm" aria-label={`Graded pair ${at}`}>
              <p className="flex flex-wrap items-center gap-2">
                <LevelBadge level={p.level} />
                <strong>{correctionMoney(p.amount_minor, p.currency)}</strong>
                <span>
                  {debit?.account_label ?? "an account"} ({debit?.ordering_date}) → {credit?.account_label ?? "an account"} ({credit?.ordering_date})
                </span>
                {p.within_tolerance && <span className="text-xs">also in the candidates above</span>}
              </p>
              <p className="text-xs">How well matched: {p.reasons.match.join("; ")}</p>
              <p className="text-xs">
                How substantiated: {p.reasons.substantiation.join("; ") || "nothing beyond the match"}
              </p>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => onSource(p.debit_id)}>
                  Open debit source (graded {at})
                </Button>
                <Button size="sm" variant="outline" onClick={() => onSource(p.credit_id)}>
                  Open credit source (graded {at})
                </Button>
              </div>
            </li>
          )
        })}
      </ul>
      {list.length > PAGE && (
        <div className="flex items-center gap-2 text-sm">
          <Button size="sm" disabled={!page} onClick={() => setPage((v) => v - 1)}>
            Previous graded pairs
          </Button>
          <span>
            {page * PAGE + 1}–{Math.min(list.length, (page + 1) * PAGE)} of {list.length.toLocaleString("en-US")}
          </span>
          <Button size="sm" disabled={(page + 1) * PAGE >= list.length} onClick={() => setPage((v) => v + 1)}>
            Next graded pairs
          </Button>
        </div>
      )}
    </section>
  )
}
