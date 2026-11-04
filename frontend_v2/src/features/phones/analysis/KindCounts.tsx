import type { AnalysisRun } from "./money-api"
import { kindCountWords } from "./typed-words"

/** A completed run's hits by kind of term (05 10.4, 12.4), every kind with its count, and what it could not compare. */
export function KindCounts({ run }: { run: AnalysisRun }) {
  const { items, missing } = kindCountWords(run.counts as Record<string, unknown> | null)
  return (
    <div className="text-sm" data-testid="kind-counts">
      <p className="font-medium">Matches by kind of term in this run</p>
      <ul className="list-disc pl-5">
        {items.map((i) => (
          <li key={i.kind} data-kind={i.kind}>{`${i.count.toLocaleString("en-US")} on ${i.words}`}</li>
        ))}
      </ul>
      <p className="text-muted-foreground">{missing} A record matching more than one kind is counted under each.</p>
    </div>
  )
}
